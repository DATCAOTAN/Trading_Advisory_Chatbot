from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_human_value_approval_lock import _config as _approval_config
from scripts.test_human_value_approval_lock import _inputs as _approval_inputs
from src.services.trading.execution.live_order_contract_parameterization import (
    LIVE_ORDER_CONTRACT_PARAMETER_SLOT_STATUSES,
    LIVE_ORDER_CONTRACT_PARAMETER_SLOT_TYPES,
    LIVE_ORDER_CONTRACT_PARAMETER_VALUE_STATES,
    LIVE_ORDER_CONTRACT_PARAMETERIZATION_BLOCK_REASONS,
    LIVE_ORDER_CONTRACT_PARAMETERIZATION_SCOPES,
    LIVE_ORDER_CONTRACT_PARAMETERIZATION_STATUSES,
    REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES,
    LiveOrderContractParameterSlotBuilder,
    LiveOrderContractParameterizationConfig,
    LiveOrderContractParameterizationFormatter,
    LiveOrderContractParameterizationGate,
    LiveOrderContractParameterizationJournalStore,
    LiveOrderContractParameterizationService,
    LiveOrderContractParameterizationValidator,
)
from src.services.trading.execution.live_value_approval_lock import HumanValueApprovalLockService


def _approval_lock_config(tmp_path: Path | None = None):
    config = _approval_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> LiveOrderContractParameterizationConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "live_order_contract_parameterizations.jsonl")}
    values.update(kwargs)
    return LiveOrderContractParameterizationConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _approval_inputs(tmp_path)
    approval_result = HumanValueApprovalLockService(config=_approval_lock_config(tmp_path)).run(**sources)
    values = dict(
        approval_lock=approval_result.approval_lock,
        approval_lock_validation=approval_result.validation_report,
        value_proposal=sources["value_proposal"],
        value_proposal_validation=sources["value_proposal_validation"],
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
    )
    values.update(overrides)
    return values


def _service_result(tmp_path: Path):
    return LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "PARAMETERIZATION_BOUNDARY_CREATED" in LIVE_ORDER_CONTRACT_PARAMETERIZATION_STATUSES
    assert "CONTRACT_VALIDATION_ONLY" in LIVE_ORDER_CONTRACT_PARAMETERIZATION_SCOPES
    assert "SIDE_CONTRACT_SLOT" in LIVE_ORDER_CONTRACT_PARAMETER_SLOT_TYPES
    assert "PARAMETERIZED_FOR_VALIDATION_ONLY" in LIVE_ORDER_CONTRACT_PARAMETER_SLOT_STATUSES
    assert "REDACTED_REFERENCE_ONLY" in LIVE_ORDER_CONTRACT_PARAMETER_VALUE_STATES
    assert "ORDER_REQUEST_MAPPING_NOT_ALLOWED" in LIVE_ORDER_CONTRACT_PARAMETERIZATION_BLOCK_REASONS


def test_slot_parameterization_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [slot.as_dict() for slot in result.parameterization.contract_slots]
    payloads += [
        result.parameterization.as_dict(),
        result.validation_report.as_dict(),
        result.journal_record.as_dict(),
    ]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "mt5_order_request" not in text


def test_config_defaults_enabled_and_requirements():
    config = LiveOrderContractParameterizationConfig()
    assert config.enabled is True
    assert config.require_approval_lock is True
    assert config.require_approval_lock_validation is True
    assert config.require_parameterization_workflow_allowed is True
    assert config.require_value_proposal is True
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
    assert config.reject_raw_values is True
    assert config.require_final_human_review is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"approval_lock": None}, "MISSING_APPROVAL_LOCK"),
        ({"approval_lock_validation": None}, "MISSING_APPROVAL_LOCK_VALIDATION"),
        ({"value_proposal": None}, "MISSING_VALUE_PROPOSAL"),
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
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.parameterization.blockers
    assert result.parameterization.contract_validation_workflow_allowed is False


def test_invalid_approval_validation_and_parameterization_workflow_false_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["approval_lock_validation"].valid = False
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_APPROVAL_LOCK_VALIDATION" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    inputs["approval_lock_validation"].contract_parameterization_workflow_allowed = False
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "CONTRACT_PARAMETERIZATION_NOT_ALLOWED" in result.parameterization.blockers


def test_preflight_source_refs_idempotency_and_payload_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.parameterization.blockers

    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.parameterization.blockers
    assert "MISSING_IDEMPOTENCY" in result.parameterization.blockers

    inputs = _inputs(tmp_path)
    inputs["approval_lock"].raw_values_stored = True
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "RAW_VALUES_NOT_ALLOWED" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    inputs["approval_lock"].executable_order_created = True
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "EXECUTABLE_ORDER_NOT_ALLOWED" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    inputs["approval_lock"].mt5_payload_created = True
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "MT5_PAYLOAD_NOT_ALLOWED" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    inputs["approval_lock"].order_contract_ready = True
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "ORDER_CONTRACT_READY_NOT_ALLOWED" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    inputs["approval_lock"].order_request_mapping_allowed = True
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert "ORDER_REQUEST_MAPPING_NOT_ALLOWED" in result.parameterization.blockers


