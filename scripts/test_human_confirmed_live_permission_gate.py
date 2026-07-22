from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_design import LiveExecutionDesignPolicy, LiveExecutionReadinessSpecReportBuilder
from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport
from src.services.trading.execution.permission import (
    LIVE_PERMISSION_BLOCK_REASONS,
    LIVE_PERMISSION_CONFIRMATION_STATES,
    LIVE_PERMISSION_SCOPES,
    LIVE_PERMISSION_STATUSES,
    LivePermissionConfirmationService,
    LivePermissionGate,
    LivePermissionGateDecision,
    LivePermissionGateFormatter,
    LivePermissionGateService,
    LivePermissionGateValidator,
    LivePermissionIntent,
    LivePermissionIntentBuilder,
    LivePermissionJournalRecord,
    LivePermissionJournalStore,
    LivePermissionPolicy,
)
from src.services.trading.execution.preflight import LiveExecutionPreflightHarness, LiveExecutionPreflightPolicy
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft


SOURCE_REF = "permission://source/ref"


def _capability() -> LiveExecutionCapabilityReport:
    return LiveExecutionCapabilityReport(
        report_id="capability_1",
        created_at="2026-07-17T00:00:00+00:00",
        source_contract_id="contract_1",
        source_simulated_receipt_id="sim_receipt_1",
        source_draft_id="draft_1",
        source_refs=[SOURCE_REF],
    )


