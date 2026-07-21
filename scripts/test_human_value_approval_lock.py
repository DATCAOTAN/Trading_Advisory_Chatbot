from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_controlled_live_parameter_value_proposal import _inputs as _proposal_inputs
from src.services.trading.execution.live_parameter_value_proposal import (
    ControlledLiveParameterValueProposalConfig,
    ControlledLiveParameterValueProposalService,
)
from src.services.trading.execution.live_value_approval_lock import (
    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    HUMAN_VALUE_APPROVAL_ACTIONS,
    HUMAN_VALUE_APPROVAL_LOCK_BLOCK_REASONS,
    HUMAN_VALUE_APPROVAL_LOCK_SCOPES,
    HUMAN_VALUE_APPROVAL_LOCK_STATUSES,
    HUMAN_VALUE_APPROVAL_REVIEW_STATES,
    HUMAN_VALUE_APPROVAL_SLOT_LOCK_STATUSES,
    HUMAN_VALUE_LOCK_STATES,
    REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES,
    HumanValueApprovalConfirmationService,
    HumanValueApprovalLockConfig,
    HumanValueApprovalLockFormatter,
    HumanValueApprovalLockGate,
    HumanValueApprovalLockJournalStore,
    HumanValueApprovalLockService,
    HumanValueApprovalLockValidator,
    HumanValueApprovalSlotLockBuilder,
)


def _proposal_config(tmp_path: Path | None = None) -> ControlledLiveParameterValueProposalConfig:
    return ControlledLiveParameterValueProposalConfig(
        journal_path=str((tmp_path or Path("data")) / "controlled_live_parameter_value_proposals.jsonl"),
        journal_enabled=False,
    )


def _config(tmp_path: Path | None = None, **kwargs) -> HumanValueApprovalLockConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "human_value_approval_locks.jsonl")}
    values.update(kwargs)
    return HumanValueApprovalLockConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _proposal_inputs(tmp_path)
    proposal_result = ControlledLiveParameterValueProposalService(config=_proposal_config(tmp_path)).run(**sources)
    values = dict(
        value_proposal=proposal_result.proposal,
        value_proposal_validation=proposal_result.validation_report,
        parameter_draft=sources["parameter_draft"],
        parameter_draft_validation=sources["parameter_draft_validation"],
        parameter_source_boundary=sources["parameter_source_boundary"],
        parameter_source_validation=sources["parameter_source_validation"],
        parameter_policy_spec=sources["parameter_policy_spec"],
        parameter_policy_validation=sources["parameter_policy_validation"],
        contract_skeleton=sources["contract_skeleton"],
        contract_skeleton_validation=sources["contract_skeleton_validation"],
        live_order_intent=sources["live_order_intent"],
        live_order_intent_validation=sources["live_order_intent_validation"],
        permission_decision=sources["permission_decision"],
        preflight_report=sources["preflight_report"],
        proposal_draft=sources["proposal_draft"],
        simulated_contract=sources["simulated_contract"],
        simulated_receipt=sources["simulated_receipt"],
        confirmation_phrase=EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    )
    values.update(overrides)
    return values


def _service_result(tmp_path: Path):
    return HumanValueApprovalLockService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION" in HUMAN_VALUE_APPROVAL_LOCK_STATUSES
    assert "CONTRACT_PARAMETERIZATION_ONLY" in HUMAN_VALUE_APPROVAL_LOCK_SCOPES
    assert "APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY" in HUMAN_VALUE_APPROVAL_ACTIONS
    assert "HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY" in HUMAN_VALUE_APPROVAL_REVIEW_STATES
    assert "LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY" in HUMAN_VALUE_LOCK_STATES
    assert "LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY" in HUMAN_VALUE_APPROVAL_SLOT_LOCK_STATUSES
    assert "WRONG_CONFIRMATION_PHRASE" in HUMAN_VALUE_APPROVAL_LOCK_BLOCK_REASONS


def test_confirmation_slot_lock_lock_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [slot.as_dict() for slot in result.approval_lock.slot_locks]
    payloads += [
        result.approval_lock.as_dict(),
        result.validation_report.as_dict(),
        result.journal_record.as_dict(),
    ]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "mt5_order_request" not in text


def test_config_defaults_enabled_and_requirements():
    config = HumanValueApprovalLockConfig()
    assert config.enabled is True
    assert config.require_value_proposal is True
    assert config.require_value_proposal_validation is True
    assert config.require_human_value_approval_allowed is True
    assert config.require_parameter_draft is True
    assert config.require_source_boundary is True
    assert config.require_policy_spec is True
    assert config.require_contract_skeleton is True
    assert config.require_live_order_intent is True
    assert config.require_permission_decision is True
    assert config.require_preflight_pass is True
    assert config.require_proposal_draft is True
    assert config.require_simulated_contract is True
    assert config.require_source_refs is True
    assert config.require_idempotency is True
    assert config.require_exact_confirmation is True
    assert config.require_value_lock is True


