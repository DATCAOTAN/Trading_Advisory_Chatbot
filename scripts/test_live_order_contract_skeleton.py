from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_order_contract import (
    LIVE_ORDER_CONTRACT_PARAMETER_GROUPS,
    LIVE_ORDER_CONTRACT_SKELETON_BLOCK_REASONS,
    LIVE_ORDER_CONTRACT_SKELETON_SCOPES,
    LIVE_ORDER_CONTRACT_SKELETON_STATUSES,
    REQUIRED_PARAMETER_GROUP_LABELS,
    LiveOrderContractSkeletonBuilder,
    LiveOrderContractSkeletonFormatter,
    LiveOrderContractSkeletonGate,
    LiveOrderContractSkeletonJournalStore,
    LiveOrderContractSkeletonPolicy,
    LiveOrderContractSkeletonService,
    LiveOrderContractSkeletonValidator,
)
from src.services.trading.execution.live_order_intent.models import LiveOrderIntent, LiveOrderIntentValidationReport
from src.services.trading.execution.permission.models import LivePermissionGateDecision
from src.services.trading.execution.preflight.models import LiveExecutionPreflightReadinessReport
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft


def _now(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _policy(tmp_path: Path | None = None, **kwargs) -> LiveOrderContractSkeletonPolicy:
    values = {"journal_path": str((tmp_path or Path("data")) / "live_order_contract_skeletons.jsonl")}
    values.update(kwargs)
    return LiveOrderContractSkeletonPolicy(**values)


def _order_intent(**kwargs) -> LiveOrderIntent:
    values = dict(
        intent_id="live_order_intent_test",
        created_at=_now().isoformat(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSD",
        status="CREATED_FOR_CONTRACT_WORKFLOW",
        scope="ORDER_CONTRACT_PREPARATION_ONLY",
        order_contract_workflow_allowed=True,
        live_execution_allowed=False,
        order_send_allowed=False,
        execution_allowed=False,
        hard_live_block_required=True,
        source_live_permission_intent_id="permission_intent_test",
        source_live_permission_decision_id="permission_decision_test",
        source_preflight_report_id="preflight_report_test",
        source_design_report_id="design_report_test",
        source_proposal_draft_id="draft_test",
        source_simulated_contract_id="sim_contract_test",
        source_simulated_receipt_id="sim_receipt_test",
        artifact_hash="artifact_hash_test",
        idempotency_key="live_order_intent_idempotency_test",
        expires_at=_now(300).isoformat(),
        permission_status="PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW",
        permission_scope="ORDER_INTENT_WORKFLOW_ONLY",
        preflight_status="PASS",
        proposal_draft_status="DRAFT_CREATED",
        simulated_contract_status="CREATED",
        source_refs=["feature:test", "intent:test"],
    )
    values.update(kwargs)
    return LiveOrderIntent(**values)


def _intent_validation(**kwargs) -> LiveOrderIntentValidationReport:
    values = dict(
        validation_report_id="live_order_intent_validation_test",
        created_at=_now().isoformat(),
        source_live_order_intent_id="live_order_intent_test",
        valid=True,
        order_contract_workflow_allowed=True,
        live_execution_allowed=False,
        order_send_allowed=False,
        execution_allowed=False,
        hard_live_block_required=True,
        validation_checks=[{"check_id": "workflow_allowed", "passed": True}],
        source_refs=["intent_validation:test"],
    )
    values.update(kwargs)
    return LiveOrderIntentValidationReport(**values)


def _permission_decision(**kwargs) -> LivePermissionGateDecision:
    values = dict(
        decision_id="permission_decision_test",
        created_at=_now().isoformat(),
        intent_id="permission_intent_test",
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
        source_refs=["permission:test"],
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
        total_checks=40,
        passed_checks=40,
        source_design_report_id="design_report_test",
        source_capability_report_id="capability_report_test",
        source_blocked_receipt_id="blocked_receipt_test",
        source_refs=["preflight:test"],
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


def _build(tmp_path: Path | None = None, **kwargs):
    values = dict(
        live_order_intent=_order_intent(),
        live_order_intent_validation=_intent_validation(),
        permission_decision=_permission_decision(),
        preflight_report=_preflight(),
        proposal_draft=_draft(),
        simulated_contract=_contract(),
        simulated_receipt=_receipt(),
    )
    values.update(kwargs)
    return LiveOrderContractSkeletonBuilder(_policy(tmp_path)).build(**values)


def test_status_scope_parameter_group_and_block_reason_values_exist():
    assert "SKELETON_CREATED" in LIVE_ORDER_CONTRACT_SKELETON_STATUSES
    assert "CONTRACT_PARAMETER_VALIDATION_ONLY" in LIVE_ORDER_CONTRACT_SKELETON_SCOPES
    assert set(REQUIRED_PARAMETER_GROUP_LABELS).issubset(LIVE_ORDER_CONTRACT_PARAMETER_GROUPS)
    assert "MISSING_LIVE_ORDER_INTENT" in LIVE_ORDER_CONTRACT_SKELETON_BLOCK_REASONS


def test_skeleton_validation_and_record_serialize_safely(tmp_path):
    result = LiveOrderContractSkeletonService(policy=_policy(tmp_path)).run(
        _order_intent(), _intent_validation(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt()
    )
    assert result.journal_record is not None
    for payload in [result.skeleton.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]:
        assert payload["live_execution_allowed"] is False
        assert payload["order_send_allowed"] is False
        assert payload["execution_allowed"] is False
        assert payload["executable"] is False
        assert payload["mt5_payload_created"] is False
        assert payload["order_sent"] is False
        json.dumps(payload)


def test_policy_defaults_and_requirements():
    policy = LiveOrderContractSkeletonPolicy()
    assert policy.enabled is True
    for field in [
        "require_live_order_intent",
        "require_valid_intent",
        "require_permission_decision",
        "require_preflight_pass",
        "require_proposal_draft",
        "require_non_executable_proposal_draft",
        "require_simulated_contract",
        "require_source_refs",
        "require_idempotency",
    ]:
        assert getattr(policy, field) is True


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"live_order_intent": None}, "MISSING_LIVE_ORDER_INTENT"),
        ({"live_order_intent_validation": None}, "MISSING_LIVE_ORDER_INTENT_VALIDATION"),
        ({"live_order_intent_validation": _intent_validation(valid=False)}, "MISSING_LIVE_ORDER_INTENT_VALIDATION"),
        ({"live_order_intent_validation": _intent_validation(order_contract_workflow_allowed=False)}, "ORDER_CONTRACT_WORKFLOW_NOT_ALLOWED"),
        ({"permission_decision": None}, "MISSING_PERMISSION_DECISION"),
        ({"preflight_report": _preflight(preflight_status="FAIL")}, "MISSING_PREFLIGHT_REPORT"),
        ({"proposal_draft": None}, "MISSING_PROPOSAL_DRAFT"),
        ({"proposal_draft": _draft(executable=True)}, "MISSING_PROPOSAL_DRAFT"),
        ({"proposal_draft": _draft(non_executable=False)}, "MISSING_PROPOSAL_DRAFT"),
        ({"simulated_contract": None}, "MISSING_SIMULATED_CONTRACT"),
        ({"simulated_contract": _contract(executable=True)}, "MISSING_SIMULATED_CONTRACT"),
        ({"live_order_intent": _order_intent(source_refs=[]), "live_order_intent_validation": _intent_validation(source_refs=[]), "permission_decision": _permission_decision(source_refs=[]), "preflight_report": _preflight(source_refs=[]), "proposal_draft": _draft(source_refs=[]), "simulated_contract": _contract(source_refs=[]), "simulated_receipt": _receipt(source_refs=[])}, "MISSING_SOURCE_REFS"),
        ({"live_order_intent": _order_intent(artifact_hash="", idempotency_key=""), "simulated_contract": _contract(artifact_hash="", idempotency_key=""), "simulated_receipt": _receipt(artifact_hash="", idempotency_key="")}, "MISSING_IDEMPOTENCY"),
    ],
)
def test_builder_blocks_invalid_inputs(tmp_path, kwargs, reason):
    skeleton = _build(tmp_path, **kwargs)
    assert skeleton.contract_parameter_validation_allowed is False
    assert reason in skeleton.blockers


