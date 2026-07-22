from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.trading.execution import (
    ExecutionAdapterPolicy,
    ExecutionAdapterRegistry,
    HardLiveBlockValidator,
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockJournalStore,
    LiveExecutionBlockedReceipt,
    LiveExecutionCapabilityReport,
    MT5ExecutionAdapterSkeleton,
    MT5ExecutionSkeletonPolicy,
    MT5ExecutionSkeletonService,
)
from src.services.trading.execution.adapter_models import (
    SimulatedExecutionJournalRecord,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
)
from src.services.trading.execution.mt5_skeleton_models import (
    LIVE_EXECUTION_BLOCK_REASONS,
    MT5_SKELETON_STATUSES,
    LiveExecutionBlockSummary,
)


def _policy(**kwargs) -> MT5ExecutionSkeletonPolicy:
    values = {
        "journal_enabled": True,
        "journal_path": "unused.jsonl",
        "max_read_records": 100,
    }
    values.update(kwargs)
    return MT5ExecutionSkeletonPolicy(**values)


def _contract(source_refs: list[str] | None = None) -> SimulatedOrderContract:
    return SimulatedOrderContract(
        contract_id="contract_1",
        created_at="2026-07-17T00:00:00+00:00",
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        contract_status="CREATED",
        simulated_only=True,
        executable=False,
        source_draft_id="draft_1",
        source_draft_status="DRAFT_CREATED",
        source_intent_id="intent_1",
        source_review_artifact_id="artifact_1",
        source_dry_run_receipt_id="dry_receipt_1",
        source_execution_journal_record_id="execution_record_1",
        source_proposal_draft_journal_record_id="draft_record_1",
        artifact_hash="hash_abc",
        idempotency_key="idem_abc",
        non_executable_proposal=True,
        readiness_action="REVIEW_READY",
        review_status="READY_FOR_REVIEW",
        proposal_boundary_status="CONFIRMED_FOR_PROPOSAL_WORKFLOW",
        draft_status="DRAFT_CREATED",
        blockers=[],
        warnings=[],
        reasons=["fixture"],
        source_refs=source_refs if source_refs is not None else ["method:one", "playbook:one"],
    )


def _simulated_receipt(source_refs: list[str] | None = None) -> SimulatedExecutionReceipt:
    return SimulatedExecutionReceipt(
        receipt_id="sim_receipt_1",
        created_at="2026-07-17T00:00:01+00:00",
        adapter_type="SIMULATED",
        contract_id="contract_1",
        contract_status="CREATED",
        simulated_only=True,
        executable=False,
        executed=False,
        accepted_by_adapter=True,
        source_draft_id="draft_1",
        source_contract_id="contract_1",
        idempotency_key="idem_abc",
        artifact_hash="hash_abc",
        blockers=[],
        warnings=[],
        message="simulated adapter accepted fixture",
        source_refs=source_refs if source_refs is not None else ["method:one", "playbook:one"],
    )


def _simulated_record() -> SimulatedExecutionJournalRecord:
    return SimulatedExecutionJournalRecord(
        journal_record_id="sim_journal_1",
        created_at="2026-07-17T00:00:02+00:00",
        event_type="SIMULATED_RECEIPT_CREATED",
        adapter_type="SIMULATED",
        contract_id="contract_1",
        receipt_id="sim_receipt_1",
        contract_status="CREATED",
        simulated_only=True,
        executable=False,
        executed=False,
        accepted_by_adapter=True,
        source_draft_id="draft_1",
        artifact_hash="hash_abc",
        idempotency_key="idem_abc",
        source_refs=["method:one"],
    )


def _blocked_receipt(**kwargs) -> LiveExecutionBlockedReceipt:
    values = {
        "receipt_id": "blocked_1",
        "created_at": "2026-07-17T00:00:03+00:00",
        "source_contract_id": "contract_1",
        "source_simulated_receipt_id": "sim_receipt_1",
        "artifact_hash": "hash_abc",
        "idempotency_key": "idem_abc",
        "source_refs": ["method:one"],
    }
    values.update(kwargs)
    return LiveExecutionBlockedReceipt(**values)


def test_mt5_skeleton_status_values_exist():
    assert {"HARD_BLOCKED", "DISABLED", "RESERVED_ONLY", "MISCONFIGURED", "UNKNOWN"} <= MT5_SKELETON_STATUSES


