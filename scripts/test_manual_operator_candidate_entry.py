from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import (
    NOW,
    lifecycle_status,
    make_inputs,
    reconciliation_unknown,
    service,
)
from scripts.test_structured_market_pending_order_candidate import structured_inputs
from src.services.trading.decision.autonomous_orchestrator import (
    MANUAL_OPERATOR_PROPOSAL_SOURCE,
    autonomous_account_context_reference,
)
from src.services.trading.decision.candidate_review import (
    present_autonomous_candidate_review,
)
from src.services.trading.decision.operator_candidate_generation import (
    AuthoritativeAutonomousInputAssembler,
    ManualOperatorProposalInput,
)
from src.ui.operator_candidate_generation import OperatorCandidateGenerationController
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    PRE_SUBMIT_STATE,
    ApprovalPreSubmitLifecycleService,
    TerminalCapabilityEvidence,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (
    MT5PreSubmitJournalStore,
)
from src.services.trading.proposal.confirmation_service import (
    HumanProposalConfirmationService,
)
from src.services.trading.proposal.intent_journal import ProposalIntentJournalService
from src.services.trading.proposal.intent_store import ProposalIntentJournalStore
from src.services.trading.proposal.policies import ProposalBoundaryPolicy


def _manual_inputs(order_type: str = "BUY"):
    inputs = structured_inputs(order_type)
    source_reference = "manual_operator_proposal_fixture"
    return replace(
        inputs,
        runtime_context=replace(
            inputs.runtime_context,
            mode="human_confirmed_live",
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
        ),
        method_selection=replace(
            inputs.method_selection,
            mode="human_confirmed_live",
            symbol="XAUUSD",
        ),
        score_report=replace(
            inputs.score_report,
            mode="human_confirmed_live",
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
        ),
        risk_result=replace(
            inputs.risk_result,
            mode="human_confirmed_live",
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
        ),
        order_market_snapshot=replace(
            inputs.order_market_snapshot,
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
            point="0.01",
            tick_size="0.01",
            digits=2,
            minimum_distance_points="0",
            volume_min="0.01",
            volume_max="10",
            volume_step="0.01",
            tick_value="1",
            contract_size="100",
        ),
        order_proposal=replace(
            inputs.order_proposal,
            symbol="XAUUSD",
            structured_reasoning=(),
        ),
        semantic_parameter_references=(
            source_reference,
            inputs.risk_result.decision_id,
            inputs.method_selection.result_id,
            inputs.runtime_context.context_pack_id,
        ),
        proposal_source=MANUAL_OPERATOR_PROPOSAL_SOURCE,
        proposal_source_reference=source_reference,
        account_context_reference=autonomous_account_context_reference("c" * 64),
        timeframe_profile=("M15", "H1", "H4"),
    )


def test_valid_manual_market_candidate_is_persisted_once(tmp_path):
    orchestrator = service(tmp_path)
    inputs = _manual_inputs("BUY")

    first = orchestrator.run_once(inputs, now=NOW, require_actionable=True)
    second = orchestrator.run_once(inputs, now=NOW, require_actionable=True)

    assert first.validation.valid
    assert first.candidate.intent == "OPEN_POSITION"
    assert first.candidate.action == "MARKET"
    assert first.candidate.proposal_source == MANUAL_OPERATOR_PROPOSAL_SOURCE
    assert first.journal_appended is True
    assert second.journal_appended is False
    assert second.journal_warning == ""
    assert len(orchestrator.journal.records()) == 1


def test_valid_manual_pending_candidate_preserves_operator_values(tmp_path):
    inputs = _manual_inputs("BUY_LIMIT")
    result = service(tmp_path).run_once(inputs, now=NOW, require_actionable=True)

    assert result.validation.valid
    assert result.candidate.action == "PENDING"
    assert result.candidate.order_type == "BUY_LIMIT"
    assert result.candidate.entry_price == inputs.order_proposal.entry_price
    assert result.candidate.stop_loss == "99"
    assert result.candidate.take_profit == "102"
    assert result.candidate.proposed_volume == "0.01"


@pytest.mark.parametrize(
    ("changed_proposal", "expected"),
    [
        ({"entry_price": "102"}, "BUY_LIMIT_PRICE_NOT_BELOW_ASK"),
        ({"proposed_volume": "0.015"}, "PROPOSED_VOLUME_STEP_MISMATCH"),
    ],
)
def test_invalid_manual_values_are_not_persisted(tmp_path, changed_proposal, expected):
    inputs = _manual_inputs("BUY_LIMIT")
    inputs = replace(
        inputs,
        order_proposal=replace(inputs.order_proposal, **changed_proposal),
    )
    orchestrator = service(tmp_path)

    result = orchestrator.run_once(inputs, now=NOW, require_actionable=True)

    assert expected in result.candidate.blocked_reason_codes
    assert result.journal_appended is False
    assert orchestrator.journal.records() == []


