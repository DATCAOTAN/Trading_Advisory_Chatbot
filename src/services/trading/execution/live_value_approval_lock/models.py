from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


HUMAN_VALUE_APPROVAL_LOCK_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_CONTRACT_PARAMETERIZATION",
    "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "REJECTED",
    "UNKNOWN",
}
HUMAN_VALUE_APPROVAL_LOCK_SCOPES = {"CONTRACT_PARAMETERIZATION_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
HUMAN_VALUE_APPROVAL_ACTIONS = {
    "APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY",
    "REJECT",
    "EXPIRE",
    "UNKNOWN",
}
HUMAN_VALUE_APPROVAL_REVIEW_STATES = {
    "NOT_REVIEWED",
    "HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
}
HUMAN_VALUE_LOCK_STATES = {
    "NOT_LOCKED",
    "LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY",
    "BLOCKED",
    "EXPIRED",
    "UNKNOWN",
}
HUMAN_VALUE_APPROVAL_SLOT_LOCK_STATUSES = {
    "LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY",
    "REVIEW_REQUIRED",
    "REJECTED",
    "BLOCKED",
    "UNKNOWN",
}
HUMAN_VALUE_APPROVAL_LOCK_BLOCK_REASONS = {
    "MISSING_VALUE_PROPOSAL",
    "MISSING_VALUE_PROPOSAL_VALIDATION",
    "HUMAN_VALUE_APPROVAL_NOT_ALLOWED",
    "MISSING_PARAMETER_DRAFT",
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
    "MISSING_REQUIRED_LOCK_SLOTS",
    "WRONG_CONFIRMATION_PHRASE",
    "CONFIRMATION_EXPIRED",
    "HUMAN_REVIEW_NOT_APPROVED",
    "VALUE_LOCK_NOT_REQUIRED",
    "VALUE_LOCK_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "EXPIRED_APPROVAL_LOCK",
    "DUPLICATE_APPROVAL_LOCK",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
HUMAN_VALUE_APPROVAL_LOCK_JOURNAL_EVENT_TYPES = {
    "HUMAN_VALUE_APPROVAL_LOCK_CREATED",
    "HUMAN_VALUE_APPROVAL_LOCK_BLOCKED",
    "HUMAN_VALUE_APPROVAL_LOCK_REJECTED",
    "HUMAN_VALUE_APPROVAL_LOCK_DUPLICATE_DETECTED",
    "HUMAN_VALUE_APPROVAL_LOCK_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}

REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES = [
    "SIDE_VALUE_PROPOSAL_SLOT",
    "PRICE_VALUE_PROPOSAL_SLOT",
    "PROTECTION_VALUE_PROPOSAL_SLOT",
    "VOLUME_VALUE_PROPOSAL_SLOT",
    "RISK_VALUE_PROPOSAL_SLOT",
    "BROKER_SYMBOL_VALUE_PROPOSAL_SLOT",
    "EXECUTION_TIMING_VALUE_PROPOSAL_SLOT",
    "IDEMPOTENCY_VALUE_PROPOSAL_SLOT",
    "AUDIT_VALUE_PROPOSAL_SLOT",
]


@dataclass
class HumanValueApprovalConfirmation:
    confirmation_id: str
    created_at: str
    phrase: str
    expected_phrase: str
    phrase_valid: bool
    action: str
    review_state: str
    expires_at: str
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "created_at": self.created_at,
            "phrase": self.phrase,
            "expected_phrase": self.expected_phrase,
            "phrase_valid": bool(self.phrase_valid),
            "action": self.action if self.action in HUMAN_VALUE_APPROVAL_ACTIONS else "UNKNOWN",
            "review_state": self.review_state if self.review_state in HUMAN_VALUE_APPROVAL_REVIEW_STATES else "UNKNOWN",
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
        }


@dataclass
class HumanValueApprovalSlotLock:
    slot_lock_id: str
    source_value_slot_id: str
    source_draft_slot_id: str
    slot_type: str
    status: str
    review_state: str
    lock_state: str
    approved_for_future_parameterization: bool
    raw_value_stored: bool = False
    executable_value: bool = False
    mt5_payload_value: bool = False
    order_value: bool = False
    value_payload_redacted: bool = True
    source_candidate_ids: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_lock_id": self.slot_lock_id,
            "source_value_slot_id": self.source_value_slot_id,
            "source_draft_slot_id": self.source_draft_slot_id,
            "slot_type": self.slot_type,
            "status": self.status if self.status in HUMAN_VALUE_APPROVAL_SLOT_LOCK_STATUSES else "UNKNOWN",
            "review_state": self.review_state if self.review_state in HUMAN_VALUE_APPROVAL_REVIEW_STATES else "UNKNOWN",
            "lock_state": self.lock_state if self.lock_state in HUMAN_VALUE_LOCK_STATES else "UNKNOWN",
            "approved_for_future_parameterization": bool(self.approved_for_future_parameterization),
            "raw_value_stored": False,
            "executable_value": False,
            "mt5_payload_value": False,
            "order_value": False,
            "value_payload_redacted": True,
            "source_candidate_ids": _dedupe(self.source_candidate_ids),
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class HumanValueApprovalLock:
    approval_lock_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    contract_parameterization_workflow_allowed: bool = False
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
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_value_proposal_id: str = ""
    source_value_proposal_validation_id: str = ""
    source_parameter_draft_id: str = ""
    source_parameter_draft_validation_id: str = ""
    source_parameter_source_boundary_id: str = ""
    source_parameter_policy_spec_id: str = ""
    source_contract_skeleton_id: str = ""
    source_live_order_intent_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    confirmation_id: str = ""
    confirmation_phrase_valid: bool = False
    approval_action: str = "UNKNOWN"
    review_state: str = "UNKNOWN"
    lock_state: str = "UNKNOWN"
    slot_locks: List[HumanValueApprovalSlotLock] = field(default_factory=list)
    required_slot_lock_types: List[str] = field(default_factory=list)
    locked_slot_types: List[str] = field(default_factory=list)
    rejected_slot_types: List[str] = field(default_factory=list)
    missing_slot_lock_types: List[str] = field(default_factory=list)
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
            "approval_lock_id": self.approval_lock_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in HUMAN_VALUE_APPROVAL_LOCK_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in HUMAN_VALUE_APPROVAL_LOCK_SCOPES else "UNKNOWN",
            "contract_parameterization_workflow_allowed": bool(self.contract_parameterization_workflow_allowed),
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
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_value_proposal_id": self.source_value_proposal_id,
            "source_value_proposal_validation_id": self.source_value_proposal_validation_id,
            "source_parameter_draft_id": self.source_parameter_draft_id,
            "source_parameter_draft_validation_id": self.source_parameter_draft_validation_id,
            "source_parameter_source_boundary_id": self.source_parameter_source_boundary_id,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "confirmation_id": self.confirmation_id,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "approval_action": self.approval_action if self.approval_action in HUMAN_VALUE_APPROVAL_ACTIONS else "UNKNOWN",
            "review_state": self.review_state if self.review_state in HUMAN_VALUE_APPROVAL_REVIEW_STATES else "UNKNOWN",
            "lock_state": self.lock_state if self.lock_state in HUMAN_VALUE_LOCK_STATES else "UNKNOWN",
            "slot_locks": [slot_lock.as_dict() for slot_lock in self.slot_locks],
            "required_slot_lock_types": _dedupe(self.required_slot_lock_types),
            "locked_slot_types": _dedupe(self.locked_slot_types),
            "rejected_slot_types": [],
            "missing_slot_lock_types": _dedupe(self.missing_slot_lock_types),
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
class HumanValueApprovalLockValidationReport:
    validation_report_id: str
    created_at: str
    source_approval_lock_id: str
    valid: bool
    contract_parameterization_workflow_allowed: bool
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
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    slot_locks_count: int
    locked_slots_count: int
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
            "source_approval_lock_id": self.source_approval_lock_id,
            "valid": bool(self.valid),
            "contract_parameterization_workflow_allowed": bool(self.contract_parameterization_workflow_allowed),
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
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "slot_locks_count": int(self.slot_locks_count),
            "locked_slots_count": int(self.locked_slots_count),
            "rejected_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class HumanValueApprovalLockJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    approval_lock_id: str
    validation_report_id: str
    status: str
    scope: str
    contract_parameterization_workflow_allowed: bool
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
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    slot_locks_count: int
    locked_slots_count: int
    rejected_slots_count: int
    missing_slots_count: int
    artifact_hash: str
    idempotency_key: str
    source_value_proposal_id: str
    source_value_proposal_validation_id: str
    source_parameter_draft_id: str
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
            "event_type": self.event_type if self.event_type in HUMAN_VALUE_APPROVAL_LOCK_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "approval_lock_id": self.approval_lock_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in HUMAN_VALUE_APPROVAL_LOCK_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in HUMAN_VALUE_APPROVAL_LOCK_SCOPES else "UNKNOWN",
            "contract_parameterization_workflow_allowed": bool(self.contract_parameterization_workflow_allowed),
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
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "slot_locks_count": int(self.slot_locks_count),
            "locked_slots_count": int(self.locked_slots_count),
            "rejected_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_value_proposal_id": self.source_value_proposal_id,
            "source_value_proposal_validation_id": self.source_value_proposal_validation_id,
            "source_parameter_draft_id": self.source_parameter_draft_id,
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
class HumanValueApprovalLockSummary:
    total_records: int = 0
    total_locked: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_approval_lock_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_locked": int(self.total_locked),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_approval_lock_id": self.latest_approval_lock_id,
            "latest_validation_report_id": self.latest_validation_report_id,
            "latest_status": self.latest_status,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
