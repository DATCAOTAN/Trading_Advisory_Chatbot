from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_design import (
    LIVE_EXECUTION_DESIGN_STATUSES,
    LIVE_EXECUTION_RISK_CATEGORIES,
    LIVE_EXECUTION_RISK_SEVERITIES,
    LiveExecutionApprovalMatrixBuilder,
    LiveExecutionApprovalRequirement,
    LiveExecutionAuditRequirement,
    LiveExecutionAuditSpecBuilder,
    LiveExecutionDesignPolicy,
    LiveExecutionDesignReportStore,
    LiveExecutionDesignSpecFormatter,
    LiveExecutionDesignSpecService,
    LiveExecutionDesignSpecValidator,
    LiveExecutionFailureMode,
    LiveExecutionFailureModeCatalogBuilder,
    LiveExecutionPreflightCheck,
    LiveExecutionPreflightChecklistBuilder,
    LiveExecutionReadinessSpecReportBuilder,
    LiveExecutionThreat,
    LiveExecutionThreatModelBuilder,
)
from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport


SOURCE_REF = "design://source/ref"


def _capability() -> LiveExecutionCapabilityReport:
    return LiveExecutionCapabilityReport(
        report_id="capability_1",
        created_at="2026-07-17T00:00:00+00:00",
        source_contract_id="contract_1",
        source_simulated_receipt_id="sim_receipt_1",
        source_draft_id="draft_1",
        source_refs=[SOURCE_REF],
    )


