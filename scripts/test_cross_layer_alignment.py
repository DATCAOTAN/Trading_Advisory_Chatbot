import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.evidence.cross_layer_alignment import (  # noqa: E402
    CrossLayerAlignmentAudit,
    FailureClass,
    FailureClassifier,
)
from src.services.semantic.context_execution import ContextExecutionPlanner  # noqa: E402
from src.services.semantic.context_requirements import ContextRequirementPlanner  # noqa: E402
from src.services.semantic.query_plan import QueryPlanAssembler  # noqa: E402


class CrossLayerAlignmentTests(unittest.TestCase):
    def _scheduled_capabilities(self, query: str):
        plan = QueryPlanAssembler().assemble(query)
        reqs = ContextRequirementPlanner().plan(plan)
        exec_plan = ContextExecutionPlanner().plan(reqs)
        scheduled = {task.capability for task in exec_plan.deduplicated_tasks}
        unavailable = {item.split(":", 1)[0] for item in exec_plan.unavailable_capabilities}
        return plan, scheduled, unavailable

    def test_supported_families_are_inventoried(self):
        families = CrossLayerAlignmentAudit.inventories()

        for family in [
            "book_concept_explanation",
            "macro_report_summary",
            "macro_market_impact",
            "market_state_analysis",
            "multi_intent",
        ]:
            self.assertIn(family, families)

    def test_required_answer_roles_have_evidence_and_capability_paths(self):
        for family in [
            "book_concept_explanation",
            "macro_report_summary",
            "macro_market_impact",
            "market_state_analysis",
        ]:
            with self.subTest(family=family):
                audit = CrossLayerAlignmentAudit.audit_family(family)
                self.assertTrue(audit.ok, audit.as_dict())
                self.assertFalse(audit.mismatch_types)

    def test_planning_schedules_required_capabilities_for_families(self):
        fixtures = {
            "Al Brooks noi gi ve price action?": "book_concept_explanation",
            "CPI report noi gi ve inflation?": "macro_report_summary",
            "CPI moi nhat anh huong XAUUSD the nao?": "macro_market_impact",
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?": "market_state_analysis",
        }

        for query, family in fixtures.items():
            with self.subTest(query=query):
                plan, scheduled, unavailable = self._scheduled_capabilities(query)
                self.assertEqual(plan.primary_intent, family)
                audit = CrossLayerAlignmentAudit.audit_family(
                    family,
                    scheduled_capabilities=scheduled,
                    unavailable_capabilities=unavailable,
                )
                self.assertTrue(audit.ok, audit.as_dict())

    def test_market_state_driver_roles_are_conditional_not_required(self):
        inventory = CrossLayerAlignmentAudit.inventory("market_state_analysis")

        self.assertEqual(inventory.required_answer_roles, ["current_state", "recent_market_behavior"])
        self.assertIn("main_drivers", inventory.optional_answer_roles)
        self.assertIn("confirmation_or_risk_factors", inventory.optional_answer_roles)
        self.assertEqual(inventory.required_context_capabilities, ["market_snapshot", "ohlcv"])

    def test_failure_classifier_reports_artifact_mismatch(self):
        failure_class = FailureClassifier.final_artifact_consistency("aaa", "bbb")

        self.assertEqual(failure_class, FailureClass.FINAL_ARTIFACT_INCONSISTENCY)

    def test_failure_classifier_reports_intent_family_boundary_mismatch(self):
        failure_class = FailureClassifier.intent_family_boundary(
            "macro_market_impact",
            "market_state_analysis",
        )

        self.assertEqual(failure_class, FailureClass.QUERY_PLAN_ERROR)


if __name__ == "__main__":
    unittest.main(verbosity=2)
