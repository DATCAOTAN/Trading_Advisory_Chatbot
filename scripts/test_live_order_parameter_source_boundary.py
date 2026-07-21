from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_live_order_parameter_policy_validator import _sources as _policy_sources
from src.services.trading.execution.live_order_parameter_policy import (
    LiveOrderParameterPolicyConfig,
    LiveOrderParameterPolicyService,
)
from src.services.trading.execution.live_order_parameter_source import (
    LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_BLOCK_REASONS,
    LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_SCOPES,
    LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_STATUSES,
    LIVE_ORDER_PARAMETER_SOURCE_STATUSES,
    LIVE_ORDER_PARAMETER_SOURCE_TRUST_LEVELS,
    LIVE_ORDER_PARAMETER_SOURCE_TYPES,
    REQUIRED_SOURCE_CANDIDATE_MAP,
    LiveOrderParameterSourceBoundaryConfig,
    LiveOrderParameterSourceBoundaryFormatter,
    LiveOrderParameterSourceBoundaryGate,
    LiveOrderParameterSourceBoundaryService,
    LiveOrderParameterSourceBoundaryValidator,
    LiveOrderParameterSourceCandidateBuilder,
    LiveOrderParameterSourceJournalStore,
)


def _config(tmp_path: Path | None = None, **kwargs) -> LiveOrderParameterSourceBoundaryConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "live_order_parameter_sources.jsonl")}
    values.update(kwargs)
    return LiveOrderParameterSourceBoundaryConfig(**values)


def _policy_config(tmp_path: Path | None = None) -> LiveOrderParameterPolicyConfig:
    return LiveOrderParameterPolicyConfig(journal_path=str((tmp_path or Path("data")) / "live_order_parameter_policies.jsonl"))


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _policy_sources(tmp_path)
    policy_result = LiveOrderParameterPolicyService(config=_policy_config(tmp_path)).run(**sources)
    values = dict(
        parameter_policy_spec=policy_result.policy_spec,
        parameter_policy_validation=policy_result.validation_report,
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
    return LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_status_scope_source_type_trust_status_and_block_reason_values_exist():
    assert "SOURCE_BOUNDARY_VALIDATED" in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_STATUSES
    assert "HUMAN_REVIEWED_PARAMETER_DRAFT_ONLY" in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_SCOPES
    assert "MARKET_SNAPSHOT" in LIVE_ORDER_PARAMETER_SOURCE_TYPES
    assert "REQUIRED" in LIVE_ORDER_PARAMETER_SOURCE_TRUST_LEVELS
    assert "ALLOWED_AS_FUTURE_SOURCE" in LIVE_ORDER_PARAMETER_SOURCE_STATUSES
    assert "MISSING_PARAMETER_POLICY_SPEC" in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_BLOCK_REASONS


def test_candidate_boundary_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [candidate.as_dict() for candidate in result.boundary.source_candidates]
    payloads += [result.boundary.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "raw_candles" not in text
        assert "mt5_order_request" not in text


def test_config_defaults_enabled_and_requirements():
    config = LiveOrderParameterSourceBoundaryConfig()
    assert config.enabled is True
    assert config.require_policy_spec is True
    assert config.require_policy_validation is True
    assert config.require_source_boundary_allowed is True
    assert config.require_contract_skeleton is True
    assert config.require_live_order_intent is True
    assert config.require_permission_decision is True
    assert config.require_preflight_pass is True
    assert config.require_proposal_draft is True
    assert config.require_simulated_contract is True
    assert config.require_source_refs is True
    assert config.require_idempotency is True
    assert config.reject_resolved_values is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"parameter_policy_spec": None}, "MISSING_PARAMETER_POLICY_SPEC"),
        ({"parameter_policy_validation": None}, "MISSING_PARAMETER_POLICY_VALIDATION"),
        ({"contract_skeleton": None}, "MISSING_CONTRACT_SKELETON"),
        ({"live_order_intent": None}, "MISSING_LIVE_ORDER_INTENT"),
        ({"permission_decision": None}, "MISSING_PERMISSION_DECISION"),
        ({"preflight_report": None}, "MISSING_PREFLIGHT_REPORT"),
        ({"proposal_draft": None}, "MISSING_PROPOSAL_DRAFT"),
        ({"simulated_contract": None}, "MISSING_SIMULATED_CONTRACT"),
    ],
)
def test_missing_required_sources_block(tmp_path, override, reason):
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.boundary.blockers
    assert result.boundary.human_reviewed_parameter_draft_allowed is False


def test_invalid_policy_validation_and_source_boundary_false_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameter_policy_validation"].valid = False
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PARAMETER_POLICY_VALIDATION" in result.boundary.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_policy_validation"].parameter_source_boundary_allowed = False
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "PARAMETER_SOURCE_BOUNDARY_NOT_ALLOWED" in result.boundary.blockers


def test_preflight_not_pass_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.boundary.blockers


def test_missing_source_refs_and_idempotency_block(tmp_path):
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.boundary.blockers
    assert "MISSING_IDEMPOTENCY" in result.boundary.blockers


def test_resolved_and_actual_values_present_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameter_policy_spec"].resolved_parameter_values_present = True
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED" in result.boundary.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_policy_spec"].actual_order_values_present = True
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert "ACTUAL_ORDER_VALUES_NOT_ALLOWED" in result.boundary.blockers


