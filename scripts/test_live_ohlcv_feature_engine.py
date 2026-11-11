import json
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.live_data_service import MarketDataService  # noqa: E402
from src.services.trading.market import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.data_quality import DataQualityGate  # noqa: E402
from src.services.trading.market.feature_engine import FeatureEngine  # noqa: E402
from src.services.trading.market.indicators import IndicatorEngine  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.models import MarketSnapshot, OHLCVBar, TickSnapshot  # noqa: E402
from src.services.trading.market.timeframes import timeframe_duration_seconds  # noqa: E402


def make_bars(mode="up", count=80, timeframe="M15", start_price=2400.0, stale=False, duplicate=False, unsorted=False):
    now = datetime.now(timezone.utc)
    if stale:
        now = now - timedelta(days=5)
    bars = []
    price = start_price
    for index in range(count):
        if mode == "up":
            price += 1.0
        elif mode == "down":
            price -= 1.0
        elif mode == "range":
            price += 0.6 if index % 2 == 0 else -0.6
        timestamp = now - timedelta(seconds=timeframe_duration_seconds(timeframe) * (count - index))
        open_price = price - 0.3
        close = price
        high = max(open_price, close) + 0.5
        low = min(open_price, close) - 0.5
        bars.append(
            OHLCVBar(
                timestamp=timestamp.isoformat(),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=100 + index,
                timeframe=timeframe,
                symbol="XAUUSD",
            )
        )
    if duplicate and len(bars) > 2:
        bars[-1].timestamp = bars[-2].timestamp
    if unsorted and len(bars) > 3:
        bars[-1], bars[-3] = bars[-3], bars[-1]
    return bars


def snapshot(mode="up", timeframe="M15", count=80, **kwargs):
    return MarketSnapshot(
        symbol="XAUUSD",
        timeframe=timeframe,
        bars=make_bars(mode, count, timeframe, **kwargs),
        latest_bid=2500.0,
        latest_ask=2500.2,
        spread=0.2,
        provider_name="mt5_bridge",
        data_quality="COMPLETE",
    )


def provider_with_fixture(timeframe_modes):
    provider = MT5BridgeMarketDataProvider(symbol_map={"XAUUSD": "XAUUSDm"})

    def fixture(path, params=None):
        if path == "/health":
            return {"status": "OK", "message": "fixture"}
        if path == "/tick":
            return {"symbol": "XAUUSDm", "bid": 2500.0, "ask": 2500.2, "spread": 0.2, "timestamp": datetime.now(timezone.utc).isoformat()}
        if path == "/account":
            return {"account_id_hash": "abc123hash", "server_redacted": "Br***er", "redacted": True}
        if path == "/ohlcv":
            timeframe = (params or {}).get("timeframe", "M15")
            mode = timeframe_modes.get(timeframe)
            if mode is None:
                return {"symbol": "XAUUSDm", "timeframe": timeframe, "bars": [], "data_quality": "EMPTY"}
            bars = [bar.as_dict() for bar in make_bars(mode, int((params or {}).get("count", 80)), timeframe)]
            return {"symbol": "XAUUSDm", "timeframe": timeframe, "bars": bars, "source": "mt5_terminal", "data_quality": "COMPLETE"}
        return {}

    provider._get_json = fixture
    return provider


