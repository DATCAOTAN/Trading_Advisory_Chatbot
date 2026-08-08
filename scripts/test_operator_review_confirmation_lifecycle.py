from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta

from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionJournal,
    AutonomousDecisionOrchestrator,
)
from src.services.trading.decision.candidate_review import (
    build_autonomous_candidate_review_artifact,
    present_autonomous_candidate_review,
)
from src.services.trading.decision.offline_candidate_acceptance import (
    DEFAULT_REFERENCE_TIME,
    run_offline_candidate_acceptance,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.proposal import (
    HumanProposalConfirmationService,
    ProposalBoundaryPolicy,
    ProposalIntentJournalService,
    ProposalIntentJournalStore,
)
from src.ui.autonomous_candidate_review import (
    AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY,
    OperatorCandidateReviewController,
    OperatorCandidateReviewOutcome,
)


NOW = datetime.fromisoformat(DEFAULT_REFERENCE_TIME)
PHRASE = ProposalBoundaryPolicy().confirmation_phrase


def test_authoritative_market_candidate_review_exposes_required_safe_details(tmp_path):
    state = _state(tmp_path, "fresh_market")
    candidate = state["candidate"]
    view = present_autonomous_candidate_review(candidate, state["validation"], now=NOW)

    assert view.status == "VALID"
    assert view.candidate_reference == candidate.candidate_reference
    assert view.symbol == "XAUUSD"
    assert view.broker_symbol == "XAUUSDm"
    assert view.order_type == "BUY"
    assert view.timeframe_profile == ("M15", "H1", "H4")
    assert view.market_snapshot_reference == candidate.market_snapshot_reference
    assert view.account_context_status.startswith("BOUND:")
    assert view.integrity_status == "VALID"
    assert view.non_executable is True


def test_authoritative_pending_candidate_review_preserves_limit_fields(tmp_path):
    state = _state(tmp_path, "fresh_pending")
    view = present_autonomous_candidate_review(
        state["candidate"], state["validation"], now=NOW
    )

    assert view.status == "VALID"
    assert view.order_type == "BUY_LIMIT"
    assert view.entry_price != "UNAVAILABLE"
    assert view.trigger_price == "NOT_APPLICABLE"
    assert view.limit_price == "NOT_APPLICABLE"


def test_review_artifact_binds_candidate_hashes_and_sources(tmp_path):
    state = _state(tmp_path, "fresh_market")
    candidate = state["candidate"]
    artifact = build_autonomous_candidate_review_artifact(
        candidate, state["validation"], now=NOW
    )

    assert artifact.review_status == "READY_FOR_REVIEW"
    assert {
        candidate.candidate_reference,
        candidate.provenance_hash,
        candidate.structured_order_hash,
        candidate.market_snapshot_reference,
        candidate.account_context_reference,
    }.issubset(set(artifact.source_refs))


def test_valid_explicit_market_confirmation_is_bound_and_non_executable(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)

    assert result.intent.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert result.intent.candidate_reference == state["candidate"].candidate_reference
    assert result.intent.candidate_provenance_hash == state["candidate"].provenance_hash
    assert result.intent.candidate_structured_order_hash == state["candidate"].structured_order_hash
    assert result.intent.account_fingerprint_hash != state["account"].account_context_fingerprint
    assert result.intent.confirmation_binding_hash == result.intent.artifact_hash
    assert result.intent.proposal_workflow_allowed is True
    _assert_non_executable(result.intent)


def test_valid_explicit_pending_confirmation_preserves_order_binding(tmp_path):
    state = _state(tmp_path, "fresh_pending")
    result = _confirm(state)

    assert result.intent.order_type == "BUY_LIMIT"
    assert result.intent.timeframe_profile == ["M15", "H1", "H4"]
    assert state["candidate"].structured_order_hash in result.intent.source_refs
    assert state["service"].validate_candidate_confirmation(
        result.intent,
        state["candidate_journal"],
        state["account"],
        "a" * 64,
        now=NOW,
    ).passed


def test_operator_rejection_persists_no_confirmation_artifact(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _review(state, "REJECT")

    assert result.intent.proposal_boundary_status == "REJECTED"
    assert result.intent.human_confirmation_state == "REJECTED"
    assert result.intent.artifact_hash == ""
    assert result.intent.confirmation_binding_hash == ""
    assert result.intent.proposal_workflow_allowed is False
    assert len(state["review_store"].read_latest()) == 1


def test_duplicate_confirmation_returns_existing_record_without_second_append(tmp_path):
    state = _state(tmp_path, "fresh_market")
    first = _confirm(state)
    second = _confirm(state)

    assert second.intent.proposal_boundary_status == "DUPLICATE"
    assert second.journal_record == first.journal_record
    assert second.intent.artifact_hash == first.intent.artifact_hash
    assert len(state["review_store"].read_latest()) == 1


def test_duplicate_rejection_is_idempotent(tmp_path):
    state = _state(tmp_path, "fresh_market")
    first = _review(state, "REJECT")
    second = _review(state, "REJECT")

    assert second.intent.proposal_boundary_status == "DUPLICATE"
    assert second.journal_record == first.journal_record
    assert len(state["review_store"].read_latest()) == 1


def test_conflicting_terminal_review_returns_the_existing_decision(tmp_path):
    for first_action, second_action, expected_status in (
        ("CONFIRM", "REJECT", "CONFIRMED_FOR_PROPOSAL_WORKFLOW"),
        ("REJECT", "CONFIRM", "REJECTED"),
    ):
        state = _state(tmp_path / first_action.lower(), "fresh_market")

        first = _review(state, first_action)
        second = _review(state, second_action)

        assert first.intent.proposal_boundary_status == expected_status
        assert second.intent.proposal_boundary_status == "DUPLICATE"
        assert second.journal_record.operator_action == first_action
        assert len(state["review_store"].read_latest()) == 1


def test_tampered_persisted_candidate_fails_closed_before_confirmation(tmp_path):
    state = _state(tmp_path, "fresh_market")
    path = state["candidate_journal"].path
    row = json.loads(path.read_text(encoding="utf-8"))
    row["protected_candidate"]["proposed_volume"] = "9.99"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = _confirm(state)

    assert result.intent.proposal_boundary_status == "BLOCKED"
    assert "DECISION_JOURNAL_CORRUPT" in result.intent.blockers
    assert result.journal_record is None
    assert not state["review_store"].path.exists()


def test_candidate_switching_is_rejected_before_artifact_creation(tmp_path):
    market = _state(tmp_path / "market", "fresh_market")
    pending = _state(tmp_path / "pending", "fresh_pending")

    result = pending["service"].review_candidate(
        pending["candidate_journal"],
        pending["candidate"].candidate_reference,
        pending["account"],
        "a" * 64,
        operator_action="CONFIRM",
        user_acknowledgement_text=PHRASE,
        expected_candidate_reference=market["candidate"].candidate_reference,
        now=NOW,
    )

    assert result.intent.blockers == ["CANDIDATE_REFERENCE_MISMATCH"]
    assert result.journal_record is None


def test_account_fingerprint_mismatch_fails_closed(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = state["service"].review_candidate(
        state["candidate_journal"],
        state["candidate"].candidate_reference,
        state["account"],
        "b" * 64,
        operator_action="CONFIRM",
        user_acknowledgement_text=PHRASE,
        now=NOW,
    )

    assert "ACCOUNT_CONTEXT_MISMATCH" in result.intent.blockers
    assert result.journal_record is None


def test_candidate_account_context_mismatch_fails_closed(tmp_path):
    state = _state(tmp_path, "fresh_market")
    account = replace(state["account"], account_id_hash="d" * 64)
    result = state["service"].review_candidate(
        state["candidate_journal"],
        state["candidate"].candidate_reference,
        account,
        "a" * 64,
        operator_action="CONFIRM",
        user_acknowledgement_text=PHRASE,
        now=NOW,
    )

    assert "CANDIDATE_ACCOUNT_CONTEXT_MISMATCH" in result.intent.blockers
    assert result.journal_record is None


def test_expired_candidate_creates_no_confirmation_record(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state, now=NOW + timedelta(seconds=301))

    assert "CANDIDATE_EXPIRED" in result.intent.blockers
    assert result.journal_record is None


def test_expired_confirmation_is_invalid_for_next_boundary(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)
    validation = state["service"].validate_candidate_confirmation(
        result.intent,
        state["candidate_journal"],
        state["account"],
        "a" * 64,
        now=NOW + timedelta(seconds=301),
    )

    assert validation.passed is False
    assert "CONFIRMATION_EXPIRED" in validation.issues


def test_tampered_confirmation_binding_is_invalid(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)
    tampered = replace(result.intent, candidate_structured_order_hash="0" * 64)
    validation = state["service"].validate_candidate_confirmation(
        tampered,
        state["candidate_journal"],
        state["account"],
        "a" * 64,
        now=NOW,
    )

    assert validation.passed is False
    assert "CONFIRMATION_CANDIDATE_BINDING_MISMATCH" in validation.issues


def test_tampered_confirmation_phrase_is_invalid(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)
    tampered = replace(result.intent, confirmation_phrase_received="different")
    validation = state["service"].validate_candidate_confirmation(
        tampered,
        state["candidate_journal"],
        state["account"],
        "a" * 64,
        now=NOW,
    )

    assert validation.passed is False
    assert "CONFIRMATION_PHRASE_INVALID" in validation.issues
    assert "CONFIRMATION_CANDIDATE_BINDING_MISMATCH" in validation.issues


def test_removed_confirmation_source_reference_is_invalid(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)
    tampered = replace(
        result.intent,
        source_refs=[
            item
            for item in result.intent.source_refs
            if item != state["candidate"].market_snapshot_reference
        ],
    )
    validation = state["service"].validate_candidate_confirmation(
        tampered,
        state["candidate_journal"],
        state["account"],
        "a" * 64,
        now=NOW,
    )

    assert validation.passed is False
    assert "CONFIRMATION_SOURCE_BINDING_MISMATCH" in validation.issues


def test_streamlit_controller_double_click_is_journal_idempotent(tmp_path):
    state = _state(tmp_path, "fresh_market")
    calls = {"account": 0}

    def account_provider():
        calls["account"] += 1
        return state["account"], "a" * 64

    controller = OperatorCandidateReviewController(
        state["service"], state["candidate_journal"], account_provider
    )
    session = {}
    first = controller.act(
        session, state["candidate"].candidate_reference, "CONFIRM", PHRASE, now=NOW
    )
    second = controller.act(
        session, state["candidate"].candidate_reference, "CONFIRM", PHRASE, now=NOW
    )

    assert first.status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert second.status == "DUPLICATE"
    assert len(state["review_store"].read_latest()) == 1
    assert calls["account"] == 2
    assert isinstance(
        session[AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY],
        OperatorCandidateReviewOutcome,
    )
    assert all("intent" not in key for key in session)


def test_controller_construction_and_refresh_do_not_invoke_account_or_confirmation(tmp_path):
    state = _state(tmp_path, "fresh_market")
    calls = {"account": 0}

    def account_provider():
        calls["account"] += 1
        return state["account"], "a" * 64

    controller = OperatorCandidateReviewController(
        state["service"], state["candidate_journal"], account_provider
    )
    session = {}

    assert controller is not None
    assert session == {}
    assert calls["account"] == 0
    assert not state["review_store"].path.exists()


def test_controller_reloads_authoritative_candidate_not_session_object(tmp_path):
    state = _state(tmp_path, "fresh_pending")
    session = {"editable_candidate": replace(state["candidate"], order_type="SELL")}
    controller = OperatorCandidateReviewController(
        state["service"],
        state["candidate_journal"],
        lambda: (state["account"], "a" * 64),
    )
    outcome = controller.act(
        session, state["candidate"].candidate_reference, "CONFIRM", PHRASE, now=NOW
    )
    record = state["review_store"].read_latest()[0]

    assert outcome.status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert record.order_type == "BUY_LIMIT"


def test_controller_reloads_persisted_review_state_for_the_exact_candidate(tmp_path):
    state = _state(tmp_path, "fresh_market")
    _confirm(state)
    controller = OperatorCandidateReviewController(
        state["service"],
        state["candidate_journal"],
        lambda: (state["account"], "a" * 64),
    )

    outcome = controller.current_outcome(state["candidate"].candidate_reference)

    assert outcome.status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert outcome.confirmation_state == "CONFIRMED_PROPOSAL_WORKFLOW"
    assert outcome.candidate_reference == state["candidate"].candidate_reference


def test_confirmation_journal_record_hash_survives_reload(tmp_path):
    state = _state(tmp_path, "fresh_market")
    _confirm(state)

    records = state["review_store"].read_latest()
    assert len(records) == 1
    assert len(records[0].record_hash) == 64
    assert state["review_store"].warnings == []
    serialized = state["review_store"].path.read_text(encoding="utf-8")
    assert "entry_price" not in serialized
    assert "stop_loss" not in serialized
    assert "take_profit" not in serialized


def test_corrupt_confirmation_journal_blocks_without_partial_append(tmp_path):
    state = _state(tmp_path, "fresh_market")
    state["review_store"].path.parent.mkdir(parents=True, exist_ok=True)
    state["review_store"].path.write_text('{"partial":', encoding="utf-8")

    result = _confirm(state)

    assert result.intent.proposal_boundary_status == "BLOCKED"
    assert "proposal_intent_journal_write_failed" in result.warning
    assert state["review_store"].path.read_text(encoding="utf-8") == '{"partial":'


def test_candidate_public_journal_records_remain_redacted(tmp_path):
    state = _state(tmp_path, "fresh_market")
    records = state["candidate_journal"].records()

    assert len(records) == 1
    assert "protected_candidate" not in records[0]
    assert "proposed_volume" not in json.dumps(records[0])


def test_valid_confirmation_changes_no_execution_permissions_or_artifacts(tmp_path):
    state = _state(tmp_path, "fresh_market")
    result = _confirm(state)
    payload = result.intent.as_dict()

    _assert_non_executable(result.intent)
    assert payload["dry_run_allowed"] is False
    assert payload["dry_run_executed"] is False
    assert payload["source_dry_run_receipt_id"] == ""
    assert payload["source_execution_journal_record_id"] == ""
    assert payload["confirmation_binding_hash"]


def _state(tmp_path, scenario: str):
    tmp_path.mkdir(parents=True, exist_ok=True)
    candidate_path = tmp_path / "autonomous-decisions.jsonl"
    report = run_offline_candidate_acceptance(scenario, journal_path=candidate_path)
    candidate_journal = AutonomousDecisionJournal(candidate_path)
    candidate = candidate_journal.load_candidate(report["candidate_reference"])
    assert candidate is not None
    validation = AutonomousDecisionOrchestrator(
        journal=candidate_journal
    ).validate_candidate(candidate, now=NOW)
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
    review_store = ProposalIntentJournalStore(tmp_path / "proposal-intents.jsonl")
    service = HumanProposalConfirmationService(
        policy=ProposalBoundaryPolicy(),
        journal=ProposalIntentJournalService(store=review_store),
    )
    return {
        "candidate": candidate,
        "candidate_journal": candidate_journal,
        "validation": validation,
        "account": account,
        "review_store": review_store,
        "service": service,
    }


def _review(state, action: str, *, now: datetime = NOW):
    return state["service"].review_candidate(
        state["candidate_journal"],
        state["candidate"].candidate_reference,
        state["account"],
        "a" * 64,
        operator_action=action,
        user_acknowledgement_text=PHRASE if action == "CONFIRM" else "",
        confirmation_nonce="nonce-operator-review-0001",
        expected_candidate_reference=state["candidate"].candidate_reference,
        now=now,
    )


def _confirm(state, *, now: datetime = NOW):
    return _review(state, "CONFIRM", now=now)


def _assert_non_executable(intent) -> None:
    assert intent.dry_run_only is True
    assert intent.executable is False
    for name in ("dry_run_executed",):
        assert getattr(intent, name) is False
