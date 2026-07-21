from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config  # noqa: E402
from src.services.trading.calendar import CalendarContextBuilder, ForexFactoryCalendarProvider  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402


def main() -> int:
    start_total = perf_counter()
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    feature_service = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider))
    feature_result = feature_service.build_features(
        symbol=Config.MARKET_DEFAULT_SYMBOL,
        timeframes=Config.MARKET_DEFAULT_TIMEFRAMES,
        candle_count=Config.MARKET_DEFAULT_CANDLE_COUNT,
    )
    calendar_start = perf_counter()
    calendar_provider = ForexFactoryCalendarProvider()
    calendar_context = CalendarContextBuilder(calendar_provider).build(symbol=Config.MARKET_DEFAULT_SYMBOL)
    calendar_latency_ms = (perf_counter() - calendar_start) * 1000
    regime_start = perf_counter()
    regime = MarketRegimeDetector().detect(feature_result.feature_snapshot, calendar_context)
    regime_latency_ms = (perf_counter() - regime_start) * 1000

    bundle = feature_result.bundle
    features = feature_result.feature_snapshot
    quality = feature_result.quality_report
    bars_per_timeframe = {timeframe: len(snapshot.bars) for timeframe, snapshot in bundle.timeframes.items()}
    next_event = calendar_context.next_high_impact_event
    next_event_summary = "n/a"
    if next_event:
        next_event_summary = f"{next_event.currency}:{next_event.impact}:{next_event.title[:80]}"

    print(f"provider={bundle.provider_name}")
    print(f"symbol={bundle.symbol} broker_symbol={bundle.broker_symbol}")
    print(f"timeframes={','.join(bundle.timeframes.keys())}")
    print(f"bars_per_timeframe={json.dumps(bars_per_timeframe, sort_keys=True)}")
    print(f"data_quality={quality.status}")
    print(f"trend_direction={features.trend_direction}")
    print(f"trend_strength={features.trend_strength:.4f}")
    print(f"volatility_state={features.volatility_state}")
    print(f"momentum_state={features.momentum_state}")
    print(f"range_chop_score={features.range_chop_score:.4f}")
    print(f"calendar_provider_health={calendar_provider.health_check().status}")
    print(f"calendar_cache_status={calendar_context.cache_status}")
    print(f"next_high_impact_event={next_event_summary}")
    minutes = calendar_context.minutes_to_next_high_impact_event
    print(f"minutes_to_next_high_impact_event={minutes if minutes is not None else 'n/a'}")
    print(f"calendar_risk_state={calendar_context.calendar_risk_state}")
    print(f"primary_regime={regime.primary_regime}")
    print(f"secondary_regimes={','.join(regime.secondary_regimes) if regime.secondary_regimes else 'n/a'}")
    print(f"confidence={regime.confidence:.4f}")
    print(f"calendar_latency_ms={calendar_latency_ms:.2f}")
    print(f"regime_latency_ms={regime_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - start_total) * 1000:.2f}")
    if regime.warnings:
        print(f"warnings={','.join(regime.warnings[:10])}")
    if regime.blockers:
        print(f"blockers={','.join(regime.blockers[:10])}")

    if quality.status in {"INVALID", "EMPTY"}:
        return 1
    if not any(count > 0 for count in bars_per_timeframe.values()):
        return 1
    if not regime.primary_regime:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
