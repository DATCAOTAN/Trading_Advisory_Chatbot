import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.knowledge.answer_mode import AnswerMode, AnswerModeClassifier
from src.services.knowledge.query_decomposer import QueryDecomposer
from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter
from src.services.semantic.capability_registry import CapabilityRegistry
from src.services.semantic.context_execution import (
    ContextAcquisitionResult,
    ContextExecutionPlan,
    ContextExecutionPlanner,
)
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements, ContextRequirementPlanner
from src.services.semantic.context_sufficiency import ContextSufficiencyGate, ContextSufficiencyResult
from src.services.semantic.query_plan import QueryPlan, QueryPlanAssembler


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        import sys

        encoding = sys.stdout.encoding or "utf-8"
        safe_message = str(message).encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(safe_message)


@dataclass
class MarketSnapshot:
    symbol: str = ""
    timeframe: str = ""
    latest_price: Optional[float] = None
    ohlcv_summary: Dict[str, Any] = field(default_factory=dict)
    recent_trend: str = ""
    volatility_note: str = ""
    support_resistance: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: str = ""
    raw_price_output: str = ""


@dataclass
class EconomicEventContext:
    event_name: str = ""
    country: str = ""
    importance: str = ""
    release_time: str = ""
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    surprise: Optional[str] = None
    status: str = ""
    source: str = "existing_api"


@dataclass
class RetrievedKnowledgeContext:
    primary_sources: List[str] = field(default_factory=list)
    supporting_sources: List[str] = field(default_factory=list)
    source_coverage_score: float = 0.0
    grounding_warnings: List[str] = field(default_factory=list)


@dataclass
class RiskSnapshot:
    account_balance: Optional[float] = None
    max_risk_per_trade: Optional[float] = None
    open_positions: List[Dict[str, Any]] = field(default_factory=list)
    exposure: Optional[float] = None
    drawdown: Optional[float] = None
    trading_allowed: Optional[bool] = None


@dataclass
class DecisionContext:
    request_id: str
    user_query: str
    normalized_query: str
    query_intent: Dict[str, Any]
    answer_mode: Dict[str, Any]
    symbols: List[str] = field(default_factory=list)
    timeframe: str = ""
    market_data_required: bool = False
    static_knowledge_required: bool = False
    economic_calendar_required: bool = False
    news_required: bool = False
    risk_context_required: bool = False
    technical_snapshot_required: bool = False
    execution_gate_required: bool = False
    retrieved_sources: RetrievedKnowledgeContext = field(default_factory=RetrievedKnowledgeContext)
    market_snapshot: Optional[MarketSnapshot] = None
    economic_events: List[EconomicEventContext] = field(default_factory=list)
    macro_snapshot: Optional[Dict[str, Any]] = None
    technical_snapshot: Optional[Dict[str, Any]] = None
    risk_snapshot: Optional[RiskSnapshot] = None
    missing_context: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    context_freshness: Dict[str, Any] = field(default_factory=dict)
    query_plan: Optional[Dict[str, Any]] = None
    requirements: Optional[Dict[str, Any]] = None
    execution_plan: Optional[Dict[str, Any]] = None
    acquisition_results: List[Dict[str, Any]] = field(default_factory=list)
    acquisition_mode: str = "legacy_heuristic"
    task_context_views: List[Dict[str, Any]] = field(default_factory=list)
    evidence_bundles: List[Dict[str, Any]] = field(default_factory=list)
    evidence_sufficiency: Optional[Dict[str, Any]] = None
    answer_contracts: List[Dict[str, Any]] = field(default_factory=list)
    claim_validation: Optional[Dict[str, Any]] = None
    sufficiency: Optional[Dict[str, Any]] = None
    missing_required_context: List[str] = field(default_factory=list)
    missing_optional_context: List[str] = field(default_factory=list)
    freshness_map: Dict[str, Any] = field(default_factory=dict)
    provenance_map: Dict[str, Any] = field(default_factory=dict)
    completeness_score: float = 0.0
    confidence_ceiling: str = "low"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_query": self.user_query,
            "normalized_query": self.normalized_query,
            "query_intent": dict(self.query_intent),
            "answer_mode": dict(self.answer_mode),
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "market_data_required": self.market_data_required,
            "static_knowledge_required": self.static_knowledge_required,
            "economic_calendar_required": self.economic_calendar_required,
            "news_required": self.news_required,
            "risk_context_required": self.risk_context_required,
            "technical_snapshot_required": self.technical_snapshot_required,
            "execution_gate_required": self.execution_gate_required,
            "retrieved_sources": self.retrieved_sources.__dict__,
            "market_snapshot": self.market_snapshot.__dict__ if self.market_snapshot else None,
            "economic_events": [event.__dict__ for event in self.economic_events],
            "macro_snapshot": self.macro_snapshot,
            "technical_snapshot": self.technical_snapshot,
            "risk_snapshot": self.risk_snapshot.__dict__ if self.risk_snapshot else None,
            "missing_context": list(self.missing_context),
            "warnings": list(self.warnings),
            "context_freshness": dict(self.context_freshness),
            "query_plan": self.query_plan,
            "requirements": self.requirements,
            "execution_plan": self.execution_plan,
            "acquisition_results": list(self.acquisition_results),
            "acquisition_mode": self.acquisition_mode,
            "task_context_views": list(self.task_context_views),
            "evidence_bundles": list(self.evidence_bundles),
            "evidence_sufficiency": self.evidence_sufficiency,
            "answer_contracts": list(self.answer_contracts),
            "claim_validation": self.claim_validation,
            "sufficiency": self.sufficiency,
            "missing_required_context": list(self.missing_required_context),
            "missing_optional_context": list(self.missing_optional_context),
            "freshness_map": dict(self.freshness_map),
            "provenance_map": dict(self.provenance_map),
            "completeness_score": self.completeness_score,
            "confidence_ceiling": self.confidence_ceiling,
            "created_at": self.created_at,
        }


