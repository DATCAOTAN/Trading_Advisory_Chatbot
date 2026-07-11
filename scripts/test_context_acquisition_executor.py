import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import (
    ExistingEconomicCalendarAdapter,
    ExistingMarketDataAdapter,
    ExistingTechnicalSnapshotAdapter,
    MarketSnapshot,
)
from src.services.knowledge.query_intent import QueryIntentRouter
from src.services.semantic.context_acquisition import ContextAcquisitionExecutor, RuntimeContextStore
from src.services.semantic.context_execution import ContextAcquisitionResult, ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler


class FakeRetrievalAdapter:
    def __init__(self):
        self.query_intent_router = QueryIntentRouter()
        self.calls = []
        self.last_trace = None

    def infer_routing_filters(self, query, query_intent=None):
        intent = query_intent or self.query_intent_router.route(query)
        return {
            "domain": intent.primary_domain,
            "subdomain": intent.primary_subdomain,
            "event_type": intent.event_type_candidates[0] if intent.event_type_candidates else "",
            "organization": intent.preferred_organizations[0] if intent.preferred_organizations else "",
            "knowledge_type": "report" if intent.source_preference in {"official_report_first", "mixed_report_and_book"} else "book",
        }

    def retrieve(self, query, filters=None, top_k=8, use_v3=False, fallback_to_legacy=None, query_intent=None):
        intent = query_intent or self.query_intent_router.route(query)
        self.calls.append((query, filters, intent.intent_type, use_v3, fallback_to_legacy))
        self.last_trace = SimpleNamespace(
            mode_used="v3" if use_v3 else "legacy",
            requested_v3=use_v3,
            collection="knowledge_current" if use_v3 else "xauusd_knowledge_v2",
        )
        if filters and filters.get("event_type") == "CPI":
            return [{
                "content": "US CPI Report context",
                "metadata": {
                    "title": "US CPI Report",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "event_type": "CPI",
                    "domain": "macro",
                    "subdomain": "inflation",
                    "source_tier": "tier1",
                },
                "score": 0.9,
            }]
        if "world gold council" in query.lower() or "gold" in query.lower():
            return [{
                "content": "Gold Market Commentary context",
                "metadata": {
                    "title": "Gold Market Commentary",
                    "organization": "World Gold Council",
                    "knowledge_type": "report",
                    "event_type": "GOLD_MARKET",
                    "domain": "market",
                    "subdomain": "gold",
                    "source_tier": "tier1",
                },
                "score": 0.9,
            }]
        return [{
            "content": "Al Brooks price action context",
            "metadata": {
                "title": "Reading Price Charts Bar by Bar",
                "author": "Al Brooks",
                "knowledge_type": "book",
                "domain": "technical",
                "subdomain": "price_action",
            },
            "score": 0.9,
        }]


class FakeGenericPriceActionRetrievalAdapter(FakeRetrievalAdapter):
    def retrieve(self, query, filters=None, top_k=8, use_v3=False, fallback_to_legacy=None, query_intent=None):
        intent = query_intent or self.query_intent_router.route(query)
        self.calls.append((query, filters, intent.intent_type, use_v3, fallback_to_legacy))
        self.last_trace = SimpleNamespace(
            mode_used="v3" if use_v3 else "legacy",
            requested_v3=use_v3,
            collection="knowledge_current" if use_v3 else "xauusd_knowledge_v2",
        )
        return [{
            "content": "Generic price action guide context",
            "metadata": {
                "title": "Price-Action-Trading-Guide.pdf",
                "knowledge_type": "book",
                "domain": "technical",
                "subdomain": "price_action",
            },
            "score": 0.9,
        }]


class FakeReranker:
    def __init__(self):
        self.calls = []

    def process(self, query, raw_documents, enabled=None, query_intent=None):
        self.calls.append((query, getattr(query_intent, "intent_type", "")))
        return raw_documents[0]["content"], raw_documents


class FakeLiveService:
    def __init__(self, empty_candles=False):
        self.empty_candles = empty_candles
        self.price_calls = 0
        self.candle_calls = 0
        self.calendar_calls = 0

    def get_live_price(self, symbol="XAUUSD"):
        self.price_calls += 1
        return f"💰 **{symbol}**: $2,400.00 - *Nguồn: FakeFeed*"

    def get_historical_candles(self, symbol="XAUUSD", timeframe="1h", limit=100, target_date=None, indicators=None):
        self.candle_calls += 1
        if self.empty_candles:
            return []
        return [
            {"timestamp": "2026-07-05T00:00:00Z", "open": 2390, "high": 2410, "low": 2385, "close": 2400, "volume": 1, "rsi_14": 55}
        ]

    def get_economic_calendar(self, impact="All"):
        self.calendar_calls += 1
        return "CPI actual=3.4 forecast=3.2 previous=3.1"


def make_executor(fake_retrieval=None, fake_live=None, fake_reranker=None):
    fake_live = fake_live or FakeLiveService()
    return ContextAcquisitionExecutor(
        retrieval_adapter=fake_retrieval or FakeRetrievalAdapter(),
        reranker_module=fake_reranker or FakeReranker(),
        market_adapter=ExistingMarketDataAdapter(fake_live),
        calendar_adapter=ExistingEconomicCalendarAdapter(fake_live),
        technical_adapter=ExistingTechnicalSnapshotAdapter(),
        live_service=fake_live,
        use_v3=True,
        fallback_to_legacy=False,
        enable_reranker=False,
    ), fake_live


def plan_for(query):
    query_plan = QueryPlanAssembler().assemble(query, query)
    requirements = ContextRequirementPlanner().plan(query_plan)
    execution_plan = ContextExecutionPlanner().plan(requirements)
    return query_plan, requirements, execution_plan


