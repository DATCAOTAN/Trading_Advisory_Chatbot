from __future__ import annotations

import hashlib
import json
from time import perf_counter

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_design.approval_models import LiveExecutionApprovalRequirement
from src.services.trading.execution.live_design.audit_models import LiveExecutionAuditRequirement
from src.services.trading.execution.live_design.common import clamp, dedupe, now_utc_iso
from src.services.trading.execution.live_design.failure_models import LiveExecutionFailureMode
from src.services.trading.execution.live_design.policy import LiveExecutionDesignPolicy
from src.services.trading.execution.live_design.preflight_models import LiveExecutionPreflightCheck
from src.services.trading.execution.live_design.readiness_models import LiveExecutionReadinessSpecReport
from src.services.trading.execution.live_design.threat_models import LiveExecutionThreat
from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport


class LiveExecutionThreatModelBuilder:
    def build(
        self,
        capability_report: LiveExecutionCapabilityReport,
        blocked_receipt: LiveExecutionBlockedReceipt,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        draft=None,
    ) -> list[LiveExecutionThreat]:
        refs = _refs(capability_report, blocked_receipt, contract, simulated_receipt, draft)
        rows = [
            ("threat_stale_market_data", "MARKET_DATA", "CRITICAL", "Stale market data", "Feature or tick data may be stale before a future adapter review.", "provider timestamp outside freshness policy", "future review could use stale context", "freshness gates and manual timestamp check", "data quality and provider health checks", "block future continuation until fresh data exists", "medium"),
            ("threat_wrong_broker_symbol_mapping", "SYMBOL_MAPPING", "CRITICAL", "Wrong broker symbol mapping", "Logical symbol may map to the wrong broker instrument.", "symbol map drift or suffix mismatch", "future review could reference the wrong instrument", "manual broker symbol verification", "compare logical and broker symbol in all artifacts", "block future continuation until symbol is verified", "medium"),
            ("threat_disconnected_terminal", "ACCOUNT_STATE", "HIGH", "Disconnected MT5 terminal", "Terminal may be disconnected during future readiness review.", "bridge health unavailable or terminal disconnected", "future adapter cannot rely on terminal state", "terminal health check remains required", "bridge health status", "keep live execution blocked", "low"),
            ("threat_wrong_terminal_account", "ACCOUNT_STATE", "CRITICAL", "Wrong terminal account selected", "The visible terminal account may not be the intended account.", "manual account check skipped", "future adapter could target an unintended account", "manual account verification outside stored payload", "redacted account hash and operator checklist", "block without explicit verification", "medium"),
            ("threat_duplicate_attempt", "DUPLICATION", "HIGH", "Duplicated execution attempt", "Repeated user actions may replay the same artifact.", "same artifact hash appears again", "duplicate future request could slip through", "idempotency key and duplicate journal scan", "journal lookup by idempotency key", "block duplicate context", "low"),
            ("threat_idempotency_collision", "IDEMPOTENCY", "HIGH", "Idempotency collision", "A key collision could merge unrelated contexts.", "unexpected same idempotency key for different artifact hash", "audit trail becomes ambiguous", "hash includes source artifact identity", "compare artifact hash and idempotency key", "block on mismatch", "low"),
            ("threat_network_timeout", "NETWORK", "HIGH", "Network timeout during broker interaction", "Future broker interaction may timeout with unknown result.", "provider call timeout", "state could be unknown", "no live call in this sprint; future retry policy required", "timeout and response status audit", "require unknown-state recovery plan", "medium"),
            ("threat_unknown_broker_response", "BROKER", "CRITICAL", "Partial or unknown broker response", "Future provider may return an ambiguous status.", "missing success/failure confirmation", "state cannot be trusted", "response classification and manual reconciliation", "provider response audit", "block until reconciliation", "medium"),
            ("threat_spread_spike", "MARKET_DATA", "HIGH", "Spread spike", "Spread may expand after review context was produced.", "spread state changes to wide", "future action could be unsafe", "latest spread gate", "feature snapshot spread state", "wait for stable spread", "medium"),
            ("threat_calendar_event_risk", "MARKET_DATA", "HIGH", "Calendar event risk", "High-impact event window may begin after review.", "calendar risk not clear", "future review context can become stale", "calendar risk gate", "calendar context risk state", "block or wait around event windows", "medium"),
            ("threat_parameter_construction_bug", "ORDER_CONSTRUCTION", "CRITICAL", "Order parameter construction bug", "Future parameter construction could be wrong if introduced.", "future code creates executable parameters", "future request may become unsafe", "separate proposal spec and validator before any live sprint", "forbidden marker scans", "hard block remains required", "high"),
            ("threat_missing_hard_block", "SYSTEM_CONFIG", "CRITICAL", "Missing hard block", "Hard block could be disabled by configuration drift.", "hard block flag false", "live path might appear reachable", "config invariant and CI scan", "capability report flags", "invalid report and block", "low"),
            ("threat_accidental_live_adapter_enablement", "SYSTEM_CONFIG", "CRITICAL", "Accidental live adapter enablement", "Reserved adapter may be enabled without approval.", "registry returns non-skeleton live adapter", "future path bypasses design review", "registry hard-block test", "adapter type audit", "fail startup or validation", "low"),
            ("threat_audit_write_failure", "AUDIT", "HIGH", "Audit log write failure", "A future audit record may fail to append.", "journal path unavailable", "traceability lost", "append-only journal validation", "store warnings and write result", "block if audit cannot write", "medium"),
            ("threat_account_data_leakage", "COMPLIANCE", "CRITICAL", "Raw account data leakage", "Sensitive account data may enter logs or journals.", "unredacted account field appears", "privacy and compliance breach", "redaction policy and forbidden marker scan", "payload validator", "reject payload", "low"),
            ("threat_docker_mt5_import_misuse", "SYSTEM_CONFIG", "HIGH", "Docker-side MT5 import misuse", "App container may import a local terminal package by mistake.", "MetaTrader marker in app source", "Docker environment becomes coupled to terminal", "source scan", "CI scan for imports", "block deployment", "low"),
            ("threat_bridge_endpoint_drift", "SYSTEM_CONFIG", "CRITICAL", "Unexpected live endpoint added to bridge", "Market-data bridge could drift into execution bridge.", "new POST or execution endpoint appears", "boundary violation", "endpoint source scan", "bridge endpoint scan", "block release", "low"),
            ("threat_ui_wording_confusion", "HUMAN_CONFIRMATION", "HIGH", "UI wording confusion", "Users may confuse design review with live execution permission.", "button or label implies execution", "human confirmation may be misunderstood", "UI wording review", "dashboard text scan", "rename or remove confusing UI", "medium"),
            ("threat_expired_artifact_replay", "DUPLICATION", "HIGH", "Replay of expired artifact", "Old artifacts may be reused after market context changes.", "artifact timestamp outside TTL", "future review based on stale context", "TTL validation", "artifact created_at and journal timestamps", "block expired context", "low"),
            ("threat_unreviewed_context", "HUMAN_CONFIRMATION", "CRITICAL", "Unreviewed proposal context", "A context could skip human review layers.", "missing review or proposal intent id", "future process lacks accountability", "source id chain required", "source id validation", "block incomplete chain", "medium"),
        ]
        return [
            LiveExecutionThreat(
                threat_id=row[0],
                category=row[1],
                severity=row[2],
                title=row[3],
                description=row[4],
                trigger_condition=row[5],
                impact=row[6],
                required_control=row[7],
                detection_method=row[8],
                mitigation=row[9],
                residual_risk=row[10],
                blocking=True,
                source_refs=refs,
            )
            for row in rows
        ]


