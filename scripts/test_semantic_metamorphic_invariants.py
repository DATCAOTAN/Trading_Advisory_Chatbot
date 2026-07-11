import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler


class SemanticMetamorphicInvariantTests(unittest.TestCase):
    def setUp(self):
        self.assembler = QueryPlanAssembler()
        self.requirement_planner = ContextRequirementPlanner()

    def assert_group(self, queries, expected_intent, expected_capabilities, entity_assertion):
        for query in queries:
            with self.subTest(query=query):
                plan = self.assembler.assemble(query)
                reqs = self.requirement_planner.plan(plan)
                capabilities = {need.capability for need in reqs.needs}

                self.assertEqual(plan.primary_intent, expected_intent)
                self.assertTrue(set(expected_capabilities).issubset(capabilities))
                entity_assertion(self, plan)
                self.assertFalse(plan.requires_execution)

    def test_al_brooks_price_action_paraphrases_preserve_author_and_book(self):
        queries = [
            "Al Brooks noi gi ve price action?",
            "Theo Al Brooks, price action duoc hieu nhu the nao?",
            "Quan diem cua Al Brooks ve hanh dong gia la gi?",
            "Trong sach cua Al Brooks, ong tiep can price action ra sao?",
        ]

        self.assert_group(
            queries,
            "book_concept_explanation",
            {"static_knowledge"},
            lambda case, plan: (
                case.assertIn("Al Brooks", plan.entities.authors),
                case.assertIn("Reading Price Charts Bar by Bar", plan.entities.books),
                case.assertIn("price_action", plan.entities.concepts),
            ),
        )

    def test_cpi_gold_impact_paraphrases_preserve_macro_market_impact(self):
        queries = [
            "CPI moi nhat anh huong XAUUSD the nao?",
            "Du lieu CPI moi cong bo tac dong ra sao den gia vang?",
            "Lam phat My moi nhat co the anh huong vang nhu the nao?",
            "Lạm phát mới nhất của Mỹ có thể tác động đến vàng qua cơ chế nào?",
            "Through what mechanism can inflation transmit to gold?",
            "How can policy rates affect XAUUSD through USD and yields?",
        ]

        self.assert_group(
            queries,
            "macro_market_impact",
            {"official_report", "economic_event", "market_snapshot"},
            lambda case, plan: (
                case.assertTrue(plan.entities.macro_events),
                case.assertIn("XAUUSD", plan.entities.symbols),
                case.assertTrue(plan.entities.organizations),
            ),
        )

    def test_current_gold_market_paraphrases_preserve_market_state(self):
        queries = [
            "XAUUSD hien tai chiu tac dong boi yeu to nao?",
            "Nhung yeu to nao dang chi phoi gia vang luc nay?",
            "Hien tai dong luc chinh cua XAUUSD la gi?",
            "What is driving gold now?",
        ]

        self.assert_group(
            queries,
            "market_state_analysis",
            {"market_snapshot", "ohlcv"},
            lambda case, plan: (
                case.assertIn("XAUUSD", plan.entities.symbols),
                case.assertIn("GOLD_MARKET", plan.entities.macro_events),
                case.assertEqual(plan.temporal_scope, "current"),
            ),
        )

    def test_boundary_negative_queries_do_not_cross_families(self):
        macro = self.assembler.assemble("How can inflation affect gold through interest rates and USD?")
        market_state = self.assembler.assemble("What is driving gold now?")

        self.assertEqual(macro.primary_intent, "macro_market_impact")
        self.assertEqual(market_state.primary_intent, "market_state_analysis")
        self.assertNotEqual(market_state.primary_intent, "macro_market_impact")

    def test_static_cpi_report_paraphrases_preserve_report_summary(self):
        queries = [
            "CPI report noi gi ve inflation?",
            "Bao cao CPI cho thay dieu gi ve lam phat?",
            "Theo bao cao CPI, ap luc gia hien nhu the nao?",
        ]

        self.assert_group(
            queries,
            "macro_report_summary",
            {"official_report"},
            lambda case, plan: (
                case.assertIn("CPI", plan.entities.macro_events),
                case.assertIn("BLS", plan.entities.organizations),
                case.assertNotIn("XAUUSD", plan.entities.symbols),
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
