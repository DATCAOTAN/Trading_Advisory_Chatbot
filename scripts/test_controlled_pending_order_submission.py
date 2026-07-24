from __future__ import annotations

from collections import namedtuple
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW
from scripts.test_controlled_pending_order_dry_run import (
    FINGERPRINT,
    build_result,
)
from scripts.test_mt5_controlled_execution_integration import (
    AUTH_TOKEN,
    CONFIRMATION,
    FakeExecutionClient,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    SUPPORTED_PENDING_ORDER_TYPES,
    _build_draft,
    _canonical_json,
    _contract_material,
    _sha256,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from tools.mt5_bridge.execution import (
    ControlledExecutionConfig,
    ControlledMT5ExecutionService,
    ProtectedExecutionJournal,
)
from tools.mt5_bridge.reconciliation import (
    ProtectedReconciliationRequest,
    _match_evidence,
)


Result = namedtuple("Result", "retcode order deal comment")


class FakePendingMT5:
    TRADE_ACTION_PENDING = 5
    ORDER_TYPE_BUY_LIMIT = 10
    ORDER_TYPE_SELL_LIMIT = 11
    ORDER_TYPE_BUY_STOP = 12
    ORDER_TYPE_SELL_STOP = 13
    ORDER_TYPE_BUY_STOP_LIMIT = 14
    ORDER_TYPE_SELL_STOP_LIMIT = 15
    ORDER_TIME_GTC = 20
    ORDER_FILLING_RETURN = 21
    SYMBOL_EXPIRATION_GTC = 1
    TRADE_RETCODE_DONE = 100
    TRADE_RETCODE_DONE_PARTIAL = 101
    TRADE_RETCODE_PLACED = 102

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result or Result(self.TRADE_RETCODE_PLACED, 123456, 0, "placed")
        self.error = error
        self.calls = 0
        self.requests: list[dict] = []

    def order_send(self, request):
        self.calls += 1
        self.requests.append(dict(request))
        if self.error:
            raise self.error
        return self.result


class FakePendingClient:
    def __init__(
        self,
        *,
        fingerprint=FINGERPRINT,
        bid="100",
        ask="101",
        tick_size="0.1",
        trade_stops_level="2",
        volume_min="0.01",
        volume_max="10",
        volume_step="0.01",
        supported=None,
    ):
        self.fingerprint = fingerprint
        self.bid = bid
        self.ask = ask
        self.tick_size = tick_size
        self.trade_stops_level = trade_stops_level
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step
        self.supported = list(supported or SUPPORTED_PENDING_ORDER_TYPES)

    def execution_context(self):
        return {
            "status": "OK",
            "terminal_connected": True,
            "terminal_trade_allowed": True,
            "account_trade_allowed": True,
            "account_context_fingerprint": self.fingerprint,
            "redacted": True,
        }

    def pending_order_context(self, symbol):
        return {
            "status": "OK",
            "symbol": symbol,
            "symbol_available": True,
            "symbol_trade_allowed": True,
            "bid": self.bid,
            "ask": self.ask,
            "digits": 1,
            "point": "0.1",
            "tick_size": self.tick_size,
            "trade_stops_level": self.trade_stops_level,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "expiration_mode": FakePendingMT5.SYMBOL_EXPIRATION_GTC,
            "supported_pending_order_types": self.supported,
            "metadata_redacted": True,
        }


def pending_artifacts(tmp_path, order_type="BUY_LIMIT"):
    base, _, _, _ = build_result(tmp_path, order_type)
    assert base.validation.valid and base.request_draft is not None
    current = datetime.now(timezone.utc)
    contract = resign_contract(
        base.contract,
        generated_at=current.isoformat(),
        expires_at=(current + timedelta(minutes=5)).isoformat(),
        expiration_policy="GTC",
        deviation=10,
        magic=42,
        comment="pending-test",
        audit="pending-submission-fixture",
    )
    return replace(base, contract=contract, request_draft=_build_draft(contract))


def resign_contract(contract, **changes):
    provisional = replace(
        contract,
        **changes,
        contract_reference="",
        canonical_integrity_hash="",
        idempotency_key="",
    )
    digest = _sha256(_canonical_json(_contract_material(provisional)))
    return replace(
        provisional,
        contract_reference="controlled_pending_" + digest[:24],
        canonical_integrity_hash=digest,
        idempotency_key=_sha256("controlled-pending-dry-run/v1|" + digest),
    )


def pending_request(tmp_path, order_type="BUY_LIMIT", *, contract=None, permission=True):
    result = pending_artifacts(tmp_path, order_type)
    selected = contract or result.contract
    draft = _build_draft(selected)
    return MT5ControlledExecutionRequest.from_pending_artifacts(
        selected,
        result.validation,
        draft,
        SimpleNamespace(
            valid=True,
            controlled_demo_integration_workflow_allowed=True,
            report_id="pre-submit-pending-fixture",
        ),
        expected_account_context_fingerprint=FINGERPRINT,
        human_confirmation_phrase=CONFIRMATION,
        execution_permission_requested=permission,
        now=datetime.now(timezone.utc),
    )


def bridge_config(tmp_path, **overrides):
    values = {
        "enabled": True,
        "hard_block": False,
        "kill_switch_engaged": False,
        "order_send_enabled": True,
        "live_execution_enabled": True,
        "pending_submission_enabled": True,
        "pending_submission_hard_block": False,
        "pending_limit_enabled": True,
        "pending_stop_enabled": True,
        "pending_stop_limit_enabled": True,
        "auth_token": AUTH_TOKEN,
        "confirmation_phrase": CONFIRMATION,
        "max_request_age_seconds": 300,
        "submit_timeout_seconds": 0.2,
        "journal_path": str(tmp_path / "pending-execution.jsonl"),
    }
    values.update(overrides)
    return ControlledExecutionConfig(**values)


def bridge_service(tmp_path, *, client=None, mt5=None, config=None):
    selected = config or bridge_config(tmp_path)
    return ControlledMT5ExecutionService(
        client or FakePendingClient(),
        config=selected,
        mt5_module=mt5 or FakePendingMT5(),
        journal=ProtectedExecutionJournal(selected.journal_path),
    )


@pytest.mark.parametrize(
    ("order_type", "expected_constant"),
    [
        ("BUY_LIMIT", FakePendingMT5.ORDER_TYPE_BUY_LIMIT),
        ("SELL_LIMIT", FakePendingMT5.ORDER_TYPE_SELL_LIMIT),
        ("BUY_STOP", FakePendingMT5.ORDER_TYPE_BUY_STOP),
        ("SELL_STOP", FakePendingMT5.ORDER_TYPE_SELL_STOP),
    ],
)
def test_regular_pending_types_use_existing_call_once(tmp_path, order_type, expected_constant):
    fake = FakePendingMT5()
    response, status = bridge_service(tmp_path, mt5=fake).handle(
        pending_request(tmp_path, order_type).as_protected_dict(), AUTH_TOKEN
    )
    assert status == 200 and response["status"] == "ACCEPTED"
    assert fake.calls == 1
    assert fake.requests[0]["action"] == fake.TRADE_ACTION_PENDING
    assert fake.requests[0]["type"] == expected_constant
    expected_price = pending_artifacts(tmp_path, order_type).contract.entry_price
    assert fake.requests[0]["price"] == float(expected_price)
    assert "stoplimit" not in fake.requests[0]


@pytest.mark.parametrize(
    ("order_type", "expected_constant"),
    [
        ("BUY_STOP_LIMIT", FakePendingMT5.ORDER_TYPE_BUY_STOP_LIMIT),
        ("SELL_STOP_LIMIT", FakePendingMT5.ORDER_TYPE_SELL_STOP_LIMIT),
    ],
)
def test_stop_limit_preserves_trigger_and_limit(tmp_path, order_type, expected_constant):
    fake = FakePendingMT5()
    artifacts = pending_artifacts(tmp_path, order_type)
    request = pending_request(tmp_path, order_type, contract=artifacts.contract)
    response, _ = bridge_service(tmp_path, mt5=fake).handle(
        request.as_protected_dict(), AUTH_TOKEN
    )
    assert response["status"] == "ACCEPTED"
    assert fake.requests[0]["type"] == expected_constant
    assert fake.requests[0]["price"] == float(artifacts.contract.trigger_price)
    assert fake.requests[0]["stoplimit"] == float(artifacts.contract.limit_price)
    assert fake.requests[0]["price"] != fake.requests[0]["stoplimit"]


def test_terminal_without_stop_limit_support_fails_closed(tmp_path):
    fake = FakePendingMT5()
    client = FakePendingClient(supported=["BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"])
    response, _ = bridge_service(tmp_path, client=client, mt5=fake).handle(
        pending_request(tmp_path, "BUY_STOP_LIMIT").as_protected_dict(), AUTH_TOKEN
    )
    assert response["reason"] == "PENDING_ORDER_TYPE_UNSUPPORTED_BY_TERMINAL"
    assert fake.calls == 0


def test_pending_submission_is_blocked_by_default_on_app_and_bridge(tmp_path):
    request = pending_request(tmp_path)
    app_config = MT5LiveAdapterPreSubmitConfig(
        live_adapter_enabled=True,
        live_adapter_hard_block=False,
        allow_live_submission=True,
        allow_order_send=True,
        kill_switch_engaged=False,
        controlled_execution_enabled=True,
        execution_auth_token=AUTH_TOKEN,
    )
    fake_client = FakeExecutionClient(account_fingerprint=FINGERPRINT)
    receipt = MT5LiveAdapterDisabled(
        config=app_config, execution_client=fake_client
    ).submit_prepared_request(request, typed_confirmation=CONFIRMATION)
    assert receipt.reason == "PENDING_SUBMISSION_DISABLED"
    assert fake_client.submissions == 0

    fake = FakePendingMT5()
    response, _ = bridge_service(
        tmp_path,
        mt5=fake,
        config=bridge_config(
            tmp_path,
            pending_submission_enabled=False,
            pending_submission_hard_block=True,
        ),
    ).handle(request.as_protected_dict(), AUTH_TOKEN)
    assert response["reason"] == "PENDING_SUBMISSION_DISABLED"
    assert fake.calls == 0


def test_missing_execution_permission_is_blocked(tmp_path):
    with pytest.raises(ValueError, match="PENDING_EXECUTION_REQUEST_INCOMPLETE"):
        pending_request(tmp_path, permission=False)
    payload = pending_request(tmp_path).as_protected_dict()
    payload["execution_permission_requested"] = False
    response, _ = bridge_service(tmp_path).handle(payload, AUTH_TOKEN)
    assert response["reason"] == "PRE_SUBMIT_VALIDATION_REQUIRED"


def test_invalid_approval_and_confirmation_bindings_are_blocked(tmp_path):
    payload = pending_request(tmp_path).as_protected_dict()
    payload["approval_reference"] = "wrong-reference"
    response, _ = bridge_service(tmp_path).handle(payload, AUTH_TOKEN)
    assert response["reason"] == "PENDING_CONTRACT_REFERENCE_MISMATCH"

    payload = pending_request(tmp_path).as_protected_dict()
    payload["human_confirmation_reference"] = "0" * 64
    response, _ = bridge_service(tmp_path).handle(payload, AUTH_TOKEN)
    assert response["reason"] == "HUMAN_CONFIRMATION_INVALID"


def test_contract_mutation_invalidates_app_integrity(tmp_path):
    result = pending_artifacts(tmp_path)
    changed = replace(result.contract, trigger_price="99.9")
    assert not changed.integrity_valid()
    with pytest.raises(ValueError, match="PENDING_CONTRACT_INTEGRITY_INVALID"):
        pending_request(tmp_path, contract=changed)


def test_stale_contract_and_account_mismatch_are_blocked(tmp_path):
    result = pending_artifacts(tmp_path)
    stale = replace(
        result.contract,
        generated_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    )
    with pytest.raises(ValueError, match="PENDING_CONTRACT_EXPIRED"):
        pending_request(tmp_path, contract=stale)

    fake = FakePendingMT5()
    response, _ = bridge_service(
        tmp_path, client=FakePendingClient(fingerprint="b" * 64), mt5=fake
    ).handle(pending_request(tmp_path).as_protected_dict(), AUTH_TOKEN)
    assert response["reason"] == "ACCOUNT_CONTEXT_MISMATCH"
    assert fake.calls == 0


@pytest.mark.parametrize(
    ("client", "reason"),
    [
        (FakePendingClient(ask="100.4"), "PENDING_PRICE_RELATIONSHIP_INVALID"),
        (FakePendingClient(tick_size="0.4"), "PENDING_PRICE_INCREMENT_INVALID"),
        (FakePendingClient(trade_stops_level="6"), "PENDING_PRICE_RELATIONSHIP_INVALID"),
        (FakePendingClient(volume_min="0.02"), "PENDING_TERMINAL_CONSTRAINT_INVALID"),
    ],
)
def test_terminal_price_distance_and_volume_constraints_fail_closed(tmp_path, client, reason):
    fake = FakePendingMT5()
    response, _ = bridge_service(tmp_path, client=client, mt5=fake).handle(
        pending_request(tmp_path, "BUY_LIMIT").as_protected_dict(), AUTH_TOKEN
    )
    assert response["reason"] == reason
    assert fake.calls == 0


def test_invalid_protection_direction_and_expiration_fail_closed(tmp_path):
    result = pending_artifacts(tmp_path)
    invalid_protection = resign_contract(result.contract, stop_loss="101.0")
    response, _ = bridge_service(tmp_path).handle(
        pending_request(tmp_path, contract=invalid_protection).as_protected_dict(),
        AUTH_TOKEN,
    )
    assert response["reason"] == "PENDING_PROTECTION_DIRECTION_INVALID"

    unsupported_expiry = resign_contract(result.contract, expiration_policy="DAY")
    with pytest.raises(ValueError, match="PENDING_EXPIRATION_POLICY_REQUIRED"):
        pending_request(tmp_path, contract=unsupported_expiry)


def test_identical_completed_request_replays_protected_result_without_resubmit(tmp_path):
    fake = FakePendingMT5()
    executor = bridge_service(tmp_path, mt5=fake)
    payload = pending_request(tmp_path).as_protected_dict()
    first, _ = executor.handle(payload, AUTH_TOKEN)
    second, status = executor.handle(payload, AUTH_TOKEN)
    assert first["status"] == second["status"] == "ACCEPTED"
    assert status == 200 and second["idempotency_status"] == "RESULT_CONFIRMED"
    assert second["ticket"] is None and second["deal"] is None
    assert fake.calls == 1


def test_conflicting_duplicate_and_restart_fail_closed(tmp_path):
    fake = FakePendingMT5()
    payload = pending_request(tmp_path).as_protected_dict()
    first_service = bridge_service(tmp_path, mt5=fake)
    first_service.handle(payload, AUTH_TOKEN)
    conflict = dict(payload)
    conflict["pre_submit_validation_reference"] = "different-valid-reference"
    restarted = bridge_service(tmp_path, mt5=fake)
    response, status = restarted.handle(conflict, AUTH_TOKEN)
    assert status == 409 and response["reason"] == "IDEMPOTENCY_CONFLICT"
    assert fake.calls == 1


def test_result_unknown_is_retry_prohibited_across_restart(tmp_path):
    fake = FakePendingMT5(error=TimeoutError("unknown"))
    payload = pending_request(tmp_path).as_protected_dict()
    first, _ = bridge_service(tmp_path, mt5=fake).handle(payload, AUTH_TOKEN)
    second, _ = bridge_service(tmp_path, mt5=fake).handle(payload, AUTH_TOKEN)
    assert first["idempotency_status"] == "RESULT_UNKNOWN"
    assert second["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert second["idempotency_status"] == "RESULT_UNKNOWN"
    assert fake.calls == 1


def reconciliation_request(order_type="BUY"):
    return ProtectedReconciliationRequest(
        request_version="mt5-execution-reconciliation/v1",
        protected_execution_reference="mt5_execution_fixture",
        correlation_identity="a" * 64,
        correlation_tag="mt5rfixture",
        expected_account_context_fingerprint=FINGERPRINT,
        symbol_reference="TEST_SYMBOL",
        expected_order_type=order_type,
        expected_volume="0.01",
        submission_window_start=(NOW - timedelta(minutes=1)).isoformat(),
        submission_window_end=(NOW + timedelta(minutes=1)).isoformat(),
        canonical_semantic_hash="b" * 64,
        approval_reference="approval",
        lock_reference="lock",
        source_artifact_reference="source",
    )


def evidence_order(status):
    return {
        "ticket": 123456,
        "order": None,
        "position_id": None,
        "symbol": "TEST_SYMBOL",
        "direction": "BUY",
        "volume": "0.01",
        "comment": "mt5rfixture",
        "order_status": status,
    }


@pytest.mark.parametrize(
    ("order_status", "classification"),
    [
        ("ACTIVE", "UNIQUE_ACTIVE_ORDER_MATCH"),
        ("FILLED", "UNIQUE_CONFIRMED_MATCH"),
        ("CANCELLED", "UNIQUE_CANCELLED_ORDER_MATCH"),
        ("EXPIRED", "UNIQUE_EXPIRED_ORDER_MATCH"),
        ("REJECTED", "UNIQUE_REJECTED_ORDER_MATCH"),
    ],
)
def test_pending_order_reconciliation_classifies_terminal_state(order_status, classification):
    match = _match_evidence(
        reconciliation_request(),
        {"status": "OK", "orders": [evidence_order(order_status)], "deals": [], "positions": []},
    )
    assert match["classification"] == classification


def test_filled_pending_order_can_reconcile_to_position():
    order = evidence_order("FILLED")
    deal = {
        "ticket": 654321,
        "order": 123456,
        "position_id": 777,
        "symbol": "TEST_SYMBOL",
        "direction": "BUY",
        "volume": "0.01",
        "comment": "mt5rfixture",
    }
    position = {
        "ticket": 777,
        "symbol": "TEST_SYMBOL",
        "direction": "BUY",
        "volume": "0.01",
        "comment": "",
    }
    match = _match_evidence(
        reconciliation_request(),
        {"status": "OK", "orders": [order], "deals": [deal], "positions": [position]},
    )
    assert match["classification"] == "UNIQUE_CONFIRMED_MATCH"
    assert match["protected_broker_references"]["positions"] == [777]


def test_public_receipt_redacts_broker_identifiers(tmp_path):
    response, _ = bridge_service(tmp_path).handle(
        pending_request(tmp_path).as_protected_dict(), AUTH_TOKEN
    )
    assert response["ticket"] is None and response["deal"] is None
    assert response["metadata_redacted"] is True


def test_default_flags_and_static_execution_invariants():
    app = MT5LiveAdapterPreSubmitConfig()
    bridge = ControlledExecutionConfig()
    assert app.pending_submission_enabled is False
    assert app.pending_submission_hard_block is True
    assert not app.pending_limit_enabled and not app.pending_stop_enabled
    assert app.pending_stop_limit_enabled is False
    assert bridge.pending_submission_enabled is False
    assert bridge.pending_submission_hard_block is True
    execution_text = Path("tools/mt5_bridge/execution.py").read_text(encoding="utf-8")
    assert execution_text.count(".order_send(") == 1
    src_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in Path("src").rglob("*.py")
    )
    assert "import MetaTrader5" not in src_text