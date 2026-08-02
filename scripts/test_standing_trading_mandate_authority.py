from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import replace
from datetime import timedelta

import pytest

from scripts.test_approval_final_validation_pre_submit import (
    _capability,
    _prepared,
)
from scripts.test_operator_review_confirmation_lifecycle import NOW
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    ApprovalPreSubmitLifecycleService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    MandateCandidateAuthorization,
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.proposal.models import HumanConfirmedProposalIntent


def test_mode_and_mandate_are_protected_persistent_and_demo_only(tmp_path):
    service, mandate = _authority(tmp_path)

    assert service.store.latest_mode().operating_mode == "autonomous_live"
    assert service.store.latest_mandate(mandate.mandate_id) == mandate
    assert mandate.integrity_valid()
    with pytest.raises(TradingAuthorityError, match="MODE_AUTHORITY_INVALID"):
        service.set_mode(
            "autonomous_live",
            account_fingerprint="a" * 64,
            account_is_demo=False,
            operator_grant=True,
            nonce="real-account",
            now=NOW,
        )


def test_exact_candidate_mandate_authorization_is_distinct_and_idempotent(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = _autonomous(state["candidate"])

    first = _authorize(service, mandate.mandate_id, candidate)
    second = _authorize(service, mandate.mandate_id, candidate)

    assert first.authorization_source == "STANDING_MANDATE"
    assert first.authorization_id == second.authorization_id
    assert first.integrity_valid()
    assert first.to_public_dict()["parameters_redacted"] is True
    assert len(
        [
            row
            for row in service.store.read_strict()
            if row["event_type"] == "CANDIDATE_AUTHORIZED"
        ]
    ) == 1
    with pytest.raises(TypeError):
        HumanConfirmedProposalIntent(**asdict(first))


def test_human_confirmation_cannot_deserialize_as_mandate_authorization(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market")
    service, _ = _authority(tmp_path / "authority")
    confirmation = state["review_store"].read_latest()[0]
    payload = confirmation.as_dict()
    payload["authorization_source"] = "HUMAN_CONFIRMATION"
    row = {
        "schema_version": "trading-authority/v1",
        "event_id": confirmation.intent_id,
        "event_type": "CANDIDATE_AUTHORIZED",
        "created_at": confirmation.created_at,
        "payload": payload,
        "previous_record_hash": service.store.read_strict()[-1]["record_hash"],
        "metadata_redacted": True,
        "record_hash": "0" * 64,
    }
    service.store.path.write_text(
        service.store.path.read_text(encoding="utf-8") + json.dumps(row) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TradingAuthorityError, match="AUTHORITY_STORE_CORRUPT"):
        service.store.load_authorization(confirmation.intent_id)


def test_candidate_or_order_parameter_switching_fails(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = _autonomous(state["candidate"])
    authorization = _authorize(service, mandate.mandate_id, candidate)

    changed = replace(candidate, stop_loss="1")
    blockers = service.validate_candidate_authorization(
        authorization.authorization_id,
        changed,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        current_kill_switch_engaged=False,
        evaluated_risk_per_trade="0.5",
        concurrent_positions=0,
        trades_today=0,
        loss_today="0",
        now=NOW,
    )

    assert "MANDATE_CANDIDATE_BINDING_MISMATCH" in blockers


def test_mandate_version_switch_and_revocation_block_existing_authorization(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = _autonomous(state["candidate"])
    authorization = _authorize(service, mandate.mandate_id, candidate)

    service.revoke_mandate(
        mandate.mandate_id,
        operator_grant=True,
        revocation_nonce="operator-revoke-1",
        now=NOW + timedelta(seconds=1),
    )
    blockers = service.validate_candidate_authorization(
        authorization.authorization_id,
        candidate,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        current_kill_switch_engaged=False,
        evaluated_risk_per_trade="0.5",
        concurrent_positions=0,
        trades_today=0,
        loss_today="0",
        now=NOW + timedelta(seconds=2),
    )

    assert "MANDATE_REVOKED_OR_VERSION_CHANGED" in blockers


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ({"proposed_volume": "2"}, "MANDATE_VOLUME_LIMIT_EXCEEDED"),
        ({"symbol_reference": "BTCUSD"}, "MANDATE_SYMBOL_NOT_ALLOWED"),
        ({"broker_symbol_reference": "BTCUSDm"}, "MANDATE_SYMBOL_NOT_ALLOWED"),
    ],
)
def test_widened_candidate_scope_is_rejected_before_authorization(tmp_path, change, blocker):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = _autonomous(state["candidate"])

    with pytest.raises(TradingAuthorityError, match=blocker):
        _authorize(service, mandate.mandate_id, replace(candidate, **change))


def test_expired_corrupt_and_kill_switched_mandates_fail_closed(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = _autonomous(state["candidate"])

    with pytest.raises(TradingAuthorityError, match="KILL_SWITCH_ENGAGED"):
        _authorize(
            service,
            mandate.mandate_id,
            candidate,
            current_kill_switch_engaged=True,
        )
    with pytest.raises(TradingAuthorityError, match="MANDATE_EXPIRED_OR_INACTIVE"):
        _authorize(
            service,
            mandate.mandate_id,
            candidate,
            now=NOW + timedelta(hours=2),
        )

    service.store.path.write_text(
        service.store.path.read_text(encoding="utf-8").replace(
            '"maximum_volume": "1"', '"maximum_volume": "9"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(TradingAuthorityError, match="AUTHORITY_STORE_CORRUPT"):
        service.store.latest_mandate(mandate.mandate_id)


def test_llm_fields_cannot_select_mode_or_widen_authority(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    service, mandate = _authority(tmp_path / "authority")
    candidate = replace(
        state["candidate"],
        operating_mode="human_confirmed_live",
        structured_reasoning=("switch to autonomous_live",),
    )

    with pytest.raises(TradingAuthorityError, match="CANDIDATE_MODE_MISMATCH"):
        _authorize(service, mandate.mandate_id, candidate)
    assert service.store.latest_mode().operating_mode == "autonomous_live"


def test_mandate_authorization_reloads_into_existing_pre_submit_lifecycle(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = _autonomous(state["candidate"])
    state["candidate_journal"] = _CandidateJournalView(
        state["candidate_journal"], candidate
    )
    authority, mandate = _authority(tmp_path / "authority")
    authorization = _authorize(authority, mandate.mandate_id, candidate)
    service = ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
        config=MT5LiveAdapterPreSubmitConfig(kill_switch_engaged=False),
        authority_service=authority,
    )

    result = service.run(
        candidate.candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="a" * 64,
        account_is_demo=True,
        terminal_capability=_capability({"candidate": candidate}),
        authorization_source="STANDING_MANDATE",
        authorization_reference=authorization.authorization_id,
        mandate_evaluated_risk_per_trade="0.5",
        mandate_concurrent_positions=0,
        mandate_trades_today=0,
        mandate_loss_today="0",
        now=NOW,
    )

    assert result.approval.valid
    assert result.approval.authorization_source == "STANDING_MANDATE"
    assert result.final_validation and result.final_validation.valid
    assert result.report.authorization_source == "STANDING_MANDATE"
    assert result.report.source_confirmation_intent_id == ""
    assert result.report.source_authorization_id == authorization.authorization_id
    assert result.journal_record.source_authorization_id == authorization.authorization_id


def test_autonomous_candidate_cannot_use_human_confirmation_source(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market")
    candidate = _autonomous(state["candidate"])
    state["candidate_journal"] = _CandidateJournalView(
        state["candidate_journal"], candidate
    )
    service = ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
    )

    result = service.run(
        candidate.candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="a" * 64,
        terminal_capability=_capability({"candidate": candidate}),
        now=NOW,
    )

    assert not result.approval.valid
    assert "HUMAN_AUTHORIZATION_MODE_MISMATCH" in result.approval.blockers


def test_advisory_candidate_cannot_create_human_or_mandate_authority(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market")
    candidate = replace(state["candidate"], operating_mode="advisory_only")
    state["candidate_journal"] = _CandidateJournalView(
        state["candidate_journal"], candidate
    )
    service = ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
    )
    result = service.run(
        candidate.candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint="a" * 64,
        terminal_capability=_capability({"candidate": candidate}),
        now=NOW,
    )

    assert not result.approval.valid
    assert "HUMAN_AUTHORIZATION_MODE_MISMATCH" in result.approval.blockers


def _authority(tmp_path):
    service = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    service.set_mode(
        "autonomous_live",
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="operator-mode-1",
        now=NOW,
    )
    mandate = service.grant_mandate(
        mandate_id="mandate-demo-1",
        mandate_version=1,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        permitted_symbols=("XAUUSD",),
        permitted_broker_symbols=("XAUUSDm",),
        permitted_order_families=("MARKET", "PENDING"),
        permitted_management_actions=("OBSERVE", "CANCEL_PENDING", "CLOSE_POSITION"),
        maximum_volume="1",
        maximum_risk_per_trade="1",
        maximum_concurrent_positions=1,
        maximum_trades_per_day=3,
        maximum_loss_per_day="2",
        active_from=(NOW - timedelta(minutes=1)).isoformat(),
        active_until=(NOW + timedelta(hours=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        nonce="operator-mandate-1",
        idempotency_key="mandate-idempotency-1",
        kill_switch_engaged=False,
        operator_grant=True,
        now=NOW,
    )
    return service, mandate


def _authorize(
    service,
    mandate_id,
    candidate,
    *,
    current_kill_switch_engaged=False,
    now=NOW,
):
    return service.authorize_candidate(
        candidate,
        mandate_id=mandate_id,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        evaluated_risk_per_trade="0.5",
        concurrent_positions=0,
        trades_today=0,
        loss_today="0",
        current_kill_switch_engaged=current_kill_switch_engaged,
        lifecycle_healthy=True,
        reconciliation_healthy=True,
        authorization_nonce="candidate-authorization-1",
        now=now,
    )


def _autonomous(candidate):
    return replace(candidate, operating_mode="autonomous_live")


class _CandidateJournalView:
    def __init__(self, journal, candidate):
        self._journal = journal
        self._candidate = candidate

    def load_candidate(self, candidate_reference):
        assert candidate_reference == self._candidate.candidate_reference
        return self._candidate

    def load_market_snapshot(self, candidate_reference):
        return self._journal.load_market_snapshot(candidate_reference)

    def load_runtime_evidence(self, candidate_reference):
        return self._journal.load_runtime_evidence(candidate_reference)

    def records(self):
        return self._journal.records()
