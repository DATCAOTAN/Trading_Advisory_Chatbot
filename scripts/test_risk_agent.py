import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator import RAGOrchestrator
from src.services.agents import (
    AgentDispatcher,
    AgentExecutionPlanBuilder,
    AgentResultAggregator,
    AgentResultEnvelope,
    AgentRuntimeContext,
    AgentRuntimeRegistry,
    AgentTaskEnvelope,
    MarketContextAgentRuntime,
    RiskAgentRuntime,
    RiskInputAssembler,
    StrategyAgentRuntime,
)
from src.services.agents.runtime import AgentStatus, build_agent_handoff
from src.services.decision_context import DecisionContext
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput, OrchestratorOutput
from src.services.semantic.query_plan import QueryEntities, QueryPlan


def acquisition_result(result_id, capability, target, owner="task_1"):
    return {
        "result_id": result_id,
        "task_id": result_id,
        "capability": capability,
        "target": target,
        "status": "success",
        "requested_by_tasks": [owner],
        "task_ids": [owner],
        "data": {"symbol": target, "timestamp": "2026-07-11T00:00:00Z", "recent_trend": "up"},
        "provenance": {"source": "fixture", "symbol": target, "timestamp": "2026-07-11T00:00:00Z"},
    }


def decision_context(query_plan=None, owner="task_1"):
    query_plan = query_plan or QueryPlan(
        "market",
        "market",
        task_id=owner,
        primary_intent="market_state_analysis",
        temporal_scope="current",
        entities=QueryEntities(symbols=["XAUUSD"]),
    ).as_dict()
    return DecisionContext(
        request_id="risk_req",
        user_query="risk assessment",
        normalized_query="risk assessment",
        query_intent={},
        answer_mode={"mode": "MARKET_ANALYSIS"},
        query_plan=query_plan,
        acquisition_results=[
            acquisition_result("market_snapshot:XAUUSD", "market_snapshot", "XAUUSD", owner),
            acquisition_result("ohlcv:XAUUSD", "ohlcv", "XAUUSD", owner),
            acquisition_result("technical_snapshot:XAUUSD", "technical_snapshot", "XAUUSD", owner),
        ],
        task_context_views=[{"task_id": owner, "sufficiency_status": "COMPLETE", "confidence_ceiling": "medium"}],
        evidence_bundles=[{"task_id": owner, "items": [{"evidence_id": "market_evidence"}]}],
        sufficiency={"status": "COMPLETE", "confidence_ceiling": "medium"},
        evidence_sufficiency={"status": "COMPLETE"},
        confidence_ceiling="medium",
        market_data_required=True,
        technical_snapshot_required=True,
    )


def runtime_context(ctx, prior_results=None):
    return AgentRuntimeContext(
        decision_context_ref=ctx,
        query_plan_ref=ctx.query_plan,
        task_context_refs={item["task_id"]: item for item in ctx.task_context_views},
        acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        evidence_refs={item["task_id"]: item for item in ctx.evidence_bundles},
        metadata={"agent_results_by_task": dict(prior_results or {})},
    )


def risk_task(parent="task_1"):
    return AgentTaskEnvelope(
        task_id=f"{parent}:RiskAgent",
        parent_task_id=parent,
        agent_type="RiskAgent",
        intent_family="market_state_analysis",
        required=False,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD", "ohlcv:XAUUSD", "technical_snapshot:XAUUSD"],
        dependency_ids=[f"{parent}:StrategyAgent"],
    )


def market_context_result(parent="task_1"):
    payload = {
        "request_id": "risk_req",
        "task_id": f"{parent}:MarketContextAgent",
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "assessment_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "market_state": {"directional_bias": "balanced"},
        "dominant_factors": [{"factor": "recent price behavior", "evidence_refs": [f"evidence_bundle:{parent}"]}],
        "conflicting_signals": [{"signal_a": "macro pressure", "signal_b": "momentum", "explanation": "mixed"}],
        "macro_context": {"active_events": ["generic event"]},
        "uncertainty": {"confidence": 0.6, "limitations": [], "missing_context": []},
    }
    return AgentResultEnvelope(
        task_id=f"{parent}:MarketContextAgent",
        parent_task_id=parent,
        agent_type="MarketContextAgent",
        status=AgentStatus.SUCCESS,
        structured_payload=payload,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD"],
        confidence=0.6,
    )


