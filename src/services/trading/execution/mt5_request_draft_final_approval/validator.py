from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES,
    MT5RequestDraftFinalApprovalBoundary,
    MT5RequestDraftFinalApprovalJournalRecord,
    MT5RequestDraftFinalApprovalValidationReport,
)
from src.services.trading.execution.mt5_request_draft_final_approval.policy import (
    MT5RequestDraftFinalApprovalConfig,
)


@dataclass
class MT5RequestDraftFinalApprovalValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5RequestDraftFinalApprovalValidator:
    def __init__(self, config: MT5RequestDraftFinalApprovalConfig | None = None):
        self.config = config or MT5RequestDraftFinalApprovalConfig.from_config()

    def validate_final_approval(
        self,
        approval: MT5RequestDraftFinalApprovalBoundary,
        request_draft_report=None,
    ) -> MT5RequestDraftFinalApprovalValidationResult:
        issues: list[str] = []
        for field_name in [
            "source_request_draft_id",
            "source_request_draft_validation_report_id",
            "source_dry_run_validation_id",
            "source_dry_run_validation_report_id",
            "source_pre_mt5_mapping_id",
            "source_pre_mt5_mapping_validation_id",
            "source_final_review_id",
            "source_parameterization_id",
            "source_approval_lock_id",
            "source_value_proposal_id",
            "source_parameter_draft_id",
            "source_parameter_source_boundary_id",
            "source_parameter_policy_spec_id",
            "source_contract_skeleton_id",
            "source_live_order_intent_id",
            "source_live_permission_decision_id",
            "source_preflight_report_id",
        ]:
            if not getattr(approval, field_name, ""):
                issues.append(f"{field_name}_required")
        if not approval.source_refs:
            issues.append("source_refs_required")
        if not approval.artifact_hash or not approval.idempotency_key:
            issues.append("idempotency_required")
        if approval.confirmation_phrase_valid is not True:
            issues.append("confirmation_phrase_valid_must_be_true")
        if (
            request_draft_report is not None
            and approval.mt5_request_dict_dry_run_builder_workflow_allowed
            and getattr(request_draft_report, "mt5_request_draft_final_approval_workflow_allowed", False) is not True
        ):
            issues.append("request_draft_final_approval_workflow_required")
        _append_safety_issues(approval, issues, "")
        fields = list(approval.approved_fields or [])
        if len(fields) != len(REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES):
            issues.append("approved_fields_count_must_match_required")
        field_categories = {item.field_category for item in fields}
        for category in REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES:
            if category not in field_categories:
                issues.append(f"missing_approved_field_category:{category}")
        for item in fields:
            if not item.source_refs:
                issues.append("approved_field_source_refs_required")
            if item.approved_as_reference_only is not True:
                issues.append("approved_as_reference_only_must_be_true")
            if item.dry_run_request_dict_builder_validation_required is not True:
                issues.append("dry_run_request_dict_builder_validation_required_must_be_true")
            if item.draft_field_present is not True:
                issues.append("draft_field_present_must_be_true")
            if item.draft_value_created is not False:
                issues.append("draft_value_created_must_be_false")
            if item.draft_value_redacted is not True:
                issues.append("draft_value_redacted_must_be_true")
            if item.raw_value_stored is not False:
                issues.append("approved_field_raw_value_stored_must_be_false")
            if item.mt5_payload_value_created is not False:
                issues.append("approved_field_mt5_payload_value_created_must_be_false")
            if item.mt5_request_field_value_created is not False:
                issues.append("approved_field_mt5_request_field_value_created_must_be_false")
            if item.mt5_constant_used is not False:
                issues.append("approved_field_mt5_constant_used_must_be_false")
            if item.executable_order_value is not False:
                issues.append("approved_field_executable_order_value_must_be_false")
            if item.broker_submission_value is not False:
                issues.append("approved_field_broker_submission_value_must_be_false")
            if item.final_human_approval_required is not True:
                issues.append("final_human_approval_required_must_be_true")
        issues.extend(_forbidden_payload_issues(approval.as_dict(), self.config.max_payload_chars))
        return MT5RequestDraftFinalApprovalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(
        self,
        report: MT5RequestDraftFinalApprovalValidationReport,
    ) -> MT5RequestDraftFinalApprovalValidationResult:
        issues: list[str] = []
        _append_safety_issues(report, issues, "report_")
        if report.confirmation_phrase_valid is not True and report.valid:
            issues.append("report_confirmation_phrase_valid_must_be_true")
        if report.valid and report.mt5_request_dict_dry_run_builder_workflow_allowed is not True:
            issues.append("valid_report_must_allow_dry_run_request_dict_builder_workflow")
        issues.extend(_forbidden_payload_issues(report.as_dict(), self.config.max_payload_chars))
        return MT5RequestDraftFinalApprovalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(
        self,
        record: MT5RequestDraftFinalApprovalJournalRecord,
    ) -> MT5RequestDraftFinalApprovalValidationResult:
        issues: list[str] = []
        _append_safety_issues(record, issues, "record_")
        if record.confirmation_phrase_valid is not True and record.status == "FINAL_APPROVAL_GRANTED_FOR_DRY_RUN_REQUEST_DICT_BUILDER":
            issues.append("record_confirmation_phrase_valid_must_be_true")
        issues.extend(_forbidden_payload_issues(record.as_dict(), self.config.max_payload_chars))
        return MT5RequestDraftFinalApprovalValidationResult(not issues, list(dict.fromkeys(issues)))


