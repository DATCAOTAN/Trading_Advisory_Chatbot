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
from src.services.trading.execution import DryRunConfirmationService  # noqa: E402
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder  # noqa: E402
from src.services.trading.market.live_feature_service import LiveFeatureService  # noqa: E402
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder  # noqa: E402
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402
from src.services.trading.proposal import HumanProposalConfirmationService, ProposalBoundaryPolicy, ProposalIntentJournalStore  # noqa: E402
from src.services.trading.reasoning import MethodSelectorService  # noqa: E402
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter  # noqa: E402
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("PROPOSAL_BOUNDARY_CHECK_MODE", "REVIEW_ONLY")
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
    policy = ProposalBoundaryPolicy.from_config()
    confirm_started = perf_counter()
    proposal_result = HumanProposalConfirmationService(policy=policy).confirm_with_journal(
        artifact,
        dry_run_result.receipt,
        execution_journal_record=dry_run_result.journal_record,
        user_acknowledgement_text=policy.confirmation_phrase,
    )
    proposal_confirmation_latency_ms = (perf_counter() - confirm_started) * 1000
    read_started = perf_counter()
    store = ProposalIntentJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    proposal_journal_read_latency_ms = (perf_counter() - read_started) * 1000

    intent = proposal_result.intent
    journal_record = proposal_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0

    print(f"mode={mode}")
    print(f"symbol={intent.symbol} broker_symbol={intent.broker_symbol}")
    print(f"review_status={intent.review_status}")
    print(f"readiness_action={intent.readiness_action}")
    print(f"gate_action={intent.gate_action}")
    print(f"dry_run_only={str(intent.dry_run_only).lower()}")
    print(f"dry_run_executed={str(intent.dry_run_executed).lower()}")
    print(f"proposal_boundary_status={intent.proposal_boundary_status}")
    print(f"human_confirmation_state={intent.human_confirmation_state}")
    print(f"proposal_workflow_allowed={str(intent.proposal_workflow_allowed).lower()}")
    print(f"executable={str(intent.executable).lower()}")
    print(f"artifact_hash_prefix={intent.artifact_hash[:12]}")
    print(f"idempotency_key_prefix={intent.idempotency_key[:12]}")
    print(f"intent_id={intent.intent_id}")
    print(f"proposal_intent_journal_record_id={journal_record.journal_record_id if journal_record else 'n/a'}")
    print(f"source_refs_count={len(intent.source_refs)}")
    print(f"payload_size_chars={intent.payload_size_chars}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_intents={summary.total_intents}")
    print(f"total_confirmed={summary.total_confirmed}")
    print(f"total_blocked={summary.total_blocked}")
    print(f"proposal_confirmation_latency_ms={proposal_confirmation_latency_ms:.2f}")
    print(f"proposal_journal_read_latency_ms={proposal_journal_read_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"proposal_journal_file_size_bytes={journal_file_size}")
    if proposal_result.warning:
        print(f"warning={proposal_result.warning}")

    if not intent.dry_run_only:
        return 1
    if intent.executable:
        return 1
    if intent.dry_run_executed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
