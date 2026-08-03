from __future__ import annotations

import hashlib
import json
from typing import Any

from src.config import Config
from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import CandidateKnowledgeSet, RuntimeContextPack, now_utc_iso
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot


class RuntimeContextPackBuilder:
    def build(
        self,
        candidates: CandidateKnowledgeSet,
        feature_snapshot: FeatureSnapshot,
        calendar_context: CalendarContext,
        market_regime: MarketRegimeSnapshot,
        mode: str,
        symbol: str,
        broker_symbol: str,
    ) -> RuntimeContextPack:
        max_methods = int(getattr(Config, "KNOWLEDGE_MAX_METHOD_CARDS", 3))
        max_macros = int(getattr(Config, "KNOWLEDGE_MAX_MACRO_CARDS", 3))
        max_playbooks = int(getattr(Config, "KNOWLEDGE_MAX_PLAYBOOKS", 3))
        created_at = now_utc_iso()
        selected_methods = [_method_summary(item) for item in candidates.method_cards[:max_methods]]
        selected_macros = [_macro_summary(item) for item in candidates.macro_cards[:max_macros]]
        selected_playbooks = [_playbook_summary(item) for item in candidates.strategy_playbooks[:max_playbooks]]
        source_refs = list(
            dict.fromkeys(
                list(candidates.source_refs)
                + _collect_source_refs(selected_methods)
                + _collect_source_refs(selected_macros)
                + _collect_source_refs(selected_playbooks)
            )
        )
        warnings = list(candidates.warnings)
        if len(candidates.method_cards) > max_methods:
            warnings.append("method_cards_truncated")
        if len(candidates.macro_cards) > max_macros:
            warnings.append("macro_cards_truncated")
        if len(candidates.strategy_playbooks) > max_playbooks:
            warnings.append("playbooks_truncated")

        pack = RuntimeContextPack(
            context_pack_id=_pack_id(mode, symbol, feature_snapshot.feature_snapshot_id, market_regime.regime_snapshot_id, created_at),
            created_at=created_at,
            mode=mode,
            symbol=symbol,
            broker_symbol=broker_symbol,
            feature_snapshot_summary=_feature_summary(feature_snapshot),
            calendar_context_summary=_calendar_summary(calendar_context),
            market_regime_summary=_regime_summary(market_regime),
            selected_method_cards=selected_methods,
            selected_macro_cards=selected_macros,
            selected_playbooks=selected_playbooks,
            rejected_or_blocked_knowledge=[item.as_dict() for item in candidates.rejected_items],
            source_refs=source_refs,
            warnings=warnings,
            blockers=list(market_regime.blockers) + list(calendar_context.errors),
        )
        payload = pack.as_dict()
        payload_chars = len(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        pack.payload_size_chars = payload_chars
        pack.token_budget_estimate = max(1, payload_chars // 4)
        max_chars = int(getattr(Config, "KNOWLEDGE_MAX_CONTEXT_CHARS", 12000))
        if payload_chars > max_chars:
            pack.blockers.append("CONTEXT_PACK_TOO_LARGE")
        return pack


def _feature_summary(feature: FeatureSnapshot) -> dict[str, Any]:
    summary = {
        "feature_snapshot_id": feature.feature_snapshot_id,
        "source_snapshot_ids": list(feature.source_snapshot_ids),
        "symbol": feature.symbol,
        "broker_symbol": feature.broker_symbol,
        "provider_name": feature.provider_name,
        "timeframes": list(feature.timeframes),
        "primary_timeframe": feature.primary_timeframe,
        "trend_direction": feature.trend_direction,
        "trend_strength": round(float(feature.trend_strength), 4),
        "volatility_state": feature.volatility_state,
        "momentum_state": feature.momentum_state,
        "pullback_detected": bool(feature.pullback_detected),
        "breakout_candidate": bool(feature.breakout_candidate),
        "range_chop_score": round(float(feature.range_chop_score), 4),
        "multi_timeframe_alignment": feature.multi_timeframe_alignment,
        "spread_state": feature.spread_state,
        "data_quality_status": feature.data_quality_status,
        "warnings": list(feature.warnings),
        "blockers": list(feature.blockers),
    }
    evidence = getattr(feature, "reasoning_evidence_v2", None)
    if evidence is not None:
        summary["reasoning_evidence_v2"] = evidence.compact_context()
    return summary


def _calendar_summary(context: CalendarContext) -> dict[str, Any]:
    next_event = context.next_high_impact_event
    recent_event = context.recent_high_impact_event
    return {
        "context_id": context.context_id,
        "provider_name": context.provider_name,
        "calendar_risk_state": context.calendar_risk_state,
        "cache_status": context.cache_status,
        "relevant_event_count": len(context.relevant_events),
        "next_high_impact_event": _event_summary(next_event),
        "minutes_to_next_high_impact_event": context.minutes_to_next_high_impact_event,
        "recent_high_impact_event": _event_summary(recent_event),
        "minutes_since_recent_high_impact_event": context.minutes_since_recent_high_impact_event,
        "warnings": list(context.warnings),
        "errors": list(context.errors),
    }


def _regime_summary(regime: MarketRegimeSnapshot) -> dict[str, Any]:
    return {
        "regime_snapshot_id": regime.regime_snapshot_id,
        "source_feature_snapshot_id": regime.source_feature_snapshot_id,
        "source_calendar_context_id": regime.source_calendar_context_id,
        "primary_regime": regime.primary_regime,
        "regime_version": regime.regime_version,
        "reasoning_regime": regime.reasoning_regime,
        "supporting_factors": list(regime.supporting_factors),
        "opposing_factors": list(regime.opposing_factors),
        "secondary_regimes": list(regime.secondary_regimes),
        "confidence": round(float(regime.confidence), 4),
        "trend_direction": regime.trend_direction,
        "volatility_state": regime.volatility_state,
        "momentum_state": regime.momentum_state,
        "range_chop_score": round(float(regime.range_chop_score), 4),
        "pullback_detected": bool(regime.pullback_detected),
        "breakout_candidate": bool(regime.breakout_candidate),
        "calendar_risk_state": regime.calendar_risk_state,
        "warnings": list(regime.warnings),
        "blockers": list(regime.blockers),
    }


def _event_summary(event: Any) -> dict[str, Any] | None:
    if not event:
        return None
    return {
        "event_id": event.event_id,
        "title": event.title,
        "currency": event.currency,
        "impact": event.impact,
        "event_time_utc": event.event_time_utc,
    }


def _method_summary(item: Any) -> dict[str, Any]:
    return {
        "method_id": item.method_id,
        "method_name": item.method_name,
        "source_type": item.source_type,
        "source_refs": list(item.source_refs),
        "domains": list(item.domains),
        "suitable_regimes": list(item.suitable_regimes),
        "bad_regimes": list(item.bad_regimes),
        "required_features": list(item.required_features),
        "confirmation_features": list(item.confirmation_features),
        "invalidation_features": list(item.invalidation_features),
        "preferred_timeframes": list(item.preferred_timeframes),
        "asset_scope": list(item.asset_scope),
        "risk_notes": list(item.risk_notes),
        "confidence": item.confidence,
    }


def _macro_summary(item: Any) -> dict[str, Any]:
    return {
        "macro_id": item.macro_id,
        "title": item.title,
        "source_type": item.source_type,
        "source_refs": list(item.source_refs),
        "event_type": item.event_type,
        "affected_assets": list(item.affected_assets),
        "affected_currencies": list(item.affected_currencies),
        "release_date": item.release_date,
        "freshness": item.freshness,
        "key_points": list(item.key_points),
        "gold_impact": item.gold_impact,
        "usd_impact": item.usd_impact,
        "uncertainty": item.uncertainty,
    }


def _playbook_summary(item: Any) -> dict[str, Any]:
    return {
        "playbook_id": item.playbook_id,
        "method_id": item.method_id,
        "name": item.name,
        "compatible_regimes": list(item.compatible_regimes),
        "required_market_features": list(item.required_market_features),
        "no_trade_conditions": list(item.no_trade_conditions),
        "confirmation_rules": list(item.confirmation_rules),
        "invalidation_rules": list(item.invalidation_rules),
        "preferred_timeframes": list(item.preferred_timeframes),
        "scoring_weights": dict(item.scoring_weights),
        "source_refs": list(item.source_refs),
    }


def _collect_source_refs(items: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in items:
        refs.extend(str(ref) for ref in item.get("source_refs", []) if ref)
    return refs


def _pack_id(mode: str, symbol: str, feature_id: str, regime_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{mode}|{symbol}|{feature_id}|{regime_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"runtime_context_pack_{digest}"
