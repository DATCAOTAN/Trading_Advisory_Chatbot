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
from src.services.trading.execution import DryRunExecutionAdapter, ExecutionGate  # noqa: E402
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
    mode = os.getenv("EXECUTION_GATE_CHECK_MODE", "REVIEW_ONLY")
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
    candidates = KnowledgeRouter().route("autonomous_live", symbol, feature, calendar, regime)
    context_pack = RuntimeContextPackBuilder().build(candidates, feature, calendar, regime, "autonomous_live", symbol, feature.broker_symbol)
    selection = MethodSelectorService().select(context_pack, mode="autonomous_live")
    score_report = SignalScoringEngine().score(feature, calendar, regime, context_pack, selection, mode="autonomous_live")
    readiness = TradeDecisionPolicyEngine().decide(score_report, feature, calendar, regime, context_pack, selection, mode="autonomous_live")
    artifact = HumanReviewArtifactBuilder().build(readiness, score_report, selection, context_pack, regime, calendar, feature)
    card = HumanReviewFormatter().to_card(artifact)

    gate_started = perf_counter()
    gate_decision = ExecutionGate().evaluate(artifact, card=card, mode=mode)
    gate_latency_ms = (perf_counter() - gate_started) * 1000
    receipt_started = perf_counter()
    receipt = DryRunExecutionAdapter().run(gate_decision, artifact)
    receipt_latency_ms = (perf_counter() - receipt_started) * 1000

    print(f"mode={mode}")
    print(f"symbol={artifact.symbol} broker_symbol={artifact.broker_symbol}")
    print(f"review_status={artifact.review_status}")
    print(f"readiness_action={artifact.readiness_action}")
    print(f"gate_action={gate_decision.action}")
    print(f"dry_run_allowed={str(receipt.allowed).lower()}")
    print(f"executed={str(receipt.executed).lower()}")
    print(f"dry_run_only={str(receipt.dry_run_only).lower()}")
    print(f"artifact_hash_prefix={gate_decision.artifact_hash[:12]}")
    print(f"idempotency_key_prefix={receipt.idempotency_key[:12]}")
    print(f"blockers_count={len(receipt.blockers)}")
    print(f"warnings_count={len(receipt.warnings)}")
    print(f"source_refs_count={len(receipt.source_refs)}")
    print(f"gate_payload_size_chars={gate_decision.payload_size_chars}")
    print(f"receipt_payload_size_chars={receipt.payload_size_chars}")
    print(f"gate_decision_latency_ms={gate_latency_ms:.2f}")
    print(f"dry_run_receipt_latency_ms={receipt_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")

    if receipt.executed:
        return 1
    if not receipt.dry_run_only:
        return 1
    if not receipt.source_refs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
