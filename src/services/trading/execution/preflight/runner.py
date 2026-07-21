from __future__ import annotations

import json
from time import perf_counter

from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport
from src.services.trading.execution.preflight.checks import PreflightCheckRunner
from src.services.trading.execution.preflight.evidence import PreflightEvidenceCollector
from src.services.trading.execution.preflight.models import LiveExecutionPreflightReadinessReport, now_utc_iso
from src.services.trading.execution.preflight.policy import LiveExecutionPreflightPolicy
from src.services.trading.execution.preflight.validator import LiveExecutionPreflightValidator


class LiveExecutionPreflightHarness:
    def __init__(
        self,
        policy: LiveExecutionPreflightPolicy | None = None,
        evidence_collector: PreflightEvidenceCollector | None = None,
        check_runner: PreflightCheckRunner | None = None,
        validator: LiveExecutionPreflightValidator | None = None,
    ):
        self.policy = policy or LiveExecutionPreflightPolicy.from_config()
        self.evidence_collector = evidence_collector or PreflightEvidenceCollector(self.policy)
        self.check_runner = check_runner or PreflightCheckRunner(self.policy)
        self.validator = validator or LiveExecutionPreflightValidator(self.policy)
        self.last_timings_ms: dict[str, float] = {}

    def build(
        self,
        design_report,
        capability_report: LiveExecutionCapabilityReport | None,
        blocked_receipt: LiveExecutionBlockedReceipt | None,
        simulated_contract=None,
        simulated_receipt=None,
        live_block_journal_record=None,
    ) -> LiveExecutionPreflightReadinessReport:
        evidence_started = perf_counter()
        evidence = self.evidence_collector.collect(
            design_report,
            capability_report,
            blocked_receipt,
            simulated_contract,
            simulated_receipt,
            live_block_journal_record,
        )
        self.last_timings_ms["evidence_collection_latency_ms"] = (perf_counter() - evidence_started) * 1000

        runner_started = perf_counter()
        check_results = self.check_runner.run(evidence)
        self.last_timings_ms["check_runner_latency_ms"] = (perf_counter() - runner_started) * 1000

        passed = sum(1 for item in check_results if item.status == "PASS")
        failed = sum(1 for item in check_results if item.status == "FAIL")
        warning = sum(1 for item in check_results if item.status == "WARN")
        skipped = sum(1 for item in check_results if item.status == "SKIPPED")
        blocking_failures = sum(1 for item in check_results if item.status == "FAIL" and item.blocking)
        critical_failures = sum(1 for item in check_results if item.status == "FAIL" and item.severity == "CRITICAL")
        total = len(check_results)
        status = "PASS" if failed == 0 else "FAIL"
        source_refs = _dedupe(
            list(getattr(design_report, "source_refs", []) or [])
            + list(getattr(blocked_receipt, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
        )
        report = LiveExecutionPreflightReadinessReport(
            report_id=f"live_execution_preflight_report_{_short_hash(now_utc_iso())}",
            created_at=now_utc_iso(),
            preflight_status=status,
            live_execution_allowed=False,
            hard_live_block_required=True,
            all_blocking_checks_passed=blocking_failures == 0,
            total_checks=total,
            passed_checks=passed,
            failed_checks=failed,
            warning_checks=warning,
            skipped_checks=skipped,
            blocking_failures=blocking_failures,
            critical_failures=critical_failures,
            source_design_report_id=getattr(design_report, "report_id", ""),
            source_capability_report_id=getattr(capability_report, "report_id", ""),
            source_blocked_receipt_id=getattr(blocked_receipt, "receipt_id", ""),
            source_refs=source_refs,
            evidence_snapshot=evidence,
            check_results=check_results,
            blockers=[item.check_id for item in check_results if item.status == "FAIL" and item.blocking],
            warnings=list(evidence.warnings) + [item.check_id for item in check_results if item.status == "WARN"],
            readiness_score=(passed + warning * 0.5) / total if total else 0.0,
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_report(report)
        if not validation.passed:
            report.blockers = _dedupe(list(report.blockers) + validation.issues)
            report.preflight_status = "FAIL"
            report.failed_checks = max(report.failed_checks, 1)
            report.blocking_failures = max(report.blocking_failures, 1)
            report.all_blocking_checks_passed = False
            report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        self.last_timings_ms["report_build_latency_ms"] = sum(self.last_timings_ms.values())
        return report


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _dedupe(items):
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
