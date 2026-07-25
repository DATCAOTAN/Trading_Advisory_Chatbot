from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List

from src.config import Config
from src.services.trading.market.data_quality import DataQualityReport
from src.services.trading.market.feature_models import FeatureSnapshot, IndicatorSnapshot
from src.services.trading.market.indicators import IndicatorEngine
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundle


class FeatureEngine:
    def __init__(self, indicator_engine: IndicatorEngine | None = None):
        self.indicator_engine = indicator_engine or IndicatorEngine()

    def compute(self, bundle: MarketSnapshotBundle, quality_report: DataQualityReport, primary_timeframe: str = "M15") -> FeatureSnapshot:
        created_at = datetime.now(timezone.utc).isoformat()
        indicator_snapshots: Dict[str, IndicatorSnapshot] = {}
        warnings: List[str] = list(bundle.warnings) + list(quality_report.warnings)
        blockers: List[str] = [issue.code for issue in quality_report.issues if issue.severity == "ERROR"]

        for timeframe, snapshot in sorted(bundle.timeframes.items()):
            if snapshot.bars:
                indicator_snapshots[timeframe] = self.indicator_engine.compute(snapshot)
            else:
                indicator_snapshots[timeframe] = IndicatorSnapshot(bundle.symbol, timeframe, data_quality="EMPTY", warnings=["empty_bars"])

        primary = indicator_snapshots.get(primary_timeframe) or next(iter(indicator_snapshots.values()), None)
        trend_direction = _trend_direction(primary)
        trend_strength = _trend_strength(primary)
        volatility_state = _volatility_state(primary)
        momentum_state = _momentum_state(primary)
        range_chop_score = _range_chop_score(primary, trend_strength)
        spread_state = _spread_state(bundle)

        snapshot = FeatureSnapshot(
            feature_snapshot_id=_feature_id(bundle.bundle_id, created_at),
            created_at=created_at,
            symbol=bundle.symbol,
            broker_symbol=bundle.broker_symbol,
            provider_name=bundle.provider_name,
            timeframes=list(bundle.timeframes.keys()),
            primary_timeframe=primary.timeframe if primary else primary_timeframe,
            indicator_snapshots=indicator_snapshots,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            volatility_state=volatility_state,
            momentum_state=momentum_state,
            pullback_detected=_pullback_detected(primary, trend_direction),
            breakout_candidate=_breakout_candidate(primary),
            range_chop_score=range_chop_score,
            multi_timeframe_alignment=_multi_timeframe_alignment(indicator_snapshots),
            spread_state=spread_state,
            data_quality_status=quality_report.status,
            warnings=warnings,
            blockers=blockers,
            source_snapshot_ids=[bundle.bundle_id],
        )
        if quality_report.status in {"INVALID", "EMPTY"}:
            snapshot.trend_direction = "UNKNOWN"
            snapshot.volatility_state = "UNKNOWN"
            snapshot.momentum_state = "UNKNOWN"
            snapshot.multi_timeframe_alignment = "UNKNOWN"
        return snapshot


def _trend_direction(indicator: IndicatorSnapshot | None) -> str:
    if not indicator or indicator.ema_fast is None or indicator.ema_slow is None or indicator.latest_close is None:
        return "UNKNOWN"
    ema_distance_ratio = abs(indicator.ema_fast - indicator.ema_slow) / max(abs(indicator.latest_close), 1.0)
    if ema_distance_ratio < 0.0002:
        return "SIDEWAYS"
    if indicator.ema_fast > indicator.ema_slow and indicator.latest_close >= indicator.ema_fast:
        return "UP"
    if indicator.ema_fast < indicator.ema_slow and indicator.latest_close <= indicator.ema_fast:
        return "DOWN"
    return "SIDEWAYS"


def _trend_strength(indicator: IndicatorSnapshot | None) -> float:
    if not indicator or not indicator.latest_close or indicator.ema_fast is None or indicator.ema_slow is None:
        return 0.0
    ema_distance = abs(indicator.ema_fast - indicator.ema_slow) / max(abs(indicator.latest_close), 1.0)
    atr_ratio = (indicator.atr or 0.0) / max(abs(indicator.latest_close), 1.0)
    return _clamp((ema_distance * 80) + (atr_ratio * 8))