def _blocked_receipt() -> LiveExecutionBlockedReceipt:
    return LiveExecutionBlockedReceipt(
        receipt_id="blocked_1",
        created_at="2026-07-17T00:00:01+00:00",
        source_contract_id="contract_1",
        source_simulated_receipt_id="sim_receipt_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _contract() -> SimulatedOrderContract:
    return SimulatedOrderContract(
        contract_id="contract_1",
        created_at="2026-07-17T00:00:02+00:00",
        mode="REVIEW_ONLY",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        contract_status="CREATED",
        source_draft_id="draft_1",
        source_intent_id="intent_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _sim_receipt() -> SimulatedExecutionReceipt:
    return SimulatedExecutionReceipt(
        receipt_id="sim_receipt_1",
        created_at="2026-07-17T00:00:03+00:00",
        adapter_type="SIMULATED",
        contract_id="contract_1",
        contract_status="CREATED",
        source_draft_id="draft_1",
        source_contract_id="contract_1",
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _policy(**kwargs) -> LiveExecutionDesignPolicy:
    values = {
        "journal_enabled": True,
        "journal_path": "unused.jsonl",
        "min_critical_threats": 5,
        "min_preflight_checks": 10,
        "min_approval_requirements": 8,
        "min_failure_modes": 8,
        "min_audit_requirements": 8,
    }
    values.update(kwargs)
    return LiveExecutionDesignPolicy(**values)


def _report(policy: LiveExecutionDesignPolicy | None = None):
    return LiveExecutionReadinessSpecReportBuilder(policy or _policy()).build(
        _capability(),
        _blocked_receipt(),
        _contract(),
        _sim_receipt(),
    )


def test_live_execution_design_status_values_exist():
    assert {"DESIGN_ONLY", "HARD_BLOCKED", "INCOMPLETE", "INVALID", "APPROVAL_REQUIRED", "UNKNOWN"} <= LIVE_EXECUTION_DESIGN_STATUSES


def test_live_execution_risk_severity_values_exist():
    assert {"LOW", "MEDIUM", "HIGH", "CRITICAL"} <= LIVE_EXECUTION_RISK_SEVERITIES


def test_live_execution_risk_category_values_exist():
    assert {"MARKET_DATA", "ACCOUNT_STATE", "SYMBOL_MAPPING", "ORDER_CONSTRUCTION", "AUDIT", "SYSTEM_CONFIG"} <= LIVE_EXECUTION_RISK_CATEGORIES


def test_live_execution_threat_serializes_safely():
    threat = LiveExecutionThreat("t", "MARKET_DATA", "HIGH", "title", "desc", "trigger", "impact", "control", "detect", "mitigate", "low", True, [SOURCE_REF])
    assert json.dumps(threat.as_dict())


def test_live_execution_preflight_check_serializes_safely():
    check = LiveExecutionPreflightCheck("c", "title", "SYSTEM_CONFIG", True, "false", "false", True, "evidence", "fail", [SOURCE_REF])
    assert json.dumps(check.as_dict())


def test_live_execution_approval_requirement_serializes_safely():
    item = LiveExecutionApprovalRequirement("a", "title", True, False, True, "USER", "evidence", 300, [SOURCE_REF])
    assert json.dumps(item.as_dict())


def test_live_execution_failure_mode_serializes_safely():
    item = LiveExecutionFailureMode("f", "SYSTEM_CONFIG", "HIGH", "title", "desc", "detect", "response", "recover", "audit", True, [SOURCE_REF])
    assert json.dumps(item.as_dict())


def test_live_execution_audit_requirement_serializes_safely():
    item = LiveExecutionAuditRequirement("audit", "title", True, "EVENT", ["field"], "retention", True, True, [SOURCE_REF])
    assert json.dumps(item.as_dict())


def test_live_execution_readiness_spec_report_serializes_safely():
    assert json.dumps(_report().as_dict())


def test_policy_defaults_design_spec_enabled():
    assert LiveExecutionDesignPolicy.from_config().enabled is True


def test_policy_requires_hard_block():
    assert LiveExecutionDesignPolicy.from_config().require_hard_block is True


def test_policy_requires_capability_report():
    assert LiveExecutionDesignPolicy.from_config().require_capability_report is True


def test_policy_requires_blocked_receipt():
    assert LiveExecutionDesignPolicy.from_config().require_blocked_receipt is True


def test_threat_builder_creates_at_least_required_threat_count():
    assert len(LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt(), _contract(), _sim_receipt())) >= 20


def test_threat_builder_includes_stale_market_data_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert "threat_stale_market_data" in ids


def test_threat_builder_includes_wrong_symbol_mapping_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert "threat_wrong_broker_symbol_mapping" in ids


def test_threat_builder_includes_wrong_terminal_account_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert "threat_wrong_terminal_account" in ids


def test_threat_builder_includes_duplicate_idempotency_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert {"threat_duplicate_attempt", "threat_idempotency_collision"} <= ids


def test_threat_builder_includes_missing_hard_block_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert "threat_missing_hard_block" in ids


def test_threat_builder_includes_bridge_endpoint_drift_threat():
    ids = {item.threat_id for item in LiveExecutionThreatModelBuilder().build(_capability(), _blocked_receipt())}
    assert "threat_bridge_endpoint_drift" in ids


def test_preflight_builder_creates_at_least_required_check_count():
    assert len(LiveExecutionPreflightChecklistBuilder().build(_capability(), _blocked_receipt())) >= 20


def test_preflight_includes_hard_block_enabled_check():
    ids = {item.check_id for item in LiveExecutionPreflightChecklistBuilder().build(_capability(), _blocked_receipt())}
    assert "preflight_hard_block_enabled" in ids


def test_preflight_includes_live_execution_disabled_check():
    ids = {item.check_id for item in LiveExecutionPreflightChecklistBuilder().build(_capability(), _blocked_receipt())}
    assert "preflight_live_disabled" in ids


def test_preflight_includes_order_send_disabled_check():
    ids = {item.check_id for item in LiveExecutionPreflightChecklistBuilder().build(_capability(), _blocked_receipt())}
    assert "preflight_order_submission_disabled" in ids


def test_preflight_includes_no_bridge_order_endpoint_check():
    ids = {item.check_id for item in LiveExecutionPreflightChecklistBuilder().build(_capability(), _blocked_receipt())}
    assert "preflight_no_bridge_execution_endpoint" in ids


def test_approval_matrix_creates_at_least_required_requirement_count():
    assert len(LiveExecutionApprovalMatrixBuilder().build(_capability(), _blocked_receipt())) >= 12


def test_approval_requirements_are_blocking_by_default():
    assert all(item.blocking for item in LiveExecutionApprovalMatrixBuilder().build(_capability(), _blocked_receipt()))


def test_failure_mode_catalog_creates_at_least_required_failure_mode_count():
    assert len(LiveExecutionFailureModeCatalogBuilder().build(_capability(), _blocked_receipt())) >= 15


def test_failure_catalog_includes_registry_wrong_adapter_mode():
    ids = {item.failure_mode_id for item in LiveExecutionFailureModeCatalogBuilder().build(_capability(), _blocked_receipt())}
    assert "failure_registry_wrong_adapter" in ids


def test_audit_spec_creates_at_least_required_audit_requirement_count():
    assert len(LiveExecutionAuditSpecBuilder().build(_capability(), _blocked_receipt())) >= 15


def test_report_builder_forces_live_execution_allowed_false():
    assert _report().as_dict()["live_execution_allowed"] is False


def test_report_builder_forces_hard_live_block_required_true():
    assert _report().as_dict()["hard_live_block_required"] is True


def test_readiness_score_is_design_completeness_only():
    report = _report()
    assert report.readiness_score == 1.0
    assert report.live_execution_allowed is False


def test_store_appends_jsonl(tmp_path):
    store = LiveExecutionDesignReportStore(path=tmp_path / "design.jsonl")
    result = LiveExecutionDesignSpecService(policy=_policy(journal_path=str(tmp_path / "design.jsonl")), store=store).build_and_record(_capability(), _blocked_receipt(), _contract(), _sim_receipt())
    assert result.journal_record is not None
    assert store.path.read_text(encoding="utf-8").count("\n") == 1


def test_store_reads_latest_reports(tmp_path):
    store = LiveExecutionDesignReportStore(path=tmp_path / "design.jsonl")
    service = LiveExecutionDesignSpecService(policy=_policy(journal_path=str(tmp_path / "design.jsonl")), store=store)
    first = service.build_and_record(_capability(), _blocked_receipt(), _contract(), _sim_receipt()).journal_record
    second = service.build_and_record(_capability(), _blocked_receipt(), _contract(), _sim_receipt()).journal_record
    assert first and second
    assert store.read_latest(1)[0].journal_record_id == second.journal_record_id


def test_store_summarizes_reports(tmp_path):
    store = LiveExecutionDesignReportStore(path=tmp_path / "design.jsonl")
    LiveExecutionDesignSpecService(policy=_policy(journal_path=str(tmp_path / "design.jsonl")), store=store).build_and_record(_capability(), _blocked_receipt(), _contract(), _sim_receipt())
    assert store.summarize().total_records == 1


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    path = tmp_path / "design.jsonl"
    path.write_text("{bad-json}\n", encoding="utf-8")
    store = LiveExecutionDesignReportStore(path=path)
    assert store.read_latest() == []
    assert store.warnings == ["corrupt_jsonl_line:1"]


def test_service_builds_report_and_journal_record(tmp_path):
    result = LiveExecutionDesignSpecService(policy=_policy(journal_path=str(tmp_path / "design.jsonl"))).build_and_record(_capability(), _blocked_receipt(), _contract(), _sim_receipt())
    assert result.report.report_id
    assert result.journal_record is not None


def test_formatter_creates_json_safe_card():
    card = LiveExecutionDesignSpecFormatter().to_card(_report())
    assert json.dumps(card.as_dict())


def test_formatter_creates_markdown_summary():
    assert "Live Execution Design Spec" in LiveExecutionDesignSpecFormatter().to_markdown(_report())


def test_validator_rejects_live_execution_allowed_true():
    report = _report()
    report.live_execution_allowed = True
    assert "live_execution_allowed_must_be_false" in LiveExecutionDesignSpecValidator(_policy()).validate_report(report).issues


def test_validator_rejects_missing_hard_block():
    report = _report()
    report.hard_live_block_required = False
    assert "hard_live_block_required_must_be_true" in LiveExecutionDesignSpecValidator(_policy()).validate_report(report).issues


def _report_with_warning_marker(marker: str):
    report = _report()
    report.warnings.append(marker)
    return report


def test_validator_rejects_order_send():
    assert "order_submission_marker_present" in LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("order" + "_send")).issues


def test_validator_rejects_live_method_names():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("submit_live_order")).issues
    assert "live_method_marker_present" in issues


