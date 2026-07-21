from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.permission.models import LivePermissionJournalRecord, LivePermissionSummary


class LivePermissionJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_LIVE_PERMISSION_JOURNAL_PATH",
            "data/trading/execution_journal/live_permission_intents.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_LIVE_PERMISSION_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: LivePermissionJournalRecord) -> LivePermissionJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[LivePermissionJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("live_permission_journal_missing")
            return []
        records: list[LivePermissionJournalRecord] = []
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

    def summarize(self, limit: int | None = None) -> LivePermissionSummary:
        records = self.read_latest(limit)
        summary = LivePermissionSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_granted = sum(1 for item in records if item.permission_status == "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW")
        summary.total_blocked = sum(1 for item in records if item.permission_status in {"BLOCKED", "INVALID", "EXPIRED"})
        summary.total_duplicates = sum(1 for item in records if item.permission_status == "DUPLICATE")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_intent_id = latest.intent_id
        summary.latest_decision_id = latest.decision_id
        summary.latest_permission_status = latest.permission_status
        return summary

    def idempotency_keys(self, limit: int | None = None) -> set[str]:
        return {item.idempotency_key for item in self.read_latest(limit) if item.idempotency_key}


def _record_from_dict(data: dict) -> LivePermissionJournalRecord:
    return LivePermissionJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        intent_id=str(data.get("intent_id", "")),
        decision_id=str(data.get("decision_id", "")),
        permission_status=str(data.get("permission_status", "UNKNOWN")),
        permission_scope=str(data.get("permission_scope", "UNKNOWN")),
        confirmation_state=str(data.get("confirmation_state", "UNKNOWN")),
        order_intent_workflow_allowed=bool(data.get("order_intent_workflow_allowed", False)),
        live_execution_allowed=bool(data.get("live_execution_allowed", False)),
        order_send_allowed=bool(data.get("order_send_allowed", False)),
        execution_allowed=bool(data.get("execution_allowed", False)),
        hard_live_block_required=bool(data.get("hard_live_block_required", True)),
        artifact_hash=str(data.get("artifact_hash", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        source_preflight_report_id=str(data.get("source_preflight_report_id", "")),
        source_design_report_id=str(data.get("source_design_report_id", "")),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
