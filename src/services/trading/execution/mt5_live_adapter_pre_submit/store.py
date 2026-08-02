from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from pathlib import Path

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import MT5PreSubmitJournalRecord, MT5PreSubmitSummary


class MT5PreSubmitJournalStore:
    _process_lock = threading.Lock()

    def __init__(self, path: str | Path = "data/trading/execution_journal/mt5_pre_submit_checks.jsonl", max_read_records: int = 100):
        self.path = Path(path)
        self.max_read_records = max_read_records
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(self, record: MT5PreSubmitJournalRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    def append_idempotent(
        self, record: MT5PreSubmitJournalRecord
    ) -> tuple[dict, bool]:
        with self._exclusive_lock():
            rows = self._read_strict()
            key_hash = record.idempotency_key_hash
            authority_id = (
                record.source_authorization_id
                or record.source_confirmation_intent_id
            )
            existing = next(
                (row for row in rows if row.get("idempotency_key_hash") == key_hash),
                None,
            )
            if existing is not None:
                if not hmac.compare_digest(
                    str(existing.get("artifact_hash", "")), record.artifact_hash
                ):
                    raise RuntimeError("PRE_SUBMIT_IDEMPOTENCY_CONFLICT")
                return existing, False
            reused = next(
                (
                    row
                    for row in rows
                    if authority_id
                    and (
                        row.get("source_authorization_id")
                        or row.get("source_confirmation_intent_id")
                    )
                    == authority_id
                ),
                None,
            )
            if reused is not None:
                raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
            payload = record.as_dict()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return payload, True

    def _read_strict(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeError("PRE_SUBMIT_JOURNAL_UNAVAILABLE") from exc
        rows: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("PRE_SUBMIT_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict):
                raise RuntimeError("PRE_SUBMIT_JOURNAL_CORRUPT")
            if row.get("record_hash"):
                actual = str(row["record_hash"])
                material = dict(row)
                material["record_hash"] = ""
                expected = pre_submit_record_hash(material)
                if not hmac.compare_digest(actual, expected):
                    raise RuntimeError("PRE_SUBMIT_JOURNAL_CORRUPT")
            elif not {
                "journal_record_id",
                "pre_submit_report_id",
                "idempotency_key_hash",
                "metadata_redacted",
            }.issubset(row) or row.get("metadata_redacted") is not True:
                raise RuntimeError("PRE_SUBMIT_JOURNAL_CORRUPT")
            rows.append(row)
        return rows

    def _exclusive_lock(self):
        store = self

        class LockContext:
            def __enter__(self):
                store._process_lock.acquire()
                store.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.fd = os.open(
                        store.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                except (FileExistsError, OSError) as exc:
                    store._process_lock.release()
                    raise RuntimeError("PRE_SUBMIT_JOURNAL_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    store.lock_path.unlink()
                finally:
                    store._process_lock.release()

        return LockContext()

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


def pre_submit_record_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
