from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.live_parameter_value_proposal.models import (
    REQUIRED_CONTROLLED_VALUE_SLOT_TYPES,
    ControlledLiveParameterValueProposal,
    ControlledLiveParameterValueProposalJournalRecord,
    ControlledLiveParameterValueProposalValidationReport,
)
from src.services.trading.execution.live_parameter_value_proposal.policy import (
    ControlledLiveParameterValueProposalConfig,
)


@dataclass
class ControlledLiveParameterValueProposalValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class ControlledLiveParameterValueProposalValidator:
    def __init__(self, config: ControlledLiveParameterValueProposalConfig | None = None):
        self.config = config or ControlledLiveParameterValueProposalConfig.from_config()

    def validate_proposal(
        self, proposal: ControlledLiveParameterValueProposal
    ) -> ControlledLiveParameterValueProposalValidationResult:
        issues: list[str] = []
        payload = proposal.as_dict()
        for field_name in [
            "source_parameter_draft_id",
            "source_parameter_draft_validation_id",
            "source_parameter_source_boundary_id",
            "source_parameter_source_validation_id",
            "source_parameter_policy_spec_id",
            "source_contract_skeleton_id",
            "source_live_order_intent_id",
            "source_live_permission_decision_id",
            "source_preflight_report_id",
            "source_proposal_draft_id",
            "source_simulated_contract_id",
        ]:
            if not getattr(proposal, field_name, ""):
                issues.append(f"{field_name}_required")
        if not proposal.source_refs:
            issues.append("source_refs_required")
        issues.extend(_forced_flag_issues(proposal))
        issues.extend(_slot_issues(proposal))
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.config.max_payload_chars))
        return ControlledLiveParameterValueProposalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_report(
        self, report: ControlledLiveParameterValueProposalValidationReport
    ) -> ControlledLiveParameterValueProposalValidationResult:
        issues: list[str] = []
        payload = report.as_dict()
        if not report.source_proposal_id:
            issues.append("source_proposal_id_required")
        if not report.source_refs:
            issues.append("source_refs_required")
        issues.extend(_forced_flag_issues(report))
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.config.max_payload_chars))
        return ControlledLiveParameterValueProposalValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(
        self, record: ControlledLiveParameterValueProposalJournalRecord
    ) -> ControlledLiveParameterValueProposalValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        for field_name in [
            "proposal_id",
            "validation_report_id",
            "source_parameter_draft_id",
            "source_parameter_draft_validation_id",
            "source_parameter_source_boundary_id",
            "source_parameter_policy_spec_id",
            "source_contract_skeleton_id",
            "source_live_order_intent_id",
            "source_live_permission_decision_id",
            "source_preflight_report_id",
        ]:
            if not getattr(record, field_name, ""):
                issues.append(f"{field_name}_required")
        if not record.source_refs:
            issues.append("source_refs_required")
        issues.extend(_forced_flag_issues(record))
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.config.max_payload_chars))
        return ControlledLiveParameterValueProposalValidationResult(not issues, list(dict.fromkeys(issues)))


def _forced_flag_issues(value: Any) -> list[str]:
    issues: list[str] = []
    if getattr(value, "live_execution_allowed", False) is not False:
        issues.append("live_execution_allowed_must_be_false")
    if getattr(value, "order_send_allowed", False) is not False:
        issues.append("order_send_allowed_must_be_false")
    if getattr(value, "execution_allowed", False) is not False:
        issues.append("execution_allowed_must_be_false")
    if getattr(value, "executable", False) is not False:
        issues.append("executable_must_be_false")
    if getattr(value, "mt5_payload_created", False) is not False:
        issues.append("mt5_payload_created_must_be_false")
    if getattr(value, "order_sent", False) is not False:
        issues.append("order_sent_must_be_false")
    if getattr(value, "hard_live_block_required", True) is not True:
        issues.append("hard_live_block_required_must_be_true")
    if getattr(value, "order_contract_ready", False) is not False:
        issues.append("order_contract_ready_must_be_false")
    if getattr(value, "value_lock_required", True) is not True:
        issues.append("value_lock_required_must_be_true")
    if getattr(value, "human_review_required", True) is not True:
        issues.append("human_review_required_must_be_true")
    return issues


