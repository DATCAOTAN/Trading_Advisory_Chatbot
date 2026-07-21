from __future__ import annotations

from src.services.trading.execution.journal_models import ExecutionJournalRecord, ExecutionJournalSummary


class ExecutionJournalFormatter:
    def record_summary(self, record: ExecutionJournalRecord) -> dict:
        return {
            "created_at": record.created_at,
            "event_type": record.event_type,
            "gate_action": record.gate_action,
            "allowed": record.allowed,
            "dry_run_only": True,
            "executed": False,
            "artifact_hash_prefix": record.artifact_hash[:12],
            "idempotency_key_prefix": record.idempotency_key[:12],
            "source_refs_count": len(record.source_refs),
        }

    def summary_dict(self, summary: ExecutionJournalSummary) -> dict:
        return summary.as_dict()
