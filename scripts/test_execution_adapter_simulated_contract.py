from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.trading.execution import (
    EXECUTION_ADAPTER_TYPES,
    ExecutionAdapterPolicy,
    ExecutionAdapterRegistry,
    ExecutionAdapterHealth,
    ExecutionAdapterContractValidator,
    SimulatedExecutionAdapter,
    SimulatedExecutionJournalService,
    SimulatedExecutionJournalStore,
    SimulatedExecutionService,
    SimulatedOrderContractBuilder,
)
from src.services.trading.execution.adapter_models import SimulatedExecutionJournalRecord, SimulatedOrderContract, now_utc_iso
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft, ProposalDraftJournalRecord
from src.services.trading.proposal.models import HumanConfirmedProposalIntent


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_execution_adapter_type_values_exist():
    assert {"SIMULATED", "RESERVED_MT5_LIVE", "DISABLED", "UNKNOWN"}.issubset(EXECUTION_ADAPTER_TYPES)


def test_execution_adapter_health_serializes_safely():
    health = ExecutionAdapterHealth(adapter_type="SIMULATED", status="OK", message="ready")
    payload = health.as_dict()
    assert payload["live_execution_supported"] is False
    assert payload["simulated_only"] is True


def test_simulated_order_contract_validates_required_fields():
    assert ExecutionAdapterContractValidator().validate_contract(_contract()).passed


def test_contract_has_simulated_only_true():
    assert _contract().as_dict()["simulated_only"] is True


def test_contract_has_executable_false():
    assert _contract().as_dict()["executable"] is False


def test_contract_preserves_draft_source_ids():
    assert _contract().source_draft_id == "draft_fixture"


def test_contract_preserves_source_refs():
    assert SOURCE_REF in _contract().source_refs


def test_contract_builder_rejects_executable_draft():
    draft = _draft()
    draft.executable = True
    contract = SimulatedOrderContractBuilder(policy=_policy()).build(draft, intent=_intent())
    assert "draft_executable_true" in contract.blockers


def test_contract_builder_rejects_missing_source_refs():
    draft = _draft()
    draft.source_refs = []
    contract = SimulatedOrderContractBuilder(policy=_policy()).build(draft, intent=_intent())
    assert "source_refs_required" in contract.blockers


def test_contract_builder_rejects_expired_draft_if_ttl_enabled():
    draft = _draft(created_at=(datetime.now(timezone.utc) - timedelta(seconds=999)).isoformat())
    contract = SimulatedOrderContractBuilder(policy=ExecutionAdapterPolicy(contract_ttl_seconds=1)).build(draft, intent=_intent())
    assert contract.contract_status == "EXPIRED"


def test_contract_idempotency_key_is_stable():
    first = _contract()
    second = _contract()
    assert first.idempotency_key == second.idempotency_key


def test_contract_artifact_hash_is_stable():
    assert _contract().artifact_hash == _contract().artifact_hash


def test_adapter_health_ok_when_enabled():
    assert SimulatedExecutionAdapter(policy=_policy()).health_check().status == "OK"


def test_adapter_disabled_health_when_disabled():
    policy = ExecutionAdapterPolicy(simulated_adapter_enabled=False)
    assert SimulatedExecutionAdapter(policy=policy).health_check().status == "DISABLED"


def test_adapter_validates_contract():
    assert SimulatedExecutionAdapter(policy=_policy()).validate_contract(_contract()).passed


def test_adapter_returns_receipt():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).receipt_id


def test_receipt_has_simulated_only_true():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).simulated_only is True


def test_receipt_has_executable_false():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).executable is False


def test_receipt_has_executed_false():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).executed is False


def test_receipt_accepts_only_valid_contract():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).accepted_by_adapter is True


def test_blocked_contract_returns_not_accepted():
    contract = SimulatedOrderContractBuilder(policy=_policy()).build(_draft(status="BLOCKED"), intent=_intent())
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(contract).accepted_by_adapter is False


def test_registry_returns_simulated_adapter_by_default():
    assert ExecutionAdapterRegistry(policy=_policy()).get_adapter().adapter_type() == "SIMULATED"


def test_registry_does_not_create_live_mt5_adapter():
    adapter = ExecutionAdapterRegistry(policy=ExecutionAdapterPolicy(adapter_type="RESERVED_MT5_LIVE")).get_adapter()
    assert adapter.adapter_type() == "RESERVED_MT5_LIVE"
    assert adapter.health_check().status == "BLOCKED"


def test_unknown_adapter_returns_safe_disabled_status():
    adapter = ExecutionAdapterRegistry(policy=ExecutionAdapterPolicy(adapter_type="NOPE")).get_adapter()
    assert adapter.health_check().status == "DISABLED"


def test_simulated_journal_store_appends_jsonl(tmp_path):
    path = tmp_path / "simulated.jsonl"
    SimulatedExecutionJournalStore(path=path).append(_record())
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_simulated_journal_store_reads_latest_records(tmp_path):
    store = SimulatedExecutionJournalStore(path=tmp_path / "simulated.jsonl")
    for index in range(3):
        store.append(_record(receipt_id=f"receipt_{index}"))
    assert [item.receipt_id for item in store.read_latest(2)] == ["receipt_1", "receipt_2"]


