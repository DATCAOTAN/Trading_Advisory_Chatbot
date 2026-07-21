from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
    MT5ReconciliationRequest,
)
from tools.mt5_bridge.execution import ProtectedExecutionJournal
from tools.mt5_bridge.reconciliation import (
    ControlledMT5ReconciliationService,
    ProtectedReconciliationRequest,
    ReconciliationConfig,
)


ACCOUNT_A = "a" * 64
ACCOUNT_B = "b" * 64
AUTH_TOKEN = "reconciliation-fixture-token"
ORDER_ID = 700001
DEAL_ID = 800001
POSITION_ID = 900001


class FakeReconciliationClient:
    def __init__(self, evidence=None, *, fingerprint=ACCOUNT_A, raise_query=False):
        self.fingerprint = fingerprint
        self.evidence = evidence or {"status": "OK", "orders": [], "deals": [], "positions": []}
        self.raise_query = raise_query
        self.query_calls = 0

    def execution_context(self):
        return {
            "status": "OK",
            "terminal_connected": True,
            "account_context_fingerprint": self.fingerprint,
            "redacted": True,
        }

    def reconciliation_evidence(self, start, end):
        self.query_calls += 1
        assert start < end
        if self.raise_query:
            raise TimeoutError("fixture query timeout")
        return self.evidence


def controlled_request(idempotency_key="reconcile-idempotency-1"):
    now = datetime.now(timezone.utc)
    return MT5ControlledExecutionRequest(
        request_version="controlled-mt5-execution/v1",
        approved_semantic_parameters={
            "symbol": "TEST_SYMBOL",
            "order_type": "BUY",
            "volume": "0.01",
        },
        canonical_semantic_hash="c" * 64,
        approval_value_hash="c" * 64,
        lock_value_hash="c" * 64,
        approval_reference="approval-reference",
        lock_reference="lock-reference",
        source_artifact_reference="source-reference",
        approval_timestamp=(now - timedelta(seconds=60)).isoformat(),
        lock_timestamp=(now - timedelta(seconds=60)).isoformat(),
        human_confirmation_reference="d" * 64,
        human_confirmation_phrase="SUBMIT CONTROLLED MT5 ORDER",
        pre_submit_validation_reference="pre-submit-reference",
        pre_submit_validation_valid=True,
        idempotency_key=idempotency_key,
        expected_account_context_fingerprint=ACCOUNT_A,
        execution_permission_requested=True,
    )


def reconciliation_request(idempotency_key="reconcile-idempotency-1"):
    return MT5ReconciliationRequest.from_controlled_request(
        controlled_request(idempotency_key),
        submission_window_end=datetime.now(timezone.utc).isoformat(),
    )


def unique_evidence(*, extra=False):
    orders = [
        {
            "ticket": ORDER_ID,
            "symbol": "TEST_SYMBOL",
            "direction": "BUY",
            "volume": "0.01",
            "comment": "fixture",
        }
    ]
    deals = [
        {
            "ticket": DEAL_ID,
            "order": ORDER_ID,
            "position_id": POSITION_ID,
            "symbol": "TEST_SYMBOL",
            "direction": "BUY",
            "volume": "0.01",
            "comment": "fixture",
        }
    ]
    positions = [
        {
            "ticket": POSITION_ID,
            "symbol": "TEST_SYMBOL",
            "direction": "BUY",
            "volume": "0.01",
            "comment": "fixture",
        }
    ]
    if extra:
        orders.append({**orders[0], "ticket": ORDER_ID + 1})
        deals.append(
            {
                **deals[0],
                "ticket": DEAL_ID + 1,
                "order": ORDER_ID + 1,
                "position_id": POSITION_ID + 1,
            }
        )
        positions.append({**positions[0], "ticket": POSITION_ID + 1})
    return {"status": "OK", "orders": orders, "deals": deals, "positions": positions}


def config(tmp_path, **overrides):
    values = {
        "enabled": True,
        "auth_token": AUTH_TOKEN,
        "max_window_seconds": 3600,
        "reserved_stale_seconds": 0,
        "submission_stale_seconds": 0,
        "journal_path": str(tmp_path / "protected-execution.jsonl"),
    }
    values.update(overrides)
    return ReconciliationConfig(**values)


def seed_record(tmp_path, state="RESULT_UNKNOWN", *, idempotency_key="reconcile-idempotency-1"):
    request = reconciliation_request(idempotency_key)
    journal = ProtectedExecutionJournal(config(tmp_path).journal_path)
    journal.reserve(
        idempotency_key,
        "request-hash",
        ACCOUNT_A,
        protected_execution={
            "protected_execution_reference": request.protected_execution_reference,
            "correlation_identity": request.correlation_identity,
            "correlation_tag": request.correlation_tag,
            "canonical_semantic_hash": request.canonical_semantic_hash,
            "approval_reference": request.approval_reference,
            "lock_reference": request.lock_reference,
            "source_artifact_reference": request.source_artifact_reference,
            "symbol": request.symbol_reference,
            "order_type": request.expected_order_type,
            "volume": request.expected_volume,
            "submission_window_start": request.submission_window_start,
        },
    )
    if state in {"SUBMISSION_STARTED", "RESULT_UNKNOWN"}:
        journal.transition(idempotency_key, "SUBMISSION_STARTED")
    if state == "RESULT_UNKNOWN":
        journal.transition(idempotency_key, "RESULT_UNKNOWN", reason="fixture")
    return request, journal


