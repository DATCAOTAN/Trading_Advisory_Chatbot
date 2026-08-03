from __future__ import annotations

import hashlib
from typing import Optional

from src.config import Config
from src.services.trading.calendar.models import CalendarContext
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot, created_at_utc


class MarketRegimeDetector:
    def detect(self, feature_snapshot: FeatureSnapshot, calendar_context: Optional[CalendarContext] = None) -> MarketRegimeSnapshot:
        created_at = created_at_utc()
        warnings = list(feature_snapshot.warnings)
        blockers = list(feature_snapshot.blockers)
        secondary: list[str] = []
        calendar_risk_state = calendar_context.calendar_risk_state if calendar_context else "UNKNOWN"
        if calendar_context:
            warnings.extend(calendar_context.warnings)
            blockers.extend(calendar_context.errors)

        primary = "UNKNOWN"
        confidence = 0.0
        if feature_snapshot.data_quality_status in {"INVALID", "EMPTY"}:
            blockers.append(f"DATA_QUALITY_{feature_snapshot.data_quality_status}")
            primary = "UNKNOWN"
            confidence = 0.0
        elif calendar_risk_state in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"}:
            blockers.append("IMMEDIATE_HIGH_IMPACT_EVENT")
            primary = "NEWS_RISK"
            confidence = 0.85
        else:
            primary, confidence = _market_regime_from_features(feature_snapshot)

        if calendar_risk_state in {"UPCOMING_HIGH_IMPACT", "POST_EVENT_COOLDOWN"}:
            secondary.append("NEWS_RISK")
        if feature_snapshot.volatility_state == "EXTREME":
            secondary.append("HIGH_VOLATILITY")
        if feature_snapshot.volatility_state == "LOW":
            secondary.append("LOW_VOLATILITY")
        if feature_snapshot.breakout_candidate:
            secondary.append("BREAKOUT_CANDIDATE")
        if feature_snapshot.range_chop_score >= float(getattr(Config, "MARKET_REGIME_CHOP_SCORE_THRESHOLD", 0.72)):
            secondary.append("CHOPPY")

        evidence = getattr(feature_snapshot, "reasoning_evidence_v2", None)
        return MarketRegimeSnapshot(
            regime_snapshot_id=_regime_id(feature_snapshot.feature_snapshot_id, calendar_context.context_id if calendar_context else "", created_at),
            created_at=created_at,
            symbol=feature_snapshot.symbol,
            primary_regime=primary,
            secondary_regimes=secondary,
            confidence=confidence,
            trend_direction=feature_snapshot.trend_direction,
            volatility_state=feature_snapshot.volatility_state,
            momentum_state=feature_snapshot.momentum_state,
            range_chop_score=feature_snapshot.range_chop_score,
            pullback_detected=feature_snapshot.pullback_detected,
            breakout_candidate=feature_snapshot.breakout_candidate,
            multi_timeframe_alignment=feature_snapshot.multi_timeframe_alignment,
            calendar_risk_state=calendar_risk_state,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            source_feature_snapshot_id=feature_snapshot.feature_snapshot_id,
            source_calendar_context_id=calendar_context.context_id if calendar_context else "",
            regime_version=("market-regime/v2" if evidence else "market-regime/v1"),
            reasoning_regime=(evidence.regime if evidence else ""),
            supporting_factors=(
                [item.code for item in evidence.reasons if item.severity == "INFO"]
                if evidence else []
            ),
            opposing_factors=(
                [item.code for item in evidence.reasons if item.severity in {"WARN", "ERROR"}]
                if evidence else []
            ),
        )


def _market_regime_from_features(feature: FeatureSnapshot) -> tuple[str, float]:
    trend_threshold = float(getattr(Config, "MARKET_REGIME_TREND_STRENGTH_THRESHOLD", 0.2))
    max_trend_chop = float(getattr(Config, "MARKET_REGIME_TREND_MAX_CHOP_SCORE", 0.62))
    chop_threshold = float(getattr(Config, "MARKET_REGIME_CHOP_SCORE_THRESHOLD", 0.72))

    if feature.pullback_detected and feature.trend_direction == "UP":
        return "PULLBACK_UPTREND", _confidence(feature, base=0.68)
    if feature.pullback_detected and feature.trend_direction == "DOWN":
        return "PULLBACK_DOWNTREND", _confidence(feature, base=0.68)
    if feature.trend_direction == "UP" and feature.trend_strength >= trend_threshold and feature.range_chop_score <= max_trend_chop:
        return "TRENDING_UP", _confidence(feature, base=0.72)
    if feature.trend_direction == "DOWN" and feature.trend_strength >= trend_threshold and feature.range_chop_score <= max_trend_chop:
        return "TRENDING_DOWN", _confidence(feature, base=0.72)
    if feature.range_chop_score >= chop_threshold:
        return "CHOPPY", _confidence(feature, base=0.62)
    if feature.trend_direction == "SIDEWAYS":
        return "RANGING", _confidence(feature, base=0.58)
    if feature.breakout_candidate:
        return "BREAKOUT_CANDIDATE", _confidence(feature, base=0.55)
    if feature.volatility_state == "EXTREME":
        return "HIGH_VOLATILITY", 0.55
    if feature.volatility_state == "LOW":
        return "LOW_VOLATILITY", 0.5
    return "UNKNOWN", 0.2


def _confidence(feature: FeatureSnapshot, base: float) -> float:
    quality_bonus = 0.12 if feature.data_quality_status == "COMPLETE" else 0.05 if feature.data_quality_status == "PARTIAL" else 0.0
    alignment_bonus = 0.08 if feature.multi_timeframe_alignment in {"ALIGNED_UP", "ALIGNED_DOWN"} else 0.0
    strength_bonus = min(0.12, feature.trend_strength * 0.12)
    chop_penalty = max(0.0, feature.range_chop_score - 0.75) * 0.15
    return _clamp(base + quality_bonus + alignment_bonus + strength_bonus - chop_penalty)


def _regime_id(feature_id: str, context_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{feature_id}|{context_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"market_regime_{digest}"


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
