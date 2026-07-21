from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


MT5_DRY_RUN_PAYLOAD_VALIDATION_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_MT5_REQUEST_DRAFT_BOUNDARY",
    "DRY_RUN_PAYLOAD_VALIDATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_VALIDATION_SCOPES = {
    "MT5_REQUEST_DRAFT_BOUNDARY_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES = {
    "ACTION_FIELD",
    "SYMBOL_FIELD",
    "VOLUME_FIELD",
    "ORDER_TYPE_FIELD",
    "PRICE_FIELD",
    "STOP_LOSS_FIELD",
    "TAKE_PROFIT_FIELD",
    "DEVIATION_FIELD",
    "MAGIC_FIELD",
    "COMMENT_FIELD",
    "IDEMPOTENCY_FIELD",
    "AUDIT_FIELD",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_FIELD_STATUSES = {
    "SCHEMA_VALIDATED",
    "VALIDATION_REQUIRED",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_VALUE_STATES = {
    "SCHEMA_ONLY",
    "VALUE_NOT_CREATED",
    "VALUE_REDACTED",
    "MT5_CONSTANT_NOT_USED",
    "BLOCKED",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_VALIDATION_BLOCK_REASONS = {
    "MISSING_PRE_MT5_MAPPING",
    "MISSING_PRE_MT5_MAPPING_VALIDATION",
    "DRY_RUN_PAYLOAD_VALIDATION_WORKFLOW_NOT_ALLOWED",
    "MISSING_FINAL_REVIEW",
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
    "MISSING_REQUIRED_PAYLOAD_FIELDS",
    "RAW_VALUES_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "MT5_REQUEST_DICT_NOT_ALLOWED",
    "MT5_CONSTANT_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "ORDER_REQUEST_MAPPING_NOT_ALLOWED",
    "BROKER_MAPPING_NOT_ALLOWED",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "EXPIRED_DRY_RUN_VALIDATION",
    "DUPLICATE_DRY_RUN_VALIDATION",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
MT5_DRY_RUN_PAYLOAD_VALIDATION_JOURNAL_EVENT_TYPES = {
    "MT5_DRY_RUN_PAYLOAD_VALIDATED",
    "MT5_DRY_RUN_PAYLOAD_VALIDATION_BLOCKED",
    "MT5_DRY_RUN_PAYLOAD_VALIDATION_DUPLICATE_DETECTED",
    "MT5_DRY_RUN_PAYLOAD_VALIDATION_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}
REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES = [
    "ACTION_FIELD",
    "SYMBOL_FIELD",
    "VOLUME_FIELD",
    "ORDER_TYPE_FIELD",
    "PRICE_FIELD",
    "STOP_LOSS_FIELD",
    "TAKE_PROFIT_FIELD",
    "DEVIATION_FIELD",
    "MAGIC_FIELD",
    "COMMENT_FIELD",
    "IDEMPOTENCY_FIELD",
    "AUDIT_FIELD",
]


@dataclass
class MT5DryRunPayloadFieldValidation:
    field_validation_id: str
    source_mapping_slot_id: str
    source_final_review_slot_validation_id: str
    field_category: str
    status: str
    value_state: str
    schema_present: bool = True
    value_created: bool = False
    value_redacted: bool = True
    raw_value_stored: bool = False
    mt5_payload_value_created: bool = False
    mt5_request_field_value_created: bool = False
    mt5_constant_used: bool = False
    executable_order_value: bool = False
    broker_submission_value: bool = False
    future_mt5_field_label: str = ""
    validation_requirements: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "field_validation_id": self.field_validation_id,
            "source_mapping_slot_id": self.source_mapping_slot_id,
            "source_final_review_slot_validation_id": self.source_final_review_slot_validation_id,
            "field_category": self.field_category
            if self.field_category in MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES
            else "UNKNOWN",
            "status": self.status if self.status in MT5_DRY_RUN_PAYLOAD_FIELD_STATUSES else "UNKNOWN",
            "value_state": self.value_state if self.value_state in MT5_DRY_RUN_PAYLOAD_VALUE_STATES else "UNKNOWN",
            "schema_present": True,
            "value_created": False,
            "value_redacted": True,
            "raw_value_stored": False,
            "mt5_payload_value_created": False,
            "mt5_request_field_value_created": False,
            "mt5_constant_used": False,
            "executable_order_value": False,
            "broker_submission_value": False,
            "future_mt5_field_label": self.future_mt5_field_label,
            "validation_requirements": _dedupe(self.validation_requirements),
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class MT5OrderRequestDryRunPayloadValidation:
    dry_run_validation_id: str
    created_at: str
    mode: str = "DRY_RUN_PAYLOAD_VALIDATION_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    mt5_request_draft_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    mt5_request_dict_created: bool = False
    mt5_constants_used: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    order_request_mapping_allowed: bool = False
    broker_mapping_created: bool = False
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_pre_mt5_mapping_id: str = ""
    source_pre_mt5_mapping_validation_id: str = ""
    source_final_review_id: str = ""
    source_parameterization_id: str = ""
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
    field_validations: List[MT5DryRunPayloadFieldValidation] = field(default_factory=list)
    required_field_categories: List[str] = field(default_factory=list)
    validated_field_categories: List[str] = field(default_factory=list)
    missing_field_categories: List[str] = field(default_factory=list)
    invalid_field_categories: List[str] = field(default_factory=list)
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
            "dry_run_validation_id": self.dry_run_validation_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in MT5_DRY_RUN_PAYLOAD_VALIDATION_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in MT5_DRY_RUN_PAYLOAD_VALIDATION_SCOPES else "UNKNOWN",
            "mt5_request_draft_workflow_allowed": bool(self.mt5_request_draft_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_pre_mt5_mapping_id": self.source_pre_mt5_mapping_id,
            "source_pre_mt5_mapping_validation_id": self.source_pre_mt5_mapping_validation_id,
            "source_final_review_id": self.source_final_review_id,
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
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "field_validations": [field_validation.as_dict() for field_validation in self.field_validations],
            "required_field_categories": _dedupe(self.required_field_categories),
            "validated_field_categories": _dedupe(self.validated_field_categories),
            "missing_field_categories": _dedupe(self.missing_field_categories),
            "invalid_field_categories": _dedupe(self.invalid_field_categories),
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
class MT5OrderRequestDryRunPayloadValidationReport:
    validation_report_id: str
    created_at: str
    source_dry_run_validation_id: str
    valid: bool
    mt5_request_draft_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    mt5_constants_used: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    field_validations_count: int
    validated_fields_count: int
    missing_fields_count: int
    invalid_fields_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_dry_run_validation_id": self.source_dry_run_validation_id,
            "valid": bool(self.valid),
            "mt5_request_draft_workflow_allowed": bool(self.mt5_request_draft_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "field_validations_count": int(self.field_validations_count),
            "validated_fields_count": int(self.validated_fields_count),
            "missing_fields_count": int(self.missing_fields_count),
            "invalid_fields_count": int(self.invalid_fields_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class MT5OrderRequestDryRunPayloadValidationJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    dry_run_validation_id: str
    validation_report_id: str
    status: str
    scope: str
    mt5_request_draft_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    mt5_constants_used: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    field_validations_count: int
    validated_fields_count: int
    missing_fields_count: int
    invalid_fields_count: int
    artifact_hash: str
    idempotency_key: str
    source_pre_mt5_mapping_id: str
    source_pre_mt5_mapping_validation_id: str
    source_final_review_id: str
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
            "event_type": self.event_type
            if self.event_type in MT5_DRY_RUN_PAYLOAD_VALIDATION_JOURNAL_EVENT_TYPES
            else "UNKNOWN",
            "dry_run_validation_id": self.dry_run_validation_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in MT5_DRY_RUN_PAYLOAD_VALIDATION_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in MT5_DRY_RUN_PAYLOAD_VALIDATION_SCOPES else "UNKNOWN",
            "mt5_request_draft_workflow_allowed": bool(self.mt5_request_draft_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "field_validations_count": int(self.field_validations_count),
            "validated_fields_count": int(self.validated_fields_count),
            "missing_fields_count": int(self.missing_fields_count),
            "invalid_fields_count": int(self.invalid_fields_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_pre_mt5_mapping_id": self.source_pre_mt5_mapping_id,
            "source_pre_mt5_mapping_validation_id": self.source_pre_mt5_mapping_validation_id,
            "source_final_review_id": self.source_final_review_id,
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
class MT5DryRunPayloadValidationSummary:
    total_records: int = 0
    total_validated: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_dry_run_validation_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_validated": int(self.total_validated),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_dry_run_validation_id": self.latest_dry_run_validation_id,
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
