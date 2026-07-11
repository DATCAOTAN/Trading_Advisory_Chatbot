import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from test_context_acquisition_executor import (  # noqa: E402
    FakeGenericPriceActionRetrievalAdapter,
    FakeLiveService,
    FakeRetrievalAdapter,
    make_executor,
    plan_for,
)
from src.services.decision_context import DecisionContext, MarketSnapshot
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.semantic.context_acquisition import RuntimeContextStore
from src.services.semantic.context_execution import ContextAcquisitionResult


class AcquisitionInvariantTests(unittest.TestCase):
    def test_planned_capability_executes_through_registered_executor(self):
        retrieval = FakeRetrievalAdapter()
        executor, _ = make_executor(fake_retrieval=retrieval)
        plan, reqs, exec_plan = plan_for("Al Brooks noi gi ve price action?")

        batch = executor.execute(plan, reqs, exec_plan)

        self.assertEqual(batch.results[0].capability, "static_knowledge")
        self.assertEqual(batch.results[0].operation, "retrieval_adapter.retrieve")
        self.assertEqual(len(retrieval.calls), 1)

    def test_required_capability_omission_by_legacy_agent_does_not_matter(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("CPI moi nhat anh huong XAUUSD the nao?")

        batch = executor.execute(plan, reqs, exec_plan, runtime_store=RuntimeContextStore())
        capabilities = {result.capability for result in batch.results}

        self.assertIn("economic_event", capabilities)
        self.assertEqual(live.calendar_calls, 1)

    def test_legacy_extra_unnecessary_tool_is_blocked_by_static_requirements(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("Al Brooks noi gi ve price action?")

        batch = executor.execute(plan, reqs, exec_plan)

        self.assertEqual([result.capability for result in batch.results], ["static_knowledge"])
        self.assertEqual(live.price_calls, 0)
        self.assertEqual(live.calendar_calls, 0)
        self.assertEqual(live.candle_calls, 0)

    def test_compatible_runtime_context_is_reused(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")
        store = RuntimeContextStore()
        store.put(
            ContextAcquisitionResult(
                capability="market_snapshot",
                target="XAUUSD",
                status="success",
                data=MarketSnapshot(symbol="XAUUSD", latest_price=2400),
                freshness_status="fresh",
            )
        )

        batch = executor.execute(plan, reqs, exec_plan, runtime_store=store)
        market = next(result for result in batch.results if result.capability == "market_snapshot")

        self.assertEqual(market.status, "reused")
        self.assertEqual(live.price_calls, 0)

    def test_incompatible_runtime_context_is_rejected_and_refetched(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")
        store = RuntimeContextStore()
        store.put(
            ContextAcquisitionResult(
                capability="market_snapshot",
                target="EURUSD",
                status="success",
                data=MarketSnapshot(symbol="EURUSD", latest_price=1.1),
                freshness_status="fresh",
            )
        )

        batch = executor.execute(plan, reqs, exec_plan, runtime_store=store)
        market = next(result for result in batch.results if result.capability == "market_snapshot")

        self.assertEqual(market.status, "success")
        self.assertEqual(live.price_calls, 1)

    def test_equivalent_requests_are_deduplicated_and_required_wins(self):
        executor, live = make_executor()
        query = "CPI moi nhat anh huong XAUUSD the nao?\nXAUUSD hien tai dang chiu tac dong boi yeu to nao?"
        plan, reqs, exec_plan = plan_for(query)

        batch = executor.execute(plan, reqs, exec_plan)
        market_results = [result for result in batch.results if result.capability == "market_snapshot"]
        ohlcv_results = [result for result in batch.results if result.capability == "ohlcv"]

        self.assertEqual(len(market_results), 1)
        self.assertEqual(len(ohlcv_results), 1)
        self.assertTrue(ohlcv_results[0].required)
        self.assertEqual(live.price_calls, 1)
        self.assertEqual(live.candle_calls, 1)

    def test_failed_dependency_skips_dependent_capability(self):
        executor, _ = make_executor(fake_live=FakeLiveService(empty_candles=True))
        plan, reqs, exec_plan = plan_for("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")

        batch = executor.execute(plan, reqs, exec_plan)
        technical = next(result for result in batch.results if result.capability == "technical_snapshot")

        self.assertEqual(technical.status, "skipped")
        self.assertIn("failed_dependency", technical.reason)

    def test_results_contain_truthful_provenance_and_freshness(self):
        executor, _ = make_executor()
        plan, reqs, exec_plan = plan_for("CPI report noi gi ve inflation?")

        batch = executor.execute(plan, reqs, exec_plan)
        result = batch.results[0]

        self.assertEqual(result.provenance.get("title"), "US CPI Report")
        self.assertEqual(result.provenance.get("organization"), "BLS")
        self.assertEqual(result.freshness_status, "acceptable")

    def test_failed_acquisition_cannot_become_success_through_broad_topic(self):
        retrieval = FakeGenericPriceActionRetrievalAdapter()
        executor, _ = make_executor(fake_retrieval=retrieval)
        plan, reqs, exec_plan = plan_for("Al Brooks noi gi ve price action?")

        batch = executor.execute(plan, reqs, exec_plan)

        self.assertEqual(batch.results[0].status, "failed")
        self.assertEqual(batch.results[0].error_code, "knowledge_not_found")

    def test_knowledge_capability_uses_canonical_v3_path(self):
        retrieval = FakeRetrievalAdapter()
        executor, _ = make_executor(fake_retrieval=retrieval)
        executor.use_v3 = False
        executor.fallback_to_legacy = True
        plan, reqs, exec_plan = plan_for("Al Brooks noi gi ve price action?")

        executor.execute(plan, reqs, exec_plan)

        self.assertTrue(retrieval.calls[0][3])
        self.assertFalse(retrieval.calls[0][4])

    def test_child_query_plan_constraints_survive_acquisition_planning(self):
        query = "Al Brooks noi gi ve price action?\nAnna Coulling noi gi ve volume price analysis?"
        plan, reqs, _ = plan_for(query)
        task_authors = {
            task_id: task_req.required_needs[0].parameters.get("author")
            for task_id, task_req in reqs.task_requirements.items()
        }

        self.assertEqual(task_authors["task_1"], "Al Brooks")
        self.assertEqual(task_authors["task_2"], "Anna Coulling")

    def test_execution_allowed_remains_false(self):
        ctx = DecisionContext(
            request_id="exec",
            user_query="Co nen vao XAUUSD bay gio khong?",
            normalized_query="co nen vao xauusd bay gio khong",
            query_intent={},
            answer_mode={},
            query_plan={"primary_intent": "trade_opportunity_analysis"},
            sufficiency={"status": "DEGRADED", "confidence_ceiling": "medium"},
            market_data_required=True,
        )

        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx, permissions={"execution": True}))

        self.assertFalse(output.execution_allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
