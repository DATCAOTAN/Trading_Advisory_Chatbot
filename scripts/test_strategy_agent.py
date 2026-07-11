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
    StrategyAgentRuntime,
    StrategyInputAssembler,
    StrategyThesis,
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
        "data": {
            "symbol": target if capability == "market_snapshot" else "XAUUSD",
            "timestamp": "2026-07-11T00:00:00Z",
            "recent_trend": "up",
            "ohlcv_summary": {"first_close": 2400.0, "last_close": 2410.0},
        },
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
        request_id="strategy_req",
        user_query="market thesis",
        normalized_query="market thesis",
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


def strategy_task(parent="task_1", evidence_refs=None, source_refs=None):
    return AgentTaskEnvelope(
        task_id=f"{parent}:StrategyAgent",
        parent_task_id=parent,
        agent_type="StrategyAgent",
        intent_family="market_state_analysis",
        required=False,
        evidence_refs=evidence_refs or [f"evidence_bundle:{parent}"],
        source_refs=source_refs or ["market_snapshot:XAUUSD", "ohlcv:XAUUSD", "technical_snapshot:XAUUSD"],
        dependency_ids=[f"{parent}:MarketContextAgent"],
    )


def market_context_result(parent="task_1", status=AgentStatus.SUCCESS):
    payload = {
        "request_id": "strategy_req",
        "task_id": f"{parent}:MarketContextAgent",
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "assessment_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "market_state": {"directional_bias": "balanced"},
        "dominant_factors": [
            {
                "factor": "recent price behavior",
                "category": "market",
                "directional_pressure": "neutral",
                "support_strength": "adequate",
                "evidence_refs": [f"evidence_bundle:{parent}"],
            }
        ],
        "conflicting_signals": [],
        "confirmation_conditions": {"neutral_or_range_confirmation": "Evidence remains balanced."},
        "invalidation_conditions": ["Supplied context becomes one-sided."],
        "uncertainty": {"confidence": 0.6, "limitations": [], "missing_context": []},
    }
    return AgentResultEnvelope(
        task_id=f"{parent}:MarketContextAgent",
        parent_task_id=parent,
        agent_type="MarketContextAgent",
        status=status,
        structured_payload=payload,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD"],
        confidence=0.6,
    )


class BadBackend:
    def __init__(self, mutation):
        self.mutation = mutation

    def produce(self, strategy_input):
        thesis = StrategyAgentRuntime().backend.produce(strategy_input).as_dict()
        thesis.update(self.mutation)
        return thesis


class FailingMarketContextAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.INVALID_RESULT,
            failure_code="AGENT_RESULT_INVALID",
            failure_reason="deterministic market context failure",
            confidence=0.0,
        )