def test_expired_and_duplicate_source_boundary_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_SOURCE_BOUNDARY" in result.boundary.blockers
    inputs = _inputs(tmp_path)
    first = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = LiveOrderParameterSourceBoundaryService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.boundary.status == "DUPLICATE"
    assert "DUPLICATE_SOURCE_BOUNDARY" in duplicate.boundary.blockers


def test_valid_inputs_create_boundary_with_safe_flags(tmp_path):
    result = _service_result(tmp_path)
    boundary = result.boundary
    validation = result.validation_report
    assert boundary.status == "SOURCE_BOUNDARY_VALIDATED"
    assert validation.valid is True
    assert validation.human_reviewed_parameter_draft_allowed is True
    for item in [boundary, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.resolved_parameter_values_present is False
        assert item.actual_order_values_present is False
    assert all(candidate.actual_value_allowed_now is False for candidate in boundary.source_candidates)
    assert all(candidate.value_resolved_now is False for candidate in boundary.source_candidates)


@pytest.mark.parametrize(
    ("group", "source_types"),
    sorted(REQUIRED_SOURCE_CANDIDATE_MAP.items()),
)
def test_candidate_builder_creates_required_source_types(group, source_types):
    candidates = LiveOrderParameterSourceCandidateBuilder().build_candidates(["source:test"])
    actual = {item.source_type for item in candidates if item.parameter_group == group}
    assert set(source_types).issubset(actual)
    assert all(item.actual_value_allowed_now is False and item.value_resolved_now is False for item in candidates)


def test_gate_valid_only_enables_human_reviewed_parameter_draft(tmp_path):
    result = _service_result(tmp_path)
    report = LiveOrderParameterSourceBoundaryGate(_config(tmp_path)).validate(result.boundary)
    assert report.valid is True
    assert report.human_reviewed_parameter_draft_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.actual_order_values_present is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = LiveOrderParameterSourceJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_validated == 1
    assert store.find_by_idempotency_key(result.boundary.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = LiveOrderParameterSourceJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_boundary_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.boundary.boundary_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = LiveOrderParameterSourceBoundaryFormatter()
    card = formatter.to_card(result.boundary, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.boundary, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["actual_order_values_present"] is False
    assert "human_reviewed_parameter_draft_allowed" in markdown
    assert "order_send_allowed: false" in markdown


@pytest.mark.parametrize(
    ("field_name", "issue"),
    [
        ("live_execution_allowed", "live_execution_allowed_must_be_false"),
        ("order_send_allowed", "order_send_allowed_must_be_false"),
        ("execution_allowed", "execution_allowed_must_be_false"),
        ("executable", "executable_must_be_false"),
        ("mt5_payload_created", "mt5_payload_created_must_be_false"),
        ("order_sent", "order_sent_must_be_false"),
        ("resolved_parameter_values_present", "resolved_parameter_values_present_must_be_false"),
        ("actual_order_values_present", "actual_order_values_present_must_be_false"),
    ],
)
def test_validator_rejects_unsafe_flags(tmp_path, field_name, issue):
    boundary = _service_result(tmp_path).boundary
    setattr(boundary, field_name, True)
    result = LiveOrderParameterSourceBoundaryValidator(_config(tmp_path)).validate_boundary(boundary)
    assert issue in result.issues


def test_validator_rejects_candidate_actual_value_flags(tmp_path):
    boundary = _service_result(tmp_path).boundary
    boundary.source_candidates[0].actual_value_allowed_now = True
    result = LiveOrderParameterSourceBoundaryValidator(_config(tmp_path)).validate_boundary(boundary)
    assert "candidate_actual_value_allowed_now_must_be_false" in result.issues
    boundary = _service_result(tmp_path).boundary
    boundary.source_candidates[0].value_resolved_now = True
    result = LiveOrderParameterSourceBoundaryValidator(_config(tmp_path)).validate_boundary(boundary)
    assert "candidate_value_resolved_now_must_be_false" in result.issues


@pytest.mark.parametrize(
    "marker",
    [
        "order_send",
        "submit_live_order",
        "send_order",
        "place_order",
        "execute_trade",
        "executable_order",
        "mt5_payload",
        "mt5_ticket",
        "deal_id",
        "trade_side",
        "side",
        "BUY",
        "SELL",
        "LONG",
        "SHORT",
        "entry",
        "entry_price",
        "stop_loss",
        "take_profit",
        "lot",
        "volume",
        "account_risk",
        "position_size",
        "raw_candles",
        "raw_full_book",
        "account_id",
        "credentials",
        "MetaTrader5",
        "llm_prompt",
    ],
)
def test_validator_rejects_forbidden_markers_in_blockers(tmp_path, marker):
    boundary = _service_result(tmp_path).boundary
    boundary.blockers = [marker]
    result = LiveOrderParameterSourceBoundaryValidator(_config(tmp_path)).validate_boundary(boundary)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_source_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Live Order Parameter Source Boundary" in text
    assert "This only defines allowed future parameter sources" in text
    assert "does not create actual order parameters" in text
    for forbidden in ['"Confirm Trade"', '"Execute Trade"', '"Place Order"', '"Buy"', '"Sell"']:
        assert forbidden not in text


def test_mt5_bridge_has_no_order_endpoints():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    for forbidden in ["/order", "/execute", "/send_order", "/order_send", "/trade", "/position/open"]:
        assert forbidden not in text


def test_no_order_send_implementation_and_no_rag_evidence_behavior_changed():
    source = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in Path("src/services/trading/execution").rglob("*.py"))
    assert "def order_send" not in source
    assert "qdrant.delete_collection" not in source.lower()
    assert "qdrant.recreate_collection" not in source.lower()
