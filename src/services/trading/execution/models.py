from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


EXECUTION_MODES = {
    "DISABLED",
    "REVIEW_ONLY",
    "HUMAN_CONFIRMED_DRY_RUN",
    "HUMAN_CONFIRMED_LIVE_RESERVED",
    "AUTONOMOUS_DISABLED",
}

EXECUTION_GATE_ACTIONS = {
    "ALLOW_DRY_RUN",
    "BLOCKED",
    "REQUIRES_HUMAN_CONFIRMATION",
    "ARTIFACT_EXPIRED",
    "DUPLICATE_ARTIFACT",
    "INVALID_ARTIFACT",
    "EXECUTION_DISABLED",
    "UNKNOWN",
}


@dataclass
class ExecutionGateDecision:
    gate_decision_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    action: str = "UNKNOWN"
    allowed: bool = False
    dry_run_only: bool = True
    reason: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifact_id: str = ""
    artifact_hash: str = ""
    artifact_age_seconds: float = 0.0
    source_review_artifact_id: str = ""
    source_readiness_decision_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "gate_decision_id": self.gate_decision_id,
            "created_at": self.created_at,
            "mode": self.mode if self.mode in EXECUTION_MODES else "DISABLED",
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "action": self.action if self.action in EXECUTION_GATE_ACTIONS else "UNKNOWN",
            "allowed": bool(self.allowed),
            "dry_run_only": bool(self.dry_run_only),
            "reason": self.reason,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "artifact_age_seconds": round(float(self.artifact_age_seconds), 3),
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_readiness_decision_id": self.source_readiness_decision_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class DryRunExecutionReceipt:
    receipt_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    dry_run_only: bool = True
    gate_action: str = "UNKNOWN"
    allowed: bool = False
    executed: bool = False
    execution_provider: str = "dry_run"
    artifact_id: str = ""
    artifact_hash: str = ""
    idempotency_key: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    message: str = ""
    source_gate_decision_id: str = ""
    source_review_artifact_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "mode": self.mode if self.mode in EXECUTION_MODES else "DISABLED",
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "dry_run_only": True,
            "gate_action": self.gate_action if self.gate_action in EXECUTION_GATE_ACTIONS else "UNKNOWN",
            "allowed": bool(self.allowed),
            "executed": False,
            "execution_provider": self.execution_provider,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "message": self.message,
            "source_gate_decision_id": self.source_gate_decision_id,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
