import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import event_result, market_result, ohlcv_result, query_plan, task_view, technical_result  # noqa: E402
from src.services.evidence import EvidenceSelector  # noqa: E402


class DynamicEvidenceContractTests(unittest.TestCase):
    def test_economic_event_preserves_structured_fields(self):
        plan = query_plan(
            primary_intent="macro_market_impact",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            macro_events=["CPI"],
            symbols=["XAUUSD"],
        )
        bundle = EvidenceSelector().select(plan, task_view(plan), [event_result()], "scenario_analysis", "task_1")

        self.assertEqual(len(bundle.event_evidence), 1)
        content = bundle.event_evidence[0].content
        self.assertIn("actual=3.4%", content)
        self.assertIn("forecast=3.2%", content)
        self.assertIn("previous=3.1%", content)

    def test_market_snapshot_preserves_price_timestamp_and_provider(self):
        plan = query_plan(primary_intent="market_state_analysis", query="XAUUSD hien tai ra sao?", symbols=["XAUUSD"])
        bundle = EvidenceSelector().select(plan, task_view(plan), [market_result()], "market_analysis", "task_1")

        item = bundle.current_market_evidence[0]
        self.assertEqual(item.symbol, "XAUUSD")
        self.assertIn("price=2345.67", item.content)
        self.assertIn("source=existing_live_data", item.content)
        self.assertEqual(item.freshness_status, "fresh")

    def test_ohlcv_and_technical_evidence_remain_structured(self):
        plan = query_plan(primary_intent="market_state_analysis", query="XAUUSD hien tai ra sao?", symbols=["XAUUSD"])
        bundle = EvidenceSelector().select(
            plan,
            task_view(plan),
            [market_result(), ohlcv_result(), technical_result()],
            "market_analysis",
            "task_1",
        )

        self.assertTrue(any(item.evidence_type == "ohlcv_summary" for item in bundle.technical_evidence))
        self.assertTrue(any(item.evidence_type == "technical_snapshot" for item in bundle.technical_evidence))
        self.assertIn("latest_close", bundle.technical_evidence[0].content)


if __name__ == "__main__":
    unittest.main()
