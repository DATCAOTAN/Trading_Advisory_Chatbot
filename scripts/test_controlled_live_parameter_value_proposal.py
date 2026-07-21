from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.test_human_reviewed_live_parameter_draft import _inputs as _draft_inputs
from src.services.trading.execution.live_parameter_draft import (
    HumanReviewedLiveParameterDraftConfig,
    HumanReviewedLiveParameterDraftService,
)
from src.services.trading.execution.live_parameter_value_proposal import (
    CONTROLLED_VALUE_PROPOSAL_BLOCK_REASONS,
    CONTROLLED_VALUE_PROPOSAL_SCOPES,
    CONTROLLED_VALUE_PROPOSAL_STATUSES,
    CONTROLLED_VALUE_REVIEW_STATES,
    CONTROLLED_VALUE_SLOT_STATUSES,
    CONTROLLED_VALUE_SLOT_TYPES,
    REQUIRED_CONTROLLED_VALUE_SLOT_MAP,
    REQUIRED_CONTROLLED_VALUE_SLOT_TYPES,
    ControlledLiveParameterValueProposalConfig,
    ControlledLiveParameterValueProposalFormatter,
    ControlledLiveParameterValueProposalGate,
    ControlledLiveParameterValueProposalService,
    ControlledLiveParameterValueProposalValidator,
    ControlledLiveParameterValueProposalJournalStore,
    ControlledLiveParameterValueSlotBuilder,
)


def _config(tmp_path: Path | None = None, **kwargs) -> ControlledLiveParameterValueProposalConfig:
    values = {"journal_path": str((tmp_path or Path("data")) / "controlled_live_parameter_value_proposals.jsonl")}
    values.update(kwargs)
    return ControlledLiveParameterValueProposalConfig(**values)


def _draft_config(tmp_path: Path | None = None) -> HumanReviewedLiveParameterDraftConfig:
    return HumanReviewedLiveParameterDraftConfig(journal_path=str((tmp_path or Path("data")) / "human_reviewed_live_parameter_drafts.jsonl"))


def _inputs(tmp_path: Path | None = None, **overrides):
    sources = _draft_inputs(tmp_path)
    draft_result = HumanReviewedLiveParameterDraftService(config=_draft_config(tmp_path)).run(**sources)
    values = dict(
        parameter_draft=draft_result.draft,
        parameter_draft_validation=draft_result.validation_report,
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
    return ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**_inputs(tmp_path))


def test_status_scope_slot_status_review_state_and_block_reason_values_exist():
    assert "PROPOSAL_CREATED" in CONTROLLED_VALUE_PROPOSAL_STATUSES
    assert "HUMAN_VALUE_APPROVAL_ONLY" in CONTROLLED_VALUE_PROPOSAL_SCOPES
    assert "SIDE_VALUE_PROPOSAL_SLOT" in CONTROLLED_VALUE_SLOT_TYPES
    assert "REVIEW_REQUIRED" in CONTROLLED_VALUE_SLOT_STATUSES
    assert "HUMAN_REVIEW_REQUIRED" in CONTROLLED_VALUE_REVIEW_STATES
    assert "MISSING_PARAMETER_DRAFT" in CONTROLLED_VALUE_PROPOSAL_BLOCK_REASONS


def test_slot_proposal_validation_and_record_serialize_safely(tmp_path):
    result = _service_result(tmp_path)
    assert result.journal_record is not None
    payloads = [slot.as_dict() for slot in result.proposal.value_slots]
    payloads += [result.proposal.as_dict(), result.validation_report.as_dict(), result.journal_record.as_dict()]
    for payload in payloads:
        text = json.dumps(payload, sort_keys=True)
        assert "raw_account_id" not in text
        assert "credentials" not in text
        assert "mt5_order_request" not in text


def test_config_defaults_enabled_and_requirements():
    config = ControlledLiveParameterValueProposalConfig()
    assert config.enabled is True
    assert config.require_parameter_draft is True
    assert config.require_parameter_draft_validation is True
    assert config.require_value_proposal_workflow_allowed is True
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
    assert config.require_human_review is True
    assert config.require_value_lock is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"parameter_draft": None}, "MISSING_PARAMETER_DRAFT"),
        ({"parameter_draft_validation": None}, "MISSING_PARAMETER_DRAFT_VALIDATION"),
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
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**_inputs(tmp_path, **override))
    assert reason in result.proposal.blockers
    assert result.proposal.human_value_approval_allowed is False


