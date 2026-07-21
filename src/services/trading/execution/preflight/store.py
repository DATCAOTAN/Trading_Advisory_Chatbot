from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.preflight.models import LiveExecutionPreflightSummary, PreflightJournalRecord


class LiveExecutionPreflightReportStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_LIVE_PREFLIGHT_JOURNAL_PATH",
            "data/trading/execution_journal/live_execution_preflight_reports.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_LIVE_PREFLIGHT_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: PreflightJournalRecord) -> PreflightJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[PreflightJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("live_execution_preflight_journal_missing")
            return []
        records: list[PreflightJournalRecord] = []
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

    def summarize(self, limit: int | None = None) -> LiveExecutionPreflightSummary:
        records = self.read_latest(limit)
        summary = LiveExecutionPreflightSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_pass = sum(1 for item in records if item.preflight_status == "PASS")
        summary.total_fail = sum(1 for item in records if item.preflight_status == "FAIL")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_report_id = latest.report_id
        summary.latest_preflight_status = latest.preflight_status
        summary.latest_blocking_failures = latest.blocking_failures
        return summary


def _record_from_dict(data: dict) -> PreflightJournalRecord:
    return PreflightJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        report_id=str(data.get("report_id", "")),
        preflight_status=str(data.get("preflight_status", "UNKNOWN")),
        live_execution_allowed=bool(data.get("live_execution_allowed", False)),
        all_blocking_checks_passed=bool(data.get("all_blocking_checks_passed", False)),
        total_checks=int(data.get("total_checks", 0) or 0),
        passed_checks=int(data.get("passed_checks", 0) or 0),
        failed_checks=int(data.get("failed_checks", 0) or 0),
        warning_checks=int(data.get("warning_checks", 0) or 0),
        blocking_failures=int(data.get("blocking_failures", 0) or 0),
        critical_failures=int(data.get("critical_failures", 0) or 0),
        hard_live_block_required=bool(data.get("hard_live_block_required", True)),
        source_design_report_id=str(data.get("source_design_report_id", "")),
        source_capability_report_id=str(data.get("source_capability_report_id", "")),
        source_blocked_receipt_id=str(data.get("source_blocked_receipt_id", "")),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
