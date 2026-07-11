import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import (
    DecisionContextBuilder,
    ExistingEconomicCalendarAdapter,
    ExistingMacroDataAdapter,
    ExistingMarketDataAdapter,
)
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput


class FakeLiveService:
    def __init__(self):
        self.price_calls = 0
        self.candle_calls = 0
        self.calendar_calls = 0
        self.macro_calls = 0

    def get_live_price(self, symbol="XAUUSD"):
        self.price_calls += 1
        return f"**{symbol}**: $2350.50 - *Nguon: FakeFeed*"

    def get_historical_candles(self, symbol="XAUUSD", timeframe="1h", limit=100, target_date=None, indicators=None):
        self.candle_calls += 1
        return [
            {"timestamp": "2026-07-04T01:00:00Z", "open": 2340, "high": 2355, "low": 2335, "close": 2348, "volume": 10},
            {"timestamp": "2026-07-04T02:00:00Z", "open": 2348, "high": 2360, "low": 2344, "close": 2350.5, "volume": 12, "ema_20": 2347},
        ]

    def get_economic_calendar(self, impact="All"):
        self.calendar_calls += 1
        return "2026-07-04 19:30 | USD | [High] US CPI"

    def get_latest_macro_report(self):
        self.macro_calls += 1
        return "Fake macro snapshot"


def make_builder(fake):
    return DecisionContextBuilder(
        market_adapter=ExistingMarketDataAdapter(fake),
        calendar_adapter=ExistingEconomicCalendarAdapter(fake),
        macro_adapter=ExistingMacroDataAdapter(fake),
    )


class SemanticContextOrchestratorFlowTests(unittest.TestCase):
    def test_static_book_flow_has_no_market_calls(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "Al Brooks nói gì về price action?",
            retrieval_results=[{"metadata": {"title": "Reading Price Charts Bar by Bar", "author": "Al Brooks"}}],
        )
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketDataAgent"]))

        self.assertEqual(ctx.query_plan["primary_intent"], "book_concept_explanation")
        self.assertFalse(ctx.market_data_required)
        self.assertEqual(fake.price_calls, 0)
        self.assertEqual(output.answer_type, "static_explanation")
        self.assertFalse(output.execution_allowed)

    def test_macro_market_impact_is_scenario_not_static(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI mới nhất ảnh hưởng XAUUSD thế nào?",
            retrieval_results=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )
        output = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"])
        )

        self.assertEqual(ctx.query_plan["primary_intent"], "macro_market_impact")
        self.assertTrue(ctx.market_data_required)
        self.assertTrue(ctx.economic_calendar_required)
        self.assertEqual(fake.price_calls, 1)
        self.assertEqual(fake.calendar_calls, 1)
        self.assertIn(ctx.sufficiency["status"], {"COMPLETE", "DEGRADED"})
        self.assertEqual(output.answer_type, "scenario_analysis")
        self.assertFalse(output.execution_allowed)

    def test_missing_required_official_report_blocks_scenario_answer(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI moi nhat anh huong XAUUSD the nao?",
            retrieval_results=[
                {
                    "metadata": {
                        "title": "Gold Market Commentary",
                        "organization": "World Gold Council",
                        "event_type": "GOLD_MARKET",
                        "domain": "market",
                        "subdomain": "gold",
                    }
                }
            ],
        )
        output = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"])
        )

        self.assertEqual(ctx.query_plan["primary_intent"], "macro_market_impact")
        self.assertEqual(ctx.sufficiency["status"], "INSUFFICIENT")
        self.assertIn("official_report:CPI", ctx.sufficiency["missing_required"])
        self.assertEqual(output.answer_type, "insufficient_context")
        official_results = [
            result
            for result in ctx.acquisition_results
            if result["capability"] == "official_report" and result["target"] == "CPI"
        ]
        self.assertEqual(official_results[0]["status"], "missing")
        self.assertNotIn("US CPI Report - BLS", output.source_refs)
        self.assertFalse(output.execution_allowed)

    def test_dynamic_multi_intent_unions_context_and_stays_scenario(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI moi nhat anh huong XAUUSD the nao?\n"
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?",
            retrieval_results=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )
        output = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"])
        )

        self.assertEqual(ctx.query_plan["primary_intent"], "multi_intent")
        self.assertEqual(len(ctx.query_plan["child_plans"]), 2)
        self.assertTrue(ctx.market_data_required)
        self.assertTrue(ctx.economic_calendar_required)
        self.assertEqual(fake.price_calls, 1)
        self.assertEqual(fake.calendar_calls, 1)
        self.assertIn(ctx.sufficiency["status"], {"COMPLETE", "DEGRADED"})
        self.assertEqual(output.answer_type, "scenario_analysis")
        self.assertNotEqual(output.answer_type, "static_explanation")
        self.assertFalse(output.execution_allowed)

    def test_position_sizing_is_blocked_without_account_capability(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build("Tài khoản này nên vào bao nhiêu lot XAUUSD?")
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=["RiskAgent"]))

        self.assertEqual(ctx.query_plan["primary_intent"], "position_sizing")
        self.assertEqual(ctx.sufficiency["status"], "BLOCKED")
        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(output.execution_allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
