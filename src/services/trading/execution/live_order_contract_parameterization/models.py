from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_ORDER_CONTRACT_PARAMETERIZATION_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_CONTRACT_VALIDATION",
    "PARAMETERIZATION_BOUNDARY_CREATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_PARAMETERIZATION_SCOPES = {"CONTRACT_VALIDATION_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
LIVE_ORDER_CONTRACT_PARAMETER_SLOT_TYPES = {
    "SIDE_CONTRACT_SLOT",
    "PRICE_CONTRACT_SLOT",
    "PROTECTION_CONTRACT_SLOT",
    "VOLUME_CONTRACT_SLOT",
    "RISK_CONTRACT_SLOT",
    "BROKER_SYMBOL_CONTRACT_SLOT",
    "EXECUTION_TIMING_CONTRACT_SLOT",
    "IDEMPOTENCY_CONTRACT_SLOT",
    "AUDIT_CONTRACT_SLOT",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_PARAMETER_SLOT_STATUSES = {
    "PARAMETERIZED_FOR_VALIDATION_ONLY",
    "VALIDATION_REQUIRED",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_PARAMETER_VALUE_STATES = {
    "REDACTED_REFERENCE_ONLY",
    "RAW_VALUE_NOT_STORED",
    "VALIDATION_REQUIRED",
    "BLOCKED",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_PARAMETERIZATION_BLOCK_REASONS = {
    "MISSING_APPROVAL_LOCK",
    "MISSING_APPROVAL_LOCK_VALIDATION",
    "CONTRACT_PARAMETERIZATION_NOT_ALLOWED",
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
    "MISSING_REQUIRED_CONTRACT_SLOTS",
    "RAW_VALUES_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "ORDER_REQUEST_MAPPING_NOT_ALLOWED",
    "EXPIRED_PARAMETERIZATION",
    "DUPLICATE_PARAMETERIZATION",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_PARAMETERIZATION_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_CONTRACT_PARAMETERIZATION_CREATED",
    "LIVE_ORDER_CONTRACT_PARAMETERIZATION_BLOCKED",
    "LIVE_ORDER_CONTRACT_PARAMETERIZATION_DUPLICATE_DETECTED",
    "LIVE_ORDER_CONTRACT_PARAMETERIZATION_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}

REQUIRED_CONTRACT_PARAMETER_SLOT_MAP = {
    "SIDE_CONTRACT_SLOT": "SIDE_VALUE_PROPOSAL_SLOT",
    "PRICE_CONTRACT_SLOT": "PRICE_VALUE_PROPOSAL_SLOT",
    "PROTECTION_CONTRACT_SLOT": "PROTECTION_VALUE_PROPOSAL_SLOT",
    "VOLUME_CONTRACT_SLOT": "VOLUME_VALUE_PROPOSAL_SLOT",
    "RISK_CONTRACT_SLOT": "RISK_VALUE_PROPOSAL_SLOT",
    "BROKER_SYMBOL_CONTRACT_SLOT": "BROKER_SYMBOL_VALUE_PROPOSAL_SLOT",
    "EXECUTION_TIMING_CONTRACT_SLOT": "EXECUTION_TIMING_VALUE_PROPOSAL_SLOT",
    "IDEMPOTENCY_CONTRACT_SLOT": "IDEMPOTENCY_VALUE_PROPOSAL_SLOT",
    "AUDIT_CONTRACT_SLOT": "AUDIT_VALUE_PROPOSAL_SLOT",
}
REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES = list(REQUIRED_CONTRACT_PARAMETER_SLOT_MAP.keys())


@dataclass
class LiveOrderContractParameterSlot:
    contract_slot_id: str
    source_slot_lock_id: str
    source_value_slot_id: str
    source_draft_slot_id: str
    slot_type: str
    parameter_group: str
    status: str
    value_state: str
    parameterized_for_validation_only: bool = True
    raw_value_stored: bool = False
    redacted_value_reference_present: bool = True
    executable_value: bool = False
    mt5_payload_value: bool = False
    order_request_value: bool = False
    broker_mapping_required: bool = False
    contract_validation_required: bool = True
    final_human_review_required: bool = True
    source_candidate_ids: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "contract_slot_id": self.contract_slot_id,
            "source_slot_lock_id": self.source_slot_lock_id,
            "source_value_slot_id": self.source_value_slot_id,
            "source_draft_slot_id": self.source_draft_slot_id,
            "slot_type": self.slot_type if self.slot_type in LIVE_ORDER_CONTRACT_PARAMETER_SLOT_TYPES else "UNKNOWN",
            "parameter_group": self.parameter_group,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_PARAMETER_SLOT_STATUSES else "UNKNOWN",
            "value_state": self.value_state if self.value_state in LIVE_ORDER_CONTRACT_PARAMETER_VALUE_STATES else "UNKNOWN",
            "parameterized_for_validation_only": True,
            "raw_value_stored": False,
            "redacted_value_reference_present": True,
            "executable_value": False,
            "mt5_payload_value": False,
            "order_request_value": False,
            "broker_mapping_required": bool(self.broker_mapping_required),
            "contract_validation_required": True,
            "final_human_review_required": True,
            "source_candidate_ids": _dedupe(self.source_candidate_ids),
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class LiveOrderContractParameterizationBoundary:
    parameterization_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    contract_validation_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    order_request_mapping_allowed: bool = False
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_approval_lock_id: str = ""
    source_approval_lock_validation_id: str = ""
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
    contract_slots: List[LiveOrderContractParameterSlot] = field(default_factory=list)
    required_contract_slot_types: List[str] = field(default_factory=list)
    parameterized_slot_types: List[str] = field(default_factory=list)
    missing_contract_slot_types: List[str] = field(default_factory=list)
    invalid_contract_slot_types: List[str] = field(default_factory=list)
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
            "parameterization_id": self.parameterization_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_PARAMETERIZATION_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_PARAMETERIZATION_SCOPES else "UNKNOWN",
            "contract_validation_workflow_allowed": bool(self.contract_validation_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_approval_lock_id": self.source_approval_lock_id,
            "source_approval_lock_validation_id": self.source_approval_lock_validation_id,
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
            "contract_slots": [slot.as_dict() for slot in self.contract_slots],
            "required_contract_slot_types": _dedupe(self.required_contract_slot_types),
            "parameterized_slot_types": _dedupe(self.parameterized_slot_types),
            "missing_contract_slot_types": _dedupe(self.missing_contract_slot_types),
            "invalid_contract_slot_types": _dedupe(self.invalid_contract_slot_types),
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
class LiveOrderContractParameterizationValidationReport:
    validation_report_id: str
    created_at: str
    source_parameterization_id: str
    valid: bool
    contract_validation_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    raw_values_stored: bool
    executable_order_created: bool
    contract_slots_count: int
    parameterized_slots_count: int
    missing_slots_count: int
    invalid_slots_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_parameterization_id": self.source_parameterization_id,
            "valid": bool(self.valid),
            "contract_validation_workflow_allowed": bool(self.contract_validation_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "contract_slots_count": int(self.contract_slots_count),
            "parameterized_slots_count": int(self.parameterized_slots_count),
            "missing_slots_count": int(self.missing_slots_count),
            "invalid_slots_count": int(self.invalid_slots_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderContractParameterizationJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    parameterization_id: str
    validation_report_id: str
    status: str
    scope: str
    contract_validation_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    raw_values_stored: bool
    executable_order_created: bool
    contract_slots_count: int
    parameterized_slots_count: int
    missing_slots_count: int
    invalid_slots_count: int
    artifact_hash: str
    idempotency_key: str
    source_approval_lock_id: str
    source_approval_lock_validation_id: str
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
            "event_type": self.event_type if self.event_type in LIVE_ORDER_CONTRACT_PARAMETERIZATION_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "parameterization_id": self.parameterization_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_PARAMETERIZATION_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_PARAMETERIZATION_SCOPES else "UNKNOWN",
            "contract_validation_workflow_allowed": bool(self.contract_validation_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "contract_slots_count": int(self.contract_slots_count),
            "parameterized_slots_count": int(self.parameterized_slots_count),
            "missing_slots_count": int(self.missing_slots_count),
            "invalid_slots_count": int(self.invalid_slots_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
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
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveOrderContractParameterizationSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_parameterization_id: str = ""
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
            "latest_parameterization_id": self.latest_parameterization_id,
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
