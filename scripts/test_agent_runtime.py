import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents import (
    AgentDispatcher,
    AgentExecutionPlan,
    AgentExecutionPlanBuilder,
    AgentHandoffContext,
    AgentResultAggregator,
    AgentResultEnvelope,
    AgentRuntimeContext,
    AgentRuntimeRegistry,
    AgentTaskEnvelope,
)
from src.services.agents.runtime import AgentStatus, build_agent_handoff
from src.services.decision_context import DecisionContext
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput, OrchestratorOutput
from src.services.semantic.query_plan import QueryPlan


class SuccessAgent:
    def __init__(self, confidence=0.9):
        self.calls = 0
        self.confidence = confidence

    def execute(self, task, context):
        self.calls += 1
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.SUCCESS,
            structured_payload={"observations": ["ok"]},
            summary="structured result",
            evidence_refs=list(task.evidence_refs),
            confidence=self.confidence,
        )


class MarketContextSuccessAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.SUCCESS,
            structured_payload={
                "assessment_ref": f"market_context_assessment:{task.task_id}",
                "market_state": {"directional_bias": "balanced"},
            },
            summary="market context assessment",
            evidence_refs=list(task.evidence_refs),
            source_refs=list(task.source_refs),
            confidence=0.7,
        )


class PartialAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.PARTIAL,
            summary="partial result",
            evidence_refs=list(task.evidence_refs),
            confidence=0.5,
            warnings=["partial agent output"],
        )


class FailingAgent:
    def execute(self, task, context):
        raise RuntimeError("deterministic failure")


class InvalidEvidenceAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.SUCCESS,
            summary="leaks sibling evidence",
            evidence_refs=["evidence_bundle:sibling_task"],
            confidence=0.8,
        )


class ExecutionInstructionAgent:
    def execute(self, task, context):
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.SUCCESS,
            structured_payload={"execution_allowed": True},
            summary="place_order now",
            confidence=0.8,
        )


class SlowAgent:
    def execute(self, task, context):
        time.sleep(0.2)
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=task.agent_type,
            status=AgentStatus.SUCCESS,
            confidence=0.9,
        )


def make_decision_context(query_plan, request_id="agent_test"):
    return DecisionContext(
        request_id=request_id,
        user_query="test",
        normalized_query="test",
        query_intent={},
        answer_mode={},
        query_plan=query_plan,
        sufficiency={"status": "COMPLETE"},
        evidence_sufficiency={"status": "COMPLETE"},
        acquisition_results=[],
        task_context_views=[{"task_id": "task_1", "sufficiency_status": "COMPLETE"}],
        evidence_bundles=[{"task_id": "task_1", "items": []}],
        static_knowledge_required=True,
    )


def make_plan(tasks, request_id="agent_req"):
    return AgentExecutionPlan(
        request_id=request_id,
        parent_plan_id="parent",
        parent_intent="test_intent",
        tasks=list(tasks),
        dependency_graph={task.task_id: list(task.dependency_ids) for task in tasks},
        parallel_groups=AgentExecutionPlanBuilder._parallel_groups(tasks),
        execution_allowed=False,
    )


