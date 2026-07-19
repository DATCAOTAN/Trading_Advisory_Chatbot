from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_live_order_contract_final_review import _config as _final_review_config
from scripts.test_live_order_contract_final_review import _inputs as _final_review_inputs
from src.services.trading.execution.live_order_contract_final_review import (
    LiveOrderContractFinalReviewService,
)
from src.services.trading.execution.pre_mt5_order_mapping import (
    PRE_MT5_MAPPING_SLOT_STATUSES,
    PRE_MT5_MAPPING_SLOT_TYPES,
    PRE_MT5_MAPPING_VALUE_STATES,
    PRE_MT5_ORDER_REQUEST_MAPPING_BLOCK_REASONS,
    PRE_MT5_ORDER_REQUEST_MAPPING_SCOPES,
    PRE_MT5_ORDER_REQUEST_MAPPING_STATUSES,
    REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES,
    PreMT5MappingSlotBuilder,
    PreMT5OrderRequestMappingConfig,
    PreMT5OrderRequestMappingFormatter,
    PreMT5OrderRequestMappingGate,
    PreMT5OrderRequestMappingJournalStore,
    PreMT5OrderRequestMappingService,
    PreMT5OrderRequestMappingValidator,
)


def _review_config(tmp_path: Path | None = None):
    config = _final_review_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> PreMT5OrderRequestMappingConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "pre_mt5_order_request_mappings.jsonl")}
    values.update(kwargs)
    return PreMT5OrderRequestMappingConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _final_review_inputs(tmp_path)
    final_review_result = LiveOrderContractFinalReviewService(config=_review_config(tmp_path)).run(**sources)
    values = dict(
        final_review=final_review_result.final_review,
        final_review_validation=final_review_result.validation_report,
        parameterization=sources["parameterization"],
        parameterization_validation=sources["parameterization_validation"],
        approval_lock=sources["approval_lock"],
        approval_lock_validation=sources["approval_lock_validation"],
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
    return PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "MAPPING_BOUNDARY_CREATED" in PRE_MT5_ORDER_REQUEST_MAPPING_STATUSES
    assert "MT5_DRY_RUN_PAYLOAD_VALIDATION_ONLY" in PRE_MT5_ORDER_REQUEST_MAPPING_SCOPES
    assert "ACTION_MAPPING_SLOT" in PRE_MT5_MAPPING_SLOT_TYPES
    assert "AUDIT_MAPPING_SLOT" in PRE_MT5_MAPPING_SLOT_TYPES
    assert "MAPPED_AS_SCHEMA_ONLY" in PRE_MT5_MAPPING_SLOT_STATUSES
    assert "SCHEMA_ONLY" in PRE_MT5_MAPPING_VALUE_STATES
    assert "MT5_REQUEST_DICT_NOT_ALLOWED" in PRE_MT5_ORDER_REQUEST_MAPPING_BLOCK_REASONS


def test_mapping_slot_boundary_report_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [slot.as_dict() for slot in result.mapping_boundary.mapping_slots]
    payloads += [result.mapping_boundary.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "raw_parameter_value" not in text
        assert "ORDER_TYPE_BUY" not in text
        assert "TRADE_ACTION_DEAL" not in text


def test_config_defaults_enabled_and_requirements():
    config = PreMT5OrderRequestMappingConfig()
    assert config.enabled is True
    assert config.require_final_review is True
    assert config.require_final_review_validation is True
    assert config.require_pre_mt5_workflow_allowed is True
    assert config.require_parameterization is True
    assert config.require_approval_lock is True
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
    assert config.reject_mt5_payload is True
    assert config.reject_mt5_request_dict is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"final_review": None}, "MISSING_FINAL_REVIEW"),
        ({"final_review_validation": None}, "MISSING_FINAL_REVIEW_VALIDATION"),
        ({"parameterization": None}, "MISSING_PARAMETERIZATION"),
        ({"approval_lock": None}, "MISSING_APPROVAL_LOCK"),
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
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.mapping_boundary.blockers
    assert result.mapping_boundary.mt5_dry_run_payload_validation_workflow_allowed is False


def test_final_review_validation_workflow_preflight_refs_and_idempotency_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["final_review_validation"].valid = False
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_FINAL_REVIEW_VALIDATION" in result.mapping_boundary.blockers
    inputs = _inputs(tmp_path)
    inputs["final_review_validation"].pre_mt5_mapping_boundary_workflow_allowed = False
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert "PRE_MT5_MAPPING_WORKFLOW_NOT_ALLOWED" in result.mapping_boundary.blockers
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.mapping_boundary.blockers
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.mapping_boundary.blockers
    assert "MISSING_IDEMPOTENCY" in result.mapping_boundary.blockers


