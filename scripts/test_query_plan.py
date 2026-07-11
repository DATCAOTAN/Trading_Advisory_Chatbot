import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.query_plan import QueryPlanAssembler


class QueryPlanTests(unittest.TestCase):
    def setUp(self):
        self.assembler = QueryPlanAssembler()

    def test_book_explanation_plan(self):
        plan = self.assembler.assemble("Al Brooks nói gì về price action?")

        self.assertEqual(plan.primary_intent, "book_concept_explanation")
        self.assertEqual(plan.entities.authors, ["Al Brooks"])
        self.assertIn("price_action", plan.entities.concepts)
        self.assertEqual(plan.temporal_scope, "timeless")
        self.assertEqual(plan.user_action_intent, "explanation")
        self.assertEqual(plan.task_id, "task_1")

    def test_static_cpi_report_plan(self):
        plan = self.assembler.assemble("CPI report nói gì về inflation?")

        self.assertEqual(plan.primary_intent, "macro_report_summary")
        self.assertIn("CPI", plan.entities.macro_events)
        self.assertIn(plan.temporal_scope, {"historical", "latest"})
        self.assertEqual(plan.user_action_intent, "explanation")
        self.assertEqual(plan.task_id, "task_1")

    def test_multi_intent_book_query_stays_multi_intent(self):
        plan = self.assembler.assemble(
            "Al Brooks noi gi ve price action?\n"
            "Anna Coulling noi gi ve volume price analysis?\n"
            "Van Tharp noi gi ve position sizing?\n"
            "Mark Douglas noi gi ve trading discipline?"
        )

        self.assertEqual(plan.primary_intent, "multi_intent")
        self.assertEqual(plan.task_id, "")
        self.assertEqual(plan.secondary_intents, ["book_concept_explanation"])
        self.assertEqual(len(plan.child_plans), 4)
        self.assertTrue(all(child.primary_intent == "book_concept_explanation" for child in plan.child_plans))
        self.assertIn("Al Brooks", plan.entities.authors)
        self.assertIn("Anna Coulling", plan.entities.authors)
        self.assertIn("Van Tharp", plan.entities.authors)
        self.assertIn("Mark Douglas", plan.entities.authors)
        self.assertIn("price_action", plan.entities.concepts)
        self.assertIn("volume_price_analysis", plan.entities.concepts)
        self.assertIn("position_sizing", plan.entities.concepts)
        self.assertIn("trading_discipline", plan.entities.concepts)
        self.assertFalse(plan.requires_execution)

    def test_dynamic_multi_intent_preserves_child_plans(self):
        plan = self.assembler.assemble(
            "CPI moi nhat anh huong XAUUSD the nao?\n"
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?"
        )

        self.assertEqual(plan.primary_intent, "multi_intent")
        self.assertEqual(len(plan.child_plans), 2)
        self.assertEqual(plan.child_plans[0].primary_intent, "macro_market_impact")
        self.assertEqual(plan.child_plans[1].primary_intent, "market_state_analysis")
        self.assertIn("macro_market_impact", plan.secondary_intents)
        self.assertIn("market_state_analysis", plan.secondary_intents)
        self.assertIn("XAUUSD", plan.entities.symbols)
        self.assertIn("CPI", plan.entities.macro_events)

    def test_cpi_gold_impact_plan(self):
        plan = self.assembler.assemble("CPI mới nhất ảnh hưởng XAUUSD thế nào?")

        self.assertEqual(plan.primary_intent, "macro_market_impact")
        self.assertEqual(plan.entities.symbols, ["XAUUSD"])
        self.assertIn("CPI", plan.entities.macro_events)
        self.assertEqual(plan.temporal_scope, "latest")
        self.assertIn("event_surprise_analysis", plan.requested_analysis)
        self.assertIn("market_impact_analysis", plan.requested_analysis)

    def test_accented_macro_causal_asset_query_is_macro_market_impact(self):
        plan = self.assembler.assemble("Lạm phát mới nhất của Mỹ có thể tác động đến vàng qua cơ chế nào?")

        self.assertEqual(plan.primary_intent, "macro_market_impact")
        self.assertEqual(plan.temporal_scope, "latest")
        self.assertIn("CPI", plan.entities.macro_events)
        self.assertIn("XAUUSD", plan.entities.symbols)
        self.assertIn("market_impact_analysis", plan.requested_analysis)
        self.assertFalse(plan.requires_execution)

    def test_query_rewriter_metadata_cannot_shift_original_causal_family(self):
        plan = self.assembler.assemble(
            "Lạm phát mới nhất của Mỹ có thể tác động đến vàng qua cơ chế nào?",
            rewritten_query="current XAUUSD market state and recent drivers",
        )

        self.assertEqual(plan.primary_intent, "macro_market_impact")
        self.assertEqual(plan.source_signals["rewritten_query"], "current XAUUSD market state and recent drivers")

    def test_temporal_scope_is_independent_from_intent_family(self):
        latest = self.assembler.assemble("Latest inflation impact on gold through rates and USD?")
        historical = self.assembler.assemble("Historically, how can inflation affect gold through rates and USD?")
        current_state = self.assembler.assemble("What is driving gold now?")

        self.assertEqual(latest.primary_intent, "macro_market_impact")
        self.assertEqual(latest.temporal_scope, "latest")
        self.assertEqual(historical.primary_intent, "macro_market_impact")
        self.assertEqual(current_state.primary_intent, "market_state_analysis")
        self.assertEqual(current_state.temporal_scope, "current")

    def test_generic_current_driver_query_does_not_become_macro_impact(self):
        plan = self.assembler.assemble("What is driving gold now?")

        self.assertEqual(plan.primary_intent, "market_state_analysis")
        self.assertNotIn("event_surprise_analysis", plan.requested_analysis)

    def test_trade_opportunity_plan_does_not_require_execution(self):
        plan = self.assembler.assemble("Có nên vào XAUUSD bây giờ không?")

        self.assertEqual(plan.primary_intent, "trade_opportunity_analysis")
        self.assertEqual(plan.entities.symbols, ["XAUUSD"])
        self.assertEqual(plan.temporal_scope, "current")
        self.assertEqual(plan.user_action_intent, "consider_entry")
        self.assertFalse(plan.requires_execution)

    def test_position_sizing_plan(self):
        plan = self.assembler.assemble("Tài khoản này nên vào bao nhiêu lot XAUUSD?")

        self.assertEqual(plan.primary_intent, "position_sizing")
        self.assertEqual(plan.user_action_intent, "position_sizing")
        self.assertIn("XAUUSD", plan.entities.symbols)


if __name__ == "__main__":
    unittest.main(verbosity=2)
