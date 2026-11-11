from __future__ import annotations

import hashlib
import json
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import test_mt5_controlled_execution_integration as controlled
from src.services.trading.execution.mt5_live_adapter_pre_submit import controlled_management as management_contract
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementRequest,
    MT5ManagementIntent,
    MT5ManagementProposal,
    management_confirmation_phrase,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleJournal,
    MT5LifecycleObservation,
    MT5LifecycleState,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from tools.mt5_bridge.execution import ProtectedExecutionJournal
from tools.mt5_bridge.management import (
    ControlledManagementConfig,
    ControlledMT5ManagementService,
)
from tools.mt5_bridge.mt5_client import protection_reference_hash
from tools.mt5_bridge.redaction import hash_identifier


ACCOUNT_A = "a" * 64
ACCOUNT_B = "b" * 64
AUTH_TOKEN = "management-fixture-token"
EXECUTION_REFERENCE = "mt5_execution_fixture_reference"
ORDER_IDENTIFIER = 123456
POSITION_IDENTIFIER = 654321
ORDER_REFERENCE = hash_identifier(ORDER_IDENTIFIER)
POSITION_REFERENCE = hash_identifier(POSITION_IDENTIFIER)
Result = namedtuple("Result", "retcode order deal comment")


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_REMOVE = 2
    TRADE_ACTION_SLTP = 3
    ORDER_TYPE_BUY = 4
    ORDER_TYPE_SELL = 5
    TRADE_RETCODE_DONE = 100
    TRADE_RETCODE_DONE_PARTIAL = 101
    TRADE_RETCODE_PLACED = 102

    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls = 0
        self.requests: list[dict] = []

    def order_send(self, request):
        self.calls += 1
        self.requests.append(dict(request))
        if self.error:
            raise self.error
        return Result(self.TRADE_RETCODE_DONE, 777001, 888001, "accepted")


class FakeManagementClient:
    def __init__(self, target: dict, snapshot: dict, *, fingerprints=None):
        self.target = dict(target)
        self.snapshot = dict(snapshot)
        self.fingerprints = list(fingerprints or [ACCOUNT_A])
        self.context_calls = 0
        self.target_calls = 0
        self.snapshot_calls = 0

    def execution_context(self):
        index = min(self.context_calls, len(self.fingerprints) - 1)
        fingerprint = self.fingerprints[index]
        self.context_calls += 1
        return {
            "status": "OK",
            "terminal_connected": True,
            "terminal_trade_allowed": True,
            "account_trade_allowed": True,
            "account_context_fingerprint": fingerprint,
        }

    def resolve_management_target(self, target_kind, protected_reference, symbol):
        self.target_calls += 1
        return dict(self.target)

    def lifecycle_snapshot(self, start, end, tags):
        self.snapshot_calls += 1
        assert start < end
        return dict(self.snapshot)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _observation(
    state: str,
    *,
    orders=None,
    positions=None,
    discrepancy="",
    observed_at: datetime | None = None,
) -> MT5LifecycleObservation:
    timestamp = (observed_at or datetime.now(timezone.utc)).isoformat()
    row = {
        "protected_execution_reference": EXECUTION_REFERENCE,
        "lifecycle_state": state,
        "account_fingerprint_hash": _sha(ACCOUNT_A),
        "evidence_classification": "UNIQUE_MANAGEMENT_TARGET",
        "protected_broker_references": {
            "orders": list(orders or []),
            "deals": [],
            "positions": list(positions or []),
        },
        "discrepancy_reason": discrepancy,
        "source_snapshot_reference": "mt5_lifecycle_snapshot_fixture",
    }
    digest = _sha(_canonical(row))
    return MT5LifecycleObservation(
        observation_id="mt5_lifecycle_observation_" + digest[:24],
        previous_lifecycle_state=MT5LifecycleState.UNKNOWN.value,
        observation_timestamp=timestamp,
        observation_hash=digest,
        **row,
    )


