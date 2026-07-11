import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import DecisionContext, ExistingMarketDataAdapter, MarketSnapshot
from src.services.evidence.cross_layer_alignment import FailureClass, FailureClassifier
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.response_gate import ResponseGate
from src.services.semantic.context_acquisition import ContextAcquisitionExecutor
from src.services.semantic.context_execution import ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements
from src.services.semantic.context_sufficiency import ContextSufficiencyGate
from src.services.semantic.query_plan import QueryEntities, QueryPlan
from src.ui.tab_chatbot import _answer_sha256, _build_answer_delivery_artifact, check_answer_completeness


class EmptyRetrievalAdapter:
    def __init__(self):
        from src.services.knowledge.query_intent import QueryIntentRouter

        self.query_intent_router = QueryIntentRouter()
        self.calls = []
        self.last_trace = SimpleNamespace(mode_used="v3", requested_v3=True, collection="knowledge_current")

    def infer_routing_filters(self, query, query_intent=None):
        return {}

    def retrieve(self, query, filters=None, top_k=8, use_v3=False, fallback_to_legacy=None, query_intent=None):
        self.calls.append(query)
        return []


class StaticReranker:
    def process(self, query, raw_documents, enabled=None, query_intent=None, is_refinement=False):
        return "", raw_documents


class GoodPriceLiveService:
    def __init__(self):
        self.price_calls = 0

    def get_live_price(self, symbol="XAUUSD"):
        self.price_calls += 1
        return f"{symbol}: 2400.00 source=FakeFeed"


def make_context(plan, requirements, batch, sufficiency):
    confidence_ceiling = getattr(sufficiency, "confidence_ceiling", "low")
    return DecisionContext(
        request_id="controlled",
        user_query=plan.original_query,
        normalized_query=plan.normalized_query,
        query_intent={},
        answer_mode={},
        query_plan=plan.as_dict(),
        requirements=requirements,
        acquisition_results=list(batch.results),
        task_context_views=list(batch.task_context_views),
        sufficiency=sufficiency.as_dict(),
        missing_required_context=list(getattr(sufficiency, "missing_required", [])),
        missing_optional_context=list(getattr(sufficiency, "missing_optional", [])),
        warnings=list(getattr(sufficiency, "warnings", [])),
        confidence_ceiling=confidence_ceiling,
        evidence_sufficiency={"status": "COMPLETE", "confidence_ceiling": confidence_ceiling},
    )


def gate_for(ctx):
    output = OrchestratorContractBuilder().build(OrchestratorInput(ctx, permissions={"execution": False}))
    return output, ResponseGate.evaluate(ctx, output)


