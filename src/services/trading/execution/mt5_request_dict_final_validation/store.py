from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    MT5RequestDictFinalValidationJournalRecord,
    MT5RequestDictFinalValidationSummary,
)


class MT5RequestDictFinalValidationJournalStore:
    def __init__(self, path: str | Path = "data/trading/execution_journal/mt5_request_dict_final_validations.jsonl", max_read_records: int = 100):
        self.path = Path(path)
        self.max_read_records = max_read_records

    def append(self, record: MT5RequestDictFinalValidationJournalRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    def read_latest(self, limit: int | None = None) -> list[dict]:
        limit = int(limit or self.max_read_records)
        if not self.path.exists():
            return []
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:]

    def summarize(self) -> MT5RequestDictFinalValidationSummary:
        warnings: list[str] = []
        rows: list[dict] = []
        if self.path.exists():
            for index, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    warnings.append(f"corrupt_jsonl_line:{index}")
        latest = rows[-1] if rows else {}
        return MT5RequestDictFinalValidationSummary(
            total_records=len(rows),
            total_passed=sum(1 for row in rows if row.get("status") == "FINAL_VALIDATION_PASSED"),
            total_blocked=sum(1 for row in rows if row.get("status") in {"BLOCKED", "EXPIRED", "DUPLICATE", "INVALID"}),
            latest_final_validation_id=latest.get("final_validation_id", ""),
            latest_validation_report_id=latest.get("validation_report_id", ""),
            latest_status=latest.get("status", ""),
            warnings=warnings,
        )

    def idempotency_keys(self) -> set[str]:
        return {row.get("idempotency_key", "") for row in self.read_latest(self.max_read_records) if row.get("idempotency_key")}

    def find_by_idempotency_key(self, key: str) -> dict | None:
        for row in reversed(self.read_latest(self.max_read_records)):
            if row.get("idempotency_key") == key:
                return row
        return None