def test_live_execution_block_reason_values_exist():
    assert {
        "HARD_LIVE_BLOCK_ENABLED",
        "LIVE_EXECUTION_DISABLED",
        "MT5_LIVE_ADAPTER_NOT_IMPLEMENTED",
        "ORDER_SEND_FORBIDDEN",
        "EXECUTABLE_ORDER_FORBIDDEN",
        "TRADE_SIDE_FORBIDDEN",
        "ORDER_PARAMETERS_FORBIDDEN",
        "INVALID_SOURCE_CONTRACT",
        "INVALID_SIMULATED_RECEIPT",
        "UNKNOWN",
    } <= LIVE_EXECUTION_BLOCK_REASONS


def test_capability_report_serializes_safely():
    report = MT5ExecutionAdapterSkeleton(policy=_policy()).capability_report(_contract(), _simulated_receipt())
    payload = report.as_dict()
    assert json.dumps(payload)
    assert payload["live_execution_supported"] is False
    assert payload["mt5_order_send_available"] is False


def test_blocked_receipt_serializes_safely():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt())
    payload = receipt.as_dict()
    assert json.dumps(payload)
    assert payload["blocked"] is True
    assert payload["executed"] is False
    assert payload["order_sent"] is False


def test_live_block_journal_record_serializes_safely():
    record = LiveExecutionBlockJournalRecord(
        journal_record_id="record_1",
        created_at="2026-07-17T00:00:04+00:00",
        event_type="LIVE_EXECUTION_BLOCKED",
        adapter_type="RESERVED_MT5_LIVE",
        skeleton_status="HARD_BLOCKED",
        receipt_id="blocked_1",
        blocked=True,
        executed=False,
        order_sent=False,
        live_execution_supported=False,
        hard_live_block_enabled=True,
        block_reason="HARD_LIVE_BLOCK_ENABLED",
        source_contract_id="contract_1",
        source_simulated_receipt_id="sim_receipt_1",
        artifact_hash="hash_abc",
        idempotency_key="idem_abc",
        source_refs=["method:one"],
    )
    assert json.dumps(record.as_dict())


def test_policy_defaults_hard_block_enabled():
    assert MT5ExecutionSkeletonPolicy.from_config().hard_live_block_enabled is True


def test_policy_defaults_live_execution_disabled():
    assert MT5ExecutionSkeletonPolicy.from_config().live_execution_enabled is False


def test_policy_defaults_order_send_disabled():
    assert MT5ExecutionSkeletonPolicy.from_config().order_submission_enabled is False


def test_capability_report_has_live_execution_supported_false():
    report = MT5ExecutionAdapterSkeleton(policy=_policy()).capability_report(_contract(), _simulated_receipt())
    assert report.live_execution_supported is False


def test_capability_report_has_live_execution_enabled_false():
    report = MT5ExecutionAdapterSkeleton(policy=_policy()).capability_report(_contract(), _simulated_receipt())
    assert report.live_execution_enabled is False


def test_capability_report_has_mt5_order_send_available_false():
    report = MT5ExecutionAdapterSkeleton(policy=_policy()).capability_report(_contract(), _simulated_receipt())
    assert report.mt5_order_send_available is False


def test_capability_report_has_hard_live_block_enabled_true():
    report = MT5ExecutionAdapterSkeleton(policy=_policy()).capability_report(_contract(), _simulated_receipt())
    assert report.hard_live_block_enabled is True


def test_blocked_receipt_has_blocked_true():
    assert MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt()).blocked is True


def test_blocked_receipt_has_executed_false():
    assert MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt()).executed is False


def test_blocked_receipt_has_order_sent_false():
    assert MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt()).order_sent is False


def test_blocked_receipt_preserves_source_contract_id():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt())
    assert receipt.source_contract_id == "contract_1"


def test_blocked_receipt_preserves_simulated_receipt_id():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt())
    assert receipt.source_simulated_receipt_id == "sim_receipt_1"


def test_blocked_receipt_preserves_artifact_hash():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt())
    assert receipt.artifact_hash == "hash_abc"


def test_blocked_receipt_preserves_idempotency_key():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), _simulated_receipt())
    assert receipt.idempotency_key == "idem_abc"


def test_missing_simulated_contract_still_returns_blocked_receipt():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(None, _simulated_receipt())
    assert receipt.blocked is True
    assert "simulated_contract_required" in receipt.blockers