class LiveExecutionPreflightChecklistBuilder:
    def build(self, capability_report: LiveExecutionCapabilityReport, blocked_receipt: LiveExecutionBlockedReceipt) -> list[LiveExecutionPreflightCheck]:
        refs = _refs(capability_report, blocked_receipt)
        rows = [
            ("preflight_hard_block_enabled", "Hard live block enabled", "SYSTEM_CONFIG", "true", "true"),
            ("preflight_live_disabled", "Live execution disabled", "SYSTEM_CONFIG", "false", "false"),
            ("preflight_order_submission_disabled", "Order submission disabled", "SYSTEM_CONFIG", "false", "false"),
            ("preflight_execution_bridge_disabled", "Execution bridge disabled", "SYSTEM_CONFIG", "false", "false"),
            ("preflight_mt5_adapter_not_implemented", "MT5 adapter not implemented", "SYSTEM_CONFIG", "false", "false"),
            ("preflight_no_bridge_execution_endpoint", "No bridge execution endpoint", "SYSTEM_CONFIG", "market_data_only", "market_data_only"),
            ("preflight_source_refs_present", "Source refs present", "AUDIT", "present", "present"),
            ("preflight_artifact_ttl_valid", "Artifact TTL valid", "DUPLICATION", "approval_required", "fresh"),
            ("preflight_idempotency_available", "Idempotency available", "IDEMPOTENCY", "present", "present"),
            ("preflight_audit_journal_writable", "Audit journal writable", "AUDIT", "required", "writable"),
            ("preflight_account_redacted", "Raw account id redacted", "COMPLIANCE", "redacted", "redacted"),
            ("preflight_terminal_account_manual", "MT5 terminal account manually verified placeholder", "ACCOUNT_STATE", "approval_required", "verified"),
            ("preflight_symbol_mapping_manual", "Broker symbol mapping manually verified placeholder", "SYMBOL_MAPPING", "approval_required", "verified"),
            ("preflight_calendar_checked", "Calendar risk checked", "MARKET_DATA", "required", "clear_or_acknowledged"),
            ("preflight_spread_data_quality_checked", "Spread and data quality checked", "MARKET_DATA", "required", "clean"),
            ("preflight_human_boundary_present", "Human confirmation boundary present", "HUMAN_CONFIRMATION", "present", "present"),
            ("preflight_draft_non_executable", "Proposal draft non-executable", "SYSTEM_CONFIG", "true", "true"),
            ("preflight_simulated_receipt_exists", "Simulated adapter receipt exists", "AUDIT", "present", "present"),
            ("preflight_hard_block_receipt_exists", "Hard-block receipt exists", "AUDIT", "present", "present"),
            ("preflight_no_docker_mt5_import", "Docker app has no MetaTrader import", "SYSTEM_CONFIG", "absent", "absent"),
        ]
        return [
            LiveExecutionPreflightCheck(
                check_id=row[0],
                title=row[1],
                category=row[2],
                required=True,
                current_status=row[3],
                expected_status=row[4],
                blocking=True,
                evidence_required=f"machine_check:{row[0]}",
                failure_message=f"{row[1]} is required before any future live design review can continue.",
                source_refs=refs,
            )
            for row in rows
        ]