class StrategyAgentTests(unittest.TestCase):
    def test_strategy_input_construction_uses_market_context_assessment(self):
        ctx = decision_context()
        mc = market_context_result()
        task = strategy_task()
        strategy_input = StrategyInputAssembler.assemble(task, runtime_context(ctx, {mc.task_id: mc}))

        self.assertEqual(strategy_input.parent_task_id, "task_1")
        self.assertEqual(strategy_input.market_context_assessment_ref, "market_context_assessment:task_1:MarketContextAgent")
        self.assertEqual(strategy_input.allowed_evidence_refs, ["evidence_bundle:task_1"])
        self.assertEqual(strategy_input.confidence_ceiling, "medium")

    def test_strategy_agent_runtime_success_and_confidence_ceiling(self):
        ctx = decision_context()
        mc = market_context_result()
        envelope = StrategyAgentRuntime().execute(strategy_task(), runtime_context(ctx, {mc.task_id: mc}))

        self.assertEqual(envelope.status, AgentStatus.SUCCESS)
        self.assertEqual(envelope.agent_type, "StrategyAgent")
        self.assertLessEqual(envelope.confidence, 0.65)
        self.assertIn("strategy_thesis:", envelope.structured_payload["thesis_ref"])
        self.assertNotIn("entry_price", str(envelope.structured_payload))

    def test_out_of_scope_refs_and_forbidden_outputs_fail(self):
        ctx = decision_context()
        mc = market_context_result()
        cases = [
            {"evidence_refs": ["evidence_bundle:sibling"]},
            {"market_context_refs": ["market_context_assessment:task_2:MarketContextAgent"]},
            {"entry_price": 2410.0},
            {"activation_conditions": [{"condition": "buy now", "reason": "invalid"}]},
            {"invalidation_conditions": [{"condition": "stop-loss at 2400", "reason": "invalid"}]},
            {"scenario_map": {"mt5_action": "place_order"}},
            {"confidence": {"value": 0.9, "ceiling": "medium", "rationale": "too high"}},
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                envelope = StrategyAgentRuntime(BadBackend(mutation)).execute(strategy_task(), runtime_context(ctx, {mc.task_id: mc}))
                self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
                self.assertEqual(envelope.failure_code, "AGENT_RESULT_INVALID")

    def test_missing_market_context_assessment_is_invalid_without_dependency_result(self):
        ctx = decision_context()
        envelope = StrategyAgentRuntime().execute(strategy_task(), runtime_context(ctx))

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("missing_market_context_assessment", envelope.failure_reason)

    def test_dependency_blocks_strategy_when_market_context_fails(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", FailingMarketContextAgent())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        mc_task = AgentTaskEnvelope(
            task_id="task_1:MarketContextAgent",
            parent_task_id="task_1",
            agent_type="MarketContextAgent",
            intent_family="market_state_analysis",
            evidence_refs=["evidence_bundle:task_1"],
            source_refs=["market_snapshot:XAUUSD"],
        )
        st_task = strategy_task()
        plan = type("Plan", (), {
            "request_id": "dep_req",
            "tasks": [mc_task, st_task],
            "parallel_groups": [[mc_task.task_id], [st_task.task_id]],
            "parent_plan_id": "parent",
            "parent_intent": "market_state_analysis",
            "unavailable_agents": [],
        })()

        results = AgentDispatcher(registry).execute(plan, runtime_context(decision_context()))

        self.assertEqual(results[0].status, AgentStatus.INVALID_RESULT)
        self.assertEqual(results[1].status, AgentStatus.DEPENDENCY_BLOCKED)

    def test_observed_multi_intent_shape_plans_strategy_for_market_child_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
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

        self.assertEqual([task.task_id for task in plan.tasks], ["task_1:MarketContextAgent", "task_1:StrategyAgent"])
        self.assertEqual(plan.tasks[1].dependency_ids, ["task_1:MarketContextAgent"])
        self.assertEqual(plan.tasks[1].parent_task_id, "task_1")
        self.assertNotIn("task_2:StrategyAgent", [task.task_id for task in plan.tasks])

    def test_dispatch_handoff_and_prompt_enrichment_include_strategy_thesis_for_task_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        ctx = decision_context()
        contract = OrchestratorOutput(
            answer_type="market_analysis",
            selected_agents=["MarketContextAgent", "StrategyAgent"],
            execution_allowed=False,
        )
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, runtime_context(ctx))
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", {"handoff": handoff.as_dict()})

        self.assertEqual([result.status for result in results], [AgentStatus.SUCCESS, AgentStatus.SUCCESS])
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(handoff.strategy_theses_by_task, {"task_1": "strategy_thesis:task_1:StrategyAgent"})
        self.assertIn("StrategyThesis", prompt)
        self.assertIn("task_id=task_1", prompt)
        self.assertNotIn("task_id=task_2", prompt)
        self.assertNotIn("EvidenceItem", prompt)
        self.assertFalse(plan.execution_allowed)

    def test_static_query_excludes_strategy_agent(self):
        registry = AgentRuntimeRegistry()
        registry.register("StrategyAgent", StrategyAgentRuntime())
        ctx = decision_context(QueryPlan("book", "book", task_id="task_1", primary_intent="book_concept_explanation").as_dict())
        contract = OrchestratorOutput(answer_type="static_explanation", selected_agents=["StaticKnowledgeAgent"], execution_allowed=False)
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertEqual(plan.tasks, [])

    def test_single_intent_contract_selects_strategy_when_runtime_available(self):
        available = ["MarketContextAgent", "StrategyAgent", "MarketDataAgent", "TechnicalAnalysisAgent"]
        for intent in ["market_state_analysis", "macro_market_impact"]:
            with self.subTest(intent=intent):
                ctx = decision_context(QueryPlan("market", "market", task_id="task_1", primary_intent=intent).as_dict())
                contract = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=available))
                self.assertIn("MarketContextAgent", contract.selected_agents)
                self.assertIn("StrategyAgent", contract.selected_agents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
