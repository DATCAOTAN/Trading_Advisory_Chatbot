from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_PERMISSION_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_PERMISSION",
    "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_PERMISSION_SCOPES = {"ORDER_INTENT_WORKFLOW_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
LIVE_PERMISSION_CONFIRMATION_STATES = {
    "NOT_CONFIRMED",
    "CONFIRMED_PERMISSION_GATE_ONLY",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
}
LIVE_PERMISSION_BLOCK_REASONS = {
    "PREFLIGHT_NOT_PASS",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_DESIGN_REPORT",
    "MISSING_HARD_BLOCK_RECEIPT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "MISSING_CONFIRMATION_PHRASE",
    "WRONG_CONFIRMATION_PHRASE",
    "EXPIRED_PERMISSION_REQUEST",
    "DUPLICATE_PERMISSION_REQUEST",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_PERMISSION_JOURNAL_EVENT_TYPES = {
    "LIVE_PERMISSION_INTENT_CREATED",
    "LIVE_PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
    "LIVE_PERMISSION_BLOCKED",
    "LIVE_PERMISSION_DUPLICATE_DETECTED",
    "LIVE_PERMISSION_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class LivePermissionIntent:
    intent_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    permission_status: str = "UNKNOWN"
    permission_scope: str = "EXECUTION_NOT_ALLOWED"
    confirmation_state: str = "NOT_CONFIRMED"
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    order_intent_workflow_allowed: bool = False
    hard_live_block_required: bool = True
    user_acknowledgement_text: str = ""
    confirmation_phrase_required: str = ""
    confirmation_phrase_received: str = ""
    source_preflight_report_id: str = ""
    source_design_report_id: str = ""
    source_capability_report_id: str = ""
    source_blocked_receipt_id: str = ""
    source_simulated_contract_id: str = ""
    source_proposal_draft_id: str = ""
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
            "intent_id": self.intent_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "permission_status": self.permission_status
            if self.permission_status in LIVE_PERMISSION_STATUSES
            else "UNKNOWN",
            "permission_scope": self.permission_scope if self.permission_scope in LIVE_PERMISSION_SCOPES else "UNKNOWN",
            "confirmation_state": self.confirmation_state
            if self.confirmation_state in LIVE_PERMISSION_CONFIRMATION_STATES
            else "UNKNOWN",
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "order_intent_workflow_allowed": bool(self.order_intent_workflow_allowed),
            "hard_live_block_required": True,
            "user_acknowledgement_text": self.user_acknowledgement_text,
            "confirmation_phrase_required": self.confirmation_phrase_required,
            "confirmation_phrase_received": self.confirmation_phrase_received,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_design_report_id": self.source_design_report_id,
            "source_capability_report_id": self.source_capability_report_id,
            "source_blocked_receipt_id": self.source_blocked_receipt_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
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
class LivePermissionGateDecision:
    decision_id: str
    created_at: str
    intent_id: str
    permission_status: str
    permission_scope: str
    gate_allowed: bool
    order_intent_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    block_reasons: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_preflight_report_id: str = ""
    source_design_report_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "intent_id": self.intent_id,
            "permission_status": self.permission_status
            if self.permission_status in LIVE_PERMISSION_STATUSES
            else "UNKNOWN",
            "permission_scope": self.permission_scope if self.permission_scope in LIVE_PERMISSION_SCOPES else "UNKNOWN",
            "gate_allowed": bool(self.gate_allowed),
            "order_intent_workflow_allowed": bool(self.order_intent_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "block_reasons": _dedupe(self.block_reasons),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_design_report_id": self.source_design_report_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LivePermissionJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    intent_id: str
    decision_id: str
    permission_status: str
    permission_scope: str
    confirmation_state: str
    order_intent_workflow_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    hard_live_block_required: bool
    artifact_hash: str
    idempotency_key: str
    source_preflight_report_id: str
    source_design_report_id: str
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type
            if self.event_type in LIVE_PERMISSION_JOURNAL_EVENT_TYPES
            else "UNKNOWN",
            "intent_id": self.intent_id,
            "decision_id": self.decision_id,
            "permission_status": self.permission_status
            if self.permission_status in LIVE_PERMISSION_STATUSES
            else "UNKNOWN",
            "permission_scope": self.permission_scope if self.permission_scope in LIVE_PERMISSION_SCOPES else "UNKNOWN",
            "confirmation_state": self.confirmation_state
            if self.confirmation_state in LIVE_PERMISSION_CONFIRMATION_STATES
            else "UNKNOWN",
            "order_intent_workflow_allowed": bool(self.order_intent_workflow_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_design_report_id": self.source_design_report_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LivePermissionSummary:
    total_records: int = 0
    total_granted: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_intent_id: str = ""
    latest_decision_id: str = ""
    latest_permission_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_granted": int(self.total_granted),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_intent_id": self.latest_intent_id,
            "latest_decision_id": self.latest_decision_id,
            "latest_permission_status": self.latest_permission_status,
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