class LiveExecutionApprovalMatrixBuilder:
    def build(self, capability_report: LiveExecutionCapabilityReport, blocked_receipt: LiveExecutionBlockedReceipt) -> list[LiveExecutionApprovalRequirement]:
        refs = _refs(capability_report, blocked_receipt)
        rows = [
            ("approval_future_live_sprint", "Explicit user approval for future live execution sprint", "USER"),
            ("approval_code_review", "Explicit separate code review", "ENGINEERING"),
            ("approval_account_verification", "Explicit broker/account verification", "OPERATOR"),
            ("approval_symbol_mapping", "Explicit symbol mapping verification", "OPERATOR"),
            ("approval_risk_policy", "Explicit risk limit policy defined", "RISK_OWNER"),
            ("approval_recovery_plan", "Explicit rollback plan defined", "ENGINEERING"),
            ("approval_audit_retention", "Explicit audit retention defined", "COMPLIANCE"),
            ("approval_simulated_parity", "Explicit dry-run to simulated parity check", "QA"),
            ("approval_kill_switch_test", "Explicit kill switch test", "QA"),
            ("approval_idempotency_test", "Explicit duplicate/idempotency test", "QA"),
            ("approval_ui_wording_review", "Explicit UI wording review", "PRODUCT"),
            ("approval_no_autonomous_default", "Explicit no-autonomous-default rule", "RISK_OWNER"),
        ]
        return [
            LiveExecutionApprovalRequirement(
                requirement_id=row[0],
                title=row[1],
                required=True,
                satisfied=False,
                blocking=True,
                approver_type=row[2],
                evidence_required=f"signed_artifact:{row[0]}",
                expiry_seconds=300,
                source_refs=refs,
            )
            for row in rows
        ]


