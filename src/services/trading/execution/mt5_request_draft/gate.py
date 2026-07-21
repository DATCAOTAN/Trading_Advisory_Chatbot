from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_request_draft.models import (
    REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES,
    MT5RequestDraftBoundary,
    MT5RequestDraftValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_draft.policy import MT5RequestDraftConfig


class MT5RequestDraftGate:
    def __init__(self, config: MT5RequestDraftConfig | None = None):
        self.config = config or MT5RequestDraftConfig.from_config()

    def validate(self, request_draft: MT5RequestDraftBoundary) -> MT5RequestDraftValidationReport:
        blockers = list(request_draft.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check("status_created", request_draft.status == "REQUEST_DRAFT_CREATED", "INVALID_INPUT")
        check("scope_final_approval_only", request_draft.scope == "FINAL_DRAFT_APPROVAL_ONLY", "INVALID_INPUT")
        check(
            "final_approval_workflow_allowed",
            request_draft.mt5_request_draft_final_approval_workflow_allowed is True,
            "MT5_REQUEST_DRAFT_WORKFLOW_NOT_ALLOWED",
        )
        check("live_execution_disabled", request_draft.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_submission_disabled", request_draft.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
        check("execution_disabled", request_draft.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
        check("non_executable", request_draft.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("no_mt5_payload", request_draft.mt5_payload_created is False, "MT5_PAYLOAD_NOT_ALLOWED")
        check("no_mt5_request_dict", request_draft.mt5_request_dict_created is False, "MT5_REQUEST_DICT_NOT_ALLOWED")
        check("no_mt5_constants", request_draft.mt5_constants_used is False, "MT5_CONSTANT_NOT_ALLOWED")
        check("no_broker_submission", request_draft.broker_submission_created is False, "BROKER_SUBMISSION_NOT_ALLOWED")
        check("not_order_sent", request_draft.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
        check("hard_live_block", request_draft.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_contract_not_ready", request_draft.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
        check("order_mapping_disabled", request_draft.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("broker_mapping_absent", request_draft.broker_mapping_created is False, "BROKER_MAPPING_NOT_ALLOWED")
        check("raw_values_absent", request_draft.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
        check("executable_order_absent", request_draft.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("source_refs_present", bool(request_draft.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(request_draft.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(request_draft.idempotency_key), "MISSING_IDEMPOTENCY")

        fields = list(request_draft.draft_fields or [])
        field_categories = {item.field_category for item in fields}
        missing = [item for item in REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES if item not in field_categories]
        invalid = [
            item.field_category
            for item in fields
            if item.blockers
            or item.status != "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY"
            or not item.draft_field_present
            or item.draft_value_created
            or not item.draft_value_redacted
            or item.raw_value_stored
            or item.mt5_payload_value_created
            or item.mt5_request_field_value_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
            or not item.final_draft_approval_required
        ]
        check(
            "required_draft_field_categories_present",
            len(fields) == len(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES) and not missing,
            "MISSING_REQUIRED_DRAFT_FIELDS",
        )
        check("draft_fields_reference_only", not invalid, "MISSING_REQUIRED_DRAFT_FIELDS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = MT5RequestDraftValidationReport(
            validation_report_id=f"mt5_request_draft_report_{_digest(request_draft.request_draft_id)[:16]}",
            created_at=now_utc_iso(),
            source_request_draft_id=request_draft.request_draft_id,
            valid=valid,
            mt5_request_draft_final_approval_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            draft_fields_count=len(fields),
            created_draft_fields_count=len(fields) if valid else 0,
            missing_draft_fields_count=len(missing),
            invalid_draft_fields_count=len(invalid),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(request_draft.warnings or []),
            source_refs=list(request_draft.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
