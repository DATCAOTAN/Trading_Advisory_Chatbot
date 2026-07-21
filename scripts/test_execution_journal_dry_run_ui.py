from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.services.trading.execution import (
    DryRunConfirmationService,
    DryRunExecutionAdapter,
    ExecutionGate,
    ExecutionGatePolicy,
    ExecutionJournalService,
    ExecutionJournalStore,
    ExecutionJournalValidator,
    InMemoryIdempotencyStore,
)
from src.services.trading.execution.journal_models import ExecutionJournalRecord, now_utc_iso
from src.services.trading.execution.models import ExecutionGateDecision
from src.services.trading.review.models import HumanReviewArtifact, ReviewCard


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_execution_journal_record_serializes_to_json():
    payload = json.dumps(_record().as_dict())
    assert "journal_record_id" in payload


def test_journal_store_creates_directory(tmp_path):
    path = tmp_path / "nested" / "dry_run_receipts.jsonl"
    ExecutionJournalStore(path=path).append(_record())
    assert path.parent.exists()


def test_journal_store_appends_jsonl_record(tmp_path):
    path = tmp_path / "journal.jsonl"
    ExecutionJournalStore(path=path).append(_record())
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_journal_store_reads_latest_n_records(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    for index in range(3):
        store.append(_record(receipt_id=f"receipt_{index}"))
    records = store.read_latest(2)
    assert [item.receipt_id for item in records] == ["receipt_1", "receipt_2"]


def test_journal_store_handles_corrupted_line_with_warning(tmp_path):
    path = tmp_path / "journal.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = ExecutionJournalStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_journal_summary_counts_dry_runs(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    store.append(_record())
    assert store.summarize().total_dry_runs == 1


def test_journal_summary_counts_blocked_receipts(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    store.append(_record(allowed=False, gate_action="BLOCKED"))
    assert store.summarize().total_blocked == 1


def test_journal_summary_counts_allowed_dry_runs(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    store.append(_record(allowed=True, gate_action="ALLOW_DRY_RUN"))
    assert store.summarize().total_allowed == 1


def test_journal_summary_counts_duplicate_records(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    store.append(_record(event_type="DRY_RUN_DUPLICATE_DETECTED", gate_action="DUPLICATE_ARTIFACT"))
    assert store.summarize().total_duplicates == 1


def test_journal_service_writes_receipt_record(tmp_path):
    service = _journal_service(tmp_path)
    record = service.append_receipt(_artifact(), _gate_decision(), _receipt())
    assert record is not None
    assert service.store.path.exists()


def test_journal_service_skips_write_when_disabled(tmp_path):
    service = ExecutionJournalService(store=ExecutionJournalStore(path=tmp_path / "journal.jsonl"), enabled=False)
    record = service.append_receipt(_artifact(), _gate_decision(), _receipt())
    assert record is None
    assert service.last_warning == "journal_disabled"


def test_journal_service_preserves_artifact_hash(tmp_path):
    record = _journal_service(tmp_path).append_receipt(_artifact(), _gate_decision(), _receipt())
    assert record.artifact_hash == "abc123hash"


def test_journal_service_preserves_idempotency_key(tmp_path):
    receipt = _receipt()
    record = _journal_service(tmp_path).append_receipt(_artifact(), _gate_decision(), receipt)
    assert record.idempotency_key == receipt.idempotency_key


def test_journal_service_preserves_source_refs(tmp_path):
    record = _journal_service(tmp_path).append_receipt(_artifact(), _gate_decision(), _receipt())
    assert SOURCE_REF in record.source_refs


def test_dry_run_confirmation_service_runs_gate_receipt_journal(tmp_path):
    service = _dry_run_service(tmp_path)
    result = service.run(_artifact(), card=_card())
    assert result.gate_decision
    assert result.receipt
    assert result.journal_record


def test_dry_run_confirmation_service_handles_blocked_artifact(tmp_path):
    service = _dry_run_service(tmp_path)
    result = service.run(_artifact(review_status="WAITING", readiness_action="WAIT"), card=_card(status_label="WAITING"))
    assert result.receipt.allowed is False
    assert result.receipt.executed is False


def test_dry_run_confirmation_service_handles_duplicate_artifact(tmp_path):
    service = _dry_run_service(tmp_path)
    artifact = _artifact()
    assert service.run(artifact, card=_card()).gate_decision.action == "ALLOW_DRY_RUN"
    assert service.run(artifact, card=_card()).gate_decision.action == "DUPLICATE_ARTIFACT"


def test_dry_run_confirmation_service_returns_executed_false(tmp_path):
    result = _dry_run_service(tmp_path).run(_artifact(), card=_card())
    assert result.receipt.executed is False


def test_dry_run_confirmation_service_returns_dry_run_only_true(tmp_path):
    result = _dry_run_service(tmp_path).run(_artifact(), card=_card())
    assert result.receipt.dry_run_only is True


def test_validator_rejects_buy_sell():
    record = _record(warnings=["contains_" + "buy"])
    assert not ExecutionJournalValidator().validate(record).passed


def test_validator_rejects_price_and_size_markers():
    record = _record(warnings=["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    assert not ExecutionJournalValidator().validate(record).passed


def test_validator_rejects_order_submission_marker():
    assert not ExecutionJournalValidator().validate(_record(warnings=["order" + "_send"])).passed


def test_validator_rejects_executable_order_fields():
    assert not ExecutionJournalValidator().validate(_record(warnings=["executable_order"])).passed


def test_validator_rejects_raw_candles():
    assert not ExecutionJournalValidator().validate(_record(warnings=["raw_candles"])).passed


def test_validator_rejects_raw_full_book_report_text():
    assert not ExecutionJournalValidator().validate(_record(warnings=["full_raw_book", "full_raw_report"])).passed


def test_validator_rejects_account_id_credentials_markers():
    assert not ExecutionJournalValidator().validate(_record(warnings=["account_id", "api_key", "password"])).passed


def test_journal_file_contains_no_buy_sell(tmp_path):
    path = tmp_path / "journal.jsonl"
    ExecutionJournalStore(path=path).append(_record())
    payload = path.read_text(encoding="utf-8").lower()
    assert "buy" not in payload
    assert "sell" not in payload


def test_journal_file_contains_no_price_or_size_fields(tmp_path):
    path = tmp_path / "journal.jsonl"
    ExecutionJournalStore(path=path).append(_record())
    payload = path.read_text(encoding="utf-8").lower()
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_journal_file_contains_no_raw_account_id(tmp_path):
    path = tmp_path / "journal.jsonl"
    ExecutionJournalStore(path=path).append(_record())
    assert "account_id" not in path.read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_real_confirm_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()
    assert "confirm trade" not in text
    assert "confirm live trade" not in text


def test_dashboard_code_does_not_add_execute_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()
    assert "execute trade" not in text
    assert "mt5 execution button" not in text


def test_dashboard_labels_dry_run_clearly():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Run Dry-Run Gate" in text
    assert "Dry-run only" in text
    assert "executed=false" in text


def test_execution_journal_code_does_not_call_llm_or_mt5_or_live_service():
    root = Path("src/services/trading/execution")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "LLMReasoningAdapter" not in text
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text


def test_execution_journal_code_has_no_order_submission_call_marker():
    root = Path("src/services/trading/execution")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "order" + "_send(" not in text


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def test_journal_summary_exposes_latest_fields(tmp_path):
    store = ExecutionJournalStore(path=tmp_path / "journal.jsonl")
    store.append(_record(receipt_id="latest_receipt", gate_action="ALLOW_DRY_RUN"))
    summary = store.summarize()
    assert summary.latest_receipt_id == "latest_receipt"
    assert summary.latest_gate_action == "ALLOW_DRY_RUN"


def _journal_service(tmp_path) -> ExecutionJournalService:
    return ExecutionJournalService(store=ExecutionJournalStore(path=tmp_path / "journal.jsonl"), enabled=True)


def _dry_run_service(tmp_path) -> DryRunConfirmationService:
    store = InMemoryIdempotencyStore()
    gate = ExecutionGate(policy=ExecutionGatePolicy(), idempotency_store=store)
    journal = ExecutionJournalService(store=ExecutionJournalStore(path=tmp_path / "journal.jsonl"), enabled=True)
    return DryRunConfirmationService(gate=gate, journal=journal)


def _record(
    event_type: str = "DRY_RUN_RECEIPT_CREATED",
    allowed: bool = False,
    gate_action: str = "BLOCKED",
    receipt_id: str = "receipt_fixture",
    warnings: list[str] | None = None,
) -> ExecutionJournalRecord:
    record = ExecutionJournalRecord(
        journal_record_id="journal_fixture",
        created_at=now_utc_iso(),
        event_type=event_type,
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        idempotency_key="idem123",
        gate_decision_id="gate_fixture",
        gate_action=gate_action,
        receipt_id=receipt_id,
        dry_run_only=True,
        executed=False,
        allowed=allowed,
        review_status="READY_FOR_REVIEW",
        readiness_action="REVIEW_READY",
        blockers=[] if allowed else ["review_status_waiting"],
        warnings=warnings or [],
        source_refs=[SOURCE_REF],
        metadata_redacted={"artifact_hash_prefix": "abc123hash"[:6]},
    )
    record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
    return record


def _artifact(review_status: str = "READY_FOR_REVIEW", readiness_action: str = "REVIEW_READY") -> HumanReviewArtifact:
    return HumanReviewArtifact(
        artifact_id="artifact_fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
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


def _card(status_label: str = "READY_FOR_REVIEW") -> ReviewCard:
    return ReviewCard(
        title="Human Review Card",
        status_label=status_label,
        summary="Dry-run review card.",
        disclaimer="Dry-run only.",
    )


def _gate_decision() -> ExecutionGateDecision:
    return ExecutionGateDecision(
        gate_decision_id="gate_fixture",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        action="ALLOW_DRY_RUN",
        allowed=True,
        dry_run_only=True,
        reason="dry_run_gate_passed",
        artifact_id="artifact_fixture",
        artifact_hash="abc123hash",
        source_review_artifact_id="artifact_fixture",
        source_readiness_decision_id="readiness_fixture",
        source_refs=[SOURCE_REF],
    )


def _receipt():
    return DryRunExecutionAdapter().run(_gate_decision(), _artifact())