def _seed_journals(tmp_path: Path, observation: MT5LifecycleObservation):
    execution_path = tmp_path / "protected-execution.jsonl"
    lifecycle_path = tmp_path / "position-lifecycle.jsonl"
    journal = ProtectedExecutionJournal(execution_path)
    assert journal.reserve(
        "opening-execution-idempotency",
        "request-hash",
        ACCOUNT_A,
        protected_execution={
            "protected_execution_reference": EXECUTION_REFERENCE,
            "correlation_identity": "c" * 64,
            "correlation_tag": "mt5rfixture001",
            "canonical_semantic_hash": "d" * 64,
            "approval_reference": "approval-ref",
            "lock_reference": "lock-ref",
            "source_artifact_reference": "source-ref",
            "symbol": "TEST_SYMBOL",
            "order_type": "BUY",
            "volume": "1",
            "submission_window_start": observation.observation_timestamp,
        },
    )
    journal.transition("opening-execution-idempotency", "SUBMISSION_STARTED")
    journal.transition("opening-execution-idempotency", "RESULT_CONFIRMED")
    assert MT5LifecycleJournal(lifecycle_path).append_if_changed(observation)
    return execution_path, lifecycle_path


def _target(kind: str, volume="1") -> dict:
    identifier = ORDER_IDENTIFIER if kind == "order" else POSITION_IDENTIFIER
    reference = ORDER_REFERENCE if kind == "order" else POSITION_REFERENCE
    return {
        "status": "OK",
        "match_count": 1,
        "target_kind": kind,
        "ticket": identifier,
        "broker_reference_hash": reference,
        "symbol": "TEST_SYMBOL",
        "direction": "BUY",
        "volume": volume,
        "stop_loss": "0.8",
        "take_profit": "1.2",
        "bid": "1.0",
        "ask": "1.01",
        "minimum_stop_distance": "0.001",
        "volume_min": "0.01",
        "volume_step": "0.01",
    }


def _snapshot(*, active_orders=None, positions=None, recent_deals=None) -> dict:
    return {
        "status": "OK",
        "active_orders": list(active_orders or []),
        "recent_orders": [],
        "recent_deals": list(recent_deals or []),
        "positions": list(positions or []),
        "metadata_redacted": True,
    }


def _request(
    intent: str,
    observation: MT5LifecycleObservation,
    *,
    idempotency="management-idempotency-1",
    current_volume="1",
    resulting_volume=None,
    stop_loss=None,
    take_profit=None,
    deviation=None,
    phrase=None,
) -> MT5ControlledManagementRequest:
    proposal = MT5ManagementProposal.from_lifecycle_observation(
        observation,
        management_intent=intent,
        expected_account_context_fingerprint=ACCOUNT_A,
        symbol="TEST_SYMBOL",
        current_observed_volume=current_volume,
        idempotency_key=idempotency,
        requested_resulting_volume=resulting_volume,
        requested_stop_loss=stop_loss,
        requested_take_profit=take_profit,
        requested_deviation=deviation,
    )
    return MT5ControlledManagementRequest.confirm(
        proposal,
        typed_confirmation=phrase or management_confirmation_phrase(intent),
    )


def _config(execution_path: Path, lifecycle_path: Path, **overrides):
    values = {
        "enabled": True,
        "hard_block": False,
        "kill_switch_engaged": False,
        "global_kill_switch_engaged": False,
        "cancel_allowed": True,
        "protection_modification_allowed": True,
        "position_close_allowed": True,
        "order_send_enabled": True,
        "live_execution_enabled": True,
        "auth_token": AUTH_TOKEN,
        "max_request_age_seconds": 300,
        "submit_timeout_seconds": 0.2,
        "history_window_seconds": 3600,
        "journal_path": str(execution_path),
        "lifecycle_journal_path": str(lifecycle_path),
    }
    values.update(overrides)
    return ControlledManagementConfig(**values)


def _run(tmp_path, request, observation, target, snapshot, *, mt5=None, client=None, config_overrides=None):
    execution_path, lifecycle_path = _seed_journals(tmp_path, observation)
    fake_mt5 = mt5 or FakeMT5()
    fake_client = client or FakeManagementClient(target, snapshot)
    service = ControlledMT5ManagementService(
        fake_client,
        config=_config(execution_path, lifecycle_path, **(config_overrides or {})),
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(execution_path),
    )
    response, status = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    return response, status, fake_mt5, fake_client, ProtectedExecutionJournal(execution_path)


