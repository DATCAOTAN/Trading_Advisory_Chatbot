from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


MT5_REQUEST_DRAFT_FINAL_APPROVAL_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_DRY_RUN_REQUEST_DICT_BUILDER",
    "FINAL_APPROVAL_GRANTED_FOR_DRY_RUN_REQUEST_DICT_BUILDER",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "REJECTED",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_SCOPES = {
    "DRY_RUN_REQUEST_DICT_BUILDER_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_ACTIONS = {
    "APPROVE_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY",
    "REJECT",
    "EXPIRE",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_REVIEW_STATES = {
    "NOT_REVIEWED",
    "HUMAN_APPROVED_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_FIELD_STATUSES = {
    "APPROVED_AS_REFERENCE_ONLY",
    "FINAL_BUILDER_VALIDATION_REQUIRED",
    "BLOCKED",
    "INVALID",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_VALUE_STATES = {
    "REFERENCE_ONLY",
    "VALUE_NOT_CREATED",
    "VALUE_REDACTED",
    "MT5_CONSTANT_NOT_USED",
    "PAYLOAD_NOT_CREATED",
    "BROKER_SUBMISSION_NOT_CREATED",
    "BLOCKED",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_BLOCK_REASONS = {
    "MISSING_REQUEST_DRAFT",
    "MISSING_REQUEST_DRAFT_VALIDATION_REPORT",
    "REQUEST_DRAFT_FINAL_APPROVAL_WORKFLOW_NOT_ALLOWED",
    "MISSING_DRY_RUN_PAYLOAD_VALIDATION",
    "MISSING_PRE_MT5_MAPPING",
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
    "MISSING_REQUIRED_APPROVED_FIELDS",
    "WRONG_CONFIRMATION_PHRASE",
    "CONFIRMATION_EXPIRED",
    "FINAL_APPROVAL_REJECTED",
    "RAW_VALUES_NOT_ALLOWED",
    "MT5_PAYLOAD_NOT_ALLOWED",
    "MT5_REQUEST_DICT_NOT_ALLOWED",
    "MT5_CONSTANT_NOT_ALLOWED",
    "BROKER_SUBMISSION_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "ORDER_CONTRACT_READY_NOT_ALLOWED",
    "ORDER_REQUEST_MAPPING_NOT_ALLOWED",
    "BROKER_MAPPING_NOT_ALLOWED",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "EXPIRED_FINAL_APPROVAL",
    "DUPLICATE_FINAL_APPROVAL",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
MT5_REQUEST_DRAFT_FINAL_APPROVAL_JOURNAL_EVENT_TYPES = {
    "MT5_REQUEST_DRAFT_FINAL_APPROVAL_GRANTED",
    "MT5_REQUEST_DRAFT_FINAL_APPROVAL_BLOCKED",
    "MT5_REQUEST_DRAFT_FINAL_APPROVAL_DUPLICATE_DETECTED",
    "MT5_REQUEST_DRAFT_FINAL_APPROVAL_REJECTED",
    "MT5_REQUEST_DRAFT_FINAL_APPROVAL_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}
REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES = [
    "ACTION_DRAFT_FIELD",
    "SYMBOL_DRAFT_FIELD",
    "VOLUME_DRAFT_FIELD",
    "ORDER_TYPE_DRAFT_FIELD",
    "PRICE_DRAFT_FIELD",
    "STOP_LOSS_DRAFT_FIELD",
    "TAKE_PROFIT_DRAFT_FIELD",
    "DEVIATION_DRAFT_FIELD",
    "MAGIC_DRAFT_FIELD",
    "COMMENT_DRAFT_FIELD",
    "IDEMPOTENCY_DRAFT_FIELD",
    "AUDIT_DRAFT_FIELD",
]


@dataclass
class MT5RequestDraftFinalApprovalConfirmation:
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
            "action": self.action if self.action in MT5_REQUEST_DRAFT_FINAL_APPROVAL_ACTIONS else "UNKNOWN",
            "review_state": (
                self.review_state
                if self.review_state in MT5_REQUEST_DRAFT_FINAL_APPROVAL_REVIEW_STATES
                else "UNKNOWN"
            ),
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
        }

    def as_redacted_dict(self) -> Dict[str, Any]:
        payload = self.as_dict()
        payload["phrase"] = ""
        payload["expected_phrase"] = ""
        return payload


@dataclass
class MT5RequestDraftApprovedField:
    approved_field_id: str
    source_draft_field_id: str
    source_field_validation_id: str
    source_mapping_slot_id: str
    source_final_review_slot_validation_id: str
    field_category: str
    status: str
    value_state: str
    approved_as_reference_only: bool = True
    dry_run_request_dict_builder_validation_required: bool = True
    draft_field_present: bool = True
    draft_value_created: bool = False
    draft_value_redacted: bool = True
    raw_value_stored: bool = False
    mt5_payload_value_created: bool = False
    mt5_request_field_value_created: bool = False
    mt5_constant_used: bool = False
    executable_order_value: bool = False
    broker_submission_value: bool = False
    final_human_approval_required: bool = True
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "approved_field_id": self.approved_field_id,
            "source_draft_field_id": self.source_draft_field_id,
            "source_field_validation_id": self.source_field_validation_id,
            "source_mapping_slot_id": self.source_mapping_slot_id,
            "source_final_review_slot_validation_id": self.source_final_review_slot_validation_id,
            "field_category": self.field_category,
            "status": (
                self.status
                if self.status in MT5_REQUEST_DRAFT_FINAL_APPROVAL_FIELD_STATUSES
                else "UNKNOWN"
            ),
            "value_state": (
                self.value_state
                if self.value_state in MT5_REQUEST_DRAFT_FINAL_APPROVAL_VALUE_STATES
                else "UNKNOWN"
            ),
            "approved_as_reference_only": True,
            "dry_run_request_dict_builder_validation_required": True,
            "draft_field_present": True,
            "draft_value_created": False,
            "draft_value_redacted": True,
            "raw_value_stored": False,
            "mt5_payload_value_created": False,
            "mt5_request_field_value_created": False,
            "mt5_constant_used": False,
            "executable_order_value": False,
            "broker_submission_value": False,
            "final_human_approval_required": True,
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class MT5RequestDraftFinalApprovalBoundary:
    final_approval_id: str
    created_at: str
    mode: str = "REQUEST_DRAFT_FINAL_APPROVAL_BOUNDARY_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    mt5_request_dict_dry_run_builder_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    mt5_request_dict_created: bool = False
    mt5_constants_used: bool = False
    broker_submission_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    order_contract_ready: bool = False
    order_request_mapping_allowed: bool = False
    broker_mapping_created: bool = False
    raw_values_stored: bool = False
    executable_order_created: bool = False
    source_request_draft_id: str = ""
    source_request_draft_validation_report_id: str = ""
    source_dry_run_validation_id: str = ""
    source_dry_run_validation_report_id: str = ""
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
    confirmation_id: str = ""
    confirmation_phrase_valid: bool = False
    final_approval_action: str = "UNKNOWN"
    final_approval_review_state: str = "UNKNOWN"
    approved_fields: List[MT5RequestDraftApprovedField] = field(default_factory=list)
    required_approved_field_categories: List[str] = field(default_factory=list)
    approved_field_categories: List[str] = field(default_factory=list)
    missing_approved_field_categories: List[str] = field(default_factory=list)
    invalid_approved_field_categories: List[str] = field(default_factory=list)
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
            "final_approval_id": self.final_approval_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": (
                self.status
                if self.status in MT5_REQUEST_DRAFT_FINAL_APPROVAL_STATUSES
                else "UNKNOWN"
            ),
            "scope": self.scope if self.scope in MT5_REQUEST_DRAFT_FINAL_APPROVAL_SCOPES else "UNKNOWN",
            "mt5_request_dict_dry_run_builder_workflow_allowed": bool(
                self.mt5_request_dict_dry_run_builder_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "source_request_draft_id": self.source_request_draft_id,
            "source_request_draft_validation_report_id": self.source_request_draft_validation_report_id,
            "source_dry_run_validation_id": self.source_dry_run_validation_id,
            "source_dry_run_validation_report_id": self.source_dry_run_validation_report_id,
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
            "confirmation_id": self.confirmation_id,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "final_approval_action": (
                self.final_approval_action
                if self.final_approval_action in MT5_REQUEST_DRAFT_FINAL_APPROVAL_ACTIONS
                else "UNKNOWN"
            ),
            "final_approval_review_state": (
                self.final_approval_review_state
                if self.final_approval_review_state in MT5_REQUEST_DRAFT_FINAL_APPROVAL_REVIEW_STATES
                else "UNKNOWN"
            ),
            "approved_fields": [item.as_dict() for item in self.approved_fields],
            "required_approved_field_categories": _dedupe(self.required_approved_field_categories),
            "approved_field_categories": _dedupe(self.approved_field_categories),
            "missing_approved_field_categories": _dedupe(self.missing_approved_field_categories),
            "invalid_approved_field_categories": _dedupe(self.invalid_approved_field_categories),
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
class MT5RequestDraftFinalApprovalValidationReport:
    validation_report_id: str
    created_at: str
    source_final_approval_id: str
    valid: bool
    mt5_request_dict_dry_run_builder_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    mt5_constants_used: bool
    broker_submission_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    approved_fields_count: int
    approved_fields_valid_count: int
    missing_approved_fields_count: int
    invalid_approved_fields_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_final_approval_id": self.source_final_approval_id,
            "valid": bool(self.valid),
            "mt5_request_dict_dry_run_builder_workflow_allowed": bool(
                self.mt5_request_dict_dry_run_builder_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "approved_fields_count": int(self.approved_fields_count),
            "approved_fields_valid_count": int(self.approved_fields_valid_count),
            "missing_approved_fields_count": int(self.missing_approved_fields_count),
            "invalid_approved_fields_count": int(self.invalid_approved_fields_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class MT5RequestDraftFinalApprovalJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    final_approval_id: str
    validation_report_id: str
    status: str
    scope: str
    mt5_request_dict_dry_run_builder_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    mt5_request_dict_created: bool
    mt5_constants_used: bool
    broker_submission_created: bool
    order_sent: bool
    hard_live_block_required: bool
    order_contract_ready: bool
    order_request_mapping_allowed: bool
    broker_mapping_created: bool
    raw_values_stored: bool
    executable_order_created: bool
    confirmation_phrase_valid: bool
    approved_fields_count: int
    approved_fields_valid_count: int
    missing_approved_fields_count: int
    invalid_approved_fields_count: int
    artifact_hash: str
    idempotency_key: str
    source_request_draft_id: str
    source_request_draft_validation_report_id: str
    source_dry_run_validation_id: str
    source_dry_run_validation_report_id: str
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
            "event_type": (
                self.event_type
                if self.event_type in MT5_REQUEST_DRAFT_FINAL_APPROVAL_JOURNAL_EVENT_TYPES
                else "UNKNOWN"
            ),
            "final_approval_id": self.final_approval_id,
            "validation_report_id": self.validation_report_id,
            "status": (
                self.status
                if self.status in MT5_REQUEST_DRAFT_FINAL_APPROVAL_STATUSES
                else "UNKNOWN"
            ),
            "scope": self.scope if self.scope in MT5_REQUEST_DRAFT_FINAL_APPROVAL_SCOPES else "UNKNOWN",
            "mt5_request_dict_dry_run_builder_workflow_allowed": bool(
                self.mt5_request_dict_dry_run_builder_workflow_allowed
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "mt5_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "raw_values_stored": False,
            "executable_order_created": False,
            "confirmation_phrase_valid": bool(self.confirmation_phrase_valid),
            "approved_fields_count": int(self.approved_fields_count),
            "approved_fields_valid_count": int(self.approved_fields_valid_count),
            "missing_approved_fields_count": int(self.missing_approved_fields_count),
            "invalid_approved_fields_count": int(self.invalid_approved_fields_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_request_draft_id": self.source_request_draft_id,
            "source_request_draft_validation_report_id": self.source_request_draft_validation_report_id,
            "source_dry_run_validation_id": self.source_dry_run_validation_id,
            "source_dry_run_validation_report_id": self.source_dry_run_validation_report_id,
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
class MT5RequestDraftFinalApprovalSummary:
    total_records: int = 0
    total_approved: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    total_rejected: int = 0
    latest_record_at: str = ""
    latest_final_approval_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_approved": int(self.total_approved),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "total_rejected": int(self.total_rejected),
            "latest_record_at": self.latest_record_at,
            "latest_final_approval_id": self.latest_final_approval_id,
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
