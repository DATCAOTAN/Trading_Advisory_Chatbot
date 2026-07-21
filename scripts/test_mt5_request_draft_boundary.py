from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_mt5_order_request_dry_run_payload_validator import _config as _dry_run_config
from scripts.test_mt5_order_request_dry_run_payload_validator import _inputs as _dry_run_inputs
from src.services.trading.execution.mt5_dry_run_payload_validator import (
    MT5OrderRequestDryRunPayloadValidationService,
)
from src.services.trading.execution.mt5_request_draft import (
    MT5_REQUEST_DRAFT_BLOCK_REASONS,
    MT5_REQUEST_DRAFT_FIELD_CATEGORIES,
    MT5_REQUEST_DRAFT_FIELD_STATUSES,
    MT5_REQUEST_DRAFT_SCOPES,
    MT5_REQUEST_DRAFT_STATUSES,
    MT5_REQUEST_DRAFT_VALUE_STATES,
    REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES,
    MT5RequestDraftConfig,
    MT5RequestDraftFieldBuilder,
    MT5RequestDraftFormatter,
    MT5RequestDraftGate,
    MT5RequestDraftJournalStore,
    MT5RequestDraftService,
    MT5RequestDraftValidator,
)


def _dry_run_service_config(tmp_path: Path | None = None):
    config = _dry_run_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> MT5RequestDraftConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "mt5_request_drafts.jsonl")}
    values.update(kwargs)
    return MT5RequestDraftConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _dry_run_inputs(tmp_path)
    dry_run_result = MT5OrderRequestDryRunPayloadValidationService(
        config=_dry_run_service_config(tmp_path)
    ).run(**sources)
    values = dict(
        dry_run_validation=dry_run_result.dry_run_validation,
        dry_run_validation_report=dry_run_result.validation_report,
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
    return MT5RequestDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "REQUEST_DRAFT_CREATED" in MT5_REQUEST_DRAFT_STATUSES
    assert "FINAL_DRAFT_APPROVAL_ONLY" in MT5_REQUEST_DRAFT_SCOPES
    assert "ACTION_DRAFT_FIELD" in MT5_REQUEST_DRAFT_FIELD_CATEGORIES
    assert "TAKE_PROFIT_DRAFT_FIELD" in MT5_REQUEST_DRAFT_FIELD_CATEGORIES
    assert "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY" in MT5_REQUEST_DRAFT_FIELD_STATUSES
    assert "REFERENCE_ONLY" in MT5_REQUEST_DRAFT_VALUE_STATES
    assert "BROKER_SUBMISSION_NOT_ALLOWED" in MT5_REQUEST_DRAFT_BLOCK_REASONS


def test_draft_field_object_report_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [field.as_dict() for field in result.request_draft.draft_fields]
    payloads += [result.request_draft.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "raw_parameter_value" not in text
        assert "ORDER_TYPE_BUY" not in text
        assert "TRADE_ACTION_DEAL" not in text


def test_config_defaults_enabled_and_requirements():
    config = MT5RequestDraftConfig()
    assert config.enabled is True
    assert config.require_dry_run_validation is True
    assert config.require_dry_run_validation_report is True
    assert config.require_workflow_allowed is True
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
    assert config.reject_mt5_payload is True
    assert config.reject_mt5_request_dict is True
    assert config.reject_mt5_constants is True
    assert config.reject_broker_submission is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"dry_run_validation": None}, "MISSING_DRY_RUN_PAYLOAD_VALIDATION"),
        ({"dry_run_validation_report": None}, "MISSING_DRY_RUN_PAYLOAD_VALIDATION_REPORT"),
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
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.request_draft.blockers
    assert result.request_draft.mt5_request_draft_final_approval_workflow_allowed is False


def test_dry_run_validation_workflow_refs_and_idempotency_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["dry_run_validation_report"].valid = False
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_DRY_RUN_PAYLOAD_VALIDATION_REPORT" in result.request_draft.blockers
    inputs = _inputs(tmp_path)
    inputs["dry_run_validation_report"].mt5_request_draft_workflow_allowed = False
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MT5_REQUEST_DRAFT_WORKFLOW_NOT_ALLOWED" in result.request_draft.blockers
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.request_draft.blockers
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.request_draft.blockers
    assert "MISSING_IDEMPOTENCY" in result.request_draft.blockers