def test_cancel_one_eligible_pending_order(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    response, status, fake_mt5, _, journal = _run(
        tmp_path, request, observation, _target("order"), _snapshot()
    )
    assert status == 200 and response["status"] == "ACCEPTED"
    assert fake_mt5.calls == 1
    assert fake_mt5.requests[0] == {"action": fake_mt5.TRADE_ACTION_REMOVE, "order": ORDER_IDENTIFIER}
    assert journal.management_record(request.idempotency_key)["state"] == "RESULT_CONFIRMED"


@pytest.mark.parametrize("state", ["POSITION_CLOSED", "BROKER_REJECTED", "INCONSISTENT"])
def test_cancel_rejects_filled_closed_or_inconsistent_state(state):
    observation = _observation(state, orders=[ORDER_REFERENCE])
    with pytest.raises(ValueError, match="MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE"):
        _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)


def test_modify_protection_for_unique_open_position(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
        observation,
        resulting_volume="1",
        stop_loss="0.9",
        take_profit="1.2",
    )
    position = {
        "broker_reference_hash": POSITION_REFERENCE,
        "volume": "1",
        "protection_reference_hash": protection_reference_hash("TEST_SYMBOL", "0.9", "1.2"),
    }
    response, _, fake_mt5, _, _ = _run(
        tmp_path, request, observation, _target("position"), _snapshot(positions=[position])
    )
    assert response["management_applied"] is True
    assert fake_mt5.requests[0]["position"] == POSITION_IDENTIFIER
    assert fake_mt5.requests[0]["action"] == fake_mt5.TRADE_ACTION_SLTP


def test_modify_protection_rejects_ambiguous_evidence():
    observation = _observation(
        MT5LifecycleState.POSITION_OPEN.value,
        positions=[POSITION_REFERENCE, "f" * 64],
    )
    with pytest.raises(ValueError, match="PROTECTED_BROKER_REFERENCE_AMBIGUOUS"):
        _request(
            MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
            observation,
            resulting_volume="1",
            stop_loss="0.9",
        )


def test_modify_protection_rejects_volume_increase():
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    with pytest.raises(ValueError, match="POSITION_VOLUME_INCREASE_NOT_ALLOWED"):
        _request(
            MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
            observation,
            resulting_volume="1.1",
            stop_loss="0.9",
        )


def test_fully_close_one_open_position(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.CLOSE_POSITION.value,
        observation,
        resulting_volume="0",
        deviation=10,
    )
    closing_deal = {"position_reference_hash": POSITION_REFERENCE, "entry": "OUT"}
    response, _, fake_mt5, _, _ = _run(
        tmp_path,
        request,
        observation,
        _target("position"),
        _snapshot(recent_deals=[closing_deal]),
    )
    assert response["status"] == "ACCEPTED"
    assert fake_mt5.requests[0]["position"] == POSITION_IDENTIFIER
    assert fake_mt5.requests[0]["volume"] == 1.0
    assert fake_mt5.requests[0]["type"] == fake_mt5.ORDER_TYPE_SELL


def test_partially_close_one_open_position(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.CLOSE_POSITION.value,
        observation,
        resulting_volume="0.4",
        deviation=10,
    )
    remaining = {"broker_reference_hash": POSITION_REFERENCE, "volume": "0.4"}
    response, _, fake_mt5, _, _ = _run(
        tmp_path, request, observation, _target("position"), _snapshot(positions=[remaining])
    )
    assert response["status"] == "ACCEPTED"
    assert fake_mt5.requests[0]["volume"] == pytest.approx(0.6)


def test_close_rejects_volume_greater_than_current():
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    with pytest.raises(ValueError):
        _request(
            MT5ManagementIntent.CLOSE_POSITION.value,
            observation,
            resulting_volume="-0.1",
            deviation=10,
        )


