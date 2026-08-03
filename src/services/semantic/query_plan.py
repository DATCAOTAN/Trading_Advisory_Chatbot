import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.knowledge.answer_mode import AnswerMode, AnswerModeClassifier
from src.services.knowledge.query_decomposer import QueryDecomposer
from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter
from src.services.trading.market.timeframes import resolve_symbol, resolve_symbols_from_text
from src.services.trading.reasoning.strategy_evidence import (
    INDICATOR_REGISTRY,
    IndicatorSpec,
    parse_indicator_specs,
)
from src.services.semantic.conversational_context import ConversationalIntentContext


@dataclass
class QueryEntities:
    symbols: List[str] = field(default_factory=list)
    broker_symbols: List[str] = field(default_factory=list)
    raw_symbols: List[str] = field(default_factory=list)
    unresolved_symbols: List[str] = field(default_factory=list)
    macro_events: List[str] = field(default_factory=list)
    organizations: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    books: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "broker_symbols": list(self.broker_symbols),
            "raw_symbols": list(self.raw_symbols),
            "unresolved_symbols": list(self.unresolved_symbols),
            "macro_events": list(self.macro_events),
            "organizations": list(self.organizations),
            "authors": list(self.authors),
            "books": list(self.books),
            "concepts": list(self.concepts),
            "strategies": list(self.strategies),
            "timeframes": list(self.timeframes),
            "countries": list(self.countries),
        }


@dataclass
class QueryPlan:
    original_query: str
    normalized_query: str
    task_id: str = ""
    primary_intent: str = "unknown"
    secondary_intents: List[str] = field(default_factory=list)
    entities: QueryEntities = field(default_factory=QueryEntities)
    temporal_scope: str = "unknown"
    requested_analysis: List[str] = field(default_factory=list)
    requested_indicators: List[IndicatorSpec] = field(default_factory=list)
    current_market_request: bool = False
    conceptual_request: bool = False
    user_action_intent: str = "unknown"
    requires_execution: bool = False
    conversation_dependency: str = "none"
    ambiguity: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    child_plans: List["QueryPlan"] = field(default_factory=list)
    source_signals: Dict[str, Any] = field(default_factory=dict)
    conversational_context: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "primary_intent": self.primary_intent,
            "secondary_intents": list(self.secondary_intents),
            "entities": self.entities.as_dict(),
            "temporal_scope": self.temporal_scope,
            "requested_analysis": list(self.requested_analysis),
            "requested_indicators": [item.as_dict() for item in self.requested_indicators],
            "current_market_request": self.current_market_request,
            "conceptual_request": self.conceptual_request,
            "user_action_intent": self.user_action_intent,
            "requires_execution": self.requires_execution,
            "conversation_dependency": self.conversation_dependency,
            "ambiguity": list(self.ambiguity),
            "constraints": dict(self.constraints),
            "confidence": self.confidence,
            "child_plans": [child.as_dict() for child in self.child_plans],
            "source_signals": dict(self.source_signals),
            "conversational_context": dict(self.conversational_context),
        }


