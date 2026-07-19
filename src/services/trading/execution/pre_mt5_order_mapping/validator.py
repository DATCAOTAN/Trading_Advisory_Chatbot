from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.pre_mt5_order_mapping.models import (
    REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES,
    PreMT5OrderRequestMappingBoundary,
    PreMT5OrderRequestMappingJournalRecord,
    PreMT5OrderRequestMappingValidationReport,
)
from src.services.trading.execution.pre_mt5_order_mapping.policy import (
    PreMT5OrderRequestMappingConfig,
)


@dataclass
class PreMT5OrderRequestMappingValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class PreMT5OrderRequestMappingValidator:
    def __init__(self, config: PreMT5OrderRequestMappingConfig | None = None):
        self.config = config or PreMT5OrderRequestMappingConfig.from_config()

    def validate_mapping_boundary(
        self, boundary: PreMT5OrderRequestMappingBoundary, final_review_validation=None
    ) -> PreMT5OrderRequestMappingValidationResult:
        issues: list[str] = []
        for field_name in [
            "source_final_review_id",
            "source_final_review_validation_id",
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
            final_review_validation is not None
            and boundary.mt5_dry_run_payload_validation_workflow_allowed
            and getattr(final_review_validation, "pre_mt5_mapping_boundary_workflow_allowed", False) is not True
        ):
            issues.append("final_review_pre_mt5_workflow_required")
        if boundary.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if boundary.order_send_allowed is not False:
            issues.append("order_send_allowed_must_be_false")
        if boundary.execution_allowed is not False:
            issues.append("execution_allowed_must_be_false")
        if boundary.executable is not False:
            issues.append("executable_must_be_false")
        if boundary.mt5_payload_created is not False:
            issues.append("mt5_payload_created_must_be_false")
        if boundary.mt5_request_dict_created is not False:
            issues.append("mt5_request_dict_created_must_be_false")
        if boundary.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if boundary.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if boundary.order_contract_ready is not False:
            issues.append("order_contract_ready_must_be_false")
        if boundary.order_request_mapping_allowed is not False:
            issues.append("order_request_mapping_allowed_must_be_false")
        if boundary.broker_mapping_created is not False:
            issues.append("broker_mapping_created_must_be_false")
        if boundary.raw_values_stored is not False:
            issues.append("raw_values_stored_must_be_false")
        if boundary.executable_order_created is not False:
            issues.append("executable_order_created_must_be_false")
        slots = list(boundary.mapping_slots or [])
        if len(slots) != len(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES):
            issues.append("mapping_slots_count_must_match_required")
        slot_types = {slot.slot_type for slot in slots}
        for slot_type in REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES:
            if slot_type not in slot_types:
                issues.append(f"missing_mapping_slot:{slot_type}")
        for slot in slots:
            if not slot.source_refs:
                issues.append("slot_source_refs_required")
            if slot.mapped_as_schema_only is not True:
                issues.append("slot_mapped_as_schema_only_must_be_true")
            if slot.dry_run_payload_validation_required is not True:
                issues.append("slot_dry_run_payload_validation_required_must_be_true")
            if slot.raw_value_stored is not False:
                issues.append("slot_raw_value_stored_must_be_false")
            if slot.mt5_payload_value_created is not False:
                issues.append("slot_mt5_payload_value_created_must_be_false")
            if slot.mt5_request_field_value_created is not False:
                issues.append("slot_mt5_request_field_value_created_must_be_false")
            if slot.executable_order_value is not False:
                issues.append("slot_executable_order_value_must_be_false")
            if slot.broker_submission_value is not False:
                issues.append("slot_broker_submission_value_must_be_false")
        issues.extend(_forbidden_payload_issues(boundary.as_dict(), self.config.max_payload_chars))
        return PreMT5OrderRequestMappingValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(
        self, report: PreMT5OrderRequestMappingValidationReport
    ) -> PreMT5OrderRequestMappingValidationResult:
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
        if report.valid and report.mt5_dry_run_payload_validation_workflow_allowed is not True:
            issues.append("valid_report_must_allow_dry_run_payload_validation_workflow")
        issues.extend(_forbidden_payload_issues(report.as_dict(), self.config.max_payload_chars))
        return PreMT5OrderRequestMappingValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(
        self, record: PreMT5OrderRequestMappingJournalRecord
    ) -> PreMT5OrderRequestMappingValidationResult:
        issues = _forbidden_payload_issues(record.as_dict(), self.config.max_payload_chars)
        if record.live_execution_allowed or record.order_send_allowed or record.execution_allowed:
            issues.append("record_execution_flags_must_be_false")
        if record.executable or record.mt5_payload_created or record.mt5_request_dict_created or record.order_sent:
            issues.append("record_order_flags_must_be_false")
        if record.order_contract_ready or record.order_request_mapping_allowed or record.broker_mapping_created:
            issues.append("record_mapping_flags_must_be_false")
        if record.raw_values_stored or record.executable_order_created:
            issues.append("record_raw_or_executable_must_be_false")
        return PreMT5OrderRequestMappingValidationResult(not issues, list(dict.fromkeys(issues)))


def _forbidden_payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    sanitized = _strip_allowed_false_fields(payload)
    text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True).lower()
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
        "broker_mapping_payload",
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
        "executable_order_created",
        "order_request_mapping_allowed",
        "broker_mapping_created",
        "raw_values_stored",
        "raw_value_stored",
        "mt5_payload_value_created",
        "mt5_request_field_value_created",
        "executable_order_value",
        "broker_submission_value",
        "metadata_redacted",
        "required_mapping_slot_types",
        "mapped_slot_types",
        "missing_mapping_slot_types",
        "invalid_mapping_slot_types",
        "validation_checks",
        "source_refs",
        "future_mt5_field_label",
        "future_validation_requirements",
    }
    if isinstance(value, dict):
        return {key: _strip_allowed_false_fields(item) for key, item in value.items() if key not in allowed_keys}
    if isinstance(value, list):
        return [_strip_allowed_false_fields(item) for item in value]
    return value
