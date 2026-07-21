from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    service = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider))
    result = service.build_features(
        symbol=Config.MARKET_DEFAULT_SYMBOL,
        timeframes=Config.MARKET_DEFAULT_TIMEFRAMES,
        candle_count=Config.MARKET_DEFAULT_CANDLE_COUNT,
    )
    bundle = result.bundle
    quality = result.quality_report
    features = result.feature_snapshot
    bars_per_timeframe = {timeframe: len(snapshot.bars) for timeframe, snapshot in bundle.timeframes.items()}
    latest_by_timeframe = quality.latest_timestamp_by_timeframe
    payload = features.as_dict()

    print(f"provider={bundle.provider_name}")
    print(f"symbol={bundle.symbol} broker_symbol={bundle.broker_symbol}")
    print(f"timeframes={','.join(bundle.timeframes.keys())}")
    print(f"bars_per_timeframe={json.dumps(bars_per_timeframe, sort_keys=True)}")
    print(f"latest_timestamp_by_timeframe={json.dumps(latest_by_timeframe, sort_keys=True)}")
    print(f"data_quality={quality.status}")
    print(f"trend_direction={features.trend_direction}")
    print(f"trend_strength={features.trend_strength:.4f}")
    print(f"volatility_state={features.volatility_state}")
    print(f"momentum_state={features.momentum_state}")
    print(f"pullback_detected={features.pullback_detected}")
    print(f"range_chop_score={features.range_chop_score:.4f}")
    print(f"spread_state={features.spread_state}")
    print(f"bundle_latency_ms={result.bundle_latency_ms:.2f}")
    print(f"feature_latency_ms={result.feature_latency_ms:.2f}")
    print(f"payload_chars={len(json.dumps(payload, sort_keys=True))}")
    if features.blockers:
        print(f"blockers={','.join(features.blockers)}")
    if features.warnings:
        print(f"warnings={','.join(features.warnings[:10])}")

    if quality.status in {"INVALID", "EMPTY"}:
        return 1
    if not any(count > 0 for count in bars_per_timeframe.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
