from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


PRIMARY_REGIMES = {
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGING",
    "CHOPPY",
    "PULLBACK_UPTREND",
    "PULLBACK_DOWNTREND",
    "BREAKOUT_CANDIDATE",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "NEWS_RISK",
    "UNKNOWN",
}


@dataclass
class MarketRegimeSnapshot:
    regime_snapshot_id: str
    created_at: str
    symbol: str
    primary_regime: str = "UNKNOWN"
    secondary_regimes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    trend_direction: str = "UNKNOWN"
    volatility_state: str = "UNKNOWN"
    momentum_state: str = "UNKNOWN"
    range_chop_score: float = 0.0
    pullback_detected: bool = False
    breakout_candidate: bool = False
    multi_timeframe_alignment: str = "UNKNOWN"
    calendar_risk_state: str = "UNKNOWN"
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_feature_snapshot_id: str = ""
    source_calendar_context_id: str = ""
    regime_version: str = "market-regime/v1"
    reasoning_regime: str = ""
    supporting_factors: List[str] = field(default_factory=list)
    opposing_factors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "regime_snapshot_id": self.regime_snapshot_id,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "primary_regime": self.primary_regime,
            "secondary_regimes": list(dict.fromkeys(self.secondary_regimes)),
            "confidence": _clamp(self.confidence),
            "trend_direction": self.trend_direction,
            "volatility_state": self.volatility_state,
            "momentum_state": self.momentum_state,
            "range_chop_score": _clamp(self.range_chop_score),
            "pullback_detected": bool(self.pullback_detected),
            "breakout_candidate": bool(self.breakout_candidate),
            "multi_timeframe_alignment": self.multi_timeframe_alignment,
            "calendar_risk_state": self.calendar_risk_state,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "source_feature_snapshot_id": self.source_feature_snapshot_id,
            "source_calendar_context_id": self.source_calendar_context_id,
            "regime_version": self.regime_version,
            "reasoning_regime": self.reasoning_regime,
            "supporting_factors": list(self.supporting_factors),
            "opposing_factors": list(self.opposing_factors),
        }


def created_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
