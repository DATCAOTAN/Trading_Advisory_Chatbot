from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.models import DryRunExecutionReceipt
from src.services.trading.proposal import (
    HumanProposalConfirmationService,
    ProposalBoundaryFormatter,
    ProposalBoundaryPolicy,
    ProposalBoundaryValidator,
    ProposalIntentJournalService,
    ProposalIntentJournalStore,
)
from src.services.trading.proposal.models import HumanConfirmedProposalIntent, ProposalIntentJournalRecord, now_utc_iso
from src.services.trading.review.models import HumanReviewArtifact


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"
PHRASE = "I understand this is dry-run only and does not execute a trade"


def test_policy_loads_defaults():
    policy = ProposalBoundaryPolicy()
    assert policy.enabled is True
    assert policy.require_dry_run_receipt is True


def test_confirmation_phrase_required():
    assert ProposalBoundaryPolicy().confirmation_phrase == PHRASE


def test_missing_confirmation_phrase_does_not_confirm(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), "")
    assert intent.proposal_workflow_allowed is False
    assert intent.human_confirmation_state == "NOT_REQUESTED"


def test_wrong_confirmation_phrase_does_not_confirm(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), "wrong phrase")
    assert intent.proposal_boundary_status == "INVALID"
    assert intent.proposal_workflow_allowed is False


def test_correct_phrase_creates_confirmed_proposal_intent(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert intent.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert intent.proposal_workflow_allowed is True


def test_intent_always_has_dry_run_only_true(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert intent.dry_run_only is True


def test_intent_always_has_executable_false(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert intent.executable is False


def test_blocked_review_artifact_blocks_proposal_intent(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(review_status="BLOCKED"), _receipt(), _journal_record(), PHRASE)
    assert intent.proposal_boundary_status == "BLOCKED"


def test_waiting_review_artifact_blocks_by_default(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(review_status="WAITING"), _receipt(), _journal_record(), PHRASE)
    assert intent.proposal_boundary_status == "BLOCKED"


def test_ready_for_review_artifact_can_continue_if_dry_run_allowed(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(allowed=True), _journal_record(), PHRASE)
    assert intent.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"


def test_missing_dry_run_receipt_blocks(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), None, _journal_record(), PHRASE)
    assert "dry_run_receipt_required" in intent.blockers


def test_dry_run_receipt_with_executed_true_blocks(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(executed=True), _journal_record(), PHRASE)
    assert "dry_run_receipt_executed_true" in intent.blockers


def test_dry_run_receipt_with_dry_run_only_false_blocks(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(dry_run_only=False), _journal_record(), PHRASE)
    assert "dry_run_receipt_not_dry_run_only" in intent.blockers


def test_missing_journal_record_blocks_when_required(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), None, PHRASE)
    assert "execution_journal_record_required" in intent.blockers


def test_expired_artifact_returns_expired(tmp_path):
    old = datetime.now(timezone.utc) - timedelta(seconds=999)
    intent = _service(tmp_path).confirm(_artifact(created_at=old.isoformat()), _receipt(), _journal_record(), PHRASE)
    assert intent.proposal_boundary_status == "EXPIRED"


def test_duplicate_artifact_returns_duplicate(tmp_path):
    service = _service(tmp_path)
    assert service.confirm(_artifact(), _receipt(), _journal_record(), PHRASE).proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
    assert service.confirm(_artifact(), _receipt(), _journal_record(), PHRASE).proposal_boundary_status == "DUPLICATE"


def test_proposal_intent_preserves_artifact_hash(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert intent.artifact_hash == "abc123hash"


def test_proposal_intent_preserves_idempotency_key(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert intent.idempotency_key == "idem123"


def test_proposal_intent_preserves_source_refs(tmp_path):
    intent = _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert SOURCE_REF in intent.source_refs


def test_journal_store_appends_jsonl(tmp_path):
    path = tmp_path / "proposal_intents.jsonl"
    ProposalIntentJournalStore(path=path).append(_proposal_record())
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_journal_store_reads_latest_records(tmp_path):
    store = ProposalIntentJournalStore(path=tmp_path / "proposal_intents.jsonl")
    for index in range(3):
        store.append(_proposal_record(intent_id=f"intent_{index}"))
    assert [item.intent_id for item in store.read_latest(2)] == ["intent_1", "intent_2"]


def test_journal_store_summarizes_records(tmp_path):
    store = ProposalIntentJournalStore(path=tmp_path / "proposal_intents.jsonl")
    store.append(_proposal_record(status="CONFIRMED_FOR_PROPOSAL_WORKFLOW"))
    assert store.summarize().total_confirmed == 1


def test_corrupted_journal_line_returns_warning(tmp_path):
    path = tmp_path / "proposal_intents.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = ProposalIntentJournalStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_formatter_generates_markdown_safely(tmp_path):
    markdown = ProposalBoundaryFormatter().to_markdown(_confirmed_intent(tmp_path))
    assert "Proposal Boundary Confirmation" in markdown
    assert "order" + "_send" not in markdown


def test_formatter_generates_json_safe_card(tmp_path):
    card = ProposalBoundaryFormatter().to_card(_confirmed_intent(tmp_path))
    assert card.as_dict()["status_label"] == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"


def test_validator_rejects_buy_sell():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["contains_" + "buy"])).passed
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["contains_" + "sell"])).passed