def _append_safety_issues(item, issues: list[str], prefix: str) -> None:
    checks = {
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "executable": False,
        "mt5_payload_created": False,
        "mt5_request_dict_created": False,
        "mt5_constants_used": False,
        "broker_submission_created": False,
        "order_sent": False,
        "hard_live_block_required": True,
        "order_contract_ready": False,
        "order_request_mapping_allowed": False,
        "broker_mapping_created": False,
        "raw_values_stored": False,
        "executable_order_created": False,
    }
    for name, expected in checks.items():
        if getattr(item, name, expected) is not expected:
            issues.append(f"{prefix}{name}_must_be_{str(expected).lower()}")


def _forbidden_payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    sanitized = _strip_allowed_false_fields(payload)
    text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True).lower()
    for allowed in [
        "mt5_request_dict_dry_run_builder_workflow_allowed",
        "mt5_request_draft_final_approval",
        "final_approval_granted_for_dry_run_request_dict_builder",
        "ready_for_dry_run_request_dict_builder",
        "dry_run_request_dict_builder_only",
        "approve_for_future_dry_run_request_dict_builder_only",
        "human_approved_for_future_dry_run_request_dict_builder_only",
        "request_draft",
        "final_approval",
        "dry_run_validation",
        "pre_mt5_mapping",
    ]:
        text = text.replace(allowed, "")
    issues: list[str] = []
    if len(text) > int(max_payload_chars):
        issues.append("payload_size_exceeds_limit")
    forbidden = [
        "order" + "_send",
        "submit_live_order",
        "send_order",
        "place_order",
        "execute_trade",
        "executable_order",
        "mt5_order_request",
        "mt5_request",
        "mt5_payload",
        "mt5_ticket",
        "deal_id",
        "broker_order_mapping",
        "broker_submission",
        "broker_submission_payload",
        "raw_account_id",
        "raw_parameter_value",
        "account_id",
        "password",
        "api_key",
        "secret",
        "credentials",
        "raw_candles",
        "raw_full_book",
        "raw_full_report",
        "metatrader5",
        "order_type_buy",
        "order_type_sell",
        "trade_action_deal",
        "llm_prompt",
    ]
    for marker in forbidden:
        if marker in text:
            issues.append(f"forbidden_marker:{marker}")
    return issues


def _strip_allowed_false_fields(value):
    allowed_keys = {
        "order_send_allowed",
        "mt5_payload_created",
        "mt5_request_dict_created",
        "mt5_request_dict_dry_run_builder_workflow_allowed",
        "mt5_constants_used",
        "broker_submission_created",
        "executable_order_created",
        "order_request_mapping_allowed",
        "broker_mapping_created",
        "raw_values_stored",
        "raw_value_stored",
        "mt5_payload_value_created",
        "mt5_request_field_value_created",
        "mt5_constant_used",
        "executable_order_value",
        "broker_submission_value",
        "metadata_redacted",
        "required_approved_field_categories",
        "approved_field_categories",
        "missing_approved_field_categories",
        "invalid_approved_field_categories",
        "validation_checks",
        "source_refs",
    }
    if isinstance(value, dict):
        return {key: _strip_allowed_false_fields(item) for key, item in value.items() if key not in allowed_keys}
    if isinstance(value, list):
        return [_strip_allowed_false_fields(item) for item in value]
    return value
