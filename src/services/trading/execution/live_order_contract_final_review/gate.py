from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_contract_final_review.models import (
    REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES,
    LiveOrderContractFinalReview,
    LiveOrderContractFinalReviewValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract_final_review.policy import (
    LiveOrderContractFinalReviewConfig,
)


class LiveOrderContractFinalReviewGate:
    def __init__(self, config: LiveOrderContractFinalReviewConfig | None = None):
        self.config = config or LiveOrderContractFinalReviewConfig.from_config()

    def validate(self, final_review: LiveOrderContractFinalReview) -> LiveOrderContractFinalReviewValidationReport:
        blockers = list(final_review.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check("status_approved", final_review.status == "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY", "INVALID_INPUT")
        check("scope_pre_mt5_only", final_review.scope == "PRE_MT5_MAPPING_BOUNDARY_ONLY", "INVALID_INPUT")
        check(
            "pre_mt5_mapping_boundary_workflow_allowed",
            final_review.pre_mt5_mapping_boundary_workflow_allowed is True,
            "PRE_MT5_MAPPING_NOT_ALLOWED",
        )
        check("confirmation_phrase_valid", final_review.confirmation_phrase_valid is True, "WRONG_CONFIRMATION_PHRASE")
        check("live_execution_disabled", final_review.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_submission_disabled", final_review.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
        check("execution_disabled", final_review.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
        check("non_executable", final_review.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("no_mt5_payload", final_review.mt5_payload_created is False, "MT5_PAYLOAD_NOT_ALLOWED")
        check("not_order_sent", final_review.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
        check("hard_live_block", final_review.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_contract_not_ready", final_review.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
        check("order_mapping_disabled", final_review.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("broker_mapping_absent", final_review.broker_mapping_created is False, "PRE_MT5_MAPPING_NOT_ALLOWED")
        check("raw_values_absent", final_review.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
        check("executable_order_absent", final_review.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("source_refs_present", bool(final_review.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(final_review.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(final_review.idempotency_key), "MISSING_IDEMPOTENCY")

        slot_validations = list(final_review.slot_validations or [])
        slot_types = {slot.slot_type for slot in slot_validations}
        missing = [item for item in REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES if item not in slot_types]
        blocked = [
            slot.slot_type
            for slot in slot_validations
            if slot.blockers
            or slot.status != "VALIDATION_ONLY_READY"
            or slot.raw_value_stored
            or slot.executable_value
            or slot.mt5_payload_value
            or slot.order_request_value
            or slot.broker_mapping_created
            or not slot.validation_only_ready
            or not slot.final_human_review_required
        ]
        check("exactly_nine_slot_validations", len(slot_validations) == 9 and not missing, "MISSING_REQUIRED_SLOT_VALIDATIONS")
        check("slot_validations_safe", not blocked, "MISSING_REQUIRED_SLOT_VALIDATIONS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = LiveOrderContractFinalReviewValidationReport(
            validation_report_id=f"live_order_contract_final_review_validation_{_digest(final_review.final_review_id)[:16]}",
            created_at=now_utc_iso(),
            source_final_review_id=final_review.final_review_id,
            valid=valid,
            pre_mt5_mapping_boundary_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            confirmation_phrase_valid=final_review.confirmation_phrase_valid and valid,
            slot_validations_count=len(slot_validations),
            passed_slot_validations_count=len(slot_validations) if valid else 0,
            blocked_slot_validations_count=len(blocked),
            missing_slot_validations_count=len(missing),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(final_review.warnings or []),
            source_refs=list(final_review.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
