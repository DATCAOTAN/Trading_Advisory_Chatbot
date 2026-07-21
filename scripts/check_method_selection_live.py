from __future__ import annotations

import os
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config  # noqa: E402
from src.services.trading.calendar import CalendarContextBuilder, ForexFactoryCalendarProvider  # noqa: E402
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402
from src.services.trading.reasoning import MethodSelectorService  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("METHOD_SELECTION_CHECK_MODE", "autonomous_live")
    symbol = Config.MARKET_DEFAULT_SYMBOL
    started = perf_counter()

    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    feature_result = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider)).build_features(
        symbol,
        Config.MARKET_DEFAULT_TIMEFRAMES,
        Config.MARKET_DEFAULT_CANDLE_COUNT,
    )
    feature = feature_result.feature_snapshot
    calendar = CalendarContextBuilder(ForexFactoryCalendarProvider()).build(symbol=symbol)
    regime = MarketRegimeDetector().detect(feature, calendar)
    candidates = KnowledgeRouter().route(mode, symbol, feature, calendar, regime)
    context_pack = RuntimeContextPackBuilder().build(candidates, feature, calendar, regime, mode, symbol, feature.broker_symbol)

    selector = MethodSelectorService()
    result = selector.select(context_pack, mode=mode)

    print(f"mode={mode}")
    print(f"symbol={symbol} broker_symbol={feature.broker_symbol}")
    print(f"data_quality={feature.data_quality_status}")
    print(f"calendar_risk_state={calendar.calendar_risk_state}")
    print(f"primary_regime={regime.primary_regime}")
    print(f"primary_method_id={result.primary_method_id or 'n/a'}")
    print(f"supporting_method_ids={','.join(result.supporting_method_ids) if result.supporting_method_ids else 'n/a'}")
    print(f"rejected_method_ids={','.join(result.rejected_method_ids) if result.rejected_method_ids else 'n/a'}")
    print(f"selected_playbook_ids={','.join(result.selected_playbook_ids) if result.selected_playbook_ids else 'n/a'}")
    print(f"confidence={result.confidence:.4f}")
    print(f"overall_context_fit={result.overall_context_fit:.4f}")
    print(f"source_refs_count={len(result.source_refs)}")
    print(f"used_llm={str(selector.last_used_llm).lower()}")
    print(f"method_selection_latency_ms={selector.last_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    if result.warnings:
        print(f"warnings={','.join(result.warnings[:10])}")
    if result.blockers:
        print(f"blockers={','.join(result.blockers[:10])}")

    if feature.data_quality_status in {"INVALID", "EMPTY"}:
        return 1
    if not result.primary_method_id:
        return 1
    if not result.source_refs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
