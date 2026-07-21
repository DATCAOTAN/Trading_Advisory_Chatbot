from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE = (
    "I understand this final review only allows a future Pre-MT5 mapping boundary and does not create or send an order"
)

LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_PRE_MT5_MAPPING_BOUNDARY",
    "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "REJECTED",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_FINAL_REVIEW_SCOPES = {
    "PRE_MT5_MAPPING_BOUNDARY_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_FINAL_REVIEW_ACTIONS = {
    "APPROVE_FOR_FUTURE_PRE_MT5_MAPPING_ONLY",
    "REJECT",
    "EXPIRE",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATES = {
    "NOT_REVIEWED",
    "HUMAN_REVIEW_APPROVED_FOR_FUTURE_MAPPING_ONLY",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_VALIDATION_SEVERITIES = {"INFO", "WARNING", "BLOCKING", "CRITICAL"}
LIVE_ORDER_CONTRACT_SLOT_VALIDATION_STATUSES = {
    "VALIDATION_ONLY_READY",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_FINAL_REVIEW_BLOCK_REASONS = {
    "MISSING_PARAMETERIZATION",
    "MISSING_PARAMETERIZATION_VALIDATION",
    "CONTRACT_VALIDATION_WORKFLOW_NOT_ALLOWED",
    "MISSING_APPROVAL_LOCK",
    "MISSING_VALUE_PROPOSAL",
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
    "MISSING_REQUIRED_SLOT_VALIDATIONS",
    "WRONG_CONFIRMATION_PHRASE",
    "CONFIRMATION_EXPIRED",
    "FINAL_HUMAN_REVIEW_NOT_APPROVED",
    "RAW_VALUES_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "ORDER_REQUEST_MAPPING_NOT_ALLOWED",
    "PRE_MT5_MAPPING_NOT_ALLOWED",
    "EXPIRED_FINAL_REVIEW",
    "DUPLICATE_FINAL_REVIEW",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_FINAL_REVIEW_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_CONTRACT_FINAL_REVIEW_APPROVED",
    "LIVE_ORDER_CONTRACT_FINAL_REVIEW_BLOCKED",
    "LIVE_ORDER_CONTRACT_FINAL_REVIEW_DUPLICATE_DETECTED",
    "LIVE_ORDER_CONTRACT_FINAL_REVIEW_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}
REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES = [
    "SIDE_CONTRACT_SLOT",
    "PRICE_CONTRACT_SLOT",
    "PROTECTION_CONTRACT_SLOT",
    "VOLUME_CONTRACT_SLOT",
    "RISK_CONTRACT_SLOT",
    "BROKER_SYMBOL_CONTRACT_SLOT",
    "EXECUTION_TIMING_CONTRACT_SLOT",
    "IDEMPOTENCY_CONTRACT_SLOT",
    "AUDIT_CONTRACT_SLOT",
]


@dataclass
class LiveOrderContractFinalReviewConfirmation:
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
            "phrase": "[REDACTED]",
            "expected_phrase": "[REDACTED]",
            "phrase_valid": bool(self.phrase_valid),
            "action": self.action if self.action in LIVE_ORDER_CONTRACT_FINAL_REVIEW_ACTIONS else "UNKNOWN",
            "review_state": self.review_state if self.review_state in LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATES else "UNKNOWN",
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
        }


@dataclass
class LiveOrderContractSlotValidation:
    slot_validation_id: str
    source_contract_slot_id: str
    source_slot_lock_id: str
    source_value_slot_id: str
    slot_type: str
    status: str
    severity: str
    validation_only_ready: bool = True
    raw_value_stored: bool = False
    executable_value: bool = False
    mt5_payload_value: bool = False
    order_request_value: bool = False
    broker_mapping_created: bool = False
    final_human_review_required: bool = True
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot_validation_id": self.slot_validation_id,
            "source_contract_slot_id": self.source_contract_slot_id,
            "source_slot_lock_id": self.source_slot_lock_id,
            "source_value_slot_id": self.source_value_slot_id,
            "slot_type": self.slot_type if self.slot_type in REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES else "UNKNOWN",
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_SLOT_VALIDATION_STATUSES else "UNKNOWN",
            "severity": self.severity if self.severity in LIVE_ORDER_CONTRACT_VALIDATION_SEVERITIES else "CRITICAL",
            "validation_only_ready": True,
            "raw_value_stored": False,
            "executable_value": False,
            "mt5_payload_value": False,
            "order_request_value": False,
            "broker_mapping_created": False,
            "final_human_review_required": True,
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class LiveOrderContractFinalReview:
    final_review_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    pre_mt5_mapping_boundary_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    order_request_mapping_allowed: bool = False
    broker_mapping_created: bool = False
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_parameterization_id: str = ""
    source_parameterization_validation_id: str = ""
    source_approval_lock_id: str = ""
    source_approval_lock_validation_id: str = ""
    source_value_proposal_id: str = ""
    source_parameter_draft_id: str = ""
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
    final_review_action: str = "UNKNOWN"
    final_review_state: str = "UNKNOWN"
    slot_validations: List[LiveOrderContractSlotValidation] = field(default_factory=list)
    required_slot_validation_types: List[str] = field(default_factory=list)
    passed_slot_validation_types: List[str] = field(default_factory=list)
    blocked_slot_validation_types: List[str] = field(default_factory=list)
    missing_slot_validation_types: List[str] = field(default_factory=list)
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
            "final_review_id": self.final_review_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_FINAL_REVIEW_SCOPES else "UNKNOWN",
            "pre_mt5_mapping_boundary_workflow_allowed": bool(self.pre_mt5_mapping_boundary_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_parameterization_id": self.source_parameterization_id,
            "source_parameterization_validation_id": self.source_parameterization_validation_id,
            "source_approval_lock_id": self.source_approval_lock_id,
            "source_approval_lock_validation_id": self.source_approval_lock_validation_id,
            "source_value_proposal_id": self.source_value_proposal_id,
            "source_parameter_draft_id": self.source_parameter_draft_id,
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
            "final_review_action": self.final_review_action,
            "final_review_state": self.final_review_state,
            "slot_validations": [slot.as_dict() for slot in self.slot_validations],
            "required_slot_validation_types": _dedupe(self.required_slot_validation_types),
            "passed_slot_validation_types": _dedupe(self.passed_slot_validation_types),
            "blocked_slot_validation_types": _dedupe(self.blocked_slot_validation_types),
            "missing_slot_validation_types": _dedupe(self.missing_slot_validation_types),
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
class LiveOrderContractFinalReviewValidationReport:
    validation_report_id: str
    created_at: str
    source_final_review_id: str
    valid: bool
    pre_mt5_mapping_boundary_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    slot_validations_count: int
    passed_slot_validations_count: int
    blocked_slot_validations_count: int
    missing_slot_validations_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_final_review_id": self.source_final_review_id,
            "valid": bool(self.valid),
            "pre_mt5_mapping_boundary_workflow_allowed": bool(self.pre_mt5_mapping_boundary_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "slot_validations_count": int(self.slot_validations_count),
            "passed_slot_validations_count": int(self.passed_slot_validations_count),
            "blocked_slot_validations_count": int(self.blocked_slot_validations_count),
            "missing_slot_validations_count": int(self.missing_slot_validations_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderContractFinalReviewJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    final_review_id: str
    validation_report_id: str
    status: str
    scope: str
    pre_mt5_mapping_boundary_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    slot_validations_count: int
    passed_slot_validations_count: int
    blocked_slot_validations_count: int
    missing_slot_validations_count: int
    artifact_hash: str
    idempotency_key: str
    source_parameterization_id: str
    source_parameterization_validation_id: str
    source_approval_lock_id: str
    source_value_proposal_id: str
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
            "event_type": self.event_type if self.event_type in LIVE_ORDER_CONTRACT_FINAL_REVIEW_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "final_review_id": self.final_review_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_FINAL_REVIEW_SCOPES else "UNKNOWN",
            "pre_mt5_mapping_boundary_workflow_allowed": bool(self.pre_mt5_mapping_boundary_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "slot_validations_count": int(self.slot_validations_count),
            "passed_slot_validations_count": int(self.passed_slot_validations_count),
            "blocked_slot_validations_count": int(self.blocked_slot_validations_count),
            "missing_slot_validations_count": int(self.missing_slot_validations_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_parameterization_id": self.source_parameterization_id,
            "source_parameterization_validation_id": self.source_parameterization_validation_id,
            "source_approval_lock_id": self.source_approval_lock_id,
            "source_value_proposal_id": self.source_value_proposal_id,
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
class LiveOrderContractFinalReviewSummary:
    total_records: int = 0
    total_approved: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_final_review_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_approved": int(self.total_approved),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_final_review_id": self.latest_final_review_id,
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
