from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


PROPOSAL_BOUNDARY_STATUSES = {
    "READY_FOR_CONFIRMATION",
    "CONFIRMED_FOR_PROPOSAL_WORKFLOW",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}

HUMAN_CONFIRMATION_STATES = {
    "NOT_REQUESTED",
    "ACKNOWLEDGED_DRY_RUN_ONLY",
    "CONFIRMED_PROPOSAL_WORKFLOW",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
}

PROPOSAL_INTENT_EVENT_TYPES = {
    "PROPOSAL_INTENT_CREATED",
    "PROPOSAL_INTENT_CONFIRMED",
    "PROPOSAL_INTENT_BLOCKED",
    "PROPOSAL_INTENT_EXPIRED",
    "PROPOSAL_INTENT_DUPLICATE",
    "PROPOSAL_INTENT_INVALID",
    "JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class HumanConfirmedProposalIntent:
    intent_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    proposal_boundary_status: str = "UNKNOWN"
    human_confirmation_state: str = "UNKNOWN"
    proposal_workflow_allowed: bool = False
    dry_run_only: bool = True
    executable: bool = False
    user_acknowledgement_text: str = ""
    confirmation_phrase_required: str = ""
    confirmation_phrase_received: str = ""
    review_status: str = ""
    readiness_action: str = ""
    gate_action: str = ""
    dry_run_allowed: bool = False
    dry_run_executed: bool = False
    artifact_id: str = ""
    artifact_hash: str = ""
    dry_run_receipt_id: str = ""
    idempotency_key: str = ""
    source_review_artifact_id: str = ""
    source_gate_decision_id: str = ""
    source_dry_run_receipt_id: str = ""
    source_execution_journal_record_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "proposal_boundary_status": self.proposal_boundary_status
            if self.proposal_boundary_status in PROPOSAL_BOUNDARY_STATUSES
            else "UNKNOWN",
            "human_confirmation_state": self.human_confirmation_state
            if self.human_confirmation_state in HUMAN_CONFIRMATION_STATES
            else "UNKNOWN",
            "proposal_workflow_allowed": bool(self.proposal_workflow_allowed),
            "dry_run_only": True,
            "executable": False,
            "user_acknowledgement_text": self.user_acknowledgement_text,
            "confirmation_phrase_required": self.confirmation_phrase_required,
            "confirmation_phrase_received": self.confirmation_phrase_received,
            "review_status": self.review_status,
            "readiness_action": self.readiness_action,
            "gate_action": self.gate_action,
            "dry_run_allowed": bool(self.dry_run_allowed),
            "dry_run_executed": False,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "dry_run_receipt_id": self.dry_run_receipt_id,
            "idempotency_key": self.idempotency_key,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_gate_decision_id": self.source_gate_decision_id,
            "source_dry_run_receipt_id": self.source_dry_run_receipt_id,
            "source_execution_journal_record_id": self.source_execution_journal_record_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "reasons": list(dict.fromkeys(self.reasons)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ProposalIntentJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    intent_id: str
    proposal_boundary_status: str
    human_confirmation_state: str
    proposal_workflow_allowed: bool
    dry_run_only: bool
    executable: bool
    artifact_id: str
    artifact_hash: str
    dry_run_receipt_id: str
    idempotency_key: str
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in PROPOSAL_INTENT_EVENT_TYPES else "UNKNOWN",
            "intent_id": self.intent_id,
            "proposal_boundary_status": self.proposal_boundary_status,
            "human_confirmation_state": self.human_confirmation_state,
            "proposal_workflow_allowed": bool(self.proposal_workflow_allowed),
            "dry_run_only": True,
            "executable": False,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "dry_run_receipt_id": self.dry_run_receipt_id,
            "idempotency_key": self.idempotency_key,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class ProposalBoundarySummary:
    latest_intent_id: str = ""
    latest_status: str = ""
    total_intents: int = 0
    total_confirmed: int = 0
    total_blocked: int = 0
    total_expired: int = 0
    total_duplicates: int = 0
    latest_created_at: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "latest_intent_id": self.latest_intent_id,
            "latest_status": self.latest_status,
            "total_intents": int(self.total_intents),
            "total_confirmed": int(self.total_confirmed),
            "total_blocked": int(self.total_blocked),
            "total_expired": int(self.total_expired),
            "total_duplicates": int(self.total_duplicates),
            "latest_created_at": self.latest_created_at,
            "warnings": list(dict.fromkeys(self.warnings)),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
