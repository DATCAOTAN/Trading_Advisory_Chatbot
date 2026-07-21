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
    LiveExecutionPreflightService,
    LivePermissionGateService,
    LivePermissionJournalStore,
    LivePermissionPolicy,
    MT5ExecutionSkeletonService,
    SimulatedExecutionService,
)
from src.services.trading.execution.live_design import LiveExecutionDesignSpecService  # noqa: E402
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
    mode = os.getenv("LIVE_PERMISSION_CHECK_MODE", "REVIEW_ONLY")
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
    skeleton_result = MT5ExecutionSkeletonService().run(
        simulated_result.contract,
        simulated_result.receipt,
        simulated_result.journal_record,
    )
    design_result = LiveExecutionDesignSpecService().build_and_record(
        skeleton_result.capability_report,
        skeleton_result.blocked_receipt,
        contract=simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
        draft=draft_result.draft,
    )
    preflight_result = LiveExecutionPreflightService().run(
        design_result.report,
        skeleton_result.capability_report,
        skeleton_result.blocked_receipt,
        simulated_contract=simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
        live_block_journal_record=skeleton_result.journal_record,
    )

    permission_policy = LivePermissionPolicy.from_config()
    permission_started = perf_counter()
    permission_result = LivePermissionGateService(policy=permission_policy).run(
        preflight_result.report,
        design_result.report,
        skeleton_result.capability_report,
        skeleton_result.blocked_receipt,
        simulated_contract=simulated_result.contract,
        proposal_draft=draft_result.draft,
        user_acknowledgement_text=permission_policy.confirmation_phrase,
    )
    permission_latency_ms = (perf_counter() - permission_started) * 1000
    read_started = perf_counter()
    store = LivePermissionJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    journal_read_latency_ms = (perf_counter() - read_started) * 1000

    intent = permission_result.intent
    decision = permission_result.decision
    journal_record = permission_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0
    timings = permission_result.timings_ms or {}

    print(f"permission_status={intent.permission_status}")
    print(f"confirmation_state={intent.confirmation_state}")
    print(f"gate_allowed={str(decision.gate_allowed).lower()}")
    print(f"order_intent_workflow_allowed={str(decision.order_intent_workflow_allowed).lower()}")
    print(f"live_execution_allowed={str(decision.live_execution_allowed).lower()}")
    print(f"order_send_allowed={str(decision.order_send_allowed).lower()}")
    print(f"execution_allowed={str(decision.execution_allowed).lower()}")
    print(f"hard_live_block_required={str(decision.hard_live_block_required).lower()}")
    print(f"source_refs_count={len(intent.source_refs)}")
    print(f"intent_payload_size={intent.payload_size_chars}")
    print(f"decision_payload_size={decision.payload_size_chars}")
    print(f"journal_record_id={journal_record.journal_record_id if journal_record else 'n/a'}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_permission_records={summary.total_records}")
    print(f"permission_intent_build_latency_ms={timings.get('permission_intent_build_latency_ms', 0.0):.2f}")
    print(f"permission_gate_latency_ms={timings.get('permission_gate_latency_ms', 0.0):.2f}")
    print(f"permission_journal_append_latency_ms={timings.get('permission_journal_append_latency_ms', 0.0):.2f}")
    print(f"permission_journal_read_latency_ms={journal_read_latency_ms:.2f}")
    print(f"permission_service_latency_ms={permission_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"permission_journal_file_size_bytes={journal_file_size}")
    if permission_result.warning:
        print(f"warning={permission_result.warning}")

    if decision.live_execution_allowed or decision.order_send_allowed or decision.execution_allowed:
        return 1
    if not decision.hard_live_block_required:
        return 1
    if journal_record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