def test_raw_payload_request_dict_constants_submission_executable_ready_mapping_and_broker_mapping_block(tmp_path):
    for target_name, field_name, reason in [
        ("dry_run_validation", "raw_values_stored", "RAW_VALUES_NOT_ALLOWED"),
        ("dry_run_validation", "mt5_payload_created", "MT5_PAYLOAD_NOT_ALLOWED"),
        ("dry_run_validation", "mt5_request_dict_created", "MT5_REQUEST_DICT_NOT_ALLOWED"),
        ("dry_run_validation", "mt5_constants_used", "MT5_CONSTANT_NOT_ALLOWED"),
        ("dry_run_validation", "broker_submission_created", "BROKER_SUBMISSION_NOT_ALLOWED"),
        ("dry_run_validation", "executable_order_created", "EXECUTABLE_ORDER_NOT_ALLOWED"),
        ("dry_run_validation", "order_contract_ready", "ORDER_CONTRACT_READY_NOT_ALLOWED"),
        ("dry_run_validation", "order_request_mapping_allowed", "ORDER_REQUEST_MAPPING_NOT_ALLOWED"),
        ("dry_run_validation", "broker_mapping_created", "BROKER_MAPPING_NOT_ALLOWED"),
    ]:
        inputs = _inputs(tmp_path)
        setattr(inputs[target_name], field_name, True)
        result = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
        assert reason in result.request_draft.blockers


def test_expired_and_duplicate_draft_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = MT5RequestDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_REQUEST_DRAFT" in result.request_draft.blockers
    inputs = _inputs(tmp_path)
    first = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = MT5RequestDraftService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.request_draft.status == "DUPLICATE"
    assert "DUPLICATE_REQUEST_DRAFT" in duplicate.request_draft.blockers


def test_valid_inputs_create_request_draft_with_safe_flags_and_fields(tmp_path):
    result = _service_result(tmp_path)
    draft = result.request_draft
    report = result.validation_report
    assert draft.status == "REQUEST_DRAFT_CREATED"
    assert report.valid is True
    assert report.mt5_request_draft_final_approval_workflow_allowed is True
    for item in [draft, report]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.mt5_request_dict_created is False
        assert item.mt5_constants_used is False
        assert item.broker_submission_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.order_request_mapping_allowed is False
        assert item.broker_mapping_created is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert report.draft_fields_count == 12
    assert report.created_draft_fields_count == 12
    assert report.missing_draft_fields_count == 0
    assert report.invalid_draft_fields_count == 0
    assert draft.required_draft_field_categories == REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES
    assert {item.field_category for item in draft.draft_fields} == set(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES)
    assert all(item.draft_field_present is True for item in draft.draft_fields)
    assert all(item.draft_value_created is False for item in draft.draft_fields)
    assert all(item.draft_value_redacted is True for item in draft.draft_fields)
    assert all(item.raw_value_stored is False for item in draft.draft_fields)
    assert all(item.mt5_payload_value_created is False for item in draft.draft_fields)
    assert all(item.mt5_request_field_value_created is False for item in draft.draft_fields)
    assert all(item.mt5_constant_used is False for item in draft.draft_fields)
    assert all(item.executable_order_value is False for item in draft.draft_fields)
    assert all(item.broker_submission_value is False for item in draft.draft_fields)
    assert all(item.final_draft_approval_required is True for item in draft.draft_fields)


def test_field_builder_maps_required_categories_without_values(tmp_path):
    inputs = _inputs(tmp_path)
    fields = MT5RequestDraftFieldBuilder().build_draft_fields(
        inputs["dry_run_validation"], inputs["dry_run_validation"].source_refs
    )
    assert len(fields) == 12
    assert {item.field_category for item in fields} == set(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES)
    assert all(item.status == "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY" for item in fields)
    assert all(item.value_state == "REFERENCE_ONLY" for item in fields)
    assert all(not item.blockers for item in fields)


def test_gate_valid_only_enables_final_draft_approval_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = MT5RequestDraftGate(_config(tmp_path)).validate(result.request_draft)
    assert report.valid is True
    assert report.mt5_request_draft_final_approval_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.mt5_request_dict_created is False
    assert report.mt5_constants_used is False
    assert report.broker_submission_created is False


