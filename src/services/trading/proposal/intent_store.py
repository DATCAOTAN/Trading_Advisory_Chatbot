from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.proposal.models import ProposalBoundarySummary, ProposalIntentJournalRecord


class ProposalIntentJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(Config, "TRADING_PROPOSAL_JOURNAL_PATH", "data/trading/execution_journal/proposal_intents.jsonl")
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_EXECUTION_JOURNAL_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: ProposalIntentJournalRecord) -> ProposalIntentJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

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
    return ProposalIntentJournalRecord(
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
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
