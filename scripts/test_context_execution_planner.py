import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.context_execution import ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements


class ContextExecutionPlannerTests(unittest.TestCase):
    def test_duplicate_requirements_are_deduplicated(self):
        reqs = ContextRequirements(
            query_plan_id="test",
            needs=[
                ContextNeed("market_snapshot", "XAUUSD", True),
                ContextNeed("market_snapshot", "XAUUSD", True),
            ],
        )
        plan = ContextExecutionPlanner().plan(reqs)

        self.assertEqual(len(plan.deduplicated_tasks), 1)
        self.assertEqual(plan.deduplicated_tasks[0].task_id(), "market_snapshot:XAUUSD")

    def test_technical_snapshot_dependency_expands_to_ohlcv(self):
        reqs = ContextRequirements(
            query_plan_id="test",
            needs=[ContextNeed("technical_snapshot", "XAUUSD", False)],
        )
        plan = ContextExecutionPlanner().plan(reqs)
        task_ids = {task.task_id() for task in plan.deduplicated_tasks}

        self.assertIn("technical_snapshot:XAUUSD", task_ids)
        self.assertIn("ohlcv:XAUUSD", task_ids)
        self.assertTrue(any(task.capability == "technical_snapshot" for task in plan.dependent_tasks))

    def test_unavailable_capability_is_reported(self):
        reqs = ContextRequirements(
            query_plan_id="test",
            needs=[ContextNeed("account_state", "account", True)],
        )
        plan = ContextExecutionPlanner().plan(reqs)

        self.assertIn("account_state:account", plan.unavailable_capabilities)


if __name__ == "__main__":
    unittest.main(verbosity=2)