def test_validator_rejects_trade_side():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["trade_side"])).passed


def test_validator_rejects_price_and_size_markers():
    assert not ProposalBoundaryValidator().validate_intent(
        _intent(warnings=["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    ).passed


def test_validator_rejects_order_submission_marker():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["order" + "_send"])).passed


def test_validator_rejects_executable_order_fields():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["real_order_id", "mt5_order_request", "executable_order"])).passed


def test_validator_rejects_raw_candles():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["raw_candles"])).passed


def test_validator_rejects_raw_full_book_report_text():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["full_raw_book", "full_raw_report"])).passed


def test_validator_rejects_account_id_credentials_markers():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["account_id", "api_key", "password"])).passed


def test_validator_rejects_metatrader_marker():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["Meta" + "Trader5"])).passed


def test_validator_rejects_llm_prompt_marker():
    assert not ProposalBoundaryValidator().validate_intent(_intent(warnings=["compact_prompt"])).passed


def test_validator_rejects_oversized_payload():
    assert not ProposalBoundaryValidator(max_payload_chars=100).validate_intent(_intent(warnings=["x" * 200])).passed


def test_validator_accepts_clean_confirmed_intent():
    assert ProposalBoundaryValidator().validate_intent(_intent()).passed


def test_journal_record_serializes_to_json():
    assert "journal_record_id" in json.dumps(_proposal_record().as_dict())


def test_journal_record_forces_dry_run_only_and_executable_false():
    payload = _proposal_record().as_dict()
    assert payload["dry_run_only"] is True
    assert payload["executable"] is False


def test_journal_service_appends_confirmed_intent(tmp_path):
    service = _service(tmp_path)
    result = service.confirm_with_journal(_artifact(), _receipt(), _journal_record(), PHRASE)
    assert result.journal_record is not None


def test_journal_summary_counts_blocked_expired_duplicates(tmp_path):
    store = ProposalIntentJournalStore(path=tmp_path / "proposal_intents.jsonl")
    store.append(_proposal_record(status="BLOCKED"))
    store.append(_proposal_record(status="EXPIRED"))
    store.append(_proposal_record(status="DUPLICATE"))
    summary = store.summarize()
    assert summary.total_blocked == 1
    assert summary.total_expired == 1
    assert summary.total_duplicates == 1


def test_dashboard_code_does_not_add_confirm_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()
    assert "confirm trade" not in text


def test_dashboard_code_does_not_add_execute_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()
    assert "execute trade" not in text


def test_dashboard_code_does_not_add_place_order_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()
    assert "place order" not in text


def test_dashboard_labels_proposal_workflow_non_executable():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Confirm Proposal Workflow" in text
    assert "executable=false" in text
    assert "No live order is sent" in text


def test_proposal_boundary_code_does_not_call_llm():
    text = _proposal_source_text()
    assert "LLMReasoningAdapter" not in text


def test_proposal_boundary_code_does_not_import_metatrader5():
    assert "Meta" + "Trader5" not in _proposal_source_text()


def test_proposal_boundary_code_does_not_import_live_data_service():
    assert "live_data_service" not in _proposal_source_text()


def test_proposal_boundary_code_has_no_order_submission_call_marker():
    assert "order" + "_send(" not in _proposal_source_text()


def test_gitignore_ignores_runtime_jsonl():
    assert "data/trading/execution_journal/*.jsonl" in Path(".gitignore").read_text(encoding="utf-8")


def test_runtime_journal_file_contains_no_price_or_size_fields(tmp_path):
    path = tmp_path / "proposal_intents.jsonl"
    ProposalIntentJournalStore(path=path).append(_proposal_record())
    payload = path.read_text(encoding="utf-8").lower()
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_runtime_journal_file_contains_no_raw_account_id(tmp_path):
    path = tmp_path / "proposal_intents.jsonl"
    ProposalIntentJournalStore(path=path).append(_proposal_record())
    assert "account_id" not in path.read_text(encoding="utf-8").lower()


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def _service(tmp_path) -> HumanProposalConfirmationService:
    policy = ProposalBoundaryPolicy(confirmation_phrase=PHRASE)
    journal = ProposalIntentJournalService(store=ProposalIntentJournalStore(path=tmp_path / "proposal_intents.jsonl"))
    return HumanProposalConfirmationService(policy=policy, journal=journal)