def test_expired_and_duplicate_parameterization_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_PARAMETERIZATION" in result.parameterization.blockers
    inputs = _inputs(tmp_path)
    first = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = LiveOrderContractParameterizationService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.parameterization.status == "DUPLICATE"
    assert "DUPLICATE_PARAMETERIZATION" in duplicate.parameterization.blockers


def test_valid_inputs_create_parameterization_with_safe_flags_and_exactly_nine_contract_slots(tmp_path):
    result = _service_result(tmp_path)
    parameterization = result.parameterization
    validation = result.validation_report
    assert parameterization.status == "PARAMETERIZATION_BOUNDARY_CREATED"
    assert validation.valid is True
    assert validation.contract_validation_workflow_allowed is True
    for item in [parameterization, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.order_request_mapping_allowed is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert len(parameterization.contract_slots) == 9
    assert parameterization.required_contract_slot_types == REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES
    assert all(slot.raw_value_stored is False for slot in parameterization.contract_slots)
    assert all(slot.executable_value is False for slot in parameterization.contract_slots)
    assert all(slot.mt5_payload_value is False for slot in parameterization.contract_slots)
    assert all(slot.order_request_value is False for slot in parameterization.contract_slots)
    assert all(slot.parameterized_for_validation_only is True for slot in parameterization.contract_slots)
    assert all(slot.contract_validation_required is True for slot in parameterization.contract_slots)
    assert all(slot.final_human_review_required is True for slot in parameterization.contract_slots)


def test_contract_slot_builder_creates_required_contract_slot_types(tmp_path):
    approval_lock = _inputs(tmp_path)["approval_lock"]
    slots = LiveOrderContractParameterSlotBuilder().build_contract_slots(approval_lock, ["source:test"])
    assert [slot.slot_type for slot in slots] == REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES
    assert all(slot.source_slot_lock_id for slot in slots)
    assert all(slot.source_value_slot_id for slot in slots)
    assert all(slot.source_draft_slot_id for slot in slots)
    assert all(slot.parameterized_for_validation_only is True for slot in slots)
    assert all(slot.raw_value_stored is False for slot in slots)
    assert all(slot.redacted_value_reference_present is True for slot in slots)
    assert all(slot.final_human_review_required is True for slot in slots)


def test_gate_valid_only_enables_contract_validation_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = LiveOrderContractParameterizationGate(_config(tmp_path)).validate(result.parameterization)
    assert report.valid is True
    assert report.contract_validation_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.order_contract_ready is False
    assert report.order_request_mapping_allowed is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = LiveOrderContractParameterizationJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_created == 1
    assert store.find_by_idempotency_key(result.parameterization.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = LiveOrderContractParameterizationJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_parameterization_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.parameterization.parameterization_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = LiveOrderContractParameterizationFormatter()
    card = formatter.to_card(result.parameterization, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.parameterization, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["order_contract_ready"] is False
    assert card.as_dict()["fields"]["order_request_mapping_allowed"] is False
    assert card.as_dict()["fields"]["raw_values_stored"] is False
    assert "contract_validation_workflow_allowed" in markdown
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
        ("order_request_mapping_allowed", "order_request_mapping_allowed_must_be_false", True),
        ("raw_values_stored", "raw_values_stored_must_be_false", True),
        ("executable_order_created", "executable_order_created_must_be_false", True),
    ],
)
def test_validator_rejects_unsafe_flags(tmp_path, field_name, issue, value):
    parameterization = _service_result(tmp_path).parameterization
    setattr(parameterization, field_name, value)
    result = LiveOrderContractParameterizationValidator(_config(tmp_path)).validate_parameterization(parameterization)
    assert issue in result.issues


@pytest.mark.parametrize(
    ("slot_field", "issue"),
    [
        ("raw_value_stored", "slot_raw_value_stored_must_be_false"),
        ("executable_value", "slot_executable_value_must_be_false"),
        ("mt5_payload_value", "slot_mt5_payload_value_must_be_false"),
        ("order_request_value", "slot_order_request_value_must_be_false"),
    ],
)
def test_validator_rejects_slot_unsafe_flags_and_missing_hard_block(tmp_path, slot_field, issue):
    parameterization = _service_result(tmp_path).parameterization
    setattr(parameterization.contract_slots[0], slot_field, True)
    result = LiveOrderContractParameterizationValidator(_config(tmp_path)).validate_parameterization(parameterization)
    assert issue in result.issues
    parameterization = _service_result(tmp_path).parameterization
    parameterization.hard_live_block_required = False
    result = LiveOrderContractParameterizationValidator(_config(tmp_path)).validate_parameterization(parameterization)
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
    parameterization = _service_result(tmp_path).parameterization
    parameterization.blockers = [marker]
    result = LiveOrderContractParameterizationValidator(_config(tmp_path)).validate_parameterization(parameterization)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_validation_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Contract Parameterization Boundary" in text
    assert "This only builds a contract parameterization boundary for future validation" in text
    assert "does not allow broker order request mapping yet" in text
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