def test_simulated_journal_store_summarizes_records(tmp_path):
    store = SimulatedExecutionJournalStore(path=tmp_path / "simulated.jsonl")
    store.append(_record(accepted=True))
    store.append(_record(accepted=False))
    summary = store.summarize()
    assert summary.total_accepted == 1
    assert summary.total_rejected == 1


def test_corrupt_journal_line_returns_warning(tmp_path):
    path = tmp_path / "simulated.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = SimulatedExecutionJournalStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_simulated_execution_service_runs_contract_receipt_journal(tmp_path):
    service = _service(tmp_path)
    result = service.run(_draft(), intent=_intent(), proposal_draft_journal_record=_draft_record())
    assert result.contract
    assert result.receipt
    assert result.journal_record


def test_validator_rejects_buy_sell():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["contains_" + "buy"])).passed
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["contains_" + "sell"])).passed


def test_validator_rejects_long_short():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["long"])).passed
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["short"])).passed


def test_validator_rejects_trade_side():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["trade_side"])).passed


def test_validator_rejects_price_and_size_markers():
    assert not ExecutionAdapterContractValidator().validate_contract(
        _contract(warnings=["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    ).passed


def test_validator_rejects_position_size():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["position_size"])).passed


def test_validator_rejects_order_submission_marker():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["order" + "_send"])).passed


def test_validator_rejects_executable_order_fields():
    assert not ExecutionAdapterContractValidator().validate_contract(
        _contract(warnings=["real_order_id", "mt5_order_request", "executable_order"])
    ).passed


def test_validator_rejects_mt5_ticket_deal_id():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["mt5_ticket", "deal_id"])).passed


def test_validator_rejects_raw_candles():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["raw_candles"])).passed


def test_validator_rejects_raw_full_book_report_text():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["full_raw_book", "full_raw_report"])).passed


def test_validator_rejects_account_id_credentials_markers():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["account_id", "api_key", "password"])).passed


def test_validator_rejects_metatrader_marker():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["Meta" + "Trader5"])).passed


def test_validator_rejects_llm_prompt_marker():
    assert not ExecutionAdapterContractValidator().validate_contract(_contract(warnings=["compact_prompt"])).passed


def test_validator_rejects_receipt_executed_true():
    receipt = SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract())
    receipt.executed = True
    assert not ExecutionAdapterContractValidator().validate_receipt(receipt).passed


def test_validator_rejects_record_executable_true():
    record = _record()
    record.executable = True
    assert not ExecutionAdapterContractValidator().validate_record(record).passed


def test_dashboard_code_does_not_add_confirm_trade_button():
    assert "confirm trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_execute_trade_button():
    assert "execute trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_place_order_button():
    assert "place order" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8").lower()


def test_dashboard_code_does_not_add_buy_sell_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert 'st.button("Buy' not in text
    assert 'st.button("Sell' not in text


def test_dashboard_labels_adapter_as_simulated_non_executable():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Run Simulated Adapter Contract" in text
    assert "Simulated adapter contract only" in text
    assert "executed=false" in text


def test_execution_adapter_code_does_not_call_llm():
    assert "LLMReasoningAdapter" not in _adapter_source_text()


def test_execution_adapter_code_does_not_import_metatrader5():
    assert "Meta" + "Trader5" not in _adapter_source_text()


def test_execution_adapter_code_does_not_import_live_data_service():
    assert "live_data_service" not in _adapter_source_text()


def test_execution_adapter_code_has_no_order_submission_call_marker():
    assert "order" + "_send(" not in _adapter_source_text()


def test_no_live_order_methods_added_to_interface():
    text = Path("src/services/trading/execution/adapter_interface.py").read_text(encoding="utf-8")
    assert "submit_live" not in text
    assert "send_order" not in text
    assert "place_order" not in text


def test_journal_file_contains_no_forbidden_fields(tmp_path):
    path = tmp_path / "simulated.jsonl"
    SimulatedExecutionJournalStore(path=path).append(_record())
    payload = path.read_text(encoding="utf-8").lower()
    for marker in ["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk", "mt5_ticket", "deal_id"]:
        assert marker not in payload


def test_gitignore_ignores_runtime_jsonl():
    assert "data/trading/execution_journal/*.jsonl" in Path(".gitignore").read_text(encoding="utf-8")


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def test_service_warns_when_journal_disabled(tmp_path):
    service = SimulatedExecutionService(
        policy=_policy(),
        journal=SimulatedExecutionJournalService(store=SimulatedExecutionJournalStore(path=tmp_path / "simulated.jsonl"), enabled=False),
    )
    result = service.run(_draft(), intent=_intent(), proposal_draft_journal_record=_draft_record())
    assert result.journal_record is None
    assert result.warning == "simulated_execution_journal_disabled"


def test_disabled_adapter_receipt_is_not_accepted(tmp_path):
    policy = ExecutionAdapterPolicy(adapter_type="DISABLED")
    service = SimulatedExecutionService(
        policy=policy,
        journal=SimulatedExecutionJournalService(
            store=SimulatedExecutionJournalStore(path=tmp_path / "simulated.jsonl")
        ),
    )
    assert service.run(_draft(), intent=_intent()).receipt.accepted_by_adapter is False