def strategy_result(parent="task_1", status=AgentStatus.SUCCESS):
    payload = {
        "request_id": "risk_req",
        "task_id": f"{parent}:StrategyAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "intent_family": "market_state_analysis",
        "thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "thesis_type": "mixed",
        "thesis_direction": "mixed",
        "thesis_summary": "Conditional mixed thesis.",
        "activation_conditions": [{"condition": "confirmation improves", "reason": "context"}],
        "invalidation_conditions": [{"condition": "context weakens", "reason": "risk"}],
        "conflicting_factors": [{"factor": "macro", "conflict_with": "momentum", "explanation": "mixed"}],
        "assumptions": ["No execution decision is made by StrategyAgent."],
        "limitations": [],
        "missing_context": [],
        "confidence": {"value": 0.6, "ceiling": "medium", "rationale": "bounded"},
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
    }
    return AgentResultEnvelope(
        task_id=f"{parent}:StrategyAgent",
        parent_task_id=parent,
        agent_type="StrategyAgent",
        status=status,
        structured_payload=payload,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD"],
        confidence=0.6,
    )


class BadBackend:
    def __init__(self, mutation):
        self.mutation = mutation

    def produce(self, risk_input):
        assessment = RiskAgentRuntime().backend.produce(risk_input).as_dict()
        assessment.update(self.mutation)
        return assessment


class FailingStrategyAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.INVALID_RESULT,
            failure_code="AGENT_RESULT_INVALID",
            failure_reason="deterministic strategy failure",
            confidence=0.0,
        )


