from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_live_order_contract_parameterization import _config as _parameterization_config
from scripts.test_live_order_contract_parameterization import _inputs as _parameterization_inputs
from src.services.trading.execution.live_order_contract_final_review import (
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    LIVE_ORDER_CONTRACT_FINAL_REVIEW_ACTIONS,
    LIVE_ORDER_CONTRACT_FINAL_REVIEW_BLOCK_REASONS,
    LIVE_ORDER_CONTRACT_FINAL_REVIEW_SCOPES,
    LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATES,
    LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATUSES,
    LIVE_ORDER_CONTRACT_SLOT_VALIDATION_STATUSES,
    LIVE_ORDER_CONTRACT_VALIDATION_SEVERITIES,
    REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES,
    LiveOrderContractFinalReviewConfig,
    LiveOrderContractFinalReviewConfirmationService,
    LiveOrderContractFinalReviewFormatter,
    LiveOrderContractFinalReviewGate,
    LiveOrderContractFinalReviewJournalStore,
    LiveOrderContractFinalReviewService,
    LiveOrderContractFinalReviewValidator,
    LiveOrderContractSlotValidationBuilder,
)
from src.services.trading.execution.live_order_contract_parameterization import (
    LiveOrderContractParameterizationService,
)


def _param_config(tmp_path: Path | None = None):
    config = _parameterization_config(tmp_path)
    config.journal_enabled = False
    return config


def _config(tmp_path: Path | None = None, **kwargs) -> LiveOrderContractFinalReviewConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "live_order_contract_final_reviews.jsonl")}
    values.update(kwargs)
    return LiveOrderContractFinalReviewConfig(**values)


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _parameterization_inputs(tmp_path)
    parameterization_result = LiveOrderContractParameterizationService(config=_param_config(tmp_path)).run(**sources)
    values = dict(
        parameterization=parameterization_result.parameterization,
        parameterization_validation=parameterization_result.validation_report,
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
        confirmation_phrase=EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    )
    values.update(overrides)
    return values


def _service_result(tmp_path: Path):
    return LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_enum_values_exist():
    assert "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY" in LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATUSES
    assert "PRE_MT5_MAPPING_BOUNDARY_ONLY" in LIVE_ORDER_CONTRACT_FINAL_REVIEW_SCOPES
    assert "APPROVE_FOR_FUTURE_PRE_MT5_MAPPING_ONLY" in LIVE_ORDER_CONTRACT_FINAL_REVIEW_ACTIONS
    assert "HUMAN_REVIEW_APPROVED_FOR_FUTURE_MAPPING_ONLY" in LIVE_ORDER_CONTRACT_FINAL_REVIEW_STATES
    assert "INFO" in LIVE_ORDER_CONTRACT_VALIDATION_SEVERITIES
    assert "VALIDATION_ONLY_READY" in LIVE_ORDER_CONTRACT_SLOT_VALIDATION_STATUSES
    assert "PRE_MT5_MAPPING_NOT_ALLOWED" in LIVE_ORDER_CONTRACT_FINAL_REVIEW_BLOCK_REASONS


