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
from src.services.trading.execution import DryRunConfirmationService, ExecutionJournalStore  # noqa: E402
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
    mode = os.getenv("EXECUTION_JOURNAL_CHECK_MODE", "REVIEW_ONLY")
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

    service_started = perf_counter()
    result = DryRunConfirmationService().run(artifact, card=card, mode=mode)
    dry_run_service_latency_ms = (perf_counter() - service_started) * 1000
    read_started = perf_counter()
    store = ExecutionJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    journal_read_latency_ms = (perf_counter() - read_started) * 1000

    receipt = result.receipt
    record = result.journal_record
    journal_path = str(store.path)
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0

    print(f"mode={mode}")
    print(f"symbol={artifact.symbol} broker_symbol={artifact.broker_symbol}")
    print(f"review_status={artifact.review_status}")
    print(f"readiness_action={artifact.readiness_action}")
    print(f"gate_action={result.gate_decision.action}")
    print(f"dry_run_allowed={str(receipt.allowed).lower()}")
    print(f"executed={str(receipt.executed).lower()}")
    print(f"dry_run_only={str(receipt.dry_run_only).lower()}")
    print(f"artifact_hash_prefix={receipt.artifact_hash[:12]}")
    print(f"idempotency_key_prefix={receipt.idempotency_key[:12]}")
    print(f"journal_record_id={record.journal_record_id if record else 'n/a'}")
    print(f"journal_path={journal_path}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_dry_runs={summary.total_dry_runs}")
    print(f"total_blocked={summary.total_blocked}")
    print(f"total_allowed={summary.total_allowed}")
    print(f"source_refs_count={len(receipt.source_refs)}")
    print(f"journal_append_latency_ms={dry_run_service_latency_ms:.2f}")
    print(f"journal_read_latency_ms={journal_read_latency_ms:.2f}")
    print(f"dry_run_service_latency_ms={dry_run_service_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"journal_file_size_bytes={journal_file_size}")
    if result.warning:
        print(f"warning={result.warning}")

    if receipt.executed:
        return 1
    if not receipt.dry_run_only:
        return 1
    if record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