def test_invalid_parameter_draft_validation_and_workflow_false_block(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["parameter_draft_validation"].valid = False
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PARAMETER_DRAFT_VALIDATION" in result.proposal.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_draft_validation"].value_proposal_workflow_allowed = False
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "VALUE_PROPOSAL_WORKFLOW_NOT_ALLOWED" in result.proposal.blockers


def test_preflight_not_pass_blocks(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["preflight_report"].preflight_status = "FAIL"
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_PREFLIGHT_REPORT" in result.proposal.blockers


def test_missing_source_refs_and_idempotency_block(tmp_path):
    inputs = _inputs(tmp_path)
    for item in inputs.values():
        if hasattr(item, "source_refs"):
            item.source_refs = []
        if hasattr(item, "artifact_hash"):
            item.artifact_hash = ""
        if hasattr(item, "idempotency_key"):
            item.idempotency_key = ""
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "MISSING_SOURCE_REFS" in result.proposal.blockers
    assert "MISSING_IDEMPOTENCY" in result.proposal.blockers


def test_human_review_value_lock_executable_and_payload_blocks(tmp_path):
    class NoReviewSlotBuilder(ControlledLiveParameterValueSlotBuilder):
        def build_slots(self, parameter_draft, source_refs=None):
            slots = super().build_slots(parameter_draft, source_refs)
            slots[0].human_review_required = False
            return slots

    service = ControlledLiveParameterValueProposalService(config=_config(tmp_path))
    service.builder.slot_builder = NoReviewSlotBuilder()
    result = service.run(**_inputs(tmp_path))
    assert "HUMAN_REVIEW_NOT_COMPLETED" in result.proposal.blockers

    class NoLockSlotBuilder(ControlledLiveParameterValueSlotBuilder):
        def build_slots(self, parameter_draft, source_refs=None):
            slots = super().build_slots(parameter_draft, source_refs)
            slots[0].value_lock_required = False
            return slots

    service = ControlledLiveParameterValueProposalService(config=_config(tmp_path))
    service.builder.slot_builder = NoLockSlotBuilder()
    result = service.run(**_inputs(tmp_path))
    assert "VALUE_LOCK_NOT_ALLOWED" in result.proposal.blockers

    inputs = _inputs(tmp_path)
    inputs["proposal_draft"].executable = True
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "EXECUTABLE_ORDER_NOT_ALLOWED" in result.proposal.blockers
    inputs = _inputs(tmp_path)
    inputs["parameter_draft"].mt5_payload_created = True
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert "MT5_PAYLOAD_NOT_ALLOWED" in result.proposal.blockers


def test_expired_and_duplicate_value_proposal_block(tmp_path):
    late = datetime.now(timezone.utc) + timedelta(seconds=999)
    result = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**_inputs(tmp_path), current_time=late)
    assert "EXPIRED_VALUE_PROPOSAL" in result.proposal.blockers
    inputs = _inputs(tmp_path)
    first = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert first.journal_record is not None
    duplicate = ControlledLiveParameterValueProposalService(config=_config(tmp_path)).run(**inputs)
    assert duplicate.proposal.status == "DUPLICATE"
    assert "DUPLICATE_VALUE_PROPOSAL" in duplicate.proposal.blockers


def test_valid_inputs_create_proposal_with_safe_flags_and_exactly_nine_value_slots(tmp_path):
    result = _service_result(tmp_path)
    proposal = result.proposal
    validation = result.validation_report
    assert proposal.status == "PROPOSAL_CREATED"
    assert validation.valid is True
    assert validation.human_value_approval_allowed is True
    for item in [proposal, validation]:
        assert item.live_execution_allowed is False
        assert item.order_send_allowed is False
        assert item.execution_allowed is False
        assert item.executable is False
        assert item.mt5_payload_created is False
        assert item.order_sent is False
        assert item.hard_live_block_required is True
        assert item.order_contract_ready is False
        assert item.value_lock_required is True
        assert item.human_review_required is True
    assert len(proposal.value_slots) == 9
    assert proposal.required_value_slot_types == REQUIRED_CONTROLLED_VALUE_SLOT_TYPES
    assert all(slot.executable_value is False for slot in proposal.value_slots)
    assert all(slot.human_review_required is True for slot in proposal.value_slots)
    assert all(slot.value_lock_required is True for slot in proposal.value_slots)