class AgentRuntimeTests(unittest.TestCase):
    def test_agent_execution_plan_constructs_available_tasks_and_unavailable_agents(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        contract = OrchestratorOutput(
            answer_type="static_explanation",
            selected_agents=["StaticKnowledgeAgent", "MarketDataAgent"],
            execution_allowed=False,
        )
        ctx = make_decision_context(QueryPlan("q", "q", task_id="task_1", primary_intent="book_concept_explanation").as_dict())

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertEqual([task.agent_type for task in plan.tasks], ["StaticKnowledgeAgent"])
        self.assertEqual(plan.unavailable_agents, ["MarketDataAgent"])
        self.assertFalse(plan.execution_allowed)
        self.assertEqual(plan.tasks[0].input_refs, ["decision_context", "query_plan", "orchestrator_contract"])

    def test_empty_or_unavailable_agent_plan_is_backward_compatible(self):
        contract = OrchestratorOutput(
            answer_type="market_analysis",
            selected_agents=["MarketDataAgent"],
            execution_allowed=False,
        )
        ctx = make_decision_context(QueryPlan("q", "q", task_id="task_1", primary_intent="market_state_analysis").as_dict())

        plan = AgentExecutionPlanBuilder(AgentRuntimeRegistry()).build(contract, ctx)
        results = AgentDispatcher(AgentRuntimeRegistry()).execute(plan, AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)

        self.assertEqual(plan.tasks, [])
        self.assertEqual(plan.unavailable_agents, ["MarketDataAgent"])
        self.assertEqual(aggregate.status, "SKIPPED")
        self.assertEqual(handoff.agent_execution_status, "SKIPPED")

    def test_successful_task_dispatch_returns_structured_result(self):
        registry = AgentRuntimeRegistry()
        runtime = SuccessAgent()
        registry.register("StaticKnowledgeAgent", runtime)
        task = AgentTaskEnvelope(
            task_id="task_1:StaticKnowledgeAgent",
            parent_task_id="task_1",
            agent_type="StaticKnowledgeAgent",
            evidence_refs=["evidence_bundle:task_1"],
        )

        results = AgentDispatcher(registry).execute(make_plan([task]), AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(make_plan([task]), results)

        self.assertEqual(results[0].status, AgentStatus.SUCCESS)
        self.assertEqual(results[0].structured_payload["observations"], ["ok"])
        self.assertEqual(results[0].evidence_refs, ["evidence_bundle:task_1"])
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(runtime.calls, 1)

    def test_invalid_result_is_rejected_for_sibling_evidence_reference(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", InvalidEvidenceAgent())
        task = AgentTaskEnvelope(
            task_id="task_1:StaticKnowledgeAgent",
            parent_task_id="task_1",
            agent_type="StaticKnowledgeAgent",
            evidence_refs=["evidence_bundle:task_1"],
        )

        results = AgentDispatcher(registry).execute(make_plan([task]), AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(make_plan([task]), results)

        self.assertEqual(results[0].status, AgentStatus.INVALID_RESULT)
        self.assertEqual(results[0].failure_code, "AGENT_RESULT_INVALID")
        self.assertIn("evidence_ref_out_of_scope", results[0].failure_reason)
        self.assertEqual(aggregate.status, "FAIL")

    def test_invalid_result_rejects_execution_instruction(self):
        registry = AgentRuntimeRegistry()
        registry.register("RiskAgent", ExecutionInstructionAgent())
        task = AgentTaskEnvelope(task_id="task_1:RiskAgent", parent_task_id="task_1", agent_type="RiskAgent")

        result = AgentDispatcher(registry).execute(make_plan([task]), AgentRuntimeContext())[0]

        self.assertEqual(result.status, AgentStatus.INVALID_RESULT)
        self.assertIn("execution_instruction_not_allowed", result.failure_reason)

    def test_required_agent_failure_blocks_aggregate(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", FailingAgent())
        task = AgentTaskEnvelope(task_id="task_1:StaticKnowledgeAgent", parent_task_id="task_1", agent_type="StaticKnowledgeAgent", required=True)

        results = AgentDispatcher(registry).execute(make_plan([task]), AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(make_plan([task]), results)

        self.assertEqual(results[0].status, AgentStatus.FAILED)
        self.assertEqual(results[0].failure_code, "AGENT_EXECUTION_FAILED")
        self.assertEqual(aggregate.status, "FAIL")
        self.assertEqual(aggregate.confidence_ceiling, "low")

    def test_optional_agent_failure_warns_without_blocking_required_success(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        registry.register("TechnicalAnalysisAgent", FailingAgent())
        required = AgentTaskEnvelope(task_id="task_1:StaticKnowledgeAgent", parent_task_id="task_1", agent_type="StaticKnowledgeAgent", required=True)
        optional = AgentTaskEnvelope(task_id="task_1:TechnicalAnalysisAgent", parent_task_id="task_1", agent_type="TechnicalAnalysisAgent", required=False)
        plan = make_plan([required, optional])

        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(plan, results)

        self.assertEqual({result.status for result in results}, {AgentStatus.SUCCESS, AgentStatus.FAILED})
        self.assertEqual(aggregate.status, "WARN")
        self.assertEqual(aggregate.confidence_ceiling, "medium")

    def test_timeout_is_explicit(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketDataAgent", SlowAgent())
        task = AgentTaskEnvelope(
            task_id="task_1:MarketDataAgent",
            parent_task_id="task_1",
            agent_type="MarketDataAgent",
            timeout_ms=1,
        )

        result = AgentDispatcher(registry).execute(make_plan([task]), AgentRuntimeContext())[0]

        self.assertEqual(result.status, AgentStatus.TIMEOUT)
        self.assertEqual(result.failure_code, "AGENT_TIMEOUT")

    def test_dependency_success_allows_dependent_task(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketDataAgent", SuccessAgent())
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        upstream = AgentTaskEnvelope(task_id="task_1:MarketDataAgent", parent_task_id="task_1", agent_type="MarketDataAgent")
        dependent = AgentTaskEnvelope(
            task_id="task_1:StaticKnowledgeAgent",
            parent_task_id="task_1",
            agent_type="StaticKnowledgeAgent",
            dependency_ids=[upstream.task_id],
        )
        plan = make_plan([upstream, dependent])

        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext())

        self.assertEqual([result.status for result in results], [AgentStatus.SUCCESS, AgentStatus.SUCCESS])

    def test_dependency_failure_blocks_dependent_task(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketDataAgent", FailingAgent())
        downstream = SuccessAgent()
        registry.register("StaticKnowledgeAgent", downstream)
        upstream = AgentTaskEnvelope(task_id="task_1:MarketDataAgent", parent_task_id="task_1", agent_type="MarketDataAgent")
        dependent = AgentTaskEnvelope(
            task_id="task_1:StaticKnowledgeAgent",
            parent_task_id="task_1",
            agent_type="StaticKnowledgeAgent",
            dependency_ids=[upstream.task_id],
        )
        plan = make_plan([upstream, dependent])

        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(plan, results)

        self.assertEqual(results[0].status, AgentStatus.FAILED)
        self.assertEqual(results[1].status, AgentStatus.DEPENDENCY_BLOCKED)
        self.assertEqual(downstream.calls, 0)
        self.assertEqual(aggregate.status, "FAIL")

    def test_parallel_independent_tasks_are_supported(self):
        registry = AgentRuntimeRegistry()
        first = SuccessAgent()
        second = SuccessAgent()
        registry.register("StaticKnowledgeAgent", first)
        registry.register("MarketDataAgent", second)
        task_a = AgentTaskEnvelope(task_id="task_1:StaticKnowledgeAgent", parent_task_id="task_1", agent_type="StaticKnowledgeAgent")
        task_b = AgentTaskEnvelope(task_id="task_1:MarketDataAgent", parent_task_id="task_1", agent_type="MarketDataAgent")
        plan = make_plan([task_a, task_b])

        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext())

        self.assertEqual(set(plan.parallel_groups[0]), {task_a.task_id, task_b.task_id})
        self.assertEqual({result.status for result in results}, {AgentStatus.SUCCESS})
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 1)

    def test_duplicate_dispatch_is_prevented_for_same_attempt(self):
        registry = AgentRuntimeRegistry()
        runtime = SuccessAgent()
        registry.register("StaticKnowledgeAgent", runtime)
        task = AgentTaskEnvelope(task_id="task_1:StaticKnowledgeAgent", parent_task_id="task_1", agent_type="StaticKnowledgeAgent")
        plan = make_plan([task], request_id="duplicate_req")
        dispatcher = AgentDispatcher(registry)

        first = dispatcher.execute(plan, AgentRuntimeContext())
        second = dispatcher.execute(plan, AgentRuntimeContext())

        self.assertEqual(first[0].status, AgentStatus.SUCCESS)
        self.assertEqual(second[0].status, AgentStatus.SKIPPED_WITH_REASON)
        self.assertEqual(second[0].failure_code, "AGENT_DUPLICATE_DISPATCH")
        self.assertEqual(runtime.calls, 1)

    def test_handoff_preserves_result_identity_without_converting_to_evidence(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        task = AgentTaskEnvelope(
            task_id="task_1:StaticKnowledgeAgent",
            parent_task_id="task_1",
            agent_type="StaticKnowledgeAgent",
            evidence_refs=["evidence_bundle:task_1"],
        )
        plan = make_plan([task])
        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext())
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)

        self.assertIsInstance(handoff, AgentHandoffContext)
        self.assertEqual(handoff.evidence_refs, ["evidence_bundle:task_1"])
        self.assertEqual(handoff.agent_results[0].structured_payload, {"observations": ["ok"]})
        self.assertNotIn("EvidenceItem", str(handoff.as_dict()))

    def test_multi_intent_agent_tasks_are_child_scoped(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        registry.register("MarketDataAgent", SuccessAgent())
        parent = QueryPlan(
            "parent",
            "parent",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("book", "book", task_id="task_1", primary_intent="book_concept_explanation"),
                QueryPlan("market", "market", task_id="task_2", primary_intent="market_state_analysis"),
            ],
        ).as_dict()
        ctx = make_decision_context(parent)
        contract = OrchestratorOutput(
            answer_type="multi_analysis",
            selected_agents=["StaticKnowledgeAgent", "MarketDataAgent"],
            execution_allowed=False,
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        by_task = {task.task_id: task for task in plan.tasks}
        self.assertIn("task_1:StaticKnowledgeAgent", by_task)
        self.assertIn("task_2:MarketDataAgent", by_task)
        self.assertEqual(by_task["task_1:StaticKnowledgeAgent"].evidence_refs, ["evidence_bundle:task_1"])
        self.assertEqual(by_task["task_2:MarketDataAgent"].evidence_refs, ["evidence_bundle:task_2"])
        self.assertNotIn("task_1:MarketDataAgent", by_task)
        self.assertNotIn("task_2:StaticKnowledgeAgent", by_task)

    def test_multi_intent_market_child_plans_market_context_even_when_parent_selection_omits_it(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextSuccessAgent())
        parent = QueryPlan(
            "parent",
            "parent",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("market impact", "market impact", task_id="task_1", primary_intent="macro_market_impact"),
                QueryPlan("book", "book", task_id="task_2", primary_intent="book_concept_explanation"),
            ],
        ).as_dict()
        ctx = make_decision_context(parent, request_id="multi_child_agent_req")
        ctx.acquisition_results = [
            {
                "result_id": "market_snapshot:generic",
                "capability": "market_snapshot",
                "target": "generic",
                "status": "success",
                "requested_by_tasks": ["task_1"],
                "task_ids": ["task_1"],
            },
            {
                "result_id": "static_knowledge:concept",
                "capability": "static_knowledge",
                "target": "concept",
                "status": "success",
                "requested_by_tasks": ["task_2"],
                "task_ids": ["task_2"],
            },
        ]
        contract = OrchestratorOutput(
            answer_type="scenario_analysis",
            selected_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"],
            execution_allowed=False,
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext(decision_context_ref=ctx))
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)

        self.assertEqual([task.task_id for task in plan.tasks], ["task_1:MarketContextAgent"])
        self.assertEqual(plan.tasks[0].parent_task_id, "task_1")
        self.assertEqual(plan.tasks[0].intent_family, "macro_market_impact")
        self.assertEqual(plan.tasks[0].source_refs, ["market_snapshot:generic"])
        self.assertNotIn("static_knowledge:concept", plan.tasks[0].source_refs)
        self.assertEqual(results[0].status, AgentStatus.SUCCESS)
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(
            handoff.market_context_assessments_by_task,
            {"task_1": "market_context_assessment:task_1:MarketContextAgent"},
        )
        self.assertFalse(plan.execution_allowed)

    def test_orchestrator_contract_to_agent_handoff_controlled_integration(self):
        registry = AgentRuntimeRegistry()
        registry.register("StaticKnowledgeAgent", SuccessAgent())
        query_plan = QueryPlan("q", "q", task_id="task_1", primary_intent="book_concept_explanation").as_dict()
        ctx = make_decision_context(query_plan, request_id="integration_req")
        contract = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent"])
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        results = AgentDispatcher(registry).execute(plan, AgentRuntimeContext(decision_context_ref=ctx))
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)

        self.assertEqual(contract.selected_agents, ["StaticKnowledgeAgent"])
        self.assertEqual(plan.tasks[0].parent_task_id, "task_1")
        self.assertEqual(results[0].task_id, plan.tasks[0].task_id)
        self.assertEqual(handoff.agent_execution_status, "PASS")
        self.assertFalse(plan.execution_allowed)
        self.assertFalse(contract.execution_allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
