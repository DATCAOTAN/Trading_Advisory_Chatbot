from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from scripts.test_autonomous_decision_orchestrator import NOW, service
from scripts.test_manual_operator_candidate_entry import _manual_inputs
from src.services.trading.decision.autonomous_orchestrator import (
    EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
)
from src.services.trading.decision.candidate_review import (
    present_autonomous_candidate_review,
)
from src.services.trading.decision.operator_candidate_generation import (
    EditableTradeDraftCandidateService,
    draft_candidate_source_reference,
)
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraft,
    EditableTradeDraftService,
    EditableTradeDraftStore,
    TradeFieldValue,
    TradeDraftMarketEvidence,
    TradeParameterPatch,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.proposal.confirmation_service import (
    HumanProposalConfirmationService,
)
from src.services.trading.proposal.intent_journal import ProposalIntentJournalService
from src.services.trading.proposal.intent_store import ProposalIntentJournalStore
from src.services.trading.proposal.policies import ProposalBoundaryPolicy


def _field(value, *, status="VALID"):
    return TradeFieldValue(value=value, status=status, source="SYSTEM_CALCULATED")


def _draft(*, revision=1, blockers=()):
    return EditableTradeDraft(
        draft_id="editable_trade_draft_fixture",
        conversation_id="conversation-fixture",
        source_request_id="request-fixture",
        revision=revision,
        created_at=NOW.isoformat(),
        strategy_id="strategy-fixture",
        strategy_version="v1",
        strategy_hash="a" * 64,
        symbol=_field(
            {
                "canonical_symbol": "XAUUSD",
                "broker_symbol": "XAUUSDm",
                "timeframes": ("M15", "H1", "H4"),
            }
        ),
        direction=_field("BUY"),
        action=_field("OPEN_POSITION"),
        entry=_field({"order_type": "MARKET", "reference_price": "101", "rules": ({"left": "RSI", "operator": "GREATER_THAN", "constants": (55,)},)}),
        stop=_field({"method": "USER_EXPLICIT", "price": "99", "atr_multiplier": ""}),
        target=_field({"method": "REWARD_RISK_RATIO", "price": "105", "reward_risk_ratio": "2"}),
        risk=_field({"fraction": "0.01", "amount": "100"}),
        sizing=_field({"method": "ACCOUNT_RISK_FRACTION", "proposed_volume": "0.01"}),
        exit_rule=TradeFieldValue(value={"rules": ()}, status="NOT_APPLICABLE", source="STRATEGY_POLICY"),
        mode=_field("human_confirmed_live"),
        confirmation_policy=_field("CONFIRM_EVERY_TRADE"),
        account_scope=_field("DEMO"),
        market_evidence_reference="market-evidence-fixture",
        market_evidence_timestamp=NOW.isoformat(),
        account_context_bound=True,
        blockers=tuple(blockers),
    )


def _strategy():
    return SimpleNamespace(
        canonical_symbol="XAUUSD",
        requested_mode="human_confirmed_live",
        identity=SimpleNamespace(
            strategy_id="strategy-fixture",
            strategy_version="v1",
            normalized_strategy_hash="a" * 64,
        ),
    )


