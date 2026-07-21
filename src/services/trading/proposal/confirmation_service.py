from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.models import DryRunExecutionReceipt
from src.services.trading.proposal.intent_journal import ProposalIntentJournalService
from src.services.trading.proposal.models import HumanConfirmedProposalIntent, ProposalIntentJournalRecord, now_utc_iso
from src.services.trading.proposal.policies import ProposalBoundaryPolicy
from src.services.trading.proposal.validator import ProposalBoundaryValidator
from src.services.trading.review.models import HumanReviewArtifact


@dataclass
class ProposalConfirmationResult:
    intent: HumanConfirmedProposalIntent
    journal_record: ProposalIntentJournalRecord | None = None
    warning: str = ""


class HumanProposalConfirmationService:
    def __init__(
        self,
        policy: ProposalBoundaryPolicy | None = None,
        journal: ProposalIntentJournalService | None = None,
        validator: ProposalBoundaryValidator | None = None,
    ):
        self.policy = policy or ProposalBoundaryPolicy.from_config()
        self.validator = validator or ProposalBoundaryValidator(max_payload_chars=self.policy.max_payload_chars)
        self.journal = journal or ProposalIntentJournalService(enabled=self.policy.journal_enabled, validator=self.validator)
        self._seen_idempotency_keys: set[str] = set()
        self.last_journal_record: ProposalIntentJournalRecord | None = None
        self.last_warning = ""

    def confirm(
        self,
        artifact: HumanReviewArtifact,
        receipt: DryRunExecutionReceipt | None,
        execution_journal_record: ExecutionJournalRecord | None = None,
        user_acknowledgement_text: str = "",
        now: datetime | None = None,
    ) -> HumanConfirmedProposalIntent:
        result = self.confirm_with_journal(
            artifact,
            receipt,
            execution_journal_record=execution_journal_record,
            user_acknowledgement_text=user_acknowledgement_text,
            now=now,
        )
        return result.intent

    def confirm_with_journal(
        self,
        artifact: HumanReviewArtifact,
        receipt: DryRunExecutionReceipt | None,
        execution_journal_record: ExecutionJournalRecord | None = None,
        user_acknowledgement_text: str = "",
        now: datetime | None = None,
    ) -> ProposalConfirmationResult:
        self.last_warning = ""
        created_at = now_utc_iso()
        blockers: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []
        status = "READY_FOR_CONFIRMATION"
        human_state = "NOT_REQUESTED"
        allowed = False

        if not self.policy.enabled:
            status = "BLOCKED"
            blockers.append("proposal_boundary_disabled")

        if receipt is None:
            if self.policy.require_dry_run_receipt:
                status = "BLOCKED"
                blockers.append("dry_run_receipt_required")
            receipt = _empty_receipt(artifact)

        if receipt.executed:
            status = "BLOCKED"
            blockers.append("dry_run_receipt_executed_true")
        if receipt.dry_run_only is not True:
            status = "BLOCKED"
            blockers.append("dry_run_receipt_not_dry_run_only")
        if self.policy.require_dry_run_allowed and not receipt.allowed:
            status = "BLOCKED"
            blockers.append("dry_run_receipt_not_allowed")

        if self.policy.require_journal_record and execution_journal_record is None:
            status = "BLOCKED"
            blockers.append("execution_journal_record_required")

        if self.policy.require_ready_for_review and artifact.review_status != "READY_FOR_REVIEW":
            if artifact.review_status == "WAITING" and not self.policy.allow_waiting_artifact:
                status = "BLOCKED"
                blockers.append("review_status_waiting")
            elif artifact.review_status in {"BLOCKED", "NO_TRADE_CONTEXT"} and not self.policy.allow_blocked_artifact:
                status = "BLOCKED"
                blockers.append(f"review_status_{artifact.review_status.lower()}")
            elif artifact.review_status not in {"WAITING", "BLOCKED", "NO_TRADE_CONTEXT"}:
                status = "BLOCKED"
                blockers.append(f"review_status_{artifact.review_status.lower()}")

        age_seconds = _artifact_age_seconds(artifact.created_at, now=now)
        if age_seconds > self.policy.intent_ttl_seconds:
            status = "EXPIRED"
            human_state = "EXPIRED"
            blockers.append("proposal_boundary_artifact_expired")

        received = (user_acknowledgement_text or "").strip()
        required = self.policy.confirmation_phrase.strip()
        if status not in {"BLOCKED", "EXPIRED"}:
            if not received:
                human_state = "NOT_REQUESTED"
                reasons.append("confirmation_phrase_required")
            elif received != required:
                status = "INVALID"
                human_state = "ACKNOWLEDGED_DRY_RUN_ONLY"
                blockers.append("confirmation_phrase_mismatch")
            else:
                human_state = "CONFIRMED_PROPOSAL_WORKFLOW"

        idempotency_key = receipt.idempotency_key or _fallback_idempotency_key(artifact, receipt)
        if self.policy.idempotency_enabled and status not in {"BLOCKED", "EXPIRED", "INVALID"}:
            if idempotency_key in self._seen_idempotency_keys:
                status = "DUPLICATE"
                blockers.append("duplicate_proposal_intent")
            elif human_state == "CONFIRMED_PROPOSAL_WORKFLOW":
                self._seen_idempotency_keys.add(idempotency_key)

        if status == "READY_FOR_CONFIRMATION" and human_state == "CONFIRMED_PROPOSAL_WORKFLOW":
            status = "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
            allowed = True
            reasons.append("confirmation_phrase_matched")
        elif status == "READY_FOR_CONFIRMATION":
            allowed = False
        else:
            allowed = False

        intent = HumanConfirmedProposalIntent(
            intent_id=_intent_id(artifact.artifact_id, receipt.receipt_id, idempotency_key, created_at),
            created_at=created_at,
            mode=receipt.mode or artifact.mode,
            symbol=artifact.symbol,
            broker_symbol=artifact.broker_symbol,
            proposal_boundary_status=status,
            human_confirmation_state=human_state,
            proposal_workflow_allowed=allowed,
            dry_run_only=True,
            executable=False,
            user_acknowledgement_text=received,
            confirmation_phrase_required=required,
            confirmation_phrase_received=received,
            review_status=artifact.review_status,
            readiness_action=artifact.readiness_action,
            gate_action=receipt.gate_action,
            dry_run_allowed=receipt.allowed,
            dry_run_executed=False,
            artifact_id=artifact.artifact_id,
            artifact_hash=receipt.artifact_hash,
            dry_run_receipt_id=receipt.receipt_id,
            idempotency_key=idempotency_key,
            source_review_artifact_id=artifact.artifact_id,
            source_gate_decision_id=receipt.source_gate_decision_id,
            source_dry_run_receipt_id=receipt.receipt_id,
            source_execution_journal_record_id=execution_journal_record.journal_record_id if execution_journal_record else "",
            source_refs=list(dict.fromkeys(receipt.source_refs or artifact.source_refs)),
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            reasons=list(dict.fromkeys(reasons)),
        )
        intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_intent(intent)
        if not validation.passed and status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            intent.proposal_boundary_status = "INVALID"
            intent.proposal_workflow_allowed = False
            intent.blockers.extend(validation.issues)
            intent.blockers = list(dict.fromkeys(intent.blockers))
            intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))

        journal_record = self.journal.append_intent(intent)
        self.last_journal_record = journal_record
        self.last_warning = self.journal.last_warning
        return ProposalConfirmationResult(intent=intent, journal_record=journal_record, warning=self.last_warning)


def _empty_receipt(artifact: HumanReviewArtifact) -> DryRunExecutionReceipt:
    return DryRunExecutionReceipt(
        receipt_id="",
        created_at=now_utc_iso(),
        mode="REVIEW_ONLY",
        symbol=artifact.symbol,
        broker_symbol=artifact.broker_symbol,
        dry_run_only=True,
        gate_action="UNKNOWN",
        allowed=False,
        executed=False,
        artifact_id=artifact.artifact_id,
        artifact_hash="",
        idempotency_key="",
        source_refs=list(artifact.source_refs),
    )


def _artifact_age_seconds(created_at: str, now: datetime | None = None) -> float:
    try:
        value = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.0, (current - value).total_seconds())
    except Exception:
        return 999999.0


def _fallback_idempotency_key(artifact: HumanReviewArtifact, receipt: DryRunExecutionReceipt) -> str:
    return hashlib.sha256(f"{artifact.artifact_id}|{receipt.receipt_id}|{artifact.created_at}".encode("utf-8")).hexdigest()


def _intent_id(artifact_id: str, receipt_id: str, idempotency_key: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{artifact_id}|{receipt_id}|{idempotency_key}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"proposal_intent_{digest}"
