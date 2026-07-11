from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.decision_context import DecisionContext


def _ordered_unique(items: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def select_agents_for_intent(intent_family: str) -> List[str]:
    """Return semantic agent candidates for an intent family.

    This is intentionally intent-based, not entity- or query-string based.
    Some entries are legacy metadata/runtime-compatible names; the runtime
    registry still decides which ones are executable in production.
    """
    intent = str(intent_family or "")
    if intent in {"book_concept_explanation", "macro_report_summary"}:
        return ["StaticKnowledgeAgent"]
    if intent == "macro_market_impact":
        return ["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent", "MarketContextAgent", "StrategyAgent", "RiskAgent"]
    if intent == "market_state_analysis":
        return ["MarketDataAgent", "TechnicalAnalysisAgent", "MarketContextAgent", "StrategyAgent", "RiskAgent"]
    if intent == "trade_opportunity_analysis":
        return ["MarketDataAgent", "TechnicalAnalysisAgent", "RiskAgent"]
    if intent == "position_sizing":
        return ["RiskAgent"]
    return []


@dataclass
class OrchestratorInput:
    decision_context: DecisionContext
    user_intent: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Any] = field(default_factory=dict)
    available_agents: List[str] = field(default_factory=list)


@dataclass
class OrchestratorOutput:
    answer_type: str
    selected_agents: List[str] = field(default_factory=list)
    reasoning_sections: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    execution_allowed: bool = False
    next_actions: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "answer_type": self.answer_type,
            "selected_agents": list(self.selected_agents),
            "reasoning_sections": list(self.reasoning_sections),
            "source_refs": list(self.source_refs),
            "risk_warnings": list(self.risk_warnings),
            "execution_allowed": self.execution_allowed,
            "next_actions": list(self.next_actions),
        }