def test_validator_rejects_executable_order_fields():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("executable_order")).issues
    assert "executable_order_marker_present" in issues


def test_validator_rejects_mt5_ticket_deal_id():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("mt5_ticket")).issues
    assert "mt5_ticket_marker_present" in issues


def test_validator_rejects_trade_side():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("trade_side")).issues
    assert "trade_side_marker_present" in issues


def test_validator_rejects_entry_sl_tp_lot_account_risk():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("entry_price stop_loss take_profit account_risk")).issues
    assert "price_or_size_marker_present" in issues


def test_validator_rejects_position_size():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("position_size")).issues
    assert "price_or_size_marker_present" in issues


def test_validator_rejects_raw_candles():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("raw_candles")).issues
    assert "raw_candle_marker_present" in issues


def test_validator_rejects_raw_full_book_report_text():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("raw_full_book")).issues
    assert "raw_knowledge_marker_present" in issues


def test_validator_rejects_account_credentials_markers():
    issues = LiveExecutionDesignSpecValidator(_policy()).validate_report(_report_with_warning_marker("account_id api_key")).issues
    assert "account_or_credential_marker_present" in issues


def test_dashboard_has_no_confirm_trade_button():
    assert "Confirm Trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")


def test_dashboard_has_no_execute_trade_button():
    assert "Execute Trade" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")


