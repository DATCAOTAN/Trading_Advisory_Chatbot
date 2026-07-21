from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.journal_models import ExecutionJournalRecord, ExecutionJournalSummary


class ExecutionJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(Config, "TRADING_EXECUTION_JOURNAL_PATH", "data/trading/execution_journal/dry_run_receipts.jsonl")
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_EXECUTION_JOURNAL_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: ExecutionJournalRecord) -> ExecutionJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[ExecutionJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("journal_missing")
            return []
        limit = int(limit or self.max_read_records)
        records: list[ExecutionJournalRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    records.append(_record_from_dict(data))
                except Exception:
                    self.warnings.append(f"corrupt_jsonl_line:{line_number}")
        return records[-limit:]

    def summarize(self, limit: int | None = None) -> ExecutionJournalSummary:
        records = self.read_latest(limit)
        summary = ExecutionJournalSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_dry_runs = sum(1 for item in records if item.dry_run_only)
        summary.total_blocked = sum(1 for item in records if not item.allowed or item.gate_action in {"BLOCKED", "DUPLICATE_ARTIFACT"})
        summary.total_allowed = sum(1 for item in records if item.allowed)
        summary.total_duplicates = sum(1 for item in records if item.gate_action == "DUPLICATE_ARTIFACT" or item.event_type == "DRY_RUN_DUPLICATE_DETECTED")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_artifact_hash = latest.artifact_hash
        summary.latest_gate_action = latest.gate_action
        summary.latest_receipt_id = latest.receipt_id
        return summary


def _record_from_dict(data: dict) -> ExecutionJournalRecord:
    return ExecutionJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        mode=str(data.get("mode", "")),
        symbol=str(data.get("symbol", "")),
        broker_symbol=str(data.get("broker_symbol", "")),
        artifact_id=str(data.get("artifact_id", "")),
        artifact_hash=str(data.get("artifact_hash", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        gate_decision_id=str(data.get("gate_decision_id", "")),
        gate_action=str(data.get("gate_action", "")),
        receipt_id=str(data.get("receipt_id", "")),
        dry_run_only=bool(data.get("dry_run_only", True)),
        executed=bool(data.get("executed", False)),
        allowed=bool(data.get("allowed", False)),
        review_status=str(data.get("review_status", "")),
        readiness_action=str(data.get("readiness_action", "")),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