def test_exact_wrong_case_missing_and_expired_confirmation_behavior():
    service = HumanValueApprovalConfirmationService(HumanValueApprovalLockConfig())
    exact = service.confirm(EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE)
    assert exact.phrase_valid is True
    assert exact.action == "APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY"
    wrong = service.confirm("wrong phrase")
    assert wrong.phrase_valid is False
    assert "WRONG_CONFIRMATION_PHRASE" in wrong.blockers
    case_mismatch = service.confirm(EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE.upper())
    assert case_mismatch.phrase_valid is False
    missing = service.confirm(None)
    assert missing.phrase_valid is False
    expired = HumanValueApprovalConfirmationService(HumanValueApprovalLockConfig(ttl_seconds=-1)).confirm(
        EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE
    )
    assert "CONFIRMATION_EXPIRED" in expired.blockers
    assert expired.phrase_valid is False


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"value_proposal": None}, "MISSING_VALUE_PROPOSAL"),
        ({"value_proposal_validation": None}, "MISSING_VALUE_PROPOSAL_VALIDATION"),
        ({"parameter_draft": None}, "MISSING_PARAMETER_DRAFT"),
        ({"parameter_source_boundary": None}, "MISSING_SOURCE_BOUNDARY"),
        ({"parameter_policy_spec": None}, "MISSING_PARAMETER_POLICY_SPEC"),
        ({"contract_skeleton": None}, "MISSING_CONTRACT_SKELETON"),
        ({"live_order_intent": None}, "MISSING_LIVE_ORDER_INTENT"),
        ({"permission_decision": None}, "MISSING_PERMISSION_DECISION"),
        ({"preflight_report": None}, "MISSING_PREFLIGHT_REPORT"),
        ({"proposal_draft": None}, "MISSING_PROPOSAL_DRAFT"),
        ({"simulated_contract": None}, "MISSING_SIMULATED_CONTRACT"),
    ],
)
def test_missing_required_sources_block(tmp_path, override, reason):
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.approval_lock.blockers
    assert result.approval_lock.contract_parameterization_workflow_allowed is False


def test_invalid_proposal_validation_and_human_value_approval_false_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["value_proposal_validation"].valid = False
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_VALUE_PROPOSAL_VALIDATION" in result.approval_lock.blockers
    inputs = _inputs(tmp_path)
    inputs["value_proposal_validation"].human_value_approval_allowed = False
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "HUMAN_VALUE_APPROVAL_NOT_ALLOWED" in result.approval_lock.blockers


def test_preflight_source_refs_idempotency_confirmation_value_lock_and_payload_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.approval_lock.blockers

    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.approval_lock.blockers
    assert "MISSING_IDEMPOTENCY" in result.approval_lock.blockers

    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(
        **_inputs(tmp_path, confirmation_phrase="not exact")
    )
    assert "WRONG_CONFIRMATION_PHRASE" in result.approval_lock.blockers

    inputs = _inputs(tmp_path)
    inputs["value_proposal"].value_lock_required = False
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "VALUE_LOCK_NOT_REQUIRED" in result.approval_lock.blockers

    inputs = _inputs(tmp_path)
    inputs["proposal_draft"].executable = True
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "EXECUTABLE_ORDER_NOT_ALLOWED" in result.approval_lock.blockers
    inputs = _inputs(tmp_path)
    inputs["value_proposal"].mt5_payload_created = True
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "MT5_PAYLOAD_NOT_ALLOWED" in result.approval_lock.blockers
    inputs = _inputs(tmp_path)
    inputs["value_proposal"].order_contract_ready = True
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert "ORDER_CONTRACT_READY_NOT_ALLOWED" in result.approval_lock.blockers


def test_expired_and_duplicate_approval_lock_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = HumanValueApprovalLockService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_APPROVAL_LOCK" in result.approval_lock.blockers
    inputs = _inputs(tmp_path)
    first = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = HumanValueApprovalLockService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.approval_lock.status == "DUPLICATE"
    assert "DUPLICATE_APPROVAL_LOCK" in duplicate.approval_lock.blockers