def test_missing_simulated_receipt_still_returns_blocked_receipt():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(_contract(), None)
    assert receipt.blocked is True
    assert "simulated_receipt_required" in receipt.blockers


def test_invalid_source_refs_returns_blocked_receipt():
    receipt = MT5ExecutionAdapterSkeleton(policy=_policy()).attempt_live_execution_blocked(
        _contract(source_refs=[]),
        _simulated_receipt(source_refs=[]),
    )
    assert receipt.blocked is True
    assert "source_refs_required" in receipt.blockers


def test_mt5_skeleton_does_not_call_mt5():
    text = Path("src/services/trading/execution/mt5_skeleton_adapter.py").read_text(encoding="utf-8")
    assert "MetaTrader5" not in text
    assert "mt5_client" not in text


def test_mt5_skeleton_does_not_call_llm():
    text = Path("src/services/trading/execution/mt5_skeleton_adapter.py").read_text(encoding="utf-8").lower()
    assert "llm" not in text


def test_mt5_skeleton_does_not_import_metatrader5():
    text = Path("src/services/trading/execution/mt5_skeleton_adapter.py").read_text(encoding="utf-8")
    assert "import MetaTrader5" not in text
    assert "from MetaTrader5" not in text


@pytest.mark.parametrize("method_name", ["order_send", "submit_live_order", "send_order", "place_order", "execute_trade"])
def test_mt5_skeleton_has_no_forbidden_live_method(method_name):
    assert not hasattr(MT5ExecutionAdapterSkeleton(policy=_policy()), method_name)


def test_registry_default_remains_simulated():
    assert ExecutionAdapterRegistry(policy=ExecutionAdapterPolicy(adapter_type="SIMULATED")).get_adapter().adapter_type() == "SIMULATED"


def test_registry_reserved_mt5_live_path_returns_skeleton_only():
    adapter = ExecutionAdapterRegistry(policy=ExecutionAdapterPolicy(adapter_type="RESERVED_MT5_LIVE")).get_adapter()
    assert isinstance(adapter, MT5ExecutionAdapterSkeleton)
    assert adapter.capability_report().live_execution_supported is False


def test_registry_does_not_create_real_live_mt5_adapter():
    adapter = ExecutionAdapterRegistry(policy=ExecutionAdapterPolicy(adapter_type="MT5_LIVE")).get_adapter()
    assert adapter.adapter_type() == "RESERVED_MT5_LIVE"
    assert adapter.capability_report().skeleton_status in {"HARD_BLOCKED", "DISABLED"}


def test_live_block_journal_store_appends_jsonl(tmp_path):
    path = tmp_path / "blocks.jsonl"
    store = LiveExecutionBlockJournalStore(path=path)
    record = MT5ExecutionSkeletonService(policy=_policy(journal_path=str(path))).run(_contract(), _simulated_receipt(), _simulated_record()).journal_record
    assert record is not None
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_live_block_journal_store_reads_latest_records(tmp_path):
    path = tmp_path / "blocks.jsonl"
    store = LiveExecutionBlockJournalStore(path=path)
    service = MT5ExecutionSkeletonService(policy=_policy(journal_path=str(path)))
    first = service.run(_contract(), _simulated_receipt(), _simulated_record()).journal_record
    second = service.run(_contract(), _simulated_receipt(), _simulated_record()).journal_record
    assert first is not None and second is not None
    records = store.read_latest(1)
    assert records[0].journal_record_id == second.journal_record_id


def test_live_block_journal_store_summarizes_records(tmp_path):
    path = tmp_path / "blocks.jsonl"
    MT5ExecutionSkeletonService(policy=_policy(journal_path=str(path))).run(_contract(), _simulated_receipt(), _simulated_record())
    summary = LiveExecutionBlockJournalStore(path=path).summarize()
    assert isinstance(summary, LiveExecutionBlockSummary)
    assert summary.total_records == 1
    assert summary.total_blocked == 1


def test_corrupt_journal_line_returns_warning_not_crash(tmp_path):
    path = tmp_path / "blocks.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")
    store = LiveExecutionBlockJournalStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_mt5_execution_skeleton_service_returns_capability_receipt_journal(tmp_path):
    result = MT5ExecutionSkeletonService(policy=_policy(journal_path=str(tmp_path / "blocks.jsonl"))).run(
        _contract(),
        _simulated_receipt(),
        _simulated_record(),
    )
    assert result.capability_report.live_execution_supported is False
    assert result.blocked_receipt.blocked is True
    assert result.journal_record is not None


