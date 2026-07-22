from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping


APPROVED_SEMANTIC_EXECUTION_SCHEMA_VERSION = "approved-semantic-execution-parameters/v1"
APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES = (
    "action",
    "symbol",
    "volume",
    "order_type",
    "price",
    "stop_loss",
    "take_profit",
    "deviation",
    "magic",
    "comment",
    "idempotency",
    "audit",
)


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
    "INVALID_APPROVED_SEMANTIC_VALUES",
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


@dataclass(frozen=True)
class ApprovedSemanticExecutionParameters:
    schema_version: str
    action: str = field(repr=False)
    symbol: str = field(repr=False)
    volume: Decimal = field(repr=False)
    order_type: str = field(repr=False)
    price: Decimal = field(repr=False)
    stop_loss: Decimal = field(repr=False)
    take_profit: Decimal = field(repr=False)
    deviation: int = field(repr=False)
    magic: int = field(repr=False)
    comment: str = field(repr=False)
    idempotency: str = field(repr=False)
    audit: str = field(repr=False)
    approval_artifact_ref: str
    lock_artifact_ref: str
    source_artifact_ref: str
    approved_at: str
    locked_at: str
    canonical_values_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != APPROVED_SEMANTIC_EXECUTION_SCHEMA_VERSION:
            raise ValueError("unsupported approved semantic execution schema version")
        for name in (
            "approval_artifact_ref",
            "lock_artifact_ref",
            "source_artifact_ref",
            "approved_at",
            "locked_at",
        ):
            if not str(getattr(self, name, "")).strip():
                raise ValueError(f"{name} is required")
        canonical = _canonicalize_semantic_values(
            {name: getattr(self, name) for name in APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES}
        )
        for name, value in canonical.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "canonical_values_hash", self._calculate_hash(canonical))

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        approval_artifact_ref: str,
        lock_artifact_ref: str,
        source_artifact_ref: str,
        approved_at: str,
        locked_at: str,
        schema_version: str = APPROVED_SEMANTIC_EXECUTION_SCHEMA_VERSION,
    ) -> "ApprovedSemanticExecutionParameters":
        canonical = _canonicalize_semantic_values(values)
        return cls(
            schema_version=schema_version,
            approval_artifact_ref=approval_artifact_ref,
            lock_artifact_ref=lock_artifact_ref,
            source_artifact_ref=source_artifact_ref,
            approved_at=approved_at,
            locked_at=locked_at,
            **canonical,
        )

    @classmethod
    def from_protected_dict(cls, payload: Mapping[str, Any]) -> "ApprovedSemanticExecutionParameters":
        allowed = set(APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES) | {
            "schema_version",
            "approval_artifact_ref",
            "lock_artifact_ref",
            "source_artifact_ref",
            "approved_at",
            "locked_at",
            "canonical_values_hash",
        }
        if set(payload) != allowed:
            raise ValueError("protected approved semantic payload fields do not match schema")
        instance = cls.from_mapping(
            {name: payload[name] for name in APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES},
            approval_artifact_ref=str(payload["approval_artifact_ref"]),
            lock_artifact_ref=str(payload["lock_artifact_ref"]),
            source_artifact_ref=str(payload["source_artifact_ref"]),
            approved_at=str(payload["approved_at"]),
            locked_at=str(payload["locked_at"]),
            schema_version=str(payload["schema_version"]),
        )
        if instance.canonical_values_hash != str(payload["canonical_values_hash"]):
            raise ValueError("approved semantic values hash mismatch")
        return instance

    def to_protected_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            **self._canonical_values_payload(),
            "approval_artifact_ref": self.approval_artifact_ref,
            "lock_artifact_ref": self.lock_artifact_ref,
            "source_artifact_ref": self.source_artifact_ref,
            "approved_at": self.approved_at,
            "locked_at": self.locked_at,
            "canonical_values_hash": self.canonical_values_hash,
        }

    def as_redacted_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "approved_field_names": list(APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES),
            "approved_fields_count": len(APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES),
            "approval_artifact_ref": self.approval_artifact_ref,
            "lock_artifact_ref": self.lock_artifact_ref,
            "source_artifact_ref": self.source_artifact_ref,
            "approved_at": self.approved_at,
            "locked_at": self.locked_at,
            "canonical_values_hash": self.canonical_values_hash,
            "values_redacted": True,
            "execution_permission_granted": False,
        }

    def integrity_valid(self) -> bool:
        try:
            canonical = _canonicalize_semantic_values(
                {name: getattr(self, name) for name in APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES}
            )
            return self.canonical_values_hash == self._calculate_hash(canonical)
        except (TypeError, ValueError):
            return False

    def _canonical_values_payload(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "symbol": self.symbol,
            "volume": _decimal_text(self.volume),
            "order_type": self.order_type,
            "price": _decimal_text(self.price),
            "stop_loss": _decimal_text(self.stop_loss),
            "take_profit": _decimal_text(self.take_profit),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": self.comment,
            "idempotency": self.idempotency,
            "audit": self.audit,
        }

    def _calculate_hash(self, canonical: Mapping[str, Any]) -> str:
        values = {
            name: _decimal_text(canonical[name]) if isinstance(canonical[name], Decimal) else canonical[name]
            for name in APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES
        }
        payload = {
            "schema_version": self.schema_version,
            "approval_artifact_ref": self.approval_artifact_ref,
            "lock_artifact_ref": self.lock_artifact_ref,
            "source_artifact_ref": self.source_artifact_ref,
            "approved_at": self.approved_at,
            "locked_at": self.locked_at,
            "values": values,
        }
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
    approved_semantic_values_hash: str = ""
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
            "approved_semantic_values_hash": self.approved_semantic_values_hash,
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
    approved_semantic_parameters: ApprovedSemanticExecutionParameters | None = field(default=None, repr=False)
    approved_semantic_values_hash: str = ""
    approval_value_hash: str = ""
    lock_value_hash: str = ""
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
            "approved_semantic_parameters": (
                self.approved_semantic_parameters.as_redacted_dict()
                if self.approved_semantic_parameters is not None
                else None
            ),
            "approved_semantic_values_hash": self.approved_semantic_values_hash,
            "approval_value_hash": self.approval_value_hash,
            "lock_value_hash": self.lock_value_hash,
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

    def as_protected_dict(self) -> Dict[str, Any]:
        """Serialize the lock with its approved values for protected local workflows."""
        if self.approved_semantic_parameters is None:
            raise ValueError("approved semantic parameters are missing")
        payload = self.as_dict()
        payload["approved_semantic_parameters"] = self.approved_semantic_parameters.to_protected_dict()
        return payload


    def approved_semantic_integrity_valid(self) -> bool:
        parameters = self.approved_semantic_parameters
        if parameters is None:
            return False
        value_hash = parameters.canonical_values_hash
        return (
            parameters.integrity_valid()
            and parameters.approval_artifact_ref == self.confirmation_id
            and parameters.lock_artifact_ref == self.approval_lock_id
            and parameters.source_artifact_ref == self.source_value_proposal_id
            and value_hash == self.approved_semantic_values_hash
            and value_hash == self.approval_value_hash
            and value_hash == self.lock_value_hash
        )


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


