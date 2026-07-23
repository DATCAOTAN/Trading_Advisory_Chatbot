from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_SCHEMA_VERSION,
    AutonomousDecisionCandidate,
    AutonomousDecisionConfig,
    AutonomousDecisionEligibility,
    AutonomousDecisionIntent,
    AutonomousDecisionOrchestrator,
)
from src.services.trading.decision.models import DecisionBlocker, TradeReadinessDecision
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ManagementIntent,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
    MT5LifecycleState,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)


AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION = "autonomous-execution-policy-result/v1"
AUTONOMOUS_POLICY_VERSION = "autonomous-execution-policy/v1"


class AutonomousPolicyDecision(str, Enum):
    BLOCK = "BLOCK"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    ELIGIBLE_FOR_CONTROLLED_BOUNDARY = "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"


class AutonomousControlledBoundary(str, Enum):
    NONE = "NONE"
    CONTROLLED_OPEN_POSITION = "CONTROLLED_OPEN_POSITION"
    CONTROLLED_CANCEL_PENDING_ORDER = "CONTROLLED_CANCEL_PENDING_ORDER"
    CONTROLLED_MODIFY_POSITION_PROTECTION = "CONTROLLED_MODIFY_POSITION_PROTECTION"
    CONTROLLED_CLOSE_POSITION = "CONTROLLED_CLOSE_POSITION"


class AutonomousPolicyJournalError(RuntimeError):
    """Fail-closed policy persistence error with a public-safe reason."""


@dataclass(frozen=True)
class AutonomousExecutionPolicyConfig:
    enabled: bool = False
    open_eligibility_enabled: bool = False
    management_eligibility_enabled: bool = False
    hard_block: bool = True
    allowed_operating_modes: tuple[str, ...] = ("autonomous_candidate",)
    maximum_candidate_age_seconds: int = 300
    journal_path: str = "data/trading/execution_journal/autonomous_policy_decisions.jsonl"
    max_read_records: int = 100

    def __post_init__(self) -> None:
        if self.maximum_candidate_age_seconds <= 0:
            raise ValueError("maximum candidate age must be positive")
        if not self.allowed_operating_modes:
            raise ValueError("at least one operating mode is required")
        if not self.journal_path or self.max_read_records <= 0:
            raise ValueError("policy journal settings are invalid")

    @classmethod
    def from_config(cls) -> "AutonomousExecutionPolicyConfig":
        from src.config import Config

        return cls(
            enabled=Config.TRADING_AUTONOMOUS_POLICY_GATE_ENABLED,
            open_eligibility_enabled=Config.TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED,
            management_eligibility_enabled=Config.TRADING_AUTONOMOUS_MANAGEMENT_ELIGIBILITY_ENABLED,
            hard_block=Config.TRADING_AUTONOMOUS_POLICY_HARD_BLOCK,
            allowed_operating_modes=tuple(Config.TRADING_AUTONOMOUS_POLICY_ALLOWED_MODES),
            maximum_candidate_age_seconds=Config.TRADING_AUTONOMOUS_POLICY_MAX_CANDIDATE_AGE_SECONDS,
            journal_path=Config.TRADING_AUTONOMOUS_POLICY_JOURNAL_PATH,
            max_read_records=Config.TRADING_AUTONOMOUS_POLICY_MAX_READ_RECORDS,
        )


@dataclass(frozen=True)
class AutonomousPolicyInputs:
    candidate: AutonomousDecisionCandidate
    risk_result: TradeReadinessDecision | None
    account_context_reference: str
    account_context_created_at: str
    account_context_matches: bool
    semantic_proposal_complete: bool
    lifecycle_observation: MT5LifecycleObservation | None = None
    reconciliation_result: MT5ReconciliationReceipt | None = None
    management_exposure_effect: str = "NONE"
    requested_close_volume: str = ""
    observed_volume: str = ""


