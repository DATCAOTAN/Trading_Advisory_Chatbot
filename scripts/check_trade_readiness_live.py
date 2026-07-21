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
from src.services.trading.decision import TradeDecisionPolicyEngine  # noqa: E402
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
    mode = os.getenv("TRADE_READINESS_CHECK_MODE", "autonomous_live")
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
    selection = MethodSelectorService().select(context_pack, mode=mode)
    score_report = SignalScoringEngine().score(feature, calendar, regime, context_pack, selection, mode=mode)

    decision_started = perf_counter()
    decision = TradeDecisionPolicyEngine().decide(score_report, feature, calendar, regime, context_pack, selection, mode=mode)
    decision_latency_ms = (perf_counter() - decision_started) * 1000

    print(f"mode={mode}")
    print(f"symbol={symbol} broker_symbol={feature.broker_symbol}")
    print(f"data_quality={feature.data_quality_status}")
    print(f"calendar_risk_state={calendar.calendar_risk_state}")
    print(f"primary_regime={regime.primary_regime}")
    print(f"primary_method_id={decision.primary_method_id or 'n/a'}")
    print(f"final_context_score={score_report.final_context_score:.4f}")
    print(f"action={decision.action}")
    print(f"readiness_score={decision.readiness_score:.4f}")
    print(f"confidence={decision.confidence:.4f}")
    print(f"grade={decision.grade}")
    print(f"source_refs_count={len(decision.source_refs)}")
    print(f"payload_size_chars={decision.payload_size_chars}")
    print(f"decision_latency_ms={decision_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    if decision.warnings:
        print(f"warnings={','.join(decision.warnings[:10])}")
    if decision.blockers:
        print("blockers=" + ",".join(item.code for item in decision.blockers[:10]))

    if not decision.source_refs:
        return 1
    if decision.action == "UNKNOWN":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
