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
from src.services.trading.knowledge import KnowledgeRouter, KnowledgeSelectionValidator, RuntimeContextPackBuilder  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("KNOWLEDGE_ROUTER_CHECK_MODE", "autonomous_live")
    symbol = Config.MARKET_DEFAULT_SYMBOL

    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    feature_service = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider))
    feature_result = feature_service.build_features(symbol, Config.MARKET_DEFAULT_TIMEFRAMES, Config.MARKET_DEFAULT_CANDLE_COUNT)
    feature = feature_result.feature_snapshot
    calendar = CalendarContextBuilder(ForexFactoryCalendarProvider()).build(symbol=symbol)
    regime = MarketRegimeDetector().detect(feature, calendar)

    router_start = perf_counter()
    candidates = KnowledgeRouter().route(mode, symbol, feature, calendar, regime)
    router_latency_ms = (perf_counter() - router_start) * 1000
    pack_start = perf_counter()
    pack = RuntimeContextPackBuilder().build(candidates, feature, calendar, regime, mode, symbol, feature.broker_symbol)
    pack_latency_ms = (perf_counter() - pack_start) * 1000
    validation = KnowledgeSelectionValidator().validate(pack)

    print(f"mode={mode}")
    print(f"symbol={symbol} broker_symbol={feature.broker_symbol}")
    print(f"data_quality={feature.data_quality_status}")
    print(f"calendar_risk_state={calendar.calendar_risk_state}")
    print(f"primary_regime={regime.primary_regime}")
    print(f"selected_method_card_ids={','.join(item['method_id'] for item in pack.selected_method_cards) or 'n/a'}")
    print(f"selected_macro_card_ids={','.join(item['macro_id'] for item in pack.selected_macro_cards) or 'n/a'}")
    print(f"selected_playbook_ids={','.join(item['playbook_id'] for item in pack.selected_playbooks) or 'n/a'}")
    print(f"source_refs_count={len(pack.source_refs)}")
    print(f"payload_size_chars={pack.payload_size_chars}")
    print(f"token_budget_estimate={pack.token_budget_estimate}")
    print(f"router_latency_ms={router_latency_ms:.2f}")
    print(f"context_pack_build_latency_ms={pack_latency_ms:.2f}")
    if pack.warnings:
        print(f"warnings={','.join(pack.warnings[:10])}")
    if pack.blockers:
        print(f"blockers={','.join(pack.blockers[:10])}")
    if not validation.passed:
        print(f"validation_issues={','.join(validation.issues[:10])}")
        return 1
    if feature.data_quality_status in {"INVALID", "EMPTY"}:
        return 1
    if not pack.source_refs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
