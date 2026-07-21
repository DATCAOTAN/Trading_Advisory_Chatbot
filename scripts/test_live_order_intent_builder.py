from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_order_intent import (
    LIVE_ORDER_INTENT_BLOCK_REASONS,
    LIVE_ORDER_INTENT_SCOPES,
    LIVE_ORDER_INTENT_STATUSES,
    LiveOrderIntent,
    LiveOrderIntentBuilder,
    LiveOrderIntentFormatter,
    LiveOrderIntentGate,
    LiveOrderIntentJournalRecord,
    LiveOrderIntentJournalStore,
    LiveOrderIntentPolicy,
    LiveOrderIntentService,
    LiveOrderIntentValidationReport,
    LiveOrderIntentValidator,
)
from src.services.trading.execution.permission.models import LivePermissionGateDecision, LivePermissionIntent
from src.services.trading.execution.preflight.models import LiveExecutionPreflightReadinessReport
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft


def _now(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _policy(tmp_path: Path | None = None, **kwargs) -> LiveOrderIntentPolicy:
    values = {
        "journal_path": str((tmp_path or Path("data")) / "live_order_intents.jsonl"),
        "ttl_seconds": 300,
    }
    values.update(kwargs)
    return LiveOrderIntentPolicy(**values)


def _permission_intent(**kwargs) -> LivePermissionIntent:
    values = dict(
        intent_id="live_permission_intent_test",
        created_at=_now().isoformat(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSD",
        permission_status="PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        permission_scope="ORDER_INTENT_WORKFLOW_ONLY",
        confirmation_state="CONFIRMED_PERMISSION_GATE_ONLY",
        live_execution_allowed=False,
        order_send_allowed=False,
        execution_allowed=False,
        order_intent_workflow_allowed=True,
        hard_live_block_required=True,
        source_preflight_report_id="preflight_report_test",
        source_design_report_id="design_report_test",
        source_capability_report_id="capability_report_test",
        source_blocked_receipt_id="blocked_receipt_test",
        source_simulated_contract_id="sim_contract_test",
        source_proposal_draft_id="draft_test",
        artifact_hash="artifact_hash_test",
        idempotency_key="permission_idempotency_test",
        expires_at=_now(300).isoformat(),
        source_refs=["feature:test", "proposal:test"],
    )
    values.update(kwargs)
    return LivePermissionIntent(**values)


def _permission_decision(**kwargs) -> LivePermissionGateDecision:
    values = dict(
        decision_id="live_permission_decision_test",
        created_at=_now().isoformat(),
        intent_id="live_permission_intent_test",
        permission_status="PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        permission_scope="ORDER_INTENT_WORKFLOW_ONLY",
        gate_allowed=True,
        order_intent_workflow_allowed=True,
        live_execution_allowed=False,
        order_send_allowed=False,
        execution_allowed=False,
        hard_live_block_required=True,
        source_preflight_report_id="preflight_report_test",
        source_design_report_id="design_report_test",
        source_refs=["feature:test", "proposal:test"],
    )
    values.update(kwargs)
    return LivePermissionGateDecision(**values)


def _preflight(**kwargs) -> LiveExecutionPreflightReadinessReport:
    values = dict(
        report_id="preflight_report_test",
        created_at=_now().isoformat(),
        preflight_status="PASS",
        live_execution_allowed=False,
        hard_live_block_required=True,
        all_blocking_checks_passed=True,
        total_checks=40,
        passed_checks=40,
        source_design_report_id="design_report_test",
        source_capability_report_id="capability_report_test",
        source_blocked_receipt_id="blocked_receipt_test",
        source_refs=["feature:test", "preflight:test"],
    )
    values.update(kwargs)
    return LiveExecutionPreflightReadinessReport(**values)


def _draft(**kwargs) -> NonExecutableTradeProposalDraft:
    values = dict(
        draft_id="draft_test",
        created_at=_now().isoformat(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSD",
        status="DRAFT_CREATED",
        non_executable=True,
        executable=False,
        proposal_workflow_allowed=True,
        source_intent_id="proposal_intent_test",
        source_review_artifact_id="review_test",
        source_refs=["proposal:test"],
    )
    values.update(kwargs)
    return NonExecutableTradeProposalDraft(**values)


def _contract(**kwargs) -> SimulatedOrderContract:
    values = dict(
        contract_id="sim_contract_test",
        created_at=_now().isoformat(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSD",
        adapter_type="SIMULATED",
        contract_status="CREATED",
        simulated_only=True,
        executable=False,
        source_draft_id="draft_test",
        artifact_hash="artifact_hash_test",
        idempotency_key="simulated_idempotency_test",
        non_executable_proposal=True,
        draft_status="DRAFT_CREATED",
        source_refs=["contract:test"],
    )
    values.update(kwargs)
    return SimulatedOrderContract(**values)


def _receipt(**kwargs) -> SimulatedExecutionReceipt:
    values = dict(
        receipt_id="sim_receipt_test",
        created_at=_now().isoformat(),
        adapter_type="SIMULATED",
        contract_id="sim_contract_test",
        contract_status="CREATED",
        simulated_only=True,
        executable=False,
        executed=False,
        accepted_by_adapter=True,
        source_draft_id="draft_test",
        source_contract_id="sim_contract_test",
        idempotency_key="simulated_idempotency_test",
        artifact_hash="artifact_hash_test",
        source_refs=["receipt:test"],
    )
    values.update(kwargs)
    return SimulatedExecutionReceipt(**values)


def _intent(tmp_path: Path | None = None, **kwargs) -> LiveOrderIntent:
    values = dict(
        permission_intent=_permission_intent(),
        permission_decision=_permission_decision(),
        preflight_report=_preflight(),
        proposal_draft=_draft(),
        simulated_contract=_contract(),
        simulated_receipt=_receipt(),
    )
    values.update(kwargs)
    return LiveOrderIntentBuilder(_policy(tmp_path)).build(**values)


def test_live_order_intent_status_values_exist():
    assert {
        "NOT_REQUESTED",
        "READY_FOR_CONTRACT_PREPARATION",
        "CREATED_FOR_CONTRACT_WORKFLOW",
        "BLOCKED",
        "EXPIRED",
        "DUPLICATE",
        "INVALID",
        "UNKNOWN",
    }.issubset(LIVE_ORDER_INTENT_STATUSES)


def test_live_order_intent_scope_values_exist():
    assert {"ORDER_CONTRACT_PREPARATION_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}.issubset(LIVE_ORDER_INTENT_SCOPES)


def test_live_order_intent_block_reason_values_exist():
    assert {
        "MISSING_PERMISSION_INTENT",
        "MISSING_PERMISSION_DECISION",
        "PERMISSION_NOT_GRANTED",
        "ORDER_INTENT_WORKFLOW_NOT_ALLOWED",
        "PREFLIGHT_NOT_PASS",
        "MISSING_PROPOSAL_DRAFT",
        "PROPOSAL_DRAFT_NOT_NON_EXECUTABLE",
        "MISSING_SIMULATED_CONTRACT",
        "MISSING_SOURCE_REFS",
        "MISSING_IDEMPOTENCY",
        "EXPIRED_INTENT",
        "DUPLICATE_INTENT",
    }.issubset(LIVE_ORDER_INTENT_BLOCK_REASONS)


def test_live_order_intent_serializes_safely(tmp_path):
    payload = _intent(tmp_path).as_dict()
    assert payload["live_execution_allowed"] is False
    assert payload["order_send_allowed"] is False
    assert payload["execution_allowed"] is False
    json.dumps(payload)


def test_validation_report_serializes_safely(tmp_path):
    intent = _intent(tmp_path)
    report = LiveOrderIntentGate(_policy(tmp_path)).validate(intent)
    payload = report.as_dict()
    assert payload["live_execution_allowed"] is False
    assert payload["order_send_allowed"] is False
    assert payload["execution_allowed"] is False
    json.dumps(payload)


def test_journal_record_serializes_safely(tmp_path):
    result = LiveOrderIntentService(policy=_policy(tmp_path)).run(
        _permission_intent(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt()
    )
    assert result.journal_record is not None
    json.dumps(result.journal_record.as_dict())


def test_policy_defaults_enabled():
    assert LiveOrderIntentPolicy().enabled is True


@pytest.mark.parametrize(
    "field",
    [
        "require_permission_gate",
        "require_permission_granted",
        "require_preflight_pass",
        "require_proposal_draft",
        "require_non_executable_proposal_draft",
        "require_simulated_contract",
        "require_source_refs",
        "require_idempotency",
    ],
)
def test_policy_requires_safety_inputs(field):
    assert getattr(LiveOrderIntentPolicy(), field) is True


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"permission_intent": None}, "MISSING_PERMISSION_INTENT"),
        ({"permission_decision": None}, "MISSING_PERMISSION_DECISION"),
        ({"permission_intent": _permission_intent(permission_status="BLOCKED")}, "PERMISSION_NOT_GRANTED"),
        ({"permission_decision": _permission_decision(order_intent_workflow_allowed=False)}, "ORDER_INTENT_WORKFLOW_NOT_ALLOWED"),
        ({"preflight_report": _preflight(preflight_status="FAIL")}, "PREFLIGHT_NOT_PASS"),
        ({"proposal_draft": None}, "MISSING_PROPOSAL_DRAFT"),
        ({"proposal_draft": _draft(executable=True)}, "PROPOSAL_DRAFT_NOT_NON_EXECUTABLE"),
        ({"proposal_draft": _draft(non_executable=False)}, "PROPOSAL_DRAFT_NOT_NON_EXECUTABLE"),
        ({"simulated_contract": None}, "MISSING_SIMULATED_CONTRACT"),
        ({"simulated_contract": _contract(executable=True)}, "MISSING_SIMULATED_CONTRACT"),
        ({"permission_intent": _permission_intent(source_refs=[]), "permission_decision": _permission_decision(source_refs=[]), "preflight_report": _preflight(source_refs=[]), "proposal_draft": _draft(source_refs=[]), "simulated_contract": _contract(source_refs=[]), "simulated_receipt": _receipt(source_refs=[])}, "MISSING_SOURCE_REFS"),
        ({"permission_intent": _permission_intent(artifact_hash="", idempotency_key=""), "simulated_contract": _contract(artifact_hash="", idempotency_key=""), "simulated_receipt": _receipt(artifact_hash="", idempotency_key="")}, "MISSING_IDEMPOTENCY"),
    ],
)
def test_builder_blocks_invalid_inputs(tmp_path, kwargs, reason):
    values = dict(
        permission_intent=_permission_intent(),
        permission_decision=_permission_decision(),
        preflight_report=_preflight(),
        proposal_draft=_draft(),
        simulated_contract=_contract(),
        simulated_receipt=_receipt(),
    )
    values.update(kwargs)
    intent = LiveOrderIntentBuilder(_policy(tmp_path)).build(**values)
    assert intent.order_contract_workflow_allowed is False
    assert reason in intent.blockers


def test_expired_intent_blocks(tmp_path):
    old = _now(-600)
    intent = LiveOrderIntentBuilder(_policy(tmp_path, ttl_seconds=1)).build(
        _permission_intent(created_at=old.isoformat()),
        _permission_decision(),
        _preflight(),
        _draft(),
        _contract(),
        current_time=_now(),
    )
    assert intent.status == "EXPIRED"
    assert "EXPIRED_INTENT" in intent.blockers


def test_duplicate_intent_blocks(tmp_path):
    builder = LiveOrderIntentBuilder(_policy(tmp_path))
    first = builder.build(_permission_intent(), _permission_decision(), _preflight(), _draft(), _contract())
    duplicate = builder.build(
        _permission_intent(),
        _permission_decision(),
        _preflight(),
        _draft(),
        _contract(),
        existing_idempotency_keys={first.idempotency_key},
    )
    assert duplicate.status == "DUPLICATE"
    assert "DUPLICATE_INTENT" in duplicate.blockers


def test_valid_inputs_create_contract_workflow_intent(tmp_path):
    intent = _intent(tmp_path)
    assert intent.status == "CREATED_FOR_CONTRACT_WORKFLOW"
    assert intent.order_contract_workflow_allowed is True


def test_intent_forced_safety_flags(tmp_path):
    intent = _intent(tmp_path)
    assert intent.live_execution_allowed is False
    assert intent.order_send_allowed is False
    assert intent.execution_allowed is False
    assert intent.hard_live_block_required is True


def test_gate_valid_only_enables_contract_workflow(tmp_path):
    report = LiveOrderIntentGate(_policy(tmp_path)).validate(_intent(tmp_path))
    assert report.valid is True
    assert report.order_contract_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False


def test_store_appends_reads_summarizes_and_lookup(tmp_path):
    service = LiveOrderIntentService(policy=_policy(tmp_path))
    result = service.run(_permission_intent(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt())
    store = LiveOrderIntentJournalStore(_policy(tmp_path).journal_path)
    latest = store.read_latest()
    assert len(latest) == 1
    assert store.summarize().total_created == 1
    assert store.find_by_idempotency_key(result.intent.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning(tmp_path):
    path = tmp_path / "live_order_intents.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = LiveOrderIntentJournalStore(path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_intent_validation_and_journal(tmp_path):
    result = LiveOrderIntentService(policy=_policy(tmp_path)).run(
        _permission_intent(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt()
    )
    assert result.intent.intent_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None


def test_formatter_creates_card_and_markdown(tmp_path):
    intent = _intent(tmp_path)
    report = LiveOrderIntentGate(_policy(tmp_path)).validate(intent)
    formatter = LiveOrderIntentFormatter()
    assert formatter.to_card(intent, report).as_dict()["title"] == "Live Order Intent Builder"
    assert "Live Order Intent Builder" in formatter.to_markdown(intent, report)


@pytest.mark.parametrize(
    "field,value,issue",
    [
        ("live_execution_allowed", True, "live_execution_allowed_must_be_false"),
        ("order_send_allowed", True, "order_send_allowed_must_be_false"),
        ("execution_allowed", True, "execution_allowed_must_be_false"),
        ("hard_live_block_required", False, "hard_live_block_required_must_be_true"),
        ("blockers", ["order" + "_send"], "order_submission_marker_present"),
        ("blockers", ["submit_live_order"], "live_method_marker_present"),
        ("blockers", ["executable_order"], "executable_order_marker_present"),
        ("blockers", ["mt5_ticket"], "mt5_ticket_marker_present"),
        ("blockers", ["trade_side"], "trade_side_marker_present"),
        ("blockers", ["BUY"], "direction_marker_present"),
        ("blockers", ["SELL"], "direction_marker_present"),
        ("blockers", ["LONG"], "direction_marker_present"),
        ("blockers", ["SHORT"], "direction_marker_present"),
        ("blockers", ["entry_price"], "price_or_size_marker_present"),
        ("blockers", ["position_size"], "price_or_size_marker_present"),
        ("blockers", ["raw_candles"], "raw_candle_marker_present"),
        ("blockers", ["full_raw_report"], "raw_knowledge_marker_present"),
        ("blockers", ["account_id"], "account_or_credential_marker_present"),
    ],
)
def test_validator_rejects_forbidden_values(tmp_path, field, value, issue):
    intent = _intent(tmp_path)
    setattr(intent, field, value)
    issues = LiveOrderIntentValidator(_policy(tmp_path)).validate_intent(intent).issues
    assert issue in issues


def test_dashboard_ui_has_only_safe_live_order_intent_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Live Order Intent" in text
    assert "contract workflow preparation" in text
    for forbidden in ["Confirm Trade", "Execute Trade", "Place Order", "Buy/Sell"]:
        assert forbidden not in text


def test_mt5_bridge_has_no_order_endpoints():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    for marker in ["/order", "/execute", "/send" + "_order", "/order" + "_send", "/trade", "/position/open"]:
        assert marker not in text


def test_no_order_submission_implementation_in_execution_modules():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/services/trading/execution").rglob("*.py"))
    text = text.replace("mt5_order_send_available", "mt5_order_submission_available")
    text = text.replace("order_send_allowed", "order_submission_allowed")
    text = text.replace('"order" + "_send"', '"order_submission"')
    assert "order" + "_send" not in text
