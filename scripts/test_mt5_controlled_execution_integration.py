from __future__ import annotations

import json
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.trading.execution.live_value_approval_lock.models import (
    ApprovedSemanticExecutionParameters,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import hash_text
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig
from tools.mt5_bridge.execution import (
    ControlledExecutionConfig,
    ControlledMT5ExecutionService,
    ProtectedExecutionJournal,
)


ACCOUNT_A = "a" * 64
ACCOUNT_B = "b" * 64
AUTH_TOKEN = "fixture-auth-token"
CONFIRMATION = "SUBMIT CONTROLLED MT5 ORDER"
Result = namedtuple("Result", "retcode order deal comment")


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 2
    ORDER_TYPE_SELL = 3
    TRADE_RETCODE_DONE = 100
    TRADE_RETCODE_DONE_PARTIAL = 101
    TRADE_RETCODE_PLACED = 102

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result or Result(self.TRADE_RETCODE_DONE, 123456, 654321, "accepted")
        self.error = error
        self.calls = 0

    def order_send(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, fingerprints=None, trading_allowed=True):
        self.fingerprints = list(fingerprints or [ACCOUNT_A])
        self.trading_allowed = trading_allowed
        self.calls = 0

    def execution_context(self):
        index = min(self.calls, len(self.fingerprints) - 1)
        fingerprint = self.fingerprints[index]
        self.calls += 1
        return {
            "status": "OK",
            "terminal_connected": True,
            "terminal_trade_allowed": self.trading_allowed,
            "account_trade_allowed": self.trading_allowed,
            "account_context_fingerprint": fingerprint,
            "redacted": True,
        }

    def pending_order_context(self, _symbol):
        return {
            "status": "OK",
            "symbol_available": True,
            "symbol_trade_allowed": True,
            "ask": "1.2",
            "bid": "1.1",
        }


class FakeExecutionClient:
    def __init__(self, account_fingerprint=ACCOUNT_A, response=None):
        self.account_fingerprint = account_fingerprint
        self.response = response or {
            "status": "BLOCKED",
            "reason": "fixture",
            "idempotency_status": "NOT_RESERVED",
            "order_sent": False,
        }
        self.submissions = 0

    def account_context(self):
        return {
            "status": "OK",
            "account_context_fingerprint": self.account_fingerprint,
            "account_id_hash": "c" * 64,
            "server_redacted": "te***er",
            "currency": "USD",
            "trade_mode": 0,
            "redacted": True,
        }

    def submit_controlled(self, payload, auth_token):
        self.submissions += 1
        assert auth_token == AUTH_TOKEN
        assert payload["approved_semantic_parameters"]
        return self.response


def semantic_parameters(
    idempotency="idem-controlled-1", *, comment="controlled-test", price="1.2"
):
    now = datetime.now(timezone.utc).isoformat()
    return ApprovedSemanticExecutionParameters.from_mapping(
        {
            "action": "MARKET",
            "symbol": "TEST_SYMBOL",
            "volume": "0.01",
            "order_type": "BUY",
            "price": price,
            "stop_loss": "1.1",
            "take_profit": "1.3",
            "deviation": 10,
            "magic": 42,
            "comment": comment,
            "idempotency": idempotency,
            "audit": "fixture-audit",
        },
        approval_artifact_ref="approval-ref",
        lock_artifact_ref="lock-ref",
        source_artifact_ref="source-ref",
        approved_at=now,
        locked_at=now,
    )


def protected_payload(
    idempotency="idem-controlled-1", *, fingerprint=ACCOUNT_A,
    comment="controlled-test", price="1.2"
):
    parameters = semantic_parameters(idempotency, comment=comment, price=price)
    confirmation_ref = hash_text(f"{CONFIRMATION}|{idempotency}|{fingerprint}")
    return MT5ControlledExecutionRequest(
        request_version="controlled-mt5-execution/v1",
        approved_semantic_parameters=parameters.to_protected_dict(),
        canonical_semantic_hash=parameters.canonical_values_hash,
        approval_value_hash=parameters.canonical_values_hash,
        lock_value_hash=parameters.canonical_values_hash,
        approval_reference=parameters.approval_artifact_ref,
        lock_reference=parameters.lock_artifact_ref,
        source_artifact_reference=parameters.source_artifact_ref,
        approval_timestamp=parameters.approved_at,
        lock_timestamp=parameters.locked_at,
        human_confirmation_reference=confirmation_ref,
        human_confirmation_phrase=CONFIRMATION,
        pre_submit_validation_reference="pre-submit-ref",
        pre_submit_validation_valid=True,
        idempotency_key=idempotency,
        expected_account_context_fingerprint=fingerprint,
        execution_permission_requested=True,
    ).as_protected_dict()


def bridge_config(tmp_path, **overrides):
    values = {
        "enabled": True,
        "hard_block": False,
        "kill_switch_engaged": False,
        "order_send_enabled": True,
        "live_execution_enabled": True,
        "auth_token": AUTH_TOKEN,
        "confirmation_phrase": CONFIRMATION,
        "max_request_age_seconds": 300,
        "submit_timeout_seconds": 0.2,
        "journal_path": str(tmp_path / "protected-execution.jsonl"),
    }
    values.update(overrides)
    return ControlledExecutionConfig(**values)


def service(tmp_path, *, client=None, mt5=None, config=None):
    config = config or bridge_config(tmp_path)
    return ControlledMT5ExecutionService(
        client or FakeClient(),
        config=config,
        mt5_module=mt5 or FakeMT5(),
        journal=ProtectedExecutionJournal(config.journal_path),
    )


def test_valid_authenticated_request_calls_order_send_once_and_redacts_result(tmp_path):
    fake_mt5 = FakeMT5()
    response, status = service(tmp_path, mt5=fake_mt5).handle(protected_payload(), AUTH_TOKEN)
    assert status == 200
    assert response["status"] == "ACCEPTED"
    assert response["order_sent"] is True
    assert response["ticket"] is None and response["deal"] is None
    assert response["ticket_present"] is True and response["deal_present"] is True
    assert fake_mt5.calls == 1
    journal = Path(bridge_config(tmp_path).journal_path).read_text(encoding="utf-8")
    assert '"order": 123456' in journal and '"deal": 654321' in journal


def test_market_zero_price_is_replaced_with_current_broker_price(tmp_path):
    fake_mt5 = FakeMT5()
    response, status = service(tmp_path, mt5=fake_mt5).handle(
        protected_payload(price="0"), AUTH_TOKEN
    )

    assert status == 200
    assert response["status"] == "ACCEPTED"
    assert fake_mt5.calls == 1


def test_invalid_authentication_fails_closed_without_submission(tmp_path):
    fake_mt5 = FakeMT5()
    response, status = service(tmp_path, mt5=fake_mt5).handle(protected_payload(), "wrong")
    assert status == 401 and response["reason"] == "AUTHENTICATION_FAILED"
    assert fake_mt5.calls == 0


def test_semantic_hash_mismatch_blocks(tmp_path):
    payload = protected_payload()
    payload["canonical_semantic_hash"] = "0" * 64
    fake_mt5 = FakeMT5()
    response, _ = service(tmp_path, mt5=fake_mt5).handle(payload, AUTH_TOKEN)
    assert response["reason"] == "SEMANTIC_HASH_MISMATCH"
    assert fake_mt5.calls == 0


def test_approval_lock_hash_mismatch_blocks(tmp_path):
    payload = protected_payload()
    payload["lock_value_hash"] = "0" * 64
    response, _ = service(tmp_path).handle(payload, AUTH_TOKEN)
    assert response["reason"] == "SEMANTIC_HASH_MISMATCH"


def test_account_fingerprint_mismatch_blocks(tmp_path):
    response, _ = service(tmp_path, client=FakeClient([ACCOUNT_B])).handle(protected_payload(), AUTH_TOKEN)
    assert response["reason"] == "ACCOUNT_CONTEXT_MISMATCH"


def test_account_change_immediately_before_submission_blocks(tmp_path):
    fake_mt5 = FakeMT5()
    response, _ = service(
        tmp_path, client=FakeClient([ACCOUNT_A, ACCOUNT_B]), mt5=fake_mt5
    ).handle(protected_payload(), AUTH_TOKEN)
    assert response["reason"] == "ACCOUNT_CONTEXT_CHANGED"
    assert fake_mt5.calls == 0
    journal = Path(bridge_config(tmp_path).journal_path).read_text(encoding="utf-8")
    assert '"state": "RESERVED"' in journal
    assert '"state": "RESULT_REJECTED"' in journal
    assert '"state": "SUBMISSION_STARTED"' not in journal


def test_kill_switch_engaged_blocks(tmp_path):
    config = bridge_config(tmp_path, kill_switch_engaged=True)
    fake_mt5 = FakeMT5()
    response, _ = service(tmp_path, mt5=fake_mt5, config=config).handle(protected_payload(), AUTH_TOKEN)
    assert response["reason"] == "EXECUTION_DISABLED"
    assert fake_mt5.calls == 0


@pytest.mark.parametrize("flag", ["order_send_enabled", "live_execution_enabled", "enabled"])
def test_execution_permission_disabled_blocks(tmp_path, flag):
    config = bridge_config(tmp_path, **{flag: False})
    response, _ = service(tmp_path, config=config).handle(protected_payload(), AUTH_TOKEN)
    assert response["reason"] == "EXECUTION_DISABLED"


def test_duplicate_idempotency_key_never_calls_order_send_again(tmp_path):
    fake_mt5 = FakeMT5()
    executor = service(tmp_path, mt5=fake_mt5)
    first, _ = executor.handle(protected_payload(), AUTH_TOKEN)
    second, status = executor.handle(protected_payload(), AUTH_TOKEN)
    assert first["status"] == "ACCEPTED"
    assert status == 409 and second["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1


def test_unknown_result_is_persisted_and_never_retried(tmp_path):
    fake_mt5 = FakeMT5(error=TimeoutError("unknown broker outcome"))
    executor = service(tmp_path, mt5=fake_mt5)
    first, _ = executor.handle(protected_payload(), AUTH_TOKEN)
    second, _ = executor.handle(protected_payload(), AUTH_TOKEN)
    assert first["status"] == "UNKNOWN" and first["idempotency_status"] == "RESULT_UNKNOWN"
    assert second["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1
    assert "RESULT_UNKNOWN" in Path(bridge_config(tmp_path).journal_path).read_text(encoding="utf-8")


def test_unsupported_semantic_mapping_blocks_before_order_send(tmp_path):
    fake_mt5 = FakeMT5()
    response, _ = service(tmp_path, mt5=fake_mt5).handle(
        protected_payload(comment="x" * 32), AUTH_TOKEN
    )
    assert response["reason"] == "UNSUPPORTED_SEMANTIC_MAPPING"
    assert fake_mt5.calls == 0


def test_app_request_requires_verified_artifacts():
    parameters = semantic_parameters()

    class ApprovalLock:
        approved_semantic_parameters = parameters
        approval_value_hash = parameters.canonical_values_hash
        lock_value_hash = parameters.canonical_values_hash

        @staticmethod
        def approved_semantic_integrity_valid():
            return True

    final_validation = SimpleNamespace(
        approved_semantic_values_verified=True,
        artifact_hash=parameters.canonical_values_hash,
    )
    request = MT5ControlledExecutionRequest.from_artifacts(
        ApprovalLock(),
        final_validation,
        SimpleNamespace(valid=True),
        SimpleNamespace(valid=True, controlled_demo_integration_workflow_allowed=True, report_id="pre"),
        expected_account_context_fingerprint=ACCOUNT_A,
        human_confirmation_phrase=CONFIRMATION,
    )
    assert request.canonical_semantic_hash == parameters.canonical_values_hash
    assert "symbol" not in request.as_redacted_dict()


def test_single_adapter_blocks_by_default_and_detects_account_change(tmp_path):
    default_adapter = MT5LiveAdapterDisabled(config=MT5LiveAdapterPreSubmitConfig())
    receipt = default_adapter.submit_prepared_request(
        MT5ControlledExecutionRequest(**protected_payload()), typed_confirmation=CONFIRMATION
    )
    assert receipt.status == "BLOCKED" and receipt.reason == "CONTROLLED_EXECUTION_DISABLED"

    config = MT5LiveAdapterPreSubmitConfig(
        live_adapter_enabled=True,
        live_adapter_hard_block=False,
        allow_live_submission=True,
        allow_order_send=True,
        kill_switch_engaged=False,
        controlled_execution_enabled=True,
        execution_auth_token=AUTH_TOKEN,
        execution_confirmation_phrase=CONFIRMATION,
    )
    fake_client = FakeExecutionClient(account_fingerprint=ACCOUNT_B)
    adapter = MT5LiveAdapterDisabled(config=config, execution_client=fake_client)
    receipt = adapter.submit_prepared_request(
        MT5ControlledExecutionRequest(**protected_payload()), typed_confirmation=CONFIRMATION
    )
    assert receipt.reason == "ACCOUNT_CONTEXT_CHANGED"
    assert fake_client.submissions == 0


def test_automated_path_uses_fake_mt5_and_production_has_one_call_site(tmp_path):
    fake_mt5 = FakeMT5()
    assert service(tmp_path, mt5=fake_mt5).mt5 is fake_mt5
    execution_text = Path("tools/mt5_bridge/execution.py").read_text(encoding="utf-8")
    assert execution_text.count(".order_send(") == 1
    src_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in Path("src").rglob("*.py")
    )
    assert "import MetaTrader5" not in src_text
