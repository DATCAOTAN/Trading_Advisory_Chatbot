from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockSummary,
)


class LiveExecutionBlockJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_MT5_SKELETON_JOURNAL_PATH",
            "data/trading/execution_journal/live_execution_blocks.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_MT5_SKELETON_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: LiveExecutionBlockJournalRecord) -> LiveExecutionBlockJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[LiveExecutionBlockJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("live_execution_block_journal_missing")
            return []
        records: list[LiveExecutionBlockJournalRecord] = []
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

    def summarize(self, limit: int | None = None) -> LiveExecutionBlockSummary:
        records = self.read_latest(limit)
        summary = LiveExecutionBlockSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_blocked = sum(1 for item in records if item.blocked)
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_receipt_id = latest.receipt_id
        summary.latest_block_reason = latest.block_reason
        return summary


def _record_from_dict(data: dict) -> LiveExecutionBlockJournalRecord:
    return LiveExecutionBlockJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        adapter_type=str(data.get("adapter_type", "RESERVED_MT5_LIVE")),
        skeleton_status=str(data.get("skeleton_status", "HARD_BLOCKED")),
        receipt_id=str(data.get("receipt_id", "")),
        blocked=bool(data.get("blocked", True)),
        executed=bool(data.get("executed", False)),
        order_sent=bool(data.get("order_sent", False)),
        live_execution_supported=bool(data.get("live_execution_supported", False)),
        hard_live_block_enabled=bool(data.get("hard_live_block_enabled", True)),
        block_reason=str(data.get("block_reason", "HARD_LIVE_BLOCK_ENABLED")),
        source_contract_id=str(data.get("source_contract_id", "")),
        source_simulated_receipt_id=str(data.get("source_simulated_receipt_id", "")),
        artifact_hash=str(data.get("artifact_hash", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