class ControlledFailureGateTests(unittest.TestCase):
    def test_required_capability_unavailable_is_classified_and_blocks_synthesis(self):
        plan = QueryPlan(
            original_query="Tinh vi the theo tai khoan.",
            normalized_query="tinh vi the theo tai khoan",
            task_id="task_1",
            primary_intent="position_sizing",
            entities=QueryEntities(symbols=["XAUUSD"]),
        )
        requirements = ContextRequirements(
            query_plan_id=plan.plan_id,
            task_id="task_1",
            needs=[ContextNeed("account_state", "account", True)],
        )
        execution_plan = ContextExecutionPlanner().plan(requirements)

        executor = ContextAcquisitionExecutor()
        batch = executor.execute(plan, requirements, execution_plan)
        sufficiency = ContextSufficiencyGate().evaluate(
            make_context(plan, requirements, batch, SimpleNamespace(as_dict=lambda: {})),
            requirements,
            execution_plan,
        )
        ctx = make_context(plan, requirements, batch, sufficiency)
        output, gate = gate_for(ctx)

        self.assertEqual(execution_plan.unavailable_capabilities, ["account_state:account"])
        self.assertEqual(batch.unavailable_count, 1)
        self.assertEqual(batch.results[0].status, "unavailable")
        self.assertEqual(batch.task_context_views[0].sufficiency_status, "INSUFFICIENT")
        self.assertIn(sufficiency.status, {"INSUFFICIENT", "BLOCKED"})
        self.assertIn(FailureClass.CAPABILITY_GAP, FailureClassifier.context_acquisition(requirements, execution_plan, batch.results))
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertEqual(gate.answer_type, "insufficient_context")
        self.assertFalse(output.execution_allowed)
        self.assertIn("Thieu", gate.message)

    def test_required_acquisition_failure_is_accounted_and_blocks_synthesis(self):
        plan = QueryPlan(
            original_query="Summarize official macro report.",
            normalized_query="summarize official macro report",
            task_id="task_1",
            primary_intent="macro_report_summary",
            entities=QueryEntities(macro_events=["CPI"], organizations=["BLS"]),
        )
        requirements = ContextRequirements(
            query_plan_id=plan.plan_id,
            task_id="task_1",
            needs=[ContextNeed("official_report", "CPI", True)],
        )
        execution_plan = ContextExecutionPlanner().plan(requirements)
        executor = ContextAcquisitionExecutor(
            retrieval_adapter=EmptyRetrievalAdapter(),
            reranker_module=StaticReranker(),
            use_v3=True,
            fallback_to_legacy=False,
            enable_reranker=False,
        )

        batch = executor.execute(plan, requirements, execution_plan)
        sufficiency = ContextSufficiencyGate().evaluate(
            make_context(plan, requirements, batch, SimpleNamespace(as_dict=lambda: {})),
            requirements,
            execution_plan,
        )
        ctx = make_context(plan, requirements, batch, sufficiency)
        output, gate = gate_for(ctx)
        result = batch.results[0]

        self.assertEqual([task.task_id() for task in execution_plan.deduplicated_tasks], ["official_report:CPI"])
        self.assertEqual(len(executor.retrieval_adapter.calls), 1)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "knowledge_not_found")
        self.assertEqual(batch.failed_count, 1)
        self.assertIn("official_report:CPI", sufficiency.missing_required)
        self.assertEqual(sufficiency.status, "INSUFFICIENT")
        classes = FailureClassifier.context_acquisition(requirements, execution_plan, batch.results)
        self.assertIn(FailureClass.ACQUISITION_FAILURE, classes)
        self.assertNotIn(FailureClass.CAPABILITY_GAP, classes)
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertFalse(output.execution_allowed)
        self.assertEqual(len(batch.results), len(execution_plan.deduplicated_tasks))

    def test_optional_acquisition_failure_preserves_required_sufficiency_and_degrades(self):
        plan = QueryPlan(
            original_query="Analyze market state.",
            normalized_query="analyze market state",
            task_id="task_1",
            primary_intent="market_state_analysis",
            entities=QueryEntities(symbols=["XAUUSD"]),
        )
        requirements = ContextRequirements(
            query_plan_id=plan.plan_id,
            task_id="task_1",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("static_knowledge", "general", False),
            ],
        )
        execution_plan = ContextExecutionPlanner().plan(requirements)
        live = GoodPriceLiveService()
        executor = ContextAcquisitionExecutor(
            retrieval_adapter=EmptyRetrievalAdapter(),
            reranker_module=StaticReranker(),
            market_adapter=ExistingMarketDataAdapter(live),
            use_v3=True,
            fallback_to_legacy=False,
            enable_reranker=False,
        )

        batch = executor.execute(plan, requirements, execution_plan)
        sufficiency = ContextSufficiencyGate().evaluate(
            make_context(plan, requirements, batch, SimpleNamespace(as_dict=lambda: {})),
            requirements,
            execution_plan,
        )
        ctx = make_context(plan, requirements, batch, sufficiency)
        output, gate = gate_for(ctx)
        by_cap = {result.capability: result for result in batch.results}

        self.assertEqual(by_cap["market_snapshot"].status, "success")
        self.assertEqual(by_cap["static_knowledge"].status, "failed")
        self.assertTrue(by_cap["static_knowledge"].reason)
        self.assertEqual(batch.failed_count, 1)
        self.assertEqual(sufficiency.missing_required, [])
        self.assertIn("static_knowledge:general", sufficiency.missing_optional)
        self.assertEqual(sufficiency.status, "DEGRADED")
        self.assertEqual(sufficiency.confidence_ceiling, "medium")
        self.assertEqual(FailureClassifier.context_acquisition(requirements, execution_plan, batch.results), [])
        self.assertTrue(gate.normal_synthesis_allowed)
        self.assertEqual(gate.confidence_ceiling, "medium")
        self.assertFalse(output.execution_allowed)
        self.assertEqual(len(batch.results), len(execution_plan.deduplicated_tasks))

    def test_bounded_response_artifact_identity_and_memory_candidate_consistency(self):
        answer = "Chua du ngu canh bat buoc de tra loi co can cu."
        selected_hash = _answer_sha256(answer)
        runtime_artifacts = {
            "is_bounded_response": True,
            "final_answer_artifact": {
                "content": answer,
                "source": "bounded",
                "repair_status": "NOT_ATTEMPTED",
                "chars": len(answer),
                "sha256": selected_hash,
            },
        }
        runtime_artifacts["answer_delivery_artifact"] = _build_answer_delivery_artifact(
            canonical_answer=answer,
            display_answer=answer,
            selected_artifact=runtime_artifacts["final_answer_artifact"],
        )
        completion = check_answer_completeness(
            answer,
            "BOUNDED_RESPONSE",
            min_chars=1,
            intent="FINANCIAL_RAG",
            runtime_artifacts=runtime_artifacts,
        )
        runtime_artifacts["memory_candidate_artifact"] = {
            "chars": len(answer),
            "sha256": _answer_sha256(answer),
            "matches_selected": _answer_sha256(answer) == selected_hash,
        }

        self.assertEqual(completion["overall_status"], "PASS")
        self.assertEqual(completion["reason"], "bounded_pass")
        self.assertTrue(runtime_artifacts["answer_delivery_artifact"]["matches_selected"])
        self.assertTrue(runtime_artifacts["memory_candidate_artifact"]["matches_selected"])

    def test_multi_intent_child_required_failure_is_task_scoped(self):
        task_1 = ContextRequirements(
            query_plan_id="task_1",
            task_id="task_1",
            needs=[ContextNeed("market_snapshot", "XAUUSD", True)],
        )
        task_2 = ContextRequirements(
            query_plan_id="task_2",
            task_id="task_2",
            needs=[ContextNeed("account_state", "account", True)],
        )
        shared = ContextRequirements(
            query_plan_id="parent",
            needs=task_1.needs + task_2.needs,
            task_requirements={"task_1": task_1, "task_2": task_2},
            task_need_mapping={
                "task_1": ["market_snapshot:XAUUSD"],
                "task_2": ["account_state:account"],
            },
        )
        plan = QueryPlan(
            original_query="market plus account",
            normalized_query="market plus account",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("market", "market", task_id="task_1", primary_intent="market_state_analysis", entities=QueryEntities(symbols=["XAUUSD"])),
                QueryPlan("risk", "risk", task_id="task_2", primary_intent="position_sizing", entities=QueryEntities(symbols=["XAUUSD"])),
            ],
        )
        execution_plan = ContextExecutionPlanner().plan(shared)
        live = GoodPriceLiveService()
        executor = ContextAcquisitionExecutor(market_adapter=ExistingMarketDataAdapter(live))

        batch = executor.execute(plan, shared, execution_plan)
        sufficiency = ContextSufficiencyGate().evaluate(
            make_context(plan, shared, batch, SimpleNamespace(as_dict=lambda: {})),
            shared,
            execution_plan,
        )
        ctx = make_context(plan, shared, batch, sufficiency)
        _, gate = gate_for(ctx)

        self.assertEqual(sufficiency.task_statuses["task_1"]["status"], "COMPLETE")
        self.assertIn(sufficiency.task_statuses["task_2"]["status"], {"INSUFFICIENT", "BLOCKED"})
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertIn(FailureClass.CAPABILITY_GAP, FailureClassifier.context_acquisition(shared, execution_plan, batch.results))
        market_result = next(result for result in batch.results if result.capability == "market_snapshot")
        account_result = next(result for result in batch.results if result.capability == "account_state")
        self.assertEqual(market_result.requested_by_tasks, ["task_1"])
        self.assertEqual(account_result.requested_by_tasks, ["task_2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