def _confirmed_intent(tmp_path) -> HumanConfirmedProposalIntent:
    return _service(tmp_path).confirm(_artifact(), _receipt(), _journal_record(), PHRASE)


def _artifact(
    review_status: str = "READY_FOR_REVIEW",
    readiness_action: str = "REVIEW_READY",
    created_at: str | None = None,
) -> HumanReviewArtifact:
    return HumanReviewArtifact(
        artifact_id="artifact_fixture",
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        review_status=review_status,
        readiness_action=readiness_action,
        readiness_score=0.82,
        confidence=0.78,
        grade="GOOD",
        primary_method_id="al_brooks_trend_pullback",
        selected_playbook_ids=["trend_pullback_v1"],
        primary_regime="PULLBACK_UPTREND",
        calendar_risk_state="CLEAR",
        final_context_score=0.82,
        reasons=["score_above_review_ready_threshold"],
        warnings=[],
        blockers=[],
        source_refs=[SOURCE_REF],
        source_readiness_decision_id="readiness_fixture",
        source_score_report_id="score_fixture",
        source_method_selection_id="method_selection_fixture",
        source_context_pack_id="context_fixture",
    )


def _receipt(allowed: bool = True, executed: bool = False, dry_run_only: bool = True) -> DryRunExecutionReceipt:
    return DryRunExecutionReceipt(
        receipt_id="receipt_fixture",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        dry_run_only=dry_run_only,
        gate_action="ALLOW_DRY_RUN" if allowed else "BLOCKED",
        allowed=allowed,
        executed=executed,
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        idempotency_key="idem123",
        source_gate_decision_id="gate_fixture",
        source_review_artifact_id="artifact_fixture",
        source_refs=[SOURCE_REF],
    )


def _journal_record() -> ExecutionJournalRecord:
    return ExecutionJournalRecord(
        journal_record_id="execution_journal_fixture",
        created_at=now_utc_iso(),
        event_type="DRY_RUN_ALLOWED",
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        idempotency_key="idem123",
        gate_decision_id="gate_fixture",
        gate_action="ALLOW_DRY_RUN",
        receipt_id="receipt_fixture",
        dry_run_only=True,
        executed=False,
        allowed=True,
        review_status="READY_FOR_REVIEW",
        readiness_action="REVIEW_READY",
        source_refs=[SOURCE_REF],
    )


def _intent(warnings: list[str] | None = None) -> HumanConfirmedProposalIntent:
    intent = HumanConfirmedProposalIntent(
        intent_id="intent_fixture",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        proposal_boundary_status="CONFIRMED_FOR_PROPOSAL_WORKFLOW",
        human_confirmation_state="CONFIRMED_PROPOSAL_WORKFLOW",
        proposal_workflow_allowed=True,
        dry_run_only=True,
        executable=False,
        user_acknowledgement_text=PHRASE,
        confirmation_phrase_required=PHRASE,
        confirmation_phrase_received=PHRASE,
        review_status="READY_FOR_REVIEW",
        readiness_action="REVIEW_READY",
        gate_action="ALLOW_DRY_RUN",
        dry_run_allowed=True,
        dry_run_executed=False,
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        dry_run_receipt_id="receipt_fixture",
        idempotency_key="idem123",
        source_review_artifact_id="artifact_fixture",
        source_gate_decision_id="gate_fixture",
        source_dry_run_receipt_id="receipt_fixture",
        source_execution_journal_record_id="execution_journal_fixture",
        source_refs=[SOURCE_REF],
        warnings=warnings or [],
        reasons=["confirmation_phrase_matched"],
    )
    intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
    return intent


def _proposal_record(
    intent_id: str = "intent_fixture",
    status: str = "CONFIRMED_FOR_PROPOSAL_WORKFLOW",
) -> ProposalIntentJournalRecord:
    record = ProposalIntentJournalRecord(
        journal_record_id="proposal_intent_journal_fixture",
        created_at=now_utc_iso(),
        event_type="PROPOSAL_INTENT_CONFIRMED",
        intent_id=intent_id,
        proposal_boundary_status=status,
        human_confirmation_state="CONFIRMED_PROPOSAL_WORKFLOW",
        proposal_workflow_allowed=status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW",
        dry_run_only=True,
        executable=False,
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        dry_run_receipt_id="receipt_fixture",
        idempotency_key="idem123",
        source_refs=[SOURCE_REF],
        metadata_redacted={"artifact_hash_prefix": "abc123hash"[:12]},
    )
    record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
    return record


def _proposal_source_text() -> str:
    root = Path("src/services/trading/proposal")
    return "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
