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
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter  # noqa: E402
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("HUMAN_REVIEW_CHECK_MODE", "autonomous_live")
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
    readiness = TradeDecisionPolicyEngine().decide(score_report, feature, calendar, regime, context_pack, selection, mode=mode)

    artifact_started = perf_counter()
    artifact = HumanReviewArtifactBuilder().build(readiness, score_report, selection, context_pack, regime, calendar, feature)
    artifact_latency_ms = (perf_counter() - artifact_started) * 1000
    format_started = perf_counter()
    card = HumanReviewFormatter().to_card(artifact)
    markdown = HumanReviewFormatter().to_markdown(artifact)
    markdown_latency_ms = (perf_counter() - format_started) * 1000

    print(f"mode={mode}")
    print(f"symbol={symbol} broker_symbol={feature.broker_symbol}")
    print(f"review_status={artifact.review_status}")
    print(f"readiness_action={artifact.readiness_action}")
    print(f"readiness_score={artifact.readiness_score:.4f}")
    print(f"confidence={artifact.confidence:.4f}")
    print(f"grade={artifact.grade}")
    print(f"primary_method_id={artifact.primary_method_id or 'n/a'}")
    print(f"primary_regime={artifact.primary_regime}")
    print(f"calendar_risk_state={artifact.calendar_risk_state}")
    print(f"final_context_score={artifact.final_context_score:.4f}")
    print(f"blockers_count={len(artifact.blockers)}")
    print(f"warnings_count={len(artifact.warnings)}")
    print(f"source_refs_count={len(artifact.source_refs)}")
    print(f"artifact_payload_size_chars={artifact.payload_size_chars}")
    print(f"card_payload_size_chars={card.payload_size_chars}")
    print(f"markdown_chars={len(markdown)}")
    print(f"artifact_build_latency_ms={artifact_latency_ms:.2f}")
    print(f"markdown_format_latency_ms={markdown_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")

    if not artifact.source_refs:
        return 1
    if artifact.review_status == "UNKNOWN":
        return 1
    if not card.summary:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