def test_account_fingerprint_change_before_management_blocks(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    client = FakeManagementClient(_target("order"), _snapshot(), fingerprints=[ACCOUNT_A, ACCOUNT_B])
    response, _, fake_mt5, _, journal = _run(
        tmp_path, request, observation, _target("order"), _snapshot(), client=client
    )
    assert response["reason"] == "ACCOUNT_CONTEXT_CHANGED"
    assert fake_mt5.calls == 0
    assert journal.management_record(request.idempotency_key)["state"] == "RESULT_REJECTED"


def test_stale_lifecycle_observation_blocks():
    observation = _observation(
        MT5LifecycleState.ORDER_ACTIVE.value,
        orders=[ORDER_REFERENCE],
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    with pytest.raises(ValueError, match="LIFECYCLE_OBSERVATION_STALE"):
        _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)


def test_wrong_confirmation_intent_blocks():
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    with pytest.raises(ValueError, match="MANAGEMENT_CONFIRMATION_INVALID"):
        _request(
            MT5ManagementIntent.CANCEL_PENDING_ORDER.value,
            observation,
            phrase=management_confirmation_phrase(MT5ManagementIntent.CLOSE_POSITION.value),
        )


def test_management_kill_switch_engaged_blocks(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    response, _, fake_mt5, _, _ = _run(
        tmp_path,
        request,
        observation,
        _target("order"),
        _snapshot(),
        config_overrides={"kill_switch_engaged": True},
    )
    assert response["reason"] == "MANAGEMENT_DISABLED"
    assert fake_mt5.calls == 0


@pytest.mark.parametrize(
    "flag",
    ["enabled", "cancel_allowed", "order_send_enabled", "live_execution_enabled"],
)
def test_management_permission_disabled_blocks(tmp_path, flag):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    response, _, fake_mt5, _, _ = _run(
        tmp_path,
        request,
        observation,
        _target("order"),
        _snapshot(),
        config_overrides={flag: False},
    )
    assert response["reason"] == "MANAGEMENT_DISABLED"
    assert fake_mt5.calls == 0


def test_duplicate_idempotency_never_mutates_twice(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    execution_path, lifecycle_path = _seed_journals(tmp_path, observation)
    fake_mt5 = FakeMT5()
    service = ControlledMT5ManagementService(
        FakeManagementClient(_target("order"), _snapshot()),
        config=_config(execution_path, lifecycle_path),
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(execution_path),
    )
    first, _ = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    second, status = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert first["status"] == "ACCEPTED"
    assert status == 409 and second["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1


def test_transport_loss_becomes_unknown_and_never_retries(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    execution_path, lifecycle_path = _seed_journals(tmp_path, observation)
    fake_mt5 = FakeMT5(error=TimeoutError("unknown"))
    client = FakeManagementClient(
        _target("order"),
        _snapshot(active_orders=[{"broker_reference_hash": ORDER_REFERENCE}]),
    )
    service = ControlledMT5ManagementService(
        client,
        config=_config(execution_path, lifecycle_path),
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(execution_path),
    )
    first, _ = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    second, _ = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert first["status"] == "UNKNOWN" and first["idempotency_status"] == "RESULT_UNKNOWN"
    assert second["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1


def test_management_reconciliation_failure_after_broker_call_is_unknown(tmp_path, monkeypatch):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    execution_path, lifecycle_path = _seed_journals(tmp_path, observation)
    fake_mt5 = FakeMT5()
    service = ControlledMT5ManagementService(
        FakeManagementClient(_target("order"), _snapshot()),
        config=_config(execution_path, lifecycle_path),
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(execution_path),
    )

    def fail(*_args):
        raise RuntimeError("private failure")

    monkeypatch.setattr(service, "_reconcile", fail)
    first, status = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    duplicate, _ = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert status == 200 and first["status"] == "UNKNOWN"
    assert first["reason"] == "BROKER_RESULT_UNVERIFIED"
    assert first["reconciliation_required"] is True
    assert duplicate["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert fake_mt5.calls == 1


@pytest.mark.parametrize("intent", list(MT5ManagementIntent))
def test_cancel_modify_close_reconciliation_is_recorded(tmp_path, intent):
    if intent is MT5ManagementIntent.CANCEL_PENDING_ORDER:
        observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
        request = _request(intent.value, observation)
        target = _target("order")
        snapshot = _snapshot()
    elif intent is MT5ManagementIntent.MODIFY_POSITION_PROTECTION:
        observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
        request = _request(intent.value, observation, resulting_volume="1", stop_loss="0.9", take_profit="1.2")
        target = _target("position")
        snapshot = _snapshot(positions=[{
            "broker_reference_hash": POSITION_REFERENCE,
            "volume": "1",
            "protection_reference_hash": protection_reference_hash("TEST_SYMBOL", "0.9", "1.2"),
        }])
    else:
        observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
        request = _request(intent.value, observation, resulting_volume="0", deviation=10)
        target = _target("position")
        snapshot = _snapshot(recent_deals=[{"position_reference_hash": POSITION_REFERENCE, "entry": "OUT"}])
    response, _, _, client, journal = _run(tmp_path, request, observation, target, snapshot)
    record = journal.management_record(request.idempotency_key)
    assert response["management_applied"] is True
    assert record["protected_result"]["reconciliation_status"] == "CONFIRMED"
    assert client.snapshot_calls == 1


def test_public_request_and_receipt_are_redacted(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.CLOSE_POSITION.value,
        observation,
        resulting_volume="0",
        deviation=10,
    )
    public = request.as_redacted_dict()
    assert "protected_broker_reference" not in public
    assert "current_observed_volume" not in public
    response, _, _, _, _ = _run(
        tmp_path,
        request,
        observation,
        _target("position"),
        _snapshot(recent_deals=[{"position_reference_hash": POSITION_REFERENCE, "entry": "OUT"}]),
    )
    assert response["ticket"] is None and response["deal"] is None and response["position"] is None
    assert response["metadata_redacted"] is True


def test_exact_broker_identifiers_remain_only_in_protected_journal(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    response, _, _, _, journal = _run(
        tmp_path, request, observation, _target("order"), _snapshot()
    )
    assert str(ORDER_IDENTIFIER) not in json.dumps(response)
    protected = journal.path.read_text(encoding="utf-8")
    assert str(ORDER_IDENTIFIER) in protected


def test_default_management_config_is_fully_blocked():
    config = MT5LiveAdapterPreSubmitConfig()
    bridge = ControlledManagementConfig()
    assert config.controlled_management_enabled is False
    assert config.management_hard_block is True
    assert config.management_kill_switch_engaged is True
    assert config.management_cancel_allowed is False
    assert config.management_protection_modification_allowed is False
    assert config.management_position_close_allowed is False
    assert bridge.enabled is False and bridge.hard_block is True
    assert bridge.kill_switch_engaged is True


def test_automated_management_uses_fake_mt5_and_single_production_call_site(tmp_path):
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    fake_mt5 = FakeMT5()
    _run(tmp_path, request, observation, _target("order"), _snapshot(), mt5=fake_mt5)
    assert fake_mt5.calls == 1
    production = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (Path("src"), Path("tools"))
        for path in root.rglob("*.py")
        if "test" not in path.name
    )
    assert production.count(".order_send(") == 1
    assert "import MetaTrader5" not in "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in Path("src").rglob("*.py")
    )


def test_existing_controlled_submission_behavior_is_unchanged(tmp_path):
    fake_mt5 = controlled.FakeMT5()
    response, status = controlled.service(tmp_path, mt5=fake_mt5).handle(
        controlled.protected_payload("neighboring-controlled-submit"),
        controlled.AUTH_TOKEN,
    )
    assert status == 200 and response["status"] == "ACCEPTED"
    assert fake_mt5.calls == 1

def test_modify_one_protection_field_preserves_the_other(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
        observation,
        resulting_volume="1",
        stop_loss="0.9",
    )
    position = {
        "broker_reference_hash": POSITION_REFERENCE,
        "volume": "1",
        "protection_reference_hash": protection_reference_hash("TEST_SYMBOL", "0.9", "1.2"),
    }
    response, _, fake_mt5, _, _ = _run(
        tmp_path, request, observation, _target("position"), _snapshot(positions=[position])
    )
    assert response["status"] == "ACCEPTED"
    assert fake_mt5.requests[0]["sl"] == 0.9
    assert fake_mt5.requests[0]["tp"] == 1.2

def test_shared_adapter_blocks_management_by_default_without_bridge_call():
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)

    class NoCallClient:
        calls = 0

        def manage_controlled(self, payload, token):
            self.calls += 1
            raise AssertionError("default-blocked adapter must not call bridge")

    client = NoCallClient()
    adapter = MT5LiveAdapterDisabled(
        config=MT5LiveAdapterPreSubmitConfig(), execution_client=client
    )
    receipt = adapter.manage_prepared_request(
        request,
        typed_confirmation=management_confirmation_phrase(request.management_intent),
    )
    assert receipt.status == "BLOCKED"
    assert receipt.reason == "CONTROLLED_MANAGEMENT_DISABLED"
    assert client.calls == 0

def test_stale_management_confirmation_blocks():
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)
    values = request.as_protected_dict()
    stale = (datetime.fromisoformat(request.created_at) - timedelta(minutes=10)).isoformat()
    values["human_confirmation_timestamp"] = stale
    values["human_confirmation_reference"] = management_contract._confirmation_reference(
        request.human_confirmation_phrase,
        request.management_intent,
        request.protected_broker_reference,
        request.expected_account_context_fingerprint,
        request.lifecycle_observation_reference,
        request.mutation_hash,
        stale,
    )
    values["integrity_hash"] = management_contract._request_integrity_hash(values)
    stale_request = MT5ControlledManagementRequest(**values)
    with pytest.raises(ValueError, match="MANAGEMENT_CONFIRMATION_EXPIRED"):
        stale_request.validate()

def test_shared_adapter_forwards_one_enabled_management_request():
    observation = _observation(MT5LifecycleState.ORDER_ACTIVE.value, orders=[ORDER_REFERENCE])
    request = _request(MT5ManagementIntent.CANCEL_PENDING_ORDER.value, observation)

    class ManagementClient:
        calls = 0

        def account_context(self):
            return {
                "status": "OK",
                "account_context_fingerprint": ACCOUNT_A,
                "account_id_hash": "c" * 64,
                "server_redacted": "te***er",
                "currency": "USD",
                "trade_mode": 0,
                "redacted": True,
            }

        def manage_controlled(self, payload, token):
            self.calls += 1
            assert token == AUTH_TOKEN
            assert payload["integrity_hash"] == request.integrity_hash
            return {
                "status": "ACCEPTED",
                "management_intent": request.management_intent,
                "idempotency_status": "RESULT_CONFIRMED",
                "management_applied": True,
                "reconciliation_required": False,
                "lifecycle_update_required": True,
                "order_sent": True,
                "ticket_present": True,
                "deal_present": False,
                "position_present": False,
                "ticket": None,
                "deal": None,
                "position": None,
                "metadata_redacted": True,
            }

    config = MT5LiveAdapterPreSubmitConfig(
        live_adapter_enabled=True,
        live_adapter_hard_block=False,
        allow_live_submission=True,
        allow_order_send=True,
        kill_switch_engaged=False,
        execution_auth_token=AUTH_TOKEN,
        controlled_management_enabled=True,
        management_hard_block=False,
        management_kill_switch_engaged=False,
        management_cancel_allowed=True,
    )
    client = ManagementClient()
    receipt = MT5LiveAdapterDisabled(config=config, execution_client=client).manage_prepared_request(
        request,
        typed_confirmation=management_confirmation_phrase(request.management_intent),
    )
    assert receipt.status == "ACCEPTED"
    assert receipt.ticket is None and receipt.deal is None and receipt.position is None
    assert client.calls == 1

def test_close_rejects_unknown_target_direction(tmp_path):
    observation = _observation(MT5LifecycleState.POSITION_OPEN.value, positions=[POSITION_REFERENCE])
    request = _request(
        MT5ManagementIntent.CLOSE_POSITION.value,
        observation,
        resulting_volume="0",
        deviation=10,
    )
    target = _target("position")
    target["direction"] = "UNKNOWN"
    response, _, fake_mt5, _, _ = _run(
        tmp_path,
        request,
        observation,
        target,
        _snapshot(recent_deals=[{"position_reference_hash": POSITION_REFERENCE, "entry": "OUT"}]),
    )
    assert response["reason"] == "PROTECTED_BROKER_TARGET_MISMATCH"
    assert fake_mt5.calls == 0