def test_expired_and_duplicate_skeleton_block(tmp_path):
    old = _now(-600)
    expired = LiveOrderContractSkeletonBuilder(_policy(tmp_path, ttl_seconds=1)).build(
        _order_intent(created_at=old.isoformat()),
        _intent_validation(),
        _permission_decision(),
        _preflight(),
        _draft(),
        _contract(),
        current_time=_now(),
    )
    assert expired.status == "EXPIRED"
    first = _build(tmp_path)
    duplicate = _build(tmp_path, existing_idempotency_keys={first.idempotency_key})
    assert duplicate.status == "DUPLICATE"


def test_valid_skeleton_allows_parameter_validation_only(tmp_path):
    skeleton = _build(tmp_path)
    report = LiveOrderContractSkeletonGate(_policy(tmp_path)).validate(skeleton)
    assert skeleton.status == "SKELETON_CREATED"
    assert report.valid is True
    assert report.contract_parameter_validation_allowed is True
    assert not any([report.live_execution_allowed, report.order_send_allowed, report.execution_allowed])
    assert not any([report.executable, report.mt5_payload_created, report.order_sent])


def test_parameter_groups_are_labels_only_and_unresolved(tmp_path):
    skeleton = _build(tmp_path)
    assert skeleton.required_parameter_groups == REQUIRED_PARAMETER_GROUP_LABELS
    assert skeleton.missing_parameter_groups == REQUIRED_PARAMETER_GROUP_LABELS
    assert skeleton.resolved_parameter_groups == []