def reconcile(tmp_path, client, *, state="RESULT_UNKNOWN", idempotency_key="reconcile-idempotency-1"):
    request, journal = seed_record(tmp_path, state, idempotency_key=idempotency_key)
    service = ControlledMT5ReconciliationService(
        client,
        config=config(tmp_path),
        journal=journal,
    )
    payload, status = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    return payload, status, request, journal, service


def test_result_unknown_unique_order_deal_match_confirms(tmp_path):
    payload, status, _, _, _ = reconcile(tmp_path, FakeReconciliationClient(unique_evidence()))
    assert status == 200
    assert payload["status"] == "CONFIRMED"
    assert payload["evidence_classification"] == "UNIQUE_CONFIRMED_MATCH"
    assert payload["resulting_execution_state"] == "RESULT_CONFIRMED"


def test_result_unknown_multiple_matches_remain_ambiguous(tmp_path):
    payload, _, _, _, _ = reconcile(tmp_path, FakeReconciliationClient(unique_evidence(extra=True)))
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["evidence_classification"] == "AMBIGUOUS_MATCH"
    assert payload["resulting_execution_state"] == "RESULT_UNKNOWN"


def test_result_unknown_no_match_remains_inconclusive(tmp_path):
    payload, _, _, _, _ = reconcile(tmp_path, FakeReconciliationClient())
    assert payload["evidence_classification"] == "NO_MATCH"
    assert payload["resulting_execution_state"] == "RESULT_UNKNOWN"


def test_result_unknown_query_failure_fails_closed(tmp_path):
    payload, _, _, _, _ = reconcile(
        tmp_path, FakeReconciliationClient(raise_query=True)
    )
    assert payload["status"] == "FAILED"
    assert payload["evidence_classification"] == "QUERY_FAILED"
    assert payload["resulting_execution_state"] == "RESULT_UNKNOWN"

