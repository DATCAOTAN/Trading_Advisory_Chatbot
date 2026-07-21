from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import MT5PreSubmitJournalRecord, MT5PreSubmitSummary


class MT5PreSubmitJournalStore:
    def __init__(self, path: str | Path = "data/trading/execution_journal/mt5_pre_submit_checks.jsonl", max_read_records: int = 100):
        self.path = Path(path)
        self.max_read_records = max_read_records

    def append(self, record: MT5PreSubmitJournalRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    def read_latest(self, limit: int | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-int(limit or self.max_read_records):]

    def summarize(self) -> MT5PreSubmitSummary:
        warnings = []
        rows = []
        if self.path.exists():
            for index, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    warnings.append(f"corrupt_jsonl_line:{index}")
        latest = rows[-1] if rows else {}
        return MT5PreSubmitSummary(
            total_records=len(rows),
            total_valid=sum(1 for row in rows if row.get("valid") is True),
            total_blocked=sum(1 for row in rows if row.get("valid") is not True),
            latest_report_id=latest.get("pre_submit_report_id", ""),
            latest_status=latest.get("status", ""),
            warnings=warnings,
        )
