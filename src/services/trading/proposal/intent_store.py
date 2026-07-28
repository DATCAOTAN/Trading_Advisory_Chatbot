from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from pathlib import Path

from src.config import Config
from src.services.trading.proposal.models import ProposalBoundarySummary, ProposalIntentJournalRecord


class ProposalIntentJournalStore:
    _process_lock = threading.Lock()

    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(Config, "TRADING_PROPOSAL_JOURNAL_PATH", "data/trading/execution_journal/proposal_intents.jsonl")
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_EXECUTION_JOURNAL_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(self, record: ProposalIntentJournalRecord) -> ProposalIntentJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def append_idempotent(
        self, record: ProposalIntentJournalRecord
    ) -> tuple[ProposalIntentJournalRecord, bool]:
        with self._exclusive_lock():
            records = self.read_latest(2**31 - 1)
            if any(item != "proposal_intent_journal_missing" for item in self.warnings):
                raise RuntimeError("PROPOSAL_INTENT_JOURNAL_CORRUPT")
            existing = next(
                (
                    item
                    for item in records
                    if item.candidate_reference == record.candidate_reference
                    and item.candidate_reference
                ),
                None,
            )
            if existing is not None:
                return existing, False
            return self.append(record), True

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
                    raise RuntimeError("PROPOSAL_INTENT_JOURNAL_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    store.lock_path.unlink()
                finally:
                    store._process_lock.release()

        return LockContext()

    def read_latest(self, limit: int | None = None) -> list[ProposalIntentJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("proposal_intent_journal_missing")
            return []
        records: list[ProposalIntentJournalRecord] = []
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

    def summarize(self, limit: int | None = None) -> ProposalBoundarySummary:
        records = self.read_latest(limit)
        summary = ProposalBoundarySummary(total_intents=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_confirmed = sum(
            1 for item in records if item.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
        )
        summary.total_blocked = sum(1 for item in records if item.proposal_boundary_status in {"BLOCKED", "INVALID"})
        summary.total_expired = sum(1 for item in records if item.proposal_boundary_status == "EXPIRED")
        summary.total_duplicates = sum(1 for item in records if item.proposal_boundary_status == "DUPLICATE")
        latest = records[-1]
        summary.latest_intent_id = latest.intent_id
        summary.latest_status = latest.proposal_boundary_status
        summary.latest_created_at = latest.created_at
        return summary


def _record_from_dict(data: dict) -> ProposalIntentJournalRecord:
    record = ProposalIntentJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        intent_id=str(data.get("intent_id", "")),
        proposal_boundary_status=str(data.get("proposal_boundary_status", "UNKNOWN")),
        human_confirmation_state=str(data.get("human_confirmation_state", "UNKNOWN")),
        proposal_workflow_allowed=bool(data.get("proposal_workflow_allowed", False)),
        dry_run_only=bool(data.get("dry_run_only", True)),
        executable=bool(data.get("executable", False)),
        artifact_id=str(data.get("artifact_id", "")),
        artifact_hash=str(data.get("artifact_hash", "")),
        dry_run_receipt_id=str(data.get("dry_run_receipt_id", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        candidate_reference=str(data.get("candidate_reference", "")),
        candidate_provenance_hash=str(data.get("candidate_provenance_hash", "")),
        candidate_structured_order_hash=str(data.get("candidate_structured_order_hash", "")),
        account_context_reference=str(data.get("account_context_reference", "")),
        account_fingerprint_hash=str(data.get("account_fingerprint_hash", "")),
        symbol=str(data.get("symbol", "")),
        broker_symbol=str(data.get("broker_symbol", "")),
        order_type=str(data.get("order_type", "")),
        timeframe_profile=list(data.get("timeframe_profile", []) or []),
        operator_action=str(data.get("operator_action", "")),
        confirmation_nonce=str(data.get("confirmation_nonce", "")),
        confirmation_expires_at=str(data.get("confirmation_expires_at", "")),
        confirmation_binding_hash=str(data.get("confirmation_binding_hash", "")),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
        record_hash=str(data.get("record_hash", "")),
    )
    if record.candidate_reference and not _record_hash_valid(record):
        raise ValueError("candidate confirmation record hash is invalid")
    return record


def proposal_record_hash(record: ProposalIntentJournalRecord) -> str:
    payload = record.as_dict()
    payload.pop("record_hash", None)
    payload.pop("payload_size_chars", None)
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record_hash_valid(record: ProposalIntentJournalRecord) -> bool:
    return len(record.record_hash) == 64 and hmac.compare_digest(
        record.record_hash, proposal_record_hash(record)
    )
