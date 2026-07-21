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
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("SIGNAL_SCORE_CHECK_MODE", "autonomous_live")
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
    selection_service = MethodSelectorService()
    selection = selection_service.select(context_pack, mode=mode)

    scoring_started = perf_counter()
    score_report = SignalScoringEngine().score(feature, calendar, regime, context_pack, selection, mode=mode)
    scoring_latency_ms = (perf_counter() - scoring_started) * 1000

    print(f"mode={mode}")
    print(f"symbol={symbol} broker_symbol={feature.broker_symbol}")
    print(f"data_quality={feature.data_quality_status}")
    print(f"calendar_risk_state={calendar.calendar_risk_state}")
    print(f"primary_regime={regime.primary_regime}")
    print(f"primary_method_id={score_report.primary_method_id or 'n/a'}")
    print(f"selected_playbook_ids={','.join(score_report.selected_playbook_ids) if score_report.selected_playbook_ids else 'n/a'}")
    print("component_scores=" + _component_summary(score_report))
    print(f"final_context_score={score_report.final_context_score:.4f}")
    print(f"grade={score_report.grade}")
    print(f"source_refs_count={len(score_report.source_refs)}")
    print(f"payload_size_chars={score_report.payload_size_chars}")
    print(f"scoring_latency_ms={scoring_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    if score_report.warnings:
        print(f"warnings={','.join(score_report.warnings[:10])}")
    if score_report.blockers:
        print(f"blockers={','.join(score_report.blockers[:10])}")

    if feature.data_quality_status in {"INVALID", "EMPTY"}:
        return 1
    if not score_report.primary_method_id:
        return 1
    if not score_report.source_refs:
        return 1
    return 0


def _component_summary(report) -> str:
    components = report.components.as_dict() if report.components else {}
    items = []
    for name, value in components.items():
        if not isinstance(value, dict):
            continue
        items.append(f"{name}:{value.get('score', 0.0):.4f}/{value.get('grade', 'UNKNOWN')}")
    return ";".join(items)


if __name__ == "__main__":
    sys.exit(main())