def test_confirmation_slot_validation_final_review_report_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    confirmation = LiveOrderContractFinalReviewConfirmationService(_config(tmp_path)).confirm(
        EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE
    )
    assert result.journal_record is not None
    payloads = [confirmation.as_dict()]
    payloads += [slot.as_dict() for slot in result.final_review.slot_validations]
    payloads += [result.final_review.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE not in text
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "broker_mapping_payload" not in text


def test_config_defaults_enabled_and_requirements():
    config = LiveOrderContractFinalReviewConfig()
    assert config.enabled is True
    assert config.require_parameterization is True
    assert config.require_parameterization_validation is True
    assert config.require_contract_validation_workflow_allowed is True
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
    assert config.require_exact_confirmation is True
    assert config.reject_raw_values is True
    assert config.reject_broker_mapping is True


def test_exact_wrong_case_missing_and_expired_confirmation_behavior():
    service = LiveOrderContractFinalReviewConfirmationService(LiveOrderContractFinalReviewConfig())
    exact = service.confirm(EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE)
    assert exact.phrase_valid is True
    assert exact.action == "APPROVE_FOR_FUTURE_PRE_MT5_MAPPING_ONLY"
    wrong = service.confirm("wrong phrase")
    assert wrong.phrase_valid is False
    assert "WRONG_CONFIRMATION_PHRASE" in wrong.blockers
    case_mismatch = service.confirm(EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE.upper())
    assert case_mismatch.phrase_valid is False
    missing = service.confirm(None)
    assert missing.phrase_valid is False
    expired = LiveOrderContractFinalReviewConfirmationService(LiveOrderContractFinalReviewConfig(ttl_seconds=-1)).confirm(
        EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE
    )
    assert "CONFIRMATION_EXPIRED" in expired.blockers
    assert expired.phrase_valid is False


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"parameterization": None}, "MISSING_PARAMETERIZATION"),
        ({"parameterization_validation": None}, "MISSING_PARAMETERIZATION_VALIDATION"),
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
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.final_review.blockers
    assert result.final_review.pre_mt5_mapping_boundary_workflow_allowed is False


def test_parameterization_validation_workflow_preflight_refs_idempotency_and_confirmation_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameterization_validation"].valid = False
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PARAMETERIZATION_VALIDATION" in result.final_review.blockers
    inputs = _inputs(tmp_path)
    inputs["parameterization_validation"].contract_validation_workflow_allowed = False
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert "CONTRACT_VALIDATION_WORKFLOW_NOT_ALLOWED" in result.final_review.blockers
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.final_review.blockers
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.final_review.blockers
    assert "MISSING_IDEMPOTENCY" in result.final_review.blockers
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(
        **_inputs(tmp_path, confirmation_phrase="not exact")
    )
    assert "WRONG_CONFIRMATION_PHRASE" in result.final_review.blockers


def test_raw_executable_payload_order_ready_mapping_and_broker_mapping_block(tmp_path):
    for field_name, reason in [
        ("raw_values_stored", "RAW_VALUES_NOT_ALLOWED"),
        ("executable_order_created", "EXECUTABLE_ORDER_NOT_ALLOWED"),
        ("mt5_payload_created", "MT5_PAYLOAD_NOT_ALLOWED"),
        ("order_contract_ready", "ORDER_CONTRACT_READY_NOT_ALLOWED"),
        ("order_request_mapping_allowed", "ORDER_REQUEST_MAPPING_NOT_ALLOWED"),
        ("broker_mapping_created", "PRE_MT5_MAPPING_NOT_ALLOWED"),
    ]:
        inputs = _inputs(tmp_path)
        setattr(inputs["parameterization"], field_name, True)
        result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
        assert reason in result.final_review.blockers


def test_expired_and_duplicate_final_review_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_FINAL_REVIEW" in result.final_review.blockers
    inputs = _inputs(tmp_path)
    first = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = LiveOrderContractFinalReviewService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.final_review.status == "DUPLICATE"
    assert "DUPLICATE_FINAL_REVIEW" in duplicate.final_review.blockers


