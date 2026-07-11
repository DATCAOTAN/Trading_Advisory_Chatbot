import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import DecisionContext, MarketSnapshot, RetrievedKnowledgeContext
from src.services.semantic.context_execution import ContextAcquisitionResult, ContextExecutionPlan
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements
from src.services.semantic.context_sufficiency import ContextSufficiencyGate


def base_context(**kwargs):
    defaults = {
        "request_id": "test",
        "user_query": "query",
        "normalized_query": "query",
        "query_intent": {},
        "answer_mode": {},
    }
    defaults.update(kwargs)
    return DecisionContext(**defaults)


class ContextSufficiencyGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = ContextSufficiencyGate()

    def test_complete_when_required_context_available(self):
        ctx = base_context(
            retrieved_sources=RetrievedKnowledgeContext(primary_sources=["US CPI Report - BLS"]),
            market_snapshot=MarketSnapshot(symbol="XAUUSD", ohlcv_summary={"candles": 2}),
            economic_events=[object()],
        )
        reqs = ContextRequirements(
            query_plan_id="p",
            needs=[
                ContextNeed("official_report", "CPI", True),
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("economic_event", "CPI", True),
            ],
        )

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.confidence_ceiling, "high")

    def test_degraded_when_optional_missing(self):
        ctx = base_context(market_snapshot=MarketSnapshot(symbol="XAUUSD", ohlcv_summary={"candles": 2}))
        reqs = ContextRequirements(
            query_plan_id="p",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("economic_event", "macro", False),
            ],
        )

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "DEGRADED")
        self.assertEqual(result.confidence_ceiling, "medium")
        self.assertIn("economic_event:macro", result.missing_optional)

    def test_insufficient_when_required_missing(self):
        ctx = base_context()
        reqs = ContextRequirements(query_plan_id="p", needs=[ContextNeed("market_snapshot", "XAUUSD", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertIn("market_snapshot:XAUUSD", result.missing_required)

    def test_static_knowledge_provenance_constraints_are_required(self):
        ctx = base_context(
            acquisition_results=[
                ContextAcquisitionResult(
                    capability="static_knowledge",
                    target="price_action",
                    status="success",
                    provenance={
                        "title": "Price-Action-Trading-Guide.pdf",
                        "author": "",
                        "domain": "technical",
                        "subdomain": "price_action",
                    },
                )
            ]
        )
        reqs = ContextRequirements(
            query_plan_id="p",
            needs=[
                ContextNeed(
                    "static_knowledge",
                    "price_action",
                    True,
                    parameters={
                        "author": "Al Brooks",
                        "book": "Reading Price Charts Bar by Bar",
                    },
                )
            ],
        )

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertIn("static_knowledge:price_action", result.missing_required)

    def test_blocked_when_operational_capability_unavailable(self):
        ctx = base_context()
        reqs = ContextRequirements(query_plan_id="p", needs=[ContextNeed("account_state", "account", True)])
        execution = ContextExecutionPlan(unavailable_capabilities=["account_state:account"])

        result = self.gate.evaluate(ctx, reqs, execution)

        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.confidence_ceiling, "low")

    def test_task_level_sufficiency_reports_missing_child_context(self):
        ctx = base_context(
            retrieved_sources=RetrievedKnowledgeContext(primary_sources=["US CPI Report - BLS"]),
            market_snapshot=MarketSnapshot(symbol="XAUUSD", ohlcv_summary={"candles": 0}),
            economic_events=[object()],
        )
        task_1 = ContextRequirements(
            query_plan_id="task_plan_1",
            task_id="task_1",
            needs=[
                ContextNeed("official_report", "CPI", True),
                ContextNeed("economic_event", "CPI", True),
                ContextNeed("market_snapshot", "XAUUSD", True),
            ],
        )
        task_2 = ContextRequirements(
            query_plan_id="task_plan_2",
            task_id="task_2",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("ohlcv", "XAUUSD", True),
            ],
        )
        shared = ContextRequirements(
            query_plan_id="parent",
            needs=task_1.needs + task_2.needs,
            task_requirements={"task_1": task_1, "task_2": task_2},
        )

        result = self.gate.evaluate(ctx, shared)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertEqual(result.task_statuses["task_1"]["status"], "COMPLETE")
        self.assertEqual(result.task_statuses["task_2"]["status"], "INSUFFICIENT")
        self.assertIn("ohlcv:XAUUSD", result.task_statuses["task_2"]["missing_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
