import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler


class ContextRequirementPlannerTests(unittest.TestCase):
    def setUp(self):
        self.assembler = QueryPlanAssembler()
        self.planner = ContextRequirementPlanner()

    def capabilities(self, requirements, required=True):
        needs = requirements.required_needs if required else requirements.optional_needs
        return {need.capability for need in needs}

    def test_book_explanation_requires_static_only(self):
        plan = self.assembler.assemble("Al Brooks nói gì về price action?")
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"static_knowledge"})
        self.assertFalse({"market_snapshot", "economic_event"} & self.capabilities(reqs))
        need = reqs.required_needs[0]
        self.assertEqual(need.parameters.get("author"), "Al Brooks")
        self.assertEqual(need.parameters.get("book"), "Reading Price Charts Bar by Bar")
        self.assertEqual(reqs.task_id, "task_1")

    def test_cpi_report_requires_official_report_only(self):
        plan = self.assembler.assemble("CPI report nói gì về inflation?")
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"official_report"})
        self.assertFalse({"market_snapshot", "economic_event"} & self.capabilities(reqs))
        self.assertEqual(reqs.task_id, "task_1")

    def test_multi_intent_book_query_requires_static_only(self):
        plan = self.assembler.assemble(
            "Al Brooks noi gi ve price action?\n"
            "Anna Coulling noi gi ve volume price analysis?\n"
            "Van Tharp noi gi ve position sizing?\n"
            "Mark Douglas noi gi ve trading discipline?"
        )
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"static_knowledge"})
        self.assertFalse({"market_snapshot", "account_state", "economic_event"} & self.capabilities(reqs))

    def test_dynamic_multi_intent_unions_child_requirements(self):
        plan = self.assembler.assemble(
            "CPI moi nhat anh huong XAUUSD the nao?\n"
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?"
        )
        reqs = self.planner.plan(plan)
        required = {(need.capability, need.target) for need in reqs.required_needs}
        optional = {(need.capability, need.target) for need in reqs.optional_needs}

        self.assertEqual(len(reqs.task_requirements), 2)
        self.assertIn(("official_report", "CPI"), required)
        self.assertIn(("economic_event", "CPI"), required)
        self.assertIn(("market_snapshot", "XAUUSD"), required)
        self.assertIn(("ohlcv", "XAUUSD"), required)
        self.assertIn(("market_knowledge", "gold"), optional)

    def test_required_need_wins_over_optional_duplicate(self):
        plan = self.assembler.assemble(
            "CPI moi nhat anh huong XAUUSD the nao?\n"
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?"
        )
        reqs = self.planner.plan(plan)
        ohlcv_needs = [need for need in reqs.needs if need.capability == "ohlcv" and need.target == "XAUUSD"]

        self.assertEqual(len(ohlcv_needs), 1)
        self.assertTrue(ohlcv_needs[0].required)

    def test_cpi_gold_impact_requirements(self):
        plan = self.assembler.assemble("CPI mới nhất ảnh hưởng XAUUSD thế nào?")
        reqs = self.planner.plan(plan)

        self.assertEqual(
            self.capabilities(reqs),
            {"official_report", "economic_event", "market_snapshot"},
        )
        self.assertEqual(self.capabilities(reqs, required=False), {"ohlcv", "market_knowledge"})

    def test_macro_causal_asset_boundary_uses_macro_impact_requirements(self):
        plan = self.assembler.assemble("Lạm phát mới nhất của Mỹ có thể tác động đến vàng qua cơ chế nào?")
        reqs = self.planner.plan(plan)

        self.assertEqual(plan.primary_intent, "macro_market_impact")
        self.assertEqual(
            self.capabilities(reqs),
            {"official_report", "economic_event", "market_snapshot"},
        )
        self.assertEqual(self.capabilities(reqs, required=False), {"ohlcv", "market_knowledge"})

    def test_market_state_requirements(self):
        plan = self.assembler.assemble("XAUUSD hiện tại đang chịu tác động bởi yếu tố nào?")
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"market_snapshot", "ohlcv"})
        self.assertIn("technical_snapshot", self.capabilities(reqs, required=False))
        self.assertNotIn("account_state", self.capabilities(reqs))

    def test_trade_opportunity_requirements(self):
        plan = self.assembler.assemble("Có nên vào XAUUSD bây giờ không?")
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"market_snapshot", "ohlcv", "economic_event"})
        self.assertIn("technical_snapshot", self.capabilities(reqs, required=False))

    def test_position_sizing_requirements(self):
        plan = self.assembler.assemble("Tài khoản này nên vào bao nhiêu lot XAUUSD?")
        reqs = self.planner.plan(plan)

        self.assertEqual(self.capabilities(reqs), {"account_state", "instrument_spec", "stop_distance", "risk_limit"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