class RiskAgentTests(unittest.TestCase):
    def test_risk_input_construction_uses_strategy_and_market_context(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result()
        risk_input = RiskInputAssembler.assemble(risk_task(), runtime_context(ctx, {mc.task_id: mc, st.task_id: st}))

        self.assertEqual(risk_input.parent_task_id, "task_1")
        self.assertEqual(risk_input.strategy_thesis_ref, "strategy_thesis:task_1:StrategyAgent")
        self.assertEqual(risk_input.market_context_assessment_ref, "market_context_assessment:task_1:MarketContextAgent")
        self.assertEqual(risk_input.allowed_evidence_refs, ["evidence_bundle:task_1"])

    def test_risk_agent_runtime_success_and_adjusted_confidence(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result()
        envelope = RiskAgentRuntime().execute(risk_task(), runtime_context(ctx, {mc.task_id: mc, st.task_id: st}))

        self.assertEqual(envelope.status, AgentStatus.SUCCESS)
        self.assertEqual(envelope.agent_type, "RiskAgent")
        self.assertLessEqual(envelope.confidence, 0.6)
        self.assertIn("risk_assessment:", envelope.structured_payload["risk_ref"])
        self.assertNotIn("lot_size", str(envelope.structured_payload))

    def test_out_of_scope_refs_confidence_and_forbidden_outputs_fail(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result()
        cases = [
            {"evidence_refs": ["evidence_bundle:sibling"]},
            {"market_context_refs": ["market_context_assessment:task_2:MarketContextAgent"]},
            {"strategy_thesis_refs": ["strategy_thesis:task_2:StrategyAgent"]},
            {"entry_price": 2410.0},
            {"stop_loss": 2400.0},
            {"take_profit": 2440.0},
            {"lot_size": 0.01},
            {"account_risk_percent": 1},
            {"risk_summary": "risk 1% of account"},
            {"risk_summary": "buy now"},
            {"risk_summary": "place order in MT5"},
            {"confidence_adjustment": {"original_strategy_confidence": 0.6, "adjusted_confidence": 0.8}},
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                envelope = RiskAgentRuntime(BadBackend(mutation)).execute(risk_task(), runtime_context(ctx, {mc.task_id: mc, st.task_id: st}))
                self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
                self.assertEqual(envelope.failure_code, "AGENT_RESULT_INVALID")

    def test_missing_strategy_thesis_is_invalid_without_dependency_result(self):
        ctx = decision_context()
        mc = market_context_result()
        envelope = RiskAgentRuntime().execute(risk_task(), runtime_context(ctx, {mc.task_id: mc}))

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("missing_strategy_thesis", envelope.failure_reason)

    def test_dependency_blocks_risk_when_strategy_fails(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", FailingStrategyAgent())
        registry.register("RiskAgent", RiskAgentRuntime())
        mc_task = AgentTaskEnvelope(
            task_id="task_1:MarketContextAgent",
            parent_task_id="task_1",
            agent_type="MarketContextAgent",
            intent_family="market_state_analysis",
            evidence_refs=["evidence_bundle:task_1"],
            source_refs=["market_snapshot:XAUUSD"],
        )
        st_task = AgentTaskEnvelope(
            task_id="task_1:StrategyAgent",
            parent_task_id="task_1",
            agent_type="StrategyAgent",
            intent_family="market_state_analysis",
            required=False,
            evidence_refs=["evidence_bundle:task_1"],
            source_refs=["market_snapshot:XAUUSD"],
            dependency_ids=["task_1:MarketContextAgent"],
        )
        rk_task = risk_task()
        plan = type("Plan", (), {
            "request_id": "risk_dep_req",
            "tasks": [mc_task, st_task, rk_task],
            "parallel_groups": [[mc_task.task_id], [st_task.task_id], [rk_task.task_id]],
            "parent_plan_id": "parent",
            "parent_intent": "market_state_analysis",
            "unavailable_agents": [],
        })()

        results = AgentDispatcher(registry).execute(plan, runtime_context(decision_context()))

        self.assertEqual(results[1].status, AgentStatus.INVALID_RESULT)
        self.assertEqual(results[2].status, AgentStatus.DEPENDENCY_BLOCKED)

    def test_observed_multi_intent_shape_plans_risk_for_market_child_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        registry.register("RiskAgent", RiskAgentRuntime())
        parent = QueryPlan(
            "parent",
            "parent",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("macro", "macro", task_id="task_1", primary_intent="macro_market_impact", entities=QueryEntities(symbols=["XAUUSD"])),
                QueryPlan("book", "book", task_id="task_2", primary_intent="book_concept_explanation"),
            ],
        ).as_dict()
        ctx = decision_context(parent)
        contract = OrchestratorOutput(
            answer_type="scenario_analysis",
            selected_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"],
            execution_allowed=False,
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertEqual([task.task_id for task in plan.tasks], ["task_1:MarketContextAgent", "task_1:StrategyAgent", "task_1:RiskAgent"])
        self.assertEqual(plan.tasks[2].dependency_ids, ["task_1:StrategyAgent"])
        self.assertNotIn("task_2:RiskAgent", [task.task_id for task in plan.tasks])

    def test_dispatch_handoff_and_prompt_enrichment_include_risk_for_task_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        registry.register("RiskAgent", RiskAgentRuntime())
        ctx = decision_context()
        contract = OrchestratorOutput(
            answer_type="market_analysis",
            selected_agents=["MarketContextAgent", "StrategyAgent", "RiskAgent"],
            execution_allowed=False,
        )
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, runtime_context(ctx))
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", {"handoff": handoff.as_dict()})

        self.assertEqual([result.status for result in results], [AgentStatus.SUCCESS, AgentStatus.SUCCESS, AgentStatus.SUCCESS])
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(handoff.risk_assessments_by_task, {"task_1": "risk_assessment:task_1:RiskAgent"})
        self.assertIn("RiskAssessment", prompt)
        self.assertIn("task_id=task_1", prompt)
        self.assertNotIn("task_id=task_2", prompt)
        self.assertNotIn("EvidenceItem", prompt)
        self.assertFalse(plan.execution_allowed)

    def test_static_query_excludes_risk_agent(self):
        registry = AgentRuntimeRegistry()
        registry.register("RiskAgent", RiskAgentRuntime())
        ctx = decision_context(QueryPlan("book", "book", task_id="task_1", primary_intent="book_concept_explanation").as_dict())
        contract = OrchestratorOutput(answer_type="static_explanation", selected_agents=["StaticKnowledgeAgent"], execution_allowed=False)
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertEqual(plan.tasks, [])

    def test_single_intent_contract_selects_risk_when_runtime_available(self):
        available = ["MarketContextAgent", "StrategyAgent", "RiskAgent", "MarketDataAgent", "TechnicalAnalysisAgent"]
        for intent in ["market_state_analysis", "macro_market_impact"]:
            with self.subTest(intent=intent):
                ctx = decision_context(QueryPlan("market", "market", task_id="task_1", primary_intent=intent).as_dict())
                contract = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=available))
                self.assertIn("MarketContextAgent", contract.selected_agents)
                self.assertIn("StrategyAgent", contract.selected_agents)
                self.assertIn("RiskAgent", contract.selected_agents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