@dataclass(frozen=True)
class AutonomousExecutionPolicyResult:
    schema_version: str
    policy_decision_reference: str
    candidate_reference: str
    candidate_intent: str
    decision: str
    generated_at: str
    expires_at: str
    policy_version: str
    candidate_provenance_hash: str
    lifecycle_reference: str
    reconciliation_reference: str
    account_context_reference: str
    deterministic_reason_codes: tuple[str, ...]
    target_controlled_boundary: str
    policy_hash: str
    policy_idempotency_key: str
    execution_authority: bool = False
    human_confirmation_present: bool = False
    execution_permission_requested: bool = False
    live_submission_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    order_sent: bool = False
    metadata_redacted: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_decision_reference": self.policy_decision_reference,
            "candidate_reference": self.candidate_reference,
            "candidate_intent": self.candidate_intent,
            "decision": self.decision,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "policy_version": self.policy_version,
            "candidate_provenance_hash": self.candidate_provenance_hash,
            "lifecycle_reference_present": bool(self.lifecycle_reference),
            "reconciliation_reference_present": bool(self.reconciliation_reference),
            "account_context_reference_redacted": _redacted_reference(
                self.account_context_reference
            ),
            "deterministic_reason_codes": list(self.deterministic_reason_codes),
            "target_controlled_boundary": self.target_controlled_boundary,
            "policy_hash": self.policy_hash,
            "policy_idempotency_key_hash": _sha256(self.policy_idempotency_key),
            "execution_authority": False,
            "human_confirmation_present": False,
            "execution_permission_requested": False,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "metadata_redacted": True,
        }


@dataclass(frozen=True)
class AutonomousPolicyValidationResult:
    valid: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutonomousPolicyRunResult:
    policy_result: AutonomousExecutionPolicyResult
    validation: AutonomousPolicyValidationResult
    journal_appended: bool
    persistence_safe: bool
    journal_warning: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.policy_result.to_public_dict()
        payload.update(
            {
                "validation_valid": self.validation.valid,
                "journal_appended": self.journal_appended,
                "persistence_safe": self.persistence_safe,
                "journal_warning": self.journal_warning,
            }
        )
        return payload