def _blocked_receipt() -> LiveExecutionBlockedReceipt:
    return LiveExecutionBlockedReceipt(
        receipt_id="blocked_1",
        created_at="2026-07-17T00:00:01+00:00",
        source_contract_id="contract_1",
        source_simulated_receipt_id="sim_receipt_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _contract() -> SimulatedOrderContract:
    return SimulatedOrderContract(
        contract_id="contract_1",
        created_at="2026-07-17T00:00:02+00:00",
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        contract_status="CREATED",
        source_draft_id="draft_1",
        source_intent_id="intent_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _sim_receipt() -> SimulatedExecutionReceipt:
    return SimulatedExecutionReceipt(
        receipt_id="sim_receipt_1",
        created_at="2026-07-17T00:00:03+00:00",
        adapter_type="SIMULATED",
        contract_id="contract_1",
        contract_status="CREATED",
        source_draft_id="draft_1",
        source_contract_id="contract_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _draft() -> NonExecutableTradeProposalDraft:
    return NonExecutableTradeProposalDraft(
        draft_id="draft_1",
        created_at="2026-07-17T00:00:04+00:00",
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        status="DRAFT_CREATED",
        source_refs=[SOURCE_REF],
    )


def _design_report():
    policy = LiveExecutionDesignPolicy(
        journal_enabled=False,
        min_critical_threats=5,
        min_preflight_checks=10,
        min_approval_requirements=8,
        min_failure_modes=8,
        min_audit_requirements=8,
    )
    return LiveExecutionReadinessSpecReportBuilder(policy).build(
        _capability(),
        _blocked_receipt(),
        _contract(),
        _sim_receipt(),
    )


def _preflight_report(tmp_path: Path | None = None):
    policy = LiveExecutionPreflightPolicy(journal_path=str((tmp_path or Path("unused")).joinpath("preflight.jsonl")))
    return LiveExecutionPreflightHarness(policy).build(
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        simulated_receipt=_sim_receipt(),
        live_block_journal_record=object(),
    )


def _policy(tmp_path: Path | None = None, **kwargs) -> LivePermissionPolicy:
    values = {"journal_path": str((tmp_path or Path("unused")).joinpath("permission.jsonl"))}
    values.update(kwargs)
    return LivePermissionPolicy(**values)


def _intent(tmp_path: Path | None = None, **kwargs) -> LivePermissionIntent:
    policy = _policy(tmp_path)
    values = {
        "preflight_report": _preflight_report(tmp_path),
        "design_report": _design_report(),
        "capability_report": _capability(),
        "blocked_receipt": _blocked_receipt(),
        "simulated_contract": _contract(),
        "proposal_draft": _draft(),
        "user_acknowledgement_text": policy.confirmation_phrase,
        "current_time": datetime.now(timezone.utc),
    }
    values.update(kwargs)
    return LivePermissionIntentBuilder(policy).build(**values)


def _decision(tmp_path: Path | None = None) -> LivePermissionGateDecision:
    return LivePermissionGate(_policy(tmp_path)).decide(_intent(tmp_path))


@pytest.mark.parametrize(
    "value",
    [
        "NOT_REQUESTED",
        "READY_FOR_PERMISSION",
        "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        "BLOCKED",
        "EXPIRED",
        "DUPLICATE",
        "INVALID",
        "UNKNOWN",
    ],
)
def test_live_permission_status_values_exist(value):
    assert value in LIVE_PERMISSION_STATUSES


@pytest.mark.parametrize("value", ["ORDER_INTENT_WORKFLOW_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"])
def test_live_permission_scope_values_exist(value):
    assert value in LIVE_PERMISSION_SCOPES


@pytest.mark.parametrize("value", ["NOT_CONFIRMED", "CONFIRMED_PERMISSION_GATE_ONLY", "REJECTED", "EXPIRED", "UNKNOWN"])
def test_live_permission_confirmation_state_values_exist(value):
    assert value in LIVE_PERMISSION_CONFIRMATION_STATES


@pytest.mark.parametrize(
    "value",
    [
        "PREFLIGHT_NOT_PASS",
        "MISSING_PREFLIGHT_REPORT",
        "MISSING_DESIGN_REPORT",
        "MISSING_HARD_BLOCK_RECEIPT",
        "MISSING_SOURCE_REFS",
        "MISSING_IDEMPOTENCY",
        "MISSING_CONFIRMATION_PHRASE",
        "WRONG_CONFIRMATION_PHRASE",
        "EXPIRED_PERMISSION_REQUEST",
        "DUPLICATE_PERMISSION_REQUEST",
        "LIVE_EXECUTION_STILL_DISABLED",
        "ORDER_SEND_STILL_FORBIDDEN",
        "FORBIDDEN_EXECUTION_MARKER",
        "INVALID_INPUT",
        "UNKNOWN",
    ],
)
def test_live_permission_block_reason_values_exist(value):
    assert value in LIVE_PERMISSION_BLOCK_REASONS


def test_live_permission_intent_serializes_safely(tmp_path):
    assert json.dumps(_intent(tmp_path).as_dict())


def test_live_permission_gate_decision_serializes_safely(tmp_path):
    assert json.dumps(_decision(tmp_path).as_dict())


def test_live_permission_journal_record_serializes_safely():
    record = LivePermissionJournalRecord(
        "j",
        "2026-07-17T00:00:00+00:00",
        "LIVE_PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        "intent",
        "decision",
        "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        "ORDER_INTENT_WORKFLOW_ONLY",
        "CONFIRMED_PERMISSION_GATE_ONLY",
        True,
        False,
        False,
        False,
        True,
        "hash",
        "idem",
        "preflight",
        "design",
        [SOURCE_REF],
    )
    assert json.dumps(record.as_dict())


def test_policy_defaults_permission_gate_enabled():
    assert LivePermissionPolicy.from_config().enabled is True


@pytest.mark.parametrize("attr", ["require_preflight_pass", "require_hard_block", "require_source_refs", "require_idempotency"])
def test_policy_required_defaults(attr):
    assert getattr(LivePermissionPolicy.from_config(), attr) is True


def test_confirmation_phrase_is_exposed():
    assert LivePermissionConfirmationService().required_phrase()


@pytest.mark.parametrize(
    "phrase, state, reason",
    [
        ("", "NOT_CONFIRMED", "MISSING_CONFIRMATION_PHRASE"),
        ("yes", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("confirm", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("execute", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("trade now", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("place order", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("buy", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
        ("sell", "REJECTED", "WRONG_CONFIRMATION_PHRASE"),
    ],
)
def test_wrong_or_vague_phrase_blocks(phrase, state, reason):
    result = LivePermissionConfirmationService().evaluate(phrase)
    assert result.confirmation_state == state
    assert result.block_reason == reason


def test_correct_phrase_confirms_permission_gate_only():
    service = LivePermissionConfirmationService()
    result = service.evaluate(service.required_phrase())
    assert result.confirmation_state == "CONFIRMED_PERMISSION_GATE_ONLY"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"preflight_report": None}, "MISSING_PREFLIGHT_REPORT"),
        ({"design_report": None}, "MISSING_DESIGN_REPORT"),
        ({"capability_report": None}, "INVALID_INPUT"),
        ({"blocked_receipt": None}, "MISSING_HARD_BLOCK_RECEIPT"),
    ],
)
def test_missing_required_sources_block(tmp_path, kwargs, expected):
    intent = _intent(tmp_path, **kwargs)
    assert expected in intent.blockers
    assert intent.order_intent_workflow_allowed is False


def test_preflight_not_pass_blocks(tmp_path):
    preflight = _preflight_report(tmp_path)
    preflight.preflight_status = "FAIL"
    intent = _intent(tmp_path, preflight_report=preflight)
    assert "PREFLIGHT_NOT_PASS" in intent.blockers


def test_missing_hard_block_blocks(tmp_path):
    preflight = _preflight_report(tmp_path)
    preflight.hard_live_block_required = False
    intent = _intent(tmp_path, preflight_report=preflight)
    assert "LIVE_EXECUTION_STILL_DISABLED" in intent.blockers


def test_missing_source_refs_blocks(tmp_path):
    preflight = _preflight_report(tmp_path)
    preflight.source_refs = []
    design = _design_report()
    design.source_refs = []
    receipt = _blocked_receipt()
    receipt.source_refs = []
    intent = _intent(tmp_path, preflight_report=preflight, design_report=design, blocked_receipt=receipt, simulated_contract=None, proposal_draft=None)
    assert "MISSING_SOURCE_REFS" in intent.blockers


def test_missing_idempotency_blocks(tmp_path):
    receipt = _blocked_receipt()
    receipt.artifact_hash = ""
    receipt.idempotency_key = ""
    contract = _contract()
    contract.artifact_hash = ""
    contract.idempotency_key = ""
    intent = _intent(tmp_path, blocked_receipt=receipt, simulated_contract=contract)
    assert "MISSING_IDEMPOTENCY" in intent.blockers


def test_expired_permission_request_blocks(tmp_path):
    preflight = _preflight_report(tmp_path)
    preflight.created_at = "2026-07-17T00:00:00+00:00"
    now = datetime(2026, 7, 17, 0, 10, tzinfo=timezone.utc)
    intent = _intent(tmp_path, preflight_report=preflight, current_time=now)
    assert intent.permission_status == "EXPIRED"
    assert "EXPIRED_PERMISSION_REQUEST" in intent.blockers


def test_duplicate_permission_request_blocks(tmp_path):
    intent = LivePermissionIntentBuilder(_policy(tmp_path)).build(
        _preflight_report(tmp_path),
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        proposal_draft=_draft(),
        user_acknowledgement_text=_policy(tmp_path).confirmation_phrase,
        existing_idempotency_keys={"idem_key"},
    )
    assert intent.permission_status == "DUPLICATE"


def test_valid_inputs_create_intent_with_order_intent_workflow_allowed_true(tmp_path):
    intent = _intent(tmp_path)
    assert intent.permission_status == "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW"
    assert intent.order_intent_workflow_allowed is True


def test_intent_forced_flags(tmp_path):
    intent = _intent(tmp_path)
    assert intent.live_execution_allowed is False
    assert intent.order_send_allowed is False
    assert intent.execution_allowed is False
    assert intent.hard_live_block_required is True


def test_gate_allowed_only_enables_order_intent_workflow(tmp_path):
    decision = _decision(tmp_path)
    assert decision.gate_allowed is True
    assert decision.order_intent_workflow_allowed is True
    assert decision.live_execution_allowed is False
    assert decision.order_send_allowed is False
    assert decision.execution_allowed is False


def test_journal_store_appends_jsonl(tmp_path):
    store = LivePermissionJournalStore(tmp_path / "permission.jsonl")
    result = LivePermissionGateService(_policy(tmp_path), store=store).run(
        _preflight_report(tmp_path),
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        proposal_draft=_draft(),
        user_acknowledgement_text=_policy(tmp_path).confirmation_phrase,
    )
    assert result.journal_record is not None
    assert store.path.exists()


def test_journal_store_reads_latest_records(tmp_path):
    store = LivePermissionJournalStore(tmp_path / "permission.jsonl")
    service = LivePermissionGateService(_policy(tmp_path), store=store)
    service.run(_preflight_report(tmp_path), _design_report(), _capability(), _blocked_receipt(), _contract(), _draft(), _policy(tmp_path).confirmation_phrase)
    assert store.read_latest()


def test_journal_store_summarizes_records(tmp_path):
    store = LivePermissionJournalStore(tmp_path / "permission.jsonl")
    service = LivePermissionGateService(_policy(tmp_path), store=store)
    service.run(_preflight_report(tmp_path), _design_report(), _capability(), _blocked_receipt(), _contract(), _draft(), _policy(tmp_path).confirmation_phrase)
    assert store.summarize().total_records == 1


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    path = tmp_path / "permission.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = LivePermissionJournalStore(path)
    assert store.read_latest() == []
    assert store.warnings


def test_service_builds_intent_decision_and_journal_record(tmp_path):
    store = LivePermissionJournalStore(tmp_path / "permission.jsonl")
    result = LivePermissionGateService(_policy(tmp_path), store=store).run(
        _preflight_report(tmp_path),
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        proposal_draft=_draft(),
        user_acknowledgement_text=_policy(tmp_path).confirmation_phrase,
    )
    assert result.intent.intent_id
    assert result.decision.decision_id
    assert result.journal_record is not None


def test_formatter_creates_json_safe_card(tmp_path):
    intent = _intent(tmp_path)
    decision = LivePermissionGate(_policy(tmp_path)).decide(intent)
    assert json.dumps(LivePermissionGateFormatter().to_card(intent, decision).as_dict())


def test_formatter_creates_markdown_summary(tmp_path):
    intent = _intent(tmp_path)
    decision = LivePermissionGate(_policy(tmp_path)).decide(intent)
    markdown = LivePermissionGateFormatter().to_markdown(intent, decision)
    assert "Permission gate only" in markdown
    assert "live_execution_allowed: false" in markdown


@pytest.mark.parametrize(
    "field, value, issue",
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
        ("blockers", ["full_raw_book"], "raw_knowledge_marker_present"),
        ("blockers", ["account_id"], "account_or_credential_marker_present"),
    ],
)
def test_validator_rejects_forbidden_or_invalid_flags(tmp_path, field, value, issue):
    intent = _intent(tmp_path)
    setattr(intent, field, value)
    result = LivePermissionGateValidator(_policy(tmp_path)).validate_intent(intent)
    assert issue in result.issues


def test_dashboard_ui_code_does_not_add_forbidden_buttons():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8", errors="ignore")
    for label in ["Confirm Trade", "Execute Trade", "Place Order", "Buy", "Sell"]:
        assert f'st.button("{label}"' not in text
        assert f"st.button('{label}'" not in text


def test_dashboard_ui_labels_permission_as_order_intent_preparation_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8", errors="ignore")
    assert "Confirm Live Order Intent Preparation" in text
    assert "only permits live order intent preparation" in text
    assert "Live execution remains disabled" in text


def test_no_order_endpoints_added_to_mt5_bridge_server():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8", errors="ignore")
    for marker in ["/order", "/execute", "/send" + "_order", "/order" + "_send", "/trade", "/position/open"]:
        assert marker not in text
    for endpoint in ["/execution/write-skeleton/check", "/execution/controlled-submit", "/execution/reconcile"]:
        assert endpoint in text
    assert "def do_POST" in text


def test_unit_fixtures_do_not_call_live_external_services():
    text = Path(__file__).read_text(encoding="utf-8", errors="ignore")
    assert "MT5BridgeMarketData" + "Provider(" not in text
    assert "ForexFactoryCalendar" + "Provider(" not in text
    assert "Open" + "AI(" not in text
    assert "requests." + "get(" not in text


def test_no_qdrant_reset_or_rag_redesign_markers():
    text = Path(__file__).read_text(encoding="utf-8", errors="ignore")
    assert "delete_" + "collection" not in text
    assert "recreate_" + "collection" not in text
