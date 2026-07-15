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
    ConsistencyInputAssembler,
    MarketContextAgentRuntime,
    RiskAgentRuntime,
    StrategyAgentRuntime,
    StrategyRiskConsistencyAgentRuntime,
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
        "data": {"symbol": target, "timestamp": "2026-07-11T00:00:00Z"},
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
        request_id="consistency_req",
        user_query="consistency assessment",
        normalized_query="consistency assessment",
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


def consistency_task(parent="task_1"):
    return AgentTaskEnvelope(
        task_id=f"{parent}:StrategyRiskConsistencyAgent",
        parent_task_id=parent,
        agent_type="StrategyRiskConsistencyAgent",
        intent_family="market_state_analysis",
        required=False,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD", "ohlcv:XAUUSD", "technical_snapshot:XAUUSD"],
        dependency_ids=[f"{parent}:StrategyAgent", f"{parent}:RiskAgent"],
    )


def market_context_result(parent="task_1"):
    payload = {
        "request_id": "consistency_req",
        "task_id": f"{parent}:MarketContextAgent",
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "assessment_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "market_state": {"directional_bias": "balanced"},
        "conflicting_signals": [{"signal_a": "macro pressure", "signal_b": "momentum", "explanation": "mixed"}],
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


def strategy_result(parent="task_1", status=AgentStatus.SUCCESS, confidence=0.6):
    payload = {
        "request_id": "consistency_req",
        "task_id": f"{parent}:StrategyAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "intent_family": "market_state_analysis",
        "thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "thesis_type": "mixed",
        "thesis_direction": "mixed",
        "thesis_summary": "Conditional mixed thesis.",
        "conflicting_factors": [{"factor": "macro", "conflict_with": "momentum", "explanation": "mixed"}],
        "activation_conditions": [{"condition": "confirmation improves", "reason": "context"}],
        "invalidation_conditions": [{"condition": "context weakens", "reason": "risk"}],
        "confidence": {"value": confidence, "ceiling": "medium", "rationale": "bounded"},
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
        confidence=confidence,
    )


def risk_result(parent="task_1", status=AgentStatus.SUCCESS, adjusted=0.55, posture="conflicting_context", level="elevated"):
    payload = {
        "request_id": "consistency_req",
        "task_id": f"{parent}:RiskAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-11T00:00:00Z",
        "intent_family": "market_state_analysis",
        "risk_ref": f"risk_assessment:{parent}:RiskAgent",
        "assessed_strategy_thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "assessed_market_context_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "overall_risk_level": level,
        "risk_posture": posture,
        "confidence_adjustment": {
            "original_strategy_confidence": 0.6,
            "adjusted_confidence": adjusted,
            "adjustment_reason": "conflicts",
        },
        "conflicting_factors": [{"factor": "macro", "conflict_with": "momentum", "explanation": "mixed"}],
        "limitations": [],
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{parent}:StrategyAgent"],
    }
    return AgentResultEnvelope(
        task_id=f"{parent}:RiskAgent",
        parent_task_id=parent,
        agent_type="RiskAgent",
        status=status,
        structured_payload=payload,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD"],
        confidence=adjusted,
    )


class BadBackend:
    def __init__(self, mutation):
        self.mutation = mutation

    def produce(self, consistency_input):
        assessment = StrategyRiskConsistencyAgentRuntime().backend.produce(consistency_input).as_dict()
        assessment.update(self.mutation)
        return assessment


class FailingRiskAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.INVALID_RESULT,
            failure_code="AGENT_RESULT_INVALID",
            failure_reason="deterministic risk failure",
            confidence=0.0,
        )


