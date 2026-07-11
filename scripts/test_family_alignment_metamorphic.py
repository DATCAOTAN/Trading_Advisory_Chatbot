import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.evidence.cross_layer_alignment import CrossLayerAlignmentAudit  # noqa: E402
from src.services.semantic.context_requirements import ContextRequirementPlanner  # noqa: E402
from src.services.semantic.query_plan import QueryPlanAssembler  # noqa: E402


class FamilyAlignmentMetamorphicTests(unittest.TestCase):
    def setUp(self):
        self.assembler = QueryPlanAssembler()
        self.requirement_planner = ContextRequirementPlanner()

    def assert_family_group(self, queries, family):
        expected_caps = set(CrossLayerAlignmentAudit.inventory(family).required_context_capabilities)
        for query in queries:
            with self.subTest(query=query):
                plan = self.assembler.assemble(query)
                reqs = self.requirement_planner.plan(plan)
                caps = {need.capability for need in reqs.required_needs}

                self.assertEqual(plan.primary_intent, family)
                self.assertTrue(expected_caps.issubset(caps))
                self.assertFalse(plan.requires_execution)

    def test_book_family_paraphrases_preserve_required_capability_family(self):
        self.assert_family_group(
            [
                "Al Brooks noi gi ve price action?",
                "Theo Al Brooks, price action duoc hieu the nao?",
                "Giai thich quan diem cua Al Brooks ve price action.",
            ],
            "book_concept_explanation",
        )

    def test_report_family_paraphrases_preserve_required_capability_family(self):
        self.assert_family_group(
            [
                "CPI report noi gi ve inflation?",
                "Tom tat bao cao CPI.",
                "Diem chinh trong CPI report la gi?",
            ],
            "macro_report_summary",
        )

    def test_macro_impact_family_paraphrases_preserve_required_capability_family(self):
        self.assert_family_group(
            [
                "CPI anh huong vang the nao?",
                "Lam phat moi nhat cua My co the tac dong den vang qua co che nao?",
                "How can inflation affect gold through interest rates and USD?",
            ],
            "macro_market_impact",
        )

    def test_market_state_family_paraphrases_preserve_required_capability_family(self):
        self.assert_family_group(
            [
                "XAUUSD hien chiu tac dong boi gi?",
                "Yeu to nao dang chi phoi gia vang?",
                "Dong luc chinh cua thi truong vang hien tai la gi?",
                "What is driving gold now?",
            ],
            "market_state_analysis",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