def test_store_appends_reads_summarizes_lookup_and_handles_corrupt_line(tmp_path):
    service = LiveOrderContractSkeletonService(policy=_policy(tmp_path))
    result = service.run(_order_intent(), _intent_validation(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt())
    store = LiveOrderContractSkeletonJournalStore(_policy(tmp_path).journal_path)
    assert len(store.read_latest()) == 1
    assert store.summarize().total_created == 1
    assert store.find_by_idempotency_key(result.skeleton.idempotency_key) is not None
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text("{bad json}\n", encoding="utf-8")
    corrupt_store = LiveOrderContractSkeletonJournalStore(corrupt)
    assert corrupt_store.read_latest() == []
    assert corrupt_store.warnings == ["corrupt_jsonl_line:1"]


def test_service_and_formatter(tmp_path):
    result = LiveOrderContractSkeletonService(policy=_policy(tmp_path)).run(
        _order_intent(), _intent_validation(), _permission_decision(), _preflight(), _draft(), _contract(), _receipt()
    )
    formatter = LiveOrderContractSkeletonFormatter()
    assert formatter.to_card(result.skeleton, result.validation_report).as_dict()["title"] == "Live Order Contract Skeleton"
    assert "Live Order Contract Skeleton" in formatter.to_markdown(result.skeleton, result.validation_report)


@pytest.mark.parametrize(
    "field,value,issue",
    [
        ("live_execution_allowed", True, "live_execution_allowed_must_be_false"),
        ("order_send_allowed", True, "order_send_allowed_must_be_false"),
        ("execution_allowed", True, "execution_allowed_must_be_false"),
        ("executable", True, "executable_must_be_false"),
        ("mt5_payload_created", True, "mt5_payload_created_must_be_false"),
        ("order_sent", True, "order_sent_must_be_false"),
        ("hard_live_block_required", False, "hard_live_block_required_must_be_true"),
        ("blockers", ["order" + "_send"], "order_submission_marker_present"),
        ("blockers", ["submit_live_order"], "live_method_marker_present"),
        ("blockers", ["executable_order"], "executable_order_marker_present"),
        ("blockers", ["mt5_ticket"], "mt5_ticket_marker_present"),
        ("blockers", ["trade_side"], "trade_side_marker_present"),
        ("blockers", ["side"], "raw_side_marker_present"),
        ("blockers", ["BUY"], "direction_marker_present"),
        ("blockers", ["SELL"], "direction_marker_present"),
        ("blockers", ["LONG"], "direction_marker_present"),
        ("blockers", ["SHORT"], "direction_marker_present"),
        ("blockers", ["entry_price"], "price_or_size_marker_present"),
        ("blockers", ["volume"], "price_or_size_marker_present"),
        ("blockers", ["position_size"], "price_or_size_marker_present"),
        ("blockers", ["raw_candles"], "raw_candle_marker_present"),
        ("blockers", ["full_raw_report"], "raw_knowledge_marker_present"),
        ("blockers", ["account_id"], "account_or_credential_marker_present"),
    ],
)
def test_validator_rejects_forbidden_values(tmp_path, field, value, issue):
    skeleton = _build(tmp_path)
    setattr(skeleton, field, value)
    issues = LiveOrderContractSkeletonValidator(_policy(tmp_path)).validate_skeleton(skeleton).issues
    assert issue in issues


def test_validator_rejects_invalid_parameter_groups(tmp_path):
    skeleton = _build(tmp_path)
    skeleton.required_parameter_groups = ["side"]
    skeleton.missing_parameter_groups = ["PRICE_POLICY"]
    skeleton.resolved_parameter_groups = ["SIDE_POLICY"]
    issues = LiveOrderContractSkeletonValidator(_policy(tmp_path)).validate_skeleton(skeleton).issues
    assert "required_parameter_groups_labels_only" in issues
    assert "resolved_parameter_groups_must_be_empty" in issues


def test_dashboard_ui_has_only_safe_contract_skeleton_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Live Order Contract Skeleton" in text
    assert "future parameter validation" in text
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
