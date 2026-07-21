from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport
from src.services.trading.execution.preflight.models import (
    LiveExecutionPreflightReadinessReport,
    LiveExecutionPreflightSummary,
    PreflightJournalRecord,
    now_utc_iso,
)
from src.services.trading.execution.preflight.policy import LiveExecutionPreflightPolicy
from src.services.trading.execution.preflight.runner import LiveExecutionPreflightHarness
from src.services.trading.execution.preflight.store import LiveExecutionPreflightReportStore
from src.services.trading.execution.preflight.validator import LiveExecutionPreflightValidator


@dataclass
class LiveExecutionPreflightServiceResult:
    report: LiveExecutionPreflightReadinessReport
    journal_record: PreflightJournalRecord | None
    summary: LiveExecutionPreflightSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveExecutionPreflightService:
    def __init__(
        self,
        policy: LiveExecutionPreflightPolicy | None = None,
        harness: LiveExecutionPreflightHarness | None = None,
        store: LiveExecutionPreflightReportStore | None = None,
        validator: LiveExecutionPreflightValidator | None = None,
    ):
        self.policy = policy or LiveExecutionPreflightPolicy.from_config()
        self.validator = validator or LiveExecutionPreflightValidator(self.policy)
        self.harness = harness or LiveExecutionPreflightHarness(self.policy, validator=self.validator)
        self.store = store or LiveExecutionPreflightReportStore(
            path=self.policy.journal_path,
            max_read_records=self.policy.max_read_records,
        )

    def run(
        self,
        design_report,
        capability_report: LiveExecutionCapabilityReport,
        blocked_receipt: LiveExecutionBlockedReceipt,
        simulated_contract=None,
        simulated_receipt=None,
        live_block_journal_record=None,
    ) -> LiveExecutionPreflightServiceResult:
        started = perf_counter()
        report = self.harness.build(
            design_report,
            capability_report,
            blocked_receipt,
            simulated_contract=simulated_contract,
            simulated_receipt=simulated_receipt,
            live_block_journal_record=live_block_journal_record,
        )
        warning_parts: list[str] = []
        report_validation = self.validator.validate_report(report)
        if not report_validation.passed:
            report.blockers = list(dict.fromkeys(list(report.blockers) + report_validation.issues))
            report.preflight_status = "FAIL"
            report.all_blocking_checks_passed = False
            report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("preflight_report_validation_failed:" + ",".join(report_validation.issues))
        record = None
        append_latency_ms = 0.0
        if self.policy.journal_enabled:
            record = self._build_record(report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency_ms = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"preflight_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("preflight_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("preflight_journal_disabled")
        summary = self.store.summarize()
        timings = dict(self.harness.last_timings_ms)
        timings["preflight_journal_append_latency_ms"] = append_latency_ms
        timings["service_total_latency_ms"] = (perf_counter() - started) * 1000
        return LiveExecutionPreflightServiceResult(report, record, summary, ";".join(warning_parts), timings)

    def _build_record(self, report: LiveExecutionPreflightReadinessReport) -> PreflightJournalRecord:
        created_at = now_utc_iso()
        record = PreflightJournalRecord(
            journal_record_id=_record_id(report.report_id, created_at),
            created_at=created_at,
            report_id=report.report_id,
            preflight_status=report.preflight_status,
            live_execution_allowed=False,
            all_blocking_checks_passed=report.all_blocking_checks_passed,
            total_checks=report.total_checks,
            passed_checks=report.passed_checks,
            failed_checks=report.failed_checks,
            warning_checks=report.warning_checks,
            blocking_failures=report.blocking_failures,
            critical_failures=report.critical_failures,
            hard_live_block_required=True,
            source_design_report_id=report.source_design_report_id,
            source_capability_report_id=report.source_capability_report_id,
            source_blocked_receipt_id=report.source_blocked_receipt_id,
            source_refs=list(report.source_refs),
            metadata_redacted={
                "preflight_only": True,
                "live_execution_allowed": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_execution_preflight_journal_{digest}"
