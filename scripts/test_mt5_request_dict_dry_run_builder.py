from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_mt5_request_draft_final_approval import _config as _final_approval_config
from scripts.test_mt5_request_draft_final_approval import _inputs as _final_approval_inputs
from src.services.trading.execution.mt5_request_draft_final_approval import (
    MT5RequestDraftFinalApprovalService,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder import (
    DRY_RUN_KEY_LABEL_BY_CATEGORY,
    MT5_REQUEST_DICT_DRY_RUN_BUILDER_BLOCK_REASONS,
    MT5_REQUEST_DICT_DRY_RUN_BUILDER_SCOPES,
    MT5_REQUEST_DICT_DRY_RUN_BUILDER_STATUSES,
    MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES,
    MT5_REQUEST_DICT_DRY_RUN_FIELD_STATUSES,
    MT5_REQUEST_DICT_DRY_RUN_VALUE_STATES,
    REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES,
    MT5RequestDictDryRunBuilderConfig,
    MT5RequestDictDryRunBuilderFormatter,
    MT5RequestDictDryRunBuilderGate,
    MT5RequestDictDryRunBuilderJournalStore,
    MT5RequestDictDryRunBuilderService,
    MT5RequestDictDryRunBuilderValidator,
    MT5RequestDictDryRunFieldBuilder,
)


def _final_approval_service_config(tmp_path: Path | None = None):
    config = _final_approval_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> MT5RequestDictDryRunBuilderConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "mt5_request_dict_dry_run_builders.jsonl")}
    values.update(kwargs)
    return MT5RequestDictDryRunBuilderConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _final_approval_inputs(tmp_path)
    final_approval_result = MT5RequestDraftFinalApprovalService(
        config=_final_approval_service_config(tmp_path)
    ).run(**sources)
    values = dict(
        draft_final_approval=final_approval_result.final_approval,
        draft_final_approval_validation_report=final_approval_result.validation_report,
        request_draft=sources["request_draft"],
        request_draft_validation_report=sources["request_draft_validation_report"],
        dry_run_validation=sources["dry_run_validation"],
        dry_run_validation_report=sources["dry_run_validation_report"],
        pre_mt5_mapping=sources["pre_mt5_mapping"],
        pre_mt5_mapping_validation=sources["pre_mt5_mapping_validation"],
        final_review=sources["final_review"],
        final_review_validation=sources["final_review_validation"],
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
    return MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED" in MT5_REQUEST_DICT_DRY_RUN_BUILDER_STATUSES
    assert "REQUEST_DICT_FINAL_VALIDATION_ONLY" in MT5_REQUEST_DICT_DRY_RUN_BUILDER_SCOPES
    assert "ACTION_KEY" in MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES
    assert "AUDIT_KEY" in MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES
    assert "DRY_RUN_FIELD_CREATED_AS_SCHEMA_ONLY" in MT5_REQUEST_DICT_DRY_RUN_FIELD_STATUSES
    assert "BROKER_SUBMISSION_NOT_CREATED" in MT5_REQUEST_DICT_DRY_RUN_VALUE_STATES
    assert "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED" in MT5_REQUEST_DICT_DRY_RUN_BUILDER_BLOCK_REASONS


def test_config_defaults_enabled_and_requirements():
    config = MT5RequestDictDryRunBuilderConfig()
    assert config.enabled is True
    assert config.require_draft_final_approval is True
    assert config.require_draft_final_approval_validation_report is True
    assert config.require_workflow_allowed is True
    assert config.require_request_draft is True
    assert config.require_dry_run_validation is True
    assert config.require_pre_mt5_mapping is True
    assert config.require_final_review is True
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
    assert config.reject_real_mt5_payload is True
    assert config.reject_broker_submittable_request_dict is True
    assert config.reject_mt5_constants is True
    assert config.reject_broker_submission is True


def test_boundary_report_field_and_journal_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [field.as_dict() for field in result.boundary.dry_run_fields]
    payloads += [result.boundary.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "raw_parameter_value" not in text
        assert "MetaTrader5" not in text
        assert "ORDER_TYPE_BUY" not in text
        assert "TRADE_ACTION_DEAL" not in text


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"draft_final_approval": None}, "MISSING_DRAFT_FINAL_APPROVAL"),
        ({"draft_final_approval_validation_report": None}, "MISSING_DRAFT_FINAL_APPROVAL_VALIDATION_REPORT"),
        ({"request_draft": None}, "MISSING_REQUEST_DRAFT"),
        ({"dry_run_validation": None}, "MISSING_DRY_RUN_PAYLOAD_VALIDATION"),
        ({"pre_mt5_mapping": None}, "MISSING_PRE_MT5_MAPPING"),
        ({"final_review": None}, "MISSING_FINAL_REVIEW"),
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
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.boundary.blockers
    assert result.validation_report.valid is False
    assert result.boundary.mt5_request_dict_final_validation_workflow_allowed is False


