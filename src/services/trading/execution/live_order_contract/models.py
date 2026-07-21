from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_ORDER_CONTRACT_SKELETON_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_PARAMETER_VALIDATION",
    "SKELETON_CREATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_SKELETON_SCOPES = {"CONTRACT_PARAMETER_VALIDATION_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
LIVE_ORDER_CONTRACT_PARAMETER_GROUPS = {
    "SIDE_POLICY",
    "PRICE_POLICY",
    "PROTECTION_POLICY",
    "VOLUME_POLICY",
    "RISK_POLICY",
    "BROKER_SYMBOL_POLICY",
    "EXECUTION_TIMING_POLICY",
    "IDEMPOTENCY_POLICY",
    "AUDIT_POLICY",
    "UNKNOWN",
}
REQUIRED_PARAMETER_GROUP_LABELS = [
    "SIDE_POLICY",
    "PRICE_POLICY",
    "PROTECTION_POLICY",
    "VOLUME_POLICY",
    "RISK_POLICY",
    "BROKER_SYMBOL_POLICY",
    "EXECUTION_TIMING_POLICY",
    "IDEMPOTENCY_POLICY",
    "AUDIT_POLICY",
]
LIVE_ORDER_CONTRACT_SKELETON_BLOCK_REASONS = {
    "MISSING_LIVE_ORDER_INTENT",
    "MISSING_LIVE_ORDER_INTENT_VALIDATION",
    "ORDER_CONTRACT_WORKFLOW_NOT_ALLOWED",
    "MISSING_PERMISSION_DECISION",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_PROPOSAL_DRAFT",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "EXPIRED_CONTRACT_SKELETON",
    "DUPLICATE_CONTRACT_SKELETON",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_CONTRACT_SKELETON_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_CONTRACT_SKELETON_CREATED",
    "LIVE_ORDER_CONTRACT_SKELETON_BLOCKED",
    "LIVE_ORDER_CONTRACT_SKELETON_DUPLICATE_DETECTED",
    "LIVE_ORDER_CONTRACT_SKELETON_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class LiveOrderContractSkeleton:
    contract_skeleton_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    contract_parameter_validation_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    hard_live_block_required: bool = True
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    source_live_order_intent_id: str = ""
    source_live_order_intent_validation_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    required_parameter_groups: List[str] = field(default_factory=list)
    missing_parameter_groups: List[str] = field(default_factory=list)
    resolved_parameter_groups: List[str] = field(default_factory=list)
    forbidden_parameter_groups: List[str] = field(default_factory=list)
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
            "contract_skeleton_id": self.contract_skeleton_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_SKELETON_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_SKELETON_SCOPES else "UNKNOWN",
            "contract_parameter_validation_allowed": bool(self.contract_parameter_validation_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_order_intent_validation_id": self.source_live_order_intent_validation_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "required_parameter_groups": _parameter_labels(self.required_parameter_groups),
            "missing_parameter_groups": _parameter_labels(self.missing_parameter_groups),
            "resolved_parameter_groups": [],
            "forbidden_parameter_groups": _parameter_labels(self.forbidden_parameter_groups),
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
class LiveOrderContractSkeletonValidationReport:
    validation_report_id: str
    created_at: str
    source_contract_skeleton_id: str
    valid: bool
    contract_parameter_validation_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "valid": bool(self.valid),
            "contract_parameter_validation_allowed": bool(self.contract_parameter_validation_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderContractSkeletonJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    contract_skeleton_id: str
    validation_report_id: str
    status: str
    scope: str
    contract_parameter_validation_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    artifact_hash: str
    idempotency_key: str
    source_live_order_intent_id: str
    source_live_order_intent_validation_id: str
    source_live_permission_decision_id: str
    source_preflight_report_id: str
    source_proposal_draft_id: str
    source_simulated_contract_id: str
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in LIVE_ORDER_CONTRACT_SKELETON_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "contract_skeleton_id": self.contract_skeleton_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_CONTRACT_SKELETON_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_CONTRACT_SKELETON_SCOPES else "UNKNOWN",
            "contract_parameter_validation_allowed": bool(self.contract_parameter_validation_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_order_intent_validation_id": self.source_live_order_intent_validation_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveOrderContractSkeletonSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_contract_skeleton_id: str = ""
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
            "latest_contract_skeleton_id": self.latest_contract_skeleton_id,
            "latest_validation_report_id": self.latest_validation_report_id,
            "latest_status": self.latest_status,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parameter_labels(items: List[Any] | None) -> List[str]:
    return [str(item) for item in _dedupe(items or [])]


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
