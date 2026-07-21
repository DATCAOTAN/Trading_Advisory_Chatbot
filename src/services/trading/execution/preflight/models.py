from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


PREFLIGHT_CHECK_CATEGORIES = {
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
}
PREFLIGHT_CHECK_STATUSES = {"PASS", "FAIL", "WARN", "SKIPPED", "UNKNOWN"}
PREFLIGHT_SEVERITIES = {"INFO", "WARNING", "BLOCKING", "CRITICAL"}


@dataclass
class PreflightEvidenceSnapshot:
    evidence_id: str
    created_at: str
    config_summary_redacted: Dict[str, Any] = field(default_factory=dict)
    adapter_registry_summary: Dict[str, Any] = field(default_factory=dict)
    mt5_bridge_endpoint_summary: Dict[str, Any] = field(default_factory=dict)
    code_scan_summary: Dict[str, Any] = field(default_factory=dict)
    ui_scan_summary: Dict[str, Any] = field(default_factory=dict)
    journal_summary: Dict[str, Any] = field(default_factory=dict)
    source_refs_summary: Dict[str, Any] = field(default_factory=dict)
    idempotency_summary: Dict[str, Any] = field(default_factory=dict)
    redaction_summary: Dict[str, Any] = field(default_factory=dict)
    design_spec_summary: Dict[str, Any] = field(default_factory=dict)
    simulated_contract_summary: Dict[str, Any] = field(default_factory=dict)
    runtime_env_summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "created_at": self.created_at,
            "config_summary_redacted": dict(self.config_summary_redacted),
            "adapter_registry_summary": dict(self.adapter_registry_summary),
            "mt5_bridge_endpoint_summary": dict(self.mt5_bridge_endpoint_summary),
            "code_scan_summary": dict(self.code_scan_summary),
            "ui_scan_summary": dict(self.ui_scan_summary),
            "journal_summary": dict(self.journal_summary),
            "source_refs_summary": dict(self.source_refs_summary),
            "idempotency_summary": dict(self.idempotency_summary),
            "redaction_summary": dict(self.redaction_summary),
            "design_spec_summary": dict(self.design_spec_summary),
            "simulated_contract_summary": dict(self.simulated_contract_summary),
            "runtime_env_summary": dict(self.runtime_env_summary),
            "warnings": _dedupe(self.warnings),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class PreflightCheckResult:
    check_id: str
    category: str
    title: str
    status: str
    severity: str
    blocking: bool
    expected: str
    observed: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    failure_message: str = ""
    remediation_hint: str = ""
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category if self.category in PREFLIGHT_CHECK_CATEGORIES else "UNKNOWN",
            "title": self.title,
            "status": self.status if self.status in PREFLIGHT_CHECK_STATUSES else "UNKNOWN",
            "severity": self.severity if self.severity in PREFLIGHT_SEVERITIES else "WARNING",
            "blocking": bool(self.blocking),
            "expected": self.expected,
            "observed": self.observed,
            "evidence": dict(self.evidence),
            "failure_message": self.failure_message,
            "remediation_hint": self.remediation_hint,
            "source_refs": _dedupe(self.source_refs),
        }


@dataclass
class LiveExecutionPreflightReadinessReport:
    report_id: str
    created_at: str
    preflight_status: str = "UNKNOWN"
    live_execution_allowed: bool = False
    hard_live_block_required: bool = True
    all_blocking_checks_passed: bool = False
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    skipped_checks: int = 0
    blocking_failures: int = 0
    critical_failures: int = 0
    source_design_report_id: str = ""
    source_capability_report_id: str = ""
    source_blocked_receipt_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    evidence_snapshot: PreflightEvidenceSnapshot | None = None
    check_results: List[PreflightCheckResult] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    readiness_score: float = 0.0
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "preflight_status": self.preflight_status if self.preflight_status in PREFLIGHT_CHECK_STATUSES else "UNKNOWN",
            "live_execution_allowed": False,
            "hard_live_block_required": True,
            "all_blocking_checks_passed": bool(self.all_blocking_checks_passed),
            "total_checks": int(self.total_checks),
            "passed_checks": int(self.passed_checks),
            "failed_checks": int(self.failed_checks),
            "warning_checks": int(self.warning_checks),
            "skipped_checks": int(self.skipped_checks),
            "blocking_failures": int(self.blocking_failures),
            "critical_failures": int(self.critical_failures),
            "source_design_report_id": self.source_design_report_id,
            "source_capability_report_id": self.source_capability_report_id,
            "source_blocked_receipt_id": self.source_blocked_receipt_id,
            "source_refs": _dedupe(self.source_refs),
            "evidence_snapshot": self.evidence_snapshot.as_dict() if self.evidence_snapshot else {},
            "check_results": [item.as_dict() for item in self.check_results],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "readiness_score": _clamp(self.readiness_score),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class PreflightJournalRecord:
    journal_record_id: str
    created_at: str
    report_id: str
    preflight_status: str
    live_execution_allowed: bool
    all_blocking_checks_passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_checks: int
    blocking_failures: int
    critical_failures: int
    hard_live_block_required: bool
    source_design_report_id: str
    source_capability_report_id: str
    source_blocked_receipt_id: str
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "report_id": self.report_id,
            "preflight_status": self.preflight_status if self.preflight_status in PREFLIGHT_CHECK_STATUSES else "UNKNOWN",
            "live_execution_allowed": False,
            "all_blocking_checks_passed": bool(self.all_blocking_checks_passed),
            "total_checks": int(self.total_checks),
            "passed_checks": int(self.passed_checks),
            "failed_checks": int(self.failed_checks),
            "warning_checks": int(self.warning_checks),
            "blocking_failures": int(self.blocking_failures),
            "critical_failures": int(self.critical_failures),
            "hard_live_block_required": True,
            "source_design_report_id": self.source_design_report_id,
            "source_capability_report_id": self.source_capability_report_id,
            "source_blocked_receipt_id": self.source_blocked_receipt_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveExecutionPreflightSummary:
    total_records: int = 0
    latest_record_at: str = ""
    latest_report_id: str = ""
    latest_preflight_status: str = ""
    total_pass: int = 0
    total_fail: int = 0
    latest_blocking_failures: int = 0
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "latest_record_at": self.latest_record_at,
            "latest_report_id": self.latest_report_id,
            "latest_preflight_status": self.latest_preflight_status,
            "total_pass": int(self.total_pass),
            "total_fail": int(self.total_fail),
            "latest_blocking_failures": int(self.latest_blocking_failures),
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
