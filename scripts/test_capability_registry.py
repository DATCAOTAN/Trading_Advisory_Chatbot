import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.semantic.capability_registry import CapabilityRegistry


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_existing_capabilities_are_registered(self):
        self.assertEqual(self.registry.get("market_snapshot").service_name, "LiveDataService")
        self.assertEqual(self.registry.get("market_snapshot").operation_name, "get_live_price")
        self.assertEqual(self.registry.get("ohlcv").operation_name, "get_historical_candles")
        self.assertEqual(self.registry.get("economic_event").operation_name, "get_economic_calendar")
        self.assertEqual(self.registry.get("official_report").service_name, "KnowledgeV3")

    def test_technical_snapshot_depends_on_ohlcv(self):
        self.assertIn("ohlcv", self.registry.get("technical_snapshot").dependencies)

    def test_unavailable_account_capability_is_disabled(self):
        self.assertFalse(self.registry.is_enabled("account_state"))
        self.assertFalse(self.registry.is_enabled("risk_limit"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