class StrategyRiskConsistencyAgentTests(unittest.TestCase):
    def test_consistency_input_construction_uses_strategy_and_risk(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result()
        rk = risk_result()
        consistency_input = ConsistencyInputAssembler.assemble(
            consistency_task(),
            runtime_context(ctx, {mc.task_id: mc, st.task_id: st, rk.task_id: rk}),
        )

        self.assertEqual(consistency_input.parent_task_id, "task_1")
        self.assertEqual(consistency_input.strategy_thesis_ref, "strategy_thesis:task_1:StrategyAgent")
        self.assertEqual(consistency_input.risk_assessment_ref, "risk_assessment:task_1:RiskAgent")
        self.assertEqual(consistency_input.allowed_evidence_refs, ["evidence_bundle:task_1"])

    def test_consistency_runtime_success_and_confidence_reconciliation(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result(confidence=0.6)
        rk = risk_result(adjusted=0.55)
        envelope = StrategyRiskConsistencyAgentRuntime().execute(
            consistency_task(),
            runtime_context(ctx, {mc.task_id: mc, st.task_id: st, rk.task_id: rk}),
        )

        self.assertEqual(envelope.status, AgentStatus.SUCCESS)
        self.assertEqual(envelope.agent_type, "StrategyRiskConsistencyAgent")
        self.assertLessEqual(envelope.confidence, 0.55)
        self.assertEqual(envelope.structured_payload["final_presentation_mode"], "mixed_or_uncertain")
        self.assertIn("consistency_assessment:", envelope.structured_payload["consistency_ref"])
        self.assertNotIn("entry_price", str(envelope.structured_payload))

    def test_aligned_and_insufficient_modes_are_bounded(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result(confidence=0.6)
        aligned_risk = risk_result(adjusted=0.6, posture="acceptable_with_conditions", level="moderate")
        aligned = StrategyRiskConsistencyAgentRuntime().execute(
            consistency_task(),
            runtime_context(ctx, {mc.task_id: mc, st.task_id: st, aligned_risk.task_id: aligned_risk}),
        )

        self.assertIn(aligned.structured_payload["consistency_status"], {"aligned", "partially_aligned"})
        self.assertIn(aligned.structured_payload["final_presentation_mode"], {"standard_conditional", "cautious_conditional"})

        blocked = StrategyRiskConsistencyAgentRuntime().execute(
            consistency_task(),
            runtime_context(ctx, {mc.task_id: mc, st.task_id: st}),
        )
        self.assertEqual(blocked.status, AgentStatus.INVALID_RESULT)
        self.assertIn("missing_risk_assessment", blocked.failure_reason)

    def test_out_of_scope_refs_confidence_and_forbidden_outputs_fail(self):
        ctx = decision_context()
        mc = market_context_result()
        st = strategy_result()
        rk = risk_result()
        cases = [
            {"consistency_status": "unsupported"},
            {"final_presentation_mode": "unsupported"},
            {"thesis_strength_after_risk": "unsupported"},
            {"evidence_refs": ["evidence_bundle:sibling"]},
            {"market_context_refs": ["market_context_assessment:task_2:MarketContextAgent"]},
            {"strategy_thesis_refs": ["strategy_thesis:task_2:StrategyAgent"]},
            {"risk_assessment_refs": ["risk_assessment:task_2:RiskAgent"]},
            {"entry_price": 2410.0},
            {"stop_loss": 2400.0},
            {"take_profit": 2440.0},
            {"lot_size": 0.01},
            {"account_risk_percent": 1},
            {"final_synthesis_guidance": "buy now"},
            {"final_synthesis_guidance": "risk 1% of account"},
            {"final_synthesis_guidance": "place order in MT5"},
            {"confidence_reconciliation": {"strategy_confidence": 0.6, "risk_adjusted_confidence": 0.55, "final_confidence": 0.7}},
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                envelope = StrategyRiskConsistencyAgentRuntime(BadBackend(mutation)).execute(
                    consistency_task(),
                    runtime_context(ctx, {mc.task_id: mc, st.task_id: st, rk.task_id: rk}),
                )
                self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
                self.assertEqual(envelope.failure_code, "AGENT_RESULT_INVALID")

    def test_dependency_blocks_consistency_when_risk_fails(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        registry.register("RiskAgent", FailingRiskAgent())
        registry.register("StrategyRiskConsistencyAgent", StrategyRiskConsistencyAgentRuntime())
        ctx = decision_context()
        contract = OrchestratorOutput(
            answer_type="market_analysis",
            selected_agents=["MarketContextAgent", "StrategyAgent", "RiskAgent", "StrategyRiskConsistencyAgent"],
            execution_allowed=False,
        )
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, runtime_context(ctx))

        self.assertEqual(results[-2].status, AgentStatus.INVALID_RESULT)
        self.assertEqual(results[-1].status, AgentStatus.DEPENDENCY_BLOCKED)

    def test_observed_multi_intent_shape_plans_consistency_for_market_child_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        registry.register("RiskAgent", RiskAgentRuntime())
        registry.register("StrategyRiskConsistencyAgent", StrategyRiskConsistencyAgentRuntime())
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

        self.assertEqual(
            [task.task_id for task in plan.tasks],
            [
                "task_1:MarketContextAgent",
                "task_1:StrategyAgent",
                "task_1:RiskAgent",
                "task_1:StrategyRiskConsistencyAgent",
            ],
        )
        self.assertEqual(plan.tasks[-1].dependency_ids, ["task_1:StrategyAgent", "task_1:RiskAgent"])
        self.assertNotIn("task_2:StrategyRiskConsistencyAgent", [task.task_id for task in plan.tasks])

    def test_dispatch_handoff_and_prompt_enrichment_include_consistency_for_task_only(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        registry.register("StrategyAgent", StrategyAgentRuntime())
        registry.register("RiskAgent", RiskAgentRuntime())
        registry.register("StrategyRiskConsistencyAgent", StrategyRiskConsistencyAgentRuntime())
        ctx = decision_context()
        contract = OrchestratorOutput(
            answer_type="market_analysis",
            selected_agents=["MarketContextAgent", "StrategyAgent", "RiskAgent", "StrategyRiskConsistencyAgent"],
            execution_allowed=False,
        )
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, runtime_context(ctx))
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", {"handoff": handoff.as_dict()})

        self.assertEqual([result.status for result in results], [AgentStatus.SUCCESS] * 4)
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(
            handoff.consistency_assessments_by_task,
            {"task_1": "consistency_assessment:task_1:StrategyRiskConsistencyAgent"},
        )
        self.assertIn("StrategyRiskConsistency", prompt)
        self.assertIn("task_id=task_1", prompt)
        self.assertNotIn("task_id=task_2", prompt)
        self.assertNotIn("EvidenceItem", prompt)
        self.assertFalse(plan.execution_allowed)

    def test_static_query_excludes_consistency_agent(self):
        registry = AgentRuntimeRegistry()
        registry.register("StrategyRiskConsistencyAgent", StrategyRiskConsistencyAgentRuntime())
        ctx = decision_context(QueryPlan("book", "book", task_id="task_1", primary_intent="book_concept_explanation").as_dict())
        contract = OrchestratorOutput(answer_type="static_explanation", selected_agents=["StaticKnowledgeAgent"], execution_allowed=False)
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertEqual(plan.tasks, [])

    def test_single_intent_contract_selects_consistency_when_runtime_available(self):
        available = [
            "MarketContextAgent",
            "StrategyAgent",
            "RiskAgent",
            "StrategyRiskConsistencyAgent",
            "MarketDataAgent",
            "TechnicalAnalysisAgent",
        ]
        for intent in ["market_state_analysis", "macro_market_impact"]:
            with self.subTest(intent=intent):
                ctx = decision_context(QueryPlan("market", "market", task_id="task_1", primary_intent=intent).as_dict())
                contract = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=available))
                self.assertIn("MarketContextAgent", contract.selected_agents)
                self.assertIn("StrategyAgent", contract.selected_agents)
                self.assertIn("RiskAgent", contract.selected_agents)
                self.assertIn("StrategyRiskConsistencyAgent", contract.selected_agents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
