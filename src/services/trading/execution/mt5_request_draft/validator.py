from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.mt5_request_draft.models import (
    REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES,
    MT5RequestDraftBoundary,
    MT5RequestDraftJournalRecord,
    MT5RequestDraftValidationReport,
)
from src.services.trading.execution.mt5_request_draft.policy import MT5RequestDraftConfig


@dataclass
class MT5RequestDraftValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5RequestDraftValidator:
    def __init__(self, config: MT5RequestDraftConfig | None = None):
        self.config = config or MT5RequestDraftConfig.from_config()

    def validate_request_draft(
        self,
        request_draft: MT5RequestDraftBoundary,
        dry_run_validation_report=None,
    ) -> MT5RequestDraftValidationResult:
        issues: list[str] = []
        for field_name in [
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
            if not getattr(request_draft, field_name, ""):
                issues.append(f"{field_name}_required")
        if not request_draft.source_refs:
            issues.append("source_refs_required")
        if not request_draft.artifact_hash or not request_draft.idempotency_key:
            issues.append("idempotency_required")
        if (
            dry_run_validation_report is not None
            and request_draft.mt5_request_draft_final_approval_workflow_allowed
            and getattr(dry_run_validation_report, "mt5_request_draft_workflow_allowed", False) is not True
        ):
            issues.append("dry_run_validation_workflow_required")
        if request_draft.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if request_draft.order_send_allowed is not False:
            issues.append("order_send_allowed_must_be_false")
        if request_draft.execution_allowed is not False:
            issues.append("execution_allowed_must_be_false")
        if request_draft.executable is not False:
            issues.append("executable_must_be_false")
        if request_draft.mt5_payload_created is not False:
            issues.append("mt5_payload_created_must_be_false")
        if request_draft.mt5_request_dict_created is not False:
            issues.append("mt5_request_dict_created_must_be_false")
        if request_draft.mt5_constants_used is not False:
            issues.append("mt5_constants_used_must_be_false")
        if request_draft.broker_submission_created is not False:
            issues.append("broker_submission_created_must_be_false")
        if request_draft.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if request_draft.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if request_draft.order_contract_ready is not False:
            issues.append("order_contract_ready_must_be_false")
        if request_draft.order_request_mapping_allowed is not False:
            issues.append("order_request_mapping_allowed_must_be_false")
        if request_draft.broker_mapping_created is not False:
            issues.append("broker_mapping_created_must_be_false")
        if request_draft.raw_values_stored is not False:
            issues.append("raw_values_stored_must_be_false")
        if request_draft.executable_order_created is not False:
            issues.append("executable_order_created_must_be_false")
        fields = list(request_draft.draft_fields or [])
        if len(fields) != len(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES):
            issues.append("draft_fields_count_must_match_required")
        field_categories = {item.field_category for item in fields}
        for category in REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES:
            if category not in field_categories:
                issues.append(f"missing_draft_field_category:{category}")
        for item in fields:
            if not item.source_refs:
                issues.append("draft_field_source_refs_required")
            if item.draft_field_present is not True:
                issues.append("draft_field_present_must_be_true")
            if item.draft_value_created is not False:
                issues.append("draft_value_created_must_be_false")
            if item.draft_value_redacted is not True:
                issues.append("draft_value_redacted_must_be_true")
            if item.raw_value_stored is not False:
                issues.append("draft_field_raw_value_stored_must_be_false")
            if item.mt5_payload_value_created is not False:
                issues.append("draft_field_mt5_payload_value_created_must_be_false")
            if item.mt5_request_field_value_created is not False:
                issues.append("draft_field_mt5_request_field_value_created_must_be_false")
            if item.mt5_constant_used is not False:
                issues.append("draft_field_mt5_constant_used_must_be_false")
            if item.executable_order_value is not False:
                issues.append("draft_field_executable_order_value_must_be_false")
            if item.broker_submission_value is not False:
                issues.append("draft_field_broker_submission_value_must_be_false")
            if item.final_draft_approval_required is not True:
                issues.append("draft_field_final_approval_required_must_be_true")
        issues.extend(_forbidden_payload_issues(request_draft.as_dict(), self.config.max_payload_chars))
        return MT5RequestDraftValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(self, report: MT5RequestDraftValidationReport) -> MT5RequestDraftValidationResult:
        issues: list[str] = []
        if report.live_execution_allowed is not False:
            issues.append("report_live_execution_allowed_must_be_false")
        if report.order_send_allowed is not False:
            issues.append("report_order_send_allowed_must_be_false")
        if report.execution_allowed is not False:
            issues.append("report_execution_allowed_must_be_false")
        if report.executable is not False:
            issues.append("report_executable_must_be_false")
        if report.mt5_payload_created is not False:
            issues.append("report_mt5_payload_created_must_be_false")
        if report.mt5_request_dict_created is not False:
            issues.append("report_mt5_request_dict_created_must_be_false")
        if report.mt5_constants_used is not False:
            issues.append("report_mt5_constants_used_must_be_false")
        if report.broker_submission_created is not False:
            issues.append("report_broker_submission_created_must_be_false")
        if report.order_sent is not False:
            issues.append("report_order_sent_must_be_false")
        if report.hard_live_block_required is not True:
            issues.append("report_hard_live_block_required_must_be_true")
        if report.order_contract_ready is not False:
            issues.append("report_order_contract_ready_must_be_false")
        if report.order_request_mapping_allowed is not False:
            issues.append("report_order_request_mapping_allowed_must_be_false")
        if report.broker_mapping_created is not False:
            issues.append("report_broker_mapping_created_must_be_false")
        if report.raw_values_stored is not False:
            issues.append("report_raw_values_stored_must_be_false")
        if report.executable_order_created is not False:
            issues.append("report_executable_order_created_must_be_false")
        if report.valid and report.mt5_request_draft_final_approval_workflow_allowed is not True:
            issues.append("valid_report_must_allow_final_draft_approval_workflow")
        issues.extend(_forbidden_payload_issues(report.as_dict(), self.config.max_payload_chars))
        return MT5RequestDraftValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: MT5RequestDraftJournalRecord) -> MT5RequestDraftValidationResult:
        issues = _forbidden_payload_issues(record.as_dict(), self.config.max_payload_chars)
        if record.live_execution_allowed or record.order_send_allowed or record.execution_allowed:
            issues.append("record_execution_flags_must_be_false")
        if record.executable or record.mt5_payload_created or record.mt5_request_dict_created or record.mt5_constants_used:
            issues.append("record_payload_flags_must_be_false")
        if record.broker_submission_created:
            issues.append("record_broker_submission_must_be_false")
        if record.order_sent or record.order_contract_ready or record.order_request_mapping_allowed:
            issues.append("record_order_flags_must_be_false")
        if record.broker_mapping_created or record.raw_values_stored or record.executable_order_created:
            issues.append("record_raw_or_mapping_flags_must_be_false")
        return MT5RequestDraftValidationResult(not issues, list(dict.fromkeys(issues)))


def _forbidden_payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    sanitized = _strip_allowed_false_fields(payload)
    text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True).lower()
    for allowed in [
        "mt5_request_draft_final_approval_workflow_allowed",
        "mt5_request_draft",
        "request_draft_boundary_only",
        "request_draft_created",
        "ready_for_final_draft_approval",
        "final_draft_approval_only",
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
        "mt5_request_draft_final_approval_workflow_allowed",
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
        "required_draft_field_categories",
        "created_draft_field_categories",
        "missing_draft_field_categories",
        "invalid_draft_field_categories",
        "validation_checks",
        "source_refs",
    }
    if isinstance(value, dict):
        return {key: _strip_allowed_false_fields(item) for key, item in value.items() if key not in allowed_keys}
    if isinstance(value, list):
        return [_strip_allowed_false_fields(item) for item in value]
    return value