def _slot_issues(proposal: ControlledLiveParameterValueProposal) -> list[str]:
    issues: list[str] = []
    if not proposal.value_slots:
        return ["value_slots_required"]
    slot_types = {slot.slot_type for slot in proposal.value_slots}
    if len(proposal.value_slots) != len(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES):
        issues.append("exactly_nine_value_slots_required")
    if slot_types != set(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES):
        issues.append("required_value_slot_types_missing")
    for slot in proposal.value_slots:
        if not slot.source_draft_slot_id:
            issues.append("slot_source_draft_slot_id_required")
        if not slot.source_candidate_ids:
            issues.append("slot_source_candidate_ids_required")
        if not slot.source_refs:
            issues.append("slot_source_refs_required")
        if slot.executable_value is not False:
            issues.append("slot_executable_value_must_be_false")
        if slot.human_review_required is not True:
            issues.append("slot_human_review_required_must_be_true")
        if slot.value_lock_required is not True:
            issues.append("slot_value_lock_required_must_be_true")
    return issues


def _payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ["payload_not_json_serializable"]
    return ["payload_too_large"] if len(serialized) > max_payload_chars else []


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    fields = _flatten_keys(payload)
    values = " ".join(_flatten_values(_value_scan_payload(payload))).lower()
    issues: list[str] = []
    allowed_fields = {"order_send_allowed", "mt5_payload_created"}
    field_markers = {
        "order_submission_marker_present": {"order" + "_send"} - allowed_fields,
        "live_method_marker_present": {"submit_live_order", "send_order", "place_order", "execute_trade"},
        "executable_order_marker_present": {"real_order_id", "mt5_order_request", "executable_order"},
        "mt5_payload_marker_present": {"mt5_order_payload", "mt5_payload"} - allowed_fields,
        "mt5_ticket_marker_present": {"mt5_ticket", "deal_id"},
        "raw_candle_marker_present": {"raw_candles", "raw_ohlcv", "ohlcv_bars"},
        "raw_knowledge_marker_present": {"full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"},
        "account_or_credential_marker_present": {"raw_account_id", "account_id", "api_key", "password", "secret", "credentials"},
    }
    for issue, markers in field_markers.items():
        if fields.intersection(markers):
            issues.append(issue)
    value_patterns = {
        "order_submission_marker_present": [r"\border" + r"_send\b"],
        "live_method_marker_present": [r"\bsubmit_live_order\b", r"\bsend_order\b", r"\bplace_order\b", r"\bexecute_trade\b"],
        "executable_order_marker_present": [r"\breal_order_id\b", r"\bmt5_order_request\b", r"\bexecutable_order\b"],
        "mt5_payload_marker_present": [r"\bmt5_order_payload\b", r"\bmt5_payload\b"],
        "mt5_ticket_marker_present": [r"\bmt5_ticket\b", r"\bdeal_id\b"],
        "raw_candle_marker_present": [r"\braw_candles\b", r"\braw_ohlcv\b", r"\bohlcv_bars\b"],
        "raw_knowledge_marker_present": [r"\bfull_raw_book\b", r"\bfull_raw_report\b", r"\braw_full_book\b", r"\braw_full_report\b"],
        "account_or_credential_marker_present": [
            r"\braw_account_id\b",
            r"\baccount_id\b",
            r"\bapi_key\b",
            r"\bpassword\b",
            r"\bsecret\b",
            r"\bcredentials\b",
        ],
        "metatrader_marker_present": [r"\bmeta" + r"trader5\b"],
        "llm_prompt_marker_present": [r"\bcompact_prompt\b", r"\bllm_prompt\b"],
    }
    for issue, patterns in value_patterns.items():
        if any(re.search(pattern, values) for pattern in patterns):
            issues.append(issue)
    return list(dict.fromkeys(issues))


def _value_scan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    skipped = {
        "value_slots",
        "required_value_slot_types",
        "missing_value_slot_types",
        "reviewed_value_slot_types",
        "approved_value_slot_types",
        "rejected_value_slot_types",
        "source_refs",
        "validation_checks",
    }
    return {key: value for key, value in payload.items() if key not in skipped}


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_flatten_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_flatten_keys(item))
    return keys


def _flatten_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_flatten_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_flatten_values(item))
    elif isinstance(value, str):
        values.append(value)
    return values