def test_stale_manual_market_evidence_is_not_persisted(tmp_path):
    inputs = _manual_inputs()
    inputs = replace(
        inputs,
        order_market_snapshot=replace(
            inputs.order_market_snapshot,
            observed_at="2026-07-22T00:00:00+00:00",
        ),
    )
    result = service(tmp_path).run_once(inputs, now=NOW, require_actionable=True)

    assert "MARKET_SNAPSHOT_STALE" in result.candidate.blocked_reason_codes
    assert result.journal_appended is False


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"lifecycle_status": lifecycle_status(account_match=False)}, "ACCOUNT_CONTEXT_MISMATCH"),
        ({"lifecycle_status": replace(lifecycle_status(), discrepancy_count=1)}, "LIFECYCLE_AMBIGUOUS"),
        ({"reconciliation_result": reconciliation_unknown()}, "RECONCILIATION_UNRESOLVED"),
    ],
)
def test_runtime_safety_conflicts_block_manual_admission(tmp_path, changes, expected):
    result = service(tmp_path).run_once(
        replace(_manual_inputs(), **changes),
        now=NOW,
        require_actionable=True,
    )

    assert expected in result.candidate.blocked_reason_codes
    assert result.journal_appended is False


def test_manual_review_card_shows_source_and_remains_non_executable(tmp_path):
    result = service(tmp_path).run_once(
        _manual_inputs(), now=NOW, require_actionable=True
    )
    view = present_autonomous_candidate_review(
        result.candidate, result.validation, now=NOW
    )

    assert view.proposal_source == MANUAL_OPERATOR_PROPOSAL_SOURCE
    assert view.status == "VALID"
    assert view.non_executable is True
    assert view.safety_status == "NON_EXECUTABLE"
    assert result.candidate.execution_authority is False
    assert result.candidate.execution_permission_requested is False
    assert result.candidate.order_send_allowed is False
    assert result.candidate.order_sent is False


