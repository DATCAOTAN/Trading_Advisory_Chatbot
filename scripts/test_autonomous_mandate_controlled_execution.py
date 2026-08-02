from __future__ import annotations

from datetime import datetime

import pytest

import tools.mt5_bridge.execution as bridge_execution
from scripts.test_approval_final_validation_pre_submit import _capability, _prepared
from scripts.test_mt5_controlled_execution_integration import (
    ACCOUNT_A,
    AUTH_TOKEN,
    FakeClient,
    FakeMT5,
    Result,
)
from scripts.test_operator_review_confirmation_lifecycle import NOW
from scripts.test_standing_trading_mandate_authority import (
    _CandidateJournalView,
    _authority,
    _authorize,
    _autonomous,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    ApprovalPreSubmitLifecycleService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    AUTONOMOUS_EXECUTION_REQUEST_VERSION,
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from tools.mt5_bridge.execution import (
    ControlledExecutionConfig,
    ControlledMT5ExecutionService,
    ProtectedExecutionJournal,
)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


class DemoClient(FakeClient):
    def execution_context(self):
        payload = super().execution_context()
        payload["account_environment"] = "DEMO"
        return payload

    def pending_order_context(self, symbol):
        return {
            "status": "OK",
            "symbol_available": True,
            "symbol_trade_allowed": True,
            "bid": "1999",
            "ask": "2000",
        }


def test_mandate_request_reloads_authority_and_submits_once_with_fake_mt5(
    tmp_path, monkeypatch
):
    request, authority_path = _request(tmp_path)
    fake_mt5 = FakeMT5()
    service = _service(tmp_path, authority_path, fake_mt5)
    monkeypatch.setattr(bridge_execution, "datetime", FrozenDateTime)

    first, first_status = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    duplicate, duplicate_status = service.handle(request.as_protected_dict(), AUTH_TOKEN)

    assert first_status == 200 and first["status"] == "ACCEPTED"
    assert first["ticket"] is None and first["deal"] is None
    assert duplicate_status == 409 and duplicate["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1


@pytest.mark.parametrize(
    ("environment", "reason"),
    [("REAL", "REAL_ACCOUNT_EXECUTION_FORBIDDEN"), ("UNKNOWN", "REAL_ACCOUNT_EXECUTION_FORBIDDEN")],
)
def test_mandate_execution_is_demo_only(tmp_path, monkeypatch, environment, reason):
    request, authority_path = _request(tmp_path)

    class Client(DemoClient):
        def execution_context(self):
            payload = super().execution_context()
            payload["account_environment"] = environment
            return payload

    fake_mt5 = FakeMT5()
    monkeypatch.setattr(bridge_execution, "datetime", FrozenDateTime)
    response, status = _service(tmp_path, authority_path, fake_mt5, Client()).handle(
        request.as_protected_dict(), AUTH_TOKEN
    )

    assert status == 403 and response["reason"] == reason
    assert fake_mt5.calls == 0


def test_revoked_mandate_blocks_before_fake_order_send(tmp_path, monkeypatch):
    request, authority_path, authority, mandate = _request(tmp_path, include_authority=True)
    authority.revoke_mandate(
        mandate.mandate_id,
        operator_grant=True,
        revocation_nonce="revoke-before-submit",
        now=NOW,
    )
    fake_mt5 = FakeMT5()
    monkeypatch.setattr(bridge_execution, "datetime", FrozenDateTime)

    response, status = _service(tmp_path, authority_path, fake_mt5).handle(
        request.as_protected_dict(), AUTH_TOKEN
    )

    assert status == 403 and response["reason"] == "MANDATE_NOT_CURRENT"
    assert fake_mt5.calls == 0


def test_mandate_is_reloaded_immediately_before_submission(tmp_path, monkeypatch):
    request, authority_path, authority, mandate = _request(tmp_path, include_authority=True)

    class RevokingClient(DemoClient):
        def execution_context(self):
            payload = super().execution_context()
            if self.calls == 2:
                authority.revoke_mandate(
                    mandate.mandate_id,
                    operator_grant=True,
                    revocation_nonce="revoke-during-submit",
                    now=NOW,
                )
            return payload

    fake_mt5 = FakeMT5()
    monkeypatch.setattr(bridge_execution, "datetime", FrozenDateTime)
    response, status = _service(
        tmp_path, authority_path, fake_mt5, RevokingClient([ACCOUNT_A, ACCOUNT_A])
    ).handle(request.as_protected_dict(), AUTH_TOKEN)

    assert status == 403 and response["reason"] == "MANDATE_NOT_CURRENT"
    assert fake_mt5.calls == 0


@pytest.mark.parametrize(
    ("result", "error", "expected_state"),
    [
        (Result(999, 0, 0, "rejected"), None, "RESULT_REJECTED"),
        (None, TimeoutError("unknown"), "RESULT_UNKNOWN"),
    ],
)
def test_mandate_result_states_are_monotonic(
    tmp_path, monkeypatch, result, error, expected_state
):
    request, authority_path = _request(tmp_path)
    fake_mt5 = FakeMT5(result=result, error=error)
    monkeypatch.setattr(bridge_execution, "datetime", FrozenDateTime)

    response, status = _service(tmp_path, authority_path, fake_mt5).handle(
        request.as_protected_dict(), AUTH_TOKEN
    )

    assert status == 200 and response["idempotency_status"] == expected_state
    assert fake_mt5.calls == 1


def _request(tmp_path, *, include_authority=False):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = _autonomous(state["candidate"])
    state["candidate_journal"] = _CandidateJournalView(
        state["candidate_journal"], candidate
    )
    authority, mandate = _authority(tmp_path / "authority")
    authorization = _authorize(authority, mandate.mandate_id, candidate)
    lifecycle = ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
        config=MT5LiveAdapterPreSubmitConfig(kill_switch_engaged=False),
        authority_service=authority,
    ).run(
        candidate.candidate_reference,
        account_context=state["account"],
        expected_account_fingerprint=ACCOUNT_A,
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
    request = MT5ControlledExecutionRequest.from_mandate_artifacts(
        candidate,
        authorization,
        lifecycle.final_validation,
        lifecycle.report,
        expected_account_context_fingerprint=ACCOUNT_A,
    )
    assert request.request_version == AUTONOMOUS_EXECUTION_REQUEST_VERSION
    values = (request, authority.store.path, authority, mandate)
    return values if include_authority else values[:2]


def _service(tmp_path, authority_path, fake_mt5, client=None):
    config = ControlledExecutionConfig(
        enabled=True,
        hard_block=False,
        kill_switch_engaged=False,
        order_send_enabled=True,
        live_execution_enabled=True,
        autonomous_execution_enabled=True,
        auth_token=AUTH_TOKEN,
        journal_path=str(tmp_path / "execution.jsonl"),
        authority_journal_path=str(authority_path),
    )
    return ControlledMT5ExecutionService(
        client or DemoClient([ACCOUNT_A]),
        config=config,
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(config.journal_path),
    )
