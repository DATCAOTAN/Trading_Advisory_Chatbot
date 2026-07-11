import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import DecisionContext
from src.services.semantic.context_execution import ContextAcquisitionResult, ContextExecutionPlan
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements
from src.services.semantic.context_sufficiency import ContextSufficiencyGate


def context_with_results(results):
    return DecisionContext(
        request_id="suff",
        user_query="query",
        normalized_query="query",
        query_intent={},
        answer_mode={},
        acquisition_results=[result.as_dict() if hasattr(result, "as_dict") else result for result in results],
    )


class SufficiencyInvariantTests(unittest.TestCase):
    def setUp(self):
        self.gate = ContextSufficiencyGate()

    def test_required_acquisition_success_is_complete(self):
        ctx = context_with_results([
            ContextAcquisitionResult(
                capability="official_report",
                target="CPI",
                status="success",
                provenance={"title": "US CPI Report", "organization": "BLS", "event_type": "CPI"},
                freshness_status="acceptable",
            )
        ])
        reqs = ContextRequirements("p", needs=[ContextNeed("official_report", "CPI", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "COMPLETE")

    def test_optional_failure_is_degraded(self):
        ctx = context_with_results([
            ContextAcquisitionResult("market_snapshot", "XAUUSD", status="success", freshness_status="fresh"),
            ContextAcquisitionResult("market_knowledge", "gold", status="failed", required=False),
        ])
        reqs = ContextRequirements(
            "p",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("market_knowledge", "gold", False),
            ],
        )

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "DEGRADED")
        self.assertIn("market_knowledge:gold", result.missing_optional)

    def test_required_failure_is_insufficient(self):
        ctx = context_with_results([
            ContextAcquisitionResult("economic_event", "CPI", status="failed", required=True),
        ])
        reqs = ContextRequirements("p", needs=[ContextNeed("economic_event", "CPI", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertIn("economic_event:CPI", result.missing_required)

    def test_wrong_source_provenance_is_unsatisfied(self):
        ctx = context_with_results([
            ContextAcquisitionResult(
                "static_knowledge",
                "price_action",
                status="success",
                provenance={"title": "Technical Analysis of the Financial Markets", "author": "John Murphy"},
            )
        ])
        reqs = ContextRequirements(
            "p",
            needs=[
                ContextNeed(
                    "static_knowledge",
                    "price_action",
                    True,
                    parameters={"author": "Al Brooks", "book": "Reading Price Charts Bar by Bar"},
                )
            ],
        )

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertIn("static_knowledge:price_action", result.missing_required)

    def test_stale_required_market_data_is_unsatisfied(self):
        ctx = context_with_results([
            ContextAcquisitionResult("market_snapshot", "XAUUSD", status="success", freshness_status="stale"),
        ])
        reqs = ContextRequirements("p", needs=[ContextNeed("market_snapshot", "XAUUSD", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")

    def test_planned_but_not_acquired_is_unsatisfied(self):
        ctx = context_with_results([])
        reqs = ContextRequirements("p", needs=[ContextNeed("official_report", "CPI", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")

    def test_tool_called_but_incompatible_payload_is_unsatisfied(self):
        ctx = context_with_results([
            ContextAcquisitionResult(
                "official_report",
                "CPI",
                status="success",
                provenance={"title": "Gold Market Commentary", "organization": "World Gold Council", "event_type": "GOLD_MARKET"},
            )
        ])
        reqs = ContextRequirements("p", needs=[ContextNeed("official_report", "CPI", True)])

        result = self.gate.evaluate(ctx, reqs)

        self.assertEqual(result.status, "INSUFFICIENT")

    def test_shared_multi_intent_aggregation_policy(self):
        ctx = context_with_results([
            ContextAcquisitionResult(
                "official_report",
                "CPI",
                status="success",
                requested_by_tasks=["task_1"],
                provenance={"title": "US CPI Report", "organization": "BLS", "event_type": "CPI"},
            ),
            ContextAcquisitionResult("market_snapshot", "XAUUSD", status="success", requested_by_tasks=["task_1", "task_2"]),
            ContextAcquisitionResult("ohlcv", "XAUUSD", status="failed", requested_by_tasks=["task_2"]),
        ])
        task_1 = ContextRequirements(
            "task_1_plan",
            task_id="task_1",
            needs=[
                ContextNeed("official_report", "CPI", True),
                ContextNeed("market_snapshot", "XAUUSD", True),
            ],
        )
        task_2 = ContextRequirements(
            "task_2_plan",
            task_id="task_2",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("ohlcv", "XAUUSD", True),
            ],
        )
        shared = ContextRequirements(
            "parent",
            needs=task_1.needs + task_2.needs,
            task_requirements={"task_1": task_1, "task_2": task_2},
        )

        result = self.gate.evaluate(ctx, shared)

        self.assertEqual(result.status, "INSUFFICIENT")
        self.assertEqual(result.task_statuses["task_1"]["status"], "COMPLETE")
        self.assertEqual(result.task_statuses["task_2"]["status"], "INSUFFICIENT")

    def test_blocked_operational_capability_remains_blocked(self):
        ctx = context_with_results([])
        reqs = ContextRequirements("p", needs=[ContextNeed("account_state", "account", True)])
        plan = ContextExecutionPlan(unavailable_capabilities=["account_state:account"])

        result = self.gate.evaluate(ctx, reqs, plan)

        self.assertEqual(result.status, "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
