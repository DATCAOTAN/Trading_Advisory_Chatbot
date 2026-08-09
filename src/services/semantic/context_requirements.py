from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.semantic.query_plan import QueryPlan
from src.services.trading.market.timeframes import normalize_timeframe
from src.services.trading.reasoning.strategy_evidence import INDICATOR_REGISTRY


@dataclass(frozen=True)
class ContextNeed:
    capability: str
    target: str = ""
    required: bool = True
    required_fields: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    freshness_policy: str = "default"
    max_age_seconds: int = 0
    reason: str = ""
    priority: int = 50

    def key(self) -> tuple:
        return (
            self.capability,
            self.target,
            tuple(sorted(self.required_fields)),
            tuple(sorted((str(k), str(v)) for k, v in self.parameters.items())),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "target": self.target,
            "required": self.required,
            "required_fields": list(self.required_fields),
            "parameters": dict(self.parameters),
            "freshness_policy": self.freshness_policy,
            "max_age_seconds": self.max_age_seconds,
            "reason": self.reason,
            "priority": self.priority,
        }


@dataclass
class ContextRequirements:
    query_plan_id: str
    task_id: str = ""
    needs: List[ContextNeed] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    task_requirements: Dict[str, "ContextRequirements"] = field(default_factory=dict)
    task_need_mapping: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def required_needs(self) -> List[ContextNeed]:
        return [need for need in self.needs if need.required]

    @property
    def optional_needs(self) -> List[ContextNeed]:
        return [need for need in self.needs if not need.required]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "query_plan_id": self.query_plan_id,
            "task_id": self.task_id,
            "needs": [need.as_dict() for need in self.needs],
            "required_needs": [need.as_dict() for need in self.required_needs],
            "optional_needs": [need.as_dict() for need in self.optional_needs],
            "warnings": list(self.warnings),
            "task_requirements": {task_id: req.as_dict() for task_id, req in self.task_requirements.items()},
            "task_need_mapping": {task_id: list(needs) for task_id, needs in self.task_need_mapping.items()},
        }


class SharedContextRequirementsBuilder:
    """Merge child task requirements into one acquisition plan."""

    def build(self, query_plan: QueryPlan, child_requirements: List[ContextRequirements]) -> ContextRequirements:
        merged: Dict[tuple, ContextNeed] = {}
        task_need_mapping: Dict[str, List[str]] = {}
        task_requirements: Dict[str, ContextRequirements] = {}
        total_child_needs = 0

        for index, requirements in enumerate(child_requirements, start=1):
            task_id = requirements.task_id or f"task_{index}"
            task_requirements[task_id] = requirements
            task_need_mapping[task_id] = []
            for need in requirements.needs:
                total_child_needs += 1
                key = self._merge_key(need)
                merged[key] = self._merge_need(merged.get(key), need)
                task_need_mapping[task_id].append(self._need_name(need))

        shared = ContextRequirements(
            query_plan_id=query_plan.plan_id,
            task_id=query_plan.task_id,
            needs=list(merged.values()),
            task_requirements=task_requirements,
            task_need_mapping=task_need_mapping,
        )
        print(
            "[SharedContextRequirements] "
            f"tasks={len(child_requirements)} "
            f"unique_needs={len(shared.needs)} "
            f"deduplicated={max(total_child_needs - len(shared.needs), 0)}"
        )
        return shared

    @staticmethod
    def _merge_key(need: ContextNeed) -> tuple:
        return (
            need.capability,
            need.target,
            tuple(sorted((str(k), str(v)) for k, v in need.parameters.items())),
        )

    @staticmethod
    def _merge_need(existing: ContextNeed | None, incoming: ContextNeed) -> ContextNeed:
        if existing is None:
            return incoming
        fields = []
        for field_name in list(existing.required_fields) + list(incoming.required_fields):
            if field_name not in fields:
                fields.append(field_name)
        reason_parts = [existing.reason, incoming.reason]
        reason = "; ".join(part for part in reason_parts if part)
        max_age_values = [value for value in [existing.max_age_seconds, incoming.max_age_seconds] if value]
        return ContextNeed(
            capability=existing.capability,
            target=existing.target,
            required=existing.required or incoming.required,
            required_fields=fields,
            parameters=dict(existing.parameters or incoming.parameters),
            freshness_policy=incoming.freshness_policy if existing.freshness_policy == "default" else existing.freshness_policy,
            max_age_seconds=min(max_age_values) if max_age_values else 0,
            reason=reason,
            priority=min(existing.priority, incoming.priority),
        )

    @staticmethod
    def _need_name(need: ContextNeed) -> str:
        return f"{need.capability}:{need.target or 'default'}"


