from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


SCORE_GRADES = {"EXCELLENT", "GOOD", "ACCEPTABLE", "WEAK", "BLOCKED", "UNKNOWN"}
COMPONENT_NAMES = {
    "technical_score",
    "method_fit_score",
    "regime_alignment_score",
    "macro_calendar_score",
    "risk_context_score",
    "data_quality_score",
    "execution_feasibility_score",
}


@dataclass
class ScoreComponent:
    name: str
    score: float = 0.0
    grade: str = "UNKNOWN"
    weight: float = 0.0
    weighted_score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        score = _clamp(self.score)
        weight = _clamp(self.weight)
        return {
            "name": self.name,
            "score": score,
            "grade": self.grade,
            "weight": weight,
            "weighted_score": _clamp(self.weighted_score),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "source_refs": list(dict.fromkeys(self.source_refs)),
        }


@dataclass
class SignalScoreBreakdown:
    technical_score: ScoreComponent
    method_fit_score: ScoreComponent
    regime_alignment_score: ScoreComponent
    macro_calendar_score: ScoreComponent
    risk_context_score: ScoreComponent
    data_quality_score: ScoreComponent
    execution_feasibility_score: ScoreComponent
    final_context_score: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "technical_score": self.technical_score.as_dict(),
            "method_fit_score": self.method_fit_score.as_dict(),
            "regime_alignment_score": self.regime_alignment_score.as_dict(),
            "macro_calendar_score": self.macro_calendar_score.as_dict(),
            "risk_context_score": self.risk_context_score.as_dict(),
            "data_quality_score": self.data_quality_score.as_dict(),
            "execution_feasibility_score": self.execution_feasibility_score.as_dict(),
            "final_context_score": _clamp(self.final_context_score),
        }


@dataclass
class SignalScoreReport:
    score_report_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    primary_method_id: str
    supporting_method_ids: List[str] = field(default_factory=list)
    selected_playbook_ids: List[str] = field(default_factory=list)
    components: SignalScoreBreakdown | None = None
    final_context_score: float = 0.0
    grade: str = "UNKNOWN"
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scoring_summary: str = ""
    source_feature_snapshot_id: str = ""
    source_calendar_context_id: str = ""
    source_regime_snapshot_id: str = ""
    source_context_pack_id: str = ""
    source_method_selection_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score_report_id": self.score_report_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "primary_method_id": self.primary_method_id,
            "supporting_method_ids": list(dict.fromkeys(self.supporting_method_ids)),
            "selected_playbook_ids": list(dict.fromkeys(self.selected_playbook_ids)),
            "components": self.components.as_dict() if self.components else None,
            "final_context_score": _clamp(self.final_context_score),
            "grade": self.grade,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "scoring_summary": self.scoring_summary,
            "source_feature_snapshot_id": self.source_feature_snapshot_id,
            "source_calendar_context_id": self.source_calendar_context_id,
            "source_regime_snapshot_id": self.source_regime_snapshot_id,
            "source_context_pack_id": self.source_context_pack_id,
            "source_method_selection_id": self.source_method_selection_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


def grade_for_score(score: float, blocked: bool = False) -> str:
    if blocked:
        return "BLOCKED"
    value = _clamp(score)
    if value >= 0.85:
        return "EXCELLENT"
    if value >= 0.7:
        return "GOOD"
    if value >= 0.5:
        return "ACCEPTABLE"
    if value > 0.0:
        return "WEAK"
    return "UNKNOWN"


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
