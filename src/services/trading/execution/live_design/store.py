from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.live_design.readiness_models import (
    LiveExecutionDesignReportRecord,
    LiveExecutionDesignReportSummary,
)


class LiveExecutionDesignReportStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_LIVE_DESIGN_JOURNAL_PATH",
            "data/trading/execution_journal/live_execution_design_reports.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_LIVE_DESIGN_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: LiveExecutionDesignReportRecord) -> LiveExecutionDesignReportRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[LiveExecutionDesignReportRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("live_execution_design_report_journal_missing")
            return []
        records: list[LiveExecutionDesignReportRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    records.append(_record_from_dict(json.loads(raw)))
                except Exception:
                    self.warnings.append(f"corrupt_jsonl_line:{line_number}")
        return records[-int(limit or self.max_read_records) :]

    def summarize(self, limit: int | None = None) -> LiveExecutionDesignReportSummary:
        records = self.read_latest(limit)
        summary = LiveExecutionDesignReportSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_design_only = sum(1 for item in records if item.design_status in {"DESIGN_ONLY", "APPROVAL_REQUIRED"})
        summary.total_invalid = sum(1 for item in records if item.design_status == "INVALID")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_report_id = latest.report_id
        summary.latest_design_status = latest.design_status
        return summary


def _record_from_dict(data: dict) -> LiveExecutionDesignReportRecord:
    return LiveExecutionDesignReportRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        report_id=str(data.get("report_id", "")),
        design_status=str(data.get("design_status", "UNKNOWN")),
        live_execution_allowed=bool(data.get("live_execution_allowed", False)),
        hard_live_block_required=bool(data.get("hard_live_block_required", True)),
        threats_count=int(data.get("threats_count", 0) or 0),
        preflight_checks_count=int(data.get("preflight_checks_count", 0) or 0),
        approval_requirements_count=int(data.get("approval_requirements_count", 0) or 0),
        failure_modes_count=int(data.get("failure_modes_count", 0) or 0),
        audit_requirements_count=int(data.get("audit_requirements_count", 0) or 0),
        readiness_score=float(data.get("readiness_score", 0.0) or 0.0),
        source_capability_report_id=str(data.get("source_capability_report_id", "")),
        source_blocked_receipt_id=str(data.get("source_blocked_receipt_id", "")),
        source_contract_id=str(data.get("source_contract_id", "")),
        source_refs=list(data.get("source_refs", []) or []),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
