from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.models import DryRunExecutionReceipt
from src.services.trading.proposal.intent_journal import ProposalIntentJournalService
from src.services.trading.proposal.models import HumanConfirmedProposalIntent, ProposalIntentJournalRecord, now_utc_iso
from src.services.trading.proposal.policies import ProposalBoundaryPolicy
from src.services.trading.proposal.validator import (
    ProposalBoundaryValidationResult,
    ProposalBoundaryValidator,
)
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

    def review_candidate(
        self,
        candidate_journal: Any,
        candidate_reference: str,
        account_context: Any,
        expected_account_fingerprint: str,
        *,
        operator_action: str,
        user_acknowledgement_text: str = "",
        confirmation_nonce: str = "",
        expected_candidate_reference: str = "",
        now: datetime | None = None,
    ) -> ProposalConfirmationResult:
        from src.services.trading.decision.autonomous_orchestrator import (
            AutonomousDecisionConfig,
            AutonomousDecisionJournalError,
            AutonomousDecisionOrchestrator,
        )
        from src.services.trading.decision.candidate_review import (
            build_autonomous_candidate_review_artifact,
        )

        evaluated_at = _utc(now)
        action = str(operator_action or "").strip().upper()
        if expected_candidate_reference and not hmac.compare_digest(
            str(expected_candidate_reference), str(candidate_reference)
        ):
            return self._blocked_candidate_result(
                candidate_reference, "CANDIDATE_REFERENCE_MISMATCH", evaluated_at
            )
        try:
            candidate = candidate_journal.load_candidate(candidate_reference)
        except AutonomousDecisionJournalError as exc:
            return self._blocked_candidate_result(
                candidate_reference, str(exc), evaluated_at
            )
        if candidate is None:
            return self._blocked_candidate_result(
                candidate_reference, "CANDIDATE_NOT_FOUND", evaluated_at
            )

        candidate_validation = AutonomousDecisionOrchestrator(
            AutonomousDecisionConfig(), journal=candidate_journal
        ).validate_candidate(candidate, now=evaluated_at)
        blockers = list(candidate_validation.issues)
        if (
            candidate.intent != "OPEN_POSITION"
            or candidate.action not in {"MARKET", "PENDING"}
            or candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE"
        ):
            blockers.append("CANDIDATE_NOT_ACTIONABLE")
        blockers.extend(
            _account_context_blockers(
                candidate.account_context_reference,
                account_context,
                expected_account_fingerprint,
                evaluated_at,
                self.policy.intent_ttl_seconds,
            )
        )
        if action not in {"CONFIRM", "REJECT"}:
            blockers.append("OPERATOR_ACTION_INVALID")
        required_phrase = self.policy.confirmation_phrase.strip()
        received_phrase = str(user_acknowledgement_text or "").strip()
        if action == "CONFIRM" and not hmac.compare_digest(required_phrase, received_phrase):
            blockers.append("CONFIRMATION_PHRASE_MISMATCH")
        if blockers:
            return self._blocked_candidate_result(
                candidate_reference,
                blockers[0],
                evaluated_at,
                blockers=blockers,
            )

        review = build_autonomous_candidate_review_artifact(
            candidate, candidate_validation, now=evaluated_at
        )
        nonce = str(confirmation_nonce or secrets.token_hex(16)).strip()
        if not 8 <= len(nonce) <= 128 or any(character.isspace() for character in nonce):
            return self._blocked_candidate_result(
                candidate_reference, "CONFIRMATION_NONCE_INVALID", evaluated_at
            )
        expires_at = evaluated_at + timedelta(seconds=self.policy.intent_ttl_seconds)
        fingerprint_hash = _sha256(
            str(account_context.account_context_fingerprint).strip().lower()
        )
        source_refs = list(candidate_confirmation_source_refs(candidate))
        binding_hash = (
            _candidate_confirmation_binding_hash(
                candidate,
                account_fingerprint_hash=fingerprint_hash,
                operator_action=action,
                confirmation_nonce=nonce,
                confirmation_phrase=received_phrase,
                confirmed_at=evaluated_at.isoformat(),
                expires_at=expires_at.isoformat(),
            )
            if action == "CONFIRM"
            else ""
        )
        confirmed = action == "CONFIRM"
        intent = HumanConfirmedProposalIntent(
            intent_id=_intent_id(
                review.artifact_id,
                candidate.candidate_reference,
                _sha256("candidate-review|" + candidate.candidate_reference),
                evaluated_at.isoformat(),
            ),
            created_at=evaluated_at.isoformat(),
            mode=candidate.operating_mode,
            symbol=candidate.symbol_reference,
            broker_symbol=candidate.broker_symbol_reference,
            proposal_boundary_status=(
                "CONFIRMED_FOR_PROPOSAL_WORKFLOW" if confirmed else "REJECTED"
            ),
            human_confirmation_state=(
                "CONFIRMED_PROPOSAL_WORKFLOW" if confirmed else "REJECTED"
            ),
            proposal_workflow_allowed=confirmed,
            dry_run_only=True,
            executable=False,
            user_acknowledgement_text=received_phrase if confirmed else "",
            confirmation_phrase_required=required_phrase if confirmed else "",
            confirmation_phrase_received=received_phrase if confirmed else "",
            review_status=review.review_status,
            readiness_action=review.readiness_action,
            gate_action="CONFIRMATION_ONLY",
            dry_run_allowed=False,
            dry_run_executed=False,
            artifact_id=review.artifact_id,
            artifact_hash=binding_hash,
            idempotency_key=_sha256("candidate-review|" + candidate.candidate_reference),
            source_review_artifact_id=review.artifact_id,
            candidate_reference=candidate.candidate_reference,
            candidate_provenance_hash=candidate.provenance_hash,
            candidate_structured_order_hash=candidate.structured_order_hash,
            account_context_reference=candidate.account_context_reference,
            account_fingerprint_hash=fingerprint_hash,
            order_type=candidate.order_type,
            timeframe_profile=list(candidate.timeframe_profile),
            operator_action=action,
            confirmation_nonce=nonce,
            confirmation_expires_at=expires_at.isoformat(),
            confirmation_binding_hash=binding_hash,
            source_refs=source_refs,
            reasons=[
                "candidate_confirmation_bound" if confirmed else "candidate_rejected"
            ],
        )
        intent.payload_size_chars = len(
            json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True)
        )
        validation = self.validator.validate_intent(intent)
        if not validation.passed:
            return self._blocked_candidate_result(
                candidate_reference,
                validation.issues[0],
                evaluated_at,
                blockers=validation.issues,
            )
        record, appended = self.journal.append_intent_idempotent(intent)
        self.last_journal_record = record
        self.last_warning = self.journal.last_warning
        if record is None:
            return self._blocked_candidate_result(
                candidate_reference,
                self.last_warning or "PROPOSAL_INTENT_JOURNAL_WRITE_FAILED",
                evaluated_at,
            )
        if not appended:
            intent = _duplicate_candidate_intent(intent, record)
        return ProposalConfirmationResult(
            intent=intent, journal_record=record, warning=self.last_warning
        )

    def validate_candidate_confirmation(
        self,
        intent: HumanConfirmedProposalIntent,
        candidate_journal: Any,
        account_context: Any,
        expected_account_fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> ProposalBoundaryValidationResult:
        from src.services.trading.decision.autonomous_orchestrator import (
            AutonomousDecisionConfig,
            AutonomousDecisionJournalError,
            AutonomousDecisionOrchestrator,
        )

        evaluated_at = _utc(now)
        blockers = list(self.validator.validate_intent(intent).issues)
        try:
            candidate = candidate_journal.load_candidate(intent.candidate_reference)
        except AutonomousDecisionJournalError as exc:
            candidate = None
            blockers.append(str(exc))
        if candidate is None:
            blockers.append("CANDIDATE_NOT_FOUND")
        else:
            blockers.extend(
                AutonomousDecisionOrchestrator(
                    AutonomousDecisionConfig(), journal=candidate_journal
                ).validate_candidate(candidate, now=evaluated_at).issues
            )
            expected = _candidate_confirmation_binding_hash(
                candidate,
                account_fingerprint_hash=intent.account_fingerprint_hash,
                operator_action=intent.operator_action,
                confirmation_nonce=intent.confirmation_nonce,
                confirmation_phrase=intent.confirmation_phrase_received,
                confirmed_at=intent.created_at,
                expires_at=intent.confirmation_expires_at,
            )
            comparisons = (
                (intent.candidate_provenance_hash, candidate.provenance_hash),
                (intent.candidate_structured_order_hash, candidate.structured_order_hash),
                (intent.account_context_reference, candidate.account_context_reference),
                (intent.symbol, candidate.symbol_reference),
                (intent.broker_symbol, candidate.broker_symbol_reference),
                (intent.order_type, candidate.order_type),
                (intent.confirmation_binding_hash, expected),
                (intent.artifact_hash, expected),
            )
            if any(not hmac.compare_digest(str(left), str(right)) for left, right in comparisons):
                blockers.append("CONFIRMATION_CANDIDATE_BINDING_MISMATCH")
            if tuple(intent.timeframe_profile) != candidate.timeframe_profile:
                blockers.append("CONFIRMATION_TIMEFRAME_MISMATCH")
            if tuple(intent.source_refs) != candidate_confirmation_source_refs(candidate):
                blockers.append("CONFIRMATION_SOURCE_BINDING_MISMATCH")
        blockers.extend(
            _account_context_blockers(
                intent.account_context_reference,
                account_context,
                expected_account_fingerprint,
                evaluated_at,
                self.policy.intent_ttl_seconds,
            )
        )
        actual_fingerprint_hash = _sha256(
            str(getattr(account_context, "account_context_fingerprint", ""))
            .strip()
            .lower()
        )
        if not hmac.compare_digest(
            intent.account_fingerprint_hash, actual_fingerprint_hash
        ):
            blockers.append("CONFIRMATION_ACCOUNT_FINGERPRINT_MISMATCH")
        if intent.operator_action != "CONFIRM":
            blockers.append("CONFIRMATION_ACTION_NOT_AFFIRMATIVE")
        if intent.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            blockers.append("PROPOSAL_CONFIRMATION_NOT_GRANTED")
        if intent.human_confirmation_state != "CONFIRMED_PROPOSAL_WORKFLOW":
            blockers.append("HUMAN_CONFIRMATION_NOT_GRANTED")
        if not (
            intent.confirmation_phrase_required
            and hmac.compare_digest(
                intent.confirmation_phrase_required, self.policy.confirmation_phrase
            )
            and hmac.compare_digest(
                intent.confirmation_phrase_received, intent.confirmation_phrase_required
            )
        ):
            blockers.append("CONFIRMATION_PHRASE_INVALID")
        if not _not_expired(intent.confirmation_expires_at, evaluated_at):
            blockers.append("CONFIRMATION_EXPIRED")
        return ProposalBoundaryValidationResult(
            passed=not blockers, issues=list(dict.fromkeys(blockers))
        )

    def _blocked_candidate_result(
        self,
        candidate_reference: str,
        primary_blocker: str,
        now: datetime,
        *,
        blockers: list[str] | tuple[str, ...] = (),
    ) -> ProposalConfirmationResult:
        issues = list(dict.fromkeys((*blockers, primary_blocker)))
        intent = HumanConfirmedProposalIntent(
            intent_id="blocked_candidate_review_" + _sha256(
                f"{candidate_reference}|{now.isoformat()}|{primary_blocker}"
            )[:16],
            created_at=now.isoformat(),
            mode="OFFLINE_REVIEW",
            symbol="",
            broker_symbol="",
            proposal_boundary_status="BLOCKED",
            human_confirmation_state="NOT_REQUESTED",
            proposal_workflow_allowed=False,
            dry_run_only=True,
            executable=False,
            candidate_reference=candidate_reference,
            blockers=issues,
        )
        return ProposalConfirmationResult(intent=intent, warning=primary_blocker)

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


def _candidate_confirmation_binding_hash(
    candidate,
    *,
    account_fingerprint_hash: str,
    operator_action: str,
    confirmation_nonce: str,
    confirmation_phrase: str,
    confirmed_at: str,
    expires_at: str,
) -> str:
    material = {
        "schema": "candidate-confirmation-binding/v1",
        "candidate_reference": candidate.candidate_reference,
        "candidate_provenance_hash": candidate.provenance_hash,
        "candidate_structured_order_hash": candidate.structured_order_hash,
        "source_references": list(candidate_confirmation_source_refs(candidate)),
        "account_context_reference": candidate.account_context_reference,
        "account_fingerprint_hash": account_fingerprint_hash,
        "symbol": candidate.symbol_reference,
        "broker_symbol": candidate.broker_symbol_reference,
        "order_type": candidate.order_type,
        "timeframe_profile": list(candidate.timeframe_profile),
        "operator_action": operator_action,
        "confirmation_nonce": confirmation_nonce,
        "confirmation_phrase_hash": _sha256(confirmation_phrase),
        "confirmed_at": confirmed_at,
        "expires_at": expires_at,
        "execution_permission_state": {
            "execution_authority": False,
            "live_submission_allowed": False,
            "order_send_allowed": False,
            "executable": False,
        },
    }
    return _sha256(
        json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    )


candidate_confirmation_binding_hash = _candidate_confirmation_binding_hash


def candidate_confirmation_source_refs(candidate) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(value)
            for value in (
                candidate.candidate_reference,
                candidate.provenance_hash,
                candidate.structured_order_hash,
                candidate.market_context_reference,
                candidate.market_snapshot_reference,
                candidate.market_snapshot_provenance_hash,
                candidate.reasoning_result_reference,
                candidate.score_result_reference,
                candidate.risk_result_reference,
                candidate.lifecycle_observation_reference,
                candidate.reconciliation_reference,
                candidate.account_context_reference,
                *candidate.proposed_semantic_parameter_references,
                *candidate.knowledge_evidence_references,
            )
            if str(value)
        )
    )