def test_valid_inputs_create_lock_with_safe_flags_and_exactly_nine_slot_locks(tmp_path):
    result = _service_result(tmp_path)
    approval_lock = result.approval_lock
    validation = result.validation_report
    assert approval_lock.status == "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION"
    assert validation.valid is True
    assert validation.contract_parameterization_workflow_allowed is True
    assert validation.confirmation_phrase_valid is True
    for item in [approval_lock, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert len(approval_lock.slot_locks) == 9
    assert approval_lock.required_slot_lock_types == REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES
    assert all(slot.raw_value_stored is False for slot in approval_lock.slot_locks)
    assert all(slot.executable_value is False for slot in approval_lock.slot_locks)
    assert all(slot.mt5_payload_value is False for slot in approval_lock.slot_locks)
    assert all(slot.order_value is False for slot in approval_lock.slot_locks)
    assert all(slot.value_payload_redacted is True for slot in approval_lock.slot_locks)


def test_slot_lock_builder_creates_required_lock_types(tmp_path):
    value_proposal = _inputs(tmp_path)["value_proposal"]
    slots = HumanValueApprovalSlotLockBuilder().build_slot_locks(value_proposal, True, ["source:test"])
    assert [slot.slot_type for slot in slots] == REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES
    assert all(slot.source_value_slot_id for slot in slots)
    assert all(slot.approved_for_future_parameterization is True for slot in slots)
    assert all(slot.raw_value_stored is False for slot in slots)
    assert all(slot.value_payload_redacted is True for slot in slots)


def test_gate_valid_only_enables_contract_parameterization_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = HumanValueApprovalLockGate(_config(tmp_path)).validate(result.approval_lock)
    assert report.valid is True
    assert report.contract_parameterization_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.order_contract_ready is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = HumanValueApprovalLockJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_locked == 1
    assert store.find_by_idempotency_key(result.approval_lock.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = HumanValueApprovalLockJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_lock_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.approval_lock.approval_lock_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = HumanValueApprovalLockFormatter()
    card = formatter.to_card(result.approval_lock, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.approval_lock, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["order_contract_ready"] is False
    assert card.as_dict()["fields"]["raw_values_stored"] is False
    assert "contract_parameterization_workflow_allowed" in markdown
    assert "order_send_allowed: false" in markdown


@pytest.mark.parametrize(
    ("field_name", "issue", "value"),
    [
        ("live_execution_allowed", "live_execution_allowed_must_be_false", True),
        ("order_send_allowed", "order_send_allowed_must_be_false", True),
        ("execution_allowed", "execution_allowed_must_be_false", True),
        ("executable", "executable_must_be_false", True),
        ("mt5_payload_created", "mt5_payload_created_must_be_false", True),
        ("order_sent", "order_sent_must_be_false", True),
        ("order_contract_ready", "order_contract_ready_must_be_false", True),
        ("raw_values_stored", "raw_values_stored_must_be_false", True),
        ("executable_order_created", "executable_order_created_must_be_false", True),
    ],
)
def test_validator_rejects_unsafe_flags(tmp_path, field_name, issue, value):
    approval_lock = _service_result(tmp_path).approval_lock
    setattr(approval_lock, field_name, value)
    result = HumanValueApprovalLockValidator(_config(tmp_path)).validate_lock(approval_lock)
    assert issue in result.issues


@pytest.mark.parametrize(
    ("slot_field", "issue"),
    [
        ("raw_value_stored", "slot_raw_value_stored_must_be_false"),
        ("executable_value", "slot_executable_value_must_be_false"),
        ("mt5_payload_value", "slot_mt5_payload_value_must_be_false"),
        ("order_value", "slot_order_value_must_be_false"),
    ],
)
def test_validator_rejects_slot_unsafe_flags_and_missing_hard_block(tmp_path, slot_field, issue):
    approval_lock = _service_result(tmp_path).approval_lock
    setattr(approval_lock.slot_locks[0], slot_field, True)
    result = HumanValueApprovalLockValidator(_config(tmp_path)).validate_lock(approval_lock)
    assert issue in result.issues
    approval_lock = _service_result(tmp_path).approval_lock
    approval_lock.hard_live_block_required = False
    result = HumanValueApprovalLockValidator(_config(tmp_path)).validate_lock(approval_lock)
    assert "hard_live_block_required_must_be_true" in result.issues


@pytest.mark.parametrize(
    "marker",
    [
        "order_send",
        "submit_live_order",
        "send_order",
        "place_order",
        "execute_trade",
        "executable_order",
        "mt5_order_request",
        "mt5_payload",
        "mt5_ticket",
        "deal_id",
        "raw_account_id",
        "password",
        "api_key",
        "secret",
        "credentials",
        "raw_candles",
        "raw_full_book",
        "MetaTrader5",
        "llm_prompt",
    ],
)
def test_validator_rejects_forbidden_markers_in_blockers(tmp_path, marker):
    approval_lock = _service_result(tmp_path).approval_lock
    approval_lock.blockers = [marker]
    result = HumanValueApprovalLockValidator(_config(tmp_path)).validate_lock(approval_lock)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_parameterization_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Human Value Approval Lock" in text
    assert "This only locks human approval for future contract parameterization" in text
    assert "future contract parameterization only" in text
    for forbidden in ['"Confirm Trade"', '"Execute Trade"', '"Place Order"', '"Buy"', '"Sell"']:
        assert forbidden not in text


def test_mt5_bridge_has_no_order_endpoints():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    for forbidden in ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]:
        assert forbidden not in text


def test_no_order_send_implementation_and_no_rag_evidence_behavior_changed():
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in Path("src/services/trading/execution").rglob("*.py")
    )
    assert "def order_send" not in source
    assert "qdrant.delete_collection" not in source.lower()
    assert "qdrant.recreate_collection" not in source.lower()