def test_contract_payload_size_is_recorded():
    assert _contract().payload_size_chars > 0


def test_receipt_payload_size_is_recorded():
    assert SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract()).payload_size_chars > 0


def test_record_payload_size_is_recorded():
    assert _record().payload_size_chars > 0


def test_health_never_supports_live_execution():
    assert SimulatedExecutionAdapter(policy=_policy()).health_check().live_execution_supported is False


def test_receipt_preserves_source_refs():
    receipt = SimulatedExecutionAdapter(policy=_policy()).submit_simulated(_contract())
    assert SOURCE_REF in receipt.source_refs


def test_record_preserves_source_refs():
    assert SOURCE_REF in _record().source_refs


def _policy() -> ExecutionAdapterPolicy:
    return ExecutionAdapterPolicy(adapter_type="SIMULATED", simulated_adapter_enabled=True, max_payload_chars=20000)


def _service(tmp_path) -> SimulatedExecutionService:
    return SimulatedExecutionService(
        policy=_policy(),
        journal=SimulatedExecutionJournalService(store=SimulatedExecutionJournalStore(path=tmp_path / "simulated.jsonl")),
    )


def _draft(status: str = "DRAFT_CREATED", created_at: str | None = None) -> NonExecutableTradeProposalDraft:
    return NonExecutableTradeProposalDraft(
        draft_id="draft_fixture",
        created_at=created_at or now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        status=status,
        non_executable=True,
        executable=False,
        proposal_workflow_allowed=status == "DRAFT_CREATED",
        source_intent_id="intent_fixture",
        source_review_artifact_id="artifact_fixture",
        source_score_report_id="score_fixture",
        source_method_selection_id="method_selection_fixture",
        source_context_pack_id="context_fixture",
        source_calendar_context_id="calendar_fixture",
        source_regime_snapshot_id="regime_fixture",
        primary_method_id="vpa_effort_vs_result",
        primary_regime="BREAKOUT_CANDIDATE",
        calendar_risk_state="CLEAR",
        readiness_action="REVIEW_READY",
        review_status="READY_FOR_REVIEW",
        final_context_score=0.72,
        grade="GOOD",
        source_refs=[SOURCE_REF],
    )


def _intent() -> HumanConfirmedProposalIntent:
    return HumanConfirmedProposalIntent(
        intent_id="intent_fixture",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        proposal_boundary_status="CONFIRMED_FOR_PROPOSAL_WORKFLOW",
        proposal_workflow_allowed=True,
        dry_run_only=True,
        executable=False,
        artifact_hash="abc123hash",
        idempotency_key="idem123",
        source_refs=[SOURCE_REF],
    )


def _draft_record() -> ProposalDraftJournalRecord:
    return ProposalDraftJournalRecord(
        journal_record_id="proposal_draft_journal_fixture",
        created_at=now_utc_iso(),
        draft_id="draft_fixture",
        status="DRAFT_CREATED",
        non_executable=True,
        executable=False,
        source_intent_id="intent_fixture",
        artifact_hash="abc123hash",
        primary_method_id="vpa_effort_vs_result",
        primary_regime="BREAKOUT_CANDIDATE",
        calendar_risk_state="CLEAR",
        readiness_action="REVIEW_READY",
        final_context_score=0.72,
        source_refs=[SOURCE_REF],
    )


def _contract(warnings: list[str] | None = None) -> SimulatedOrderContract:
    contract = SimulatedOrderContractBuilder(policy=_policy()).build(_draft(), intent=_intent(), proposal_draft_journal_record=_draft_record())
    if warnings:
        contract.warnings.extend(warnings)
    return contract


def _record(receipt_id: str = "receipt_fixture", accepted: bool = True) -> SimulatedExecutionJournalRecord:
    record = SimulatedExecutionJournalRecord(
        journal_record_id="simulated_execution_journal_fixture",
        created_at=now_utc_iso(),
        event_type="SIMULATED_RECEIPT_CREATED" if accepted else "SIMULATED_RECEIPT_REJECTED",
        adapter_type="SIMULATED",
        contract_id="contract_fixture",
        receipt_id=receipt_id,
        contract_status="CREATED" if accepted else "BLOCKED",
        simulated_only=True,
        executable=False,
        executed=False,
        accepted_by_adapter=accepted,
        source_draft_id="draft_fixture",
        artifact_hash="abc123hash",
        idempotency_key="idem123",
        source_refs=[SOURCE_REF],
    )
    record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
    return record


def _adapter_source_text() -> str:
    names = [
        "adapter_models.py",
        "adapter_interface.py",
        "adapter_registry.py",
        "simulated_adapter.py",
        "simulated_contract.py",
        "simulated_journal.py",
        "simulated_receipt.py",
        "simulated_service.py",
        "simulated_store.py",
        "adapter_validator.py",
    ]
    root = Path("src/services/trading/execution")
    return "\n".join((root / name).read_text(encoding="utf-8") for name in names)
