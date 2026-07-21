from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.live_design.builder import LiveExecutionReadinessSpecReportBuilder
from src.services.trading.execution.live_design.common import now_utc_iso
from src.services.trading.execution.live_design.policy import LiveExecutionDesignPolicy
from src.services.trading.execution.live_design.readiness_models import (
    LiveExecutionDesignReportRecord,
    LiveExecutionDesignReportSummary,
    LiveExecutionReadinessSpecReport,
)
from src.services.trading.execution.live_design.store import LiveExecutionDesignReportStore
from src.services.trading.execution.live_design.validator import LiveExecutionDesignSpecValidator
from src.services.trading.execution.mt5_skeleton_models import LiveExecutionBlockedReceipt, LiveExecutionCapabilityReport


@dataclass
class LiveExecutionDesignSpecResult:
    report: LiveExecutionReadinessSpecReport
    journal_record: LiveExecutionDesignReportRecord | None
    summary: LiveExecutionDesignReportSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveExecutionDesignSpecService:
    def __init__(
        self,
        policy: LiveExecutionDesignPolicy | None = None,
        builder: LiveExecutionReadinessSpecReportBuilder | None = None,
        store: LiveExecutionDesignReportStore | None = None,
        validator: LiveExecutionDesignSpecValidator | None = None,
    ):
        self.policy = policy or LiveExecutionDesignPolicy.from_config()
        self.builder = builder or LiveExecutionReadinessSpecReportBuilder(self.policy)
        self.store = store or LiveExecutionDesignReportStore(
            path=self.policy.journal_path,
            max_read_records=self.policy.max_read_records,
        )
        self.validator = validator or LiveExecutionDesignSpecValidator(self.policy)

    def build_and_record(
        self,
        capability_report: LiveExecutionCapabilityReport,
        blocked_receipt: LiveExecutionBlockedReceipt,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        draft=None,
    ) -> LiveExecutionDesignSpecResult:
        started = perf_counter()
        report = self.builder.build(capability_report, blocked_receipt, contract, simulated_receipt, draft)
        report_validation = self.validator.validate_report(report)
        warning_parts: list[str] = []
        if not report_validation.passed:
            report.blockers = list(dict.fromkeys(list(report.blockers) + report_validation.issues))
            if report.design_status != "INVALID":
                report.design_status = "INVALID"
            report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("live_design_report_validation_failed:" + ",".join(report_validation.issues))
        record = None
        if self.policy.journal_enabled:
            record = self._build_record(report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    self.store.append(record)
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_design_report_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_design_report_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_design_report_journal_disabled")
        summary = self.store.summarize()
        timings = dict(self.builder.last_timings_ms)
        timings["report_build_latency_ms"] = (perf_counter() - started) * 1000
        return LiveExecutionDesignSpecResult(report, record, summary, ";".join(warning_parts), timings)

    def _build_record(self, report: LiveExecutionReadinessSpecReport) -> LiveExecutionDesignReportRecord:
        created_at = now_utc_iso()
        record = LiveExecutionDesignReportRecord(
            journal_record_id=_record_id(report.report_id, created_at),
            created_at=created_at,
            report_id=report.report_id,
            design_status=report.design_status,
            live_execution_allowed=False,
            hard_live_block_required=True,
            threats_count=len(report.threats),
            preflight_checks_count=len(report.preflight_checks),
            approval_requirements_count=len(report.approval_requirements),
            failure_modes_count=len(report.failure_modes),
            audit_requirements_count=len(report.audit_requirements),
            readiness_score=report.readiness_score,
            source_capability_report_id=report.source_capability_report_id,
            source_blocked_receipt_id=report.source_blocked_receipt_id,
            source_contract_id=report.source_contract_id,
            source_refs=list(report.source_refs),
            blockers=list(report.blockers),
            warnings=list(report.warnings),
            metadata_redacted={
                "design_only": True,
                "live_execution_allowed": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_execution_design_report_journal_{digest}"
