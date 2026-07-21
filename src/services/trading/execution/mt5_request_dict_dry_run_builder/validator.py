from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.mt5_request_dict_dry_run_builder.models import (
    REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES,
    MT5RequestDictDryRunBuilderBoundary,
    MT5RequestDictDryRunBuilderJournalRecord,
    MT5RequestDictDryRunBuilderValidationReport,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.policy import (
    MT5RequestDictDryRunBuilderConfig,
)


@dataclass
class MT5RequestDictDryRunBuilderValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5RequestDictDryRunBuilderValidator:
    def __init__(self, config: MT5RequestDictDryRunBuilderConfig | None = None):
        self.config = config or MT5RequestDictDryRunBuilderConfig.from_config()

    def validate_boundary(self, boundary: MT5RequestDictDryRunBuilderBoundary, final_approval_report=None) -> MT5RequestDictDryRunBuilderValidationResult:
        issues: list[str] = []
        for field_name in [
            "source_draft_final_approval_id",
            "source_draft_final_approval_validation_report_id",
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
            if not getattr(boundary, field_name, ""):
                issues.append(f"{field_name}_required")
        if not boundary.source_refs:
            issues.append("source_refs_required")
        if not boundary.artifact_hash or not boundary.idempotency_key:
            issues.append("idempotency_required")
        if (
            final_approval_report is not None
            and boundary.mt5_request_dict_final_validation_workflow_allowed
            and getattr(final_approval_report, "mt5_request_dict_dry_run_builder_workflow_allowed", False) is not True
        ):
            issues.append("draft_final_approval_workflow_required")
        _append_safety_issues(boundary, issues, "")
        fields = list(boundary.dry_run_fields or [])
        if len(fields) != len(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES):
            issues.append("dry_run_fields_count_must_match_required")
        categories = {item.field_category for item in fields}
        for category in REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES:
            if category not in categories:
                issues.append(f"missing_dry_run_field_category:{category}")
        for item in fields:
            if not item.source_refs:
                issues.append("dry_run_field_source_refs_required")
            if item.dry_run_field_present is not True:
                issues.append("dry_run_field_present_must_be_true")
            if item.concrete_value_created is not False:
                issues.append("concrete_value_created_must_be_false")
            if item.value_redacted is not True:
                issues.append("value_redacted_must_be_true")
            if item.raw_value_stored is not False:
                issues.append("dry_run_field_raw_value_stored_must_be_false")
            if item.real_mt5_payload_value_created is not False:
                issues.append("real_mt5_payload_value_created_must_be_false")
            if item.broker_submittable_request_field_created is not False:
                issues.append("broker_submittable_request_field_created_must_be_false")
            if item.mt5_constant_used is not False:
                issues.append("mt5_constant_used_must_be_false")
            if item.executable_order_value is not False:
                issues.append("executable_order_value_must_be_false")
            if item.broker_submission_value is not False:
                issues.append("broker_submission_value_must_be_false")
            if item.final_validation_required is not True:
                issues.append("final_validation_required_must_be_true")
        issues.extend(_forbidden_payload_issues(boundary.as_dict(), self.config.max_payload_chars))
        return MT5RequestDictDryRunBuilderValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(self, report: MT5RequestDictDryRunBuilderValidationReport) -> MT5RequestDictDryRunBuilderValidationResult:
        issues: list[str] = []
        _append_safety_issues(report, issues, "report_")
        if report.valid and report.mt5_request_dict_final_validation_workflow_allowed is not True:
            issues.append("valid_report_must_allow_request_dict_final_validation_workflow")
        issues.extend(_forbidden_payload_issues(report.as_dict(), self.config.max_payload_chars))
        return MT5RequestDictDryRunBuilderValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: MT5RequestDictDryRunBuilderJournalRecord) -> MT5RequestDictDryRunBuilderValidationResult:
        issues: list[str] = []
        _append_safety_issues(record, issues, "record_")
        issues.extend(_forbidden_payload_issues(record.as_dict(), self.config.max_payload_chars))
        return MT5RequestDictDryRunBuilderValidationResult(not issues, list(dict.fromkeys(issues)))


def _append_safety_issues(item, issues: list[str], prefix: str) -> None:
    checks = {
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "executable": False,
        "real_mt5_payload_created": False,
        "broker_submittable_request_dict_created": False,
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
        "mt5requestdictdryrunbuilderboundary",
        "mt5requestdictdryrunbuildervalidationreport",
        "mt5_request_dict_final_validation_workflow_allowed",
        "mt5_request_dict_dry_run_builder",
        "dry_run_request_dict_boundary_created",
        "ready_for_request_dict_final_validation",
        "request_dict_final_validation_only",
        "dry_run_request_dict_id",
        "source_dry_run_request_dict_id",
        "request_dict_dry_run_builder_boundary_only",
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
        "real_mt5_payload",
        "broker_submittable_request_dict",
        "mt5_ticket",
        "deal_id",
        "broker_order_mapping",
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
        "real_mt5_payload_created",
        "broker_submittable_request_dict_created",
        "mt5_request_dict_final_validation_workflow_allowed",
        "mt5_constants_used",
        "broker_submission_created",
        "executable_order_created",
        "order_request_mapping_allowed",
        "broker_mapping_created",
        "raw_values_stored",
        "raw_value_stored",
        "real_mt5_payload_value_created",
        "broker_submittable_request_field_created",
        "mt5_constant_used",
        "executable_order_value",
        "broker_submission_value",
        "metadata_redacted",
        "required_dry_run_field_categories",
        "created_dry_run_field_categories",
        "missing_dry_run_field_categories",
        "invalid_dry_run_field_categories",
        "validation_checks",
        "source_refs",
    }
    if isinstance(value, dict):
        return {key: _strip_allowed_false_fields(item) for key, item in value.items() if key not in allowed_keys}
    if isinstance(value, list):
        return [_strip_allowed_false_fields(item) for item in value]
    return value
