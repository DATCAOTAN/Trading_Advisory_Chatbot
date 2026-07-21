from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_live_order_parameter_source_boundary import _inputs as _source_inputs
from src.services.trading.execution.live_order_parameter_source import (
    LiveOrderParameterSourceBoundaryConfig,
    LiveOrderParameterSourceBoundaryService,
)
from src.services.trading.execution.live_parameter_draft import (
    HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_BLOCK_REASONS,
    HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_SCOPES,
    HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_STATUSES,
    HUMAN_REVIEWED_PARAMETER_REVIEW_REQUIREMENTS,
    HUMAN_REVIEWED_PARAMETER_SLOT_STATUSES,
    HUMAN_REVIEWED_PARAMETER_SLOT_TYPES,
    REQUIRED_HUMAN_REVIEWED_SLOT_MAP,
    REQUIRED_HUMAN_REVIEWED_SLOT_TYPES,
    HumanReviewedLiveParameterDraftConfig,
    HumanReviewedLiveParameterDraftFormatter,
    HumanReviewedLiveParameterDraftGate,
    HumanReviewedLiveParameterDraftService,
    HumanReviewedLiveParameterDraftValidator,
    HumanReviewedParameterSlotBuilder,
    HumanReviewedLiveParameterDraftJournalStore,
)


def _config(tmp_path: Path | None = None, **kwargs) -> HumanReviewedLiveParameterDraftConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "human_reviewed_live_parameter_drafts.jsonl")}
    values.update(kwargs)
    return HumanReviewedLiveParameterDraftConfig(**values)


def _source_config(tmp_path: Path | None = None) -> LiveOrderParameterSourceBoundaryConfig:
    return LiveOrderParameterSourceBoundaryConfig(journal_path=str((tmp_path or Path("data")) / "live_order_parameter_sources.jsonl"))


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _source_inputs(tmp_path)
    source_result = LiveOrderParameterSourceBoundaryService(config=_source_config(tmp_path)).run(**sources)
    values = dict(
        parameter_source_boundary=source_result.boundary,
        parameter_source_validation=source_result.validation_report,
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
    return HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_status_scope_slot_status_review_requirement_and_block_reason_values_exist():
    assert "DRAFT_CREATED" in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_STATUSES
    assert "VALUE_PROPOSAL_WORKFLOW_ONLY" in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_SCOPES
    assert "SIDE_SLOT" in HUMAN_REVIEWED_PARAMETER_SLOT_TYPES
    assert "UNRESOLVED" in HUMAN_REVIEWED_PARAMETER_SLOT_STATUSES
    assert "HUMAN_REVIEW_REQUIRED" in HUMAN_REVIEWED_PARAMETER_REVIEW_REQUIREMENTS
    assert "MISSING_SOURCE_BOUNDARY" in HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_BLOCK_REASONS


def test_slot_draft_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [slot.as_dict() for slot in result.draft.slots]
    payloads += [result.draft.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "raw_candles" not in text
        assert "mt5_order_request" not in text


def test_config_defaults_enabled_and_requirements():
    config = HumanReviewedLiveParameterDraftConfig()
    assert config.enabled is True
    assert config.require_source_boundary is True
    assert config.require_source_boundary_validation is True
    assert config.require_human_review_allowed is True
    assert config.require_policy_spec is True
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
        ({"parameter_source_boundary": None}, "MISSING_SOURCE_BOUNDARY"),
        ({"parameter_source_validation": None}, "MISSING_SOURCE_BOUNDARY_VALIDATION"),
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
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.draft.blockers
    assert result.draft.value_proposal_workflow_allowed is False


def test_invalid_source_boundary_validation_and_allowed_false_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameter_source_validation"].valid = False
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_BOUNDARY_VALIDATION" in result.draft.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_source_validation"].human_reviewed_parameter_draft_allowed = False
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "HUMAN_REVIEWED_PARAMETER_DRAFT_NOT_ALLOWED" in result.draft.blockers


def test_preflight_not_pass_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.draft.blockers


def test_missing_source_refs_and_idempotency_block(tmp_path):
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.draft.blockers
    assert "MISSING_IDEMPOTENCY" in result.draft.blockers


def test_resolved_actual_and_slot_values_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameter_source_boundary"].resolved_parameter_values_present = True
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED" in result.draft.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_source_boundary"].actual_order_values_present = True
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert "ACTUAL_ORDER_VALUES_NOT_ALLOWED" in result.draft.blockers

    class BadSlotBuilder(HumanReviewedParameterSlotBuilder):
        def build_slots(self, source_boundary, source_refs=None):
            slots = super().build_slots(source_boundary, source_refs)
            slots[0].value_allowed_now = True
            return slots

    service = HumanReviewedLiveParameterDraftService(
        config=_config(tmp_path),
        builder=None,
    )
    service.builder.slot_builder = BadSlotBuilder()
    result = service.run(**_inputs(tmp_path))
    assert "SLOT_VALUE_NOT_ALLOWED" in result.draft.blockers