@pytest.mark.parametrize(("slot_type", "source_slot_type"), sorted(REQUIRED_CONTROLLED_VALUE_SLOT_MAP.items()))
def test_value_slot_builder_creates_required_slot_types(slot_type, source_slot_type, tmp_path):
    parameter_draft = _inputs(tmp_path)["parameter_draft"]
    slots = ControlledLiveParameterValueSlotBuilder().build_slots(parameter_draft, ["source:test"])
    slot = next(item for item in slots if item.slot_type == slot_type)
    assert slot.source_draft_slot_id
    assert source_slot_type.lower() in slot.source_draft_slot_id
    assert slot.review_state == "HUMAN_REVIEW_REQUIRED"
    assert slot.executable_value is False
    assert slot.human_review_required is True
    assert slot.value_lock_required is True


def test_gate_valid_only_enables_human_value_approval(tmp_path):
    result = _service_result(tmp_path)
    report = ControlledLiveParameterValueProposalGate(_config(tmp_path)).validate(result.proposal)
    assert report.valid is True
    assert report.human_value_approval_allowed is True
    assert report.live_execution_allowed is False
    assert report.order_send_allowed is False
    assert report.execution_allowed is False
    assert report.executable is False
    assert report.mt5_payload_created is False
    assert report.order_contract_ready is False


def test_journal_store_appends_reads_summarizes_and_looks_up_idempotency(tmp_path):
    result = _service_result(tmp_path)
    store = ControlledLiveParameterValueProposalJournalStore(_config(tmp_path).journal_path)
    records = store.read_latest()
    summary = store.summarize()
    assert len(records) == 1
    assert summary.total_records == 1
    assert summary.total_created == 1
    assert store.find_by_idempotency_key(result.proposal.idempotency_key) is not None


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    store = ControlledLiveParameterValueProposalJournalStore(_config(tmp_path).journal_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json}\n", encoding="utf-8")
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_proposal_validation_report_and_journal_record(tmp_path):
    result = _service_result(tmp_path)
    assert result.proposal.proposal_id
    assert result.validation_report.validation_report_id
    assert result.journal_record is not None
    assert result.summary.total_records >= 1


def test_formatter_creates_json_safe_card_and_markdown(tmp_path):
    result = _service_result(tmp_path)
    formatter = ControlledLiveParameterValueProposalFormatter()
    card = formatter.to_card(result.proposal, result.validation_report, result.journal_record)
    markdown = formatter.to_markdown_summary(result.proposal, result.validation_report, result.journal_record)
    assert card.as_dict()["fields"]["order_contract_ready"] is False
    assert "human_value_approval_allowed" in markdown
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
        ("value_lock_required", "value_lock_required_must_be_true", False),
        ("human_review_required", "human_review_required_must_be_true", False),
    ],
)
def test_validator_rejects_unsafe_flags(tmp_path, field_name, issue, value):
    proposal = _service_result(tmp_path).proposal
    setattr(proposal, field_name, value)
    result = ControlledLiveParameterValueProposalValidator(_config(tmp_path)).validate_proposal(proposal)
    assert issue in result.issues


def test_validator_rejects_slot_executable_and_missing_hard_block(tmp_path):
    proposal = _service_result(tmp_path).proposal
    proposal.value_slots[0].executable_value = True
    result = ControlledLiveParameterValueProposalValidator(_config(tmp_path)).validate_proposal(proposal)
    assert "slot_executable_value_must_be_false" in result.issues
    proposal = _service_result(tmp_path).proposal
    proposal.hard_live_block_required = False
    result = ControlledLiveParameterValueProposalValidator(_config(tmp_path)).validate_proposal(proposal)
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
    proposal = _service_result(tmp_path).proposal
    proposal.blockers = [marker]
    result = ControlledLiveParameterValueProposalValidator(_config(tmp_path)).validate_proposal(proposal)
    assert result.passed is False


def test_dashboard_code_does_not_add_forbidden_trade_buttons_and_labels_approval_only():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Build Controlled Value Proposal" in text
    assert "This only builds a controlled value proposal boundary" in text
    assert "future human value approval only" in text
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
