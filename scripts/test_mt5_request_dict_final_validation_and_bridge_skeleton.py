from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.test_mt5_request_dict_dry_run_builder import _config as _dry_run_builder_config
from scripts.test_mt5_request_dict_dry_run_builder import _inputs as _dry_run_builder_inputs
from src.services.trading.execution.mt5_bridge_write_skeleton import (
    MT5BridgeWriteSkeletonCheckResult,
    MT5BridgeWriteSkeletonValidator,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder import MT5RequestDictDryRunBuilderService
from src.services.trading.execution.mt5_request_dict_final_validation import (
    MT5_REQUEST_DICT_FINAL_VALIDATION_BLOCK_REASONS,
    MT5_REQUEST_DICT_FINAL_VALIDATION_SCOPES,
    MT5_REQUEST_DICT_FINAL_VALIDATION_STATUSES,
    MT5RequestDictFinalValidationConfig,
    MT5RequestDictFinalValidationFormatter,
    MT5RequestDictFinalValidationJournalStore,
    MT5RequestDictFinalValidationService,
    MT5RequestDictFinalValidationValidator,
)
from tools.mt5_bridge.server import _blocked_write_skeleton_response


def _builder_config(tmp_path: Path):
    config = _dry_run_builder_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> MT5RequestDictFinalValidationConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "mt5_request_dict_final_validations.jsonl")}
    values.update(kwargs)
    return MT5RequestDictFinalValidationConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    builder_result = MT5RequestDictDryRunBuilderService(config=_builder_config(tmp_path or Path("data"))).run(
        **_dry_run_builder_inputs(tmp_path)
    )
    values = {
        "dry_run_builder_boundary": builder_result.boundary,
        "dry_run_builder_validation_report": builder_result.validation_report,
    }
    values.update(overrides)
    return values


def _service_result(tmp_path: Path):
    return MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_final_validation_enums_exist():
    assert "FINAL_VALIDATION_PASSED" in MT5_REQUEST_DICT_FINAL_VALIDATION_STATUSES
    assert "BRIDGE_WRITE_SKELETON_CHECK_ONLY" in MT5_REQUEST_DICT_FINAL_VALIDATION_SCOPES
    assert "ORDER_SEND_NOT_ALLOWED" in MT5_REQUEST_DICT_FINAL_VALIDATION_BLOCK_REASONS


def test_final_validation_artifacts_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [field.as_dict() for field in result.final_validation.validated_fields]
    payloads += [result.final_validation.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "raw_parameter_value" not in text
        assert "MetaTrader5" not in text
        assert "ORDER_TYPE_BUY" not in text
        assert "TRADE_ACTION_DEAL" not in text


def test_config_defaults_disabled_for_execution():
    config = MT5RequestDictFinalValidationConfig()
    assert config.enabled is True
    assert config.require_dry_run_builder_boundary is True
    assert config.require_dry_run_builder_validation_report is True
    assert config.require_workflow_allowed is True
    assert config.require_source_refs is True
    assert config.require_idempotency is True
    assert config.reject_raw_values is True
    assert config.reject_real_mt5_payload is True
    assert config.reject_broker_submittable_request_dict is True
    assert config.reject_mt5_constants is True
    assert config.reject_broker_submission is True
    assert config.reject_executable_order is True
    assert config.reject_order_send is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"dry_run_builder_boundary": None}, "MISSING_DRY_RUN_BUILDER_BOUNDARY"),
        ({"dry_run_builder_validation_report": None}, "MISSING_DRY_RUN_BUILDER_VALIDATION_REPORT"),
    ],
)
def test_required_sources_block(tmp_path, override, reason):
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.final_validation.blockers
    assert result.validation_report.valid is False