def test_final_approval_report_workflow_refs_and_idempotency_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["draft_final_approval_validation_report"].valid = False
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_DRAFT_FINAL_APPROVAL_VALIDATION_REPORT" in result.boundary.blockers

    inputs = _inputs(tmp_path)
    inputs["draft_final_approval_validation_report"].mt5_request_dict_dry_run_builder_workflow_allowed = False
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs)
    assert "REQUEST_DICT_DRY_RUN_BUILDER_WORKFLOW_NOT_ALLOWED" in result.boundary.blockers

    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.boundary.blockers
    assert "MISSING_IDEMPOTENCY" in result.boundary.blockers


@pytest.mark.parametrize(
    ("target_name", "field_name", "reason"),
    [
        ("draft_final_approval", "raw_values_stored", "RAW_VALUES_NOT_ALLOWED"),
        ("draft_final_approval", "mt5_payload_created", "REAL_MT5_PAYLOAD_NOT_ALLOWED"),
        ("draft_final_approval", "mt5_request_dict_created", "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED"),
        ("draft_final_approval", "mt5_constants_used", "MT5_CONSTANT_NOT_ALLOWED"),
        ("draft_final_approval", "broker_submission_created", "BROKER_SUBMISSION_NOT_ALLOWED"),
        ("draft_final_approval", "executable_order_created", "EXECUTABLE_ORDER_NOT_ALLOWED"),
        ("draft_final_approval", "order_contract_ready", "ORDER_CONTRACT_READY_NOT_ALLOWED"),
        ("draft_final_approval", "order_request_mapping_allowed", "ORDER_REQUEST_MAPPING_NOT_ALLOWED"),
        ("draft_final_approval", "broker_mapping_created", "BROKER_MAPPING_NOT_ALLOWED"),
    ],
)
def test_raw_payload_dict_constants_submission_executable_ready_mapping_and_broker_mapping_block(
    tmp_path,
    target_name,
    field_name,
    reason,
):
    inputs = _inputs(tmp_path)
    setattr(inputs[target_name], field_name, True)
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs)
    assert reason in result.boundary.blockers


def test_expired_and_duplicate_dry_run_request_dict_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_DRY_RUN_REQUEST_DICT" in result.boundary.blockers

    fixed_now = datetime.now(timezone.utc)
    inputs = _inputs(tmp_path)
    first = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs, current_time=fixed_now)
    assert first.journal_record is not None
    duplicate = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs, current_time=fixed_now)
    assert duplicate.boundary.status == "DUPLICATE"
    assert "DUPLICATE_DRY_RUN_REQUEST_DICT" in duplicate.boundary.blockers


def test_valid_inputs_create_boundary_with_safe_flags_fields_and_labels(tmp_path):
    result = _service_result(tmp_path)
    boundary = result.boundary
    report = result.validation_report
    assert boundary.status == "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED"
    assert report.valid is True
    assert report.mt5_request_dict_final_validation_workflow_allowed is True
    for item in [boundary, report]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.real_mt5_payload_created is False
        assert item.broker_submittable_request_dict_created is False
        assert item.mt5_constants_used is False
        assert item.broker_submission_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.order_request_mapping_allowed is False
        assert item.broker_mapping_created is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert report.dry_run_fields_count == 12
    assert report.created_dry_run_fields_count == 12
    assert report.missing_dry_run_fields_count == 0
    assert report.invalid_dry_run_fields_count == 0
    assert set(boundary.created_dry_run_field_categories) == set(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES)
    assert {field.dry_run_key_label for field in boundary.dry_run_fields} == set(DRY_RUN_KEY_LABEL_BY_CATEGORY.values())
    for field in boundary.dry_run_fields:
        assert field.dry_run_field_present is True
        assert field.concrete_value_created is False
        assert field.value_redacted is True
        assert field.raw_value_stored is False
        assert field.real_mt5_payload_value_created is False
        assert field.broker_submittable_request_field_created is False
        assert field.mt5_constant_used is False
        assert field.executable_order_value is False
        assert field.broker_submission_value is False
        assert field.final_validation_required is True
        assert field.source_approved_field_id
        assert field.source_draft_field_id
        assert field.source_field_validation_id
        assert field.source_mapping_slot_id
        assert field.source_refs


def test_field_builder_and_gate_preserve_safety(tmp_path):
    inputs = _inputs(tmp_path)
    fields = MT5RequestDictDryRunFieldBuilder().build_dry_run_fields(
        inputs["draft_final_approval"],
        source_refs=inputs["draft_final_approval"].source_refs,
    )
    assert len(fields) == 12
    assert {field.field_category for field in fields} == set(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES)
    boundary = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs).boundary
    report = MT5RequestDictDryRunBuilderGate(_config(tmp_path)).validate(boundary)
    assert report.valid is True
    assert report.mt5_request_dict_final_validation_workflow_allowed is True
    assert report.order_send_allowed is False
    assert report.real_mt5_payload_created is False
    assert report.broker_submittable_request_dict_created is False
    assert report.mt5_constants_used is False
    assert report.broker_submission_created is False


