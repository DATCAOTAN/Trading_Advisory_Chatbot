import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config  # noqa: E402
from src.services.live_data_service import MarketDataService  # noqa: E402
from src.services.trading.market import MT5BridgeMarketDataProvider, ProviderRegistry  # noqa: E402
from src.services.trading.market.data_quality import DataQualityGate  # noqa: E402
from src.services.trading.market.models import AccountSnapshot, MarketSnapshot, OHLCVBar, TickSnapshot  # noqa: E402
from src.services.trading.market.timeframes import timeframe_duration_seconds  # noqa: E402
from tools.mt5_bridge import mt5_client  # noqa: E402


class MT5BridgeMarketDataBoundaryTests(unittest.TestCase):
    def test_mt5_bridge_uses_latest_completed_bar_for_all_intraday_timeframes(self):
        calls = []

        class FakeMT5:
            TIMEFRAME_M1 = 1
            TIMEFRAME_M15 = 15
            TIMEFRAME_H1 = 16385
            TIMEFRAME_H4 = 16388

            @staticmethod
            def symbol_select(symbol, selected):
                return True

            @staticmethod
            def copy_rates_from_pos(symbol, timeframe, start_pos, count):
                calls.append((symbol, timeframe, start_pos, count))
                return [
                    {
                        "time": 1785060180,
                        "open": 100.0,
                        "high": 102.0,
                        "low": 99.0,
                        "close": 101.0,
                        "tick_volume": 12,
                    }
                ]

        client = mt5_client.MT5Client()
        client._initialized = True
        with patch.object(mt5_client, "mt5", FakeMT5), patch.object(
            client,
            "tick",
            return_value={"bid": 100.0, "ask": 101.0, "spread": 1.0},
        ):
            results = {
                timeframe: client.ohlcv("BTCUSDm", timeframe, 1)
                for timeframe in ("M1", "M15", "H1", "H4")
            }

        self.assertEqual([call[2] for call in calls], [1, 1, 1, 1])
        self.assertEqual(
            [call[1] for call in calls],
            [FakeMT5.TIMEFRAME_M1, FakeMT5.TIMEFRAME_M15, FakeMT5.TIMEFRAME_H1, FakeMT5.TIMEFRAME_H4],
        )
        self.assertTrue(
            all(
                result["bars"][0]["timestamp"] == "2026-07-26T10:03:00+00:00"
                for result in results.values()
            )
        )

    def test_completed_bar_freshness_preserves_fresh_and_stale_history(self):
        now = datetime.now(timezone.utc)

        def quality(age_seconds):
            snapshot = MarketSnapshot(
                symbol="BTCUSD",
                timeframe="M1",
                bars=[
                    OHLCVBar(
                        timestamp=(
                            now
                            - timedelta(seconds=age_seconds + (34 - index) * 60)
                        ).isoformat(),
                        open=100.0,
                        high=102.0,
                        low=99.0,
                        close=101.0,
                        volume=12,
                        timeframe="M1",
                        symbol="BTCUSD",
                    )
                    for index in range(35)
                ]
            )
            return DataQualityGate()._evaluate_snapshot(snapshot)[0]

        self.assertEqual(quality(350), "COMPLETE")
        self.assertEqual(quality(370), "STALE")

    def test_timeframe_durations_and_recent_h4_close_time(self):
        self.assertEqual(
            {
                timeframe: timeframe_duration_seconds(timeframe)
                for timeframe in ("M1", "M15", "H1", "H4")
            },
            {"M1": 60, "M15": 900, "H1": 3600, "H4": 14400},
        )

        now = datetime.now(timezone.utc)

        def h4_quality(open_age):
            snapshot = MarketSnapshot(
                symbol="BTCUSD",
                timeframe="H4",
                bars=[
                    OHLCVBar(
                        timestamp=(
                            now - timedelta(seconds=open_age + (34 - index) * 14400)
                        ).isoformat(),
                        open=100.0,
                        high=102.0,
                        low=99.0,
                        close=101.0,
                        volume=12,
                        timeframe="H4",
                        symbol="BTCUSD",
                    )
                    for index in range(35)
                ],
            )
            return DataQualityGate()._evaluate_snapshot(snapshot)[0]

        self.assertEqual(h4_quality(6 * 3600), "COMPLETE")
        self.assertEqual(h4_quality(10 * 3600 + 900), "STALE")

    def test_default_provider_is_mt5_bridge_and_oanda_not_required(self):
        self.assertEqual(Config.MARKET_DATA_PROVIDER, "mt5_bridge")
        provider = ProviderRegistry.build_provider()

        self.assertEqual(provider.provider_name, "mt5_bridge")
        self.assertFalse(getattr(Config, "OANDA_LEGACY_ENABLED", False))

    def test_missing_oanda_credentials_do_not_break_provider_registry(self):
        with patch.object(Config, "OANDA_API_KEY", ""), patch.object(Config, "OANDA_ACCOUNT_ID", ""):
            provider = ProviderRegistry.build_provider("mt5_bridge")
            health = provider.health_check()

        self.assertEqual(provider.provider_name, "mt5_bridge")
        self.assertIn(health.status, {"OK", "DEGRADED", "UNAVAILABLE", "MISCONFIGURED"})

    def test_provider_registry_unknown_provider_safe(self):
        provider = ProviderRegistry.build_provider("unknown")
        health = provider.health_check()

        self.assertEqual(health.status, "MISCONFIGURED")
        self.assertEqual(provider.get_ohlcv("XAUUSD", "M15", 10).data_quality, "EMPTY")

    def test_mt5_bridge_provider_maps_ohlcv_json(self):
        provider = MT5BridgeMarketDataProvider(bridge_url="http://127.0.0.1:8765")

        def fixture(path, params=None):
            self.assertEqual(path, "/ohlcv")
            return {
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "bars": [
                    {"timestamp": "2026-01-01T00:00:00+00:00", "open": 2400, "high": 2402, "low": 2399, "close": 2401, "volume": 10}
                ],
                "latest_bid": 2401.1,
                "latest_ask": 2401.4,
                "spread": 0.3,
                "source": "mt5_terminal",
                "data_quality": "COMPLETE",
            }

        provider._get_json = fixture
        snapshot = provider.get_ohlcv("XAUUSD", "M15", 10)

        self.assertIsInstance(snapshot, MarketSnapshot)
        self.assertEqual(snapshot.data_quality, "COMPLETE")
        self.assertEqual(len(snapshot.bars), 1)
        self.assertEqual(snapshot.bars[0].source, "mt5_terminal")

    def test_mt5_bridge_provider_maps_tick_json(self):
        provider = MT5BridgeMarketDataProvider()
        provider._get_json = lambda path, params=None: {
            "symbol": "XAUUSD",
            "bid": 2401.1,
            "ask": 2401.4,
            "spread": 0.3,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

        tick = provider.get_latest_tick("XAUUSD")

        self.assertIsInstance(tick, TickSnapshot)
        self.assertEqual(tick.bid, 2401.1)
        self.assertEqual(tick.ask, 2401.4)

    def test_mt5_bridge_provider_maps_account_and_positions_redacted(self):
        provider = MT5BridgeMarketDataProvider()

        def fixture(path, params=None):
            if path == "/account":
                return {
                    "account_id_hash": "abc123hash",
                    "server_redacted": "Br***er",
                    "currency": "USD",
                    "balance": 1000,
                    "equity": 1001,
                    "margin": 0,
                    "free_margin": 1001,
                    "leverage": 100,
                    "account_environment": "DEMO",
                    "redacted": True,
                }
            if path == "/positions":
                return {
                    "positions": [
                        {
                            "position_id_hash": "poshash",
                            "symbol": "XAUUSD",
                            "side": "LONG",
                            "volume": 0.01,
                            "open_time": "2026-01-01T00:00:00+00:00",
                            "open_price": 2400,
                            "current_price": 2401,
                            "pnl": 1,
                            "source": "mt5_terminal",
                            "redacted": True,
                        }
                    ]
                }
            return {}

        provider._get_json = fixture
        account = provider.get_account()
        positions = provider.get_positions("XAUUSD")

        self.assertIsInstance(account, AccountSnapshot)
        self.assertEqual(account.account_id_hash, "abc123hash")
        self.assertEqual(account.account_environment, "DEMO")
        self.assertTrue(account.redacted)
        self.assertEqual(positions[0].position_id_hash, "poshash")
        self.assertTrue(positions[0].redacted)

    def test_timeout_and_bridge_unavailable_safe(self):
        provider = MT5BridgeMarketDataProvider()
        provider._get_json = lambda path, params=None: (_ for _ in ()).throw(TimeoutError("timeout"))

        self.assertEqual(provider.health_check().status, "UNAVAILABLE")
        self.assertEqual(provider.get_ohlcv("XAUUSD", "M15", 10).data_quality, "EMPTY")
        self.assertIsNone(provider.get_latest_tick("XAUUSD").bid)

    def test_app_side_code_does_not_import_metatrader5(self):
        src_root = PROJECT_ROOT / "src"
        matches = []
        for path in src_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "MetaTrader5" in text or "import mt5" in text:
                matches.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(matches, [])

    def test_live_data_service_delegates_to_provider_registry_and_callers_work(self):
        provider = MT5BridgeMarketDataProvider()

        def fixture(path, params=None):
            if path == "/health":
                return {"status": "OK", "message": "fixture bridge healthy"}
            if path == "/tick":
                return {
                    "symbol": "XAUUSD",
                    "bid": 2401.0,
                    "ask": 2401.2,
                    "spread": 0.2,
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            if path == "/ohlcv":
                return {
                    "symbol": "XAUUSD",
                    "timeframe": "M15",
                    "bars": [],
                    "latest_bid": 2401.0,
                    "latest_ask": 2401.2,
                    "spread": 0.2,
                    "source": "mt5_terminal",
                    "data_quality": "EMPTY",
                }
            if path == "/account":
                return {"account_id_hash": "hash", "server_redacted": "Br***er", "redacted": True}
            return {}

        provider._get_json = fixture
        service = MarketDataService(provider)

        self.assertIn("MT5 Bridge", service.get_live_price("XAUUSD"))
        self.assertEqual(service.get_historical_candles("XAUUSD", "M15", 10), [])
        self.assertEqual(service.provider_health().status, "OK")

    def test_env_example_safe_and_mt5_docs(self):
        env_text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        docs = (PROJECT_ROOT / "docs" / "operations" / "mt5_bridge_setup.md").read_text(encoding="utf-8").lower()

        self.assertIn("MARKET_DATA_PROVIDER=mt5_bridge", env_text)
        self.assertIn("OANDA_LEGACY_ENABLED=false", env_text)
        self.assertNotIn("sk-or-", env_text)
        self.assertIn("host.docker.internal", docs)
        self.assertIn("outside docker", docs)
        self.assertIn("/execution/controlled-submit", docs)
        self.assertIn("disabled and hard-blocked by default", docs)
        self.assertIn("single isolated production `order_send` call-site", docs)

    def test_no_order_send_endpoint_or_oanda_rest_unit_call(self):
        bridge_server = (PROJECT_ROOT / "tools" / "mt5_bridge" / "server.py").read_text(encoding="utf-8")
        provider_text = (PROJECT_ROOT / "src" / "services" / "trading" / "market" / "mt5_bridge_provider.py").read_text(encoding="utf-8")

        self.assertNotIn(".order" + "_send(", bridge_server)
        for marker in ["/order", "/execute", "/send" + "_order", "/order" + "_send", "/trade", "/position/open"]:
            self.assertNotIn(marker, bridge_server)
        self.assertNotIn("api-fxtrade.oanda.com", provider_text)


if __name__ == "__main__":
    unittest.main()