def _volatility_state(indicator: IndicatorSnapshot | None) -> str:
    if not indicator or not indicator.latest_close or indicator.atr is None:
        return "UNKNOWN"
    ratio = indicator.atr / max(abs(indicator.latest_close), 1.0)
    if ratio < 0.0008:
        return "LOW"
    if ratio < 0.0025:
        return "NORMAL"
    if ratio < 0.005:
        return "HIGH"
    return "EXTREME"


def _momentum_state(indicator: IndicatorSnapshot | None) -> str:
    if not indicator or indicator.rsi is None or indicator.macd_histogram is None:
        return "UNKNOWN"
    if indicator.rsi >= 55 and indicator.macd_histogram > 0:
        return "BULLISH"
    if indicator.rsi <= 45 and indicator.macd_histogram < 0:
        return "BEARISH"
    return "NEUTRAL"


def _pullback_detected(indicator: IndicatorSnapshot | None, trend_direction: str) -> bool:
    if not indicator or indicator.latest_close is None or indicator.ema_fast is None or indicator.atr is None:
        return False
    distance = abs(indicator.latest_close - indicator.ema_fast)
    near_ema = distance <= max(indicator.atr * 0.75, 0.0001)
    if trend_direction == "UP":
        return near_ema and indicator.latest_close >= (indicator.ema_slow or indicator.ema_fast)
    if trend_direction == "DOWN":
        return near_ema and indicator.latest_close <= (indicator.ema_slow or indicator.ema_fast)
    return False


def _breakout_candidate(indicator: IndicatorSnapshot | None) -> bool:
    if not indicator or indicator.latest_close is None or indicator.swing_high is None or indicator.swing_low is None or indicator.atr is None:
        return False
    buffer = indicator.atr * 0.25
    return indicator.latest_close >= indicator.swing_high - buffer or indicator.latest_close <= indicator.swing_low + buffer


def _range_chop_score(indicator: IndicatorSnapshot | None, trend_strength: float) -> float:
    if not indicator or not indicator.latest_close or indicator.ema_fast is None or indicator.ema_slow is None:
        return 1.0
    ema_distance = abs(indicator.ema_fast - indicator.ema_slow) / max(abs(indicator.latest_close), 1.0)
    volatility = indicator.rolling_volatility or 0.0
    compressed = 1.0 - _clamp(ema_distance * 200 + volatility * 80)
    return _clamp((compressed * 0.65) + ((1.0 - trend_strength) * 0.35))


def _multi_timeframe_alignment(indicators: Dict[str, IndicatorSnapshot]) -> str:
    directions = [_trend_direction(item) for item in indicators.values()]
    known = [direction for direction in directions if direction in {"UP", "DOWN", "SIDEWAYS"}]
    if not known:
        return "UNKNOWN"
    if all(direction == "UP" for direction in known):
        return "ALIGNED_UP"
    if all(direction == "DOWN" for direction in known):
        return "ALIGNED_DOWN"
    return "MIXED"


def _spread_state(bundle: MarketSnapshotBundle) -> str:
    if not bundle.tick or bundle.tick.spread is None:
        return "UNKNOWN"
    configured = getattr(Config, f"MARKET_MAX_SPREAD_{bundle.symbol}", None)
    if configured is None:
        return "UNKNOWN"
    max_spread = float(configured)
    if bundle.tick.spread < 0:
        return "UNKNOWN"
    return "OK" if bundle.tick.spread <= max_spread else "WIDE"


def _feature_id(bundle_id: str, created_at: str) -> str:
    return "feature_" + hashlib.sha256(f"{bundle_id}|{created_at}".encode("utf-8")).hexdigest()[:16]


def _clamp(value: float) -> float:
    try:
        numeric = float(value)
        if numeric != numeric:
            return 0.0
        return max(0.0, min(1.0, numeric))
    except Exception:
        return 0.0
