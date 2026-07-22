from __future__ import annotations

import hashlib
import json
import math
import statistics
import threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from time import perf_counter

import pytest

from scripts import test_mt5_controlled_execution_integration as controlled
from scripts import test_mt5_reconciliation_failure_recovery as reconciliation
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationRequest,
)
from tools.mt5_bridge import execution as bridge_execution
from tools.mt5_bridge import server as bridge_server
from tools.mt5_bridge.execution import (
    ControlledExecutionConfig,
    ControlledMT5ExecutionService,
    ProtectedExecutionJournal,
)
from tools.mt5_bridge.reconciliation import (
    ControlledMT5ReconciliationService,
    ReconciliationConfig,
)


class FakeHostBridgeClient(controlled.FakeClient):
    def __init__(self, evidence=None, *, fingerprints=None):
        super().__init__(fingerprints=fingerprints)
        self.evidence = evidence or {
            "status": "OK",
            "orders": [],
            "deals": [],
            "positions": [],
        }
        self.query_calls = 0

    def health(self):
        return {"status": "OK", "terminal_connected": True}

    def account_info(self):
        return {
            "status": "OK",
            "account_context_fingerprint": controlled.ACCOUNT_A,
            "account_id_hash": "c" * 64,
            "server_redacted": "te***er",
            "currency": "USD",
            "trade_mode": 0,
            "redacted": True,
        }

    def reconciliation_evidence(self, start, end):
        self.query_calls += 1
        assert start < end
        return self.evidence


def _enabled_adapter_config(bridge_url: str) -> MT5LiveAdapterPreSubmitConfig:
    return MT5LiveAdapterPreSubmitConfig(
        live_adapter_enabled=True,
        live_adapter_hard_block=False,
        allow_live_submission=True,
        allow_order_send=True,
        kill_switch_engaged=False,
        controlled_execution_enabled=True,
        execution_auth_token=controlled.AUTH_TOKEN,
        execution_confirmation_phrase=controlled.CONFIRMATION,
        bridge_url=bridge_url,
        controlled_execution_http_timeout_seconds=3.0,
    )


