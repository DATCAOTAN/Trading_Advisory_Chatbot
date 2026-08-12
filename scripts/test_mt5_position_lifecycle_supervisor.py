from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import namedtuple
from types import SimpleNamespace
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleJournal,
    MT5LifecycleState,
    MT5PositionLifecycleSupervisor,
    MT5PositionSupervisorConfig,
)
from tools.mt5_bridge.execution import ProtectedExecutionJournal


ACCOUNT_A = "a" * 64
ACCOUNT_B = "b" * 64
TAG = "mt5rfixture1234"
POSITION = hashlib.sha256(b"position").hexdigest()
ORDER = hashlib.sha256(b"order").hexdigest()
DEAL_IN = hashlib.sha256(b"deal-in").hexdigest()
DEAL_OUT = hashlib.sha256(b"deal-out").hexdigest()


class FakeLifecycleClient:
    def __init__(self, snapshot=None, *, error=False, entered=None, release=None):
        self.snapshot = snapshot or make_snapshot()
        self.error = error
        self.calls = 0
        self.entered = entered
        self.release = release

    def lifecycle_snapshot(self, history_window_seconds, correlation_tags, auth_token):
        self.calls += 1
        assert 0 < history_window_seconds <= 86_400
        assert correlation_tags == [] or TAG in correlation_tags
        assert auth_token == "fixture-token"
        if self.entered:
            self.entered.set()
        if self.release:
            self.release.wait(timeout=2)
        if self.error:
            raise TimeoutError("fake bridge unavailable")
        return json.loads(json.dumps(self.snapshot))


def h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def broker_row(
    reference: str,
    *,
    direction="BUY",
    volume="1.00",
    entry="UNKNOWN",
    order_reference="",
    position_reference="",
    tagged=True,
):
    return {
        "symbol": "TEST_SYMBOL",
        "direction": direction,
        "volume": volume,
        "time": "2026-07-22T00:00:00+00:00",
        "broker_reference_hash": reference,
        "order_reference_hash": order_reference,
        "position_reference_hash": position_reference,
        "entry": entry,
        "matched_correlation_tags": [TAG] if tagged else [],
        "metadata_redacted": True,
    }


def make_snapshot(
    *,
    fingerprint=ACCOUNT_A,
    active_orders=None,
    recent_orders=None,
    recent_deals=None,
    positions=None,
    reference="snapshot-a",
):
    return {
        "status": "OK",
        "terminal_connected": True,
        "terminal_trade_allowed": True,
        "account_trade_allowed": True,
        "account_context_fingerprint": fingerprint,
        "active_orders": active_orders or [],
        "recent_orders": recent_orders or [],
        "recent_deals": recent_deals or [],
        "positions": positions or [],
        "snapshot_reference": reference,
        "metadata_redacted": True,
    }


def config(tmp_path, **overrides):
    values = {
        "interval_seconds": 0.01,
        "history_window_seconds": 3600,
        "stale_submission_seconds": 30,
        "execution_journal_path": str(tmp_path / "execution.jsonl"),
        "lifecycle_journal_path": str(tmp_path / "lifecycle.jsonl"),
        "bridge_url": "http://fixture.invalid",
        "auth_token": "fixture-token",
    }
    values.update(overrides)
    return MT5PositionSupervisorConfig(**values)


def seed_execution(tmp_path, state="RESULT_CONFIRMED", *, fingerprint=ACCOUNT_A, volume="1.00"):
    cfg = config(tmp_path)
    journal = ProtectedExecutionJournal(cfg.execution_journal_path)
    protected = {
        "protected_execution_reference": "execution-fixture",
        "correlation_identity": h("correlation"),
        "correlation_tag": TAG,
        "canonical_semantic_hash": h("semantic"),
        "approval_reference": "approval-fixture",
        "lock_reference": "lock-fixture",
        "source_artifact_reference": "source-fixture",
        "symbol": "TEST_SYMBOL",
        "order_type": "BUY",
        "volume": volume,
        "submission_window_start": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    assert journal.reserve("fixture-idempotency", h("request"), fingerprint, protected)
    if state in {"SUBMISSION_STARTED", "RESULT_CONFIRMED", "RESULT_UNKNOWN"}:
        journal.transition("fixture-idempotency", "SUBMISSION_STARTED")
    if state in {"RESULT_CONFIRMED", "RESULT_UNKNOWN"}:
        journal.transition("fixture-idempotency", state)
    return cfg


def run(tmp_path, snapshot, *, state="RESULT_CONFIRMED", fingerprint=ACCOUNT_A):
    cfg = seed_execution(tmp_path, state, fingerprint=fingerprint)
    supervisor = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient(snapshot))
    return supervisor.run_once(), supervisor


