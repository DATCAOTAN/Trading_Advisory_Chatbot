from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES,
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationJournalRecord,
    MT5RequestDictFinalValidationReport,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import MT5RequestDictFinalValidationConfig


@dataclass
class MT5RequestDictFinalValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5RequestDictFinalValidationValidator:
    def __init__(self, config: MT5RequestDictFinalValidationConfig | None = None):
        self.config = config or MT5RequestDictFinalValidationConfig.from_config()

    def validate_boundary(self, boundary: MT5RequestDictFinalValidationBoundary, source_report=None) -> MT5RequestDictFinalValidationResult:
        issues: list[str] = []
        if not boundary.source_dry_run_request_dict_id:
            issues.append("source_dry_run_request_dict_id_required")
        if not boundary.source_dry_run_request_dict_validation_report_id:
            issues.append("source_dry_run_request_dict_validation_report_id_required")
        if not boundary.source_refs:
            issues.append("source_refs_required")
        if not boundary.idempotency_key or not boundary.artifact_hash:
            issues.append("idempotency_required")
        if (
            source_report is not None
            and boundary.bridge_write_skeleton_check_allowed
            and getattr(source_report, "mt5_request_dict_final_validation_workflow_allowed", False) is not True
        ):
            issues.append("request_dict_final_validation_workflow_required")
        _append_safety_issues(boundary, issues, "")
        fields = list(boundary.validated_fields or [])
        if len(fields) != len(REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES):
            issues.append("validated_fields_count_must_match_required")
        categories = {field.field_category for field in fields}
        for category in REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES:
            if category not in categories:
                issues.append(f"missing_field_category:{category}")
        for field in fields:
            if not field.source_dry_run_field_id:
                issues.append("source_dry_run_field_id_required")
            if not field.source_refs:
                issues.append("field_source_refs_required")
            if field.validation_passed is not True:
                issues.append("field_validation_must_pass")
            if field.schema_only is not True:
                issues.append("field_schema_only_required")
            if field.value_redacted is not True:
                issues.append("field_value_redacted_required")
            _append_safety_issues(field, issues, "field_")
        issues.extend(_forbidden_marker_issues(boundary.as_dict()))
        return MT5RequestDictFinalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(self, report: MT5RequestDictFinalValidationReport) -> MT5RequestDictFinalValidationResult:
        issues: list[str] = []
        if not report.source_final_validation_id:
            issues.append("source_final_validation_id_required")
        _append_safety_issues(report, issues, "")
        if report.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if report.valid and not report.bridge_write_skeleton_check_allowed:
            issues.append("valid_report_must_allow_bridge_skeleton_check")
        issues.extend(_forbidden_marker_issues(report.as_dict()))
        return MT5RequestDictFinalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: MT5RequestDictFinalValidationJournalRecord) -> MT5RequestDictFinalValidationResult:
        issues: list[str] = []
        try:
            json.dumps(record.as_dict(), sort_keys=True)
        except TypeError:
            issues.append("journal_record_not_serializable")
        _append_safety_issues(record, issues, "")
        issues.extend(_forbidden_marker_issues(record.as_dict()))
        return MT5RequestDictFinalValidationResult(not issues, list(dict.fromkeys(issues)))


def _append_safety_issues(item, issues: list[str], prefix: str) -> None:
    for name in [
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "real_mt5_payload_created",
        "broker_submittable_request_dict_created",
        "mt5_constants_used",
        "broker_submission_created",
        "order_sent",
        "concrete_value_created",
        "raw_value_stored",
        "real_mt5_payload_value_created",
        "broker_submittable_request_field_created",
        "mt5_constant_used",
        "executable_order_value",
        "broker_submission_value",
    ]:
        if getattr(item, name, False) is not False:
            issues.append(f"{prefix}{name}_must_be_false")


def _forbidden_marker_issues(payload) -> list[str]:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False).lower()
    allowed = [
        "order_send_allowed",
        "real_mt5_payload_created",
        "real_mt5_payload_value_created",
        "broker_submittable_request_dict_created",
        "broker_submittable_request_field_created",
        "mt5_request_dict_final_validation",
    ]
    for item in allowed:
        text = text.replace(item, "")
    markers = [
        "order_" + "send(",
        "order_" + "send",
        "." + "order_" + "send",
        "real_mt5_payload",
        "broker_submittable_request_dict",
        "metatrader5." + "order_" + "send",
        "submit_live_order",
        "send_order",
        "place_order",
        "execute_trade",
        "mt5_ticket",
        "deal_id",
        "raw_account_id",
        "raw_parameter_value",
        "password",
        "api_key",
        "secret",
        "metatrader5",
        "order_type_buy",
        "order_type_sell",
        "trade_action_deal",
    ]
    return [f"forbidden_marker:{marker}" for marker in markers if marker in text]
