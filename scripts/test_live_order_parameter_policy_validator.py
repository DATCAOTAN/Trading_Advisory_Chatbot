from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_live_order_contract_skeleton import (
    _build as _build_skeleton,
    _contract,
    _draft,
    _intent_validation,
    _order_intent,
    _permission_decision,
    _preflight,
    _receipt,
)
from src.services.trading.execution.live_order_contract import LiveOrderContractSkeletonGate
from src.services.trading.execution.live_order_parameter_policy import (
    LIVE_ORDER_PARAMETER_POLICY_BLOCK_REASONS,
    LIVE_ORDER_PARAMETER_POLICY_GROUPS,
    LIVE_ORDER_PARAMETER_POLICY_RULE_STATUSES,
    LIVE_ORDER_PARAMETER_POLICY_SCOPES,
    LIVE_ORDER_PARAMETER_POLICY_SEVERITIES,
    LIVE_ORDER_PARAMETER_POLICY_STATUSES,
    REQUIRED_PARAMETER_POLICY_GROUP_LABELS,
    LiveOrderParameterPolicyConfig,
    LiveOrderParameterPolicyFormatter,
    LiveOrderParameterPolicyGate,
    LiveOrderParameterPolicyJournalStore,
    LiveOrderParameterPolicyRuleBuilder,
    LiveOrderParameterPolicyService,
    LiveOrderParameterPolicySpecBuilder,
    LiveOrderParameterPolicyValidator,
)


def _config(tmp_path: Path | None = None, **kwargs) -> LiveOrderParameterPolicyConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "live_order_parameter_policies.jsonl")}
    values.update(kwargs)
    return LiveOrderParameterPolicyConfig(**values)


def _sources(tmp_path: Path | None = None, **overrides):
    skeleton = _build_skeleton(tmp_path)
    skeleton_validation = LiveOrderContractSkeletonGate().validate(skeleton)
    values = dict(
        contract_skeleton=skeleton,
        contract_skeleton_validation=skeleton_validation,
        live_order_intent=_order_intent(),
        live_order_intent_validation=_intent_validation(),
        permission_decision=_permission_decision(),
        preflight_report=_preflight(),
        proposal_draft=_draft(),
        simulated_contract=_contract(),
        simulated_receipt=_receipt(),
    )
    values.update(overrides)
    return values


def _spec(tmp_path: Path | None = None, **overrides):
    sources = _sources(tmp_path)
    sources.update(overrides)
    return LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)


def _service_result(tmp_path: Path):
    return LiveOrderParameterPolicyService(config=_config(tmp_path)).run(**_sources(tmp_path))


def test_status_scope_group_rule_severity_and_block_reason_values_exist():
    assert "POLICY_VALIDATED" in LIVE_ORDER_PARAMETER_POLICY_STATUSES
    assert "PARAMETER_SOURCE_BOUNDARY_ONLY" in LIVE_ORDER_PARAMETER_POLICY_SCOPES
    assert set(REQUIRED_PARAMETER_POLICY_GROUP_LABELS).issubset(LIVE_ORDER_PARAMETER_POLICY_GROUPS)
    assert "SATISFIED_AS_POLICY_ONLY" in LIVE_ORDER_PARAMETER_POLICY_RULE_STATUSES
    assert "BLOCKING" in LIVE_ORDER_PARAMETER_POLICY_SEVERITIES
    assert "MISSING_CONTRACT_SKELETON" in LIVE_ORDER_PARAMETER_POLICY_BLOCK_REASONS


def test_rule_spec_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [rule.as_dict() for rule in result.policy_spec.policy_rules]
    payloads += [result.policy_spec.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        json.dumps(payload, sort_keys=True)
        text = json.dumps(payload)
        assert "raw_account_id" not in text
        assert "raw_candles" not in text
        assert "mt5_order_request" not in text


def test_policy_defaults_enabled_and_requirements():
    config = LiveOrderParameterPolicyConfig()
    assert config.enabled is True
    assert config.require_contract_skeleton is True
    assert config.require_valid_contract_skeleton is True
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
        ({"contract_skeleton": None}, "MISSING_CONTRACT_SKELETON"),
        ({"contract_skeleton_validation": None}, "MISSING_CONTRACT_SKELETON_VALIDATION"),
        ({"live_order_intent": None}, "MISSING_LIVE_ORDER_INTENT"),
        ({"permission_decision": None}, "MISSING_PERMISSION_DECISION"),
        ({"preflight_report": None}, "MISSING_PREFLIGHT_REPORT"),
        ({"proposal_draft": None}, "MISSING_PROPOSAL_DRAFT"),
        ({"simulated_contract": None}, "MISSING_SIMULATED_CONTRACT"),
    ],
)
def test_missing_required_sources_block(tmp_path, override, reason):
    spec = _spec(tmp_path, **override)
    assert reason in spec.blockers
    assert spec.parameter_source_boundary_allowed is False


def test_invalid_contract_skeleton_validation_blocks(tmp_path):
    sources = _sources(tmp_path)
    sources["contract_skeleton_validation"].valid = False
    spec = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)
    assert "MISSING_CONTRACT_SKELETON_VALIDATION" in spec.blockers