def state_of(status):
    assert sum(status.lifecycle_state_counts.values()) >= 1
    return next(iter(status.lifecycle_state_counts))


def open_position(volume="1.00", *, reference=POSITION, tagged=True):
    return broker_row(reference, volume=volume, tagged=tagged)


def opening_deal(position=POSITION):
    return broker_row(
        DEAL_IN,
        entry="IN",
        order_reference=ORDER,
        position_reference=position,
    )


def closing_deal(position=POSITION):
    return broker_row(
        DEAL_OUT,
        direction="SELL",
        entry="OUT",
        order_reference=ORDER,
        position_reference=position,
        tagged=False,
    )


def test_accepted_execution_with_open_position(tmp_path):
    status, _ = run(tmp_path, make_snapshot(positions=[open_position()]))
    assert state_of(status) == MT5LifecycleState.POSITION_OPEN.value
    assert status.discrepancy_count == 0


def test_untagged_broker_evidence_is_bound_by_protected_result_reference(tmp_path):
    cfg = seed_execution(tmp_path, state="RESULT_REJECTED")
    journal = ProtectedExecutionJournal(cfg.execution_journal_path)
    journal.transition("fixture-idempotency", "RESULT_REJECTED", retcode=10016)
    protected = {
        "protected_execution_reference": "execution-confirmed",
        "correlation_identity": h("correlation-confirmed"),
        "correlation_tag": "mt5rconfirmed123",
        "canonical_semantic_hash": h("semantic-confirmed"),
        "approval_reference": "approval-confirmed",
        "lock_reference": "lock-confirmed",
        "source_artifact_reference": "source-confirmed",
        "symbol": "TEST_SYMBOL",
        "order_type": "BUY",
        "volume": "1.00",
        "submission_window_start": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    assert journal.reserve("confirmed-idempotency", h("confirmed-request"), ACCOUNT_A, protected)
    journal.transition("confirmed-idempotency", "SUBMISSION_STARTED")
    journal.transition("confirmed-idempotency", "RESULT_CONFIRMED", order="101", deal="202")
    snapshot = make_snapshot(
        recent_orders=[broker_row(h("101"), tagged=False)],
        recent_deals=[
            broker_row(
                h("202"), entry="IN", order_reference=h("101"),
                position_reference=h("303"), tagged=False,
            ),
            broker_row(
                h("204"), direction="SELL", entry="OUT", order_reference=h("101"),
                position_reference=h("303"), tagged=False,
            ),
        ],
    )

    status = MT5PositionLifecycleSupervisor(
        cfg, bridge_client=FakeLifecycleClient(snapshot)
    ).run_once()

    assert status.discrepancy_count == 0
    assert status.lifecycle_state_counts == {
        MT5LifecycleState.BROKER_REJECTED.value: 1,
        MT5LifecycleState.POSITION_CLOSED.value: 1,
    }


def test_pending_order_is_order_active(tmp_path):
    status, _ = run(tmp_path, make_snapshot(active_orders=[broker_row(ORDER)]))
    assert state_of(status) == MT5LifecycleState.ORDER_ACTIVE.value


def test_fully_closed_position_requires_linked_closing_deal(tmp_path):
    status, _ = run(tmp_path, make_snapshot(recent_deals=[opening_deal(), closing_deal()]))
    assert state_of(status) == MT5LifecycleState.POSITION_CLOSED.value


def test_partial_reduction(tmp_path):
    status, _ = run(tmp_path, make_snapshot(positions=[open_position("0.40")]))
    assert state_of(status) == MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value


def test_result_unknown_requires_reconciliation(tmp_path):
    status, _ = run(tmp_path, make_snapshot(), state="RESULT_UNKNOWN")
    assert state_of(status) == MT5LifecycleState.RECONCILIATION_REQUIRED.value


def test_account_fingerprint_change_is_inconsistent(tmp_path):
    status, _ = run(tmp_path, make_snapshot(fingerprint=ACCOUNT_B, positions=[open_position()]))
    assert state_of(status) == MT5LifecycleState.INCONSISTENT.value
    assert status.account_context_match is False
    assert status.discrepancy_count == 1


def test_duplicate_broker_match_is_inconsistent(tmp_path):
    status, _ = run(
        tmp_path,
        make_snapshot(positions=[open_position(), open_position(reference=h("position-2"))]),
    )
    assert state_of(status) == MT5LifecycleState.INCONSISTENT.value
    assert status.discrepancy_count >= 1


def test_confirmed_record_without_broker_evidence_is_inconsistent(tmp_path):
    status, _ = run(tmp_path, make_snapshot())
    assert state_of(status) == MT5LifecycleState.INCONSISTENT.value
    rows = MT5LifecycleJournal(config(tmp_path).lifecycle_journal_path).observations()
    assert rows[-1]["discrepancy_reason"] == "CONFIRMED_BROKER_EVIDENCE_ABSENT"


def test_unmatched_broker_position_is_recorded(tmp_path):
    cfg = config(tmp_path)
    supervisor = MT5PositionLifecycleSupervisor(
        cfg, bridge_client=FakeLifecycleClient(make_snapshot(positions=[open_position(tagged=False)]))
    )
    status = supervisor.run_once()
    assert status.discrepancy_count == 1
    assert status.lifecycle_state_counts == {MT5LifecycleState.INCONSISTENT.value: 1}
    assert MT5LifecycleJournal(cfg.lifecycle_journal_path).observations()[-1][
        "discrepancy_reason"
    ] == "UNMATCHED_BROKER_POSITION"


def test_bridge_unavailable_fails_closed(tmp_path):
    cfg = seed_execution(tmp_path)
    client = FakeLifecycleClient(error=True)
    status = MT5PositionLifecycleSupervisor(cfg, bridge_client=client).run_once()
    assert status.supervisor_status == "BLOCKED"
    assert status.bridge_available is False
    assert status.health_reason == "BRIDGE_UNAVAILABLE"


def test_malformed_lifecycle_journal_is_persistence_unsafe(tmp_path):
    cfg = seed_execution(tmp_path)
    Path(cfg.lifecycle_journal_path).write_text('{"broken":', encoding="utf-8")
    client = FakeLifecycleClient()
    status = MT5PositionLifecycleSupervisor(cfg, bridge_client=client).run_once()
    assert status.supervisor_status == "PERSISTENCE_UNSAFE"
    assert status.health_reason == "LIFECYCLE_JOURNAL_CORRUPT"
    assert client.calls == 0


def test_restart_reloads_lifecycle_journal(tmp_path):
    cfg = seed_execution(tmp_path)
    snapshot = make_snapshot(positions=[open_position()])
    first = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient(snapshot))
    assert first.run_once().observations_appended == 1
    restarted = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient(snapshot))
    assert restarted.run_once().observations_appended == 0
    assert len(MT5LifecycleJournal(cfg.lifecycle_journal_path).observations()) == 1


