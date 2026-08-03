from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class IndicatorSnapshot:
    symbol: str
    timeframe: str
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ema_fast: float | None = None
    ema_slow: float | None = None
    sma_fast: float | None = None
    sma_slow: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr: float | None = None
    rolling_volatility: float | None = None
    latest_close: float | None = None
    latest_range: float | None = None
    latest_body: float | None = None
    swing_high: float | None = None
    swing_low: float | None = None
    support_zones: List[float] = field(default_factory=list)
    resistance_zones: List[float] = field(default_factory=list)
    data_quality: str = "EMPTY"
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "computed_at": self.computed_at,
            "ema_fast": _json_number(self.ema_fast),
            "ema_slow": _json_number(self.ema_slow),
            "sma_fast": _json_number(self.sma_fast),
            "sma_slow": _json_number(self.sma_slow),
            "rsi": _json_number(self.rsi),
            "macd": _json_number(self.macd),
            "macd_signal": _json_number(self.macd_signal),
            "macd_histogram": _json_number(self.macd_histogram),
            "atr": _json_number(self.atr),
            "rolling_volatility": _json_number(self.rolling_volatility),
            "latest_close": _json_number(self.latest_close),
            "latest_range": _json_number(self.latest_range),
            "latest_body": _json_number(self.latest_body),
            "swing_high": _json_number(self.swing_high),
            "swing_low": _json_number(self.swing_low),
            "support_zones": [_json_number(value) for value in self.support_zones if _json_number(value) is not None],
            "resistance_zones": [_json_number(value) for value in self.resistance_zones if _json_number(value) is not None],
            "data_quality": self.data_quality,
            "warnings": list(self.warnings),
        }


@dataclass
class FeatureSnapshot:
    feature_snapshot_id: str
    created_at: str
    symbol: str
    broker_symbol: str
    provider_name: str
    timeframes: List[str]
    primary_timeframe: str
    indicator_snapshots: Dict[str, IndicatorSnapshot]
    trend_direction: str = "UNKNOWN"
    trend_strength: float = 0.0
    volatility_state: str = "UNKNOWN"
    momentum_state: str = "UNKNOWN"
    pullback_detected: bool = False
    breakout_candidate: bool = False
    range_chop_score: float = 0.0
    multi_timeframe_alignment: str = "UNKNOWN"
    spread_state: str = "UNKNOWN"
    data_quality_status: str = "EMPTY"
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    source_snapshot_ids: List[str] = field(default_factory=list)
    reasoning_evidence_v2: Any | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "feature_snapshot_id": self.feature_snapshot_id,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "provider_name": self.provider_name,
            "timeframes": list(self.timeframes),
            "primary_timeframe": self.primary_timeframe,
            "indicator_snapshots": {key: value.as_dict() for key, value in self.indicator_snapshots.items()},
            "trend_direction": self.trend_direction,
            "trend_strength": _clamp(self.trend_strength),
            "volatility_state": self.volatility_state,
            "momentum_state": self.momentum_state,
            "pullback_detected": bool(self.pullback_detected),
            "breakout_candidate": bool(self.breakout_candidate),
            "range_chop_score": _clamp(self.range_chop_score),
            "multi_timeframe_alignment": self.multi_timeframe_alignment,
            "spread_state": self.spread_state,
            "data_quality_status": self.data_quality_status,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "reasoning_evidence_v2": (
                self.reasoning_evidence_v2.as_dict()
                if self.reasoning_evidence_v2 is not None
                else None
            ),
        }


def _json_number(value: float | None) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return round(number, 8)
    except Exception:
        return None


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
