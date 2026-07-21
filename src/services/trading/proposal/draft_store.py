from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.proposal.draft_models import ProposalDraftJournalRecord, ProposalDraftSummary


class ProposalDraftJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(Config, "TRADING_PROPOSAL_DRAFT_JOURNAL_PATH", "data/trading/execution_journal/proposal_drafts.jsonl")
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_PROPOSAL_DRAFT_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: ProposalDraftJournalRecord) -> ProposalDraftJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[ProposalDraftJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("proposal_draft_journal_missing")
            return []
        records: list[ProposalDraftJournalRecord] = []
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

    def summarize(self, limit: int | None = None) -> ProposalDraftSummary:
        records = self.read_latest(limit)
        summary = ProposalDraftSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_created = sum(1 for item in records if item.status == "DRAFT_CREATED")
        summary.total_blocked = sum(1 for item in records if item.status in {"BLOCKED", "INVALID"})
        summary.total_waiting = sum(1 for item in records if item.status == "WAITING")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_draft_id = latest.draft_id
        summary.latest_status = latest.status
        return summary


def _record_from_dict(data: dict) -> ProposalDraftJournalRecord:
    return ProposalDraftJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        draft_id=str(data.get("draft_id", "")),
        status=str(data.get("status", "UNKNOWN")),
        non_executable=bool(data.get("non_executable", True)),
        executable=bool(data.get("executable", False)),
        source_intent_id=str(data.get("source_intent_id", "")),
        artifact_hash=str(data.get("artifact_hash", "")),
        primary_method_id=str(data.get("primary_method_id", "")),
        primary_regime=str(data.get("primary_regime", "UNKNOWN")),
        calendar_risk_state=str(data.get("calendar_risk_state", "UNKNOWN")),
        readiness_action=str(data.get("readiness_action", "UNKNOWN")),
        final_context_score=float(data.get("final_context_score", 0.0) or 0.0),
        blockers=list(data.get("blockers", []) or []),
        warnings=list(data.get("warnings", []) or []),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