def test_repeated_identical_snapshot_is_idempotent(tmp_path):
    cfg = seed_execution(tmp_path)
    supervisor = MT5PositionLifecycleSupervisor(
        cfg, bridge_client=FakeLifecycleClient(make_snapshot(positions=[open_position()]))
    )
    assert supervisor.run_once().observations_appended == 1
    assert supervisor.run_once().observations_appended == 0


def test_overlapping_cycles_are_prevented(tmp_path):
    cfg = seed_execution(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    supervisor = MT5PositionLifecycleSupervisor(
        cfg,
        bridge_client=FakeLifecycleClient(
            make_snapshot(positions=[open_position()]), entered=entered, release=release
        ),
    )
    thread = threading.Thread(target=supervisor.run_once)
    thread.start()
    assert entered.wait(timeout=1)
    overlap = supervisor.run_once()
    assert overlap.supervisor_status == "CYCLE_SKIPPED_OVERLAP"
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_clean_stop_and_single_active_instance_per_path(tmp_path):
    cfg = seed_execution(tmp_path)
    first = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient())
    second = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient())
    first.start()
    with pytest.raises(RuntimeError, match="already active"):
        second.start()
    first.stop()
    second.start()
    second.stop()


def test_public_status_is_redacted(tmp_path):
    status, _ = run(tmp_path, make_snapshot(positions=[open_position()]))
    payload = json.dumps(status.to_safe_dict(), sort_keys=True)
    assert ACCOUNT_A not in payload
    assert POSITION not in payload
    assert "ticket" not in payload.lower()
    assert status.account_fingerprint_prefix == ACCOUNT_A[:12]
    assert status.metadata_redacted is True