def test_journal_store_appends_reads_summarizes_lookup_and_tolerates_corrupt_lines(tmp_path):
    result = _service_result(tmp_path)
    store = MT5RequestDraftJournalStore(_config(tmp_path).journal_path)
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


def test_service_builds_draft_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.request_draft.request_draft_id
    assert result.validation_report.source_request_draft_id == result.request_draft.request_draft_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1
    assert (result.timings_ms or {})["mt5_request_draft_build_latency_ms"] >= 0


def test_formatter_creates_json_safe_card_and_markdown_summary(tmp_path):
    result = _service_result(tmp_path)
    formatter = MT5RequestDraftFormatter()
    card = formatter.to_card(result.request_draft, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.request_draft, result.validation_report, result.journal_record)
    assert card.fields["mt5_request_draft_final_approval_workflow_allowed"] is True
    assert card.fields["mt5_request_dict_created"] is False
    assert card.fields["mt5_constants_used"] is False
    assert card.fields["broker_submission_created"] is False
    assert "MT5 Request Draft Boundary" in markdown
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
def test_validator_rejects_unsafe_draft_flags(tmp_path, field_name):
    result = _service_result(tmp_path)
    setattr(result.request_draft, field_name, True)
    validation = MT5RequestDraftValidator(_config(tmp_path)).validate_request_draft(result.request_draft)
    assert validation.passed is False
    assert any(field_name in issue for issue in validation.issues)


@pytest.mark.parametrize(
    "field_name",
    [
        "draft_field_present",
        "draft_value_created",
        "draft_value_redacted",
        "raw_value_stored",
        "mt5_payload_value_created",
        "mt5_request_field_value_created",
        "mt5_constant_used",
        "executable_order_value",
        "broker_submission_value",
        "final_draft_approval_required",
    ],
)
def test_validator_rejects_unsafe_draft_field_flags(tmp_path, field_name):
    result = _service_result(tmp_path)
    unsafe_value = False if field_name in {"draft_field_present", "draft_value_redacted", "final_draft_approval_required"} else True
    setattr(result.request_draft.draft_fields[0], field_name, unsafe_value)
    validation = MT5RequestDraftValidator(_config(tmp_path)).validate_request_draft(result.request_draft)
    assert validation.passed is False
    assert any(field_name.replace("draft_", "") in issue or field_name in issue for issue in validation.issues)


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
        "broker_submission_payload",
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
    result.request_draft.draft_fields[0].blockers.append(marker)
    validation = MT5RequestDraftValidator(_config(tmp_path)).validate_request_draft(result.request_draft)
    assert validation.passed is False
    assert any("forbidden_marker" in issue for issue in validation.issues)


def test_dashboard_labels_and_buttons_are_request_draft_only():
    dashboard = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build MT5 Request Draft Boundary" in dashboard
    assert "does not create a real MT5 payload" in dashboard
    assert "does not create an MT5 request dictionary" in dashboard
    assert "does not use MT5 constants" in dashboard
    assert "does not call MT5" in dashboard
    assert "Confirm Trade" not in dashboard
    assert "Execute Trade" not in dashboard
    assert "Place Order" not in dashboard
    assert "Buy" not in dashboard
    assert "Sell" not in dashboard


def test_mt5_bridge_has_no_order_endpoints_and_no_request_draft_logic():
    server = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    forbidden_routes = ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]
    assert not any(route in server for route in forbidden_routes)
    assert "MT5RequestDraft" not in server
    assert "mt5_request_draft" not in server


def test_no_order_send_implementation_qdrant_or_rag_changes():
    execution_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in Path("src/services/trading/execution").rglob("*.py")
    )
    sanitized = execution_text.replace("order_send_allowed", "")
    assert "def order_send" not in sanitized
    assert "order_send(" not in sanitized
    assert "submit_live_order(" not in sanitized
    assert "send_order(" not in sanitized
    assert "place_order(" not in sanitized
    assert "execute_trade(" not in sanitized
    assert "qdrant reset" not in execution_text.lower()
    assert "delete qdrant" not in execution_text.lower()
    assert "Evidence" not in Path("src/services/trading/execution/mt5_request_draft/builder.py").read_text(
        encoding="utf-8"
    )
