from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_VALUE_PROPOSAL_WORKFLOW",
    "DRAFT_CREATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_SCOPES = {
    "VALUE_PROPOSAL_WORKFLOW_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
HUMAN_REVIEWED_PARAMETER_SLOT_TYPES = {
    "SIDE_SLOT",
    "PRICE_SLOT",
    "PROTECTION_SLOT",
    "VOLUME_SLOT",
    "RISK_SLOT",
    "BROKER_SYMBOL_SLOT",
    "EXECUTION_TIMING_SLOT",
    "IDEMPOTENCY_SLOT",
    "AUDIT_SLOT",
    "UNKNOWN",
}
HUMAN_REVIEWED_PARAMETER_SLOT_STATUSES = {
    "UNRESOLVED",
    "WAITING_FOR_FUTURE_VALUE_PROPOSAL",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
HUMAN_REVIEWED_PARAMETER_REVIEW_REQUIREMENTS = {
    "HUMAN_REVIEW_REQUIRED",
    "SOURCE_TRACE_REQUIRED",
    "DETERMINISTIC_VALIDATION_REQUIRED",
    "FRESHNESS_CHECK_REQUIRED",
    "BROKER_CAPABILITY_CHECK_REQUIRED",
    "RISK_POLICY_CHECK_REQUIRED",
    "AUDIT_REQUIRED",
    "REDACTION_REQUIRED",
    "UNKNOWN",
}
HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_BLOCK_REASONS = {
    "MISSING_SOURCE_BOUNDARY",
    "MISSING_SOURCE_BOUNDARY_VALIDATION",
    "HUMAN_REVIEWED_PARAMETER_DRAFT_NOT_ALLOWED",
    "MISSING_PARAMETER_POLICY_SPEC",
    "MISSING_CONTRACT_SKELETON",
    "MISSING_LIVE_ORDER_INTENT",
    "MISSING_PERMISSION_DECISION",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_PROPOSAL_DRAFT",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "MISSING_REQUIRED_SLOTS",
    "SLOT_VALUE_NOT_ALLOWED",
    "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED",
    "ACTUAL_ORDER_VALUES_NOT_ALLOWED",
    "EXPIRED_PARAMETER_DRAFT",
    "DUPLICATE_PARAMETER_DRAFT",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_JOURNAL_EVENT_TYPES = {
    "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_CREATED",
    "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_BLOCKED",
    "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_DUPLICATE_DETECTED",
    "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}

REQUIRED_HUMAN_REVIEWED_SLOT_MAP = {
    "SIDE_SLOT": "SIDE_POLICY",
    "PRICE_SLOT": "PRICE_POLICY",
    "PROTECTION_SLOT": "PROTECTION_POLICY",
    "VOLUME_SLOT": "VOLUME_POLICY",
    "RISK_SLOT": "RISK_POLICY",
    "BROKER_SYMBOL_SLOT": "BROKER_SYMBOL_POLICY",
    "EXECUTION_TIMING_SLOT": "EXECUTION_TIMING_POLICY",
    "IDEMPOTENCY_SLOT": "IDEMPOTENCY_POLICY",
    "AUDIT_SLOT": "AUDIT_POLICY",
}
REQUIRED_HUMAN_REVIEWED_SLOT_TYPES = list(REQUIRED_HUMAN_REVIEWED_SLOT_MAP.keys())


@dataclass
class HumanReviewedParameterSlot:
    slot_id: str
    slot_type: str
    parameter_group: str
    status: str
    title: str
    description: str
    value_allowed_now: bool = False
    value_resolved_now: bool = False
    actual_value_present: bool = False
    review_requirements: List[str] = field(default_factory=list)
    source_candidate_ids: List[str] = field(default_factory=list)
    future_evidence_required: List[str] = field(default_factory=list)
    human_review_required: bool = False
    deterministic_validation_required: bool = True
    freshness_required: bool = False
    broker_capability_required: bool = False
    risk_policy_required: bool = False
    audit_required: bool = False
    redaction_required: bool = False
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "slot_type": self.slot_type if self.slot_type in HUMAN_REVIEWED_PARAMETER_SLOT_TYPES else "UNKNOWN",
            "parameter_group": self.parameter_group,
            "status": self.status if self.status in HUMAN_REVIEWED_PARAMETER_SLOT_STATUSES else "UNKNOWN",
            "title": self.title,
            "description": self.description,
            "value_allowed_now": False,
            "value_resolved_now": False,
            "actual_value_present": False,
            "review_requirements": _labels(self.review_requirements, HUMAN_REVIEWED_PARAMETER_REVIEW_REQUIREMENTS),
            "source_candidate_ids": _dedupe(self.source_candidate_ids),
            "future_evidence_required": _dedupe(self.future_evidence_required),
            "human_review_required": bool(self.human_review_required),
            "deterministic_validation_required": bool(self.deterministic_validation_required),
            "freshness_required": bool(self.freshness_required),
            "broker_capability_required": bool(self.broker_capability_required),
            "risk_policy_required": bool(self.risk_policy_required),
            "audit_required": bool(self.audit_required),
            "redaction_required": bool(self.redaction_required),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
        }


@dataclass
class HumanReviewedLiveParameterDraft:
    draft_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    value_proposal_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    resolved_parameter_values_present: bool = False
    actual_order_values_present: bool = False
    source_parameter_source_boundary_id: str = ""
    source_parameter_source_validation_id: str = ""
    source_parameter_policy_spec_id: str = ""
    source_parameter_policy_validation_id: str = ""
    source_contract_skeleton_id: str = ""
    source_contract_skeleton_validation_id: str = ""
    source_live_order_intent_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    slots: List[HumanReviewedParameterSlot] = field(default_factory=list)
    required_slot_types: List[str] = field(default_factory=list)
    missing_slot_types: List[str] = field(default_factory=list)
    unresolved_slot_types: List[str] = field(default_factory=list)
    resolved_slot_types: List[str] = field(default_factory=list)
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
            "draft_id": self.draft_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_SCOPES else "UNKNOWN",
            "value_proposal_workflow_allowed": bool(self.value_proposal_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "source_parameter_source_boundary_id": self.source_parameter_source_boundary_id,
            "source_parameter_source_validation_id": self.source_parameter_source_validation_id,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_parameter_policy_validation_id": self.source_parameter_policy_validation_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_contract_skeleton_validation_id": self.source_contract_skeleton_validation_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "slots": [slot.as_dict() for slot in self.slots],
            "required_slot_types": _labels(self.required_slot_types, HUMAN_REVIEWED_PARAMETER_SLOT_TYPES),
            "missing_slot_types": _labels(self.missing_slot_types, HUMAN_REVIEWED_PARAMETER_SLOT_TYPES),
            "unresolved_slot_types": _labels(self.unresolved_slot_types, HUMAN_REVIEWED_PARAMETER_SLOT_TYPES),
            "resolved_slot_types": [],
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
class HumanReviewedLiveParameterDraftValidationReport:
    validation_report_id: str
    created_at: str
    source_draft_id: str
    valid: bool
    value_proposal_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    slots_count: int
    unresolved_slots_count: int
    resolved_slots_count: int
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
            "source_draft_id": self.source_draft_id,
            "valid": bool(self.valid),
            "value_proposal_workflow_allowed": bool(self.value_proposal_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "slots_count": int(self.slots_count),
            "unresolved_slots_count": int(self.unresolved_slots_count),
            "resolved_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class HumanReviewedLiveParameterDraftJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    draft_id: str
    validation_report_id: str
    status: str
    scope: str
    value_proposal_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    slots_count: int
    unresolved_slots_count: int
    resolved_slots_count: int
    missing_slots_count: int
    artifact_hash: str
    idempotency_key: str
    source_parameter_source_boundary_id: str
    source_parameter_source_validation_id: str
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
            "event_type": self.event_type if self.event_type in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "draft_id": self.draft_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_SCOPES else "UNKNOWN",
            "value_proposal_workflow_allowed": bool(self.value_proposal_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "slots_count": int(self.slots_count),
            "unresolved_slots_count": int(self.unresolved_slots_count),
            "resolved_slots_count": 0,
            "missing_slots_count": int(self.missing_slots_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_parameter_source_boundary_id": self.source_parameter_source_boundary_id,
            "source_parameter_source_validation_id": self.source_parameter_source_validation_id,
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
class HumanReviewedLiveParameterDraftSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_draft_id: str = ""
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
            "latest_draft_id": self.latest_draft_id,
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
