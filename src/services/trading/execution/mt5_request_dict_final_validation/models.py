from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


MT5_REQUEST_DICT_FINAL_VALIDATION_STATUSES = {
    "NOT_REQUESTED",
    "FINAL_VALIDATION_PASSED",
    "READY_FOR_BRIDGE_WRITE_SKELETON_CHECK",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
MT5_REQUEST_DICT_FINAL_VALIDATION_SCOPES = {
    "BRIDGE_WRITE_SKELETON_CHECK_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
MT5_REQUEST_DICT_FINAL_VALIDATION_BLOCK_REASONS = {
    "MISSING_DRY_RUN_BUILDER_BOUNDARY",
    "MISSING_DRY_RUN_BUILDER_VALIDATION_REPORT",
    "REQUEST_DICT_FINAL_VALIDATION_WORKFLOW_NOT_ALLOWED",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "MISSING_REQUIRED_DRY_RUN_FIELDS",
    "APPROVED_SEMANTIC_VALUES_REQUIRED",
    "APPROVED_SEMANTIC_VALUES_INTEGRITY_FAILED",
    "RAW_VALUES_NOT_ALLOWED",
    "REAL_MT5_PAYLOAD_NOT_ALLOWED",
    "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED",
    "MT5_CONSTANT_NOT_ALLOWED",
    "BROKER_SUBMISSION_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "ORDER_SEND_NOT_ALLOWED",
    "LIVE_EXECUTION_STILL_DISABLED",
    "EXPIRED_FINAL_VALIDATION",
    "DUPLICATE_FINAL_VALIDATION",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
MT5_REQUEST_DICT_FINAL_VALIDATION_EVENT_TYPES = {
    "MT5_REQUEST_DICT_FINAL_VALIDATION_PASSED",
    "MT5_REQUEST_DICT_FINAL_VALIDATION_BLOCKED",
    "MT5_REQUEST_DICT_FINAL_VALIDATION_DUPLICATE",
    "UNKNOWN",
}
REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES = [
    "ACTION_KEY",
    "SYMBOL_KEY",
    "VOLUME_KEY",
    "ORDER_TYPE_KEY",
    "PRICE_KEY",
    "STOP_LOSS_KEY",
    "TAKE_PROFIT_KEY",
    "DEVIATION_KEY",
    "MAGIC_KEY",
    "COMMENT_KEY",
    "IDEMPOTENCY_KEY",
    "AUDIT_KEY",
]


@dataclass
class MT5RequestDictFinalValidationField:
    field_id: str
    source_dry_run_field_id: str
    field_category: str
    key_label: str
    validation_passed: bool = True
    schema_only: bool = True
    concrete_value_created: bool = False
    value_redacted: bool = True
    raw_value_stored: bool = False
    real_mt5_payload_value_created: bool = False
    broker_submittable_request_field_created: bool = False
    mt5_constant_used: bool = False
    executable_order_value: bool = False
    broker_submission_value: bool = False
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "source_dry_run_field_id": self.source_dry_run_field_id,
            "field_category": self.field_category,
            "key_label": self.key_label,
            "validation_passed": bool(self.validation_passed),
            "schema_only": True,
            "concrete_value_created": False,
            "value_redacted": True,
            "raw_value_stored": False,
            "real_mt5_payload_value_created": False,
            "broker_submittable_request_field_created": False,
            "mt5_constant_used": False,
            "executable_order_value": False,
            "broker_submission_value": False,
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class MT5RequestDictFinalValidationBoundary:
    final_validation_id: str
    created_at: str
    mode: str = "REQUEST_DICT_FINAL_VALIDATION_BOUNDARY_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    bridge_write_skeleton_check_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    real_mt5_payload_created: bool = False
    broker_submittable_request_dict_created: bool = False
    mt5_constants_used: bool = False
    broker_submission_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    approved_semantic_values_required: bool = False
    approved_semantic_values_present: bool = False
    approved_semantic_values_verified: bool = False
    approved_semantic_values_hash: str = ""
    source_dry_run_request_dict_id: str = ""
    source_dry_run_request_dict_validation_report_id: str = ""
    validated_fields: List[MT5RequestDictFinalValidationField] = field(default_factory=list)
    required_field_categories: List[str] = field(default_factory=list)
    validated_field_categories: List[str] = field(default_factory=list)
    missing_field_categories: List[str] = field(default_factory=list)
    invalid_field_categories: List[str] = field(default_factory=list)
    artifact_hash: str = ""
    idempotency_key: str = ""
    expires_at: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "final_validation_id": self.final_validation_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in MT5_REQUEST_DICT_FINAL_VALIDATION_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in MT5_REQUEST_DICT_FINAL_VALIDATION_SCOPES else "UNKNOWN",
            "bridge_write_skeleton_check_allowed": bool(self.bridge_write_skeleton_check_allowed),

            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "real_mt5_payload_created": False,
            "broker_submittable_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "approved_semantic_values_required": bool(self.approved_semantic_values_required),
            "approved_semantic_values_present": bool(self.approved_semantic_values_present),
            "approved_semantic_values_verified": bool(self.approved_semantic_values_verified),
            "approved_semantic_values_hash": self.approved_semantic_values_hash,
            "source_dry_run_request_dict_id": self.source_dry_run_request_dict_id,
            "source_dry_run_request_dict_validation_report_id": self.source_dry_run_request_dict_validation_report_id,
            "validated_fields": [item.as_dict() for item in self.validated_fields],
            "required_field_categories": list(self.required_field_categories),
            "validated_field_categories": list(self.validated_field_categories),
            "missing_field_categories": list(self.missing_field_categories),
            "invalid_field_categories": list(self.invalid_field_categories),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars or 0),
        }


@dataclass
class MT5RequestDictFinalValidationReport:
    validation_report_id: str
    created_at: str
    source_final_validation_id: str
    valid: bool
    bridge_write_skeleton_check_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    real_mt5_payload_created: bool = False
    broker_submittable_request_dict_created: bool = False
    mt5_constants_used: bool = False
    broker_submission_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    validated_fields_count: int = 0
    missing_fields_count: int = 0
    invalid_fields_count: int = 0
    validation_checks: Dict[str, bool] = field(default_factory=dict)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_final_validation_id": self.source_final_validation_id,
            "valid": bool(self.valid),
            "bridge_write_skeleton_check_allowed": bool(self.bridge_write_skeleton_check_allowed),
            "concrete_value_created": bool(
                self.valid
                and self.validation_checks.get("approved_semantic_values_present", False)
                and self.validation_checks.get("approved_semantic_values_integrity", False)
            ),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "real_mt5_payload_created": False,
            "broker_submittable_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "validated_fields_count": int(self.validated_fields_count),
            "missing_fields_count": int(self.missing_fields_count),
            "invalid_fields_count": int(self.invalid_fields_count),
            "validation_checks": dict(self.validation_checks),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars or 0),
        }