class ExistingMarketDataAdapter:
    """Thin wrapper around the existing LiveDataService market/candle methods."""

    def __init__(self, live_service: Any):
        self.live_service = live_service

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        indicators: Optional[List[Dict[str, Any]]] = None,
        live_price_output: Optional[str] = None,
        candles_output: Optional[List[Dict[str, Any]]] = None,
    ) -> MarketSnapshot:
        price_output = live_price_output
        if price_output is None:
            price_output = self.live_service.get_live_price(symbol)

        candles = candles_output
        if candles is None:
            candles = self.live_service.get_historical_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                indicators=indicators,
            )

        return self._normalize_snapshot(symbol, timeframe, str(price_output or ""), candles or [])

    def _normalize_snapshot(self, symbol: str, timeframe: str, price_output: str, candles: List[Dict[str, Any]]) -> MarketSnapshot:
        latest_price = self._extract_price(price_output)
        if latest_price is None and candles:
            latest_price = self._safe_float(candles[-1].get("close"))

        closes = [self._safe_float(item.get("close")) for item in candles if self._safe_float(item.get("close")) is not None]
        highs = [self._safe_float(item.get("high")) for item in candles if self._safe_float(item.get("high")) is not None]
        lows = [self._safe_float(item.get("low")) for item in candles if self._safe_float(item.get("low")) is not None]
        recent_trend = ""
        if len(closes) >= 2:
            if closes[-1] > closes[0]:
                recent_trend = "up"
            elif closes[-1] < closes[0]:
                recent_trend = "down"
            else:
                recent_trend = "flat"

        volatility_note = ""
        if highs and lows and closes:
            avg_range = sum(high - low for high, low in zip(highs, lows)) / max(len(highs), 1)
            last_close = closes[-1] or 1
            pct_range = abs(avg_range / last_close) * 100
            volatility_note = f"avg_range_pct={pct_range:.2f}"

        source = self._extract_source(price_output)
        timestamp = str(candles[-1].get("timestamp", "")) if candles else datetime.now(timezone.utc).isoformat()
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            latest_price=latest_price,
            ohlcv_summary={
                "candles": len(candles),
                "first_close": closes[0] if closes else None,
                "last_close": closes[-1] if closes else None,
            },
            recent_trend=recent_trend,
            volatility_note=volatility_note,
            support_resistance={
                "recent_support": min(lows) if lows else None,
                "recent_resistance": max(highs) if highs else None,
            },
            source=source or "existing_api",
            timestamp=timestamp,
            raw_price_output=price_output,
        )

    @staticmethod
    def _extract_price(value: str) -> Optional[float]:
        matches = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", value or "")
        for match in matches:
            try:
                return float(match.replace(",", ""))
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_source(value: str) -> str:
        match = re.search(r"Ngu[ồo]n:\s*([^*\\n]+)", value or "", flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class ExistingEconomicCalendarAdapter:
    """Thin wrapper around the existing LiveDataService economic calendar method."""

    def __init__(self, live_service: Any):
        self.live_service = live_service

    def get_events(self, calendar_output: Optional[str] = None) -> List[EconomicEventContext]:
        output = calendar_output
        if output is None:
            output = self.live_service.get_economic_calendar()
        return self._parse_calendar_text(str(output or ""))

    @staticmethod
    def _parse_calendar_text(text: str) -> List[EconomicEventContext]:
        events: List[EconomicEventContext] = []
        for line in text.splitlines():
            if "|" not in line:
                simple = ExistingEconomicCalendarAdapter._parse_simple_calendar_line(line)
                if simple:
                    events.append(simple)
                continue
            parts = [part.strip(" -*\t") for part in line.split("|")]
            if len(parts) < 3:
                continue
            release_time = re.sub(r"^[^\d]*(?=\d)", "", parts[0]).strip()
            country = parts[1].strip()
            impact_match = re.search(r"\[([^\]]+)\]\s*(.*)", parts[2])
            if impact_match:
                importance = impact_match.group(1).strip()
                event_name = impact_match.group(2).strip()
            else:
                importance = ""
                event_name = parts[2].strip()
            events.append(
                EconomicEventContext(
                    event_name=event_name,
                    country=country,
                    importance=importance,
                    release_time=release_time,
                    status="scheduled",
                    source="existing_api",
                )
            )
        return events

    @staticmethod
    def _parse_simple_calendar_line(line: str) -> Optional[EconomicEventContext]:
        text = str(line or "").strip()
        if not text:
            return None
        normalized = AnswerModeClassifier.normalize(text)
        event_name = ""
        if "cpi" in normalized or "consumer price" in normalized:
            event_name = "US CPI"
        elif "nfp" in normalized or "nonfarm" in normalized or "payroll" in normalized:
            event_name = "US NFP"
        elif "gdp" in normalized:
            event_name = "US GDP"
        elif "fomc" in normalized or "fed" in normalized:
            event_name = "FOMC"
        if not event_name:
            return None

        def extract(label: str) -> Optional[str]:
            match = re.search(label + r"\s*[:=]\s*([^\s,;|]+)", text, flags=re.IGNORECASE)
            return match.group(1) if match else None

        return EconomicEventContext(
            event_name=event_name,
            country="USD" if event_name.startswith(("US", "FOMC")) else "",
            importance="High",
            release_time="",
            actual=extract("actual"),
            forecast=extract("forecast"),
            previous=extract("previous"),
            status="available",
            source="existing_api",
        )


class ExistingMacroDataAdapter:
    """Thin wrapper around the existing LiveDataService macro report method."""

    def __init__(self, live_service: Any):
        self.live_service = live_service

    def get_snapshot(self, macro_output: Optional[str] = None) -> Dict[str, Any]:
        output = macro_output
        if output is None:
            output = self.live_service.get_latest_macro_report()
        text = str(output or "").strip()
        return {
            "source": "existing_api",
            "summary": text,
            "available": bool(text),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class ExistingTechnicalSnapshotAdapter:
    """Normalize indicator-enriched candle output already returned by LiveDataService."""

    INDICATOR_PREFIXES = ("ema_", "sma_", "rsi_", "macd")

    def build(self, market_snapshot: Optional[MarketSnapshot], candles: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        if not market_snapshot and not candles:
            return None
        latest = (candles or [])[-1] if candles else {}
        indicators = {
            key: value
            for key, value in latest.items()
            if any(str(key).lower().startswith(prefix) for prefix in self.INDICATOR_PREFIXES)
        }
        return {
            "trend": market_snapshot.recent_trend if market_snapshot else "",
            "support_resistance": market_snapshot.support_resistance if market_snapshot else {},
            "indicators": indicators,
            "source": "existing_api",
        }


class DecisionContextBuilder:
    def __init__(
        self,
        market_adapter: Optional[ExistingMarketDataAdapter] = None,
        calendar_adapter: Optional[ExistingEconomicCalendarAdapter] = None,
        macro_adapter: Optional[ExistingMacroDataAdapter] = None,
        technical_adapter: Optional[ExistingTechnicalSnapshotAdapter] = None,
        intent_router: Optional[QueryIntentRouter] = None,
        answer_mode_classifier: Optional[AnswerModeClassifier] = None,
        query_plan_assembler: Optional[QueryPlanAssembler] = None,
        requirement_planner: Optional[ContextRequirementPlanner] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        execution_planner: Optional[ContextExecutionPlanner] = None,
        sufficiency_gate: Optional[ContextSufficiencyGate] = None,
    ):
        self.intent_router = intent_router or QueryIntentRouter()
        self.answer_mode_classifier = answer_mode_classifier or AnswerModeClassifier(self.intent_router)
        self.query_decomposer = QueryDecomposer(self.intent_router)
        self.market_adapter = market_adapter
        self.calendar_adapter = calendar_adapter
        self.macro_adapter = macro_adapter
        self.technical_adapter = technical_adapter or ExistingTechnicalSnapshotAdapter()
        self.query_plan_assembler = query_plan_assembler or QueryPlanAssembler(
            intent_router=self.intent_router,
            answer_mode_classifier=self.answer_mode_classifier,
            query_decomposer=self.query_decomposer,
        )
        self.requirement_planner = requirement_planner or ContextRequirementPlanner()
        self.capability_registry = capability_registry or CapabilityRegistry.default()
        self.execution_planner = execution_planner or ContextExecutionPlanner(self.capability_registry)
        self.sufficiency_gate = sufficiency_gate or ContextSufficiencyGate()

    def build(
        self,
        original_query: str,
        rewritten_query: str = "",
        query_intent: Optional[QueryIntent] = None,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        live_price_output: Optional[str] = None,
        candles_output: Optional[List[Dict[str, Any]]] = None,
        calendar_output: Optional[str] = None,
        macro_output: Optional[str] = None,
        risk_context: Optional[Dict[str, Any]] = None,
        query_plan: Optional[QueryPlan] = None,
        context_requirements: Optional[ContextRequirements] = None,
        context_execution_plan: Optional[ContextExecutionPlan] = None,
        acquisition_batch_result: Optional[Any] = None,
        task_context_views: Optional[List[Any]] = None,
    ) -> DecisionContext:
        started = time.time()
        request_id = uuid.uuid4().hex[:12]
        _safe_print(f"[DecisionContext] status=start query={original_query!r}")

        decomposition = self.query_decomposer.decompose(original_query)
        query_intent = query_intent or self.intent_router.route(original_query)
        if decomposition.is_multi_intent:
            answer_mode = AnswerMode(
                mode="MULTI_INTENT",
                market_impact_allowed=False,
                requires_official_report=any(item.intent.source_preference in {"official_report_first", "mixed_report_and_book"} for item in decomposition.subqueries),
                requires_book_source=any(item.intent.source_preference == "book_first" for item in decomposition.subqueries),
                template_id="multi_intent",
                confidence=0.9,
                reason=decomposition.reason,
            )
        else:
            answer_mode = self.answer_mode_classifier.classify(original_query, query_intent)
        query_plan = query_plan or self.query_plan_assembler.assemble(
            original_query=original_query,
            rewritten_query=rewritten_query,
            query_intent=query_intent,
            answer_mode=answer_mode,
        )
        context_requirements = context_requirements or self.requirement_planner.plan(query_plan)
        context_execution_plan = context_execution_plan or self.execution_planner.plan(context_requirements)
        normalized_query = AnswerModeClassifier.normalize(original_query)
        symbols = self._symbols(original_query)
        timeframe = self._timeframe(original_query)
        needs = self._determine_needs_from_requirements(context_requirements, query_plan)
        _safe_print(
            "[DecisionContext] need "
            f"static={str(needs['static']).lower()} "
            f"market={str(needs['market']).lower()} "
            f"calendar={str(needs['calendar']).lower()} "
            f"risk={str(needs['risk']).lower()}"
        )

        acquisition_mode = "executor_results" if acquisition_batch_result is not None else "legacy_heuristic"
        _safe_print(f"[DecisionContext] acquisition_mode={acquisition_mode}")

        missing: List[str] = []
        warnings: List[str] = []
        market_snapshot = None
        economic_events: List[EconomicEventContext] = []
        macro_snapshot = None
        technical_snapshot = None

        if acquisition_batch_result is not None:
            retrieval_results = self._docs_from_acquisition_results(getattr(acquisition_batch_result, "results", []))
            market_snapshot = self._market_snapshot_from_acquisition_results(getattr(acquisition_batch_result, "results", []))
            economic_events = self._economic_events_from_acquisition_results(getattr(acquisition_batch_result, "results", []))
            technical_snapshot = self._technical_snapshot_from_acquisition_results(getattr(acquisition_batch_result, "results", []))
            for result in getattr(acquisition_batch_result, "results", []):
                if getattr(result, "required", False) and not getattr(result, "ok", False):
                    missing.append(result.result_id())
            if any(result.capability in {"market_snapshot", "ohlcv"} and result.ok for result in getattr(acquisition_batch_result, "results", [])):
                _safe_print("[DecisionContext] market_data source=executor_results status=ok")
            if any(result.capability == "economic_event" and result.ok for result in getattr(acquisition_batch_result, "results", [])):
                _safe_print("[DecisionContext] calendar source=executor_results status=ok")
            context_freshness = self._freshness_from_acquisition_results(getattr(acquisition_batch_result, "results", []))
        else:
            context_freshness = {}

        if acquisition_batch_result is None and needs["market"]:
            if self.market_adapter:
                symbol = symbols[0] if symbols else "XAUUSD"
                market_snapshot = self.market_adapter.get_snapshot(
                    symbol=symbol,
                    timeframe=timeframe,
                    live_price_output=live_price_output,
                    candles_output=candles_output,
                    indicators=[{"name": "ema", "period": 20}, {"name": "rsi", "period": 14}] if needs["technical"] else None,
                )
                technical_snapshot = self.technical_adapter.build(market_snapshot, candles_output)
                _safe_print(f"[DecisionContext] market_data source=existing_api status=ok symbol={symbol}")
            else:
                missing.append("market_data")

        if acquisition_batch_result is None and needs["calendar"]:
            if self.calendar_adapter:
                economic_events = self.calendar_adapter.get_events(calendar_output=calendar_output)
                _safe_print(f"[DecisionContext] calendar source=existing_api status=ok events={len(economic_events)}")
            else:
                missing.append("economic_calendar")
            if self.macro_adapter:
                macro_snapshot = self.macro_adapter.get_snapshot(macro_output=macro_output)
                _safe_print(
                    "[DecisionContext] macro_data "
                    f"source=existing_api status={'ok' if macro_snapshot.get('available') else 'empty'}"
                )

        risk_snapshot = None
        if acquisition_batch_result is None and needs["risk"]:
            if risk_context:
                risk_snapshot = self._risk_snapshot(risk_context)
            else:
                missing.append("risk_context")

        if acquisition_batch_result is None and needs["static"] and not retrieval_results:
            missing.append("static_knowledge")

        retrieved_context = self._retrieved_context(retrieval_results or [])
        if not context_freshness:
            context_freshness = {
                "market_timestamp": market_snapshot.timestamp if market_snapshot else "",
                "calendar_events_count": len(economic_events),
                "static_sources_count": len((retrieval_results or [])),
            }
        status = "partial" if missing else "complete"
        if missing:
            _safe_print(f"[DecisionContext] status=partial missing_context={missing}")

        context = DecisionContext(
            request_id=request_id,
            user_query=original_query,
            normalized_query=normalized_query,
            query_intent=query_intent.as_dict(),
            answer_mode=answer_mode.as_dict(),
            symbols=symbols,
            timeframe=timeframe,
            market_data_required=needs["market"],
            static_knowledge_required=needs["static"],
            economic_calendar_required=needs["calendar"],
            news_required=needs["news"],
            risk_context_required=needs["risk"],
            technical_snapshot_required=needs["technical"],
            execution_gate_required=needs["execution"],
            retrieved_sources=retrieved_context,
            market_snapshot=market_snapshot,
            economic_events=economic_events,
            macro_snapshot=macro_snapshot,
            technical_snapshot=technical_snapshot,
            risk_snapshot=risk_snapshot,
            missing_context=missing,
            warnings=warnings,
            context_freshness=context_freshness,
            query_plan=query_plan.as_dict(),
            requirements=context_requirements.as_dict(),
            execution_plan=context_execution_plan.as_dict(),
            acquisition_mode=acquisition_mode,
            task_context_views=[
                view.as_dict() if hasattr(view, "as_dict") else dict(view)
                for view in (task_context_views or getattr(acquisition_batch_result, "task_context_views", []) or [])
            ],
            freshness_map=context_freshness,
            provenance_map=self._provenance_map(
                retrieval_results or [],
                market_snapshot,
                economic_events,
                macro_snapshot,
                technical_snapshot,
                risk_snapshot,
            ),
        )
        if acquisition_batch_result is not None:
            acquisition_results = list(getattr(acquisition_batch_result, "results", []) or [])
        else:
            acquisition_results = self._acquisition_results(
                context_requirements,
                retrieval_results or [],
                market_snapshot,
                economic_events,
                macro_snapshot,
                technical_snapshot,
                risk_snapshot,
            )
        context.acquisition_results = [result.as_dict() for result in acquisition_results]
        context.provenance_map = self._provenance_map(
            retrieval_results or [],
            market_snapshot,
            economic_events,
            macro_snapshot,
            technical_snapshot,
            risk_snapshot,
            acquisition_results=acquisition_results,
        )
        sufficiency = self.sufficiency_gate.evaluate(context, context_requirements, context_execution_plan)
        context.sufficiency = sufficiency.as_dict()
        context.missing_required_context = list(sufficiency.missing_required)
        context.missing_optional_context = list(sufficiency.missing_optional)
        context.completeness_score = sufficiency.completeness_score
        context.confidence_ceiling = sufficiency.confidence_ceiling
        for warning in sufficiency.warnings:
            if warning not in context.warnings:
                context.warnings.append(warning)
        _safe_print(
            "[DecisionContext] "
            f"completeness_score={context.completeness_score:.3f} "
            f"missing_required={context.missing_required_context} "
            f"missing_optional={context.missing_optional_context}"
        )
        _safe_print(f"[DecisionContext] status={status} latency_ms={(time.time() - started) * 1000:.2f}")
        return context

    @staticmethod
    def _docs_from_acquisition_results(results: List[Any]) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for result in results or []:
            if getattr(result, "capability", "") not in {"official_report", "static_knowledge", "market_knowledge"}:
                continue
            if not getattr(result, "ok", False):
                continue
            data = getattr(result, "data", None)
            if isinstance(data, dict):
                docs.append(data)
            elif isinstance(data, list):
                docs.extend([item for item in data if isinstance(item, dict)])
        return docs

    @staticmethod
    def _market_snapshot_from_acquisition_results(results: List[Any]) -> Optional[MarketSnapshot]:
        market = None
        ohlcv = None
        for result in results or []:
            if not getattr(result, "ok", False):
                continue
            if getattr(result, "capability", "") == "market_snapshot":
                market = getattr(result, "data", None)
            if getattr(result, "capability", "") == "ohlcv":
                ohlcv = getattr(result, "data", None)
        if isinstance(market, MarketSnapshot):
            if ohlcv and isinstance(market.ohlcv_summary, dict):
                market.ohlcv_summary["candles"] = len(ohlcv)
                market.ohlcv_summary["raw_candles"] = ohlcv
            return market
        return None

    @staticmethod
    def _economic_events_from_acquisition_results(results: List[Any]) -> List[EconomicEventContext]:
        events: List[EconomicEventContext] = []
        for result in results or []:
            if getattr(result, "capability", "") != "economic_event" or not getattr(result, "ok", False):
                continue
            data = getattr(result, "data", None)
            if isinstance(data, EconomicEventContext):
                events.append(data)
            elif isinstance(data, list):
                events.extend([item for item in data if isinstance(item, EconomicEventContext)])
        return events

    @staticmethod
    def _technical_snapshot_from_acquisition_results(results: List[Any]) -> Optional[Dict[str, Any]]:
        for result in results or []:
            if getattr(result, "capability", "") == "technical_snapshot" and getattr(result, "ok", False):
                data = getattr(result, "data", None)
                if isinstance(data, dict):
                    return data
        return None

    @staticmethod
    def _freshness_from_acquisition_results(results: List[Any]) -> Dict[str, Any]:
        freshness: Dict[str, Any] = {}
        for result in results or []:
            result_id = result.result_id() if hasattr(result, "result_id") else f"{getattr(result, 'capability', '')}:{getattr(result, 'target', '')}"
            freshness[result_id] = {
                "freshness_status": getattr(result, "freshness_status", "unknown"),
                "fetched_at": getattr(result, "fetched_at", ""),
                "source_timestamp": getattr(result, "source_timestamp", ""),
            }
        return freshness

    @staticmethod
    def _determine_needs_from_requirements(requirements: ContextRequirements, query_plan: QueryPlan) -> Dict[str, bool]:
        capabilities = {need.capability for need in requirements.needs}
        return {
            "static": bool(capabilities & {"official_report", "static_knowledge", "market_knowledge"}),
            "market": bool(capabilities & {"market_snapshot", "ohlcv"}),
            "calendar": "economic_event" in capabilities,
            "news": False,
            "risk": bool(capabilities & {"account_state", "instrument_spec", "stop_distance", "risk_limit"}),
            "technical": "technical_snapshot" in capabilities,
            "execution": query_plan.user_action_intent == "execution_request" or query_plan.primary_intent in {"trade_opportunity_analysis", "position_sizing"},
        }

    @staticmethod
    def _determine_needs(normalized_query: str, intent: QueryIntent, answer_mode: AnswerMode) -> Dict[str, bool]:
        static = answer_mode.mode == "MULTI_INTENT" or intent.source_preference in {"official_report_first", "mixed_report_and_book", "book_first"}
        trade_terms = any(term in f" {normalized_query} " for term in [" vao lenh", "entry", " sl ", " tp ", "position size", "lot", "nen mua", "nen ban", "buy", "sell"])
        current_terms = any(term in normalized_query for term in ["hien tai", "luc nay", "bay gio", "moi nhat", "latest", "current", "right now"])
        symbol_terms = any(term in normalized_query for term in ["xauusd", "gold", "vang"])
        market = trade_terms or (answer_mode.market_impact_allowed and symbol_terms) or (current_terms and symbol_terms)
        calendar = answer_mode.mode == "MARKET_IMPACT" and any(
            event in {"CPI", "NFP", "FOMC", "FOMC_MINUTES", "SEP", "GDP"}
            for event in intent.event_type_candidates
        )
        if current_terms and any(term in normalized_query for term in ["cpi", "nfp", "fomc", "gdp"]):
            calendar = True
        return {
            "static": static,
            "market": market,
            "calendar": calendar,
            "news": False,
            "risk": trade_terms,
            "technical": trade_terms or (market and symbol_terms),
            "execution": trade_terms,
        }

    @staticmethod
    def _symbols(query: str) -> List[str]:
        text = AnswerModeClassifier.normalize(query)
        symbols = []
        if "xauusd" in text or "gold" in text or "vang" in text:
            symbols.append("XAUUSD")
        for token in re.findall(r"\b[A-Z]{3,6}USD\b", query or ""):
            if token not in symbols:
                symbols.append(token)
        return symbols

    @staticmethod
    def _acquisition_results(
        requirements: ContextRequirements,
        docs: List[Dict[str, Any]],
        market_snapshot: Optional[MarketSnapshot],
        economic_events: List[EconomicEventContext],
        macro_snapshot: Optional[Dict[str, Any]],
        technical_snapshot: Optional[Dict[str, Any]],
        risk_snapshot: Optional[RiskSnapshot],
    ) -> List[ContextAcquisitionResult]:
        task_map = DecisionContextBuilder._task_ids_by_need(requirements)
        results = []
        for need in requirements.needs:
            result = DecisionContextBuilder._acquire_need_result(
                need,
                docs,
                market_snapshot,
                economic_events,
                macro_snapshot,
                technical_snapshot,
                risk_snapshot,
                task_map.get(DecisionContextBuilder._need_name(need), []),
            )
            results.append(result)
            source = result.provenance.get("source") or result.provenance.get("title") or result.provenance.get("event_name") or ""
            _safe_print(
                "[ContextAcquisition] "
                f"task={result.result_id()} "
                f"status={result.status} "
                f"required={str(result.required).lower()} "
                f"source={source} "
                f"reason={result.reason}"
            )
        return results

    @staticmethod
    def _task_ids_by_need(requirements: ContextRequirements) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for task_id, names in (requirements.task_need_mapping or {}).items():
            for name in names:
                mapping.setdefault(name, []).append(task_id)
        return mapping

    @staticmethod
    def _acquire_need_result(
        need: ContextNeed,
        docs: List[Dict[str, Any]],
        market_snapshot: Optional[MarketSnapshot],
        economic_events: List[EconomicEventContext],
        macro_snapshot: Optional[Dict[str, Any]],
        technical_snapshot: Optional[Dict[str, Any]],
        risk_snapshot: Optional[RiskSnapshot],
        task_ids: List[str],
    ) -> ContextAcquisitionResult:
        cap = need.capability
        if cap in {"official_report", "static_knowledge", "market_knowledge"}:
            doc = DecisionContextBuilder._matching_knowledge_doc(need, docs)
            if doc:
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance=DecisionContextBuilder._knowledge_provenance(doc),
                    data=doc,
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(
                need,
                "no matching knowledge source",
                task_ids,
            )

        if cap == "market_snapshot":
            if market_snapshot and DecisionContextBuilder._target_matches_symbol(need.target, market_snapshot.symbol):
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={
                        "source": market_snapshot.source or "existing_api",
                        "symbol": market_snapshot.symbol,
                        "timestamp": market_snapshot.timestamp,
                    },
                    data=market_snapshot,
                    freshness="fresh",
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "market snapshot missing or wrong symbol", task_ids)

        if cap == "ohlcv":
            summary = getattr(market_snapshot, "ohlcv_summary", {}) if market_snapshot else {}
            candles = summary.get("candles") if isinstance(summary, dict) else 0
            if market_snapshot and DecisionContextBuilder._target_matches_symbol(need.target, market_snapshot.symbol) and candles:
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={
                        "source": market_snapshot.source or "existing_api",
                        "symbol": market_snapshot.symbol,
                        "timeframe": market_snapshot.timeframe,
                        "candles": candles,
                        "timestamp": market_snapshot.timestamp,
                    },
                    data=summary,
                    freshness="fresh",
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "ohlcv missing or wrong symbol", task_ids)

        if cap == "economic_event":
            event = DecisionContextBuilder._matching_economic_event(need, economic_events)
            if event:
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={
                        "source": event.source,
                        "event_name": event.event_name,
                        "country": event.country,
                        "release_time": event.release_time,
                    },
                    data=event,
                    freshness="fresh",
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "matching economic event missing", task_ids)

        if cap == "technical_snapshot":
            if technical_snapshot:
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={"source": technical_snapshot.get("source", "existing_api"), "target": need.target},
                    data=technical_snapshot,
                    freshness="fresh",
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "technical snapshot missing", task_ids)

        if cap in {"account_state", "instrument_spec", "stop_distance", "risk_limit"}:
            if risk_snapshot:
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={"source": "provided_context", "target": need.target},
                    data=risk_snapshot,
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "risk/account context missing", task_ids)

        if cap == "macro_snapshot":
            if macro_snapshot and macro_snapshot.get("available"):
                return DecisionContextBuilder._acquisition_success(
                    need,
                    provenance={"source": macro_snapshot.get("source", "existing_api"), "timestamp": macro_snapshot.get("timestamp", "")},
                    data=macro_snapshot,
                    task_ids=task_ids,
                )
            return DecisionContextBuilder._acquisition_missing(need, "macro snapshot missing", task_ids)

        return DecisionContextBuilder._acquisition_missing(need, "unsupported capability", task_ids)

    @staticmethod
    def _acquisition_success(
        need: ContextNeed,
        provenance: Dict[str, Any],
        data: Any = None,
        freshness: str = "acceptable",
        task_ids: List[str] = None,
    ) -> ContextAcquisitionResult:
        return ContextAcquisitionResult(
            capability=need.capability,
            target=need.target,
            status="success",
            required=need.required,
            data=data,
            provenance=provenance,
            freshness_status=freshness,
            reason="matched",
            task_ids=list(task_ids or []),
        )

    @staticmethod
    def _acquisition_missing(need: ContextNeed, reason: str, task_ids: List[str] = None) -> ContextAcquisitionResult:
        return ContextAcquisitionResult(
            capability=need.capability,
            target=need.target,
            status="missing",
            required=need.required,
            reason=reason,
            task_ids=list(task_ids or []),
        )

    @staticmethod
    def _matching_knowledge_doc(need: ContextNeed, docs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for doc in docs:
            if DecisionContextBuilder._doc_matches_need(need, doc):
                return doc
        return None

    @staticmethod
    def _doc_matches_need(need: ContextNeed, doc: Dict[str, Any]) -> bool:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        haystack = DecisionContextBuilder._normalized_doc_haystack(doc)
        target = AnswerModeClassifier.normalize(need.target)
        event_type = AnswerModeClassifier.normalize(metadata.get("event_type", ""))
        subdomain = AnswerModeClassifier.normalize(metadata.get("subdomain", ""))
        domain = AnswerModeClassifier.normalize(metadata.get("domain", ""))
        title = AnswerModeClassifier.normalize(metadata.get("title") or metadata.get("source") or doc.get("source") or "")
        organization = AnswerModeClassifier.normalize(metadata.get("organization", ""))

        if need.capability == "official_report":
            if target in {"cpi", "nfp", "gdp", "fomc", "fomc_minutes", "sep", "global_outlook", "commodity_markets", "gold_market"}:
                if event_type == target:
                    return True
                official_terms = {
                    "cpi": ("cpi", "consumer price index", "us cpi report", "bls"),
                    "nfp": ("nonfarm", "payroll", "employment situation", "bls"),
                    "gdp": ("gdp", "gross domestic product", "bea"),
                    "fomc": ("fomc statement", "federal reserve"),
                    "fomc_minutes": ("fomc minutes", "federal reserve"),
                    "sep": ("summary of economic projections", "federal reserve"),
                    "global_outlook": ("world economic outlook", "imf"),
                    "commodity_markets": ("commodity markets outlook", "world bank"),
                    "gold_market": ("gold market commentary", "world gold council"),
                }.get(target, ())
                return any(term in haystack for term in official_terms)
            return "report" in haystack or metadata.get("knowledge_type") == "report"

        if need.capability == "market_knowledge":
            if target in {"gold", "xauusd"}:
                return subdomain == "gold" or event_type == "gold_market" or "world gold council" in haystack or "gold" in title
            return bool(target and target in haystack)

        if need.capability == "static_knowledge":
            if not target or target in {"general", "static_knowledge"}:
                return True
            aliases = {
                "price_action": ("price action", "bar by bar", "al brooks"),
                "volume_price_analysis": ("volume price analysis", "vpa", "anna coulling", "volume"),
                "position_sizing": ("position sizing", "van tharp", "r multiple", "risk"),
                "trading_discipline": ("trading discipline", "mark douglas", "psychology", "discipline"),
                "trend_following": ("trend following", "michael covel"),
                "trading_framework": ("trading", "risk", "framework", "strategy"),
            }.get(target, (target,))
            return subdomain == target or domain == target or any(term in haystack for term in aliases)

        return False

    @staticmethod
    def _normalized_doc_haystack(doc: Dict[str, Any]) -> str:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        parts = [
            metadata.get("title", ""),
            metadata.get("source", ""),
            metadata.get("organization", ""),
            metadata.get("author", ""),
            metadata.get("event_type", ""),
            metadata.get("domain", ""),
            metadata.get("subdomain", ""),
            metadata.get("knowledge_type", ""),
            doc.get("source", ""),
            doc.get("file_name", ""),
            doc.get("content", ""),
            doc.get("parent_text", ""),
            doc.get("child_text", ""),
            doc.get("text", ""),
        ]
        return AnswerModeClassifier.normalize(" ".join(str(part or "") for part in parts))

    @staticmethod
    def _matching_economic_event(need: ContextNeed, events: List[EconomicEventContext]) -> Optional[EconomicEventContext]:
        target = AnswerModeClassifier.normalize(need.target)
        if target in {"", "macro", "default"}:
            return events[0] if events else None
        aliases = {
            "cpi": ("cpi", "consumer price", "inflation"),
            "nfp": ("nfp", "nonfarm", "payroll", "employment"),
            "gdp": ("gdp", "gross domestic product"),
            "fomc": ("fomc", "fed", "federal reserve", "interest rate"),
            "fomc_minutes": ("fomc", "minutes", "federal reserve"),
            "sep": ("summary of economic projections", "sep"),
        }.get(target, (target,))
        for event in events:
            event_name = AnswerModeClassifier.normalize(event.event_name)
            if any(alias in event_name for alias in aliases):
                return event
        return None

    @staticmethod
    def _target_matches_symbol(target: str, symbol: str) -> bool:
        normalized_target = AnswerModeClassifier.normalize(target)
        normalized_symbol = AnswerModeClassifier.normalize(symbol)
        return not normalized_target or normalized_target == normalized_symbol or (normalized_target == "gold" and normalized_symbol == "xauusd")

    @staticmethod
    def _knowledge_provenance(doc: Dict[str, Any]) -> Dict[str, Any]:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        return {
            "source": metadata.get("source") or doc.get("source") or doc.get("file_name") or "",
            "title": metadata.get("title") or metadata.get("source") or doc.get("source") or "",
            "organization": metadata.get("organization") or "",
            "author": metadata.get("author") or "",
            "event_type": metadata.get("event_type") or "",
            "domain": metadata.get("domain") or "",
            "subdomain": metadata.get("subdomain") or "",
            "retrieval_mode": metadata.get("retrieval_mode") or "",
            "collection": metadata.get("collection") or "",
        }

    @staticmethod
    def _need_name(need: ContextNeed) -> str:
        return f"{need.capability}:{need.target or 'default'}"

    @staticmethod
    def _provenance_map(
        docs: List[Dict[str, Any]],
        market_snapshot: Optional[MarketSnapshot],
        economic_events: List[EconomicEventContext],
        macro_snapshot: Optional[Dict[str, Any]],
        technical_snapshot: Optional[Dict[str, Any]],
        risk_snapshot: Optional[RiskSnapshot],
        acquisition_results: Optional[List[ContextAcquisitionResult]] = None,
    ) -> Dict[str, Any]:
        provenance: Dict[str, Any] = {}
        if acquisition_results is not None:
            provenance["acquisition_results"] = [result.as_dict() for result in acquisition_results]
        if docs:
            provenance["knowledge"] = [
                {
                    "title": (doc.get("metadata") or {}).get("title"),
                    "organization": (doc.get("metadata") or {}).get("organization"),
                    "author": (doc.get("metadata") or {}).get("author"),
                    "retrieval_mode": (doc.get("metadata") or {}).get("retrieval_mode"),
                    "collection": (doc.get("metadata") or {}).get("collection"),
                }
                for doc in docs
            ]
        if market_snapshot:
            provenance["market_snapshot"] = {"source": market_snapshot.source, "timestamp": market_snapshot.timestamp}
        if economic_events:
            provenance["economic_events"] = [{"source": event.source, "event_name": event.event_name} for event in economic_events]
        if macro_snapshot:
            provenance["macro_snapshot"] = {"source": macro_snapshot.get("source"), "timestamp": macro_snapshot.get("timestamp")}
        if technical_snapshot:
            provenance["technical_snapshot"] = {"source": technical_snapshot.get("source")}
        if risk_snapshot:
            provenance["risk_snapshot"] = {"source": "provided_context"}
        return provenance

    @staticmethod
    def _timeframe(query: str) -> str:
        match = re.search(r"\b(1m|5m|15m|30m|1h|4h|1d|daily|h1|h4)\b", str(query or ""), flags=re.IGNORECASE)
        if not match:
            return "1h"
        value = match.group(1).lower()
        return {"h1": "1h", "h4": "4h", "daily": "1d"}.get(value, value)

    @staticmethod
    def _retrieved_context(docs: List[Dict[str, Any]]) -> RetrievedKnowledgeContext:
        primary = []
        supporting = []
        warnings = []
        coverage = 0.0
        for doc in docs:
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            title = metadata.get("title") or metadata.get("source") or "Unknown source"
            owner = metadata.get("organization") or metadata.get("author") or ""
            name = f"{title} - {owner}" if owner else str(title)
            if metadata.get("source_role") == "primary_source" or not primary:
                if name not in primary:
                    primary.append(name)
            else:
                if name not in supporting:
                    supporting.append(name)
            try:
                coverage = max(coverage, float(metadata.get("grounding_coverage_score", 0) or 0))
            except (TypeError, ValueError):
                pass
            for warning in metadata.get("grounding_warnings", []) or []:
                if warning not in warnings:
                    warnings.append(warning)
        if docs and coverage == 0.0:
            coverage = 1.0 if primary else 0.0
        return RetrievedKnowledgeContext(primary, supporting, coverage, warnings)

    @staticmethod
    def _risk_snapshot(risk_context: Dict[str, Any]) -> RiskSnapshot:
        return RiskSnapshot(
            account_balance=risk_context.get("account_balance"),
            max_risk_per_trade=risk_context.get("max_risk_per_trade"),
            open_positions=list(risk_context.get("open_positions", []) or []),
            exposure=risk_context.get("exposure"),
            drawdown=risk_context.get("drawdown"),
            trading_allowed=risk_context.get("trading_allowed"),
        )
