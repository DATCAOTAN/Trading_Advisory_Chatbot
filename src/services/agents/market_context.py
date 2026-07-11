from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Protocol, Set

from src.services.agents.runtime import AgentResultEnvelope, AgentRuntimeContext, AgentStatus, AgentTaskEnvelope


class MarketContextVocabulary:
    DIRECTIONAL_BIAS = {"bullish_pressure", "bearish_pressure", "balanced", "unclear"}
    TREND_STATE = {"uptrend", "downtrend", "range", "transition", "unclear"}
    MOMENTUM_STATE = {"strengthening", "weakening", "mixed", "neutral", "unclear"}
    VOLATILITY_REGIME = {"expanding", "contracting", "elevated", "subdued", "mixed", "unclear"}
    STRUCTURE_STATE = {"breakout", "range", "pullback", "trend_continuation", "unclear"}
    SUPPORT_STRENGTH = {"strong", "adequate", "weak"}
    FACTOR_PRESSURE = {"bullish_pressure", "bearish_pressure", "neutral", "mixed", "unclear"}
    CONFIDENCE_CEILING = {"high": 0.85, "medium": 0.65, "low": 0.4}
    FACTOR_PRESSURE_FROM_DIRECTIONAL_BIAS = {
        "bullish_pressure": "bullish_pressure",
        "bearish_pressure": "bearish_pressure",
        "balanced": "neutral",
        "unclear": "unclear",
    }

    @classmethod
    def factor_pressure_from_directional_bias(cls, value: str) -> str:
        value = str(value or "")
        return cls.FACTOR_PRESSURE_FROM_DIRECTIONAL_BIAS.get(value, value)


DIRECTIONAL_BIAS = MarketContextVocabulary.DIRECTIONAL_BIAS
TREND_STATE = MarketContextVocabulary.TREND_STATE
MOMENTUM_STATE = MarketContextVocabulary.MOMENTUM_STATE
VOLATILITY_REGIME = MarketContextVocabulary.VOLATILITY_REGIME
STRUCTURE_STATE = MarketContextVocabulary.STRUCTURE_STATE
SUPPORT_STRENGTH = MarketContextVocabulary.SUPPORT_STRENGTH
PRESSURE_VALUES = MarketContextVocabulary.FACTOR_PRESSURE
CONFIDENCE_CEILING = MarketContextVocabulary.CONFIDENCE_CEILING


@dataclass
class MarketContextInput:
    request_id: str
    task_id: str
    parent_task_id: str
    intent_family: str
    symbol: str = ""
    as_of: str = ""
    temporal_scope: str = ""
    market_snapshot_ref: str = ""
    ohlcv_ref: str = ""
    technical_snapshot_ref: str = ""
    economic_event_refs: List[str] = field(default_factory=list)
    official_report_refs: List[str] = field(default_factory=list)
    market_knowledge_refs: List[str] = field(default_factory=list)
    decision_context_ref: str = "decision_context"
    task_context_ref: str = ""
    allowed_evidence_refs: List[str] = field(default_factory=list)
    allowed_source_refs: List[str] = field(default_factory=list)
    missing_context: List[str] = field(default_factory=list)
    confidence_ceiling: str = "high"
    market_snapshot: Dict[str, Any] = field(default_factory=dict)
    ohlcv_summary: Dict[str, Any] = field(default_factory=dict)
    technical_snapshot: Dict[str, Any] = field(default_factory=dict)
    economic_events: List[Dict[str, Any]] = field(default_factory=list)
    official_reports: List[Dict[str, Any]] = field(default_factory=list)
    market_knowledge: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "temporal_scope": self.temporal_scope,
            "market_snapshot_ref": self.market_snapshot_ref,
            "ohlcv_ref": self.ohlcv_ref,
            "technical_snapshot_ref": self.technical_snapshot_ref,
            "economic_event_refs": list(self.economic_event_refs),
            "official_report_refs": list(self.official_report_refs),
            "market_knowledge_refs": list(self.market_knowledge_refs),
            "decision_context_ref": self.decision_context_ref,
            "task_context_ref": self.task_context_ref,
            "allowed_evidence_refs": list(self.allowed_evidence_refs),
            "allowed_source_refs": list(self.allowed_source_refs),
            "temporal_scope": self.temporal_scope,
            "missing_context": list(self.missing_context),
            "confidence_ceiling": self.confidence_ceiling,
            "market_snapshot": dict(self.market_snapshot),
            "ohlcv_summary": dict(self.ohlcv_summary),
            "technical_snapshot": dict(self.technical_snapshot),
            "economic_events": [dict(item) for item in self.economic_events],
            "official_reports": [dict(item) for item in self.official_reports],
            "market_knowledge": [dict(item) for item in self.market_knowledge],
        }


