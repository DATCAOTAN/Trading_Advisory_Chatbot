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
from src.services.trading.execution import (  # noqa: E402
    DryRunConfirmationService,
    LiveExecutionBlockJournalStore,
    MT5ExecutionSkeletonService,
    SimulatedExecutionService,
)
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402
from src.services.trading.proposal import HumanProposalConfirmationService, ProposalBoundaryPolicy, ProposalDraftService  # noqa: E402
from src.services.trading.reasoning import MethodSelectorService  # noqa: E402
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter  # noqa: E402
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("MT5_SKELETON_CHECK_MODE", "REVIEW_ONLY")
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
    context_pack = RuntimeContextPackBuilder().build(
        candidates,
        feature,
        calendar,
        regime,
        "autonomous_live",
        symbol,
        feature.broker_symbol,
    )
    selection = MethodSelectorService().select(context_pack, mode="autonomous_live")
    score_report = SignalScoringEngine().score(feature, calendar, regime, context_pack, selection, mode="autonomous_live")
    readiness = TradeDecisionPolicyEngine().decide(
        score_report,
        feature,
        calendar,
        regime,
        context_pack,
        selection,
        mode="autonomous_live",
    )
    artifact = HumanReviewArtifactBuilder().build(readiness, score_report, selection, context_pack, regime, calendar, feature)
    card = HumanReviewFormatter().to_card(artifact)
    dry_run_result = DryRunConfirmationService().run(artifact, card=card, mode=mode)
    boundary_policy = ProposalBoundaryPolicy.from_config()
    proposal_result = HumanProposalConfirmationService(policy=boundary_policy).confirm_with_journal(
        artifact,
        dry_run_result.receipt,
        execution_journal_record=dry_run_result.journal_record,
        user_acknowledgement_text=boundary_policy.confirmation_phrase,
    )
    draft_result = ProposalDraftService().build(
        proposal_result.intent,
        artifact,
        score_report,
        selection,
        context_pack,
        calendar_context=calendar,
        regime_snapshot=regime,
        feature_snapshot=feature,
    )
    simulated_result = SimulatedExecutionService().run(
        draft_result.draft,
        intent=proposal_result.intent,
        dry_run_receipt=dry_run_result.receipt,
        execution_journal_record=dry_run_result.journal_record,
        proposal_draft_journal_record=draft_result.journal_record,
    )

    skeleton_started = perf_counter()
    skeleton_result = MT5ExecutionSkeletonService().run(
        simulated_result.contract,
        simulated_result.receipt,
        simulated_result.journal_record,
    )
    skeleton_latency_ms = (perf_counter() - skeleton_started) * 1000
    read_started = perf_counter()
    store = LiveExecutionBlockJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    journal_read_latency_ms = (perf_counter() - read_started) * 1000

    report = skeleton_result.capability_report
    receipt = skeleton_result.blocked_receipt
    journal_record = skeleton_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0

    print(f"mode={mode}")
    print(f"symbol={simulated_result.contract.symbol} broker_symbol={simulated_result.contract.broker_symbol}")
    print(f"skeleton_status={report.skeleton_status}")
    print(f"live_execution_supported={str(report.live_execution_supported).lower()}")
    print(f"live_execution_enabled={str(report.live_execution_enabled).lower()}")
    print(f"mt5_order_send_available={str(report.mt5_order_send_available).lower()}")
    print(f"hard_live_block_enabled={str(report.hard_live_block_enabled).lower()}")
    print(f"blocked={str(receipt.blocked).lower()}")
    print(f"executed={str(receipt.executed).lower()}")
    print(f"order_sent={str(receipt.order_sent).lower()}")
    print(f"block_reason={receipt.block_reason}")
    print(f"source_contract_id={receipt.source_contract_id}")
    print(f"source_simulated_receipt_id={receipt.source_simulated_receipt_id}")
    print(f"artifact_hash_prefix={receipt.artifact_hash[:12]}")
    print(f"idempotency_key_prefix={receipt.idempotency_key[:12]}")
    print(f"source_refs_count={len(receipt.source_refs)}")
    print(f"receipt_payload_size={receipt.payload_size_chars}")
    print(f"journal_record_id={journal_record.journal_record_id if journal_record else 'n/a'}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_live_block_records={summary.total_records}")
    print(f"total_blocked={summary.total_blocked}")
    print(f"capability_and_block_latency_ms={skeleton_latency_ms:.2f}")
    print(f"live_block_journal_read_latency_ms={journal_read_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"live_block_journal_file_size_bytes={journal_file_size}")
    if skeleton_result.warning:
        print(f"warning={skeleton_result.warning}")

    if report.live_execution_supported:
        return 1
    if report.live_execution_enabled:
        return 1
    if report.mt5_order_send_available:
        return 1
    if not report.hard_live_block_enabled:
        return 1
    if not receipt.blocked:
        return 1
    if receipt.executed:
        return 1
    if receipt.order_sent:
        return 1
    if journal_record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