def test_expired_and_duplicate_draft_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_PARAMETER_DRAFT" in result.draft.blockers
    inputs = _inputs(tmp_path)
    first = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = HumanReviewedLiveParameterDraftService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.draft.status == "DUPLICATE"
    assert "DUPLICATE_PARAMETER_DRAFT" in duplicate.draft.blockers


def test_valid_inputs_create_draft_with_safe_flags_and_exactly_nine_unresolved_slots(tmp_path):
    result = _service_result(tmp_path)
    draft = result.draft
    validation = result.validation_report
    assert draft.status == "DRAFT_CREATED"
    assert validation.valid is True
    assert validation.value_proposal_workflow_allowed is True
    for item in [draft, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.resolved_parameter_values_present is False
        assert item.actual_order_values_present is False
    assert len(draft.slots) == 9
    assert draft.required_slot_types == REQUIRED_HUMAN_REVIEWED_SLOT_TYPES
    assert draft.unresolved_slot_types == REQUIRED_HUMAN_REVIEWED_SLOT_TYPES
    assert draft.resolved_slot_types == []
    assert all(slot.value_allowed_now is False for slot in draft.slots)
    assert all(slot.value_resolved_now is False for slot in draft.slots)
    assert all(slot.actual_value_present is False for slot in draft.slots)


@pytest.mark.parametrize(("slot_type", "parameter_group"), sorted(REQUIRED_HUMAN_REVIEWED_SLOT_MAP.items()))
def test_slot_builder_creates_required_slot_types(slot_type, parameter_group, tmp_path):
    boundary = _inputs(tmp_path)["parameter_source_boundary"]
    slots = HumanReviewedParameterSlotBuilder().build_slots(boundary, ["source:test"])
    slot = next(item for item in slots if item.slot_type == slot_type)
    assert slot.parameter_group == parameter_group
    assert slot.status == "UNRESOLVED"
    assert slot.value_allowed_now is False
    assert slot.value_resolved_now is False
    assert slot.actual_value_present is False
    assert slot.source_candidate_ids
    assert slot.source_refs


def test_gate_valid_only_enables_value_proposal_workflow(tmp_path):
    result = _service_result(tmp_path)
    report = HumanReviewedLiveParameterDraftGate(_config(tmp_path)).validate(result.draft)
    assert report.valid is True
    assert report.value_proposal_workflow_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.actual_order_values_present is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = HumanReviewedLiveParameterDraftJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_created == 1
    assert store.find_by_idempotency_key(result.draft.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = HumanReviewedLiveParameterDraftJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_draft_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.draft.draft_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = HumanReviewedLiveParameterDraftFormatter()
    card = formatter.to_card(result.draft, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.draft, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["actual_order_values_present"] is False
    assert "value_proposal_workflow_allowed" in markdown
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
    draft = _service_result(tmp_path).draft
    setattr(draft, field_name, True)
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
    assert issue in result.issues


def test_validator_rejects_slot_value_flags_and_missing_hard_block(tmp_path):
    draft = _service_result(tmp_path).draft
    draft.slots[0].value_allowed_now = True
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
    assert "slot_value_allowed_now_must_be_false" in result.issues
    draft = _service_result(tmp_path).draft
    draft.slots[0].value_resolved_now = True
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
    assert "slot_value_resolved_now_must_be_false" in result.issues
    draft = _service_result(tmp_path).draft
    draft.slots[0].actual_value_present = True
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
    assert "slot_actual_value_present_must_be_false" in result.issues
    draft = _service_result(tmp_path).draft
    draft.hard_live_block_required = False
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
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
    draft = _service_result(tmp_path).draft
    draft.blockers = [marker]
    result = HumanReviewedLiveParameterDraftValidator(_config(tmp_path)).validate_draft(draft)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_draft_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Human-Reviewed Parameter Draft" in text
    assert "This only builds unresolved human-review parameter slots" in text
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
