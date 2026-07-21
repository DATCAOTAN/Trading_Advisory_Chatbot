from __future__ import annotations

import hashlib
import json

from src.services.trading.proposal.intent_store import ProposalIntentJournalStore
from src.services.trading.proposal.models import (
    HumanConfirmedProposalIntent,
    ProposalBoundarySummary,
    ProposalIntentJournalRecord,
    now_utc_iso,
)
from src.services.trading.proposal.validator import ProposalBoundaryValidator


class ProposalIntentJournalService:
    def __init__(
        self,
        store: ProposalIntentJournalStore | None = None,
        validator: ProposalBoundaryValidator | None = None,
        enabled: bool = True,
    ):
        self.store = store or ProposalIntentJournalStore()
        self.validator = validator or ProposalBoundaryValidator()
        self.enabled = bool(enabled)
        self.last_warning = ""

    def build_record(self, intent: HumanConfirmedProposalIntent) -> ProposalIntentJournalRecord:
        created_at = now_utc_iso()
        record = ProposalIntentJournalRecord(
            journal_record_id=_record_id(intent.intent_id, created_at),
            created_at=created_at,
            event_type=_event_type(intent),
            intent_id=intent.intent_id,
            proposal_boundary_status=intent.proposal_boundary_status,
            human_confirmation_state=intent.human_confirmation_state,
            proposal_workflow_allowed=intent.proposal_workflow_allowed,
            dry_run_only=True,
            executable=False,
            artifact_id=intent.artifact_id,
            artifact_hash=intent.artifact_hash,
            dry_run_receipt_id=intent.dry_run_receipt_id,
            idempotency_key=intent.idempotency_key,
            blockers=list(intent.blockers),
            warnings=list(intent.warnings),
            source_refs=list(dict.fromkeys(intent.source_refs)),
            metadata_redacted={
                "artifact_hash_prefix": intent.artifact_hash[:12],
                "idempotency_key_prefix": intent.idempotency_key[:12],
                "dry_run_only": True,
                "executable": False,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record

    def append_intent(self, intent: HumanConfirmedProposalIntent) -> ProposalIntentJournalRecord | None:
        self.last_warning = ""
        if not self.enabled:
            self.last_warning = "proposal_intent_journal_disabled"
            return None
        record = self.build_record(intent)
        validation = self.validator.validate_record(record)
        if not validation.passed:
            self.last_warning = "proposal_intent_journal_validation_failed:" + ",".join(validation.issues)
            return None
        try:
            return self.store.append(record)
        except Exception as exc:
            self.last_warning = f"proposal_intent_journal_write_failed:{type(exc).__name__}"
            return None

    def summary(self) -> ProposalBoundarySummary:
        return self.store.summarize()


def _event_type(intent: HumanConfirmedProposalIntent) -> str:
    if intent.proposal_boundary_status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
        return "PROPOSAL_INTENT_CONFIRMED"
    if intent.proposal_boundary_status == "EXPIRED":
        return "PROPOSAL_INTENT_EXPIRED"
    if intent.proposal_boundary_status == "DUPLICATE":
        return "PROPOSAL_INTENT_DUPLICATE"
    if intent.proposal_boundary_status == "INVALID":
        return "PROPOSAL_INTENT_INVALID"
    if intent.proposal_boundary_status == "BLOCKED":
        return "PROPOSAL_INTENT_BLOCKED"
    return "PROPOSAL_INTENT_CREATED"


def _record_id(intent_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{intent_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"proposal_intent_journal_{digest}"