def test_raw_executable_payload_request_dict_order_ready_mapping_and_broker_mapping_block(tmp_path):
    for field_name, reason in [
        ("raw_values_stored", "RAW_VALUES_NOT_ALLOWED"),
        ("executable_order_created", "EXECUTABLE_ORDER_NOT_ALLOWED"),
        ("mt5_payload_created", "MT5_PAYLOAD_NOT_ALLOWED"),
        ("mt5_request_dict_created", "MT5_REQUEST_DICT_NOT_ALLOWED"),
        ("order_contract_ready", "ORDER_CONTRACT_READY_NOT_ALLOWED"),
        ("order_request_mapping_allowed", "ORDER_REQUEST_MAPPING_NOT_ALLOWED"),
        ("broker_mapping_created", "ORDER_REQUEST_MAPPING_NOT_ALLOWED"),
    ]:
        inputs = _inputs(tmp_path)
        setattr(inputs["final_review"], field_name, True)
        result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
        assert reason in result.mapping_boundary.blockers


def test_expired_and_duplicate_mapping_boundary_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_MAPPING_BOUNDARY" in result.mapping_boundary.blockers
    inputs = _inputs(tmp_path)
    first = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = PreMT5OrderRequestMappingService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.mapping_boundary.status == "DUPLICATE"
    assert "DUPLICATE_MAPPING_BOUNDARY" in duplicate.mapping_boundary.blockers


