from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.trading.execution.adapter_models import (
    SimulatedExecutionJournalRecord,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
)
from src.services.trading.execution.live_design import (
    LiveExecutionDesignPolicy,
    LiveExecutionReadinessSpecReportBuilder,
)
from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockedReceipt,
    LiveExecutionCapabilityReport,
)
from src.services.trading.execution.preflight import (
    PREFLIGHT_CHECK_CATEGORIES,
    PREFLIGHT_CHECK_STATUSES,
    PREFLIGHT_SEVERITIES,
    LiveExecutionPreflightFormatter,
    LiveExecutionPreflightHarness,
    LiveExecutionPreflightPolicy,
    LiveExecutionPreflightReadinessReport,
    LiveExecutionPreflightReportStore,
    LiveExecutionPreflightService,
    LiveExecutionPreflightValidator,
    PreflightCheckResult,
    PreflightCheckRunner,
    PreflightEvidenceCollector,
    PreflightEvidenceSnapshot,
    PreflightJournalRecord,
)


SOURCE_REF = "preflight://source/ref"


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


def _sim_record() -> SimulatedExecutionJournalRecord:
    return SimulatedExecutionJournalRecord(
        journal_record_id="sim_journal_1",
        created_at="2026-07-17T00:00:04+00:00",
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
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _block_record() -> LiveExecutionBlockJournalRecord:
    return LiveExecutionBlockJournalRecord(
        journal_record_id="block_journal_1",
        created_at="2026-07-17T00:00:05+00:00",
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
        artifact_hash="artifact_hash",
        idempotency_key="idem_key",
        source_refs=[SOURCE_REF],
    )


def _design_report():
    policy = LiveExecutionDesignPolicy(
        journal_enabled=False,
        min_critical_threats=5,
        min_preflight_checks=10,
        min_approval_requirements=8,
        min_failure_modes=8,
        min_audit_requirements=8,
    )
    return LiveExecutionReadinessSpecReportBuilder(policy).build(
        _capability(),
        _blocked_receipt(),
        _contract(),
        _sim_receipt(),
    )


def _policy(tmp_path: Path | None = None) -> LiveExecutionPreflightPolicy:
    journal_path = str((tmp_path or Path("unused")).joinpath("preflight.jsonl"))
    return LiveExecutionPreflightPolicy(journal_path=journal_path)


def _evidence(tmp_path: Path | None = None) -> PreflightEvidenceSnapshot:
    return PreflightEvidenceCollector(_policy(tmp_path)).collect(
        _design_report(),
        _capability(),
        _blocked_receipt(),
        _contract(),
        _sim_receipt(),
        _block_record(),
    )


def _report(tmp_path: Path | None = None) -> LiveExecutionPreflightReadinessReport:
    return LiveExecutionPreflightHarness(_policy(tmp_path)).build(
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        simulated_receipt=_sim_receipt(),
        live_block_journal_record=_block_record(),
    )


@pytest.mark.parametrize(
    "value",
    [
        "CONFIG",
        "HARD_BLOCK",
        "ADAPTER_REGISTRY",
        "MT5_BRIDGE",
        "CODE_SCAN",
        "UI_SCAN",
        "JOURNAL",
        "SOURCE_REFS",
        "IDEMPOTENCY",
        "REDACTION",
        "DESIGN_SPEC",
        "SIMULATED_CONTRACT",
        "RUNTIME_ENV",
        "UNKNOWN",
    ],
)
def test_preflight_check_category_values_exist(value):
    assert value in PREFLIGHT_CHECK_CATEGORIES


@pytest.mark.parametrize("value", ["PASS", "FAIL", "WARN", "SKIPPED", "UNKNOWN"])
def test_preflight_check_status_values_exist(value):
    assert value in PREFLIGHT_CHECK_STATUSES


@pytest.mark.parametrize("value", ["INFO", "WARNING", "BLOCKING", "CRITICAL"])
def test_preflight_severity_values_exist(value):
    assert value in PREFLIGHT_SEVERITIES


def test_preflight_evidence_snapshot_serializes_safely(tmp_path):
    assert json.dumps(_evidence(tmp_path).as_dict())


def test_preflight_check_result_serializes_safely():
    check = PreflightCheckResult("c", "CONFIG", "title", "PASS", "INFO", False, "expected", "observed", source_refs=[SOURCE_REF])
    assert json.dumps(check.as_dict())


def test_live_execution_preflight_readiness_report_serializes_safely(tmp_path):
    assert json.dumps(_report(tmp_path).as_dict())


def test_preflight_journal_record_serializes_safely():
    record = PreflightJournalRecord(
        "j",
        "2026-07-17T00:00:00+00:00",
        "report",
        "PASS",
        False,
        True,
        40,
        40,
        0,
        0,
        0,
        0,
        True,
        "design",
        "capability",
        "blocked",
        [SOURCE_REF],
    )
    assert json.dumps(record.as_dict())


def test_policy_defaults_preflight_enabled():
    assert LiveExecutionPreflightPolicy.from_config().enabled is True


@pytest.mark.parametrize(
    "attr",
    [
        "require_design_report",
        "require_capability_report",
        "require_blocked_receipt",
        "require_hard_block",
        "require_order_submission_absent",
        "require_controlled_order_send_boundary",
        "require_no_bridge_order_endpoints",
        "require_no_docker_mt5_import",
        "require_journal_writable",
        "require_source_refs",
        "require_idempotency",
        "require_redaction",
        "require_ui_safe_wording",
    ],
)
def test_policy_required_defaults(attr):
    assert getattr(LiveExecutionPreflightPolicy.from_config(), attr) is True


def test_evidence_collector_summarizes_config_safely(tmp_path):
    summary = _evidence(tmp_path).config_summary_redacted
    assert summary["live_execution_enabled"] is False
    assert summary["hard_block_enabled"] is True
    assert summary["order_submission_enabled"] is False


def test_evidence_collector_summarizes_adapter_registry_safely(tmp_path):
    summary = _evidence(tmp_path).adapter_registry_summary
    assert summary["default_adapter_type"] == "SIMULATED"
    assert summary["reserved_returns_skeleton_only"] is True
    assert summary["real_live_adapter_active"] is False


def test_evidence_collector_summarizes_mt5_bridge_endpoints_safely(tmp_path):
    summary = _evidence(tmp_path).mt5_bridge_endpoint_summary
    assert summary["forbidden_endpoint_present"] is False
    assert summary["controlled_endpoints_complete"] is True
    assert summary["do_post_execution_handler_present"] is True


def test_evidence_collector_summarizes_code_scan_safely(tmp_path):
    summary = _evidence(tmp_path).code_scan_summary
    assert summary["order_submission_absent"] is False
    assert summary["controlled_order_submission_call_site_valid"] is True
    assert summary["app_order_submission_absent"] is True
    assert summary["reconciliation_order_submission_absent"] is True
    assert summary["live_methods_absent"] is True
    assert summary["docker_side_mt5_import_absent"] is True


def test_evidence_collector_summarizes_ui_scan_safely(tmp_path):
    summary = _evidence(tmp_path).ui_scan_summary
    assert summary["unsafe_button_present"] is False
    assert summary["preflight_button_present"] is True


def test_evidence_collector_summarizes_journal_safely(tmp_path):
    summary = _evidence(tmp_path).journal_summary
    assert summary["journal_parent_writable"] is True
    assert summary["runtime_jsonl_gitignored"] is True


def test_evidence_collector_does_not_store_raw_file_contents(tmp_path):
    payload = json.dumps(_evidence(tmp_path).as_dict())
    assert "def render(" not in payload
    assert "class Config" not in payload


def test_runner_creates_at_least_40_checks(tmp_path):
    checks = PreflightCheckRunner(_policy(tmp_path)).run(_evidence(tmp_path))
    assert len(checks) >= 40


@pytest.mark.parametrize(
    "check_id",
    [
        "design_report_exists",
        "design_live_execution_not_allowed",
        "design_hard_block_required",
        "capability_report_exists",
        "capability_live_unsupported",
        "blocked_receipt_not_executed",
        "blocked_receipt_no_order_sent",
        "config_live_disabled",
        "config_hard_block_enabled",
        "config_order_submission_disabled",
        "bridge_no_forbidden_execution_endpoints",
        "bridge_controlled_execution_endpoints_complete",
        "bridge_post_handler_controlled",
        "code_controlled_order_submission_call_site",
        "code_no_app_order_submission_call",
        "code_no_reconciliation_order_submission_call",
        "code_no_live_method_names",
        "code_no_docker_side_mt5_import",
        "dashboard_no_confirm_trade_button",
        "dashboard_no_execute_trade_button",
        "dashboard_no_place_order_button",
        "dashboard_no_buy_sell_button",
        "dashboard_preflight_label_safe",
        "journal_path_writable",
        "runtime_jsonl_gitignored",
        "source_refs_present",
        "artifact_hash_present",
        "idempotency_key_present",
        "redaction_no_raw_account_id",
        "redaction_no_credentials",
        "simulated_contract_simulated_only",
        "simulated_receipt_non_executable",
        "simulated_receipt_not_executed",
    ],
)
def test_runner_contains_required_checks(tmp_path, check_id):
    checks = {item.check_id: item for item in PreflightCheckRunner(_policy(tmp_path)).run(_evidence(tmp_path))}
    assert check_id in checks


def test_harness_forces_live_execution_allowed_false(tmp_path):
    assert _report(tmp_path).live_execution_allowed is False


def test_harness_forces_hard_live_block_required_true(tmp_path):
    assert _report(tmp_path).hard_live_block_required is True


def test_harness_computes_counts_correctly(tmp_path):
    report = _report(tmp_path)
    assert report.total_checks == len(report.check_results)
    assert report.passed_checks + report.failed_checks + report.warning_checks + report.skipped_checks == report.total_checks


def test_harness_surfaces_blocking_failures(tmp_path):
    report = LiveExecutionPreflightHarness(_policy(tmp_path)).build(
        _design_report(),
        _capability(),
        _blocked_receipt(),
        simulated_contract=_contract(),
        simulated_receipt=None,
        live_block_journal_record=_block_record(),
    )
    assert report.blocking_failures >= 1
    assert report.blockers


def test_store_appends_jsonl(tmp_path):
    store = LiveExecutionPreflightReportStore(tmp_path / "preflight.jsonl")
    result = LiveExecutionPreflightService(_policy(tmp_path), store=store).run(
        _design_report(), _capability(), _blocked_receipt(), _contract(), _sim_receipt(), _block_record()
    )
    assert result.journal_record is not None
    assert store.path.exists()


def test_store_reads_latest_reports(tmp_path):
    store = LiveExecutionPreflightReportStore(tmp_path / "preflight.jsonl")
    service = LiveExecutionPreflightService(_policy(tmp_path), store=store)
    service.run(_design_report(), _capability(), _blocked_receipt(), _contract(), _sim_receipt(), _block_record())
    assert store.read_latest()


def test_store_summarizes_reports(tmp_path):
    store = LiveExecutionPreflightReportStore(tmp_path / "preflight.jsonl")
    service = LiveExecutionPreflightService(_policy(tmp_path), store=store)
    service.run(_design_report(), _capability(), _blocked_receipt(), _contract(), _sim_receipt(), _block_record())
    assert store.summarize().total_records == 1


def test_corrupt_jsonl_line_returns_warning_not_crash(tmp_path):
    path = tmp_path / "preflight.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    store = LiveExecutionPreflightReportStore(path)
    assert store.read_latest() == []
    assert store.warnings


def test_service_builds_report_and_journal_record(tmp_path):
    store = LiveExecutionPreflightReportStore(tmp_path / "preflight.jsonl")
    result = LiveExecutionPreflightService(_policy(tmp_path), store=store).run(
        _design_report(), _capability(), _blocked_receipt(), _contract(), _sim_receipt(), _block_record()
    )
    assert result.report.total_checks >= 40
    assert result.journal_record is not None


def test_formatter_creates_json_safe_card(tmp_path):
    card = LiveExecutionPreflightFormatter().to_card(_report(tmp_path))
    assert json.dumps(card.as_dict())


def test_formatter_creates_markdown_summary(tmp_path):
    markdown = LiveExecutionPreflightFormatter().to_markdown(_report(tmp_path))
    assert "Preflight only" in markdown
    assert "live_execution_allowed: false" in markdown


@pytest.mark.parametrize(
    "field, value, issue",
    [
        ("live_execution_allowed", True, "live_execution_allowed_must_be_false"),
        ("blockers", ["order" + "_send"], "order_submission_marker_present"),
        ("blockers", ["submit_live_order"], "live_method_marker_present"),
        ("blockers", ["executable_order"], "executable_order_marker_present"),
        ("blockers", ["mt5_ticket"], "mt5_ticket_marker_present"),
        ("blockers", ["trade_side"], "trade_side_marker_present"),
        ("blockers", ["BUY"], "direction_marker_present"),
        ("blockers", ["SELL"], "direction_marker_present"),
        ("blockers", ["LONG"], "direction_marker_present"),
        ("blockers", ["SHORT"], "direction_marker_present"),
        ("blockers", ["entry_price"], "price_or_size_marker_present"),
        ("blockers", ["position_size"], "price_or_size_marker_present"),
        ("blockers", ["raw_candles"], "raw_candle_marker_present"),
        ("blockers", ["full_raw_book"], "raw_knowledge_marker_present"),
        ("blockers", ["account_id"], "account_or_credential_marker_present"),
    ],
)
def test_validator_rejects_forbidden_markers(tmp_path, field, value, issue):
    report = _report(tmp_path)
    setattr(report, field, value)
    result = LiveExecutionPreflightValidator(_policy(tmp_path)).validate_report(report)
    assert issue in result.issues


def test_dashboard_ui_code_does_not_add_forbidden_buttons():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8", errors="ignore")
    for label in ["Confirm Trade", "Execute Trade", "Place Order", "Buy", "Sell"]:
        assert f'st.button("{label}"' not in text
        assert f"st.button('{label}'" not in text


def test_dashboard_ui_labels_preflight_as_preflight_only_and_live_disabled():
    text = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8", errors="ignore")
    assert "Run Live Execution Preflight" in text
    assert "Preflight only" in text
    assert "Live execution remains disabled" in text


def test_no_order_endpoints_added_to_mt5_bridge_server():
    text = Path("tools/mt5_bridge/server.py").read_text(encoding="utf-8", errors="ignore")
    for marker in ["/order", "/execute", "/send" + "_order", "/order" + "_send", "/trade", "/position/open"]:
        assert marker not in text
    for endpoint in ["/execution/write-skeleton/check", "/execution/controlled-submit", "/execution/reconcile"]:
        assert endpoint in text
    assert "def do_POST" in text


def test_unit_fixtures_do_not_call_live_external_services():
    text = Path(__file__).read_text(encoding="utf-8", errors="ignore")
    assert "MT5BridgeMarketData" + "Provider(" not in text
    assert "ForexFactoryCalendar" + "Provider(" not in text
    assert "Open" + "AI(" not in text
    assert "requests." + "get(" not in text


def test_no_qdrant_reset_or_rag_redesign_markers():
    text = Path(__file__).read_text(encoding="utf-8", errors="ignore")
    assert "delete_" + "collection" not in text
    assert "recreate_" + "collection" not in text