def _canonicalize_semantic_values(values: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(values, Mapping):
        raise TypeError("approved semantic values must be a mapping")
    expected = set(APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES)
    supplied = set(values)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise ValueError(f"approved semantic fields mismatch: missing={missing}, extra={extra}")

    action = _required_text(values["action"], "action").upper()
    if action != "MARKET":
        raise ValueError("unsupported semantic action")
    order_type = _required_text(values["order_type"], "order_type").upper()
    if order_type not in {"BUY", "SELL"}:
        raise ValueError("unsupported semantic order type")

    return {
        "action": action,
        "symbol": _required_text(values["symbol"], "symbol"),
        "volume": _finite_decimal(values["volume"], "volume", positive=True),
        "order_type": order_type,
        "price": _finite_decimal(values["price"], "price", positive=False),
        "stop_loss": _finite_decimal(values["stop_loss"], "stop_loss", positive=False),
        "take_profit": _finite_decimal(values["take_profit"], "take_profit", positive=False),
        "deviation": _non_negative_integer(values["deviation"], "deviation"),
        "magic": _non_negative_integer(values["magic"], "magic"),
        "comment": _required_text(values["comment"], "comment", maximum=64),
        "idempotency": _required_text(values["idempotency"], "idempotency"),
        "audit": _required_text(values["audit"], "audit"),
    }


def _required_text(value: Any, name: str, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} is invalid")
    forbidden = (
        "ORDER_TYPE_" + "BUY",
        "ORDER_TYPE_" + "SELL",
        "TRADE_ACTION_" + "DEAL",
        "Meta" + "Trader5",
    )
    if any(marker.lower() in normalized.lower() for marker in forbidden):
        raise ValueError(f"{name} contains an MT5-specific marker")
    return normalized


def _finite_decimal(value: Any, name: str, *, positive: bool) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise TypeError(f"{name} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is invalid") from exc
    if not number.is_finite() or (positive and number <= 0) or (not positive and number < 0):
        raise ValueError(f"{name} is outside the supported range")
    return number.normalize() if number else Decimal(0)


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


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