@dataclass
class MarketContextAssessment:
    request_id: str
    task_id: str
    symbol: str
    as_of: str
    market_state: Dict[str, str] = field(default_factory=dict)
    macro_context: Dict[str, Any] = field(default_factory=dict)
    technical_context: Dict[str, Any] = field(default_factory=dict)
    dominant_factors: List[Dict[str, Any]] = field(default_factory=list)
    conflicting_signals: List[Dict[str, Any]] = field(default_factory=list)
    confirmation_conditions: Dict[str, str] = field(default_factory=dict)
    invalidation_conditions: List[str] = field(default_factory=list)
    uncertainty: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    assessment_ref: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "market_state": dict(self.market_state),
            "macro_context": dict(self.macro_context),
            "technical_context": dict(self.technical_context),
            "dominant_factors": [dict(item) for item in self.dominant_factors],
            "conflicting_signals": [dict(item) for item in self.conflicting_signals],
            "confirmation_conditions": dict(self.confirmation_conditions),
            "invalidation_conditions": list(self.invalidation_conditions),
            "uncertainty": dict(self.uncertainty),
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "assessment_ref": self.assessment_ref or f"market_context_assessment:{self.task_id}",
        }


class MarketContextReasoningBackend(Protocol):
    def produce(self, market_input: MarketContextInput) -> MarketContextAssessment | Dict[str, Any]:
        ...