class OrchestratorContractBuilder:
    """Select the advisory contract for future multi-agent orchestration."""

    def build(self, orchestrator_input: OrchestratorInput) -> OrchestratorOutput:
        ctx = orchestrator_input.decision_context
        answer_type = self._answer_type(ctx)
        selected_agents = self._selected_agents(ctx, orchestrator_input.available_agents)
        risk_warnings = self._risk_warnings(ctx)
        output = OrchestratorOutput(
            answer_type=answer_type,
            selected_agents=selected_agents,
            reasoning_sections=self._reasoning_sections(ctx),
            source_refs=self._source_refs(ctx),
            risk_warnings=risk_warnings,
            execution_allowed=False,
            next_actions=self._next_actions(ctx, answer_type),
        )
        print(
            "[OrchestratorContract] "
            f"primary_intent={self._primary_intent(ctx)} "
            f"sufficiency={self._sufficiency_status(ctx)} "
            f"answer_type={output.answer_type} "
            f"selected_agents={output.selected_agents} "
            f"execution_allowed={str(output.execution_allowed).lower()}"
        )
        return output

    @staticmethod
    def _answer_type(ctx: DecisionContext) -> str:
        primary_intent = OrchestratorContractBuilder._primary_intent(ctx)
        sufficiency = OrchestratorContractBuilder._sufficiency_status(ctx)
        if sufficiency in {"BLOCKED", "INSUFFICIENT"}:
            return "insufficient_context"
        if primary_intent == "multi_intent":
            return OrchestratorContractBuilder._multi_intent_answer_type(ctx, sufficiency)
        if primary_intent in {"book_concept_explanation", "multi_intent"}:
            return "static_explanation"
        if primary_intent == "macro_report_summary":
            return "report_summary"
        if primary_intent == "market_state_analysis":
            return "market_analysis" if sufficiency in {"COMPLETE", "DEGRADED"} else "insufficient_context"
        if primary_intent == "macro_market_impact":
            return "scenario_analysis" if sufficiency in {"COMPLETE", "DEGRADED"} else "insufficient_context"
        if primary_intent == "trade_opportunity_analysis":
            if "risk_context" in ctx.missing_context or "risk_context" in ctx.missing_required_context:
                return "trade_plan_draft_without_position_size"
            return "trade_plan_draft" if sufficiency in {"COMPLETE", "DEGRADED"} else "insufficient_context"
        if primary_intent == "position_sizing":
            return "insufficient_context" if sufficiency in {"BLOCKED", "INSUFFICIENT"} else "trade_plan_draft_without_position_size"

        mode = str(ctx.answer_mode.get("mode", "UNKNOWN"))
        if ctx.execution_gate_required and "risk_context" in ctx.missing_context:
            return "trade_plan_draft_without_position_size"
        if ctx.missing_context and not ctx.market_snapshot and ctx.market_data_required:
            return "insufficient_context"
        if mode in {"REPORT_SUMMARY", "REPORT_NUMBERS", "REPORT_METHODOLOGY", "BOOK_CONCEPT_EXPLANATION", "MULTI_INTENT"}:
            return "static_explanation"
        if mode == "MARKET_IMPACT":
            return "scenario_analysis" if ctx.static_knowledge_required else "market_analysis"
        if ctx.execution_gate_required:
            return "trade_plan_draft"
        if ctx.market_data_required:
            return "market_analysis"
        if ctx.missing_context:
            return "insufficient_context"
        return "static_explanation"

    @staticmethod
    def _primary_intent(ctx: DecisionContext) -> str:
        query_plan = ctx.query_plan or {}
        return str(query_plan.get("primary_intent") or "")

    @staticmethod
    def _sufficiency_status(ctx: DecisionContext) -> str:
        sufficiency = ctx.sufficiency or {}
        return str(sufficiency.get("status") or "")

    @staticmethod
    def _child_intents(ctx: DecisionContext) -> List[str]:
        query_plan = ctx.query_plan or {}
        child_plans = query_plan.get("child_plans") or []
        return [str(child.get("primary_intent") or "") for child in child_plans if isinstance(child, dict)]

    @staticmethod
    def _multi_intent_answer_type(ctx: DecisionContext, sufficiency: str) -> str:
        child_intents = set(OrchestratorContractBuilder._child_intents(ctx))
        if "position_sizing" in child_intents and sufficiency in {"BLOCKED", "INSUFFICIENT"}:
            return "insufficient_context"
        if "trade_opportunity_analysis" in child_intents:
            return "trade_plan_draft_without_position_size"
        if "macro_market_impact" in child_intents:
            return "scenario_analysis" if sufficiency in {"COMPLETE", "DEGRADED"} else "insufficient_context"
        if "market_state_analysis" in child_intents:
            return "market_analysis" if sufficiency in {"COMPLETE", "DEGRADED"} else "insufficient_context"
        if "macro_report_summary" in child_intents and "book_concept_explanation" in child_intents:
            return "multi_analysis"
        if child_intents and child_intents <= {"book_concept_explanation"}:
            return "static_explanation"
        return "static_explanation" if sufficiency in {"COMPLETE", "DEGRADED", ""} else "insufficient_context"

    @staticmethod
    def _selected_agents(ctx: DecisionContext, available_agents: List[str]) -> List[str]:
        desired = []
        primary_intent = OrchestratorContractBuilder._primary_intent(ctx)
        query_plan = ctx.query_plan or {}
        child_plans = query_plan.get("child_plans") or []
        if ctx.static_knowledge_required:
            desired.append("StaticKnowledgeAgent")
        if ctx.market_data_required:
            desired.append("MarketDataAgent")
        if primary_intent == "multi_intent" and child_plans:
            for child in child_plans:
                if isinstance(child, dict):
                    desired.extend(select_agents_for_intent(str(child.get("primary_intent") or "")))
        else:
            desired.extend(select_agents_for_intent(primary_intent))
        if ctx.market_data_required and str(ctx.answer_mode.get("mode", "")) == "MARKET_IMPACT":
            desired.append("MarketContextAgent")
        if ctx.economic_calendar_required:
            desired.append("CalendarAgent")
        if ctx.technical_snapshot_required:
            desired.append("TechnicalAnalysisAgent")
        if ctx.risk_context_required:
            desired.append("RiskAgent")
        if ctx.execution_gate_required:
            desired.append("ExecutionGateAgent")
        if not available_agents:
            return _ordered_unique(desired)
        allowed = set(available_agents)
        return [agent for agent in _ordered_unique(desired) if agent in allowed]

    @staticmethod
    def _source_refs(ctx: DecisionContext) -> List[str]:
        refs = []
        acquisition_results = ctx.acquisition_results or []
        for result in acquisition_results:
            if not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue
            if result.get("capability") not in {"official_report", "static_knowledge", "market_knowledge"}:
                continue
            provenance = result.get("provenance") or {}
            title = provenance.get("title") or provenance.get("source") or ""
            owner = provenance.get("organization") or provenance.get("author") or ""
            ref = f"{title} - {owner}" if title and owner else title
            if ref and ref not in refs:
                refs.append(ref)
        if acquisition_results:
            return refs
        return list(ctx.retrieved_sources.primary_sources + ctx.retrieved_sources.supporting_sources)

    @staticmethod
    def _reasoning_sections(ctx: DecisionContext) -> List[str]:
        sections = []
        if ctx.static_knowledge_required:
            sections.append("static_knowledge")
        if ctx.market_data_required:
            sections.append("market_snapshot")
        if ctx.economic_calendar_required:
            sections.append("economic_calendar")
        if ctx.technical_snapshot_required:
            sections.append("technical_state")
        if ctx.risk_context_required:
            sections.append("risk_constraints")
        if ctx.missing_context:
            sections.append("missing_context")
        return sections

    @staticmethod
    def _risk_warnings(ctx: DecisionContext) -> List[str]:
        warnings = list(ctx.warnings)
        if "risk_context" in ctx.missing_context:
            warnings.append("Risk context is missing; do not provide position size.")
        if ctx.market_data_required and not ctx.market_snapshot:
            warnings.append("Market data is missing or stale; do not make live-market claims.")
        warnings.append("Execution is disabled unless explicit permission and execution gate approval are provided.")
        return warnings

    @staticmethod
    def _next_actions(ctx: DecisionContext, answer_type: str) -> List[str]:
        actions = []
        if "risk_context" in ctx.missing_context:
            actions.append("collect_account_risk_constraints")
        if "market_data" in ctx.missing_context:
            actions.append("refresh_existing_market_data")
        if "economic_calendar" in ctx.missing_context:
            actions.append("refresh_existing_calendar_data")
        if answer_type == "trade_plan_draft_without_position_size":
            actions.append("draft_without_position_size")
        return actions