class AutonomousPolicyJournal:
    _process_lock = threading.Lock()
    _required_keys = {
        "record_type",
        "policy_decision_reference",
        "candidate_reference",
        "candidate_provenance_hash",
        "policy_hash",
        "policy_idempotency_key",
        "decision",
        "target_controlled_boundary",
        "reason_codes",
        "lifecycle_reference",
        "reconciliation_reference",
        "account_context_reference",
        "generated_at",
        "expires_at",
        "execution_authority",
        "human_confirmation_present",
        "execution_permission_requested",
        "live_submission_allowed",
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "order_sent",
        "metadata_redacted",
        "record_hash",
    }

    def __init__(self, path: str | Path, max_read_records: int = 100):
        self.path = Path(path)
        self.max_read_records = max_read_records
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AutonomousPolicyJournalError("POLICY_JOURNAL_UNAVAILABLE") from exc
        records: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AutonomousPolicyJournalError("POLICY_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict) or set(row) != self._required_keys:
                raise AutonomousPolicyJournalError("POLICY_JOURNAL_CORRUPT")
            if not _journal_row_valid(row):
                raise AutonomousPolicyJournalError("POLICY_JOURNAL_CORRUPT")
            key = str(row["policy_idempotency_key"])
            policy_hash = str(row["policy_hash"])
            if key in seen and not hmac.compare_digest(seen[key], policy_hash):
                raise AutonomousPolicyJournalError("POLICY_JOURNAL_CONFLICT")
            seen[key] = policy_hash
            records.append(row)
        return records[-self.max_read_records :]

    def append_idempotent(self, result: AutonomousExecutionPolicyResult) -> bool:
        with self._exclusive_lock():
            for row in self.records():
                if hmac.compare_digest(
                    str(row["policy_idempotency_key"]), result.policy_idempotency_key
                ):
                    if not hmac.compare_digest(str(row["policy_hash"]), result.policy_hash):
                        raise AutonomousPolicyJournalError("POLICY_JOURNAL_CONFLICT")
                    return False
            row = _journal_row(result)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise AutonomousPolicyJournalError("POLICY_JOURNAL_UNAVAILABLE") from exc
            return True

    def _exclusive_lock(self):
        journal = self

        class LockContext:
            def __enter__(self):
                journal._process_lock.acquire()
                journal.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.fd = os.open(journal.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except (FileExistsError, OSError) as exc:
                    journal._process_lock.release()
                    raise AutonomousPolicyJournalError("POLICY_JOURNAL_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    journal.lock_path.unlink()
                finally:
                    journal._process_lock.release()

        return LockContext()


class AutonomousExecutionPolicyGate:
    def __init__(
        self,
        config: AutonomousExecutionPolicyConfig | None = None,
        journal: AutonomousPolicyJournal | None = None,
    ):
        self.config = config or AutonomousExecutionPolicyConfig.from_config()
        self.journal = journal or AutonomousPolicyJournal(
            self.config.journal_path, self.config.max_read_records
        )

    def evaluate_candidate(
        self,
        inputs: AutonomousPolicyInputs,
        *,
        now: datetime | None = None,
        forced_reasons: Sequence[str] = (),
    ) -> AutonomousExecutionPolicyResult:
        evaluated_at = _utc(now)
        reasons = _policy_reasons(inputs, self.config, evaluated_at)
        reasons.extend(str(reason) for reason in forced_reasons if reason)
        decision, target, terminal_reason = _policy_decision(inputs, self.config, reasons)
        if terminal_reason:
            reasons.append(terminal_reason)
        reason_codes = tuple(sorted(set(reasons)))
        canonical = _canonical_policy_inputs(
            inputs,
            self.config,
            decision=decision,
            target=target,
            reason_codes=reason_codes,
        )
        policy_hash = _sha256(_canonical_json(canonical))
        policy_reference = "autonomous_policy_" + policy_hash[:24]
        idempotency_key = _sha256("autonomous-policy/v1|" + policy_hash)
        generated_at = evaluated_at.isoformat()
        candidate_expiry = _parse_datetime(inputs.candidate.expires_at)
        fallback_expiry = evaluated_at + timedelta(
            seconds=self.config.maximum_candidate_age_seconds
        )
        expires_at = min(candidate_expiry or fallback_expiry, fallback_expiry).isoformat()
        return AutonomousExecutionPolicyResult(
            schema_version=AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION,
            policy_decision_reference=policy_reference,
            candidate_reference=inputs.candidate.candidate_reference,
            candidate_intent=inputs.candidate.intent,
            decision=decision.value,
            generated_at=generated_at,
            expires_at=expires_at,
            policy_version=AUTONOMOUS_POLICY_VERSION,
            candidate_provenance_hash=inputs.candidate.provenance_hash,
            lifecycle_reference=inputs.candidate.lifecycle_observation_reference,
            reconciliation_reference=inputs.candidate.reconciliation_reference,
            account_context_reference=inputs.account_context_reference,
            deterministic_reason_codes=reason_codes,
            target_controlled_boundary=target.value,
            policy_hash=policy_hash,
            policy_idempotency_key=idempotency_key,
        )

    def validate_policy_result(
        self,
        result: AutonomousExecutionPolicyResult,
        *,
        now: datetime | None = None,
    ) -> AutonomousPolicyValidationResult:
        issues: list[str] = []
        if result.schema_version != AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION:
            issues.append("INVALID_POLICY_SCHEMA_VERSION")
        if result.policy_version != AUTONOMOUS_POLICY_VERSION:
            issues.append("INVALID_POLICY_VERSION")
        if result.decision not in {item.value for item in AutonomousPolicyDecision}:
            issues.append("INVALID_POLICY_DECISION")
        if result.target_controlled_boundary not in {
            item.value for item in AutonomousControlledBoundary
        }:
            issues.append("INVALID_CONTROLLED_BOUNDARY")
        for name in (
            "policy_decision_reference",
            "candidate_reference",
            "candidate_intent",
            "generated_at",
            "expires_at",
            "candidate_provenance_hash",
            "lifecycle_reference",
            "account_context_reference",
            "policy_hash",
            "policy_idempotency_key",
        ):
            if not str(getattr(result, name) or "").strip():
                issues.append("MISSING_" + name.upper())
        if not _valid_hash(result.candidate_provenance_hash):
            issues.append("INVALID_CANDIDATE_PROVENANCE_HASH")
        if not _valid_hash(result.policy_hash):
            issues.append("INVALID_POLICY_HASH")
        if result.policy_decision_reference != "autonomous_policy_" + result.policy_hash[:24]:
            issues.append("INVALID_POLICY_REFERENCE")
        expected_idempotency = _sha256("autonomous-policy/v1|" + result.policy_hash)
        if not hmac.compare_digest(result.policy_idempotency_key, expected_idempotency):
            issues.append("INVALID_POLICY_IDEMPOTENCY_KEY")
        if _expired(result.expires_at, _utc(now)):
            issues.append("POLICY_RESULT_EXPIRED")
        if result.decision != AutonomousPolicyDecision.ELIGIBLE_FOR_CONTROLLED_BOUNDARY.value:
            if result.target_controlled_boundary != AutonomousControlledBoundary.NONE.value:
                issues.append("NON_ELIGIBLE_TARGET_MUST_BE_NONE")
        elif result.target_controlled_boundary == AutonomousControlledBoundary.NONE.value:
            issues.append("ELIGIBLE_TARGET_REQUIRED")
        if any(
            (
                result.execution_authority,
                result.human_confirmation_present,
                result.execution_permission_requested,
                result.live_submission_allowed,
                result.live_execution_allowed,
                result.order_send_allowed,
                result.execution_allowed,
                result.executable,
                result.order_sent,
            )
        ):
            issues.append("EXECUTION_AUTHORITY_NOT_ALLOWED")
        if result.metadata_redacted is not True:
            issues.append("METADATA_NOT_REDACTED")
        return AutonomousPolicyValidationResult(valid=not issues, issues=tuple(sorted(set(issues))))

    def run_once(
        self, inputs: AutonomousPolicyInputs, *, now: datetime | None = None
    ) -> AutonomousPolicyRunResult:
        persistence_safe = True
        warning = ""
        forced: tuple[str, ...] = ()
        try:
            self.journal.records()
        except AutonomousPolicyJournalError as exc:
            persistence_safe = False
            warning = str(exc)
            forced = (str(exc),)
        result = self.evaluate_candidate(inputs, now=now, forced_reasons=forced)
        validation = self.validate_policy_result(result, now=now)
        appended = False
        if validation.valid and persistence_safe:
            try:
                appended = self.journal.append_idempotent(result)
            except AutonomousPolicyJournalError as exc:
                persistence_safe = False
                warning = str(exc)
                result = self.evaluate_candidate(
                    inputs, now=now, forced_reasons=(str(exc),)
                )
                validation = self.validate_policy_result(result, now=now)
        return AutonomousPolicyRunResult(
            policy_result=result,
            validation=validation,
            journal_appended=appended,
            persistence_safe=persistence_safe,
            journal_warning=warning,
        )


def autonomous_policy_inputs_from_mapping(payload: Mapping[str, Any]) -> AutonomousPolicyInputs:
    candidate_data = dict(_required_mapping(payload, "candidate"))
    for name in (
        "proposed_semantic_parameter_references",
        "knowledge_evidence_references",
        "blocked_reason_codes",
    ):
        candidate_data[name] = tuple(candidate_data.get(name, ()))
    candidate = _construct(AutonomousDecisionCandidate, candidate_data)
    risk_data = payload.get("risk_result")
    if isinstance(risk_data, Mapping):
        typed_risk = dict(risk_data)
        typed_risk["blockers"] = [
            _construct(DecisionBlocker, item)
            for item in typed_risk.get("blockers", [])
            if isinstance(item, Mapping)
        ]
        risk = _construct(TradeReadinessDecision, typed_risk)
    else:
        risk = None
    observation_data = payload.get("lifecycle_observation")
    observation = (
        _construct(MT5LifecycleObservation, observation_data)
        if isinstance(observation_data, Mapping)
        else None
    )
    reconciliation_data = payload.get("reconciliation_result")
    reconciliation = (
        MT5ReconciliationReceipt.from_payload(reconciliation_data)
        if isinstance(reconciliation_data, Mapping)
        else None
    )
    return AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=risk,
        account_context_reference=str(payload.get("account_context_reference", "")),
        account_context_created_at=str(payload.get("account_context_created_at", "")),
        account_context_matches=payload.get("account_context_matches") is True,
        semantic_proposal_complete=payload.get("semantic_proposal_complete") is True,
        lifecycle_observation=observation,
        reconciliation_result=reconciliation,
        management_exposure_effect=str(payload.get("management_exposure_effect", "NONE")),
        requested_close_volume=str(payload.get("requested_close_volume", "")),
        observed_volume=str(payload.get("observed_volume", "")),
    )


def _policy_reasons(
    inputs: AutonomousPolicyInputs,
    config: AutonomousExecutionPolicyConfig,
    now: datetime,
) -> list[str]:
    candidate = inputs.candidate
    reasons: list[str] = []
    if not config.enabled:
        reasons.append("POLICY_GATE_DISABLED")
    if config.hard_block:
        reasons.append("POLICY_HARD_BLOCK")
    if candidate.operating_mode not in config.allowed_operating_modes:
        reasons.append("OPERATING_MODE_NOT_ALLOWED")
    if candidate.schema_version != AUTONOMOUS_DECISION_SCHEMA_VERSION:
        reasons.append("CANDIDATE_INVALID")
    candidate_validation = AutonomousDecisionOrchestrator(
        config=AutonomousDecisionConfig()
    ).validate_candidate(candidate, now=now)
    if not candidate_validation.valid:
        reasons.append("CANDIDATE_INVALID")
    if _expired(candidate.expires_at, now) or not _fresh(
        candidate.generated_at, now, config.maximum_candidate_age_seconds
    ):
        reasons.append("CANDIDATE_STALE_OR_EXPIRED")
    if not _candidate_integrity_valid(candidate):
        reasons.append("CANDIDATE_PROVENANCE_INVALID")
    if any(
        (
            candidate.execution_authority,
            candidate.human_confirmation_present,
            candidate.execution_permission_requested,
            candidate.live_submission_allowed,
            candidate.live_execution_allowed,
            candidate.order_send_allowed,
            candidate.execution_allowed,
            candidate.executable,
            candidate.order_sent,
        )
    ):
        reasons.append("CANDIDATE_EXECUTION_AUTHORITY_PRESENT")
    if not all(
        (
            candidate.candidate_reference,
            candidate.market_context_reference,
            candidate.reasoning_result_reference,
            candidate.score_result_reference,
            candidate.risk_result_reference,
            candidate.lifecycle_observation_reference,
        )
    ):
        reasons.append("REQUIRED_STRUCTURED_REFERENCE_MISSING")
    risk = inputs.risk_result
    if risk is None or not risk.decision_id:
        reasons.append("RISK_RESULT_UNAVAILABLE")
    elif risk.action == "BLOCKED" or risk.blockers:
        reasons.append("RISK_RESULT_BLOCKED")
    elif not hmac.compare_digest(risk.decision_id, candidate.risk_result_reference):
        reasons.append("RISK_RESULT_REFERENCE_MISMATCH")
    if not _valid_hash(inputs.account_context_reference):
        reasons.append("ACCOUNT_CONTEXT_REFERENCE_INVALID")
    if not inputs.account_context_matches:
        reasons.append("ACCOUNT_CONTEXT_CHANGED")
    if not _fresh(
        inputs.account_context_created_at, now, config.maximum_candidate_age_seconds
    ):
        reasons.append("ACCOUNT_CONTEXT_STALE")
    reasons.extend(_candidate_blocker_reasons(candidate.blocked_reason_codes))
    reasons.extend(_reconciliation_reasons(inputs))
    reasons.extend(_lifecycle_reasons(inputs, config, now))
    if any(
        marker in str(value).lower()
        for value in candidate.proposed_semantic_parameter_references
        for marker in ("averaging_down", "martingale", "grid_strategy", "recovery_trade")
    ):
        reasons.append("PROHIBITED_EXPOSURE_BEHAVIOR")
    if candidate.intent in {
        MT5ManagementIntent.CANCEL_PENDING_ORDER.value,
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
        MT5ManagementIntent.CLOSE_POSITION.value,
    } and inputs.management_exposure_effect.upper() not in {"NONE", "UNCHANGED", "REDUCE"}:
        reasons.append("EXPOSURE_INCREASE_NOT_ALLOWED")
    if candidate.intent == MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value:
        if inputs.management_exposure_effect.upper() != "UNCHANGED":
            reasons.append("EXPOSURE_INCREASE_NOT_ALLOWED")
        if inputs.requested_close_volume and inputs.observed_volume:
            if not _decimal_equal(inputs.requested_close_volume, inputs.observed_volume):
                reasons.append("VOLUME_INCREASE_NOT_ALLOWED")
    if candidate.intent == MT5ManagementIntent.CLOSE_POSITION.value:
        if inputs.management_exposure_effect.upper() != "REDUCE" or not _valid_close_volume(
            inputs.requested_close_volume, inputs.observed_volume
        ):
            reasons.append("CLOSE_VOLUME_INVALID")
    if candidate.intent not in {item.value for item in AutonomousDecisionIntent}:
        reasons.append("INTENT_UNSUPPORTED")
    return reasons


def _policy_decision(
    inputs: AutonomousPolicyInputs,
    config: AutonomousExecutionPolicyConfig,
    reasons: Sequence[str],
) -> tuple[AutonomousPolicyDecision, AutonomousControlledBoundary, str]:
    candidate = inputs.candidate
    if reasons:
        return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, ""
    if candidate.intent == AutonomousDecisionIntent.NO_ACTION.value:
        return (
            AutonomousPolicyDecision.BLOCK,
            AutonomousControlledBoundary.NONE,
            "NO_ACTION_TERMINAL",
        )
    if candidate.intent == AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW.value:
        return (
            AutonomousPolicyDecision.REQUIRE_HUMAN_REVIEW,
            AutonomousControlledBoundary.NONE,
            "HUMAN_REVIEW_REQUIRED",
        )
    if (
        candidate.deterministic_eligibility_result
        != AutonomousDecisionEligibility.ELIGIBLE_CANDIDATE.value
    ):
        return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "CANDIDATE_NOT_ELIGIBLE"
    if candidate.intent == AutonomousDecisionIntent.OPEN_POSITION.value:
        if not config.open_eligibility_enabled:
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "OPEN_ELIGIBILITY_DISABLED"
        if not inputs.semantic_proposal_complete or not candidate.proposed_semantic_parameter_references:
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "SEMANTIC_PROPOSAL_INCOMPLETE"
        if inputs.risk_result is None or inputs.risk_result.action != "REVIEW_READY":
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "OPEN_POLICY_NOT_READY"
        return (
            AutonomousPolicyDecision.ELIGIBLE_FOR_CONTROLLED_BOUNDARY,
            AutonomousControlledBoundary.CONTROLLED_OPEN_POSITION,
            "",
        )
    mapping = {
        MT5ManagementIntent.CANCEL_PENDING_ORDER.value: AutonomousControlledBoundary.CONTROLLED_CANCEL_PENDING_ORDER,
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value: AutonomousControlledBoundary.CONTROLLED_MODIFY_POSITION_PROTECTION,
        MT5ManagementIntent.CLOSE_POSITION.value: AutonomousControlledBoundary.CONTROLLED_CLOSE_POSITION,
    }
    if candidate.intent in mapping:
        if not config.management_eligibility_enabled:
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "MANAGEMENT_ELIGIBILITY_DISABLED"
        if inputs.risk_result is None or inputs.risk_result.action != "MANAGE_EXISTING_POSITION":
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "MANAGEMENT_POLICY_NOT_READY"
        if candidate.intent != MT5ManagementIntent.CANCEL_PENDING_ORDER.value and (
            not inputs.semantic_proposal_complete
            or not candidate.proposed_semantic_parameter_references
        ):
            return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "SEMANTIC_PROPOSAL_INCOMPLETE"
        return AutonomousPolicyDecision.ELIGIBLE_FOR_CONTROLLED_BOUNDARY, mapping[candidate.intent], ""
    return AutonomousPolicyDecision.BLOCK, AutonomousControlledBoundary.NONE, "INTENT_UNSUPPORTED"


def _candidate_blocker_reasons(blockers: Sequence[str]) -> list[str]:
    hard_blockers = {
        "STALE_MARKET_CONTEXT",
        "RISK_RESULT_UNAVAILABLE",
        "RISK_RESULT_BLOCKED",
        "SCORING_RESULT_BLOCKED",
        "LIFECYCLE_UNAVAILABLE",
        "LIFECYCLE_AMBIGUOUS",
        "LIFECYCLE_STALE",
        "ACCOUNT_CONTEXT_MISMATCH",
        "RECONCILIATION_UNRESOLVED",
        "DECISION_JOURNAL_CORRUPT",
        "DECISION_JOURNAL_CONFLICT",
        "DECISION_JOURNAL_UNAVAILABLE",
        "UNSUPPORTED_INTENT",
        "UNSUPPORTED_SYMBOL",
        "EXPOSURE_INCREASE_NOT_ALLOWED",
        "PROHIBITED_EXPOSURE_BEHAVIOR",
    }
    return sorted(set(blockers) & hard_blockers)


def _reconciliation_reasons(inputs: AutonomousPolicyInputs) -> list[str]:
    candidate = inputs.candidate
    reconciliation = inputs.reconciliation_result
    if candidate.reconciliation_reference and reconciliation is None:
        return ["RECONCILIATION_RESULT_MISSING"]
    if reconciliation is None:
        return []
    reasons: list[str] = []
    if not hmac.compare_digest(
        reconciliation.reconciliation_reference, candidate.reconciliation_reference
    ):
        reasons.append("RECONCILIATION_REFERENCE_MISMATCH")
    if (
        reconciliation.resulting_execution_state == "RESULT_UNKNOWN"
        or reconciliation.status not in {"CONFIRMED", "REJECTED", "NO_MATCH"}
        or reconciliation.evidence_classification
        in {"AMBIGUOUS_MATCH", "QUERY_FAILED", "RESULT_UNKNOWN", "PENDING"}
    ):
        reasons.append("RECONCILIATION_UNRESOLVED")
    return reasons


def _lifecycle_reasons(
    inputs: AutonomousPolicyInputs,
    config: AutonomousExecutionPolicyConfig,
    now: datetime,
) -> list[str]:
    candidate = inputs.candidate
    observation = inputs.lifecycle_observation
    management = candidate.intent in {
        MT5ManagementIntent.CANCEL_PENDING_ORDER.value,
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value,
        MT5ManagementIntent.CLOSE_POSITION.value,
    }
    if not management:
        if candidate.lifecycle_status in {
            MT5LifecycleState.ORDER_ACTIVE.value,
            MT5LifecycleState.POSITION_OPEN.value,
            MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
        }:
            return ["LIFECYCLE_TARGET_CONFLICT"]
        if candidate.lifecycle_status in {
            MT5LifecycleState.UNKNOWN.value,
            MT5LifecycleState.SUBMISSION_PENDING.value,
            MT5LifecycleState.RECONCILIATION_REQUIRED.value,
            MT5LifecycleState.INCONSISTENT.value,
        }:
            return ["LIFECYCLE_AMBIGUOUS"]
        return []
    if observation is None:
        return ["LIFECYCLE_OBSERVATION_MISSING"]
    reasons: list[str] = []
    if not hmac.compare_digest(
        observation.observation_id, candidate.lifecycle_observation_reference
    ):
        reasons.append("LIFECYCLE_REFERENCE_MISMATCH")
    if not _fresh(
        observation.observation_timestamp, now, config.maximum_candidate_age_seconds
    ):
        reasons.append("LIFECYCLE_STALE")
    if observation.discrepancy_reason:
        reasons.append("LIFECYCLE_AMBIGUOUS")
    references = observation.protected_broker_references
    if candidate.intent == MT5ManagementIntent.CANCEL_PENDING_ORDER.value:
        if (
            observation.lifecycle_state != MT5LifecycleState.ORDER_ACTIVE.value
            or len(references.get("orders", [])) != 1
            or references.get("positions", [])
        ):
            reasons.append("LIFECYCLE_TARGET_INVALID")
    else:
        if (
            observation.lifecycle_state
            not in {
                MT5LifecycleState.POSITION_OPEN.value,
                MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
            }
            or len(references.get("positions", [])) != 1
        ):
            reasons.append("LIFECYCLE_TARGET_INVALID")
    return reasons


def _candidate_integrity_valid(candidate: AutonomousDecisionCandidate) -> bool:
    if not _valid_hash(candidate.provenance_hash):
        return False
    if candidate.candidate_reference != "autonomous_decision_" + candidate.provenance_hash[:24]:
        return False
    expected = _sha256("autonomous-decision/v1|" + candidate.provenance_hash)
    return hmac.compare_digest(candidate.decision_idempotency_key, expected)


def _canonical_policy_inputs(
    inputs: AutonomousPolicyInputs,
    config: AutonomousExecutionPolicyConfig,
    *,
    decision: AutonomousPolicyDecision,
    target: AutonomousControlledBoundary,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    candidate = inputs.candidate
    risk = inputs.risk_result
    observation = inputs.lifecycle_observation
    reconciliation = inputs.reconciliation_result
    return {
        "schema": AUTONOMOUS_POLICY_RESULT_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_POLICY_VERSION,
        "candidate_reference": candidate.candidate_reference,
        "candidate_provenance_hash": candidate.provenance_hash,
        "candidate_intent": candidate.intent,
        "candidate_eligibility": candidate.deterministic_eligibility_result,
        "candidate_blocked_reason_codes": sorted(set(candidate.blocked_reason_codes)),
        "candidate_semantic_references": sorted(
            set(candidate.proposed_semantic_parameter_references)
        ),
        "candidate_lifecycle_reference": candidate.lifecycle_observation_reference,
        "candidate_lifecycle_status": candidate.lifecycle_status,
        "candidate_reconciliation_reference": candidate.reconciliation_reference,
        "risk_reference": risk.decision_id if risk else "",
        "risk_action": risk.action if risk else "",
        "risk_blockers": sorted(item.code for item in risk.blockers) if risk else [],
        "account_context_reference": inputs.account_context_reference,
        "account_context_matches": inputs.account_context_matches,
        "semantic_proposal_complete": inputs.semantic_proposal_complete,
        "lifecycle_observation_hash": observation.observation_hash if observation else "",
        "lifecycle_state": observation.lifecycle_state if observation else "",
        "reconciliation_status": reconciliation.status if reconciliation else "",
        "reconciliation_state": (
            reconciliation.resulting_execution_state if reconciliation else ""
        ),
        "management_exposure_effect": inputs.management_exposure_effect.upper(),
        "requested_close_volume": inputs.requested_close_volume,
        "observed_volume": inputs.observed_volume,
        "config": {
            "enabled": config.enabled,
            "open_eligibility_enabled": config.open_eligibility_enabled,
            "management_eligibility_enabled": config.management_eligibility_enabled,
            "hard_block": config.hard_block,
            "allowed_operating_modes": sorted(config.allowed_operating_modes),
            "maximum_candidate_age_seconds": config.maximum_candidate_age_seconds,
        },
        "decision": decision.value,
        "target": target.value,
        "reason_codes": sorted(set(reason_codes)),
    }


def _journal_row(result: AutonomousExecutionPolicyResult) -> dict[str, Any]:
    row = {
        "record_type": "AUTONOMOUS_EXECUTION_POLICY_RESULT",
        "policy_decision_reference": result.policy_decision_reference,
        "candidate_reference": result.candidate_reference,
        "candidate_provenance_hash": result.candidate_provenance_hash,
        "policy_hash": result.policy_hash,
        "policy_idempotency_key": result.policy_idempotency_key,
        "decision": result.decision,
        "target_controlled_boundary": result.target_controlled_boundary,
        "reason_codes": list(result.deterministic_reason_codes),
        "lifecycle_reference": result.lifecycle_reference,
        "reconciliation_reference": result.reconciliation_reference,
        "account_context_reference": result.account_context_reference,
        "generated_at": result.generated_at,
        "expires_at": result.expires_at,
        "execution_authority": False,
        "human_confirmation_present": False,
        "execution_permission_requested": False,
        "live_submission_allowed": False,
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "executable": False,
        "order_sent": False,
        "metadata_redacted": True,
    }
    row["record_hash"] = _sha256(_canonical_json(row))
    return row


def _journal_row_valid(row: Mapping[str, Any]) -> bool:
    if row.get("record_type") != "AUTONOMOUS_EXECUTION_POLICY_RESULT":
        return False
    if row.get("decision") not in {item.value for item in AutonomousPolicyDecision}:
        return False
    if row.get("target_controlled_boundary") not in {
        item.value for item in AutonomousControlledBoundary
    }:
        return False
    for name in (
        "execution_authority",
        "human_confirmation_present",
        "execution_permission_requested",
        "live_submission_allowed",
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "order_sent",
    ):
        if row.get(name) is not False:
            return False
    if row.get("metadata_redacted") is not True:
        return False
    expected = dict(row)
    actual_hash = str(expected.pop("record_hash", ""))
    return _valid_hash(actual_hash) and hmac.compare_digest(
        actual_hash, _sha256(_canonical_json(expected))
    )


def _valid_close_volume(requested: str, observed: str) -> bool:
    try:
        close_volume = Decimal(str(requested))
        observed_volume = Decimal(str(observed))
    except InvalidOperation:
        return False
    return close_volume > 0 and observed_volume > 0 and close_volume <= observed_volume


def _decimal_equal(first: str, second: str) -> bool:
    try:
        return Decimal(str(first)) == Decimal(str(second))
    except InvalidOperation:
        return False


def _construct(cls, payload: Mapping[str, Any]):
    allowed = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in payload.items() if key in allowed})


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _fresh(value: str, now: datetime, max_age_seconds: int) -> bool:
    parsed = _parse_datetime(value)
    return bool(
        parsed
        and parsed <= now + timedelta(seconds=5)
        and now - parsed <= timedelta(seconds=max_age_seconds)
    )


def _expired(value: str, now: datetime) -> bool:
    parsed = _parse_datetime(value)
    return parsed is None or parsed <= now


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(timezone.utc)
    if selected.tzinfo is None:
        selected = selected.replace(tzinfo=timezone.utc)
    return selected.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_hash(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def _redacted_reference(value: str) -> str:
    return value[:12] + "..." if value else ""
