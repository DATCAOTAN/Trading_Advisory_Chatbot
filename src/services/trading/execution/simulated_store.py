from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.adapter_models import SimulatedExecutionJournalRecord, SimulatedExecutionSummary


class SimulatedExecutionJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_EXECUTION_SIMULATED_JOURNAL_PATH",
            "data/trading/execution_journal/simulated_execution_receipts.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_EXECUTION_JOURNAL_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: SimulatedExecutionJournalRecord) -> SimulatedExecutionJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[SimulatedExecutionJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("simulated_execution_journal_missing")
            return []
        records: list[SimulatedExecutionJournalRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    records.append(_record_from_dict(json.loads(raw)))
                except Exception:
                    self.warnings.append(f"corrupt_jsonl_line:{line_number}")
        limit = int(limit or self.max_read_records)
        return records[-limit:]

    def summarize(self, limit: int | None = None) -> SimulatedExecutionSummary:
        records = self.read_latest(limit)
        summary = SimulatedExecutionSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_accepted = sum(1 for item in records if item.accepted_by_adapter)
        summary.total_rejected = sum(1 for item in records if not item.accepted_by_adapter)
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_contract_id = latest.contract_id
        summary.latest_receipt_id = latest.receipt_id
        summary.latest_contract_status = latest.contract_status
        return summary


def _record_from_dict(data: dict) -> SimulatedExecutionJournalRecord:
    return SimulatedExecutionJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        adapter_type=str(data.get("adapter_type", "SIMULATED")),
        contract_id=str(data.get("contract_id", "")),
        receipt_id=str(data.get("receipt_id", "")),
        contract_status=str(data.get("contract_status", "UNKNOWN")),
        simulated_only=bool(data.get("simulated_only", True)),
        executable=bool(data.get("executable", False)),
        executed=bool(data.get("executed", False)),
        accepted_by_adapter=bool(data.get("accepted_by_adapter", False)),
        source_draft_id=str(data.get("source_draft_id", "")),
        artifact_hash=str(data.get("artifact_hash", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
