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


class FakeLiveService:
    def __init__(self):
        self.price_calls = 0
        self.candle_calls = 0
        self.calendar_calls = 0
        self.macro_calls = 0

    def get_live_price(self, symbol="XAUUSD"):
        self.price_calls += 1
        return f"💰 **{symbol}**: $2,350.50 (Cập nhật: 10:00) - *Nguồn: FakeFeed*"

    def get_historical_candles(self, symbol="XAUUSD", timeframe="1h", limit=100, target_date=None, indicators=None):
        self.candle_calls += 1
        return [
            {"timestamp": "2026-07-02T08:00:00Z", "open": 2340, "high": 2355, "low": 2335, "close": 2345, "volume": 10},
            {"timestamp": "2026-07-02T09:00:00Z", "open": 2345, "high": 2360, "low": 2340, "close": 2350.5, "volume": 12, "ema_20": 2348, "rsi_14": 55},
        ]

    def get_economic_calendar(self, impact="All"):
        self.calendar_calls += 1
        return "**Sự kiện kinh tế tuần này:**\n\n📅 02/07/2026 19:30 | USD | [High] US CPI"

    def get_latest_macro_report(self):
        self.macro_calls += 1
        return "Fake macro snapshot: USD inflation calendar risk remains elevated."


def make_builder(fake_service):
    return DecisionContextBuilder(
        market_adapter=ExistingMarketDataAdapter(fake_service),
        calendar_adapter=ExistingEconomicCalendarAdapter(fake_service),
        macro_adapter=ExistingMacroDataAdapter(fake_service),
    )


class DecisionContextBuilderTests(unittest.TestCase):
    def test_static_book_query_does_not_call_market_api(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "Al Brooks noi gi ve price action?",
            retrieval_results=[{"metadata": {"title": "Reading Price Charts Bar By Bar", "author": "Al Brooks", "source_role": "primary_source"}}],
        )

        self.assertTrue(ctx.static_knowledge_required)
        self.assertFalse(ctx.market_data_required)
        self.assertFalse(ctx.economic_calendar_required)
        self.assertEqual(fake.price_calls, 0)
        self.assertEqual(fake.candle_calls, 0)
        self.assertEqual(fake.macro_calls, 0)

    def test_static_report_query_does_not_call_market_api(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI report noi gi ve inflation?",
            retrieval_results=[{"metadata": {"title": "US CPI Report", "organization": "BLS", "source_role": "primary_source"}}],
        )

        self.assertTrue(ctx.static_knowledge_required)
        self.assertFalse(ctx.market_data_required)
        self.assertFalse(ctx.economic_calendar_required)
        self.assertEqual(fake.price_calls, 0)
        self.assertEqual(fake.macro_calls, 0)

    def test_current_xauusd_query_calls_existing_market_adapter(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")

        self.assertTrue(ctx.market_data_required)
        self.assertEqual(fake.price_calls, 1)
        self.assertEqual(fake.candle_calls, 1)
        self.assertEqual(ctx.market_snapshot.symbol, "XAUUSD")
        self.assertEqual(ctx.market_snapshot.latest_price, 2350.50)

    def test_cpi_impact_on_xauusd_calls_calendar_and_market(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI moi nhat anh huong XAUUSD the nao?",
            retrieval_results=[{"metadata": {"title": "US CPI Report", "organization": "BLS", "source_role": "primary_source"}}],
        )

        self.assertTrue(ctx.static_knowledge_required)
        self.assertTrue(ctx.market_data_required)
        self.assertTrue(ctx.economic_calendar_required)
        self.assertEqual(fake.calendar_calls, 1)
        self.assertEqual(fake.macro_calls, 1)
        self.assertGreaterEqual(len(ctx.economic_events), 1)
        self.assertTrue(ctx.macro_snapshot["available"])

    def test_required_official_report_must_match_acquisition_target(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "CPI moi nhat anh huong XAUUSD the nao?",
            retrieval_results=[
                {
                    "metadata": {
                        "title": "SMART MONEY CONCEPTS IN THE FOREX MARKET",
                        "author": "Unknown",
                        "domain": "technical",
                        "subdomain": "smc",
                    }
                }
            ],
        )

        self.assertTrue(ctx.static_knowledge_required)
        self.assertTrue(ctx.market_data_required)
        self.assertTrue(ctx.economic_calendar_required)
        self.assertEqual(ctx.sufficiency["status"], "INSUFFICIENT")
        self.assertIn("official_report:CPI", ctx.sufficiency["missing_required"])
        cpi_results = [
            result
            for result in ctx.acquisition_results
            if result["capability"] == "official_report" and result["target"] == "CPI"
        ]
        self.assertEqual(cpi_results[0]["status"], "missing")

    def test_trade_plan_query_requires_risk_context(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build("Co nen vao lenh XAUUSD bay gio khong?")

        self.assertTrue(ctx.market_data_required)
        self.assertTrue(ctx.technical_snapshot_required)
        self.assertTrue(ctx.risk_context_required)
        self.assertTrue(ctx.execution_gate_required)
        self.assertIn("risk_context", ctx.missing_context)

    def test_existing_outputs_are_reused_without_duplicate_fetch(self):
        fake = FakeLiveService()
        ctx = make_builder(fake).build(
            "XAUUSD hien tai the nao?",
            live_price_output="💰 **XAUUSD**: $2,400.00 - *Nguồn: Existing*",
            candles_output=[{"timestamp": "2026-07-02T09:00:00Z", "open": 2390, "high": 2410, "low": 2380, "close": 2400, "volume": 1}],
        )

        self.assertEqual(fake.price_calls, 0)
        self.assertEqual(fake.candle_calls, 0)
        self.assertEqual(ctx.market_snapshot.latest_price, 2400.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