class ContextRequirementPlanner:
    """Declarative requirement policies for semantic intent classes."""

    DEFAULT_MARKET_MAX_AGE_SECONDS = 60
    DEFAULT_OHLCV_MAX_AGE_SECONDS = 300
    DEFAULT_CALENDAR_MAX_AGE_SECONDS = 900

    def plan(self, query_plan: QueryPlan) -> ContextRequirements:
        needs: List[ContextNeed] = []
        primary = query_plan.primary_intent

        if primary == "book_concept_explanation":
            needs.append(
                self._need(
                    "static_knowledge",
                    self._knowledge_target(query_plan),
                    True,
                    "book concept explanation",
                    parameters=self._knowledge_constraints(query_plan),
                )
            )

        elif primary == "conversational_strategy_request":
            pass

        elif primary == "multi_intent":
            if query_plan.child_plans:
                child_requirements = [self.plan(child) for child in query_plan.child_plans]
                return SharedContextRequirementsBuilder().build(query_plan, child_requirements)
            warnings = ["multi_intent_missing_child_plans"]
            requirements = ContextRequirements(query_plan_id=query_plan.plan_id, task_id=query_plan.task_id, warnings=warnings)
            self._log(requirements)
            return requirements

        elif primary == "macro_report_summary":
            needs.append(self._need("official_report", self._event_target(query_plan), True, "macro/report summary"))

        elif primary == "macro_market_impact":
            symbol = self._symbol_target(query_plan)
            event = self._event_target(query_plan)
            indicators = [item.as_dict() for item in query_plan.requested_indicators]
            parameters = self._market_parameters(query_plan) if indicators else {}
            needs.extend(
                [
                    self._need("official_report", event, True, "macro market impact evidence"),
                    self._need(
                        "economic_event",
                        event,
                        True,
                        "macro event actual/forecast/previous context",
                        fields=["actual", "forecast", "previous", "release_time"],
                        freshness="latest_available",
                        max_age=self.DEFAULT_CALENDAR_MAX_AGE_SECONDS,
                    ),
                    self._need(
                        "market_snapshot",
                        symbol,
                        True,
                        "current market snapshot for impacted symbol",
                        freshness="fresh",
                        max_age=self.DEFAULT_MARKET_MAX_AGE_SECONDS,
                        parameters={"timeframe": parameters["timeframe"]} if parameters else {},
                    ),
                    self._need(
                        "ohlcv",
                        symbol,
                        bool(indicators),
                        "requested technical market reaction window" if indicators else "optional market reaction window",
                        freshness="fresh",
                        max_age=self.DEFAULT_OHLCV_MAX_AGE_SECONDS,
                        parameters={**parameters, "indicators": indicators} if indicators else {},
                    ),
                    self._need("market_knowledge", "gold" if symbol == "XAUUSD" else symbol, False, "optional market background"),
                ]
            )
            if indicators:
                needs.append(
                    self._need(
                        "technical_snapshot",
                        symbol,
                        True,
                        "requested deterministic technical state",
                        parameters={**parameters, "indicators": indicators},
                    )
                )

        elif primary == "market_state_analysis":
            symbol = self._symbol_target(query_plan)
            indicators = [item.as_dict() for item in query_plan.requested_indicators]
            parameters = self._market_parameters(query_plan) if indicators else {}
            needs.extend(
                [
                    self._need(
                        "market_snapshot",
                        symbol,
                        True,
                        "current market state",
                        freshness="fresh",
                        max_age=self.DEFAULT_MARKET_MAX_AGE_SECONDS,
                        parameters={"timeframe": parameters["timeframe"]} if parameters else {},
                    ),
                    self._need(
                        "ohlcv",
                        symbol,
                        True,
                        "recent OHLCV market context",
                        freshness="fresh",
                        max_age=self.DEFAULT_OHLCV_MAX_AGE_SECONDS,
                        parameters={**parameters, "indicators": indicators} if indicators else {},
                    ),
                    self._need(
                        "technical_snapshot",
                        symbol,
                        bool(indicators),
                        "requested deterministic technical state" if indicators else "optional technical state",
                        parameters={**parameters, "indicators": indicators} if indicators else {},
                    ),
                    self._need("economic_event", "macro", False, "optional nearby macro event context"),
                ]
            )
            if query_plan.conceptual_request:
                needs.append(
                    self._need(
                        "static_knowledge",
                        self._knowledge_target(query_plan),
                        True,
                        "concept portion of mixed market request",
                        parameters=self._knowledge_constraints(query_plan),
                    )
                )

        elif primary == "trade_opportunity_analysis":
            symbol = self._symbol_target(query_plan)
            needs.extend(
                [
                    self._need(
                        "market_snapshot",
                        symbol,
                        True,
                        "live market data for trade scenario",
                        freshness="fresh",
                        max_age=self.DEFAULT_MARKET_MAX_AGE_SECONDS,
                    ),
                    self._need(
                        "ohlcv",
                        symbol,
                        True,
                        "OHLCV context for trade scenario",
                        freshness="fresh",
                        max_age=self.DEFAULT_OHLCV_MAX_AGE_SECONDS,
                    ),
                    self._need(
                        "economic_event",
                        "macro",
                        True,
                        "event risk around possible entry",
                        freshness="acceptable",
                        max_age=self.DEFAULT_CALENDAR_MAX_AGE_SECONDS,
                    ),
                    self._need("technical_snapshot", symbol, False, "optional technical confirmation"),
                    self._need("static_knowledge", "trading_framework", False, "optional static framework"),
                    self._need("account_state", "account", False, "optional risk constraints for position sizing"),
                ]
            )

        elif primary == "position_sizing":
            symbol = self._symbol_target(query_plan)
            needs.extend(
                [
                    self._need("account_state", "account", True, "account balance and exposure"),
                    self._need("instrument_spec", symbol, True, "instrument tick/lot constraints"),
                    self._need("stop_distance", symbol, True, "stop distance is needed before sizing"),
                    self._need("risk_limit", "account", True, "max risk per trade policy"),
                ]
            )

        elif primary in {"position_state_read", "position_management"}:
            symbol = self._symbol_target(query_plan)
            needs.append(
                self._need(
                    "position_read",
                    symbol or "account",
                    True,
                    "authoritative current position, pending-order, P/L, history, provenance, and management target state",
                    freshness="fresh",
                    max_age=self.DEFAULT_MARKET_MAX_AGE_SECONDS,
                    parameters={
                        "requested_data": list(query_plan.constraints.get("requested_data", [])),
                        "context_references": list(query_plan.constraints.get("context_references", [])),
                    },
                )
            )

        else:
            needs.append(self._need("static_knowledge", "general", False, "unknown intent fallback"))

        requirements = ContextRequirements(
            query_plan_id=query_plan.plan_id,
            task_id=query_plan.task_id or "task_1",
            needs=self._dedupe(needs),
        )
        self._log(requirements)
        return requirements

    @staticmethod
    def _log(requirements: ContextRequirements) -> None:
        task = f" task_id={requirements.task_id}" if requirements.task_id else ""
        print(
            f"[ContextRequirements]{task} "
            f"required={[need.capability + ':' + need.target for need in requirements.required_needs]} "
            f"optional={[need.capability + ':' + need.target for need in requirements.optional_needs]}"
        )

    @staticmethod
    def _need(
        capability: str,
        target: str,
        required: bool,
        reason: str,
        fields: List[str] = None,
        parameters: Dict[str, Any] = None,
        freshness: str = "default",
        max_age: int = 0,
        priority: int = 50,
    ) -> ContextNeed:
        return ContextNeed(
            capability=capability,
            target=target,
            required=required,
            required_fields=list(fields or []),
            parameters=dict(parameters or {}),
            freshness_policy=freshness,
            max_age_seconds=max_age,
            reason=reason,
            priority=priority,
        )

    @staticmethod
    def _symbol_target(query_plan: QueryPlan) -> str:
        return query_plan.entities.symbols[0] if query_plan.entities.symbols else ""

    @staticmethod
    def _market_parameters(query_plan: QueryPlan) -> Dict[str, Any]:
        timeframe = normalize_timeframe(
            query_plan.requested_indicators[0].timeframe
            if query_plan.requested_indicators
            else (query_plan.entities.timeframes[0] if query_plan.entities.timeframes else "H1")
        )
        required_bars = 100
        if query_plan.requested_indicators:
            required_bars = max(
                (
                    INDICATOR_REGISTRY[item.indicator_id].warmup(item.parameter_map())
                    for item in query_plan.requested_indicators
                    if item.indicator_id in INDICATOR_REGISTRY
                ),
                default=100,
            )
        return {"timeframe": timeframe, "limit": required_bars}

    @staticmethod
    def _event_target(query_plan: QueryPlan) -> str:
        if query_plan.entities.macro_events:
            return query_plan.entities.macro_events[0]
        organizations = query_plan.entities.organizations
        if "World Gold Council" in organizations:
            return "GOLD_MARKET"
        if "World Bank" in organizations:
            return "COMMODITY_MARKETS"
        return "macro"

    @staticmethod
    def _knowledge_target(query_plan: QueryPlan) -> str:
        if query_plan.entities.concepts:
            return query_plan.entities.concepts[0]
        if query_plan.entities.strategies:
            return query_plan.entities.strategies[0]
        if query_plan.entities.books:
            return query_plan.entities.books[0]
        return "static_knowledge"

    @staticmethod
    def _knowledge_constraints(query_plan: QueryPlan) -> Dict[str, Any]:
        constraints: Dict[str, Any] = {}
        if query_plan.entities.authors:
            constraints["author"] = query_plan.entities.authors[0]
        if query_plan.entities.books:
            constraints["book"] = query_plan.entities.books[0]
        if query_plan.entities.concepts:
            constraints["concept"] = query_plan.entities.concepts[0]
        if query_plan.entities.strategies:
            constraints["strategy"] = query_plan.entities.strategies[0]
        return constraints

    @staticmethod
    def _dedupe(needs: List[ContextNeed]) -> List[ContextNeed]:
        output: List[ContextNeed] = []
        seen = set()
        for need in needs:
            key = need.key()
            if key in seen:
                continue
            seen.add(key)
            output.append(need)
        return output
