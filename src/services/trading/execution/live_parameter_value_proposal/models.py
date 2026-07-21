from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


CONTROLLED_VALUE_PROPOSAL_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_HUMAN_VALUE_APPROVAL",
    "PROPOSAL_CREATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
CONTROLLED_VALUE_PROPOSAL_SCOPES = {"HUMAN_VALUE_APPROVAL_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
CONTROLLED_VALUE_SLOT_TYPES = {
    "SIDE_VALUE_PROPOSAL_SLOT",
    "PRICE_VALUE_PROPOSAL_SLOT",
    "PROTECTION_VALUE_PROPOSAL_SLOT",
    "VOLUME_VALUE_PROPOSAL_SLOT",
    "RISK_VALUE_PROPOSAL_SLOT",
    "BROKER_SYMBOL_VALUE_PROPOSAL_SLOT",
    "EXECUTION_TIMING_VALUE_PROPOSAL_SLOT",
    "IDEMPOTENCY_VALUE_PROPOSAL_SLOT",
    "AUDIT_VALUE_PROPOSAL_SLOT",
    "UNKNOWN",
}
CONTROLLED_VALUE_SLOT_STATUSES = {"PROPOSED_FOR_REVIEW", "REVIEW_REQUIRED", "BLOCKED", "INVALID", "UNKNOWN"}
CONTROLLED_VALUE_REVIEW_STATES = {
    "NOT_REVIEWED",
    "HUMAN_REVIEW_REQUIRED",
    "REJECTED",
    "APPROVED_FOR_FUTURE_LOCK_ONLY",
    "UNKNOWN",
}
CONTROLLED_VALUE_PROPOSAL_BLOCK_REASONS = {
    "MISSING_PARAMETER_DRAFT",
    "MISSING_PARAMETER_DRAFT_VALIDATION",
    "VALUE_PROPOSAL_WORKFLOW_NOT_ALLOWED",
    "MISSING_SOURCE_BOUNDARY",
    "MISSING_PARAMETER_POLICY_SPEC",
    "MISSING_CONTRACT_SKELETON",
    "MISSING_LIVE_ORDER_INTENT",
    "MISSING_PERMISSION_DECISION",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_PROPOSAL_DRAFT",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "MISSING_REQUIRED_VALUE_SLOTS",
    "HUMAN_REVIEW_NOT_COMPLETED",
    "VALUE_LOCK_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "EXPIRED_VALUE_PROPOSAL",
    "DUPLICATE_VALUE_PROPOSAL",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
CONTROLLED_VALUE_PROPOSAL_JOURNAL_EVENT_TYPES = {
    "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_CREATED",
    "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_BLOCKED",
    "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_DUPLICATE_DETECTED",
    "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}

REQUIRED_CONTROLLED_VALUE_SLOT_MAP = {
    "SIDE_VALUE_PROPOSAL_SLOT": "SIDE_SLOT",
    "PRICE_VALUE_PROPOSAL_SLOT": "PRICE_SLOT",
    "PROTECTION_VALUE_PROPOSAL_SLOT": "PROTECTION_SLOT",
    "VOLUME_VALUE_PROPOSAL_SLOT": "VOLUME_SLOT",
    "RISK_VALUE_PROPOSAL_SLOT": "RISK_SLOT",
    "BROKER_SYMBOL_VALUE_PROPOSAL_SLOT": "BROKER_SYMBOL_SLOT",
    "EXECUTION_TIMING_VALUE_PROPOSAL_SLOT": "EXECUTION_TIMING_SLOT",
    "IDEMPOTENCY_VALUE_PROPOSAL_SLOT": "IDEMPOTENCY_SLOT",
    "AUDIT_VALUE_PROPOSAL_SLOT": "AUDIT_SLOT",
}
REQUIRED_CONTROLLED_VALUE_SLOT_TYPES = list(REQUIRED_CONTROLLED_VALUE_SLOT_MAP.keys())


@dataclass
class ControlledLiveParameterValueSlot:
    value_slot_id: str
    slot_type: str
    source_draft_slot_id: str
    parameter_group: str
    status: str
    review_state: str
    title: str
    description: str
    proposed_value_present: bool = False
    proposed_value_redacted: bool = True
    value_lock_required: bool = True
    human_review_required: bool = True
    deterministic_validation_required: bool = True
    source_trace_required: bool = True
    freshness_check_required: bool = False
    broker_capability_check_required: bool = False
    risk_policy_check_required: bool = False
    audit_required: bool = False
    redaction_required: bool = True
    executable_value: bool = False
    source_candidate_ids: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "value_slot_id": self.value_slot_id,
            "slot_type": self.slot_type if self.slot_type in CONTROLLED_VALUE_SLOT_TYPES else "UNKNOWN",
            "source_draft_slot_id": self.source_draft_slot_id,
            "parameter_group": self.parameter_group,
            "status": self.status if self.status in CONTROLLED_VALUE_SLOT_STATUSES else "UNKNOWN",
            "review_state": self.review_state if self.review_state in CONTROLLED_VALUE_REVIEW_STATES else "UNKNOWN",
            "title": self.title,
            "description": self.description,
            "proposed_value_present": bool(self.proposed_value_present),
            "proposed_value_redacted": True,
            "value_lock_required": True,
            "human_review_required": True,
            "deterministic_validation_required": bool(self.deterministic_validation_required),
            "source_trace_required": bool(self.source_trace_required),
            "freshness_check_required": bool(self.freshness_check_required),
            "broker_capability_check_required": bool(self.broker_capability_check_required),
            "risk_policy_check_required": bool(self.risk_policy_check_required),
            "audit_required": bool(self.audit_required),
            "redaction_required": bool(self.redaction_required),
            "executable_value": False,
            "source_candidate_ids": _dedupe(self.source_candidate_ids),
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class ControlledLiveParameterValueProposal:
    proposal_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    human_value_approval_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    value_lock_required: bool = True
    human_review_required: bool = True
    source_parameter_draft_id: str = ""
    source_parameter_draft_validation_id: str = ""
    source_parameter_source_boundary_id: str = ""
    source_parameter_source_validation_id: str = ""
    source_parameter_policy_spec_id: str = ""
    source_contract_skeleton_id: str = ""
    source_live_order_intent_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    value_slots: List[ControlledLiveParameterValueSlot] = field(default_factory=list)
    required_value_slot_types: List[str] = field(default_factory=list)
    missing_value_slot_types: List[str] = field(default_factory=list)
    reviewed_value_slot_types: List[str] = field(default_factory=list)
    approved_value_slot_types: List[str] = field(default_factory=list)
    rejected_value_slot_types: List[str] = field(default_factory=list)
    artifact_hash: str = ""
    idempotency_key: str = ""
    expires_at: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in CONTROLLED_VALUE_PROPOSAL_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in CONTROLLED_VALUE_PROPOSAL_SCOPES else "UNKNOWN",
            "human_value_approval_allowed": bool(self.human_value_approval_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "value_lock_required": True,
            "human_review_required": True,
            "source_parameter_draft_id": self.source_parameter_draft_id,
            "source_parameter_draft_validation_id": self.source_parameter_draft_validation_id,
            "source_parameter_source_boundary_id": self.source_parameter_source_boundary_id,
            "source_parameter_source_validation_id": self.source_parameter_source_validation_id,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "value_slots": [slot.as_dict() for slot in self.value_slots],
            "required_value_slot_types": _labels(self.required_value_slot_types, CONTROLLED_VALUE_SLOT_TYPES),
            "missing_value_slot_types": _labels(self.missing_value_slot_types, CONTROLLED_VALUE_SLOT_TYPES),
            "reviewed_value_slot_types": _labels(self.reviewed_value_slot_types, CONTROLLED_VALUE_SLOT_TYPES),
            "approved_value_slot_types": [],
            "rejected_value_slot_types": [],
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "reasons": _dedupe(self.reasons),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ControlledLiveParameterValueProposalValidationReport:
    validation_report_id: str
    created_at: str
    source_proposal_id: str
    valid: bool
    human_value_approval_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    value_lock_required: bool
    human_review_required: bool
    value_slots_count: int
    review_required_slots_count: int
    approved_slots_count: int
    rejected_slots_count: int
    missing_slots_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_proposal_id": self.source_proposal_id,
            "valid": bool(self.valid),
            "human_value_approval_allowed": bool(self.human_value_approval_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "value_lock_required": True,
            "human_review_required": True,
            "value_slots_count": int(self.value_slots_count),
            "review_required_slots_count": int(self.review_required_slots_count),
            "approved_slots_count": 0,
            "rejected_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ControlledLiveParameterValueProposalJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    proposal_id: str
    validation_report_id: str
    status: str
    scope: str
    human_value_approval_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    value_lock_required: bool
    human_review_required: bool
    value_slots_count: int
    review_required_slots_count: int
    approved_slots_count: int
    rejected_slots_count: int
    missing_slots_count: int
    artifact_hash: str
    idempotency_key: str
    source_parameter_draft_id: str
    source_parameter_draft_validation_id: str
    source_parameter_source_boundary_id: str
    source_parameter_policy_spec_id: str
    source_contract_skeleton_id: str
    source_live_order_intent_id: str
    source_live_permission_decision_id: str
    source_preflight_report_id: str
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in CONTROLLED_VALUE_PROPOSAL_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "proposal_id": self.proposal_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in CONTROLLED_VALUE_PROPOSAL_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in CONTROLLED_VALUE_PROPOSAL_SCOPES else "UNKNOWN",
            "human_value_approval_allowed": bool(self.human_value_approval_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "value_lock_required": True,
            "human_review_required": True,
            "value_slots_count": int(self.value_slots_count),
            "review_required_slots_count": int(self.review_required_slots_count),
            "approved_slots_count": 0,
            "rejected_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_parameter_draft_id": self.source_parameter_draft_id,
            "source_parameter_draft_validation_id": self.source_parameter_draft_validation_id,
            "source_parameter_source_boundary_id": self.source_parameter_source_boundary_id,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class ControlledLiveParameterValueProposalSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_proposal_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_created": int(self.total_created),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_proposal_id": self.latest_proposal_id,
            "latest_validation_report_id": self.latest_validation_report_id,
            "latest_status": self.latest_status,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _labels(items: List[Any] | None, allowed: set[str]) -> List[str]:
    return [str(item) if str(item) in allowed else "UNKNOWN" for item in _dedupe(items)]


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