def _set_enabled_bridge_environment(monkeypatch, journal_path: Path) -> None:
    values = {
        "MT5_BRIDGE_CONTROLLED_EXECUTION_ENABLED": "true",
        "MT5_BRIDGE_CONTROLLED_EXECUTION_HARD_BLOCK": "false",
        "MT5_BRIDGE_EXECUTION_KILL_SWITCH": "false",
        "MT5_BRIDGE_ORDER_SEND_ENABLED": "true",
        "MT5_BRIDGE_LIVE_EXECUTION_ENABLED": "true",
        "MT5_BRIDGE_EXECUTION_TOKEN": controlled.AUTH_TOKEN,
        "MT5_BRIDGE_EXECUTION_CONFIRMATION_PHRASE": controlled.CONFIRMATION,
        "MT5_BRIDGE_EXECUTION_JOURNAL_PATH": str(journal_path),
        "MT5_BRIDGE_EXECUTION_TIMEOUT_SECONDS": "1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _reconciliation_service(journal_path: Path, client) -> ControlledMT5ReconciliationService:
    return ControlledMT5ReconciliationService(
        client,
        config=ReconciliationConfig(
            enabled=True,
            auth_token=controlled.AUTH_TOKEN,
            max_window_seconds=3600,
            reserved_stale_seconds=0,
            submission_stale_seconds=0,
            journal_path=str(journal_path),
        ),
        journal=ProtectedExecutionJournal(journal_path),
    )


def test_default_execution_path_is_blocked_and_redacted(tmp_path):
    fake_mt5 = controlled.FakeMT5()
    config = ControlledExecutionConfig(
        auth_token=controlled.AUTH_TOKEN,
        journal_path=str(tmp_path / "default-blocked.jsonl"),
    )
    response, status = controlled.service(
        tmp_path, mt5=fake_mt5, config=config
    ).handle(controlled.protected_payload(), controlled.AUTH_TOKEN)
    assert status == 403
    assert response["reason"] == "EXECUTION_DISABLED"
    assert response["metadata_redacted"] is True
    assert response["ticket"] is None and response["deal"] is None
    assert response["order_sent"] is False
    assert fake_mt5.calls == 0


def test_app_to_http_bridge_fake_mt5_lifecycle_submits_once(monkeypatch, tmp_path):
    journal_path = tmp_path / "http-e2e.jsonl"
    fake_mt5 = controlled.FakeMT5()
    fake_client = FakeHostBridgeClient()
    _set_enabled_bridge_environment(monkeypatch, journal_path)
    monkeypatch.setattr(bridge_execution, "mt5", fake_mt5)
    monkeypatch.setattr(bridge_server, "CLIENT", fake_client)

    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge_server.MT5BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bridge_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        adapter = MT5LiveAdapterDisabled(config=_enabled_adapter_config(bridge_url))
        request = MT5ControlledExecutionRequest(**controlled.protected_payload("http-e2e-1"))
        receipt = adapter.submit_prepared_request(
            request, typed_confirmation=controlled.CONFIRMATION
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert receipt.status == "ACCEPTED"
    assert receipt.order_sent is True
    assert receipt.ticket is None and receipt.deal is None
    assert receipt.ticket_present is True and receipt.deal_present is True
    assert fake_mt5.calls == 1
    assert "RESULT_CONFIRMED" in journal_path.read_text(encoding="utf-8")


def test_duplicate_is_blocked_after_execution_service_restart(tmp_path):
    journal_path = tmp_path / "duplicate-restart.jsonl"
    config = controlled.bridge_config(tmp_path, journal_path=str(journal_path))
    first_mt5 = controlled.FakeMT5()
    first_service = ControlledMT5ExecutionService(
        controlled.FakeClient(),
        config=config,
        mt5_module=first_mt5,
        journal=ProtectedExecutionJournal(journal_path),
    )
    first, _ = first_service.handle(
        controlled.protected_payload("restart-duplicate"), controlled.AUTH_TOKEN
    )

    restarted_mt5 = controlled.FakeMT5()
    restarted = ControlledMT5ExecutionService(
        controlled.FakeClient(),
        config=config,
        mt5_module=restarted_mt5,
        journal=ProtectedExecutionJournal(journal_path),
    )
    duplicate, status = restarted.handle(
        controlled.protected_payload("restart-duplicate"), controlled.AUTH_TOKEN
    )
    assert first["status"] == "ACCEPTED"
    assert status == 409 and duplicate["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert first_mt5.calls == 1 and restarted_mt5.calls == 0


def test_account_change_blocks_before_submission_started(tmp_path):
    fake_mt5 = controlled.FakeMT5()
    response, status = controlled.service(
        tmp_path,
        client=controlled.FakeClient([controlled.ACCOUNT_A, controlled.ACCOUNT_B]),
        mt5=fake_mt5,
    ).handle(controlled.protected_payload("account-change"), controlled.AUTH_TOKEN)
    journal = Path(controlled.bridge_config(tmp_path).journal_path).read_text(encoding="utf-8")
    assert status == 409 and response["reason"] == "ACCOUNT_CONTEXT_CHANGED"
    assert "SUBMISSION_STARTED" not in journal
    assert fake_mt5.calls == 0


def test_unknown_result_duplicate_restart_and_unique_reconciliation(tmp_path):
    journal_path = tmp_path / "unknown-reconcile.jsonl"
    config = controlled.bridge_config(tmp_path, journal_path=str(journal_path))
    timeout_mt5 = controlled.FakeMT5(error=TimeoutError("transport lost"))
    executor = ControlledMT5ExecutionService(
        controlled.FakeClient(),
        config=config,
        mt5_module=timeout_mt5,
        journal=ProtectedExecutionJournal(journal_path),
    )
    payload = controlled.protected_payload("unknown-reconcile")
    unknown, _ = executor.handle(payload, controlled.AUTH_TOKEN)
    assert unknown["idempotency_status"] == "RESULT_UNKNOWN"
    assert timeout_mt5.calls == 1

    restarted_mt5 = controlled.FakeMT5()
    restarted = ControlledMT5ExecutionService(
        controlled.FakeClient(),
        config=config,
        mt5_module=restarted_mt5,
        journal=ProtectedExecutionJournal(journal_path),
    )
    duplicate, _ = restarted.handle(payload, controlled.AUTH_TOKEN)
    assert duplicate["reason"] == "IDEMPOTENCY_DUPLICATE"
    assert restarted_mt5.calls == 0

    request = MT5ReconciliationRequest.from_controlled_request(
        MT5ControlledExecutionRequest(**payload),
        submission_window_end=datetime.now(timezone.utc).isoformat(),
    )
    reconciler = _reconciliation_service(
        journal_path,
        reconciliation.FakeReconciliationClient(reconciliation.unique_evidence()),
    )
    result, status = reconciler.handle(request.as_protected_dict(), controlled.AUTH_TOKEN)
    assert status == 200 and result["status"] == "CONFIRMED"
    assert result["resulting_execution_state"] == "RESULT_CONFIRMED"
    assert result["retry_decision"] == "RETRY_PROHIBITED"
    assert result["ticket"] is None and result["deal"] is None
    assert timeout_mt5.calls == 1


@pytest.mark.parametrize(
    ("client", "classification", "status"),
    [
        (reconciliation.FakeReconciliationClient(reconciliation.unique_evidence(extra=True)), "AMBIGUOUS_MATCH", "INCONCLUSIVE"),
        (reconciliation.FakeReconciliationClient(), "NO_MATCH", "INCONCLUSIVE"),
        (reconciliation.FakeReconciliationClient(raise_query=True), "QUERY_FAILED", "FAILED"),
    ],
)
def test_non_unique_reconciliation_never_authorizes_retry(
    tmp_path, client, classification, status
):
    request, journal = reconciliation.seed_record(tmp_path)
    service = _reconciliation_service(Path(journal.path), client)
    result, _ = service.handle(request.as_protected_dict(), controlled.AUTH_TOKEN)
    assert result["status"] == status
    assert result["evidence_classification"] == classification
    assert result["resulting_execution_state"] == "RESULT_UNKNOWN"
    assert result["retry_decision"] == "RETRY_PROHIBITED"
    assert result["automatic_retry_allowed"] is False


def test_missing_journal_reconciliation_fails_closed_without_query(tmp_path):
    request = reconciliation.reconciliation_request("missing-journal")
    client = reconciliation.FakeReconciliationClient(reconciliation.unique_evidence())
    result, status = _reconciliation_service(
        tmp_path / "missing.jsonl", client
    ).handle(request.as_protected_dict(), controlled.AUTH_TOKEN)
    assert status == 403 and result["reason"] == "EXECUTION_RECORD_NOT_FOUND"
    assert result["order_sent"] is False
    assert client.query_calls == 0


@pytest.mark.parametrize(
    "contents",
    [
        '{"state":"RESERVED"',
        '{"unexpected":true}\n',
        json.dumps(
            {
                "state": "RESULT_UNKNOWN",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "idempotency_key_hash": hashlib.sha256(b"conflict").hexdigest(),
                "metadata_redacted": True,
            }
        )
        + "\n",
    ],
)
def test_corrupt_journal_blocks_submission_and_preserves_original(tmp_path, contents):
    journal_path = tmp_path / "corrupt.jsonl"
    journal_path.write_text(contents, encoding="utf-8")
    before = journal_path.read_bytes()
    fake_mt5 = controlled.FakeMT5()
    config = controlled.bridge_config(tmp_path, journal_path=str(journal_path))
    response, status = ControlledMT5ExecutionService(
        controlled.FakeClient(),
        config=config,
        mt5_module=fake_mt5,
        journal=ProtectedExecutionJournal(journal_path),
    ).handle(controlled.protected_payload("corrupt-journal"), controlled.AUTH_TOKEN)
    assert status == 403 and response["reason"] == "EXECUTION_JOURNAL_CORRUPT"
    assert response["order_sent"] is False and fake_mt5.calls == 0
    assert journal_path.read_bytes() == before


def test_conflicting_transition_is_rejected_without_append(tmp_path):
    journal_path = tmp_path / "transition-conflict.jsonl"
    journal = ProtectedExecutionJournal(journal_path)
    assert journal.reserve("transition-key", "hash", controlled.ACCOUNT_A)
    journal.transition("transition-key", "SUBMISSION_STARTED")
    journal.transition("transition-key", "RESULT_UNKNOWN")
    before = journal_path.read_bytes()
    with pytest.raises(RuntimeError, match="invalid idempotency state transition"):
        journal.transition("transition-key", "RESULT_REJECTED")
    assert journal_path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(request_version="unsupported/v9"),
        lambda payload: payload["approved_semantic_parameters"].update(symbol="ALTERED"),
        lambda payload: payload.update(lock_value_hash="0" * 64),
        lambda payload: payload.pop("approval_reference"),
        lambda payload: payload.update(human_confirmation_reference="0" * 64),
    ],
)
def test_auth_and_integrity_fail_before_submission(tmp_path, mutation):
    payload = controlled.protected_payload("integrity-check")
    mutation(payload)
    fake_mt5 = controlled.FakeMT5()
    response, _ = controlled.service(tmp_path, mt5=fake_mt5).handle(
        payload, controlled.AUTH_TOKEN
    )
    assert response["status"] == "BLOCKED"
    assert response["metadata_redacted"] is True
    assert fake_mt5.calls == 0


def test_missing_and_invalid_authentication_fail_before_submission(tmp_path):
    for token in ("", "invalid-token"):
        fake_mt5 = controlled.FakeMT5()
        response, status = controlled.service(tmp_path / token.replace("-", "_"), mt5=fake_mt5).handle(
            controlled.protected_payload(f"auth-{token or 'missing'}"), token
        )
        assert status == 401 and response["reason"] == "AUTHENTICATION_FAILED"
        assert fake_mt5.calls == 0


def test_stale_approval_fails_before_submission(tmp_path):
    payload = controlled.protected_payload("stale-approval")
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload["approved_semantic_parameters"]["locked_at"] = old
    payload["lock_timestamp"] = old
    values = bridge_execution._canonical_values(
        {
            name: payload["approved_semantic_parameters"][name]
            for name in bridge_execution.SEMANTIC_FIELDS
        }
    )
    digest = bridge_execution._semantic_hash(payload["approved_semantic_parameters"], values)
    payload["approved_semantic_parameters"]["canonical_values_hash"] = digest
    payload["canonical_semantic_hash"] = digest
    payload["approval_value_hash"] = digest
    payload["lock_value_hash"] = digest
    fake_mt5 = controlled.FakeMT5()
    response, _ = controlled.service(tmp_path, mt5=fake_mt5).handle(
        payload, controlled.AUTH_TOKEN
    )
    assert response["reason"] == "APPROVAL_EXPIRED"
    assert fake_mt5.calls == 0


def _p95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def test_fake_mt5_lifecycle_latency_samples(tmp_path):
    sample_count = 20
    controlled_ms = []
    reconciliation_ms = []
    for index in range(sample_count):
        controlled_dir = tmp_path / f"controlled-{index}"
        started = perf_counter()
        response, _ = controlled.service(controlled_dir).handle(
            controlled.protected_payload(f"latency-controlled-{index}"),
            controlled.AUTH_TOKEN,
        )
        controlled_ms.append((perf_counter() - started) * 1000)
        assert response["status"] == "ACCEPTED"

        reconciliation_dir = tmp_path / f"reconciliation-{index}"
        request, journal = reconciliation.seed_record(
            reconciliation_dir,
            idempotency_key=f"latency-reconciliation-{index}",
        )
        service = _reconciliation_service(
            Path(journal.path),
            reconciliation.FakeReconciliationClient(reconciliation.unique_evidence()),
        )
        started = perf_counter()
        result, _ = service.handle(request.as_protected_dict(), controlled.AUTH_TOKEN)
        reconciliation_ms.append((perf_counter() - started) * 1000)
        assert result["status"] == "CONFIRMED"

    metrics = {
        "sample_count": sample_count,
        "controlled_median_ms": round(statistics.median(controlled_ms), 3),
        "controlled_p95_ms": round(_p95(controlled_ms), 3),
        "reconciliation_median_ms": round(statistics.median(reconciliation_ms), 3),
        "reconciliation_p95_ms": round(_p95(reconciliation_ms), 3),
    }
    metrics["slowest_major_stage"] = (
        "controlled_execution"
        if metrics["controlled_p95_ms"] >= metrics["reconciliation_p95_ms"]
        else "read_only_reconciliation"
    )
    print("SPRINT36_LATENCY=" + json.dumps(metrics, sort_keys=True))
    assert metrics["sample_count"] == sample_count