@pytest.mark.parametrize(
    ("payload_update", "expected_issue"),
    [
        ({"blockers": ["BUY"]}, "buy_sell_marker_present"),
        ({"blockers": ["LONG"]}, "side_marker_present"),
        ({"blockers": ["trade_side"]}, "side_marker_present"),
        ({"blockers": ["entry_price"]}, "price_or_size_marker_present"),
        ({"blockers": ["position_size"]}, "price_or_size_marker_present"),
        ({"blockers": ["order" + "_send"]}, "order_marker_present"),
        ({"blockers": ["submit_live_order"]}, "order_marker_present"),
        ({"blockers": ["send_order"]}, "order_marker_present"),
        ({"blockers": ["place_order"]}, "order_marker_present"),
        ({"blockers": ["execute_trade"]}, "order_marker_present"),
        ({"blockers": ["executable_order"]}, "order_marker_present"),
        ({"blockers": ["mt5_ticket"]}, "mt5_ticket_marker_present"),
        ({"blockers": ["raw_candles"]}, "raw_candle_marker_present"),
        ({"blockers": ["raw_full_book"]}, "raw_knowledge_marker_present"),
        ({"blockers": ["account_id"]}, "account_or_credential_marker_present"),
    ],
)
def test_validator_rejects_forbidden_markers(payload_update, expected_issue):
    receipt = _blocked_receipt(**payload_update)
    validation = HardLiveBlockValidator().validate_receipt(receipt)
    assert expected_issue in validation.issues


def test_dashboard_has_no_confirm_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Confirm Trade" not in text


def test_dashboard_has_no_execute_trade_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Execute Trade" not in text


def test_dashboard_has_no_place_order_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Place Order" not in text


def test_dashboard_has_no_buy_sell_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Buy" not in text
    assert "Sell" not in text


def test_dashboard_labels_live_execution_as_hard_blocked():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "MT5 Live Execution Capability - Hard Blocked" in text
    assert "Check MT5 Live Execution Capability" in text


def test_no_order_endpoints_added_to_mt5_bridge_server():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    forbidden_paths = ['"/order"', '"/execute"', '"/send_order"', '"/order_send"', '"/trade"', '"/position/open"']
    assert not any(path in text for path in forbidden_paths)


def test_mt5_bridge_post_handler_exposes_only_controlled_execution_routes():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    assert "def do_POST" in text
    for endpoint in ["/execution/write-skeleton/check", "/execution/controlled-submit", "/execution/reconcile"]:
        assert endpoint in text


def test_order_send_call_is_isolated_to_host_execution_boundary():
    src_text = "\n".join(item.read_text(encoding="utf-8", errors="ignore") for item in Path("src").rglob("*.py"))
    execution_text = Path("tools/mt5_bridge/execution.py").read_text(encoding="utf-8", errors="ignore")
    reconciliation_text = Path("tools/mt5_bridge/reconciliation.py").read_text(encoding="utf-8", errors="ignore")
    marker = ".order" + "_send("
    assert marker not in src_text
    assert execution_text.count(marker) == 1
    assert marker not in reconciliation_text


def test_no_qdrant_reset_delete_recreate():
    texts = [
        Path("src/services/trading/execution/mt5_skeleton_service.py").read_text(encoding="utf-8").lower(),
        Path("src/services/trading/execution/mt5_skeleton_adapter.py").read_text(encoding="utf-8").lower(),
    ]
    assert "delete_collection" not in "\n".join(texts)
    assert "recreate_collection" not in "\n".join(texts)


def test_no_rag_evidence_behavior_changed_in_skeleton_modules():
    text = "\n".join(
        item.read_text(encoding="utf-8")
        for item in Path("src/services/trading/execution").glob("mt5_skeleton*.py")
    ).lower()
    assert "rag" not in text
    assert "evidence" not in text


def test_unit_test_does_not_call_oanda_rest_live_calendar_real_mt5_or_llm():
    text = Path(__file__).read_text(encoding="utf-8").lower()
    assert "requests" + ".get" not in text
    assert "forexfactorycalendar" + "provider" not in text
    assert "mt5bridge" + "marketdataprovider" not in text
    assert "open" + "ai" not in text
    assert "anth" + "ropic" not in text