def test_valid_dry_run_builder_report_and_workflow_required(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["dry_run_builder_validation_report"].valid = False
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_DRY_RUN_BUILDER_VALIDATION_REPORT" in result.final_validation.blockers
    inputs = _inputs(tmp_path)
    inputs["dry_run_builder_validation_report"].mt5_request_dict_final_validation_workflow_allowed = False
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert "REQUEST_DICT_FINAL_VALIDATION_WORKFLOW_NOT_ALLOWED" in result.final_validation.blockers


def test_refs_idempotency_and_missing_fields_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["dry_run_builder_boundary"].source_refs = []
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.final_validation.blockers
    inputs = _inputs(tmp_path)
    inputs["dry_run_builder_boundary"].idempotency_key = ""
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_IDEMPOTENCY" in result.final_validation.blockers
    inputs = _inputs(tmp_path)
    inputs["dry_run_builder_boundary"].dry_run_fields = inputs["dry_run_builder_boundary"].dry_run_fields[:11]
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_REQUIRED_DRY_RUN_FIELDS" in result.final_validation.blockers


@pytest.mark.parametrize(
    ("field_name", "reason"),
    [
        ("raw_values_stored", "RAW_VALUES_NOT_ALLOWED"),
        ("real_mt5_payload_created", "REAL_MT5_PAYLOAD_NOT_ALLOWED"),
        ("broker_submittable_request_dict_created", "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED"),
        ("mt5_constants_used", "MT5_CONSTANT_NOT_ALLOWED"),
        ("broker_submission_created", "BROKER_SUBMISSION_NOT_ALLOWED"),
        ("executable_order_created", "EXECUTABLE_ORDER_NOT_ALLOWED"),
        ("order_send_allowed", "ORDER_SEND_NOT_ALLOWED"),
    ],
)
def test_unsafe_builder_flags_block(tmp_path, field_name, reason):
    inputs = _inputs(tmp_path)
    setattr(inputs["dry_run_builder_boundary"], field_name, True)
    result = MT5RequestDictFinalValidationService(config=_config(tmp_path)).run(**inputs)
    assert reason in result.final_validation.blockers


def test_valid_boundary_creates_final_validation_with_safety_flags(tmp_path):
    result = _service_result(tmp_path)
    boundary = result.final_validation
    report = result.validation_report
    assert boundary.status == "FINAL_VALIDATION_PASSED"
    assert report.valid is True
    assert report.bridge_write_skeleton_check_allowed is True
    assert report.validated_fields_count == 12
    assert report.missing_fields_count == 0
    assert report.invalid_fields_count == 0
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
    for field in boundary.validated_fields:
        assert field.validation_passed is True
        assert field.schema_only is True
        assert field.concrete_value_created is False
        assert field.value_redacted is True
        assert field.raw_value_stored is False
        assert field.real_mt5_payload_value_created is False
        assert field.broker_submittable_request_field_created is False
        assert field.mt5_constant_used is False
        assert field.executable_order_value is False
        assert field.broker_submission_value is False


def test_journal_store_appends_reads_and_warns_on_corrupt_jsonl(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    store = MT5RequestDictFinalValidationJournalStore(_config(tmp_path).journal_path)
    assert len(store.read_latest()) == 1
    assert store.summarize().total_records == 1
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{bad-json}\n")
    assert len(store.read_latest()) == 1
    assert store.summarize().warnings


def test_formatter_emits_safe_summary(tmp_path):
    result = _service_result(tmp_path)
    card = MT5RequestDictFinalValidationFormatter().to_card(
        result.final_validation,
        result.validation_report,
        result.journal_record,
    ).as_dict()
    markdown = MT5RequestDictFinalValidationFormatter().to_markdown_summary(
        result.final_validation,
        result.validation_report,
        result.journal_record,
    )
    assert card["fields"]["bridge_write_skeleton_check_allowed"] is True
    assert "FINAL_VALIDATION_PASSED" in markdown
    assert "MetaTrader5" not in json.dumps(card, sort_keys=True)


@pytest.mark.parametrize("marker", ["order_send", "real_mt5_payload", "broker_submittable_request_dict", "MetaTrader5"])
def test_validator_rejects_forbidden_markers(tmp_path, marker):
    result = _service_result(tmp_path)
    result.final_validation.warnings.append(marker)
    validation = MT5RequestDictFinalValidationValidator(_config(tmp_path)).validate_boundary(
        result.final_validation,
        _inputs(tmp_path)["dry_run_builder_validation_report"],
    )
    assert validation.passed is False


def test_bridge_endpoint_response_is_blocked_and_redacted():
    payload = _blocked_write_skeleton_response()
    assert payload["status"] == "BLOCKED"
    assert payload["endpoint"] == "/execution/write-skeleton/check"
    assert payload["write_skeleton_available"] is True
    assert payload["live_execution_allowed"] is False
    assert payload["order_send_allowed"] is False
    assert payload["execution_allowed"] is False
    assert payload["hard_live_block_required"] is True
    assert payload["order_sent"] is False
    assert payload["ticket"] is None
    assert payload["deal"] is None
    assert payload["metadata_redacted"] is True


def test_app_side_bridge_skeleton_validator_accepts_blocked_response():
    result = MT5BridgeWriteSkeletonCheckResult(
        check_id="check",
        created_at="2026-07-20T00:00:00+00:00",
        bridge_url="http://127.0.0.1:8765",
        endpoint="/execution/write-skeleton/check",
        reachable=True,
        status="BLOCKED",
        write_skeleton_available=True,
        live_execution_allowed=False,
        order_send_allowed=False,
        execution_allowed=False,
        hard_live_block_required=True,
        order_sent=False,
        ticket=None,
        deal=None,
        metadata_redacted=True,
    )
    assert MT5BridgeWriteSkeletonValidator().validate(result).passed is True


def test_static_ui_bridge_and_source_safety():
    dashboard_text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    bridge_text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    src_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path("src").rglob("*.py"))
    assert "Validate MT5 Request Dict Boundary" in dashboard_text
    assert "Check MT5 Bridge Write Skeleton" in dashboard_text
    assert "Confirm Trade" not in dashboard_text
    assert "Execute Trade" not in dashboard_text
    assert "Place Order" not in dashboard_text
    assert "Buy" not in dashboard_text
    assert "Sell" not in dashboard_text
    assert "/execution/write-skeleton/check" in bridge_text
    for endpoint in ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]:
        assert endpoint not in bridge_text
    assert ".order_send(" not in bridge_text
    assert "import MetaTrader5" not in src_text
    assert "from MetaTrader5" not in src_text
    assert "Evidence" not in Path("src/services/trading/execution/mt5_request_dict_final_validation").read_text(
        encoding="utf-8",
        errors="ignore",
    ) if Path("src/services/trading/execution/mt5_request_dict_final_validation").is_file() else True
    assert "qdrant_client.delete_collection" not in src_text
    assert "recreate_collection" not in src_text