def test_supervisor_and_cli_have_no_order_send_or_mutation_call():
    text = Path(
        "src/services/trading/execution/mt5_live_adapter_pre_submit/lifecycle_supervisor.py"
    ).read_text(encoding="utf-8") + Path("scripts/run_mt5_position_supervisor.py").read_text(encoding="utf-8")
    assert ".order_send(" not in text
    for marker in ("position_close(", "order_delete(", "order_modify(", "submit_controlled("):
        assert marker not in text
    production = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (Path("src"), Path("tools"))
        for path in root.rglob("*.py")
    )
    assert production.count(".order_send(") == 1


def test_execution_flags_remain_disabled(tmp_path):
    status, _ = run(tmp_path, make_snapshot(positions=[open_position()]))
    assert status.live_submission_allowed is False
    assert status.live_execution_allowed is False
    assert status.order_send_allowed is False
    assert status.execution_allowed is False
    assert status.executable is False
    assert status.automatic_retry_allowed is False
    assert status.kill_switch_engaged is True


def test_stale_submission_state_requires_reconciliation(tmp_path):
    cfg = seed_execution(tmp_path, state="SUBMISSION_STARTED")
    status = MT5PositionLifecycleSupervisor(
        replace(cfg, stale_submission_seconds=0), bridge_client=FakeLifecycleClient()
    ).run_once()
    assert state_of(status) == MT5LifecycleState.RECONCILIATION_REQUIRED.value
    row = MT5LifecycleJournal(cfg.lifecycle_journal_path).observations()[-1]
    assert row["discrepancy_reason"] == "STALE_SUBMISSION_STATE"


def test_position_without_closing_deal_is_not_assumed_closed(tmp_path):
    status, _ = run(tmp_path, make_snapshot(recent_deals=[opening_deal()]))
    assert state_of(status) == MT5LifecycleState.INCONSISTENT.value
    row = MT5LifecycleJournal(config(tmp_path).lifecycle_journal_path).observations()[-1]
    assert row["discrepancy_reason"] == "POSITION_CLOSED_WITHOUT_CLOSING_DEAL"

def test_lifecycle_snapshot_endpoint_requires_existing_execution_auth(monkeypatch):
    from tools.mt5_bridge import server

    class FakeBridge:
        def __init__(self):
            self.calls = 0

        def lifecycle_snapshot(self, start, end, tags):
            self.calls += 1
            assert start < end and tags == [TAG]
            return make_snapshot()

    fake = FakeBridge()
    monkeypatch.setattr(server, "CLIENT", fake)
    monkeypatch.setenv("MT5_BRIDGE_EXECUTION_TOKEN", "fixture-token")
    payload = {"history_window_seconds": 60, "correlation_tags": [TAG]}
    blocked, blocked_status = server._lifecycle_snapshot_response(payload, "wrong-token")
    assert blocked_status == 401 and blocked["reason"] == "AUTHENTICATION_FAILED"
    result, status = server._lifecycle_snapshot_response(payload, "fixture-token")
    assert status == 200 and result["metadata_redacted"] is True
    assert fake.calls == 1


