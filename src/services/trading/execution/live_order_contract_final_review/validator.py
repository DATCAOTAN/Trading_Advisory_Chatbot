from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.live_order_contract_final_review.models import (
    REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES,
    LiveOrderContractFinalReview,
    LiveOrderContractFinalReviewJournalRecord,
    LiveOrderContractFinalReviewValidationReport,
)
from src.services.trading.execution.live_order_contract_final_review.policy import (
    LiveOrderContractFinalReviewConfig,
)


@dataclass
class LiveOrderContractFinalReviewValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class LiveOrderContractFinalReviewValidator:
    def __init__(self, config: LiveOrderContractFinalReviewConfig | None = None):
        self.config = config or LiveOrderContractFinalReviewConfig.from_config()

    def validate_final_review(self, final_review: LiveOrderContractFinalReview) -> LiveOrderContractFinalReviewValidationResult:
        issues: list[str] = []
        for field_name in [
            "source_parameterization_id",
            "source_parameterization_validation_id",
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
            if not getattr(final_review, field_name, ""):
                issues.append(f"{field_name}_required")
        if not final_review.source_refs:
            issues.append("source_refs_required")
        if not final_review.artifact_hash or not final_review.idempotency_key:
            issues.append("idempotency_required")
        if final_review.confirmation_phrase_valid is not True and final_review.pre_mt5_mapping_boundary_workflow_allowed:
            issues.append("confirmation_phrase_valid_required")
        if final_review.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if final_review.order_send_allowed is not False:
            issues.append("order_send_allowed_must_be_false")
        if final_review.execution_allowed is not False:
            issues.append("execution_allowed_must_be_false")
        if final_review.executable is not False:
            issues.append("executable_must_be_false")
        if final_review.mt5_payload_created is not False:
            issues.append("mt5_payload_created_must_be_false")
        if final_review.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if final_review.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if final_review.order_contract_ready is not False:
            issues.append("order_contract_ready_must_be_false")
        if final_review.order_request_mapping_allowed is not False:
            issues.append("order_request_mapping_allowed_must_be_false")
        if final_review.broker_mapping_created is not False:
            issues.append("broker_mapping_created_must_be_false")
        if final_review.raw_values_stored is not False:
            issues.append("raw_values_stored_must_be_false")
        if final_review.executable_order_created is not False:
            issues.append("executable_order_created_must_be_false")
        slots = list(final_review.slot_validations or [])
        if len(slots) != 9:
            issues.append("slot_validations_count_must_be_9")
        slot_types = {slot.slot_type for slot in slots}
        for slot_type in REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES:
            if slot_type not in slot_types:
                issues.append(f"missing_slot_validation:{slot_type}")
        for slot in slots:
            if not slot.source_contract_slot_id:
                issues.append("slot_source_contract_slot_id_required")
            if not slot.source_slot_lock_id:
                issues.append("slot_source_slot_lock_id_required")
            if not slot.source_value_slot_id:
                issues.append("slot_source_value_slot_id_required")
            if not slot.source_refs:
                issues.append("slot_source_refs_required")
            if slot.raw_value_stored is not False:
                issues.append("slot_raw_value_stored_must_be_false")
            if slot.executable_value is not False:
                issues.append("slot_executable_value_must_be_false")
            if slot.mt5_payload_value is not False:
                issues.append("slot_mt5_payload_value_must_be_false")
            if slot.order_request_value is not False:
                issues.append("slot_order_request_value_must_be_false")
            if slot.broker_mapping_created is not False:
                issues.append("slot_broker_mapping_created_must_be_false")
            if slot.validation_only_ready is not True:
                issues.append("slot_validation_only_ready_must_be_true")
            if slot.final_human_review_required is not True:
                issues.append("slot_final_human_review_required_must_be_true")
        issues.extend(_forbidden_payload_issues(final_review.as_dict(), self.config.max_payload_chars))
        return LiveOrderContractFinalReviewValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(
        self, report: LiveOrderContractFinalReviewValidationReport
    ) -> LiveOrderContractFinalReviewValidationResult:
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
        if report.valid and report.pre_mt5_mapping_boundary_workflow_allowed is not True:
            issues.append("valid_report_must_allow_pre_mt5_mapping_boundary_workflow")
        issues.extend(_forbidden_payload_issues(report.as_dict(), self.config.max_payload_chars))
        return LiveOrderContractFinalReviewValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(
        self, record: LiveOrderContractFinalReviewJournalRecord
    ) -> LiveOrderContractFinalReviewValidationResult:
        issues = _forbidden_payload_issues(record.as_dict(), self.config.max_payload_chars)
        if record.live_execution_allowed or record.order_send_allowed or record.execution_allowed:
            issues.append("record_execution_flags_must_be_false")
        if record.executable or record.mt5_payload_created or record.order_sent:
            issues.append("record_order_flags_must_be_false")
        if record.order_contract_ready or record.order_request_mapping_allowed or record.broker_mapping_created:
            issues.append("record_mapping_flags_must_be_false")
        if record.raw_values_stored or record.executable_order_created:
            issues.append("record_raw_or_executable_must_be_false")
        return LiveOrderContractFinalReviewValidationResult(not issues, list(dict.fromkeys(issues)))


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
        "executable_order_created",
        "order_request_mapping_allowed",
        "broker_mapping_created",
        "raw_values_stored",
        "raw_value_stored",
        "mt5_payload_value",
        "executable_value",
        "order_request_value",
        "metadata_redacted",
        "slot_validations",
        "required_slot_validation_types",
        "passed_slot_validation_types",
        "blocked_slot_validation_types",
        "missing_slot_validation_types",
        "validation_checks",
        "source_refs",
    }
    if isinstance(value, dict):
        return {key: _strip_allowed_false_fields(item) for key, item in value.items() if key not in allowed_keys}
    if isinstance(value, list):
        return [_strip_allowed_false_fields(item) for item in value]
    return value