class MarketContextInputAssembler:
    @classmethod
    def assemble(cls, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> MarketContextInput:
        decision_context = context.decision_context_ref
        query_plan = getattr(decision_context, "query_plan", None) or context.query_plan_ref or {}
        parent_task_id = task.parent_task_id or str(query_plan.get("task_id") or "task_1")
        task_view = cls._task_view(context, parent_task_id)
        source_refs = list(task.source_refs or task.metadata.get("allowed_source_refs", []) or [])
        result_map = cls._scoped_results(context, parent_task_id, source_refs)
        market_snapshot_ref = cls._first_ref(result_map, "market_snapshot")
        ohlcv_ref = cls._first_ref(result_map, "ohlcv")
        technical_snapshot_ref = cls._first_ref(result_map, "technical_snapshot")
        market_snapshot = cls._data(result_map.get(market_snapshot_ref)) if market_snapshot_ref else {}
        ohlcv_summary = cls._data(result_map.get(ohlcv_ref)) if ohlcv_ref else {}
        technical_snapshot = cls._data(result_map.get(technical_snapshot_ref)) if technical_snapshot_ref else {}
        symbol = cls._symbol(task, query_plan, market_snapshot)
        as_of = cls._as_of(result_map, market_snapshot)
        missing_context = cls._missing_context(decision_context, task_view, result_map, task.intent_family)
        confidence_ceiling = cls._confidence_ceiling(decision_context, task_view)
        economic_refs = cls._refs_for(result_map, "economic_event")
        official_refs = cls._refs_for(result_map, "official_report")
        knowledge_refs = cls._refs_for(result_map, "market_knowledge")
        assembled = MarketContextInput(
            request_id=str(getattr(decision_context, "request_id", "") or "agent_request"),
            task_id=task.task_id,
            parent_task_id=parent_task_id,
            intent_family=task.intent_family,
            symbol=symbol,
            as_of=as_of,
            temporal_scope=str(query_plan.get("temporal_scope") or ""),
            market_snapshot_ref=market_snapshot_ref,
            ohlcv_ref=ohlcv_ref,
            technical_snapshot_ref=technical_snapshot_ref,
            economic_event_refs=economic_refs,
            official_report_refs=official_refs,
            market_knowledge_refs=knowledge_refs,
            task_context_ref=f"task_context:{parent_task_id}",
            allowed_evidence_refs=list(task.evidence_refs or []),
            allowed_source_refs=source_refs,
            missing_context=missing_context,
            confidence_ceiling=confidence_ceiling,
            market_snapshot=market_snapshot,
            ohlcv_summary=ohlcv_summary,
            technical_snapshot=technical_snapshot,
            economic_events=[cls._data(result_map[ref]) for ref in economic_refs],
            official_reports=[cls._data(result_map[ref]) for ref in official_refs],
            market_knowledge=[cls._data(result_map[ref]) for ref in knowledge_refs],
        )
        print(
            "[MarketContextInput] "
            f"task_id={assembled.task_id} symbol={assembled.symbol} "
            f"temporal_scope={assembled.temporal_scope} "
            f"available_context={list(result_map)} "
            f"missing_context={assembled.missing_context} "
            f"allowed_evidence_refs={assembled.allowed_evidence_refs} "
            f"confidence_ceiling={assembled.confidence_ceiling}"
        )
        return assembled

    @staticmethod
    def _task_view(context: AgentRuntimeContext, task_id: str) -> Dict[str, Any]:
        item = (context.task_context_refs or {}).get(task_id)
        return dict(item) if isinstance(item, dict) else {}

    @staticmethod
    def _scoped_results(context: AgentRuntimeContext, parent_task_id: str, source_refs: List[str]) -> Dict[str, Dict[str, Any]]:
        scoped: Dict[str, Dict[str, Any]] = {}
        allowed = set(source_refs or [])
        for result_id, result in (context.acquisition_result_refs or {}).items():
            if not isinstance(result, dict):
                continue
            rid = str(result.get("result_id") or result_id)
            if allowed and rid not in allowed:
                continue
            owners = set(result.get("requested_by_tasks") or result.get("task_ids") or [])
            if owners and parent_task_id and parent_task_id not in owners:
                continue
            if str(result.get("status") or "").lower() not in {"success", "reused"}:
                continue
            scoped[rid] = result
        return scoped

    @staticmethod
    def _first_ref(result_map: Dict[str, Dict[str, Any]], capability: str) -> str:
        for ref, result in result_map.items():
            if result.get("capability") == capability:
                return ref
        return ""

    @staticmethod
    def _refs_for(result_map: Dict[str, Dict[str, Any]], capability: str) -> List[str]:
        return [ref for ref, result in result_map.items() if result.get("capability") == capability]

    @staticmethod
    def _data(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = (result or {}).get("data")
        if isinstance(data, dict):
            return dict(data)
        return {}

    @staticmethod
    def _symbol(task: AgentTaskEnvelope, query_plan: Dict[str, Any], market_snapshot: Dict[str, Any]) -> str:
        if market_snapshot.get("symbol"):
            return str(market_snapshot.get("symbol"))
        entities = query_plan.get("entities") or {}
        symbols = entities.get("symbols") if isinstance(entities, dict) else []
        if symbols:
            return str(symbols[0])
        for ref in task.source_refs:
            if ":" in ref:
                return ref.split(":", 1)[1]
        return ""

    @staticmethod
    def _as_of(result_map: Dict[str, Dict[str, Any]], market_snapshot: Dict[str, Any]) -> str:
        if market_snapshot.get("timestamp"):
            return str(market_snapshot.get("timestamp"))
        for result in result_map.values():
            ts = result.get("source_timestamp") or result.get("fetched_at") or result.get("created_at")
            if ts:
                return str(ts)
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _missing_context(decision_context: Any, task_view: Dict[str, Any], result_map: Dict[str, Dict[str, Any]], intent_family: str) -> List[str]:
        missing = list(getattr(decision_context, "missing_required_context", []) or [])
        missing.extend(getattr(decision_context, "missing_optional_context", []) or [])
        missing.extend(task_view.get("missing_required_context", []) or [])
        missing.extend(task_view.get("missing_optional_context", []) or [])
        if intent_family == "market_state_analysis" and not any(result.get("capability") == "market_snapshot" for result in result_map.values()):
            missing.append("market_snapshot")
        return _ordered_unique(str(item) for item in missing)

    @staticmethod
    def _confidence_ceiling(decision_context: Any, task_view: Dict[str, Any]) -> str:
        value = task_view.get("confidence_ceiling") or getattr(decision_context, "confidence_ceiling", "")
        if not value and isinstance(getattr(decision_context, "sufficiency", None), dict):
            value = decision_context.sufficiency.get("confidence_ceiling")
        value = str(value or "high").lower()
        return value if value in CONFIDENCE_CEILING else "high"


class DeterministicMarketContextReasoningBackend:
    def produce(self, market_input: MarketContextInput) -> MarketContextAssessment:
        trend_state = self._trend_state(market_input)
        momentum_state = self._momentum_state(market_input, trend_state)
        volatility = self._volatility_regime(market_input)
        directional_bias = self._directional_bias(trend_state, momentum_state, market_input)
        structure_state = self._structure_state(trend_state, market_input)
        source_refs = self._used_source_refs(market_input)
        evidence_refs = list(market_input.allowed_evidence_refs)
        conflicts = self._conflicts(trend_state, momentum_state, market_input, evidence_refs)
        dominant = self._dominant_factors(market_input, trend_state, momentum_state, volatility, directional_bias, evidence_refs, source_refs)
        confidence = self._confidence(market_input, conflicts, dominant)
        market_state = {
            "directional_bias": directional_bias,
            "trend_state": trend_state,
            "momentum_state": momentum_state,
            "volatility_regime": volatility,
            "structure_state": structure_state,
        }
        assessment = MarketContextAssessment(
            request_id=market_input.request_id,
            task_id=market_input.task_id,
            symbol=market_input.symbol,
            as_of=market_input.as_of,
            market_state=market_state,
            macro_context=self._macro_context(market_input),
            technical_context=self._technical_context(market_input),
            dominant_factors=dominant,
            conflicting_signals=conflicts,
            confirmation_conditions=self._confirmation_conditions(market_input.symbol),
            invalidation_conditions=[
                "assessment weakens if new approved market context contradicts the current trend or momentum state",
                "assessment weakens if macro-event context changes after the recorded as_of time",
            ],
            uncertainty={
                "confidence": confidence,
                "confidence_ceiling": market_input.confidence_ceiling,
                "missing_context": list(market_input.missing_context),
                "conflicting_context": [item.get("explanation", "") for item in conflicts],
                "assumptions": ["assessment uses only approved structured context already acquired"],
                "limitations": self._limitations(market_input),
            },
            summary=self._summary(market_input.symbol, directional_bias, trend_state, momentum_state, volatility),
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            assessment_ref=f"market_context_assessment:{market_input.task_id}",
        )
        return assessment

    @staticmethod
    def _trend_state(market_input: MarketContextInput) -> str:
        trend = str(market_input.technical_snapshot.get("trend") or market_input.market_snapshot.get("recent_trend") or "").lower()
        if "up" in trend or "bull" in trend:
            return "uptrend"
        if "down" in trend or "bear" in trend:
            return "downtrend"
        if "range" in trend or "flat" in trend or "sideway" in trend:
            return "range"
        first_close = _safe_float(market_input.ohlcv_summary.get("first_close"))
        last_close = _safe_float(market_input.ohlcv_summary.get("last_close"))
        if first_close is not None and last_close is not None:
            if last_close > first_close:
                return "uptrend"
            if last_close < first_close:
                return "downtrend"
            return "range"
        return "unclear"

    @staticmethod
    def _momentum_state(market_input: MarketContextInput, trend_state: str) -> str:
        raw = str(market_input.technical_snapshot.get("momentum") or market_input.technical_snapshot.get("momentum_state") or "").lower()
        if "mix" in raw:
            return "mixed"
        if "strength" in raw or "bull" in raw or "positive" in raw:
            return "strengthening" if trend_state != "downtrend" else "mixed"
        if "weak" in raw or "bear" in raw or "negative" in raw:
            return "weakening" if trend_state != "uptrend" else "mixed"
        return "neutral" if trend_state in {"uptrend", "downtrend", "range"} else "unclear"

    @staticmethod
    def _volatility_regime(market_input: MarketContextInput) -> str:
        raw = str(market_input.technical_snapshot.get("volatility") or market_input.market_snapshot.get("volatility_note") or "").lower()
        if "elevated" in raw or "high" in raw:
            return "elevated"
        if "expand" in raw:
            return "expanding"
        if "contract" in raw:
            return "contracting"
        if "subdued" in raw or "low" in raw:
            return "subdued"
        pct = None
        if "avg_range_pct=" in raw:
            pct = _safe_float(raw.split("avg_range_pct=", 1)[1].split()[0])
        if pct is not None:
            if pct >= 1.0:
                return "elevated"
            if pct <= 0.25:
                return "subdued"
            return "mixed"
        return "unclear"

    @staticmethod
    def _directional_bias(trend_state: str, momentum_state: str, market_input: MarketContextInput) -> str:
        if trend_state == "uptrend" and momentum_state != "weakening":
            return "bullish_pressure"
        if trend_state == "downtrend" and momentum_state != "strengthening":
            return "bearish_pressure"
        if trend_state == "range":
            return "balanced"
        if market_input.economic_events or market_input.official_reports:
            return "balanced" if trend_state == "unclear" else "unclear"
        return "unclear"

    @staticmethod
    def _structure_state(trend_state: str, market_input: MarketContextInput) -> str:
        sr = market_input.market_snapshot.get("support_resistance") or {}
        if trend_state in {"uptrend", "downtrend"}:
            return "trend_continuation"
        if sr.get("recent_support") and sr.get("recent_resistance"):
            return "range"
        return "unclear"

    @staticmethod
    def _macro_context(market_input: MarketContextInput) -> Dict[str, Any]:
        active = [event.get("event_name", "") for event in market_input.economic_events if event.get("event_name")]
        return {
            "active_events": active,
            "inflation_context": _contains_any(active + [str(item) for item in market_input.official_reports], ["cpi", "inflation"]),
            "rates_context": _contains_any(active + [str(item) for item in market_input.official_reports], ["fed", "rate", "fomc"]),
            "usd_context": _contains_any(active + [str(item) for item in market_input.economic_events], ["usd", "us "]),
            "macro_pressure": "present" if active or market_input.official_reports else "not_available",
        }

    @staticmethod
    def _technical_context(market_input: MarketContextInput) -> Dict[str, Any]:
        return {
            "trend_signals": _compact_value(market_input.technical_snapshot.get("trend") or market_input.market_snapshot.get("recent_trend")),
            "momentum_signals": _compact_value(market_input.technical_snapshot.get("momentum")),
            "volatility_signals": _compact_value(market_input.technical_snapshot.get("volatility") or market_input.market_snapshot.get("volatility_note")),
            "structural_conditions": market_input.market_snapshot.get("support_resistance") or {},
        }

    @staticmethod
    def _dominant_factors(
        market_input: MarketContextInput,
        trend_state: str,
        momentum_state: str,
        volatility: str,
        directional_bias: str,
        evidence_refs: List[str],
        source_refs: List[str],
    ) -> List[Dict[str, Any]]:
        factors: List[Dict[str, Any]] = []
        factor_pressure = MarketContextVocabulary.factor_pressure_from_directional_bias(directional_bias)
        if market_input.market_snapshot_ref or market_input.ohlcv_ref:
            factors.append({
                "factor": "recent price behavior",
                "category": "market",
                "directional_pressure": factor_pressure,
                "support_strength": "strong" if market_input.ohlcv_ref else "adequate",
                "confidence": 0.7 if market_input.ohlcv_ref else 0.55,
                "evidence_refs": list(evidence_refs),
                "source_refs": [ref for ref in [market_input.market_snapshot_ref, market_input.ohlcv_ref] if ref],
            })
        if market_input.technical_snapshot_ref:
            factors.append({
                "factor": f"technical state: {trend_state}/{momentum_state}/{volatility}",
                "category": "technical",
                "directional_pressure": factor_pressure,
                "support_strength": "adequate",
                "confidence": 0.6,
                "evidence_refs": list(evidence_refs),
                "source_refs": [market_input.technical_snapshot_ref],
            })
        if market_input.economic_event_refs or market_input.official_report_refs:
            factors.append({
                "factor": "macro event context",
                "category": "macro",
                "directional_pressure": "mixed" if market_input.market_snapshot_ref else "unclear",
                "support_strength": "adequate",
                "confidence": 0.55,
                "evidence_refs": list(evidence_refs),
                "source_refs": market_input.economic_event_refs + market_input.official_report_refs,
            })
        if not factors and source_refs:
            factors.append({
                "factor": "limited approved context",
                "category": "context",
                "directional_pressure": "unclear",
                "support_strength": "weak",
                "confidence": 0.3,
                "evidence_refs": list(evidence_refs),
                "source_refs": list(source_refs),
            })
        return factors

    @staticmethod
    def _conflicts(trend_state: str, momentum_state: str, market_input: MarketContextInput, evidence_refs: List[str]) -> List[Dict[str, Any]]:
        conflicts = []
        if trend_state == "uptrend" and momentum_state == "weakening":
            conflicts.append({
                "signal_a": "uptrend",
                "signal_b": "weakening momentum",
                "explanation": "recent trend and momentum do not fully agree",
                "evidence_refs": list(evidence_refs),
            })
        if trend_state == "downtrend" and momentum_state == "strengthening":
            conflicts.append({
                "signal_a": "downtrend",
                "signal_b": "strengthening momentum",
                "explanation": "recent trend and momentum do not fully agree",
                "evidence_refs": list(evidence_refs),
            })
        if trend_state in {"uptrend", "downtrend"} and momentum_state == "mixed":
            conflicts.append({
                "signal_a": trend_state,
                "signal_b": "mixed momentum",
                "explanation": "directional trend exists but momentum context is mixed",
                "evidence_refs": list(evidence_refs),
            })
        if market_input.economic_events and trend_state == "unclear":
            conflicts.append({
                "signal_a": "macro event context present",
                "signal_b": "unclear current market trend",
                "explanation": "macro context is present but current price behavior is not directional",
                "evidence_refs": list(evidence_refs),
            })
        return conflicts

    @staticmethod
    def _confirmation_conditions(symbol: str) -> Dict[str, str]:
        label = symbol or "the market"
        return {
            "bullish_confirmation": f"{label} shows continued higher closes with supportive momentum in approved future context",
            "bearish_confirmation": f"{label} shows continued lower closes with weakening momentum in approved future context",
            "neutral_or_range_confirmation": f"{label} remains between recently observed support and resistance with mixed momentum",
        }

    @staticmethod
    def _limitations(market_input: MarketContextInput) -> List[str]:
        limitations = list(market_input.missing_context)
        if not market_input.as_of:
            limitations.append("as_of timestamp unavailable")
        if not market_input.technical_snapshot_ref:
            limitations.append("technical snapshot unavailable")
        if not market_input.economic_event_refs and market_input.intent_family == "macro_market_impact":
            limitations.append("economic event context unavailable")
        return _ordered_unique(limitations)

    @staticmethod
    def _confidence(market_input: MarketContextInput, conflicts: List[Dict[str, Any]], dominant: List[Dict[str, Any]]) -> float:
        ceiling = CONFIDENCE_CEILING.get(market_input.confidence_ceiling, 0.85)
        score = ceiling
        if market_input.missing_context:
            score -= 0.15
        if conflicts:
            score -= 0.1
        if not dominant:
            score -= 0.25
        return round(max(0.1, min(score, ceiling)), 2)

    @staticmethod
    def _used_source_refs(market_input: MarketContextInput) -> List[str]:
        refs = [
            market_input.market_snapshot_ref,
            market_input.ohlcv_ref,
            market_input.technical_snapshot_ref,
            *market_input.economic_event_refs,
            *market_input.official_report_refs,
            *market_input.market_knowledge_refs,
        ]
        return _ordered_unique(ref for ref in refs if ref)

    @staticmethod
    def _summary(symbol: str, directional_bias: str, trend_state: str, momentum_state: str, volatility: str) -> str:
        label = symbol or "market"
        return (
            f"{label} context is {directional_bias} with trend={trend_state}, "
            f"momentum={momentum_state}, volatility={volatility}. "
            "This is contextual analysis only, not a trade recommendation."
        )


class MarketContextAssessmentValidator:
    @classmethod
    def validate(cls, assessment: MarketContextAssessment, market_input: MarketContextInput) -> List[str]:
        reasons: List[str] = []
        state = assessment.market_state or {}
        if state.get("directional_bias") not in DIRECTIONAL_BIAS:
            reasons.append("invalid_directional_bias")
        if state.get("trend_state") not in TREND_STATE:
            reasons.append("invalid_trend_state")
        if state.get("momentum_state") not in MOMENTUM_STATE:
            reasons.append("invalid_momentum_state")
        if state.get("volatility_regime") not in VOLATILITY_REGIME:
            reasons.append("invalid_volatility_regime")
        if state.get("structure_state") not in STRUCTURE_STATE:
            reasons.append("invalid_structure_state")
        uncertainty = assessment.uncertainty or {}
        if not 0.0 <= float(uncertainty.get("confidence", 0.0) or 0.0) <= 1.0:
            reasons.append("confidence_out_of_bounds")
        ceiling = CONFIDENCE_CEILING.get(market_input.confidence_ceiling, 0.85)
        confidence = _safe_float(uncertainty.get("confidence")) or 0.0
        if confidence > ceiling:
            reasons.append("confidence_above_ceiling")
        if set(assessment.evidence_refs or []) - set(market_input.allowed_evidence_refs or []):
            reasons.append("evidence_ref_out_of_scope")
        if set(assessment.source_refs or []) - set(market_input.allowed_source_refs or []):
            reasons.append("source_ref_out_of_scope")
        for factor in assessment.dominant_factors or []:
            if factor.get("support_strength") not in SUPPORT_STRENGTH:
                reasons.append("invalid_support_strength")
            if factor.get("directional_pressure") not in PRESSURE_VALUES:
                reasons.append("invalid_factor_pressure")
        text = f"{assessment.summary} {assessment.as_dict()}".lower()
        if any(token in text for token in [" buy ", " sell ", " stop-loss", "take-profit", "lot size", "place_order", "execute_trade"]):
            reasons.append("trading_instruction_not_allowed")
        if not assessment.task_id or assessment.task_id != market_input.task_id:
            reasons.append("task_id_mismatch")
        print(
            "[MarketContextValidation] "
            f"task_id={market_input.task_id} status={'FAIL' if reasons else 'PASS'} "
            f"reason_codes={reasons}"
        )
        return _ordered_unique(reasons)


class MarketContextAgentRuntime:
    agent_type = "MarketContextAgent"

    def __init__(self, backend: Optional[MarketContextReasoningBackend] = None):
        self.backend = backend or DeterministicMarketContextReasoningBackend()

    def execute(self, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> AgentResultEnvelope:
        print(f"[MarketContextAgent] task_id={task.task_id} status=start")
        market_input = MarketContextInputAssembler.assemble(task, context)
        if not market_input.allowed_source_refs:
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=task.agent_type,
                status=AgentStatus.PARTIAL,
                result_type="market_context_assessment",
                confidence=0.1,
                failure_code="AGENT_PARTIAL",
                failure_reason="no approved task-scoped context refs available",
                limitations=["no approved structured market context available"],
            )
        try:
            produced = self.backend.produce(market_input)
            assessment = self._coerce_assessment(produced)
        except Exception as exc:
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=task.agent_type,
                status=AgentStatus.INVALID_RESULT,
                result_type="market_context_assessment",
                confidence=0.0,
                failure_code="AGENT_RESULT_INVALID",
                failure_reason=f"assessment_parse_failed:{exc}",
            )
        reasons = MarketContextAssessmentValidator.validate(assessment, market_input)
        if reasons:
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=task.agent_type,
                status=AgentStatus.INVALID_RESULT,
                result_type="market_context_assessment",
                structured_payload={"market_context_input": market_input.as_dict()},
                confidence=0.0,
                failure_code="AGENT_RESULT_INVALID",
                failure_reason=",".join(reasons),
            )
        payload = assessment.as_dict()
        payload["market_context_input"] = market_input.as_dict()
        confidence = float((assessment.uncertainty or {}).get("confidence") or 0.0)
        status = AgentStatus.SUCCESS if confidence >= 0.45 else AgentStatus.PARTIAL
        print(
            "[MarketContextAssessment] "
            f"task_id={assessment.task_id} "
            f"directional_bias={assessment.market_state.get('directional_bias')} "
            f"trend_state={assessment.market_state.get('trend_state')} "
            f"momentum_state={assessment.market_state.get('momentum_state')} "
            f"volatility_regime={assessment.market_state.get('volatility_regime')} "
            f"dominant_factors={len(assessment.dominant_factors)} "
            f"conflicts={len(assessment.conflicting_signals)} "
            f"confidence={confidence} "
            f"limitations={assessment.uncertainty.get('limitations', [])}"
        )
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=status,
            result_type="market_context_assessment",
            structured_payload=payload,
            summary=assessment.summary,
            evidence_refs=list(assessment.evidence_refs),
            source_refs=list(assessment.source_refs),
            confidence=confidence,
            assumptions=list((assessment.uncertainty or {}).get("assumptions", [])),
            limitations=list((assessment.uncertainty or {}).get("limitations", [])),
            warnings=list((assessment.uncertainty or {}).get("conflicting_context", [])),
            failure_code="AGENT_PARTIAL" if status == AgentStatus.PARTIAL else "",
            failure_reason="low confidence assessment" if status == AgentStatus.PARTIAL else "",
            metadata={"assessment_ref": assessment.assessment_ref or f"market_context_assessment:{task.task_id}"},
        )

    @staticmethod
    def _coerce_assessment(value: MarketContextAssessment | Dict[str, Any]) -> MarketContextAssessment:
        if isinstance(value, MarketContextAssessment):
            return value
        if not isinstance(value, dict):
            raise TypeError("assessment must be dict or MarketContextAssessment")
        return MarketContextAssessment(**value)


def _contains_any(values: Iterable[str], needles: Iterable[str]) -> bool:
    haystack = " ".join(str(value or "").lower() for value in values)
    return any(needle in haystack for needle in needles)


def _compact_value(value: Any) -> str:
    text = str(value or "").strip()
    return text[:200]


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip("%, "))
    except (TypeError, ValueError):
        return None


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