class LiveExecutionFailureModeCatalogBuilder:
    def build(self, capability_report: LiveExecutionCapabilityReport, blocked_receipt: LiveExecutionBlockedReceipt) -> list[LiveExecutionFailureMode]:
        refs = _refs(capability_report, blocked_receipt)
        rows = [
            ("failure_data_provider_unavailable", "MARKET_DATA", "HIGH", "Data provider unavailable"),
            ("failure_stale_feature_snapshot", "MARKET_DATA", "HIGH", "Stale feature snapshot"),
            ("failure_calendar_timeout", "NETWORK", "MEDIUM", "Calendar provider timeout"),
            ("failure_market_regime_unknown", "MARKET_DATA", "MEDIUM", "Market regime unknown"),
            ("failure_proposal_context_expired", "DUPLICATION", "HIGH", "Proposal context expired"),
            ("failure_duplicate_confirmation", "DUPLICATION", "HIGH", "Duplicate confirmation"),
            ("failure_journal_write", "AUDIT", "HIGH", "Journal write failure"),
            ("failure_simulated_receipt_mismatch", "AUDIT", "HIGH", "Simulated receipt mismatch"),
            ("failure_hard_block_disabled", "SYSTEM_CONFIG", "CRITICAL", "Hard block disabled unexpectedly"),
            ("failure_ui_trigger_confusion", "HUMAN_CONFIRMATION", "HIGH", "UI trigger confusion"),
            ("failure_account_redaction", "COMPLIANCE", "CRITICAL", "Account redaction failure"),
            ("failure_bridge_endpoint_drift", "SYSTEM_CONFIG", "CRITICAL", "Bridge endpoint drift"),
            ("failure_docker_environment_drift", "SYSTEM_CONFIG", "HIGH", "Docker environment drift"),
            ("failure_registry_wrong_adapter", "SYSTEM_CONFIG", "CRITICAL", "Registry returns wrong adapter mode"),
            ("failure_unexpected_order_method", "SYSTEM_CONFIG", "CRITICAL", "Unexpected order method appears"),
        ]
        return [
            LiveExecutionFailureMode(
                failure_mode_id=row[0],
                category=row[1],
                severity=row[2],
                title=row[3],
                description=f"{row[3]} must be detectable before any future live execution design review proceeds.",
                detection_method=f"machine_check:{row[0]}",
                required_response="block_and_record_audit_event",
                rollback_or_recovery="keep_live_execution_disabled_and_require_manual_review",
                audit_requirement=f"audit_{row[0]}",
                blocking=True,
                source_refs=refs,
            )
            for row in rows
        ]


class LiveExecutionAuditSpecBuilder:
    def build(self, capability_report: LiveExecutionCapabilityReport, blocked_receipt: LiveExecutionBlockedReceipt) -> list[LiveExecutionAuditRequirement]:
        refs = _refs(capability_report, blocked_receipt)
        rows = [
            ("audit_capability_report_created", "Capability report created", "LIVE_CAPABILITY_REPORT"),
            ("audit_blocked_receipt_created", "Blocked receipt created", "LIVE_BLOCKED_RECEIPT"),
            ("audit_block_journal_appended", "Block journal appended", "LIVE_BLOCK_JOURNAL"),
            ("audit_threat_model_report_appended", "Threat model report appended", "LIVE_DESIGN_REPORT"),
            ("audit_source_artifact_ids", "Source artifact ids preserved", "SOURCE_CHAIN"),
            ("audit_source_refs", "Source refs preserved", "SOURCE_REFS"),
            ("audit_idempotency_key", "Idempotency key preserved", "IDEMPOTENCY"),
            ("audit_account_redacted", "Account metadata redacted", "REDACTION"),
            ("audit_forbidden_marker_scan", "Forbidden marker scan recorded", "VALIDATION"),
            ("audit_bridge_endpoint_scan", "Bridge endpoint scan recorded", "BOUNDARY_SCAN"),
            ("audit_registry_adapter_type", "Registry adapter type recorded", "REGISTRY"),
            ("audit_ui_button_scan", "UI button scan recorded", "UI_SCAN"),
            ("audit_runtime_config_redacted", "Runtime config snapshot redacted", "CONFIG"),
            ("audit_validation_result", "Validation result recorded", "VALIDATION"),
            ("audit_live_execution_false", "Live execution remains false recorded", "SAFETY_INVARIANT"),
        ]
        return [
            LiveExecutionAuditRequirement(
                audit_id=row[0],
                title=row[1],
                required=True,
                event_type=row[2],
                fields_required=["created_at", "source_ids", "source_refs", "redacted_metadata", "validation_status"],
                retention_policy="append_only_jsonl_runtime_gitignored",
                redaction_required=True,
                blocking=True,
                source_refs=refs,
            )
            for row in rows
        ]


