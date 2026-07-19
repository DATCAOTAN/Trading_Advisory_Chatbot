from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


PRE_MT5_ORDER_REQUEST_MAPPING_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_DRY_RUN_PAYLOAD_VALIDATION",
    "MAPPING_BOUNDARY_CREATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
PRE_MT5_ORDER_REQUEST_MAPPING_SCOPES = {
    "MT5_DRY_RUN_PAYLOAD_VALIDATION_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
PRE_MT5_MAPPING_SLOT_TYPES = {
    "ACTION_MAPPING_SLOT",
    "SYMBOL_MAPPING_SLOT",
    "VOLUME_MAPPING_SLOT",
    "ORDER_TYPE_MAPPING_SLOT",
    "PRICE_MAPPING_SLOT",
    "PROTECTION_MAPPING_SLOT",
    "DEVIATION_MAPPING_SLOT",
    "MAGIC_MAPPING_SLOT",
    "COMMENT_MAPPING_SLOT",
    "IDEMPOTENCY_MAPPING_SLOT",
    "AUDIT_MAPPING_SLOT",
    "UNKNOWN",
}
PRE_MT5_MAPPING_SLOT_STATUSES = {
    "MAPPED_AS_SCHEMA_ONLY",
    "DRY_RUN_PAYLOAD_VALIDATION_REQUIRED",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
PRE_MT5_MAPPING_VALUE_STATES = {
    "SCHEMA_ONLY",
    "RAW_VALUE_NOT_STORED",
    "PAYLOAD_VALUE_NOT_CREATED",
    "VALIDATION_REQUIRED",
    "BLOCKED",
    "UNKNOWN",
}
PRE_MT5_ORDER_REQUEST_MAPPING_BLOCK_REASONS = {
    "MISSING_FINAL_REVIEW",
    "MISSING_FINAL_REVIEW_VALIDATION",
    "PRE_MT5_MAPPING_WORKFLOW_NOT_ALLOWED",
    "MISSING_PARAMETERIZATION",
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
    "MISSING_REQUIRED_MAPPING_SLOTS",
    "RAW_VALUES_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "MT5_REQUEST_DICT_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "ORDER_REQUEST_MAPPING_NOT_ALLOWED",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "EXPIRED_MAPPING_BOUNDARY",
    "DUPLICATE_MAPPING_BOUNDARY",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
PRE_MT5_ORDER_REQUEST_MAPPING_JOURNAL_EVENT_TYPES = {
    "PRE_MT5_MAPPING_BOUNDARY_CREATED",
    "PRE_MT5_MAPPING_BLOCKED",
    "PRE_MT5_MAPPING_DUPLICATE_DETECTED",
    "PRE_MT5_MAPPING_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}
REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES = [
    "ACTION_MAPPING_SLOT",
    "SYMBOL_MAPPING_SLOT",
    "VOLUME_MAPPING_SLOT",
    "ORDER_TYPE_MAPPING_SLOT",
    "PRICE_MAPPING_SLOT",
    "PROTECTION_MAPPING_SLOT",
    "DEVIATION_MAPPING_SLOT",
    "MAGIC_MAPPING_SLOT",
    "COMMENT_MAPPING_SLOT",
    "IDEMPOTENCY_MAPPING_SLOT",
    "AUDIT_MAPPING_SLOT",
]


@dataclass
class PreMT5MappingSlot:
    mapping_slot_id: str
    source_final_review_slot_validation_id: str
    source_contract_slot_id: str
    source_slot_lock_id: str
    source_value_slot_id: str
    slot_type: str
    status: str
    value_state: str
    mapped_as_schema_only: bool = True
    dry_run_payload_validation_required: bool = True
    raw_value_stored: bool = False
    mt5_payload_value_created: bool = False
    mt5_request_field_value_created: bool = False
    executable_order_value: bool = False
    broker_submission_value: bool = False
    source_refs: List[str] = field(default_factory=list)
    source_candidate_ids: List[str] = field(default_factory=list)
    future_mt5_field_label: str = ""
    future_validation_requirements: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mapping_slot_id": self.mapping_slot_id,
            "source_final_review_slot_validation_id": self.source_final_review_slot_validation_id,
            "source_contract_slot_id": self.source_contract_slot_id,
            "source_slot_lock_id": self.source_slot_lock_id,
            "source_value_slot_id": self.source_value_slot_id,
            "slot_type": self.slot_type if self.slot_type in PRE_MT5_MAPPING_SLOT_TYPES else "UNKNOWN",
            "status": self.status if self.status in PRE_MT5_MAPPING_SLOT_STATUSES else "UNKNOWN",
            "value_state": self.value_state if self.value_state in PRE_MT5_MAPPING_VALUE_STATES else "UNKNOWN",
            "mapped_as_schema_only": True,
            "dry_run_payload_validation_required": True,
            "raw_value_stored": False,
            "mt5_payload_value_created": False,
            "mt5_request_field_value_created": False,
            "executable_order_value": False,
            "broker_submission_value": False,
            "source_refs": _dedupe(self.source_refs),
            "source_candidate_ids": _dedupe(self.source_candidate_ids),
            "future_mt5_field_label": self.future_mt5_field_label,
            "future_validation_requirements": _dedupe(self.future_validation_requirements),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class PreMT5OrderRequestMappingBoundary:
    mapping_boundary_id: str
    created_at: str
    mode: str = "MAPPING_BOUNDARY_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    mt5_dry_run_payload_validation_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    mt5_request_dict_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    order_request_mapping_allowed: bool = False
    broker_mapping_created: bool = False
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_final_review_id: str = ""
    source_final_review_validation_id: str = ""
    source_parameterization_id: str = ""
    source_parameterization_validation_id: str = ""
    source_approval_lock_id: str = ""
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
    mapping_slots: List[PreMT5MappingSlot] = field(default_factory=list)
    required_mapping_slot_types: List[str] = field(default_factory=list)
    mapped_slot_types: List[str] = field(default_factory=list)
    missing_mapping_slot_types: List[str] = field(default_factory=list)
    invalid_mapping_slot_types: List[str] = field(default_factory=list)
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
            "mapping_boundary_id": self.mapping_boundary_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in PRE_MT5_ORDER_REQUEST_MAPPING_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in PRE_MT5_ORDER_REQUEST_MAPPING_SCOPES else "UNKNOWN",
            "mt5_dry_run_payload_validation_workflow_allowed": bool(
                self.mt5_dry_run_payload_validation_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_final_review_id": self.source_final_review_id,
            "source_final_review_validation_id": self.source_final_review_validation_id,
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
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "mapping_slots": [slot.as_dict() for slot in self.mapping_slots],
            "required_mapping_slot_types": _dedupe(self.required_mapping_slot_types),
            "mapped_slot_types": _dedupe(self.mapped_slot_types),
            "missing_mapping_slot_types": _dedupe(self.missing_mapping_slot_types),
            "invalid_mapping_slot_types": _dedupe(self.invalid_mapping_slot_types),
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
class PreMT5OrderRequestMappingValidationReport:
    validation_report_id: str
    created_at: str
    source_mapping_boundary_id: str
    valid: bool
    mt5_dry_run_payload_validation_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    mapping_slots_count: int
    mapped_slots_count: int
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
            "source_mapping_boundary_id": self.source_mapping_boundary_id,
            "valid": bool(self.valid),
            "mt5_dry_run_payload_validation_workflow_allowed": bool(
                self.mt5_dry_run_payload_validation_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "mapping_slots_count": int(self.mapping_slots_count),
            "mapped_slots_count": int(self.mapped_slots_count),
            "missing_slots_count": int(self.missing_slots_count),
            "invalid_slots_count": int(self.invalid_slots_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class PreMT5OrderRequestMappingJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    mapping_boundary_id: str
    validation_report_id: str
    status: str
    scope: str
    mt5_dry_run_payload_validation_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    mapping_slots_count: int
    mapped_slots_count: int
    missing_slots_count: int
    invalid_slots_count: int
    artifact_hash: str
    idempotency_key: str
    source_final_review_id: str
    source_final_review_validation_id: str
    source_parameterization_id: str
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
            "event_type": self.event_type if self.event_type in PRE_MT5_ORDER_REQUEST_MAPPING_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "mapping_boundary_id": self.mapping_boundary_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in PRE_MT5_ORDER_REQUEST_MAPPING_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in PRE_MT5_ORDER_REQUEST_MAPPING_SCOPES else "UNKNOWN",
            "mt5_dry_run_payload_validation_workflow_allowed": bool(
                self.mt5_dry_run_payload_validation_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "mapping_slots_count": int(self.mapping_slots_count),
            "mapped_slots_count": int(self.mapped_slots_count),
            "missing_slots_count": int(self.missing_slots_count),
            "invalid_slots_count": int(self.invalid_slots_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_final_review_id": self.source_final_review_id,
            "source_final_review_validation_id": self.source_final_review_validation_id,
            "source_parameterization_id": self.source_parameterization_id,
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
class PreMT5OrderRequestMappingSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_mapping_boundary_id: str = ""
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
            "latest_mapping_boundary_id": self.latest_mapping_boundary_id,
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