def test_contract_parameter_validation_false_blocks(tmp_path):
    sources = _sources(tmp_path)
    sources["contract_skeleton_validation"].contract_parameter_validation_allowed = False
    spec = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)
    assert "CONTRACT_PARAMETER_VALIDATION_NOT_ALLOWED" in spec.blockers


def test_preflight_not_pass_blocks(tmp_path):
    spec = _spec(tmp_path, preflight_report=_preflight(preflight_status="FAIL"))
    assert "MISSING_PREFLIGHT_REPORT" in spec.blockers


def test_missing_parameter_groups_blocks(tmp_path):
    sources = _sources(tmp_path)
    sources["contract_skeleton"].required_parameter_groups = []
    spec = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)
    assert "MISSING_PARAMETER_GROUPS" in spec.blockers


def test_resolved_parameter_values_present_blocks(tmp_path):
    sources = _sources(tmp_path)
    sources["contract_skeleton"].resolved_parameter_groups = ["SIDE_POLICY"]
    spec = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)
    assert "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED" in spec.blockers


def test_missing_source_refs_and_idempotency_block(tmp_path):
    sources = _sources(tmp_path)
    for item in [
        sources["contract_skeleton"],
        sources["contract_skeleton_validation"],
        sources["live_order_intent"],
        sources["live_order_intent_validation"],
        sources["permission_decision"],
        sources["preflight_report"],
        sources["proposal_draft"],
        sources["simulated_contract"],
        sources["simulated_receipt"],
    ]:
        item.source_refs = []
    sources["contract_skeleton"].artifact_hash = ""
    sources["contract_skeleton"].idempotency_key = ""
    sources["live_order_intent"].artifact_hash = ""
    sources["live_order_intent"].idempotency_key = ""
    sources["simulated_contract"].artifact_hash = ""
    sources["simulated_contract"].idempotency_key = ""
    sources["simulated_receipt"].artifact_hash = ""
    sources["simulated_receipt"].idempotency_key = ""
    spec = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(**sources)
    assert "MISSING_SOURCE_REFS" in spec.blockers
    assert "MISSING_IDEMPOTENCY" in spec.blockers


def test_expired_policy_spec_blocks(tmp_path):
    too_late = LiveOrderParameterPolicySpecBuilder(_config(tmp_path)).build(
        **_sources(tmp_path),
        current_time=datetime.now(timezone.utc) + timedelta(seconds=999),
    )
    assert "EXPIRED_POLICY_SPEC" in too_late.blockers


def test_duplicate_policy_spec_blocks(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    duplicate = LiveOrderParameterPolicyService(config=_config(tmp_path)).run(**_sources(tmp_path))
    assert duplicate.policy_spec.status == "DUPLICATE"
    assert "DUPLICATE_POLICY_SPEC" in duplicate.policy_spec.blockers


def test_valid_inputs_create_policy_spec_with_safe_flags(tmp_path):
    result = _service_result(tmp_path)
    spec = result.policy_spec
    validation = result.validation_report
    assert spec.status == "POLICY_VALIDATED"
    assert validation.valid is True
    assert validation.parameter_source_boundary_allowed is True
    for item in [spec, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.resolved_parameter_values_present is False
        assert item.actual_order_values_present is False


@pytest.mark.parametrize("group", REQUIRED_PARAMETER_POLICY_GROUP_LABELS)
def test_rule_builder_creates_all_policy_groups_as_policy_only(group):
    rules = LiveOrderParameterPolicyRuleBuilder().build_rules(["source:test"])
    rule = next(item for item in rules if item.group == group)
    assert rule.status == "SATISFIED_AS_POLICY_ONLY"
    assert rule.required is True
    assert rule.blocking is True
    assert rule.future_source_boundary_required is True
    assert rule.deterministic_validation_required is True
    assert rule.future_evidence_required


def test_gate_valid_only_enables_parameter_source_boundary(tmp_path):
    spec = _spec(tmp_path)
    report = LiveOrderParameterPolicyGate(_config(tmp_path)).validate(spec)
    assert report.valid is True
    assert report.parameter_source_boundary_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.actual_order_values_present is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = LiveOrderParameterPolicyJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_validated == 1
    assert store.find_by_idempotency_key(result.policy_spec.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = LiveOrderParameterPolicyJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_spec_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.policy_spec.policy_spec_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = LiveOrderParameterPolicyFormatter()
    card = formatter.to_card(result.policy_spec, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.policy_spec, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["actual_order_values_present"] is False
    assert "parameter_source_boundary_allowed" in markdown
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
    spec = _spec(tmp_path)
    setattr(spec, field_name, True)
    result = LiveOrderParameterPolicyValidator(_config(tmp_path)).validate_spec(spec)
    assert issue in result.issues


@pytest.mark.parametrize(
    "marker",
    [
        "order_send",
        "submit_live_order",
        "send_order",
        "place_order",
        "execute_trade",
        "executable_order",
        "mt5_order_payload",
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
    spec = _spec(tmp_path)
    spec.blockers = [marker]
    result = LiveOrderParameterPolicyValidator(_config(tmp_path)).validate_spec(spec)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_policy_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Validate Live Order Parameter Policies" in text
    assert "This only validates parameter policies" in text
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
