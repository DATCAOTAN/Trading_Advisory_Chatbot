from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


EXECUTION_JOURNAL_EVENT_TYPES = {
    "DRY_RUN_GATE_EVALUATED",
    "DRY_RUN_RECEIPT_CREATED",
    "DRY_RUN_DUPLICATE_DETECTED",
    "DRY_RUN_BLOCKED",
    "DRY_RUN_ALLOWED",
    "JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class ExecutionJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    mode: str
    symbol: str
    broker_symbol: str
    artifact_id: str
    artifact_hash: str
    idempotency_key: str
    gate_decision_id: str
    gate_action: str
    receipt_id: str
    dry_run_only: bool = True
    executed: bool = False
    allowed: bool = False
    review_status: str = ""
    readiness_action: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in EXECUTION_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "gate_decision_id": self.gate_decision_id,
            "gate_action": self.gate_action,
            "receipt_id": self.receipt_id,
            "dry_run_only": True,
            "executed": False,
            "allowed": bool(self.allowed),
            "review_status": self.review_status,
            "readiness_action": self.readiness_action,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class ExecutionJournalSummary:
    total_records: int = 0
    total_dry_runs: int = 0
    total_blocked: int = 0
    total_allowed: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_artifact_hash: str = ""
    latest_gate_action: str = ""
    latest_receipt_id: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_dry_runs": int(self.total_dry_runs),
            "total_blocked": int(self.total_blocked),
            "total_allowed": int(self.total_allowed),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_artifact_hash": self.latest_artifact_hash,
            "latest_gate_action": self.latest_gate_action,
            "latest_receipt_id": self.latest_receipt_id,
            "warnings": list(dict.fromkeys(self.warnings)),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
