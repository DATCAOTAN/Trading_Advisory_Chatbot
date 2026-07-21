from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES,
    MT5RequestDraftFinalApprovalBoundary,
    MT5RequestDraftFinalApprovalValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_draft_final_approval.policy import (
    MT5RequestDraftFinalApprovalConfig,
)


class MT5RequestDraftFinalApprovalGate:
    def __init__(self, config: MT5RequestDraftFinalApprovalConfig | None = None):
        self.config = config or MT5RequestDraftFinalApprovalConfig.from_config()

    def validate(self, approval: MT5RequestDraftFinalApprovalBoundary) -> MT5RequestDraftFinalApprovalValidationReport:
        blockers = list(approval.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check(
            "status_final_approval_granted",
            approval.status == "FINAL_APPROVAL_GRANTED_FOR_DRY_RUN_REQUEST_DICT_BUILDER",
            "INVALID_INPUT",
        )
        check("scope_dry_run_builder_only", approval.scope == "DRY_RUN_REQUEST_DICT_BUILDER_ONLY", "INVALID_INPUT")
        check("confirmation_phrase_valid", approval.confirmation_phrase_valid is True, "WRONG_CONFIRMATION_PHRASE")
        check(
            "dry_run_request_dict_builder_workflow_allowed",
            approval.mt5_request_dict_dry_run_builder_workflow_allowed is True,
            "REQUEST_DRAFT_FINAL_APPROVAL_WORKFLOW_NOT_ALLOWED",
        )
        check("live_execution_disabled", approval.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_submission_disabled", approval.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
        check("execution_disabled", approval.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
        check("non_executable", approval.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("no_mt5_payload", approval.mt5_payload_created is False, "MT5_PAYLOAD_NOT_ALLOWED")
        check("no_mt5_request_dict", approval.mt5_request_dict_created is False, "MT5_REQUEST_DICT_NOT_ALLOWED")
        check("no_mt5_constants", approval.mt5_constants_used is False, "MT5_CONSTANT_NOT_ALLOWED")
        check("no_broker_submission", approval.broker_submission_created is False, "BROKER_SUBMISSION_NOT_ALLOWED")
        check("not_order_sent", approval.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
        check("hard_live_block", approval.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_contract_not_ready", approval.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
        check("order_mapping_disabled", approval.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("broker_mapping_absent", approval.broker_mapping_created is False, "BROKER_MAPPING_NOT_ALLOWED")
        check("raw_values_absent", approval.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
        check("executable_order_absent", approval.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("source_refs_present", bool(approval.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(approval.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(approval.idempotency_key), "MISSING_IDEMPOTENCY")

        fields = list(approval.approved_fields or [])
        field_categories = {item.field_category for item in fields}
        missing = [item for item in REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES if item not in field_categories]
        invalid = [
            item.field_category
            for item in fields
            if item.blockers
            or item.status != "APPROVED_AS_REFERENCE_ONLY"
            or not item.approved_as_reference_only
            or not item.dry_run_request_dict_builder_validation_required
            or not item.draft_field_present
            or item.draft_value_created
            or not item.draft_value_redacted
            or item.raw_value_stored
            or item.mt5_payload_value_created
            or item.mt5_request_field_value_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
            or not item.final_human_approval_required
        ]
        check(
            "required_approved_field_categories_present",
            len(fields) == len(REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES) and not missing,
            "MISSING_REQUIRED_APPROVED_FIELDS",
        )
        check("approved_fields_reference_only", not invalid, "MISSING_REQUIRED_APPROVED_FIELDS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = MT5RequestDraftFinalApprovalValidationReport(
            validation_report_id=f"mt5_request_draft_final_approval_report_{_digest(approval.final_approval_id)[:16]}",
            created_at=now_utc_iso(),
            source_final_approval_id=approval.final_approval_id,
            valid=valid,
            mt5_request_dict_dry_run_builder_workflow_allowed=valid,
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
            confirmation_phrase_valid=approval.confirmation_phrase_valid and valid,
            approved_fields_count=len(fields),
            approved_fields_valid_count=len(fields) if valid else 0,
            missing_approved_fields_count=len(missing),
            invalid_approved_fields_count=len(invalid),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(approval.warnings or []),
            source_refs=list(approval.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