def test_mt5_none_query_result_is_query_failed(monkeypatch):
    from tools.mt5_bridge import mt5_client

    client = mt5_client.MT5Client()
    monkeypatch.setattr(client, "ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(mt5_client, "_call_mt5", lambda *args, **kwargs: None)
    evidence = client.reconciliation_evidence(
        datetime.now(timezone.utc) - timedelta(minutes=1),
        datetime.now(timezone.utc),
    )
    assert evidence["status"] == "QUERY_FAILED"
    assert evidence["message"] == "MT5_QUERY_RETURNED_NONE"


def test_account_fingerprint_change_blocks_without_state_mutation(tmp_path):
    payload, _, request, journal, _ = reconcile(
        tmp_path, FakeReconciliationClient(fingerprint=ACCOUNT_B)
    )
    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "ACCOUNT_CONTEXT_CHANGED"
    assert payload["evidence_classification"] == "ACCOUNT_CONTEXT_CHANGED"
    assert journal.execution_record(request.correlation_identity)["state"] == "RESULT_UNKNOWN"
    text = Path(config(tmp_path).journal_path).read_text(encoding="utf-8")
    assert '"record_type": "RECONCILIATION"' not in text


def test_stale_reserved_is_abandoned_without_broker_query(tmp_path):
    client = FakeReconciliationClient(unique_evidence())
    payload, _, _, journal, _ = reconcile(tmp_path, client, state="RESERVED")
    assert payload["resulting_execution_state"] == "RESERVATION_ABANDONED"
    assert payload["retry_decision"] == "NEW_REQUEST_REQUIRED"
    assert client.query_calls == 0
    assert "RESERVATION_ABANDONED" in Path(journal.path).read_text(encoding="utf-8")
    assert journal.reserve("reconcile-idempotency-1", "new-request", ACCOUNT_A) is False


def test_stale_submission_started_becomes_unknown_then_reconciles(tmp_path):
    payload, _, _, journal, _ = reconcile(
        tmp_path, FakeReconciliationClient(), state="SUBMISSION_STARTED"
    )
    assert payload["original_execution_state"] == "SUBMISSION_STARTED"
    assert payload["resulting_execution_state"] == "RESULT_UNKNOWN"
    assert "STALE_SUBMISSION_STARTED" in Path(journal.path).read_text(encoding="utf-8")


def test_restart_persistence_reloads_terminal_reconciliation(tmp_path):
    client = FakeReconciliationClient(unique_evidence())
    payload, _, request, _, _ = reconcile(tmp_path, client)
    restarted = ControlledMT5ReconciliationService(
        client,
        config=config(tmp_path),
        journal=ProtectedExecutionJournal(config(tmp_path).journal_path),
    )
    repeated, _ = restarted.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert repeated == payload
    assert client.query_calls == 1


def test_same_reconciliation_request_is_idempotent(tmp_path):
    client = FakeReconciliationClient(unique_evidence())
    payload, _, request, _, service = reconcile(tmp_path, client)
    repeated, _ = service.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert repeated == payload
    assert client.query_calls == 1


def test_pending_reconciliation_resumes_after_restart(tmp_path):
    request, journal = seed_record(tmp_path)
    reference = ProtectedReconciliationRequest.from_payload(request.as_protected_dict()).reconciliation_reference()
    journal.begin_reconciliation(reference, request.correlation_identity)
    client = FakeReconciliationClient(unique_evidence())
    restarted = ControlledMT5ReconciliationService(
        client,
        config=config(tmp_path),
        journal=ProtectedExecutionJournal(config(tmp_path).journal_path),
    )
    payload, status = restarted.handle(request.as_protected_dict(), AUTH_TOKEN)
    assert status == 200
    assert payload["status"] == "CONFIRMED"
    assert client.query_calls == 1


def test_exact_broker_identifiers_are_protected_in_journal(tmp_path):
    payload, _, _, journal, _ = reconcile(tmp_path, FakeReconciliationClient(unique_evidence()))
    public = json.dumps(payload, sort_keys=True)
    protected = Path(journal.path).read_text(encoding="utf-8")
    for identifier in (ORDER_ID, DEAL_ID, POSITION_ID):
        assert str(identifier) not in public
        assert str(identifier) in protected


def test_public_receipt_is_redacted_and_non_executable(tmp_path):
    payload, _, _, _, _ = reconcile(tmp_path, FakeReconciliationClient(unique_evidence()))
    receipt = MT5ReconciliationReceipt.from_payload(payload)
    safe = receipt.to_safe_json()
    assert receipt.ticket is None and receipt.deal is None and receipt.position is None
    assert receipt.order_send_allowed is False
    assert receipt.automatic_retry_allowed is False
    assert str(ORDER_ID) not in safe and str(DEAL_ID) not in safe


def test_no_match_never_becomes_result_rejected(tmp_path):
    payload, _, _, journal, _ = reconcile(tmp_path, FakeReconciliationClient())
    assert payload["resulting_execution_state"] == "RESULT_UNKNOWN"
    assert '"state": "RESULT_REJECTED"' not in Path(journal.path).read_text(encoding="utf-8")


def test_result_unknown_never_authorizes_retry(tmp_path):
    for client in (
        FakeReconciliationClient(),
        FakeReconciliationClient(unique_evidence(extra=True)),
        FakeReconciliationClient(raise_query=True),
    ):
        child = tmp_path / str(client.query_calls) / str(id(client))
        child.mkdir(parents=True)
        payload, _, _, _, _ = reconcile(child, client)
        assert payload["retry_decision"] == "RETRY_PROHIBITED"
        assert payload["automatic_retry_allowed"] is False


def test_reconciliation_module_has_no_submission_call(tmp_path):
    reconcile(tmp_path, FakeReconciliationClient(unique_evidence()))
    text = Path("tools/mt5_bridge/reconciliation.py").read_text(encoding="utf-8")
    assert ".order_send(" not in text


def test_existing_production_submission_call_site_remains_exactly_one():
    production = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (Path("src"), Path("tools"))
        for path in root.rglob("*.py")
    )
    assert production.count(".order_send(") == 1
    assert "class DemoExecutionAdapter" not in production
    assert "class RealExecutionAdapter" not in production


def test_invalid_reconciliation_authentication_fails_before_query(tmp_path):
    request, journal = seed_record(tmp_path)
    client = FakeReconciliationClient(unique_evidence())
    service = ControlledMT5ReconciliationService(client, config=config(tmp_path), journal=journal)
    payload, status = service.handle(request.as_protected_dict(), "wrong-token")
    assert status == 401 and payload["reason"] == "AUTHENTICATION_FAILED"
    assert client.query_calls == 0


def test_reconciliation_integrity_mismatch_fails_before_query(tmp_path):
    request, journal = seed_record(tmp_path)
    client = FakeReconciliationClient(unique_evidence())
    service = ControlledMT5ReconciliationService(client, config=config(tmp_path), journal=journal)
    changed = request.as_protected_dict()
    changed["canonical_semantic_hash"] = "f" * 64
    payload, status = service.handle(changed, AUTH_TOKEN)
    assert status == 403 and payload["reason"] == "RECONCILIATION_INTEGRITY_MISMATCH"
    assert client.query_calls == 0

def test_automated_reconciliation_uses_fake_client_only(tmp_path):
    client = FakeReconciliationClient(unique_evidence())
    payload, _, _, _, service = reconcile(tmp_path, client)
    assert service.client is client
    assert payload["status"] == "CONFIRMED"
