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
from src.services.trading.execution import DryRunConfirmationService, SimulatedExecutionJournalStore, SimulatedExecutionService  # noqa: E402
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402
from src.services.trading.proposal import (  # noqa: E402
    HumanProposalConfirmationService,
    ProposalBoundaryPolicy,
    ProposalDraftService,
)
from src.services.trading.reasoning import MethodSelectorService  # noqa: E402
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter  # noqa: E402
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("SIMULATED_ADAPTER_CHECK_MODE", "REVIEW_ONLY")
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

    adapter_started = perf_counter()
    simulated_result = SimulatedExecutionService().run(
        draft_result.draft,
        intent=proposal_result.intent,
        dry_run_receipt=dry_run_result.receipt,
        execution_journal_record=dry_run_result.journal_record,
        proposal_draft_journal_record=draft_result.journal_record,
    )
    simulated_adapter_latency_ms = (perf_counter() - adapter_started) * 1000
    read_started = perf_counter()
    store = SimulatedExecutionJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    simulated_journal_read_latency_ms = (perf_counter() - read_started) * 1000

    contract = simulated_result.contract
    receipt = simulated_result.receipt
    journal_record = simulated_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0

    print(f"mode={mode}")
    print(f"symbol={contract.symbol} broker_symbol={contract.broker_symbol}")
    print(f"adapter_type={simulated_result.adapter_health.adapter_type}")
    print(f"adapter_status={simulated_result.adapter_health.status}")
    print(f"contract_status={contract.contract_status}")
    print(f"simulated_only={str(receipt.simulated_only).lower()}")
    print(f"executable={str(receipt.executable).lower()}")
    print(f"executed={str(receipt.executed).lower()}")
    print(f"accepted_by_adapter={str(receipt.accepted_by_adapter).lower()}")
    print(f"draft_status={draft_result.draft.status}")
    print(f"proposal_workflow_allowed={str(draft_result.draft.proposal_workflow_allowed).lower()}")
    print(f"artifact_hash_prefix={contract.artifact_hash[:12]}")
    print(f"idempotency_key_prefix={contract.idempotency_key[:12]}")
    print(f"source_refs_count={len(contract.source_refs)}")
    print(f"receipt_payload_size={receipt.payload_size_chars}")
    print(f"journal_record_id={journal_record.journal_record_id if journal_record else 'n/a'}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_simulated_records={summary.total_records}")
    print(f"total_accepted={summary.total_accepted}")
    print(f"total_rejected={summary.total_rejected}")
    print(f"contract_build_and_adapter_latency_ms={simulated_adapter_latency_ms:.2f}")
    print(f"simulated_journal_read_latency_ms={simulated_journal_read_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"simulated_journal_file_size_bytes={journal_file_size}")
    if simulated_result.warning:
        print(f"warning={simulated_result.warning}")

    if not receipt.simulated_only:
        return 1
    if receipt.executable:
        return 1
    if receipt.executed:
        return 1
    if journal_record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
