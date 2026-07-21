from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


TRADE_READINESS_ACTIONS = {
    "WAIT",
    "NO_TRADE",
    "REVIEW_READY",
    "BLOCKED",
    "MANAGE_EXISTING_POSITION",
    "UNKNOWN",
}


@dataclass
class DecisionBlocker:
    code: str
    severity: str = "WARN"
    message: str = ""
    source: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
        }


@dataclass
class TradeReadinessDecision:
    decision_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    action: str = "UNKNOWN"
    readiness_score: float = 0.0
    confidence: float = 0.0
    grade: str = "UNKNOWN"
    primary_method_id: str = ""
    selected_playbook_ids: List[str] = field(default_factory=list)
    blockers: List[DecisionBlocker] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    source_score_report_id: str = ""
    source_feature_snapshot_id: str = ""
    source_calendar_context_id: str = ""
    source_regime_snapshot_id: str = ""
    source_context_pack_id: str = ""
    source_method_selection_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "action": self.action if self.action in TRADE_READINESS_ACTIONS else "UNKNOWN",
            "readiness_score": _clamp(self.readiness_score),
            "confidence": _clamp(self.confidence),
            "grade": self.grade,
            "primary_method_id": self.primary_method_id,
            "selected_playbook_ids": list(dict.fromkeys(self.selected_playbook_ids)),
            "blockers": [item.as_dict() for item in self.blockers],
            "warnings": list(dict.fromkeys(self.warnings)),
            "reasons": list(dict.fromkeys(self.reasons)),
            "source_score_report_id": self.source_score_report_id,
            "source_feature_snapshot_id": self.source_feature_snapshot_id,
            "source_calendar_context_id": self.source_calendar_context_id,
            "source_regime_snapshot_id": self.source_regime_snapshot_id,
            "source_context_pack_id": self.source_context_pack_id,
            "source_method_selection_id": self.source_method_selection_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
