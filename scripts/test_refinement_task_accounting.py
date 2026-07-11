import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.context_acquisition import ContextAcquisitionExecutor  # noqa: E402
from src.services.semantic.context_execution import ContextExecutionPlan, ContextTask  # noqa: E402
from src.services.semantic.context_requirements import ContextNeed, ContextRequirements  # noqa: E402
from src.services.semantic.query_plan import QueryPlanAssembler  # noqa: E402


class RefinementTaskAccountingTests(unittest.TestCase):
    def test_non_empty_deduplicated_plan_cannot_return_zero_outcomes(self):
        query_plan = QueryPlanAssembler().assemble("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")
        requirements = ContextRequirements(
            query_plan_id=query_plan.plan_id,
            task_id="task_1",
            needs=[ContextNeed("market_snapshot", "XAUUSD", True)],
        )
        execution_plan = ContextExecutionPlan(
            parallel_tasks=[],
            dependent_tasks=[],
            unavailable_capabilities=[],
            deduplicated_tasks=[
                ContextTask("market_snapshot", "XAUUSD", required=True),
            ],
        )

        batch = ContextAcquisitionExecutor().execute(
            query_plan,
            requirements,
            execution_plan,
            request_id="accounting_test",
        )

        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].status, "skipped")
        self.assertEqual(batch.results[0].reason, "task_not_executed_by_plan_stages")
        self.assertEqual(batch.skipped_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

