from __future__ import annotations

from typing import Any

from src.services.trading.execution.preflight.models import PreflightCheckResult, PreflightEvidenceSnapshot
from src.services.trading.execution.preflight.policy import LiveExecutionPreflightPolicy


class PreflightCheckRunner:
    def __init__(self, policy: LiveExecutionPreflightPolicy | None = None):
        self.policy = policy or LiveExecutionPreflightPolicy.from_config()

    def run(self, evidence: PreflightEvidenceSnapshot) -> list[PreflightCheckResult]:
        data = evidence.as_dict()
        checks: list[PreflightCheckResult] = []
        add = checks.append
        source_refs_count = int(data["source_refs_summary"].get("source_refs_count", 0) or 0)

        add(_check("design_report_exists", "DESIGN_SPEC", "Design report exists", data["design_spec_summary"].get("design_report_exists"), True, self.policy.require_design_report, data["design_spec_summary"], source_refs_count))
        add(_check("design_live_execution_not_allowed", "DESIGN_SPEC", "Design report keeps live execution disabled", data["design_spec_summary"].get("live_execution_allowed") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("design_hard_block_required", "DESIGN_SPEC", "Design report requires hard block", data["design_spec_summary"].get("hard_live_block_required") is True, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("capability_report_exists", "HARD_BLOCK", "Capability report exists", data["design_spec_summary"].get("capability_report_exists") is True, True, self.policy.require_capability_report, data["design_spec_summary"], source_refs_count))
        add(_check("capability_live_unsupported", "HARD_BLOCK", "Capability says live unsupported", data["design_spec_summary"].get("capability_live_execution_supported") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("capability_live_disabled", "HARD_BLOCK", "Capability says live disabled", data["design_spec_summary"].get("capability_live_execution_enabled") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("capability_order_submission_unavailable", "HARD_BLOCK", "Capability says order submission unavailable", data["design_spec_summary"].get("capability_order_submission_available") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("blocked_receipt_exists", "HARD_BLOCK", "Blocked receipt exists", data["design_spec_summary"].get("blocked_receipt_exists") is True, True, self.policy.require_blocked_receipt, data["design_spec_summary"], source_refs_count))
        add(_check("blocked_receipt_blocked", "HARD_BLOCK", "Blocked receipt proves blocked state", data["design_spec_summary"].get("blocked_receipt_blocked") is True, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("blocked_receipt_not_executed", "HARD_BLOCK", "Blocked receipt proves not executed", data["design_spec_summary"].get("blocked_receipt_executed") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("blocked_receipt_no_order_sent", "HARD_BLOCK", "Blocked receipt proves no order was sent", data["design_spec_summary"].get("blocked_receipt_order_sent") is False, True, True, data["design_spec_summary"], source_refs_count))
        add(_check("config_live_disabled", "CONFIG", "Config keeps live execution disabled", data["config_summary_redacted"].get("live_execution_enabled") is False, True, True, data["config_summary_redacted"], source_refs_count))
        add(_check("config_hard_block_enabled", "CONFIG", "Config keeps hard block enabled", data["config_summary_redacted"].get("hard_block_enabled") is True, True, self.policy.require_hard_block, data["config_summary_redacted"], source_refs_count))
        add(_check("config_order_submission_disabled", "CONFIG", "Config keeps order submission disabled", data["config_summary_redacted"].get("order_submission_enabled") is False, True, self.policy.require_order_submission_absent, data["config_summary_redacted"], source_refs_count))
        add(_check("config_execution_bridge_disabled", "CONFIG", "Config keeps execution bridge disabled", data["config_summary_redacted"].get("execution_bridge_enabled") is False, True, True, data["config_summary_redacted"], source_refs_count))
        add(_check("adapter_registry_default_simulated", "ADAPTER_REGISTRY", "Adapter registry default is simulated", data["adapter_registry_summary"].get("default_adapter_type") == "SIMULATED", True, True, data["adapter_registry_summary"], source_refs_count))
        add(_check("adapter_registry_reserved_skeleton_only", "ADAPTER_REGISTRY", "Reserved MT5 path returns skeleton only", data["adapter_registry_summary"].get("reserved_returns_skeleton_only") is True, True, True, data["adapter_registry_summary"], source_refs_count))
        add(_check("adapter_registry_no_real_live_adapter", "ADAPTER_REGISTRY", "No real live adapter is active", data["adapter_registry_summary"].get("real_live_adapter_active") is False, True, True, data["adapter_registry_summary"], source_refs_count))
        add(_check("bridge_no_execution_endpoints", "MT5_BRIDGE", "MT5 bridge has no execution endpoints", data["mt5_bridge_endpoint_summary"].get("execution_endpoint_present") is False, True, self.policy.require_no_bridge_order_endpoints, data["mt5_bridge_endpoint_summary"], source_refs_count))
        add(_check("bridge_no_post_execution_handler", "MT5_BRIDGE", "MT5 bridge has no POST execution handler", data["mt5_bridge_endpoint_summary"].get("do_post_execution_handler_present") is False, True, True, data["mt5_bridge_endpoint_summary"], source_refs_count))
        add(_check("code_no_order_submission_call", "CODE_SCAN", "Source has no order submission call", data["code_scan_summary"].get("order_submission_absent") is True, True, self.policy.require_order_submission_absent, data["code_scan_summary"], source_refs_count))
        add(_check("code_no_live_method_names", "CODE_SCAN", "Source has no live order method definitions", data["code_scan_summary"].get("live_methods_absent") is True, True, True, data["code_scan_summary"], source_refs_count))
        add(_check("code_no_docker_side_mt5_import", "CODE_SCAN", "Docker app-side source has no MT5 package import", data["code_scan_summary"].get("docker_side_mt5_import_absent") is True, True, self.policy.require_no_docker_mt5_import, data["code_scan_summary"], source_refs_count))
        add(_check("code_no_ticket_or_deal_generation", "CODE_SCAN", "Source has no ticket/deal generation marker", data["code_scan_summary"].get("mt5_ticket_or_deal_absent") is True, True, True, data["code_scan_summary"], source_refs_count))
        add(_check("dashboard_no_confirm_trade_button", "UI_SCAN", "Dashboard has no unsafe confirmation button", data["ui_scan_summary"].get("unsafe_button_present") is False, True, self.policy.require_ui_safe_wording, data["ui_scan_summary"], source_refs_count))
        add(_check("dashboard_no_execute_trade_button", "UI_SCAN", "Dashboard has no unsafe execution button", data["ui_scan_summary"].get("unsafe_button_present") is False, True, self.policy.require_ui_safe_wording, data["ui_scan_summary"], source_refs_count))
        add(_check("dashboard_no_place_order_button", "UI_SCAN", "Dashboard has no unsafe order placement button", data["ui_scan_summary"].get("unsafe_button_present") is False, True, self.policy.require_ui_safe_wording, data["ui_scan_summary"], source_refs_count))
        add(_check("dashboard_no_buy_sell_button", "UI_SCAN", "Dashboard has no directional trade button", data["ui_scan_summary"].get("unsafe_button_present") is False, True, self.policy.require_ui_safe_wording, data["ui_scan_summary"], source_refs_count))
        add(_check("dashboard_preflight_label_safe", "UI_SCAN", "Dashboard labels preflight as non-executing", data["ui_scan_summary"].get("preflight_safe_label_present") is True and data["ui_scan_summary"].get("live_disabled_label_present") is True, True, self.policy.require_ui_safe_wording, data["ui_scan_summary"], source_refs_count))
        add(_check("journal_path_writable", "JOURNAL", "Preflight journal path is writable", data["journal_summary"].get("journal_parent_writable") is True, True, self.policy.require_journal_writable, data["journal_summary"], source_refs_count))
        add(_check("runtime_jsonl_gitignored", "JOURNAL", "Runtime JSONL files are gitignored", data["journal_summary"].get("runtime_jsonl_gitignored") is True, True, True, data["journal_summary"], source_refs_count))
        add(_check("source_refs_present", "SOURCE_REFS", "Source refs are present", data["source_refs_summary"].get("source_refs_present") is True, True, self.policy.require_source_refs, data["source_refs_summary"], source_refs_count))
        add(_check("artifact_hash_present", "IDEMPOTENCY", "Artifact hash is present", data["idempotency_summary"].get("artifact_hash_present") is True, True, self.policy.require_idempotency, data["idempotency_summary"], source_refs_count))
        add(_check("idempotency_key_present", "IDEMPOTENCY", "Idempotency key is present", data["idempotency_summary"].get("idempotency_key_present") is True, True, self.policy.require_idempotency, data["idempotency_summary"], source_refs_count))
        add(_check("redaction_no_raw_account_id", "REDACTION", "Raw account id is absent", data["redaction_summary"].get("raw_account_id_absent") is True, True, self.policy.require_redaction, data["redaction_summary"], source_refs_count))
        add(_check("redaction_no_credentials", "REDACTION", "Sensitive auth material is absent", data["redaction_summary"].get("credentials_absent") is True, True, self.policy.require_redaction, data["redaction_summary"], source_refs_count))
        add(_check("simulated_contract_simulated_only", "SIMULATED_CONTRACT", "Simulated contract remains simulated only", data["simulated_contract_summary"].get("contract_simulated_only") is True, True, True, data["simulated_contract_summary"], source_refs_count))
        add(_check("simulated_receipt_non_executable", "SIMULATED_CONTRACT", "Simulated receipt remains non-executable", data["simulated_contract_summary"].get("receipt_executable") is False, True, True, data["simulated_contract_summary"], source_refs_count))
        add(_check("simulated_receipt_not_executed", "SIMULATED_CONTRACT", "Simulated receipt remains not executed", data["simulated_contract_summary"].get("receipt_executed") is False, True, True, data["simulated_contract_summary"], source_refs_count))
        add(_check("live_block_journal_record_available", "RUNTIME_ENV", "Live-block journal record exists or warning is surfaced", data["runtime_env_summary"].get("live_block_journal_record_present") is True, True, False, data["runtime_env_summary"], source_refs_count))
        return checks


def _check(
    check_id: str,
    category: str,
    title: str,
    passed: bool,
    expected_pass: bool,
    blocking: bool,
    evidence: dict[str, Any],
    source_refs_count: int,
) -> PreflightCheckResult:
    status = "PASS" if bool(passed) == bool(expected_pass) else ("FAIL" if blocking else "WARN")
    severity = "BLOCKING" if blocking else "WARNING"
    return PreflightCheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        blocking=bool(blocking),
        expected="safe preflight condition",
        observed="safe" if status == "PASS" else "requires attention",
        evidence=evidence,
        failure_message="" if status == "PASS" else f"{check_id}_failed",
        remediation_hint="" if status == "PASS" else "Keep live execution blocked and inspect this preflight evidence.",
        source_refs=["preflight://source-ref"] if source_refs_count else [],
    )