class LiveExecutionReadinessSpecReportBuilder:
    def __init__(self, policy: LiveExecutionDesignPolicy | None = None):
        self.policy = policy or LiveExecutionDesignPolicy.from_config()
        self.last_timings_ms: dict[str, float] = {}

    def build(
        self,
        capability_report: LiveExecutionCapabilityReport,
        blocked_receipt: LiveExecutionBlockedReceipt,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        draft=None,
    ) -> LiveExecutionReadinessSpecReport:
        timings: dict[str, float] = {}
        start = perf_counter()
        threats = LiveExecutionThreatModelBuilder().build(capability_report, blocked_receipt, contract, simulated_receipt, draft)
        timings["threat_model_build_latency_ms"] = (perf_counter() - start) * 1000
        start = perf_counter()
        checks = LiveExecutionPreflightChecklistBuilder().build(capability_report, blocked_receipt)
        timings["preflight_checklist_build_latency_ms"] = (perf_counter() - start) * 1000
        start = perf_counter()
        approvals = LiveExecutionApprovalMatrixBuilder().build(capability_report, blocked_receipt)
        timings["approval_matrix_build_latency_ms"] = (perf_counter() - start) * 1000
        start = perf_counter()
        failures = LiveExecutionFailureModeCatalogBuilder().build(capability_report, blocked_receipt)
        timings["failure_catalog_build_latency_ms"] = (perf_counter() - start) * 1000
        start = perf_counter()
        audits = LiveExecutionAuditSpecBuilder().build(capability_report, blocked_receipt)
        timings["audit_spec_build_latency_ms"] = (perf_counter() - start) * 1000
        refs = _refs(capability_report, blocked_receipt, contract, simulated_receipt, draft)
        blockers, warnings = _policy_findings(self.policy, capability_report, blocked_receipt, threats, checks, approvals, failures, audits)
        status = "DESIGN_ONLY"
        if blockers:
            status = "INVALID" if any(item.startswith("missing_") or item.endswith("_true") for item in blockers) else "INCOMPLETE"
        elif approvals:
            status = "APPROVAL_REQUIRED"
        score = _design_score(self.policy, threats, checks, approvals, failures, audits)
        created_at = now_utc_iso()
        report = LiveExecutionReadinessSpecReport(
            report_id=_stable_id("live_execution_design_report", created_at, getattr(capability_report, "report_id", ""), getattr(blocked_receipt, "receipt_id", "")),
            created_at=created_at,
            design_status=status,
            live_execution_allowed=False,
            hard_live_block_required=True,
            source_capability_report_id=getattr(capability_report, "report_id", ""),
            source_blocked_receipt_id=getattr(blocked_receipt, "receipt_id", ""),
            source_contract_id=getattr(blocked_receipt, "source_contract_id", "") or getattr(contract, "contract_id", ""),
            source_refs=refs,
            threats=threats,
            preflight_checks=checks,
            approval_requirements=approvals,
            failure_modes=failures,
            audit_requirements=audits,
            blockers=blockers,
            warnings=warnings,
            readiness_score=score,
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        self.last_timings_ms = timings
        return report


def _refs(*items) -> list[str]:
    refs: list[str] = []
    for item in items:
        refs.extend(list(getattr(item, "source_refs", []) or []))
    return dedupe(refs)


def _policy_findings(policy, report, receipt, threats, checks, approvals, failures, audits) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = ["design_completeness_only_not_execution_readiness"]
    if policy.require_capability_report and not getattr(report, "report_id", ""):
        blockers.append("missing_capability_report")
    if policy.require_blocked_receipt and not getattr(receipt, "receipt_id", ""):
        blockers.append("missing_blocked_receipt")
    if policy.require_hard_block and not getattr(report, "hard_live_block_enabled", False):
        blockers.append("missing_hard_live_block")
    if getattr(report, "live_execution_supported", True):
        blockers.append("live_execution_supported_true")
    if getattr(report, "live_execution_enabled", True):
        blockers.append("live_execution_enabled_true")
    if getattr(report, "mt5_order_send_available", True):
        blockers.append("mt5_order_submission_available_true")
    if not getattr(receipt, "blocked", False):
        blockers.append("blocked_receipt_not_blocked")
    if getattr(receipt, "executed", True):
        blockers.append("blocked_receipt_executed_true")
    if getattr(receipt, "order_sent", True):
        blockers.append("blocked_receipt_order_sent_true")
    critical_count = sum(1 for item in threats if item.severity == "CRITICAL")
    if critical_count < policy.min_critical_threats:
        blockers.append("critical_threat_count_below_minimum")
    if len(checks) < policy.min_preflight_checks:
        blockers.append("preflight_check_count_below_minimum")
    if len(approvals) < policy.min_approval_requirements:
        blockers.append("approval_requirement_count_below_minimum")
    if len(failures) < policy.min_failure_modes:
        blockers.append("failure_mode_count_below_minimum")
    if len(audits) < policy.min_audit_requirements:
        blockers.append("audit_requirement_count_below_minimum")
    return dedupe(blockers), dedupe(warnings)


def _design_score(policy, threats, checks, approvals, failures, audits) -> float:
    parts = [
        min(1.0, len([item for item in threats if item.severity == "CRITICAL"]) / max(policy.min_critical_threats, 1)),
        min(1.0, len(checks) / max(policy.min_preflight_checks, 1)),
        min(1.0, len(approvals) / max(policy.min_approval_requirements, 1)),
        min(1.0, len(failures) / max(policy.min_failure_modes, 1)),
        min(1.0, len(audits) / max(policy.min_audit_requirements, 1)),
    ]
    return clamp(sum(parts) / len(parts))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