class QueryPlanAssembler:
    """Build a canonical QueryPlan from existing deterministic signals.

    This class intentionally does not add a mandatory LLM call. A future
    structured semantic planner can feed richer signals through the same model.
    """

    BOOK_BY_AUTHOR = {
        "Al Brooks": "Reading Price Charts Bar by Bar",
        "Anna Coulling": "A Complete Guide to Volume Price Analysis",
        "Van Tharp": "Trade Your Way to Financial Freedom",
        "Mark Douglas": "Trading in the Zone",
        "Michael Covel": "Trend Following",
        "John Murphy": "Technical Analysis of the Financial Markets",
        "Ben Bernanke": "The Federal Reserve and the Financial Crisis",
    }

    CONCEPT_BY_INTENT = {
        "price_action": "price_action",
        "volume_analysis": "volume_price_analysis",
        "risk_management": "position_sizing",
        "trading_psychology": "trading_discipline",
        "technical_analysis": "technical_indicators",
        "monetary_policy": "monetary_policy",
    }

    EVENT_ROUTE = {
        "CPI": ("macro", "inflation", "BLS", "macro_report"),
        "NFP": ("macro", "employment", "BLS", "macro_report"),
        "GDP": ("macro", "gdp", "BEA", "macro_report"),
        "FOMC": ("macro", "central_bank", "Federal Reserve", "macro_report"),
        "FOMC_MINUTES": ("macro", "central_bank", "Federal Reserve", "macro_report"),
        "SEP": ("macro", "central_bank", "Federal Reserve", "macro_report"),
        "GLOBAL_OUTLOOK": ("macro", "global_outlook", "IMF", "macro_report"),
        "COMMODITY_MARKETS": ("market", "commodities", "World Bank", "macro_report"),
        "GOLD_MARKET": ("market", "gold", "World Gold Council", "market_gold"),
    }

    def __init__(
        self,
        intent_router: Optional[QueryIntentRouter] = None,
        answer_mode_classifier: Optional[AnswerModeClassifier] = None,
        query_decomposer: Optional[QueryDecomposer] = None,
    ):
        self.intent_router = intent_router or QueryIntentRouter()
        self.answer_mode_classifier = answer_mode_classifier or AnswerModeClassifier(self.intent_router)
        self.query_decomposer = query_decomposer or QueryDecomposer(self.intent_router)

    def assemble(
        self,
        original_query: str,
        rewritten_query: str = "",
        query_intent: Optional[QueryIntent] = None,
        answer_mode: Optional[AnswerMode] = None,
        task_id: str = "",
        decompose: bool = True,
        conversational_context: Optional[ConversationalIntentContext] = None,
    ) -> QueryPlan:
        query = original_query or ""
        normalized = AnswerModeClassifier.normalize(query)
        query_intent = query_intent or self.intent_router.route(query)
        answer_mode = answer_mode or self.answer_mode_classifier.classify(query, query_intent)
        if (
            conversational_context
            and conversational_context.is_strategy_request
            and not ({"current_market", "concept"} & set(conversational_context.intent_families))
        ):
            decompose = False
        decomposition = self.query_decomposer.decompose(query) if decompose else None

        child_plans: List[QueryPlan] = []
        if decompose and getattr(decomposition, "is_multi_intent", False):
            for index, subquery in enumerate(decomposition.subqueries, start=1):
                child_intent = subquery.intent
                child_answer_mode = self.answer_mode_classifier.classify(subquery.query, child_intent)
                child_plans.append(
                    self.assemble(
                        original_query=subquery.query,
                        query_intent=child_intent,
                        answer_mode=child_answer_mode,
                        task_id=f"task_{index}",
                        decompose=False,
                    )
                )

        entities = self._merge_child_entities(child_plans) if child_plans else self._entities(query, normalized, query_intent, decomposition)
        if conversational_context:
            if conversational_context.canonical_symbol:
                entities.symbols = [conversational_context.canonical_symbol]
                entities.broker_symbols = [conversational_context.broker_symbol]
            if conversational_context.timeframes:
                entities.timeframes = list(conversational_context.timeframes)
        default_timeframes = entities.timeframes or ["1h"]
        requested_indicators = (
            self._merge_child_indicators(child_plans)
            if child_plans
            else list(parse_indicator_specs(query, default_timeframes))
        )
        if conversational_context and conversational_context.indicators:
            requested_indicators = list(conversational_context.indicators)
        current_market_request = (
            any(child.current_market_request for child in child_plans)
            if child_plans
            else self._is_current_market_request(normalized, entities, requested_indicators)
        )
        if conversational_context and "current_market" in conversational_context.intent_families:
            current_market_request = True
        conceptual_request = (
            any(child.conceptual_request for child in child_plans)
            if child_plans
            else self._is_conceptual_request(normalized)
        )
        if conversational_context and "concept" in conversational_context.intent_families:
            conceptual_request = True
        secondary = self._secondary_intents(decomposition, child_plans)
        primary = self._primary_intent(
            normalized,
            query_intent,
            answer_mode,
            decomposition,
            current_market_request=current_market_request,
        )
        if conversational_context and conversational_context.is_strategy_request:
            if "current_market" in conversational_context.intent_families:
                primary = "market_state_analysis"
            elif "concept" in conversational_context.intent_families:
                primary = "book_concept_explanation"
            else:
                primary = "conversational_strategy_request"
        temporal_scope = self._aggregate_temporal_scope(child_plans) if child_plans else self._temporal_scope(normalized, query_intent)
        requested_analysis = (
            self._dedupe([analysis for child in child_plans for analysis in child.requested_analysis])
            if child_plans
            else self._requested_analysis(primary, normalized, query_intent, answer_mode)
        )
        if primary == "conversational_strategy_request":
            requested_analysis = ["strategy_normalization", "strategy_completeness"]
        elif conversational_context and conversational_context.is_strategy_request:
            requested_analysis = self._dedupe(
                requested_analysis + ["strategy_normalization", "strategy_completeness"]
            )
        if requested_indicators:
            requested_analysis = self._dedupe(requested_analysis + ["technical_indicator_values"])
        if conceptual_request and current_market_request:
            requested_analysis = self._dedupe(requested_analysis + ["concept_explanation"])
        user_action_intent = self._aggregate_user_action(child_plans) if child_plans else self._user_action_intent(primary, normalized, answer_mode)
        if primary == "conversational_strategy_request":
            user_action_intent = "define_strategy"
        requires_execution = any(child.requires_execution for child in child_plans) if child_plans else self._requires_execution(normalized)
        conversation_dependency = self._conversation_dependency(normalized)

        plan = QueryPlan(
            original_query=query,
            normalized_query=normalized,
            task_id=task_id or ("task_1" if not child_plans and primary != "multi_intent" else ""),
            primary_intent=primary,
            secondary_intents=secondary,
            entities=entities,
            temporal_scope=temporal_scope,
            requested_analysis=requested_analysis,
            requested_indicators=requested_indicators,
            current_market_request=current_market_request,
            conceptual_request=conceptual_request,
            user_action_intent=user_action_intent,
            requires_execution=requires_execution,
            conversation_dependency=conversation_dependency,
            ambiguity=(
                [f"unresolved_symbol:{value}" for value in entities.unresolved_symbols]
                or ([] if query_intent.intent_type != "unknown" else ["intent_unknown"])
            ),
            constraints={
                "execution_allowed": False,
                "response_format": conversational_context.response_format if conversational_context else "",
                "strategy_blockers": list(conversational_context.blockers) if conversational_context else [],
                "requested_mode": conversational_context.requested_mode if conversational_context else "",
            },
            confidence=self._aggregate_confidence(child_plans, query_intent, answer_mode),
            child_plans=child_plans,
            source_signals={
                "query_intent": query_intent.as_dict(),
                "answer_mode": answer_mode.as_dict(),
                "rewritten_query": rewritten_query or "",
                "decomposition": {
                    "is_multi_intent": bool(getattr(decomposition, "is_multi_intent", False)),
                    "subqueries": [item.query for item in getattr(decomposition, "subqueries", [])],
                    "reason": getattr(decomposition, "reason", ""),
                },
            },
            conversational_context=conversational_context.as_dict() if conversational_context else {},
        )
        print(
            "[QueryPlan] "
            f"primary_intent={plan.primary_intent} "
            f"secondary_intents={plan.secondary_intents} "
            f"temporal_scope={plan.temporal_scope} "
            f"entities={plan.entities.as_dict()} "
            f"confidence={plan.confidence:.2f}"
        )
        for child in child_plans:
            print(
                "[QueryPlanChild] "
                f"task_id={child.task_id} "
                f"primary_intent={child.primary_intent} "
                f"temporal_scope={child.temporal_scope} "
                f"entities={child.entities.as_dict()} "
                f"confidence={child.confidence:.2f}"
            )
        return plan

    @classmethod
    def intent_from_plan(cls, plan: Optional[QueryPlan]) -> QueryIntent:
        """Convert canonical QueryPlan back into the legacy QueryIntent shape.

        Downstream retrieval/ranking/grounding still accepts QueryIntent today.
        This adapter makes QueryPlan the semantic authority without forcing a
        large rewrite of those components.
        """
        if not plan:
            return QueryIntent()

        base = QueryIntent.from_dict((plan.source_signals or {}).get("query_intent"))
        if plan.primary_intent == "multi_intent":
            return QueryIntent(
                intent_type="multi_intent",
                domain_candidates=list(plan.entities.as_dict().get("domains", [])),
                confidence=plan.confidence,
                routing_reason="canonical multi-intent parent; use child plans for retrieval",
            )

        if plan.primary_intent == "book_concept_explanation" and base.source_preference == "book_first":
            return base

        if plan.primary_intent == "market_state_analysis":
            return cls._market_gold_intent(plan, base)

        event = cls._primary_event(plan)
        if event:
            return cls._event_intent(plan, event, base)

        if base.intent_type != "unknown":
            return base

        if plan.entities.symbols:
            return cls._market_gold_intent(plan, base)
        return base

    @classmethod
    def _primary_event(cls, plan: QueryPlan) -> str:
        events = [event for event in plan.entities.macro_events if event != "GOLD_MARKET"]
        if events:
            return events[0]
        if "GOLD_MARKET" in plan.entities.macro_events:
            return "GOLD_MARKET"
        return ""

    @classmethod
    def _event_intent(cls, plan: QueryPlan, event: str, base: QueryIntent) -> QueryIntent:
        domain, subdomain, organization, intent_type = cls.EVENT_ROUTE.get(
            event,
            (base.primary_domain, base.primary_subdomain, "", base.intent_type or "unknown"),
        )
        events = [event]
        organizations = [organization] if organization else []
        source_preference = "official_report_first"
        if plan.primary_intent == "macro_market_impact":
            source_preference = "mixed_report_and_book"
            if plan.entities.symbols and "GOLD_MARKET" not in events:
                events.append("GOLD_MARKET")
            if plan.entities.symbols and "World Gold Council" not in organizations:
                organizations.append("World Gold Council")
            intent_type = "mixed"

        return QueryIntent(
            intent_type=intent_type,
            domain_candidates=cls._dedupe([domain] + (["market"] if plan.primary_intent == "macro_market_impact" and domain != "market" else [])),
            subdomain_candidates=cls._dedupe([subdomain] + (["gold"] if plan.primary_intent == "macro_market_impact" and subdomain != "gold" and plan.entities.symbols else [])),
            source_preference=source_preference,
            preferred_organizations=cls._dedupe(organizations),
            preferred_authors=list(base.preferred_authors),
            event_type_candidates=cls._dedupe(events),
            period_candidates=list(base.period_candidates),
            required_source_tier="tier1_or_tier2",
            confidence=max(float(base.confidence or 0.0), float(plan.confidence or 0.0)),
            routing_reason=f"canonical QueryPlan primary_intent={plan.primary_intent} event={event}",
            expanded_terms=list(base.expanded_terms),
        )

    @classmethod
    def _market_gold_intent(cls, plan: QueryPlan, base: QueryIntent) -> QueryIntent:
        symbol = plan.entities.symbols[0] if plan.entities.symbols else ""
        is_gold = symbol == "XAUUSD"
        return QueryIntent(
            intent_type="market_gold",
            domain_candidates=["market"],
            subdomain_candidates=["gold" if is_gold else symbol.lower()] if symbol else ["market"],
            source_preference="official_report_first",
            preferred_organizations=["World Gold Council"] if is_gold else [],
            preferred_authors=list(base.preferred_authors),
            event_type_candidates=["GOLD_MARKET"] if is_gold else [],
            period_candidates=list(base.period_candidates),
            required_source_tier="tier1_or_tier2",
            confidence=max(float(base.confidence or 0.0), float(plan.confidence or 0.0), 0.90),
            routing_reason=f"canonical QueryPlan primary_intent={plan.primary_intent} symbol={','.join(plan.entities.symbols)}",
            expanded_terms=list(base.expanded_terms),
        )

    @staticmethod
    def _secondary_intents(decomposition: Any, child_plans: List[QueryPlan] = None) -> List[str]:
        if child_plans:
            return QueryPlanAssembler._dedupe([child.primary_intent for child in child_plans])
        if not getattr(decomposition, "is_multi_intent", False):
            return []
        intents = []
        for subquery in decomposition.subqueries:
            intent = subquery.intent.intent_type
            if intent and intent not in intents:
                intents.append(intent)
        return intents

    def _primary_intent(
        self,
        normalized: str,
        intent: QueryIntent,
        answer_mode: AnswerMode,
        decomposition: Any = None,
        *,
        current_market_request: bool = False,
    ) -> str:
        if getattr(decomposition, "is_multi_intent", False):
            return "multi_intent"
        if current_market_request:
            return "market_state_analysis"
        if intent.source_preference == "book_first" and not self._is_operational_position_sizing(normalized):
            return "book_concept_explanation"
        if self._is_position_sizing(normalized):
            return "position_sizing"
        if self._is_trade_opportunity(normalized):
            return "trade_opportunity_analysis"
        if self._has_macro_causal_asset_structure(normalized):
            return "macro_market_impact"
        if self._is_current_market_driver_query(normalized, intent):
            return "market_state_analysis"
        if intent.intent_type == "market_gold" and self._has_current_or_impact_terms(normalized):
            return "market_state_analysis"
        if intent.intent_type in {"mixed"} or answer_mode.mode == "MARKET_IMPACT":
            return "macro_market_impact"
        if intent.intent_type in {"market_gold"}:
            return "macro_report_summary"
        if intent.intent_type == "macro_report":
            if self._has_current_or_impact_terms(normalized) and self._symbols_from_text(normalized):
                return "macro_market_impact"
            return "macro_report_summary"
        if intent.intent_type == "unknown" and self._symbols_from_text(normalized):
            return "market_state_analysis" if self._has_current_terms(normalized) else "unknown"
        return "unknown"

    def _entities(self, query: str, normalized: str, intent: QueryIntent, decomposition: Any = None) -> QueryEntities:
        source_intents = [intent]
        if getattr(decomposition, "is_multi_intent", False):
            source_intents = [item.intent for item in decomposition.subqueries if getattr(item, "intent", None)]

        authors = []
        organizations = []
        macro_events = []
        resolutions = resolve_symbols_from_text(query)
        if any(term in normalized for term in [" gold", " vang"]):
            resolutions.append(resolve_symbol("XAUUSD"))
        symbols = self._dedupe([item.canonical_symbol for item in resolutions if item.status == "RESOLVED"])
        concepts = []
        strategies = []
        has_inflation_macro = self._has_inflation_macro_terms(normalized)

        for current_intent in source_intents:
            authors.extend(current_intent.preferred_authors)
            organizations.extend(current_intent.preferred_organizations)
            macro_events.extend(event for event in current_intent.event_type_candidates if event not in {"GOLD_MARKET"})

            if current_intent.intent_type in self.CONCEPT_BY_INTENT:
                concepts.append(self.CONCEPT_BY_INTENT[current_intent.intent_type])
            if current_intent.intent_type == "trend_following":
                strategies.append("trend_following")
                concepts.append("trend_following")
            if current_intent.intent_type == "market_gold":
                concepts.append("gold_market")
                if "GOLD_MARKET" in current_intent.event_type_candidates:
                    macro_events.append("GOLD_MARKET")

        if has_inflation_macro:
            macro_events = ["CPI"] + [event for event in macro_events if event != "CPI"]
            organizations.append("BLS")

        authors = self._dedupe(authors)
        organizations = self._dedupe(organizations)
        books = [self.BOOK_BY_AUTHOR[author] for author in authors if author in self.BOOK_BY_AUTHOR]
        timeframes = self._timeframes(query)
        countries = ["US"] if any(event in {"CPI", "NFP", "GDP", "FOMC", "FOMC_MINUTES", "SEP"} for event in macro_events) else []
        return QueryEntities(
            symbols=symbols,
            broker_symbols=self._dedupe([item.broker_symbol for item in resolutions if item.status == "RESOLVED"]),
            raw_symbols=self._dedupe([item.raw_symbol for item in resolutions]),
            unresolved_symbols=self._dedupe([item.raw_symbol for item in resolutions if item.status != "RESOLVED"]),
            macro_events=self._dedupe(macro_events),
            organizations=organizations,
            authors=authors,
            books=self._dedupe(books),
            concepts=self._dedupe(concepts),
            strategies=self._dedupe(strategies),
            timeframes=timeframes,
            countries=countries,
        )

    @staticmethod
    def _temporal_scope(normalized: str, intent: QueryIntent) -> str:
        text = QueryPlanAssembler._phrase_text(normalized)
        if any(term in text for term in [" bay gio ", " hien tai ", " now ", " right now ", " current ", " luc nay "]):
            return "current"
        if any(term in text for term in [" hom nay ", " today "]):
            return "today"
        if any(term in text for term in [" moi nhat ", " latest ", " vua roi "]):
            return "latest"
        if any(term in text for term in [" sap toi ", " upcoming ", " lich "]):
            return "upcoming"
        if intent.period_candidates:
            return "custom"
        if intent.source_preference == "book_first":
            return "timeless"
        if intent.source_preference in {"official_report_first", "mixed_report_and_book"}:
            return "historical"
        return "unknown"

    @staticmethod
    def _requested_analysis(primary: str, normalized: str, intent: QueryIntent, answer_mode: AnswerMode) -> List[str]:
        requested = []
        if primary == "macro_market_impact":
            requested.extend(["event_surprise_analysis", "market_impact_analysis"])
        if primary == "market_state_analysis":
            requested.extend(["market_state_analysis", "current_driver_analysis"])
        if primary == "trade_opportunity_analysis":
            requested.extend(["market_state_analysis", "trade_scenario_analysis"])
        if primary == "position_sizing":
            requested.extend(["risk_calculation", "position_sizing"])
        if answer_mode.mode in {"REPORT_SUMMARY", "REPORT_NUMBERS", "REPORT_METHODOLOGY"}:
            requested.append(answer_mode.mode.lower())
        if intent.intent_type == "unknown" and "compare" in normalized:
            requested.append("comparison")
        return QueryPlanAssembler._dedupe(requested)

    @staticmethod
    def _user_action_intent(primary: str, normalized: str, answer_mode: AnswerMode) -> str:
        if "execute" in normalized or "dat lenh" in normalized or "vao lenh ngay" in normalized:
            return "execution_request"
        if primary == "position_sizing":
            return "position_sizing"
        if primary == "trade_opportunity_analysis":
            return "consider_entry"
        if primary == "macro_market_impact":
            return "scenario_analysis"
        if primary == "market_state_analysis":
            return "market_analysis"
        if answer_mode.mode in {"REPORT_SUMMARY", "BOOK_CONCEPT_EXPLANATION", "REPORT_METHODOLOGY", "MULTI_INTENT"}:
            return "explanation"
        if any(term in normalized for term in [" so sanh ", " compare "]):
            return "comparison"
        return "information"

    @staticmethod
    def _conversation_dependency(normalized: str) -> str:
        if any(term in normalized for term in [" nhu tren ", " cai do ", " luc nay ", " vua noi ", " hom truoc "]):
            return "follow_up"
        if any(term in normalized for term in [" chien luoc hom truoc ", " phan tich truoc ", " setup do "]):
            return "explicit_reference"
        return "none"

    @staticmethod
    def _requires_execution(normalized: str) -> bool:
        return any(term in normalized for term in [" dat lenh", " execute", " vao lenh ngay", " market order"])

    @staticmethod
    def _is_position_sizing(normalized: str) -> bool:
        return any(term in normalized for term in [" bao nhieu lot", " lot xauusd", " position size", " risk per trade"])

    @staticmethod
    def _is_operational_position_sizing(normalized: str) -> bool:
        return QueryPlanAssembler._is_position_sizing(normalized) or any(
            term in normalized for term in [" tai khoan", " account", " bao nhieu", " how many lots"]
        )

    @staticmethod
    def _is_trade_opportunity(normalized: str) -> bool:
        return any(term in normalized for term in [" co nen vao ", " nen vao ", " vao xauusd", " long ", " short ", " buy ", " sell ", " entry "])

    @staticmethod
    def _has_current_or_impact_terms(normalized: str) -> bool:
        return QueryPlanAssembler._has_current_terms(normalized) or QueryPlanAssembler._has_impact_terms(normalized)

    @staticmethod
    def _has_impact_terms(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(
            term in text
            for term in [
                " anh huong",
                " impact",
                " affect",
                " tac dong",
                " transmit",
                " transmission",
                " co che",
                " mechanism",
                " influence",
                " lead to",
                " cause",
                " driver",
                " chi phoi",
                " dong luc",
                " yeu to",
            ]
        )

    @staticmethod
    def _has_current_terms(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(
            term in text
            for term in [
                " hien tai",
                " bay gio",
                " moi nhat",
                " latest",
                " current",
                " now",
                " right now",
                " vua roi",
                " luc nay",
            ]
        )

    @staticmethod
    def _has_inflation_macro_terms(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(term in text for term in [" cpi", " consumer price", " inflation", " lam phat", " ap luc gia"])

    @staticmethod
    def _has_macro_causal_asset_structure(normalized: str) -> bool:
        return (
            QueryPlanAssembler._has_macro_cause_terms(normalized)
            and bool(QueryPlanAssembler._symbols_from_text(normalized))
            and QueryPlanAssembler._has_causal_relation_terms(normalized)
        )

    @staticmethod
    def _has_macro_cause_terms(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(
            term in text
            for term in [
                " cpi",
                " consumer price",
                " inflation",
                " lam phat",
                " ap luc gia",
                " nfp",
                " nonfarm",
                " payroll",
                " labor market",
                " labour market",
                " viec lam",
                " that nghiep",
                " unemployment",
                " gdp",
                " growth",
                " tang truong",
                " fomc",
                " fed",
                " federal reserve",
                " central bank",
                " ngan hang trung uong",
                " monetary policy",
                " chinh sach tien te",
                " policy rate",
                " lai suat",
            ]
        )

    @staticmethod
    def _has_causal_relation_terms(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(
            term in text
            for term in [
                " anh huong",
                " tac dong",
                " truyen dan",
                " co che",
                " impact",
                " affect",
                " influence",
                " transmit",
                " transmission",
                " mechanism",
                " lead to",
                " cause",
            ]
        )

    @staticmethod
    def _is_current_market_driver_query(normalized: str, intent: QueryIntent) -> bool:
        symbols = QueryPlanAssembler._symbols_from_text(normalized)
        if not symbols:
            return False
        concrete_macro_events = {
            event
            for event in intent.event_type_candidates
            if event not in {"", "GOLD_MARKET"}
        }
        if concrete_macro_events:
            return False
        text = QueryPlanAssembler._phrase_text(normalized)
        driver_terms = any(term in text for term in [" yeu to", " chi phoi", " dong luc", " driver", " driving", " dominate", " dominating"])
        return driver_terms and (QueryPlanAssembler._has_current_terms(normalized) or " dang " in text)

    @staticmethod
    def _phrase_text(normalized: str) -> str:
        return " " + re.sub(r"[^a-z0-9]+", " ", str(normalized or "").lower()).strip() + " "

    @staticmethod
    def _symbols_from_text(normalized: str) -> List[str]:
        symbols = [item.canonical_symbol for item in resolve_symbols_from_text(normalized) if item.status == "RESOLVED"]
        if any(term in normalized for term in [" xauusd", " gold", " vang"]):
            symbols.append("XAUUSD")
        return QueryPlanAssembler._dedupe(symbols)

    @staticmethod
    def _is_current_market_request(
        normalized: str,
        entities: QueryEntities,
        requested_indicators: List[IndicatorSpec],
    ) -> bool:
        if not QueryPlanAssembler._has_current_terms(normalized):
            return False
        indicator_mentioned = any(
            alias in normalized
            for definition in INDICATOR_REGISTRY.values()
            for alias in definition.aliases
        )
        return bool(requested_indicators or indicator_mentioned)

    @staticmethod
    def _is_conceptual_request(normalized: str) -> bool:
        text = QueryPlanAssembler._phrase_text(normalized)
        return any(
            term in text
            for term in [" la gi ", " what is ", " giai thich ", " explain ", " cong thuc ", " formula ", " sach "]
        )

    @staticmethod
    def _timeframes(query: str) -> List[str]:
        found = re.findall(r"\b(?:1m|5m|15m|30m|1h|4h|1d|daily|h1|h4)\b", str(query or ""), flags=re.IGNORECASE)
        mapping = {"h1": "1h", "h4": "4h", "daily": "1d"}
        return QueryPlanAssembler._dedupe([mapping.get(item.lower(), item.lower()) for item in found])

    @staticmethod
    def _dedupe(values: List[str]) -> List[str]:
        out = []
        seen = set()
        for value in values:
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    @staticmethod
    def _merge_child_entities(child_plans: List[QueryPlan]) -> QueryEntities:
        return QueryEntities(
            symbols=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.symbols]),
            broker_symbols=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.broker_symbols]),
            raw_symbols=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.raw_symbols]),
            unresolved_symbols=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.unresolved_symbols]),
            macro_events=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.macro_events]),
            organizations=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.organizations]),
            authors=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.authors]),
            books=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.books]),
            concepts=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.concepts]),
            strategies=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.strategies]),
            timeframes=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.timeframes]),
            countries=QueryPlanAssembler._dedupe([value for child in child_plans for value in child.entities.countries]),
        )

    @staticmethod
    def _merge_child_indicators(child_plans: List[QueryPlan]) -> List[IndicatorSpec]:
        return list({item.output_alias: item for child in child_plans for item in child.requested_indicators}.values())

    @staticmethod
    def _aggregate_temporal_scope(child_plans: List[QueryPlan]) -> str:
        priority = ["current", "today", "latest", "upcoming", "custom", "historical", "timeless", "unknown"]
        scopes = {child.temporal_scope for child in child_plans}
        for scope in priority:
            if scope in scopes:
                return scope
        return "unknown"

    @staticmethod
    def _aggregate_user_action(child_plans: List[QueryPlan]) -> str:
        priority = [
            "execution_request",
            "position_sizing",
            "consider_entry",
            "scenario_analysis",
            "market_analysis",
            "comparison",
            "explanation",
            "information",
            "unknown",
        ]
        actions = {child.user_action_intent for child in child_plans}
        for action in priority:
            if action in actions:
                return action
        return "unknown"

    @staticmethod
    def _aggregate_confidence(child_plans: List[QueryPlan], intent: QueryIntent, answer_mode: AnswerMode) -> float:
        if child_plans:
            return round(sum(child.confidence for child in child_plans) / max(len(child_plans), 1), 3)
        return max(float(intent.confidence or 0.0), float(answer_mode.confidence or 0.0))