class LiveOhlcvFeatureEngineTests(unittest.TestCase):
    def test_bundle_builder_handles_multiple_timeframes(self):
        provider = provider_with_fixture({"M15": "up", "H1": "up", "H4": "up"})
        bundle = MarketSnapshotBundleBuilder(provider).build("XAUUSD", ["M15", "H1", "H4"], 60)
        self.assertEqual(set(bundle.timeframes), {"M15", "H1", "H4"})
        self.assertEqual(bundle.provider_name, "mt5_bridge")
        self.assertEqual(bundle.broker_symbol, "XAUUSDm")

    def test_missing_timeframe_partial_not_crash(self):
        provider = provider_with_fixture({"M15": "up"})
        bundle = MarketSnapshotBundleBuilder(provider).build("XAUUSD", ["M15", "H1"], 60)
        report = DataQualityGate().evaluate(bundle, ["M15", "H1"])
        self.assertEqual(report.per_timeframe_quality["H1"], "EMPTY")
        self.assertIn(report.status, {"PARTIAL", "INVALID"})

    def test_empty_bars_quality(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({})).build("XAUUSD", ["M15"], 60)
        report = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertEqual(report.per_timeframe_quality["M15"], "EMPTY")

    def test_stale_latest_bar_quality(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        bundle.timeframes["M15"] = snapshot("up", stale=True)
        quality = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertEqual(quality.per_timeframe_quality["M15"], "STALE")

    def test_open_or_future_candle_is_not_a_completed_bar(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        for offset in (-60, 60):
            with self.subTest(offset=offset):
                bundle.timeframes["M15"].bars[-1].timestamp = (
                    datetime.now(timezone.utc) + timedelta(seconds=offset)
                ).isoformat()
                report = DataQualityGate().evaluate(bundle, ["M15"])
                self.assertEqual(report.status, "INVALID")
                self.assertIn("BAR_NOT_COMPLETED", {issue.code for issue in report.issues})

    def test_invalid_high_low_quality(self):
        snap = snapshot("up")
        snap.bars[-1].high = snap.bars[-1].low - 1
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        bundle.timeframes["M15"] = snap
        report = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertEqual(report.per_timeframe_quality["M15"], "INVALID")
        self.assertTrue(any(issue.code == "HIGH_LOW_INVALID" for issue in report.issues))

    def test_duplicate_timestamps_detected(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        bundle.timeframes["M15"] = snapshot("up", duplicate=True)
        report = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertTrue(any(issue.code == "DUPLICATE_TIMESTAMP" for issue in report.issues))

    def test_unsorted_bars_detected(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        bundle.timeframes["M15"] = snapshot("up", unsorted=True)
        report = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertTrue(any(issue.code == "UNSORTED_BARS" for issue in report.issues))

    def test_indicator_engine_computes_core_indicators(self):
        indicators = IndicatorEngine().compute(snapshot("up"))
        self.assertIsNotNone(indicators.sma_fast)
        self.assertIsNotNone(indicators.ema_fast)
        self.assertIsNotNone(indicators.rsi)
        self.assertIsNotNone(indicators.macd)
        self.assertIsNotNone(indicators.atr)

    def test_indicator_output_has_no_nan_or_infinity(self):
        data = IndicatorEngine().compute(snapshot("up")).as_dict()
        encoded = json.dumps(data)
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)

    def test_feature_engine_outputs_up_down_sideways(self):
        self.assertEqual(self._feature_for("up").trend_direction, "UP")
        self.assertEqual(self._feature_for("down").trend_direction, "DOWN")
        self.assertIn(self._feature_for("range").trend_direction, {"SIDEWAYS", "UNKNOWN"})

    def test_volatility_momentum_pullback_range_alignment_spread(self):
        feature = self._feature_for("up", modes={"M15": "up", "H1": "up", "H4": "up"})
        self.assertIn(feature.volatility_state, {"LOW", "NORMAL", "HIGH", "EXTREME", "UNKNOWN"})
        self.assertIn(feature.momentum_state, {"BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"})
        self.assertIsInstance(feature.pullback_detected, bool)
        self.assertGreaterEqual(feature.range_chop_score, 0.0)
        self.assertLessEqual(feature.range_chop_score, 1.0)
        self.assertEqual(feature.multi_timeframe_alignment, "ALIGNED_UP")
        self.assertEqual(feature.spread_state, "OK")

    def test_spread_state_wide_and_unknown(self):
        bundle = MarketSnapshotBundleBuilder(provider_with_fixture({"M15": "up"})).build("XAUUSD", ["M15"], 60)
        report = DataQualityGate().evaluate(bundle, ["M15"])
        bundle.tick = TickSnapshot("XAUUSD", bid=1.0, ask=10.0, spread=9.0)
        self.assertEqual(FeatureEngine().compute(bundle, report).spread_state, "WIDE")
        bundle.tick = TickSnapshot("XAUUSD")
        self.assertEqual(FeatureEngine().compute(bundle, report).spread_state, "UNKNOWN")

    def test_feature_snapshot_contains_no_trade_decision_or_execution_fields(self):
        payload = json.dumps(self._feature_for("up").as_dict()).lower()
        for forbidden in ["buy", "sell", "entry", "stop-loss", "take-profit", "lot", "account-risk", "trade_decision"]:
            self.assertNotIn(forbidden, payload)

    def test_feature_engine_does_not_import_metatrader5_or_order_send(self):
        root = PROJECT_ROOT / "src" / "services" / "trading" / "market"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.py"))
        self.assertNotIn("MetaTrader5", text)
        self.assertNotIn("order_send", text)

    def test_bridge_unavailable_safe_and_live_data_facade_still_works(self):
        provider = MT5BridgeMarketDataProvider(bridge_url="http://127.0.0.1:9", timeout_seconds=0.1)
        bundle = MarketSnapshotBundleBuilder(provider).build("XAUUSD", ["M15"], 60)
        report = DataQualityGate().evaluate(bundle, ["M15"])
        self.assertIn(report.status, {"INVALID", "PARTIAL"})
        service = MarketDataService(provider)
        self.assertIn("unavailable", service.get_live_price("XAUUSD").lower())

    def test_env_example_and_no_oanda_rest_or_qdrant_reset(self):
        env_text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        test_text = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("MARKET_DATA_PROVIDER=mt5_bridge", env_text)
        self.assertNotIn("api-fxtrade" + ".oanda.com", test_text)
        self.assertNotIn("delete" + "_collection", test_text)
        self.assertNotIn("recreate" + "_collection", test_text)

    def _feature_for(self, mode, modes=None):
        provider = provider_with_fixture(modes or {"M15": mode, "H1": mode})
        bundle = MarketSnapshotBundleBuilder(provider).build("XAUUSD", list((modes or {"M15": mode, "H1": mode}).keys()), 80)
        report = DataQualityGate().evaluate(bundle, list(bundle.timeframes.keys()))
        return FeatureEngine().compute(bundle, report, "M15")


if __name__ == "__main__":
    unittest.main()