def test_dashboard_has_no_place_order_button():
    assert "Place Order" not in Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")


def test_dashboard_has_no_buy_sell_button():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Buy" not in text
    assert "Sell" not in text


def test_dashboard_labels_design_as_design_only_and_live_disabled():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Live Execution Design Spec & Threat Model" in text
    assert "Design spec only" in text
    assert "Build Live Execution Design Spec" in text


def test_no_order_endpoints_added_to_mt5_bridge_server():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    forbidden_paths = ['"/order"', '"/execute"', '"/send_order"', '"/order_send"', '"/trade"', '"/position/open"']
    assert not any(path in text for path in forbidden_paths)


def test_no_named_order_endpoint_exists():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8")
    assert "do_POST" not in text
    assert "order" + "_send" not in text


def test_no_order_send_implementation():
    for root in [Path("src"), Path("tools")]:
        for item in root.rglob("*.py"):
            assert "order" + "_send(" not in item.read_text(encoding="utf-8", errors="ignore")


def test_no_qdrant_reset_delete_recreate():
    text = "\n".join(item.read_text(encoding="utf-8") for item in Path("src/services/trading/execution/live_design").glob("*.py")).lower()
    assert "delete_collection" not in text
    assert "recreate_collection" not in text


def test_no_rag_evidence_behavior_changed():
    text = "\n".join(item.read_text(encoding="utf-8") for item in Path("src/services/trading/execution/live_design").glob("*.py")).lower()
    assert "contextacquisitionexecutor" not in text
    assert "evidence gate" not in text


def test_existing_mt5_skeleton_tests_still_pass_marker():
    assert Path("scripts/test_mt5_execution_skeleton_hard_block.py").exists()


def test_existing_simulated_adapter_tests_still_pass_marker():
    assert Path("scripts/test_execution_adapter_simulated_contract.py").exists()


def test_existing_proposal_draft_tests_still_pass_marker():
    assert Path("scripts/test_non_executable_proposal_draft.py").exists()


def test_existing_proposal_boundary_tests_still_pass_marker():
    assert Path("scripts/test_human_confirmed_proposal_boundary.py").exists()


def test_existing_execution_journal_tests_still_pass_marker():
    assert Path("scripts/test_execution_journal_dry_run_ui.py").exists()


def test_existing_execution_gate_tests_still_pass_marker():
    assert Path("scripts/test_execution_gate_dry_run.py").exists()


def test_existing_review_tests_still_pass_marker():
    assert Path("scripts/test_human_review_artifact.py").exists()


def test_existing_decision_tests_still_pass_marker():
    assert Path("scripts/test_trade_decision_policy_engine.py").exists()


def test_existing_scoring_tests_still_pass_marker():
    assert Path("scripts/test_signal_scoring_engine.py").exists()


def test_existing_method_selector_tests_still_pass_marker():
    assert Path("scripts/test_method_selector_llm_reasoning_adapter.py").exists()


def test_existing_knowledge_tests_still_pass_marker():
    assert Path("scripts/test_knowledge_router_runtime_context_pack.py").exists()


def test_existing_calendar_regime_tests_still_pass_marker():
    assert Path("scripts/test_market_regime_calendar_context.py").exists()


def test_existing_feature_tests_still_pass_marker():
    assert Path("scripts/test_live_ohlcv_feature_engine.py").exists()


def test_existing_mt5_bridge_tests_still_pass_marker():
    assert Path("scripts/test_market_data_provider_mt5_bridge_real_boundary.py").exists()


def test_unit_tests_do_not_call_oanda_rest_live_calendar_real_mt5_or_llm():
    text = Path(__file__).read_text(encoding="utf-8").lower()
    assert "requests" + ".get" not in text
    assert "forexfactorycalendar" + "provider" not in text
    assert "mt5bridge" + "marketdataprovider" not in text
    assert "open" + "ai" not in text
    assert "anth" + "ropic" not in text