@dataclass
class MT5RequestDictFinalValidationJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    final_validation_id: str
    validation_report_id: str
    status: str
    scope: str
    bridge_write_skeleton_check_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    real_mt5_payload_created: bool
    broker_submittable_request_dict_created: bool
    mt5_constants_used: bool
    broker_submission_created: bool
    order_sent: bool
    hard_live_block_required: bool
    validated_fields_count: int
    missing_fields_count: int
    invalid_fields_count: int
    artifact_hash: str
    idempotency_key: str
    source_dry_run_request_dict_id: str
    source_refs: List[str]
    payload_size_chars: int
    metadata_redacted: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in MT5_REQUEST_DICT_FINAL_VALIDATION_EVENT_TYPES else "UNKNOWN",
            "final_validation_id": self.final_validation_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status,
            "scope": self.scope,
            "bridge_write_skeleton_check_allowed": bool(self.bridge_write_skeleton_check_allowed),

            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "real_mt5_payload_created": False,
            "broker_submittable_request_dict_created": False,
            "mt5_constants_used": False,
            "broker_submission_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "validated_fields_count": int(self.validated_fields_count),
            "missing_fields_count": int(self.missing_fields_count),
            "invalid_fields_count": int(self.invalid_fields_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_dry_run_request_dict_id": self.source_dry_run_request_dict_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars or 0),
            "metadata_redacted": True,
        }


@dataclass
class MT5RequestDictFinalValidationSummary:
    total_records: int
    total_passed: int
    total_blocked: int
    latest_final_validation_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None and str(value) != ""))
