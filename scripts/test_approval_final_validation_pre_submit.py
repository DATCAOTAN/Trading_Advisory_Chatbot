from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from scripts.test_operator_review_confirmation_lifecycle import (
    NOW,
    _confirm,
    _review,
    _state,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionJournal,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    PRE_SUBMIT_STATE,
    ApprovalPreSubmitLifecycleService,
    TerminalCapabilityEvidence,
    terminal_capability_from_lifecycle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (
    MT5PreSubmitJournalStore,
)
from src.services.trading.proposal.intent_store import (
    ProposalIntentJournalStore,
    proposal_record_hash,
)
from src.ui.autonomous_candidate_review import (
    AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY,
    OperatorCandidatePreSubmitOutcome,
    OperatorCandidateReviewController,
)


def test_valid_market_reaches_one_non_executable_pre_submit_record(tmp_path):
    state, result = _run(tmp_path, "fresh_market")

    assert result.approval.valid
    assert result.final_validation and result.final_validation.valid
    assert result.report and result.report.status == PRE_SUBMIT_STATE
    assert result.report.pre_submit_ready is True
    assert result.journal_appended is True
    assert len(state["pre_submit_store"].read_latest()) == 1
    _assert_disabled(result)


def test_valid_pending_preserves_buy_limit_semantics(tmp_path):
    state, result = _run(tmp_path, "fresh_pending")
    intent = result.final_validation.protected_intent

    assert result.final_validation.valid
    assert intent["action"] == "PENDING"
    assert intent["order_type"] == "BUY_LIMIT"
    assert intent["entry_price"] == state["candidate"].entry_price
    assert intent["trigger_price"] == ""
    assert intent["limit_price"] == ""
    _assert_disabled(result)


def test_rejected_candidate_stops_before_final_validation(tmp_path):
    state = _prepared(tmp_path, "fresh_market", confirm=False)
    _review(state, "REJECT")
    result = _service(state).run(
        state["candidate"].candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="a" * 64,
        terminal_capability=_capability(state),
        now=NOW,
    )

    assert not result.approval.valid
    assert "PROPOSAL_CONFIRMATION_NOT_GRANTED" in result.approval.blockers
    assert result.final_validation is None
    assert not state["pre_submit_store"].path.exists()


def test_tampered_candidate_fails_before_final_artifact(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    row = json.loads(state["candidate_journal"].path.read_text(encoding="utf-8"))
    row["protected_candidate"]["stop_loss"] = "1"
    state["candidate_journal"].path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = _invoke(state)

    assert not result.approval.valid
    assert "DECISION_JOURNAL_CORRUPT" in result.approval.blockers
    assert result.journal_record is None


def test_tampered_confirmation_fails_before_final_artifact(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    row = json.loads(state["review_store"].path.read_text(encoding="utf-8"))
    row["confirmation_nonce"] = "tampered-nonce"
    state["review_store"].path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = _invoke(state)

    assert not result.approval.valid
    assert "PROPOSAL_INTENT_JOURNAL_CORRUPT" in result.approval.blockers


def test_confirmation_with_extra_source_reference_fails_exact_binding(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    record = state["review_store"].read_latest()[0]
    changed = replace(record, source_refs=[*record.source_refs, "unexpected-source"])
    changed.record_hash = proposal_record_hash(changed)
    state["review_store"].path.write_text(
        json.dumps(changed.as_dict()) + "\n", encoding="utf-8"
    )

    result = _invoke(state)

    assert not result.approval.valid
    assert "CONFIRMATION_SOURCE_BINDING_MISMATCH" in result.approval.blockers


def test_candidate_switching_is_a_precise_binding_failure(tmp_path):
    first = _prepared(tmp_path / "first", "fresh_market")
    second = _prepared(tmp_path / "second", "fresh_pending", confirm=False)
    source = first["review_store"].read_latest()[0]
    switched = replace(source, candidate_reference=second["candidate"].candidate_reference)
    switched.record_hash = proposal_record_hash(switched)
    second["review_store"].append(switched)

    result = _invoke(second)

    assert not result.approval.valid
    assert "CONFIRMATION_CANDIDATE_BINDING_MISMATCH" in result.approval.blockers


def test_wrong_account_blocks_approval_integrity(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    result = _service(state).run(
        state["candidate"].candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="b" * 64,
        terminal_capability=_capability(state),
        now=NOW,
    )

    assert not result.approval.valid
    assert "ACCOUNT_CONTEXT_MISMATCH" in result.approval.blockers


def test_candidate_and_confirmation_expiry_block(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    result = _invoke(state, now=NOW + timedelta(seconds=301))

    assert not result.approval.valid
    assert "CANDIDATE_EXPIRED" in result.approval.blockers
    assert "CONFIRMATION_EXPIRED" in result.approval.blockers


def test_permission_change_after_confirmation_blocks_final_validation(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    config = MT5LiveAdapterPreSubmitConfig(controlled_execution_enabled=True)
    result = _service(state, config=config).run(
        state["candidate"].candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="a" * 64,
        terminal_capability=_capability(state),
        now=NOW,
    )

    assert result.approval.valid
    assert not result.final_validation.valid
    assert "CURRENT_PERMISSION_STATE_MISMATCH" in result.final_validation.blockers
    assert result.journal_record is None


def test_lifecycle_conflict_blocks_final_validation(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    lifecycle = _persisted_lifecycle(state)
    result = _invoke(
        state, current_lifecycle_status=replace(lifecycle, discrepancy_count=1)
    )

    assert not result.final_validation.valid
    assert "LIFECYCLE_CONFLICT" in result.final_validation.blockers


def test_reconciliation_unknown_blocks_final_validation(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    result = _invoke(
        state,
        current_reconciliation=MT5ReconciliationReceipt(
            status="BLOCKED",
            reconciliation_reference="current-reconciliation",
            evidence_classification="RESULT_UNKNOWN",
            original_execution_state="RESULT_UNKNOWN",
            resulting_execution_state="RESULT_UNKNOWN",
            retry_decision="RETRY_PROHIBITED",
            order_reference_present=False,
            deal_reference_present=False,
            position_reference_present=False,
        ),
    )

    assert not result.final_validation.valid
    assert "RECONCILIATION_CONFLICT" in result.final_validation.blockers


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ({"trade_allowed": False}, "SYMBOL_NOT_TRADE_ENABLED"),
        ({"supported_order_types": ("SELL",)}, "ORDER_TYPE_CAPABILITY_MISMATCH"),
        ({"account_fingerprint_hash": "0" * 64}, "TERMINAL_CAPABILITY_ACCOUNT_MISMATCH"),
        ({"observed_at": (NOW - timedelta(seconds=301)).isoformat()}, "TERMINAL_CAPABILITY_STALE"),
    ],
)
def test_terminal_capability_mismatch_blocks(tmp_path, change, blocker):
    state = _prepared(tmp_path, "fresh_market")
    base = _capability(state)
    values = {
        "observed_at": base.observed_at,
        "symbol": base.symbol,
        "broker_symbol": base.broker_symbol,
        "account_fingerprint_hash": base.account_fingerprint_hash,
        "trade_allowed": base.trade_allowed,
        "supported_order_types": base.supported_order_types,
    }
    values.update(change)
    capability = TerminalCapabilityEvidence.create(**values)
    result = _invoke(state, terminal_capability=capability)

    assert not result.final_validation.valid
    assert blocker in result.final_validation.blockers


def test_invalid_symbol_metadata_blocks_final_validation(tmp_path):
    state = _prepared(tmp_path, "fresh_pending")
    original = state["candidate_journal"].load_market_snapshot(
        state["candidate"].candidate_reference
    )
    replacement_journal = AutonomousDecisionJournal(tmp_path / "metadata.jsonl")
    replacement_journal.append_idempotent(
        state["candidate"],
        market_snapshot=replace(original, tick_size=None),
        lifecycle_status=_persisted_lifecycle(state),
    )
    state["candidate_journal"] = replacement_journal
    result = _invoke(state)

    assert not result.final_validation.valid
    assert "SYMBOL_METADATA_MISSING_OR_INVALID" in result.final_validation.blockers


def test_invalid_volume_and_price_are_rechecked(tmp_path):
    state = _prepared(tmp_path, "fresh_pending")
    original = state["candidate_journal"].load_market_snapshot(
        state["candidate"].candidate_reference
    )
    replacement_journal = AutonomousDecisionJournal(tmp_path / "constraints.jsonl")
    replacement_journal.append_idempotent(
        state["candidate"],
        market_snapshot=replace(original, volume_min=1.0, volume_step=1.0),
        lifecycle_status=_persisted_lifecycle(state),
    )
    state["candidate_journal"] = replacement_journal
    result = _invoke(state)

    assert not result.final_validation.valid
    assert "PROPOSED_VOLUME_BELOW_MINIMUM" in result.final_validation.blockers
    assert "MARKET_SNAPSHOT_HASH_MISMATCH" in result.final_validation.blockers


def test_invalid_price_relationship_is_rechecked(tmp_path):
    state = _prepared(tmp_path, "fresh_pending")
    original = state["candidate_journal"].load_market_snapshot(
        state["candidate"].candidate_reference
    )
    replacement_journal = AutonomousDecisionJournal(tmp_path / "prices.jsonl")
    replacement_journal.append_idempotent(
        state["candidate"],
        market_snapshot=replace(original, bid="97", ask="98"),
        lifecycle_status=_persisted_lifecycle(state),
    )
    state["candidate_journal"] = replacement_journal

    result = _invoke(state)

    assert not result.final_validation.valid
    assert "BUY_LIMIT_PRICE_NOT_BELOW_ASK" in result.final_validation.blockers


def test_duplicate_pre_submit_is_idempotent_and_approval_is_not_reused(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    first = _invoke(state)
    second = _invoke(state)

    assert first.journal_appended is True
    assert second.journal_appended is False
    assert len(state["pre_submit_store"].read_latest()) == 1

    changed_capability = TerminalCapabilityEvidence.create(
        observed_at=(NOW + timedelta(seconds=1)).isoformat(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        account_fingerprint_hash=_fingerprint_hash(),
        trade_allowed=True,
        supported_order_types=("BUY", "SELL"),
    )
    reused = _invoke(state, terminal_capability=changed_capability)
    assert not reused.final_validation.valid
    assert "APPROVAL_ALREADY_CONSUMED" in reused.final_validation.blockers
    assert len(state["pre_submit_store"].read_latest()) == 1


def test_corrupt_pre_submit_journal_fails_closed_without_append(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    state["pre_submit_store"].path.parent.mkdir(parents=True, exist_ok=True)
    state["pre_submit_store"].path.write_text('{"partial":', encoding="utf-8")

    result = _invoke(state)

    assert not result.final_validation.valid
    assert "PRE_SUBMIT_JOURNAL_CORRUPT" in result.final_validation.blockers
    assert result.journal_record is None
    assert state["pre_submit_store"].path.read_text(encoding="utf-8") == '{"partial":'


def test_authoritative_reload_ignores_editable_session_candidate(tmp_path):
    state = _prepared(tmp_path, "fresh_pending")
    editable = replace(state["candidate"], order_type="SELL")
    session = {"candidate": editable}

    result = _invoke(state)

    assert session["candidate"].order_type == "SELL"
    assert result.final_validation.protected_intent["order_type"] == "BUY_LIMIT"


def test_pre_submit_payload_has_no_submission_or_broker_result(tmp_path):
    _, result = _run(tmp_path, "fresh_market")
    payload = result.journal_record.as_dict()

    assert payload["ticket"] is None and payload["deal"] is None
    assert "controlled-submit" not in json.dumps(payload)
    assert "order_send(" not in json.dumps(payload)
    _assert_disabled(result)


def test_controller_rerun_uses_ids_and_keeps_one_pre_submit_record(tmp_path):
    state = _prepared(tmp_path, "fresh_market")

    def evidence_provider(_candidate_reference):
        return {
            "account_context": state["account"],
            "expected_account_fingerprint": "a" * 64,
            "terminal_capability": _capability(state),
        }

    controller = OperatorCandidateReviewController(
        state["service"],
        state["candidate_journal"],
        lambda: (state["account"], "a" * 64),
        pre_submit_service=_service(state),
        pre_submit_evidence_provider=evidence_provider,
    )
    session = {"editable_candidate": replace(state["candidate"], order_type="SELL")}
    first = controller.advance_to_pre_submit(
        session, state["candidate"].candidate_reference, now=NOW
    )
    second = controller.advance_to_pre_submit(
        session, state["candidate"].candidate_reference, now=NOW
    )

    assert first.pre_submit_ready and second.pre_submit_ready
    assert len(state["pre_submit_store"].read_latest()) == 1
    assert isinstance(
        session[AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY],
        OperatorCandidatePreSubmitOutcome,
    )
    assert not hasattr(
        session[AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY],
        "protected_intent",
    )
    reloaded = controller.current_pre_submit_outcome(
        state["candidate"].candidate_reference
    )
    assert reloaded and reloaded.pre_submit_ready
    assert reloaded.journal_record_id == first.journal_record_id


def test_confirmation_does_not_advance_to_pre_submit_automatically(tmp_path):
    state = _prepared(tmp_path, "fresh_market", confirm=False)

    class UnexpectedPreSubmitService:
        def run(self, *_args, **_kwargs):
            pytest.fail("confirmation must not invoke pre-submit")

    controller = OperatorCandidateReviewController(
        state["service"],
        state["candidate_journal"],
        lambda: (state["account"], "a" * 64),
        pre_submit_service=UnexpectedPreSubmitService(),
        pre_submit_evidence_provider=lambda _reference: pytest.fail(
            "confirmation must not collect pre-submit evidence"
        ),
    )

    outcome = controller.act(
        {},
        state["candidate"].candidate_reference,
        "CONFIRM",
        state["service"].policy.confirmation_phrase,
        now=NOW,
    )

    assert outcome.status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert not state["pre_submit_store"].path.exists()


def test_runtime_evidence_failure_blocks_without_pre_submit_record(tmp_path):
    state = _prepared(tmp_path, "fresh_market")
    controller = OperatorCandidateReviewController(
        state["service"],
        state["candidate_journal"],
        lambda: (state["account"], "a" * 64),
        pre_submit_service=_service(state),
        pre_submit_evidence_provider=lambda _reference: (_ for _ in ()).throw(
            RuntimeError("DEMO_ACCOUNT_REQUIRED")
        ),
    )

    outcome = controller.advance_to_pre_submit(
        {}, state["candidate"].candidate_reference, now=NOW
    )

    assert outcome.status == "BLOCKED"
    assert outcome.blocker == "DEMO_ACCOUNT_REQUIRED"
    assert not state["pre_submit_store"].path.exists()


def test_lifecycle_capability_binds_current_candidate_and_account(tmp_path):
    state = _prepared(tmp_path, "fresh_pending")
    lifecycle = MT5RuntimeSupervisorStatus(
        supervisor_status="HEALTHY",
        last_successful_cycle=NOW.isoformat(),
        terminal_trade_allowed=True,
        account_trade_allowed=True,
    )

    capability = terminal_capability_from_lifecycle(
        state["candidate"], lifecycle, "a" * 64
    )

    assert capability.integrity_valid()
    assert capability.symbol == "XAUUSD"
    assert capability.broker_symbol == "XAUUSDm"
    assert capability.trade_allowed is True
    assert state["candidate"].order_type in capability.supported_order_types


def _run(tmp_path, scenario):
    state = _prepared(tmp_path, scenario)
    return state, _invoke(state)


def _prepared(tmp_path, scenario, *, confirm=True):
    state = _state(tmp_path, scenario)
    state["pre_submit_store"] = MT5PreSubmitJournalStore(tmp_path / "pre-submit.jsonl")
    if confirm:
        _confirm(state)
    return state


def _service(state, *, config=None):
    return ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
        config=config or MT5LiveAdapterPreSubmitConfig(),
    )


def _invoke(state, **changes):
    values = {
        "account_context": state["account"],
        "expected_account_fingerprint": "a" * 64,
        "terminal_capability": _capability(state),
        "now": NOW,
    }
    values.update(changes)
    return _service(state).run(state["candidate"].candidate_reference, **values)


def _capability(state):
    candidate = state["candidate"]
    return TerminalCapabilityEvidence.create(
        observed_at=NOW.isoformat(),
        symbol=candidate.symbol_reference,
        broker_symbol=candidate.broker_symbol_reference,
        account_fingerprint_hash=_fingerprint_hash(),
        trade_allowed=True,
        supported_order_types=(
            "BUY",
            "SELL",
            "BUY_LIMIT",
            "SELL_LIMIT",
            "BUY_STOP",
            "SELL_STOP",
            "BUY_STOP_LIMIT",
            "SELL_STOP_LIMIT",
        ),
    )


def _persisted_lifecycle(state):
    payload = state["candidate_journal"].load_runtime_evidence(
        state["candidate"].candidate_reference
    )
    return MT5RuntimeSupervisorStatus(**payload["lifecycle_status"])


def _fingerprint_hash():
    return hashlib.sha256(("a" * 64).encode("utf-8")).hexdigest()


def _assert_disabled(result):
    assert result.report.live_submission_allowed is False
    assert result.report.live_execution_allowed is False
    assert result.report.order_send_allowed is False
    assert result.report.execution_allowed is False
    assert result.report.executable is False
    assert result.report.order_sent is False
    assert result.report.kill_switch_engaged is True
