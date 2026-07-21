from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_ORDER_INTENT_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_CONTRACT_PREPARATION",
    "CREATED_FOR_CONTRACT_WORKFLOW",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_INTENT_SCOPES = {"ORDER_CONTRACT_PREPARATION_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
LIVE_ORDER_INTENT_BLOCK_REASONS = {
    "MISSING_PERMISSION_INTENT",
    "MISSING_PERMISSION_DECISION",
    "PERMISSION_NOT_GRANTED",
    "ORDER_INTENT_WORKFLOW_NOT_ALLOWED",
    "PREFLIGHT_NOT_PASS",
    "MISSING_PROPOSAL_DRAFT",
    "PROPOSAL_DRAFT_NOT_NON_EXECUTABLE",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "EXPIRED_INTENT",
    "DUPLICATE_INTENT",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_INTENT_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_INTENT_CREATED",
    "LIVE_ORDER_INTENT_BLOCKED",
    "LIVE_ORDER_INTENT_DUPLICATE_DETECTED",
    "LIVE_ORDER_INTENT_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class LiveOrderIntent:
    intent_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    order_contract_workflow_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    hard_live_block_required: bool = True
    source_live_permission_intent_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_design_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    source_simulated_receipt_id: str = ""
    artifact_hash: str = ""
    idempotency_key: str = ""
    expires_at: str = ""
    permission_status: str = "UNKNOWN"
    permission_scope: str = "UNKNOWN"
    preflight_status: str = "UNKNOWN"
    proposal_draft_status: str = "UNKNOWN"
    simulated_contract_status: str = "UNKNOWN"
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_INTENT_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_INTENT_SCOPES else "UNKNOWN",
            "order_contract_workflow_allowed": bool(self.order_contract_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "source_live_permission_intent_id": self.source_live_permission_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_design_report_id": self.source_design_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "source_simulated_receipt_id": self.source_simulated_receipt_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "expires_at": self.expires_at,
            "permission_status": self.permission_status,
            "permission_scope": self.permission_scope,
            "preflight_status": self.preflight_status,
            "proposal_draft_status": self.proposal_draft_status,
            "simulated_contract_status": self.simulated_contract_status,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "reasons": _dedupe(self.reasons),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderIntentValidationReport:
    validation_report_id: str
    created_at: str
    source_live_order_intent_id: str
    valid: bool
    order_contract_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "valid": bool(self.valid),
            "order_contract_workflow_allowed": bool(self.order_contract_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderIntentJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    intent_id: str
    validation_report_id: str
    status: str
    scope: str
    order_contract_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    artifact_hash: str
    idempotency_key: str
    source_live_permission_intent_id: str
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
            "event_type": self.event_type if self.event_type in LIVE_ORDER_INTENT_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "intent_id": self.intent_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_INTENT_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_INTENT_SCOPES else "UNKNOWN",
            "order_contract_workflow_allowed": bool(self.order_contract_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_live_permission_intent_id": self.source_live_permission_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveOrderIntentSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_intent_id: str = ""
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
            "latest_intent_id": self.latest_intent_id,
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
