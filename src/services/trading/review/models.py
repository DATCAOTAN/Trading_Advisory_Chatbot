from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


REVIEW_STATUSES = {
    "READY_FOR_REVIEW",
    "WAITING",
    "BLOCKED",
    "NO_TRADE_CONTEXT",
    "MANAGE_EXISTING_POSITION",
    "UNKNOWN",
}


@dataclass
class HumanReviewArtifact:
    artifact_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    review_status: str = "UNKNOWN"
    readiness_action: str = "UNKNOWN"
    readiness_score: float = 0.0
    confidence: float = 0.0
    grade: str = "UNKNOWN"
    primary_method_id: str = ""
    supporting_method_ids: List[str] = field(default_factory=list)
    selected_playbook_ids: List[str] = field(default_factory=list)
    primary_regime: str = "UNKNOWN"
    calendar_risk_state: str = "UNKNOWN"
    final_context_score: float = 0.0
    component_score_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    source_readiness_decision_id: str = ""
    source_score_report_id: str = ""
    source_method_selection_id: str = ""
    source_context_pack_id: str = ""
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "review_status": self.review_status if self.review_status in REVIEW_STATUSES else "UNKNOWN",
            "readiness_action": self.readiness_action,
            "readiness_score": _clamp(self.readiness_score),
            "confidence": _clamp(self.confidence),
            "grade": self.grade,
            "primary_method_id": self.primary_method_id,
            "supporting_method_ids": list(dict.fromkeys(self.supporting_method_ids)),
            "selected_playbook_ids": list(dict.fromkeys(self.selected_playbook_ids)),
            "primary_regime": self.primary_regime,
            "calendar_risk_state": self.calendar_risk_state,
            "final_context_score": _clamp(self.final_context_score),
            "component_score_summary": dict(self.component_score_summary),
            "reasons": list(dict.fromkeys(self.reasons)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "blockers": list(self.blockers),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "source_readiness_decision_id": self.source_readiness_decision_id,
            "source_score_report_id": self.source_score_report_id,
            "source_method_selection_id": self.source_method_selection_id,
            "source_context_pack_id": self.source_context_pack_id,
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ReviewCard:
    title: str
    status_label: str
    summary: str
    method_section: Dict[str, Any] = field(default_factory=dict)
    market_section: Dict[str, Any] = field(default_factory=dict)
    calendar_section: Dict[str, Any] = field(default_factory=dict)
    score_section: Dict[str, Any] = field(default_factory=dict)
    blocker_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = ""
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "method_section": dict(self.method_section),
            "market_section": dict(self.market_section),
            "calendar_section": dict(self.calendar_section),
            "score_section": dict(self.score_section),
            "blocker_section": dict(self.blocker_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
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