def _account_context_blockers(
    candidate_account_reference: str,
    account_context: Any,
    expected_account_fingerprint: str,
    now: datetime,
    maximum_age_seconds: int,
) -> list[str]:
    blockers: list[str] = []
    fingerprint = str(
        getattr(account_context, "account_context_fingerprint", "") or ""
    ).strip().lower()
    expected = str(expected_account_fingerprint or "").strip().lower()
    account_id_hash = str(getattr(account_context, "account_id_hash", "") or "").strip()
    if (
        getattr(account_context, "status", "") != "OK"
        or getattr(account_context, "redacted", False) is not True
    ):
        blockers.append("ACCOUNT_CONTEXT_INVALID")
    if not _valid_hash(fingerprint) or not _valid_hash(expected):
        blockers.append("ACCOUNT_CONTEXT_FINGERPRINT_INVALID")
    elif not hmac.compare_digest(fingerprint, expected):
        blockers.append("ACCOUNT_CONTEXT_MISMATCH")
    if not _valid_hash(account_id_hash) or not hmac.compare_digest(
        candidate_account_reference,
        "account_context_" + _sha256(account_id_hash)[:24],
    ):
        blockers.append("CANDIDATE_ACCOUNT_CONTEXT_MISMATCH")
    captured_at = _parse_time(str(getattr(account_context, "captured_at", "") or ""))
    if captured_at is None or not 0 <= (now - captured_at).total_seconds() <= maximum_age_seconds:
        blockers.append("ACCOUNT_CONTEXT_STALE")
    return blockers


def _duplicate_candidate_intent(
    current: HumanConfirmedProposalIntent,
    record: ProposalIntentJournalRecord,
) -> HumanConfirmedProposalIntent:
    return replace(
        current,
        intent_id=record.intent_id,
        created_at=record.created_at,
        proposal_boundary_status="DUPLICATE",
        human_confirmation_state=record.human_confirmation_state,
        proposal_workflow_allowed=False,
        artifact_id=record.artifact_id,
        artifact_hash=record.artifact_hash,
        confirmation_nonce=record.confirmation_nonce,
        confirmation_expires_at=record.confirmation_expires_at,
        confirmation_binding_hash=record.confirmation_binding_hash,
        operator_action=record.operator_action,
        source_refs=list(record.source_refs),
        blockers=["DUPLICATE_CANDIDATE_REVIEW"],
        reasons=["authoritative_existing_review_returned"],
    )


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _not_expired(value: str, now: datetime) -> bool:
    expiry = _parse_time(value)
    return expiry is not None and expiry > now


def _valid_hash(value: str) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
