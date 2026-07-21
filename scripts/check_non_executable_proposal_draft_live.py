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
from src.services.trading.proposal import (  # noqa: E402
    HumanProposalConfirmationService,
    ProposalBoundaryPolicy,
    ProposalDraftJournalStore,
    ProposalDraftService,
)
from src.services.trading.reasoning import MethodSelectorService  # noqa: E402
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter  # noqa: E402
from src.services.trading.scoring import SignalScoringEngine  # noqa: E402


def main() -> int:
    bridge_url = os.getenv("MT5_BRIDGE_CHECK_URL") or Config.MT5_BRIDGE_URL
    if "host.docker.internal" in bridge_url:
        bridge_url = "http://127.0.0.1:8765"
    mode = os.getenv("PROPOSAL_DRAFT_CHECK_MODE", "REVIEW_ONLY")
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

    build_started = perf_counter()
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
    draft_build_latency_ms = (perf_counter() - build_started) * 1000
    read_started = perf_counter()
    store = ProposalDraftJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    draft_journal_read_latency_ms = (perf_counter() - read_started) * 1000

    draft = draft_result.draft
    record = draft_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0

    print(f"mode={mode}")
    print(f"symbol={draft.symbol} broker_symbol={draft.broker_symbol}")
    print(f"draft_status={draft.status}")
    print(f"non_executable={str(draft.non_executable).lower()}")
    print(f"executable={str(draft.executable).lower()}")
    print(f"proposal_workflow_allowed={str(draft.proposal_workflow_allowed).lower()}")
    print(f"primary_method_id={draft.primary_method_id}")
    print(f"primary_regime={draft.primary_regime}")
    print(f"calendar_risk_state={draft.calendar_risk_state}")
    print(f"readiness_action={draft.readiness_action}")
    print(f"review_status={draft.review_status}")
    print(f"final_context_score={draft.final_context_score:.4f}")
    print(f"blockers_count={len(draft.blockers)}")
    print(f"warnings_count={len(draft.warnings)}")
    print(f"human_checks_count={len(draft.required_human_checks)}")
    print(f"source_refs_count={len(draft.source_refs)}")
    print(f"draft_payload_size={draft.payload_size_chars}")
    print(f"card_payload_size={draft_result.card.payload_size_chars}")
    print(f"journal_record_id={record.journal_record_id if record else 'n/a'}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_drafts={summary.total_records}")
    print(f"total_created={summary.total_created}")
    print(f"total_blocked={summary.total_blocked}")
    print(f"draft_build_latency_ms={draft_build_latency_ms:.2f}")
    print(f"draft_journal_read_latency_ms={draft_journal_read_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"proposal_draft_journal_file_size_bytes={journal_file_size}")
    if draft_result.warning:
        print(f"warning={draft_result.warning}")

    if not draft.non_executable:
        return 1
    if draft.executable:
        return 1
    if record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