def test_host_snapshot_hashes_broker_identifiers_before_http(monkeypatch):
    from tools.mt5_bridge import mt5_client

    Row = namedtuple(
        "Row",
        "ticket order position_id symbol type volume_initial volume time comment entry",
    )
    order_row = Row(101, 0, 0, "TEST_SYMBOL", 0, 1.0, 1.0, 1, TAG, 0)
    deal_row = Row(202, 101, 303, "TEST_SYMBOL", 0, 1.0, 1.0, 1, TAG, 0)
    position_row = Row(303, 0, 0, "TEST_SYMBOL", 0, 1.0, 1.0, 1, TAG, 0)
    fake_mt5 = SimpleNamespace(
        orders_get=lambda: None,
        history_orders_get=lambda start, end: None,
        history_deals_get=lambda start, end: None,
        positions_get=lambda: None,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        DEAL_TYPE_BUY=0,
        DEAL_TYPE_SELL=1,
        POSITION_TYPE_BUY=0,
        POSITION_TYPE_SELL=1,
        DEAL_ENTRY_IN=0,
        DEAL_ENTRY_OUT=1,
        DEAL_ENTRY_OUT_BY=2,
        DEAL_ENTRY_INOUT=3,
    )
    monkeypatch.setattr(mt5_client, "mt5", fake_mt5)

    def fake_call(operation, *args, **kwargs):
        if operation is fake_mt5.orders_get:
            return [order_row]
        if operation is fake_mt5.history_orders_get:
            return [order_row]
        if operation is fake_mt5.history_deals_get:
            return [deal_row]
        if operation is fake_mt5.positions_get:
            return [position_row]
        raise AssertionError("unexpected fake MT5 operation")

    monkeypatch.setattr(mt5_client, "_call_mt5", fake_call)
    client = mt5_client.MT5Client()
    monkeypatch.setattr(
        client,
        "execution_context",
        lambda: {
            "status": "OK",
            "terminal_connected": True,
            "terminal_trade_allowed": True,
            "account_trade_allowed": True,
            "account_context_fingerprint": ACCOUNT_A,
        },
    )
    now = datetime.now(timezone.utc)
    snapshot = client.lifecycle_snapshot(now - timedelta(minutes=1), now, [TAG])
    encoded = json.dumps(snapshot, sort_keys=True)
    assert snapshot["status"] == "OK"
    assert all(token not in encoded for token in ('"ticket"', '"order"', '"position_id"', '"comment"'))
    references = {
        row[key]
        for group in ("active_orders", "recent_orders", "recent_deals", "positions")
        for row in snapshot[group]
        for key in ("broker_reference_hash", "order_reference_hash", "position_reference_hash")
        if row[key]
    }
    assert all(len(reference) == 64 for reference in references)
    assert references.isdisjoint({"101", "202", "303"})
    assert snapshot["positions"][0]["broker_reference_hash"] == h("303")

def test_malformed_execution_journal_is_persistence_unsafe(tmp_path):
    cfg = config(tmp_path)
    Path(cfg.execution_journal_path).write_text('{"state":', encoding="utf-8")
    client = FakeLifecycleClient()
    status = MT5PositionLifecycleSupervisor(cfg, bridge_client=client).run_once()
    assert status.supervisor_status == "PERSISTENCE_UNSAFE"
    assert status.health_reason == "EXECUTION_JOURNAL_CORRUPT"
    assert client.calls == 0


def test_conflicting_position_volume_is_inconsistent(tmp_path):
    status, _ = run(tmp_path, make_snapshot(positions=[open_position("2.00")]))
    assert state_of(status) == MT5LifecycleState.INCONSISTENT.value
    row = MT5LifecycleJournal(config(tmp_path).lifecycle_journal_path).observations()[-1]
    assert row["discrepancy_reason"] == "CONFLICTING_VOLUME_OR_DIRECTION"


def test_lifecycle_journal_preserves_previous_state(tmp_path):
    cfg = seed_execution(tmp_path)
    client = FakeLifecycleClient(make_snapshot(positions=[open_position()], reference="snapshot-open"))
    supervisor = MT5PositionLifecycleSupervisor(cfg, bridge_client=client)
    assert supervisor.run_once().observations_appended == 1
    client.snapshot = make_snapshot(positions=[open_position("0.50")], reference="snapshot-partial")
    assert supervisor.run_once().observations_appended == 1
    rows = MT5LifecycleJournal(cfg.lifecycle_journal_path).observations()
    assert rows[-1]["previous_lifecycle_state"] == MT5LifecycleState.POSITION_OPEN.value
    assert rows[-1]["lifecycle_state"] == MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value
