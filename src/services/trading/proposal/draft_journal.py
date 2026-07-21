from __future__ import annotations

import hashlib
import json

from src.services.trading.proposal.draft_models import (
    NonExecutableTradeProposalDraft,
    ProposalDraftJournalRecord,
    ProposalDraftSummary,
    now_utc_iso,
)
from src.services.trading.proposal.draft_store import ProposalDraftJournalStore
from src.services.trading.proposal.draft_validator import ProposalDraftValidator
from src.services.trading.proposal.models import HumanConfirmedProposalIntent


class ProposalDraftJournalService:
    def __init__(
        self,
        store: ProposalDraftJournalStore | None = None,
        validator: ProposalDraftValidator | None = None,
        enabled: bool = True,
    ):
        self.store = store or ProposalDraftJournalStore()
        self.validator = validator or ProposalDraftValidator()
        self.enabled = bool(enabled)
        self.last_warning = ""

    def build_record(
        self,
        draft: NonExecutableTradeProposalDraft,
        intent: HumanConfirmedProposalIntent,
    ) -> ProposalDraftJournalRecord:
        created_at = now_utc_iso()
        record = ProposalDraftJournalRecord(
            journal_record_id=_record_id(draft.draft_id, created_at),
            created_at=created_at,
            draft_id=draft.draft_id,
            status=draft.status,
            non_executable=True,
            executable=False,
            source_intent_id=intent.intent_id,
            artifact_hash=intent.artifact_hash,
            primary_method_id=draft.primary_method_id,
            primary_regime=draft.primary_regime,
            calendar_risk_state=draft.calendar_risk_state,
            readiness_action=draft.readiness_action,
            final_context_score=draft.final_context_score,
            blockers=list(draft.blockers),
            warnings=list(draft.warnings),
            source_refs=list(dict.fromkeys(draft.source_refs)),
            metadata_redacted={
                "artifact_hash_prefix": intent.artifact_hash[:12],
                "non_executable": True,
                "executable": False,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record

    def append_draft(
        self,
        draft: NonExecutableTradeProposalDraft,
        intent: HumanConfirmedProposalIntent,
    ) -> ProposalDraftJournalRecord | None:
        self.last_warning = ""
        if not self.enabled:
            self.last_warning = "proposal_draft_journal_disabled"
            return None
        record = self.build_record(draft, intent)
        validation = self.validator.validate_record(record)
        if not validation.passed:
            self.last_warning = "proposal_draft_journal_validation_failed:" + ",".join(validation.issues)
            return None
        try:
            return self.store.append(record)
        except Exception as exc:
            self.last_warning = f"proposal_draft_journal_write_failed:{type(exc).__name__}"
            return None

    def summary(self) -> ProposalDraftSummary:
        return self.store.summarize()


def _record_id(draft_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{draft_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"proposal_draft_journal_{digest}"