def test_valid_inputs_create_schema_only_mapping_boundary_with_safe_flags_and_slots(tmp_path):
    result = _service_result(tmp_path)
    boundary = result.mapping_boundary
    validation = result.validation_report
    assert boundary.status == "MAPPING_BOUNDARY_CREATED"
    assert validation.valid is True
    assert validation.mt5_dry_run_payload_validation_workflow_allowed is True
    for item in [boundary, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.mt5_request_dict_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.order_request_mapping_allowed is False
        assert item.broker_mapping_created is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert validation.mapping_slots_count == 11
    assert validation.mapped_slots_count == 11
    assert validation.missing_slots_count == 0
    assert validation.invalid_slots_count == 0
    assert boundary.required_mapping_slot_types == REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES
    assert {slot.slot_type for slot in boundary.mapping_slots} == set(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES)
    assert all(slot.mapped_as_schema_only is True for slot in boundary.mapping_slots)
    assert all(slot.dry_run_payload_validation_required is True for slot in boundary.mapping_slots)
    assert all(slot.raw_value_stored is False for slot in boundary.mapping_slots)
    assert all(slot.mt5_payload_value_created is False for slot in boundary.mapping_slots)
    assert all(slot.mt5_request_field_value_created is False for slot in boundary.mapping_slots)
    assert all(slot.executable_order_value is False for slot in boundary.mapping_slots)
    assert all(slot.broker_submission_value is False for slot in boundary.mapping_slots)


def test_slot_builder_maps_required_slots_without_values(tmp_path):
    inputs = _inputs(tmp_path)
    slots = PreMT5MappingSlotBuilder().build_slots(inputs["final_review"], inputs["final_review"].source_refs)
    assert len(slots) == 11
    assert {slot.slot_type for slot in slots} == set(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES)
    assert all(slot.future_mt5_field_label.startswith("schema_") for slot in slots)
    assert all("schema_only" in slot.future_validation_requirements for slot in slots)
    assert all(not slot.blockers for slot in slots)


def test_gate_valid_only_enables_dry_run_payload_validation_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = PreMT5OrderRequestMappingGate(_config(tmp_path)).validate(result.mapping_boundary)
    assert report.valid is True
    assert report.mt5_dry_run_payload_validation_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.mt5_request_dict_created is False
    assert report.order_contract_ready is False
    assert report.order_request_mapping_allowed is False
    assert report.broker_mapping_created is False


def test_journal_store_appends_reads_summarizes_lookup_and_tolerates_corrupt_lines(tmp_path):
    result = _service_result(tmp_path)
    store = PreMT5OrderRequestMappingJournalStore(_config(tmp_path).journal_path)
    assert result.journal_record is not None
    latest = store.read_latest()
    assert latest
    summary = store.summarize()
    assert summary.total_records == 1
    assert summary.total_created == 1
    found = store.find_by_idempotency_key(result.journal_record.idempotency_key)
    assert found is not None
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{bad json}\n")
    latest = store.read_latest()
    assert latest
    assert any("corrupt_jsonl_line" in warning for warning in store.warnings)


def test_service_builds_mapping_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.mapping_boundary.mapping_boundary_id
    assert result.validation_report.source_mapping_boundary_id == result.mapping_boundary.mapping_boundary_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1
    assert (result.timings_ms or {})["pre_mt5_mapping_build_latency_ms"] >= 0


def test_formatter_creates_json_safe_card_and_markdown_summary(tmp_path):
    result = _service_result(tmp_path)
    formatter = PreMT5OrderRequestMappingFormatter()
    card = formatter.to_card(result.mapping_boundary, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.mapping_boundary, result.validation_report, result.journal_record)
    assert card.fields["mt5_dry_run_payload_validation_workflow_allowed"] is True
    assert card.fields["mt5_request_dict_created"] is False
    assert "Pre-MT5 Order Request Mapping Boundary" in markdown
    assert "raw_parameter_value" not in json.dumps(card.as_dict())


@pytest.mark.parametrize(
    "field_name",
    [
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "mt5_payload_created",
        "mt5_request_dict_created",
        "order_sent",
        "order_contract_ready",
        "order_request_mapping_allowed",
        "broker_mapping_created",
        "raw_values_stored",
        "executable_order_created",
    ],
)
def test_validator_rejects_unsafe_boundary_flags(tmp_path, field_name):
    result = _service_result(tmp_path)
    setattr(result.mapping_boundary, field_name, True)
    validation = PreMT5OrderRequestMappingValidator(_config(tmp_path)).validate_mapping_boundary(result.mapping_boundary)
    assert validation.passed is False
    assert any(field_name in issue for issue in validation.issues)


@pytest.mark.parametrize(
    "field_name",
    [
        "raw_value_stored",
        "mt5_payload_value_created",
        "mt5_request_field_value_created",
        "executable_order_value",
        "broker_submission_value",
    ],
)
def test_validator_rejects_unsafe_slot_flags(tmp_path, field_name):
    result = _service_result(tmp_path)
    setattr(result.mapping_boundary.mapping_slots[0], field_name, True)
    validation = PreMT5OrderRequestMappingValidator(_config(tmp_path)).validate_mapping_boundary(result.mapping_boundary)
    assert validation.passed is False
    assert any(field_name in issue for issue in validation.issues)


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
        "mt5_request",
        "mt5_payload",
        "mt5_ticket",
        "deal_id",
        "broker_order_mapping",
        "broker_mapping_payload",
        "raw_account_id",
        "raw_parameter_value",
        "password",
        "api_key",
        "secret",
        "MetaTrader5",
        "ORDER_TYPE_BUY",
        "ORDER_TYPE_SELL",
        "TRADE_ACTION_DEAL",
    ],
)
def test_validator_rejects_forbidden_markers(tmp_path, marker):
    result = _service_result(tmp_path)
    result.mapping_boundary.mapping_slots[0].blockers.append(marker)
    validation = PreMT5OrderRequestMappingValidator(_config(tmp_path)).validate_mapping_boundary(result.mapping_boundary)
    assert validation.passed is False
    assert any("forbidden_marker" in issue for issue in validation.issues)


def test_dashboard_labels_and_buttons_are_boundary_only():
    dashboard = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Pre-MT5 Mapping Boundary" in dashboard
    assert "dry-run payload validator" in dashboard
    assert "does not create an MT5 request dictionary" in dashboard
    assert "Confirm Trade" not in dashboard
    assert "Execute Trade" not in dashboard
    assert "Place Order" not in dashboard
    assert "Buy" not in dashboard
    assert "Sell" not in dashboard


def test_mt5_bridge_has_no_order_endpoints_and_no_mapping_logic():
    server = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    forbidden_routes = ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]
    assert not any(route in server for route in forbidden_routes)
    assert "PreMT5" not in server
    assert "pre_mt5" not in server


def test_no_order_send_implementation_qdrant_or_rag_changes():
    execution_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path("src/services/trading/execution").rglob("*.py"))
    sanitized = execution_text.replace("order_send_allowed", "")
    assert "def order_send" not in sanitized
    assert "order_send(" not in sanitized
    assert "submit_live_order(" not in sanitized
    assert "send_order(" not in sanitized
    assert "place_order(" not in sanitized
    assert "execute_trade(" not in sanitized
    assert "qdrant reset" not in execution_text.lower()
    assert "delete qdrant" not in execution_text.lower()
    assert "Evidence" not in Path("src/services/trading/execution/pre_mt5_order_mapping/builder.py").read_text(encoding="utf-8")
