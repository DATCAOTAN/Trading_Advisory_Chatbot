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
    ControlledLiveParameterValueProposalService,
    DryRunConfirmationService,
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE,
    HumanReviewedLiveParameterDraftService,
    HumanValueApprovalLockService,
    LiveExecutionPreflightService,
    LiveOrderContractFinalReviewService,
    LiveOrderContractParameterizationService,
    LiveOrderContractSkeletonService,
    LiveOrderIntentService,
    LiveOrderParameterPolicyService,
    LiveOrderParameterSourceBoundaryService,
    LivePermissionGateService,
    LivePermissionPolicy,
    MT5ExecutionSkeletonService,
    MT5OrderRequestDryRunPayloadValidationService,
    MT5RequestDictDryRunBuilderJournalStore,
    MT5RequestDictDryRunBuilderService,
    MT5RequestDraftFinalApprovalService,
    MT5RequestDraftService,
    PreMT5OrderRequestMappingService,
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
    mode = os.getenv("CONTRACT_FINAL_REVIEW_CHECK_MODE", "REVIEW_ONLY")
    symbol = Config.MARKET_DEFAULT_SYMBOL
    started = perf_counter()

    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    feature = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider)).build_features(
        symbol,
        Config.MARKET_DEFAULT_TIMEFRAMES,
        Config.MARKET_DEFAULT_CANDLE_COUNT,
    ).feature_snapshot
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
    permission_result = LivePermissionGateService(policy=permission_policy).run(
        preflight_result.report,
        design_result.report,
        skeleton_result.capability_report,
        skeleton_result.blocked_receipt,
        simulated_contract=simulated_result.contract,
        proposal_draft=draft_result.draft,
        user_acknowledgement_text=permission_policy.confirmation_phrase,
    )
    live_order_result = LiveOrderIntentService().run(
        permission_result.intent,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    contract_result = LiveOrderContractSkeletonService().run(
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    policy_result = LiveOrderParameterPolicyService().run(
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    source_result = LiveOrderParameterSourceBoundaryService().run(
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    parameter_draft_result = HumanReviewedLiveParameterDraftService().run(
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    value_proposal_result = ControlledLiveParameterValueProposalService().run(
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    approval_lock_result = HumanValueApprovalLockService().run(
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
        confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    )

    parameterization_started = perf_counter()
    parameterization_result = LiveOrderContractParameterizationService().run(
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    parameterization_latency_ms = (perf_counter() - parameterization_started) * 1000

    final_review_started = perf_counter()
    final_review_result = LiveOrderContractFinalReviewService().run(
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
        confirmation_phrase=EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    )
    final_review_latency_ms = (perf_counter() - final_review_started) * 1000

    mapping_started = perf_counter()
    mapping_result = PreMT5OrderRequestMappingService().run(
        final_review_result.final_review,
        final_review_result.validation_report,
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    mapping_latency_ms = (perf_counter() - mapping_started) * 1000

    dry_run_started = perf_counter()
    dry_run_payload_result = MT5OrderRequestDryRunPayloadValidationService().run(
        mapping_result.mapping_boundary,
        mapping_result.validation_report,
        final_review_result.final_review,
        final_review_result.validation_report,
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    dry_run_latency_ms = (perf_counter() - dry_run_started) * 1000

    request_draft_started = perf_counter()
    request_draft_result = MT5RequestDraftService().run(
        dry_run_payload_result.dry_run_validation,
        dry_run_payload_result.validation_report,
        mapping_result.mapping_boundary,
        mapping_result.validation_report,
        final_review_result.final_review,
        final_review_result.validation_report,
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    request_draft_latency_ms = (perf_counter() - request_draft_started) * 1000

    final_approval_started = perf_counter()
    final_approval_result = MT5RequestDraftFinalApprovalService().run(
        request_draft_result.request_draft,
        request_draft_result.validation_report,
        dry_run_payload_result.dry_run_validation,
        dry_run_payload_result.validation_report,
        mapping_result.mapping_boundary,
        mapping_result.validation_report,
        final_review_result.final_review,
        final_review_result.validation_report,
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
        confirmation_phrase=EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE,
    )
    final_approval_latency_ms = (perf_counter() - final_approval_started) * 1000

    builder_started = perf_counter()
    builder_result = MT5RequestDictDryRunBuilderService().run(
        final_approval_result.final_approval,
        final_approval_result.validation_report,
        request_draft_result.request_draft,
        request_draft_result.validation_report,
        dry_run_payload_result.dry_run_validation,
        dry_run_payload_result.validation_report,
        mapping_result.mapping_boundary,
        mapping_result.validation_report,
        final_review_result.final_review,
        final_review_result.validation_report,
        parameterization_result.parameterization,
        parameterization_result.validation_report,
        approval_lock_result.approval_lock,
        approval_lock_result.validation_report,
        value_proposal_result.proposal,
        value_proposal_result.validation_report,
        parameter_draft_result.draft,
        parameter_draft_result.validation_report,
        source_result.boundary,
        source_result.validation_report,
        policy_result.policy_spec,
        policy_result.validation_report,
        contract_result.skeleton,
        contract_result.validation_report,
        live_order_result.intent,
        live_order_result.validation_report,
        permission_result.decision,
        preflight_result.report,
        draft_result.draft,
        simulated_result.contract,
        simulated_receipt=simulated_result.receipt,
    )
    service_latency_ms = (perf_counter() - builder_started) * 1000

    read_started = perf_counter()
    store = MT5RequestDictDryRunBuilderJournalStore()
    latest = store.read_latest()
    summary = store.summarize()
    journal_read_latency_ms = (perf_counter() - read_started) * 1000

    boundary = builder_result.boundary
    validation = builder_result.validation_report
    journal_record = builder_result.journal_record
    journal_file_size = store.path.stat().st_size if store.path.exists() else 0
    timings = builder_result.timings_ms or {}

    print(f"mt5_request_dict_dry_run_builder_status={boundary.status}")
    print(
        "mt5_request_dict_final_validation_workflow_allowed="
        f"{str(validation.mt5_request_dict_final_validation_workflow_allowed).lower()}"
    )
    print(f"validation_valid={str(validation.valid).lower()}")
    print(f"dry_run_fields_count={validation.dry_run_fields_count}")
    print(f"created_dry_run_fields_count={validation.created_dry_run_fields_count}")
    print(f"missing_dry_run_fields_count={validation.missing_dry_run_fields_count}")
    print(f"invalid_dry_run_fields_count={validation.invalid_dry_run_fields_count}")
    print(f"real_mt5_payload_created={str(validation.real_mt5_payload_created).lower()}")
    print(f"broker_submittable_request_dict_created={str(validation.broker_submittable_request_dict_created).lower()}")
    print(f"mt5_constants_used={str(validation.mt5_constants_used).lower()}")
    print(f"broker_submission_created={str(validation.broker_submission_created).lower()}")
    print(f"raw_values_stored={str(validation.raw_values_stored).lower()}")
    print(f"executable_order_created={str(validation.executable_order_created).lower()}")
    print(f"broker_mapping_created={str(validation.broker_mapping_created).lower()}")
    print(f"order_request_mapping_allowed={str(validation.order_request_mapping_allowed).lower()}")
    print(f"order_contract_ready={str(validation.order_contract_ready).lower()}")
    print(f"live_execution_allowed={str(validation.live_execution_allowed).lower()}")
    print(f"order_send_allowed={str(validation.order_send_allowed).lower()}")
    print(f"execution_allowed={str(validation.execution_allowed).lower()}")
    print(f"executable={str(validation.executable).lower()}")
    print(f"order_sent={str(validation.order_sent).lower()}")
    print(f"hard_live_block_required={str(validation.hard_live_block_required).lower()}")
    print(f"source_refs_count={len(boundary.source_refs)}")
    print(f"boundary_payload_size={boundary.payload_size_chars}")
    print(f"report_payload_size={validation.payload_size_chars}")
    print(f"journal_record_id={journal_record.journal_record_id if journal_record else 'n/a'}")
    print(f"latest_records_count={len(latest)}")
    print(f"total_mt5_request_dict_dry_run_builder_records={summary.total_records}")
    print(
        "mt5_request_dict_dry_run_builder_build_latency_ms="
        f"{timings.get('mt5_request_dict_dry_run_builder_build_latency_ms', 0.0):.2f}"
    )
    print(
        "mt5_request_dict_dry_run_builder_report_latency_ms="
        f"{timings.get('mt5_request_dict_dry_run_builder_report_latency_ms', 0.0):.2f}"
    )
    print(
        "mt5_request_dict_dry_run_builder_journal_append_latency_ms="
        f"{timings.get('mt5_request_dict_dry_run_builder_journal_append_latency_ms', 0.0):.2f}"
    )
    print(f"mt5_request_dict_dry_run_builder_journal_read_latency_ms={journal_read_latency_ms:.2f}")
    print(f"mt5_request_dict_dry_run_builder_service_latency_ms={service_latency_ms:.2f}")
    print(f"mt5_request_draft_final_approval_service_latency_ms={final_approval_latency_ms:.2f}")
    print(f"mt5_request_draft_service_latency_ms={request_draft_latency_ms:.2f}")
    print(f"mt5_dry_run_payload_validation_service_latency_ms={dry_run_latency_ms:.2f}")
    print(f"pre_mt5_mapping_service_latency_ms={mapping_latency_ms:.2f}")
    print(f"contract_final_review_service_latency_ms={final_review_latency_ms:.2f}")
    print(f"contract_parameterization_service_latency_ms={parameterization_latency_ms:.2f}")
    print(f"live_script_total_latency_ms={(perf_counter() - started) * 1000:.2f}")
    print(f"mt5_request_dict_dry_run_builder_journal_file_size_bytes={journal_file_size}")
    if builder_result.warning:
        print(f"warning={builder_result.warning}")

    if validation.live_execution_allowed or validation.order_send_allowed or validation.execution_allowed:
        return 1
    if validation.executable or validation.real_mt5_payload_created or validation.broker_submittable_request_dict_created:
        return 1
    if validation.mt5_constants_used or validation.broker_submission_created or validation.order_sent:
        return 1
    if validation.order_contract_ready or validation.order_request_mapping_allowed or validation.broker_mapping_created:
        return 1
    if validation.raw_values_stored or validation.executable_order_created:
        return 1
    if validation.dry_run_fields_count != 12 or validation.created_dry_run_fields_count != 12:
        return 1
    if validation.invalid_dry_run_fields_count != 0 or validation.missing_dry_run_fields_count != 0:
        return 1
    if not validation.mt5_request_dict_final_validation_workflow_allowed or not validation.valid:
        return 1
    if not validation.hard_live_block_required:
        return 1
    if journal_record is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