def test_journal_store_appends_reads_summarizes_lookup_and_handles_corrupt_line(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    store = MT5RequestDictDryRunBuilderJournalStore(_config(tmp_path).journal_path)
    assert len(store.read_latest()) == 1
    assert store.summarize().total_records == 1
    assert store.find_by_idempotency_key(result.journal_record.idempotency_key) is not None
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")
    latest = store.read_latest()
    assert len(latest) == 1
    assert store.summarize().warnings


def test_service_and_formatter_create_safe_outputs(tmp_path):
    result = _service_result(tmp_path)
    card = MT5RequestDictDryRunBuilderFormatter().to_card(result.boundary, result.validation_report, result.journal_record)
    card_dict = card.as_dict()
    markdown = MT5RequestDictDryRunBuilderFormatter().to_markdown_summary(
        result.boundary,
        result.validation_report,
        result.journal_record,
    )
    assert card_dict["fields"]["mt5_request_dict_final_validation_workflow_allowed"] is True
    assert "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED" in markdown
    text = json.dumps(card_dict, sort_keys=True) + markdown
    assert "raw_account_id" not in text
    assert "MetaTrader5" not in text
    assert "ORDER_TYPE_BUY" not in text


@pytest.mark.parametrize(
    "field_name",
    [
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "real_mt5_payload_created",
        "broker_submittable_request_dict_created",
        "mt5_constants_used",
        "broker_submission_created",
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
    setattr(result.boundary, field_name, True)
    validation = MT5RequestDictDryRunBuilderValidator(_config(tmp_path)).validate_boundary(
        result.boundary,
        result.validation_report,
    )
    assert validation.passed is False


@pytest.mark.parametrize(
    "field_name",
    [
        "concrete_value_created",
        "raw_value_stored",
        "real_mt5_payload_value_created",
        "broker_submittable_request_field_created",
        "mt5_constant_used",
        "executable_order_value",
        "broker_submission_value",
    ],
)
def test_validator_rejects_unsafe_dry_run_field_flags(tmp_path, field_name):
    result = _service_result(tmp_path)
    setattr(result.boundary.dry_run_fields[0], field_name, True)
    validation = MT5RequestDictDryRunBuilderValidator(_config(tmp_path)).validate_boundary(
        result.boundary,
        result.validation_report,
    )
    assert validation.passed is False


@pytest.mark.parametrize(
    "marker",
    [
        "order_send",
        "real_mt5_payload",
        "broker_submittable_request_dict",
        "broker_submission_payload",
        "mt5_ticket",
        "deal_id",
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
    result.boundary.warnings.append(marker)
    validation = MT5RequestDictDryRunBuilderValidator(_config(tmp_path)).validate_boundary(
        result.boundary,
        result.validation_report,
    )
    assert validation.passed is False


def test_validator_does_not_reject_internal_dry_run_boundary_names(tmp_path):
    inputs = _inputs(tmp_path)
    result = MT5RequestDictDryRunBuilderService(config=_config(tmp_path)).run(**inputs)
    result.boundary.warnings.extend(
        [
            "MT5RequestDictDryRunBuilderBoundary",
            "MT5RequestDictDryRunBuilderValidationReport",
            "mt5_request_dict_final_validation_workflow_allowed",
        ]
    )
    validation = MT5RequestDictDryRunBuilderValidator(_config(tmp_path)).validate_boundary(
        result.boundary,
        inputs["draft_final_approval_validation_report"],
    )
    assert validation.passed is True


def test_dashboard_and_bridge_keep_execution_surface_forbidden():
    dashboard_text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    bridge_text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    assert "Build MT5 Request Dict Dry-Run Boundary" in dashboard_text
    assert "Confirm Trade" not in dashboard_text
    assert "Execute Trade" not in dashboard_text
    assert "Place Order" not in dashboard_text
    assert "Buy" not in dashboard_text
    assert "Sell" not in dashboard_text
    for endpoint in ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]:
        assert endpoint not in bridge_text
    assert "MetaTrader5" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")


def test_no_order_send_qdrant_or_rag_evidence_changes():
    src_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path("src").rglob("*.py"))
    builder_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in Path("src/services/trading/execution/mt5_request_dict_dry_run_builder").rglob("*.py")
    )
    assert ".order_send(" not in src_text
    assert "qdrant_client.delete_collection" not in src_text
    assert "recreate_collection" not in src_text
    assert "Evidence" not in builder_text