class ContextAcquisitionExecutorTests(unittest.TestCase):
    def test_static_book_query_only_executes_static_knowledge(self):
        retrieval = FakeRetrievalAdapter()
        executor, live = make_executor(fake_retrieval=retrieval)
        query_plan, requirements, execution_plan = plan_for("Al Brooks nói gì về price action?")

        batch = executor.execute(query_plan, requirements, execution_plan)

        self.assertEqual(live.price_calls, 0)
        self.assertEqual(live.candle_calls, 0)
        self.assertEqual(live.calendar_calls, 0)
        self.assertEqual([result.capability for result in batch.results], ["static_knowledge"])
        self.assertEqual(batch.results[0].status, "success")
        self.assertEqual(batch.results[0].requested_by_tasks, ["task_1"])
        self.assertEqual(len(batch.task_context_views), 1)
        self.assertEqual(batch.task_context_views[0].task_id, "task_1")
        self.assertEqual(batch.task_context_views[0].required_context_results[0]["result_id"], "static_knowledge:price_action")

    def test_semantic_knowledge_acquisition_forces_canonical_v3_path(self):
        retrieval = FakeRetrievalAdapter()
        executor, _ = make_executor(fake_retrieval=retrieval)
        executor.use_v3 = False
        executor.fallback_to_legacy = True
        query_plan, requirements, execution_plan = plan_for("Al Brooks noi gi ve price action?")

        batch = executor.execute(query_plan, requirements, execution_plan)

        self.assertEqual(batch.results[0].status, "success")
        self.assertEqual(batch.results[0].requested_by_tasks, ["task_1"])
        self.assertTrue(retrieval.calls[0][3])
        self.assertFalse(retrieval.calls[0][4])
        self.assertEqual(retrieval.last_trace.collection, "knowledge_current")

    def test_author_specific_book_query_rejects_generic_source(self):
        retrieval = FakeGenericPriceActionRetrievalAdapter()
        executor, live = make_executor(fake_retrieval=retrieval)
        query_plan, requirements, execution_plan = plan_for("Al Brooks nói gì về price action?")

        batch = executor.execute(query_plan, requirements, execution_plan)
        result = batch.results[0]

        self.assertEqual(live.price_calls, 0)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "knowledge_not_found")
        self.assertEqual(requirements.required_needs[0].parameters.get("author"), "Al Brooks")

    def test_cpi_latest_impact_executes_required_dynamic_context(self):
        retrieval = FakeRetrievalAdapter()
        executor, live = make_executor(fake_retrieval=retrieval)
        query_plan, requirements, execution_plan = plan_for("CPI mới nhất ảnh hưởng XAUUSD thế nào?")

        batch = executor.execute(query_plan, requirements, execution_plan)
        by_cap = {result.capability: result for result in batch.results}

        self.assertEqual(by_cap["official_report"].status, "success")
        self.assertEqual(by_cap["economic_event"].status, "success")
        self.assertEqual(by_cap["market_snapshot"].status, "success")
        self.assertEqual(live.price_calls, 1)
        self.assertEqual(live.calendar_calls, 1)
        self.assertEqual(live.candle_calls, 1)

    def test_runtime_store_reuses_prefetched_market_snapshot(self):
        retrieval = FakeRetrievalAdapter()
        executor, live = make_executor(fake_retrieval=retrieval)
        query_plan, requirements, execution_plan = plan_for("XAUUSD hiện tại đang chịu tác động bởi yếu tố nào?")
        store = RuntimeContextStore()
        store.put(
            ContextAcquisitionResult(
                capability="market_snapshot",
                target="XAUUSD",
                status="success",
                data=MarketSnapshot(symbol="XAUUSD", latest_price=2400, source="prefetch"),
                source="legacy_runtime",
                freshness_status="fresh",
            )
        )

        batch = executor.execute(query_plan, requirements, execution_plan, runtime_store=store)
        market_result = next(result for result in batch.results if result.capability == "market_snapshot")

        self.assertEqual(market_result.status, "reused")
        self.assertEqual(live.price_calls, 0)

    def test_multi_intent_shared_acquisition_deduplicates_market_requests(self):
        retrieval = FakeRetrievalAdapter()
        executor, live = make_executor(fake_retrieval=retrieval)
        query = "CPI mới nhất ảnh hưởng XAUUSD thế nào?\nXAUUSD hiện tại đang chịu tác động bởi yếu tố nào?"
        query_plan, requirements, execution_plan = plan_for(query)

        batch = executor.execute(query_plan, requirements, execution_plan)
        market_result = next(result for result in batch.results if result.capability == "market_snapshot")
        ohlcv_result = next(result for result in batch.results if result.capability == "ohlcv")

        self.assertEqual(live.price_calls, 1)
        self.assertEqual(live.candle_calls, 1)
        self.assertGreaterEqual(len(market_result.requested_by_tasks), 2)
        self.assertGreaterEqual(len(ohlcv_result.requested_by_tasks), 2)
        self.assertEqual(len(batch.task_context_views), 2)

    def test_technical_snapshot_skips_when_ohlcv_dependency_fails(self):
        executor, live = make_executor(fake_live=FakeLiveService(empty_candles=True))
        query_plan, requirements, execution_plan = plan_for("XAUUSD hiện tại đang chịu tác động bởi yếu tố nào?")

        batch = executor.execute(query_plan, requirements, execution_plan)
        technical = next(result for result in batch.results if result.capability == "technical_snapshot")

        self.assertEqual(live.candle_calls, 1)
        self.assertEqual(technical.status, "skipped")
        self.assertIn("failed_dependency", technical.reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