def _evidence():
    return TradeDraftMarketEvidence(
        reference="market-evidence-fixture",
        observed_at=NOW.isoformat(),
        canonical_symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        bid=Decimal("100"),
        ask=Decimal("101"),
        atr=Decimal("1"),
        swing_high=Decimal("105"),
        swing_low=Decimal("99"),
        point=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1"),
        minimum_distance_points=Decimal("0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("10"),
        volume_step=Decimal("0.01"),
        contract_size=Decimal("100"),
        account_equity=Decimal("10000"),
        free_margin=Decimal("10000"),
        account_reference="account-reference-fixture",
        account_environment="DEMO",
        freshness="COMPLETE",
    )


class _Assembler:
    def __init__(self):
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        proposal = kwargs["operator_proposal"]
        strategy = kwargs["strategy"]
        base = _manual_inputs(proposal.order_type)
        return replace(
            base,
            order_proposal=replace(
                base.order_proposal,
                entry_price=proposal.entry_price,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                proposed_volume=proposal.proposed_volume,
            ),
            semantic_parameter_references=(
                proposal.proposal_source_reference,
                base.risk_result.decision_id,
                base.method_selection.result_id,
                base.runtime_context.context_pack_id,
            ),
            proposal_source=proposal.proposal_source,
            proposal_source_reference=proposal.proposal_source_reference,
            strategy_id=strategy.identity.strategy_id,
            strategy_version=strategy.identity.strategy_version,
            normalized_strategy_hash=strategy.identity.normalized_strategy_hash,
        )


def _candidate_service(tmp_path, draft):
    store = EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    store.append(draft)
    assembler = _Assembler()
    return (
        EditableTradeDraftCandidateService(store, assembler, service(tmp_path / "candidate")),
        store,
        assembler,
    )


def _create(candidate_service, draft, *, revision=None, mode="human_confirmed_live"):
    return candidate_service.create(
        draft.draft_id,
        draft.revision if revision is None else revision,
        strategy=_strategy(),
        authoritative_mode=mode,
        account_environment="DEMO",
        mode_integrity_valid=True,
        now=NOW,
    )


def test_eligible_draft_explicitly_creates_one_non_executable_candidate(tmp_path):
    draft = _draft()
    candidate_service, _store, assembler = _candidate_service(tmp_path, draft)

    result = _create(candidate_service, draft)

    assert result.status == "CANDIDATE_CREATED"
    assert len(assembler.calls) == 1
    candidate = result.run_result.candidate
    assert candidate.proposal_source == EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE
    assert candidate.proposal_source_reference == draft_candidate_source_reference(draft)
    assert candidate.order_type == "BUY"
    assert (candidate.stop_loss, candidate.take_profit, candidate.proposed_volume) == ("99", "105", "0.01")
    assert (candidate.strategy_id, candidate.strategy_version, candidate.normalized_strategy_hash) == (
        draft.strategy_id,
        draft.strategy_version,
        draft.strategy_hash,
    )
    assert all(
        value is False
        for value in (
            candidate.execution_authority,
            candidate.human_confirmation_present,
            candidate.execution_permission_requested,
            candidate.live_submission_allowed,
            candidate.live_execution_allowed,
            candidate.order_send_allowed,
            candidate.execution_allowed,
            candidate.executable,
            candidate.order_sent,
        )
    )
    view = present_autonomous_candidate_review(candidate, result.run_result.validation, now=NOW)
    assert view.status == "VALID"
    assert view.non_executable is True


def test_rendering_or_loading_a_draft_has_no_candidate_side_effect(tmp_path):
    draft = _draft()
    candidate_service, _store, assembler = _candidate_service(tmp_path, draft)

    assert candidate_service.decision_orchestrator.journal.records() == []
    assert assembler.calls == []


def test_blocked_draft_stops_before_candidate_assembly(tmp_path):
    draft = _draft(blockers=("MARKET_DATA_STALE",))
    candidate_service, _store, assembler = _candidate_service(tmp_path, draft)

    result = _create(candidate_service, draft)

    assert result.status == "DRAFT_NOT_ELIGIBLE"
    assert result.blocker == "MARKET_DATA_STALE"
    assert assembler.calls == []
    assert candidate_service.decision_orchestrator.journal.records() == []


def test_duplicate_action_reuses_existing_candidate_journal_record(tmp_path):
    draft = _draft()
    candidate_service, _store, _assembler = _candidate_service(tmp_path, draft)

    first = _create(candidate_service, draft)
    second = _create(candidate_service, draft)

    assert first.status == "CANDIDATE_CREATED"
    assert second.status == "CANDIDATE_ALREADY_EXISTS"
    assert second.run_result.candidate.candidate_reference == first.run_result.candidate.candidate_reference
    assert len(candidate_service.decision_orchestrator.journal.records()) == 1


def test_stale_revision_never_assembles_or_creates_against_latest_draft(tmp_path):
    draft = _draft()
    candidate_service, store, assembler = _candidate_service(tmp_path, draft)
    store.append(replace(draft, revision=2, candidate_reference="", confirmation_reference=""))

    result = _create(candidate_service, draft, revision=1)

    assert result.status == "DRAFT_REVISION_STALE"
    assert assembler.calls == []
    assert candidate_service.decision_orchestrator.journal.records() == []


def test_revision_change_creates_a_distinct_historical_candidate_only_after_new_action(tmp_path):
    draft = _draft()
    candidate_service, store, _assembler = _candidate_service(tmp_path, draft)
    first = _create(candidate_service, draft)
    revised = EditableTradeDraftService(store=store).apply_patch(
        draft.draft_id,
        TradeParameterPatch(draft.revision, risk_fraction=Decimal("0.015")),
        evidence=_evidence(),
    )

    second = _create(candidate_service, revised)

    assert first.status == "CANDIDATE_CREATED"
    assert second.status == "CANDIDATE_CREATED"
    assert first.run_result.candidate.candidate_reference != second.run_result.candidate.candidate_reference
    assert first.run_result.candidate.proposal_source_reference != second.run_result.candidate.proposal_source_reference
    assert store.load(draft.draft_id).candidate_reference == ""
    assert len(candidate_service.decision_orchestrator.journal.records()) == 2


def test_historical_candidate_confirmation_remains_bound_after_draft_revision_changes(tmp_path):
    draft = _draft()
    candidate_service, store, _assembler = _candidate_service(tmp_path, draft)
    created = _create(candidate_service, draft)
    revised = EditableTradeDraftService(store=store).apply_patch(
        draft.draft_id,
        TradeParameterPatch(draft.revision, risk_fraction=Decimal("0.015")),
        evidence=_evidence(),
    )
    confirmation_store = ProposalIntentJournalStore(tmp_path / "proposal-intents.jsonl")
    confirmation_service = HumanProposalConfirmationService(
        journal=ProposalIntentJournalService(store=confirmation_store)
    )
    account = ProtectedAccountContextCapture(
        status="OK",
        account_context_fingerprint="a" * 64,
        account_id_hash="c" * 64,
        server_redacted="offline-demo",
        currency="USD",
        trade_mode="DEMO",
        redacted=True,
        captured_at=NOW.isoformat(),
    )

    result = confirmation_service.review_candidate(
        candidate_service.decision_orchestrator.journal,
        created.run_result.candidate.candidate_reference,
        account,
        account.account_context_fingerprint,
        operator_action="CONFIRM",
        user_acknowledgement_text=ProposalBoundaryPolicy().confirmation_phrase,
        confirmation_nonce="draft-history-confirmation-0001",
        expected_candidate_reference=created.run_result.candidate.candidate_reference,
        now=NOW,
    )

    assert result.intent.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert result.intent.candidate_reference == created.run_result.candidate.candidate_reference
    assert result.intent.candidate_provenance_hash == created.run_result.candidate.provenance_hash
    assert created.run_result.candidate.proposal_source_reference != draft_candidate_source_reference(revised)
    assert created.run_result.candidate.proposal_source_reference in result.intent.source_refs
    assert confirmation_store.read_latest()[0].candidate_reference == created.run_result.candidate.candidate_reference


def test_authoritative_mode_and_typed_strategy_bindings_are_required(tmp_path):
    draft = _draft()
    candidate_service, _store, assembler = _candidate_service(tmp_path, draft)

    mode_result = _create(candidate_service, draft, mode="autonomous_live")
    wrong_strategy = SimpleNamespace(
        canonical_symbol="XAUUSD",
        requested_mode="human_confirmed_live",
        identity=SimpleNamespace(
            strategy_id="wrong",
            strategy_version="v1",
            normalized_strategy_hash="a" * 64,
        ),
    )
    strategy_result = candidate_service.create(
        draft.draft_id,
        draft.revision,
        strategy=wrong_strategy,
        authoritative_mode="human_confirmed_live",
        account_environment="DEMO",
        mode_integrity_valid=True,
        now=NOW,
    )

    assert (mode_result.status, mode_result.blocker) == (
        "DRAFT_NOT_ELIGIBLE",
        "DRAFT_MODE_AUTHORITY_MISMATCH",
    )
    assert (strategy_result.status, strategy_result.blocker) == (
        "DRAFT_NOT_ELIGIBLE",
        "DRAFT_STRATEGY_BINDING_INVALID",
    )
    assert assembler.calls == []


def test_draft_candidate_path_has_no_raw_reparse_or_execution_side_effects():
    source = inspect.getsource(EditableTradeDraftCandidateService)

    for forbidden in (
        "resolve_conversational_context",
        "normalize_trade_instruction",
        "parse_conversational_trading_request",
        "parse_conversational_strategy",
        "parse_indicator_specs",
        "controlled-submit",
        "order_send",
    ):
        assert forbidden not in source