def test_valid_inputs_create_final_review_with_safe_flags_and_exactly_nine_slot_validations(tmp_path):
    result = _service_result(tmp_path)
    final_review = result.final_review
    validation = result.validation_report
    assert final_review.status == "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY"
    assert validation.valid is True
    assert validation.pre_mt5_mapping_boundary_workflow_allowed is True
    assert validation.confirmation_phrase_valid is True
    for item in [final_review, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.order_request_mapping_allowed is False
        assert item.broker_mapping_created is False
        assert item.raw_values_stored is False
        assert item.executable_order_created is False
    assert len(final_review.slot_validations) == 9
    assert final_review.required_slot_validation_types == REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES
    assert all(slot.raw_value_stored is False for slot in final_review.slot_validations)
    assert all(slot.executable_value is False for slot in final_review.slot_validations)
    assert all(slot.mt5_payload_value is False for slot in final_review.slot_validations)
    assert all(slot.order_request_value is False for slot in final_review.slot_validations)
    assert all(slot.broker_mapping_created is False for slot in final_review.slot_validations)
    assert all(slot.validation_only_ready is True for slot in final_review.slot_validations)
    assert all(slot.final_human_review_required is True for slot in final_review.slot_validations)


def test_slot_validation_builder_creates_required_validation_types(tmp_path):
    parameterization = _inputs(tmp_path)["parameterization"]
    slots = LiveOrderContractSlotValidationBuilder().build_slot_validations(parameterization, ["source:test"])
    assert [slot.slot_type for slot in slots] == REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES
    assert all(slot.source_contract_slot_id for slot in slots)
    assert all(slot.source_slot_lock_id for slot in slots)
    assert all(slot.source_value_slot_id for slot in slots)
    assert all(slot.validation_only_ready is True for slot in slots)
    assert all(slot.final_human_review_required is True for slot in slots)


def test_gate_valid_only_enables_future_pre_mt5_mapping_boundary_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = LiveOrderContractFinalReviewGate(_config(tmp_path)).validate(result.final_review)
    assert report.valid is True
    assert report.pre_mt5_mapping_boundary_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.order_contract_ready is False
    assert report.order_request_mapping_allowed is False
    assert report.broker_mapping_created is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = LiveOrderContractFinalReviewJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_approved == 1
    assert store.find_by_idempotency_key(result.final_review.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = LiveOrderContractFinalReviewJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_final_review_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.final_review.final_review_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = LiveOrderContractFinalReviewFormatter()
    card = formatter.to_card(result.final_review, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.final_review, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["broker_mapping_created"] is False
    assert card.as_dict()["fields"]["order_request_mapping_allowed"] is False
    assert "pre_mt5_mapping_boundary_workflow_allowed" in markdown
    assert "`order_send_allowed`: false" in markdown
    assert EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE not in markdown


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
        ("broker_mapping_created", "broker_mapping_created_must_be_false", True),
        ("raw_values_stored", "raw_values_stored_must_be_false", True),
        ("executable_order_created", "executable_order_created_must_be_false", True),
    ],
)
def test_validator_rejects_unsafe_flags(tmp_path, field_name, issue, value):
    final_review = _service_result(tmp_path).final_review
    setattr(final_review, field_name, value)
    result = LiveOrderContractFinalReviewValidator(_config(tmp_path)).validate_final_review(final_review)
    assert issue in result.issues


@pytest.mark.parametrize(
    ("slot_field", "issue"),
    [
        ("raw_value_stored", "slot_raw_value_stored_must_be_false"),
        ("executable_value", "slot_executable_value_must_be_false"),
        ("mt5_payload_value", "slot_mt5_payload_value_must_be_false"),
        ("order_request_value", "slot_order_request_value_must_be_false"),
        ("broker_mapping_created", "slot_broker_mapping_created_must_be_false"),
    ],
)
def test_validator_rejects_slot_unsafe_flags_and_missing_hard_block(tmp_path, slot_field, issue):
    final_review = _service_result(tmp_path).final_review
    setattr(final_review.slot_validations[0], slot_field, True)
    result = LiveOrderContractFinalReviewValidator(_config(tmp_path)).validate_final_review(final_review)
    assert issue in result.issues
    final_review = _service_result(tmp_path).final_review
    final_review.hard_live_block_required = False
    result = LiveOrderContractFinalReviewValidator(_config(tmp_path)).validate_final_review(final_review)
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
        "broker_order_mapping",
        "broker_mapping_payload",
        "raw_account_id",
        "raw_parameter_value",
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
    final_review = _service_result(tmp_path).final_review
    final_review.blockers = [marker]
    result = LiveOrderContractFinalReviewValidator(_config(tmp_path)).validate_final_review(final_review)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_pre_mt5_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Contract Final Review" in text
    assert "future Pre-MT5 mapping boundary" in text
    assert "does not create broker mapping" in text
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