def test_manual_provenance_survives_confirmation_and_pre_submit(tmp_path):
    orchestrator = service(tmp_path / "candidate")
    result = orchestrator.run_once(
        _manual_inputs(), now=NOW, require_actionable=True
    )
    candidate = result.candidate
    account = ProtectedAccountContextCapture(
        status="OK",
        account_context_fingerprint="a" * 64,
        account_id_hash="c" * 64,
        server_redacted="demo",
        currency="USD",
        trade_mode="DEMO",
        redacted=True,
        captured_at=NOW.isoformat(),
    )
    confirmation_store = ProposalIntentJournalStore(
        tmp_path / "proposal-intents.jsonl"
    )
    confirmation_service = HumanProposalConfirmationService(
        policy=ProposalBoundaryPolicy(),
        journal=ProposalIntentJournalService(store=confirmation_store),
    )
    confirmation = confirmation_service.review_candidate(
        orchestrator.journal,
        candidate.candidate_reference,
        account,
        "a" * 64,
        operator_action="CONFIRM",
        user_acknowledgement_text=confirmation_service.policy.confirmation_phrase,
        confirmation_nonce="manual-confirmation-nonce",
        expected_candidate_reference=candidate.candidate_reference,
        now=NOW,
    )
    capability = TerminalCapabilityEvidence.create(
        observed_at=NOW.isoformat(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        account_fingerprint_hash=hashlib.sha256(
            ("a" * 64).encode("utf-8")
        ).hexdigest(),
        trade_allowed=True,
        supported_order_types=("BUY", "BUY_LIMIT"),
    )
    pre_submit_store = MT5PreSubmitJournalStore(tmp_path / "pre-submit.jsonl")
    lifecycle = ApprovalPreSubmitLifecycleService(
        candidate_journal=orchestrator.journal,
        confirmation_store=confirmation_store,
        pre_submit_store=pre_submit_store,
    )

    pre_submit = lifecycle.run(
        candidate.candidate_reference,
        account_context=account,
        expected_account_fingerprint="a" * 64,
        terminal_capability=capability,
        now=NOW,
    )

    assert confirmation.intent.proposal_boundary_status == (
        "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    )
    assert candidate.proposal_source_reference in confirmation.intent.source_refs
    assert pre_submit.final_validation.valid
    assert pre_submit.report.status == PRE_SUBMIT_STATE
    assert pre_submit.final_validation.protected_intent["proposal_source"] == (
        MANUAL_OPERATOR_PROPOSAL_SOURCE
    )
    assert pre_submit.final_validation.protected_intent[
        "proposal_source_reference"
    ] == candidate.proposal_source_reference
    assert pre_submit.report.live_submission_allowed is False
    assert pre_submit.report.order_send_allowed is False
    assert pre_submit.report.executable is False


def test_authoritative_manual_assembly_forces_deterministic_reasoning():
    base = make_inputs()
    structured = structured_inputs("BUY")
    snapshot = structured.order_market_snapshot
    feature_result = SimpleNamespace(
        feature_snapshot=SimpleNamespace(
            feature_snapshot_id="feature-fixture",
            created_at=NOW.isoformat(),
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
            source_snapshot_ids=["snapshot-safe-ref"],
            timeframes=("M15", "H1", "H4"),
        ),
        bundle=SimpleNamespace(
            bundle_id=snapshot.snapshot_reference,
            created_at=NOW.isoformat(),
            symbol="XAUUSD",
            broker_symbol="XAUUSDm",
            provider_name="mt5_bridge",
            provider_health=SimpleNamespace(status="OK"),
            errors=[],
            account_id_hash="a" * 64,
            tick=SimpleNamespace(
                timestamp=NOW.isoformat(),
                bid=snapshot.bid,
                ask=snapshot.ask,
                point=snapshot.point,
                tick_size=snapshot.tick_size,
                digits=snapshot.digits,
                minimum_distance_points=snapshot.minimum_distance_points,
                volume_min=snapshot.volume_min,
                volume_max=snapshot.volume_max,
                volume_step=snapshot.volume_step,
                tick_value=snapshot.tick_value,
                contract_size=snapshot.contract_size,
            ),
        ),
        quality_report=SimpleNamespace(status="COMPLETE"),
    )
    method_calls = []
    proposal_calls = []

    class Component:
        def __init__(self, value):
            self.value = value

        def build_features(self, *args, **kwargs):
            return self.value

        def build(self, *args, **kwargs):
            return self.value

        def detect(self, *args, **kwargs):
            return self.value

        def route(self, *args, **kwargs):
            return self.value

        def select(self, *args, **kwargs):
            method_calls.append(kwargs)
            return self.value

        def score(self, *args, **kwargs):
            return self.value

        def decide(self, *args, **kwargs):
            return self.value

        def run_once(self):
            return self.value

        def produce(self, *args, **kwargs):
            proposal_calls.append(True)
            raise AssertionError("manual assembly must not call the proposal provider")

    assembler = AuthoritativeAutonomousInputAssembler(
        SimpleNamespace(provider=object(), calendar_provider=object()),
        feature_service=Component(feature_result),
        calendar_builder=Component(object()),
        regime_detector=Component(object()),
        knowledge_router=Component(object()),
        context_builder=Component(base.runtime_context),
        method_selector=Component(base.method_selection),
        scoring_engine=Component(base.score_report),
        decision_engine=Component(base.risk_result),
        lifecycle_supervisor=Component(base.lifecycle_status),
        proposal_provider=Component(None),
        mode="human_confirmed_live",
    )
    inputs = assembler.build(
        now=NOW,
        operator_proposal=ManualOperatorProposalInput(
            order_type="BUY",
            stop_loss="99",
            take_profit="102",
            proposed_volume="0.01",
        ),
    )

    assert method_calls == [{"mode": "human_confirmed_live", "use_llm": False}]
    assert proposal_calls == []
    assert inputs.proposal_source == MANUAL_OPERATOR_PROPOSAL_SOURCE
    assert inputs.order_proposal.structured_reasoning == ()
    equivalent = assembler.build(
        now=NOW,
        operator_proposal=ManualOperatorProposalInput(
            order_type="BUY",
            stop_loss="99.0",
            take_profit="102.00",
            proposed_volume="0.010",
        ),
    )
    assert equivalent.proposal_source_reference == inputs.proposal_source_reference


def test_controller_returns_existing_manual_candidate_for_journal_duplicate(tmp_path):
    inputs = _manual_inputs()

    class Assembler:
        def build(self, **kwargs):
            assert isinstance(kwargs["operator_proposal"], ManualOperatorProposalInput)
            return inputs

    orchestrator = service(tmp_path)

    class Orchestrator:
        def run_once(self, value, **kwargs):
            return orchestrator.run_once(value, now=NOW, **kwargs)

    controller = OperatorCandidateGenerationController(Assembler(), Orchestrator())
    state = {}
    proposal = ManualOperatorProposalInput(order_type="BUY")

    first = controller.generate(
        state, "manual-request-1", operator_proposal=proposal
    )
    duplicate = controller.generate(
        state, "manual-request-2", operator_proposal=proposal
    )

    assert first.status == "GENERATED"
    assert duplicate.status == "DUPLICATE_IGNORED"
    assert duplicate.candidate_reference == first.candidate_reference
    assert duplicate.stored is True


def test_manual_ui_has_no_automatic_confirmation_or_submission():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    block = source.split("def _render_manual_operator_candidate_form", 1)[1].split(
        "def _operator_candidate_review_controller", 1
    )[0]

    assert "Validate and Create Manual Candidate" in block
    assert "controlled-submit" not in block
    assert "order_send" not in block
    assert ".act(" not in block
    assert "advance_to_pre_submit" not in block
