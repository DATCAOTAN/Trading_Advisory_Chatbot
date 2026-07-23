from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.services.trading.decision.models import DecisionBlocker, TradeReadinessDecision
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
    MT5LifecycleState,
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport


AUTONOMOUS_DECISION_SCHEMA_VERSION = "autonomous-decision-candidate/v1"


class AutonomousDecisionIntent(str, Enum):
    NO_ACTION = "NO_ACTION"
    OPEN_POSITION = "OPEN_POSITION"
    CANCEL_PENDING_ORDER = "CANCEL_PENDING_ORDER"
    MODIFY_POSITION_PROTECTION = "MODIFY_POSITION_PROTECTION"
    CLOSE_POSITION = "CLOSE_POSITION"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"


class AutonomousDecisionEligibility(str, Enum):
    ELIGIBLE_CANDIDATE = "ELIGIBLE_CANDIDATE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class AutonomousDecisionJournalError(RuntimeError):
    """Fail-closed decision persistence error with a public-safe reason."""


@dataclass(frozen=True)
class AutonomousDecisionConfig:
    enabled: bool = True
    ttl_seconds: int = 300
    input_max_age_seconds: int = 300
    journal_path: str = "data/trading/execution_journal/autonomous_decisions.jsonl"
    max_read_records: int = 100

    def __post_init__(self) -> None:
        if self.ttl_seconds <= 0 or self.input_max_age_seconds <= 0:
            raise ValueError("decision TTL and input freshness must be positive")
        if self.max_read_records <= 0:
            raise ValueError("decision journal read limit must be positive")
        if not self.journal_path:
            raise ValueError("decision journal path is required")

    @classmethod
    def from_config(cls) -> "AutonomousDecisionConfig":
        from src.config import Config

        return cls(
            enabled=Config.TRADING_AUTONOMOUS_DECISION_ENABLED,
            ttl_seconds=Config.TRADING_AUTONOMOUS_DECISION_TTL_SECONDS,
            input_max_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
            journal_path=Config.TRADING_AUTONOMOUS_DECISION_JOURNAL_PATH,
            max_read_records=Config.TRADING_AUTONOMOUS_DECISION_MAX_READ_RECORDS,
        )


@dataclass(frozen=True)
class AutonomousDecisionInputs:
    runtime_context: RuntimeContextPack
    method_selection: MethodSelectionResult
    score_report: SignalScoreReport
    risk_result: TradeReadinessDecision | None
    lifecycle_status: MT5RuntimeSupervisorStatus
    lifecycle_observation: MT5LifecycleObservation | None = None
    reconciliation_result: MT5ReconciliationReceipt | None = None
    requested_intent: str = "AUTO"
    direction: str = ""
    semantic_parameter_references: tuple[str, ...] = ()
    exposure_effect: str = "NONE"


@dataclass(frozen=True)
class AutonomousDecisionCandidate:
    schema_version: str
    candidate_reference: str
    generated_at: str
    expires_at: str
    operating_mode: str
    symbol_reference: str
    intent: str
    direction: str
    proposed_semantic_parameter_references: tuple[str, ...]
    market_context_reference: str
    knowledge_evidence_references: tuple[str, ...]
    reasoning_result_reference: str
    score_result_reference: str
    risk_result_reference: str
    lifecycle_observation_reference: str
    lifecycle_status: str
    reconciliation_reference: str
    confidence_category: str
    deterministic_eligibility_result: str
    blocked_reason_codes: tuple[str, ...]
    provenance_hash: str
    decision_idempotency_key: str
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
            "candidate_reference": self.candidate_reference,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "operating_mode": self.operating_mode,
            "symbol_reference": self.symbol_reference,
            "intent": self.intent,
            "direction_present": bool(self.direction),
            "semantic_parameter_reference_count": len(self.proposed_semantic_parameter_references),
            "market_context_reference": self.market_context_reference,
            "knowledge_evidence_reference_count": len(self.knowledge_evidence_references),
            "reasoning_result_reference": self.reasoning_result_reference,
            "score_result_reference": self.score_result_reference,
            "risk_result_reference": self.risk_result_reference,
            "lifecycle_observation_reference": self.lifecycle_observation_reference,
            "lifecycle_status": self.lifecycle_status,
            "reconciliation_reference": self.reconciliation_reference,
            "confidence_category": self.confidence_category,
            "deterministic_eligibility_result": self.deterministic_eligibility_result,
            "blocked_reason_codes": list(self.blocked_reason_codes),
            "provenance_hash": self.provenance_hash,
            "decision_idempotency_key_hash": _sha256(self.decision_idempotency_key),
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
class AutonomousDecisionValidationResult:
    valid: bool
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutonomousDecisionRunResult:
    candidate: AutonomousDecisionCandidate
    validation: AutonomousDecisionValidationResult
    journal_appended: bool
    persistence_safe: bool
    journal_warning: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.candidate.to_public_dict()
        payload.update(
            {
                "validation_valid": self.validation.valid,
                "journal_appended": self.journal_appended,
                "persistence_safe": self.persistence_safe,
                "journal_warning": self.journal_warning,
            }
        )
        return payload


class AutonomousDecisionJournal:
    _process_lock = threading.Lock()
    _required_keys = {
        "record_type",
        "candidate_reference",
        "provenance_hash",
        "decision_idempotency_key",
        "generated_at",
        "expires_at",
        "intent",
        "eligibility_result",
        "blocked_reason_codes",
        "input_references",
        "lifecycle_reference",
        "reconciliation_reference",
        "confidence_category",
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
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_UNAVAILABLE") from exc
        records: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict) or set(row) != self._required_keys:
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
            if not _journal_row_valid(row):
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
            key = str(row["decision_idempotency_key"])
            provenance = str(row["provenance_hash"])
            if key in seen and not hmac.compare_digest(seen[key], provenance):
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
            seen[key] = provenance
            records.append(row)
        return records[-self.max_read_records :]

    def append_idempotent(self, candidate: AutonomousDecisionCandidate) -> bool:
        with self._exclusive_lock():
            for row in self.records():
                if hmac.compare_digest(
                    str(row["decision_idempotency_key"]), candidate.decision_idempotency_key
                ):
                    if not hmac.compare_digest(str(row["provenance_hash"]), candidate.provenance_hash):
                        raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
                    return False
            row = _journal_row(candidate)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_UNAVAILABLE") from exc
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
                    raise AutonomousDecisionJournalError("DECISION_JOURNAL_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    journal.lock_path.unlink()
                finally:
                    journal._process_lock.release()

        return LockContext()


class AutonomousDecisionOrchestrator:
    def __init__(
        self,
        config: AutonomousDecisionConfig | None = None,
        journal: AutonomousDecisionJournal | None = None,
    ):
        self.config = config or AutonomousDecisionConfig.from_config()
        self.journal = journal or AutonomousDecisionJournal(
            self.config.journal_path, self.config.max_read_records
        )

    def build_candidate(
        self,
        inputs: AutonomousDecisionInputs,
        *,
        now: datetime | None = None,
        forced_blockers: Sequence[str] = (),
    ) -> AutonomousDecisionCandidate:
        evaluated_at = _utc(now)
        blockers = _input_blockers(inputs, evaluated_at, self.config)
        blockers.extend(str(item) for item in forced_blockers if item)
        intent, eligibility = _classify(inputs, blockers)
        blockers = sorted(set(blockers))
        confidence = _confidence_category(inputs, intent)
        lifecycle_reference, lifecycle_state = _lifecycle_reference(inputs)
        reconciliation_reference = (
            inputs.reconciliation_result.reconciliation_reference
            if inputs.reconciliation_result
            else ""
        )
        canonical = _canonical_provenance(
            inputs,
            intent=intent,
            eligibility=eligibility,
            blockers=blockers,
            confidence=confidence,
            lifecycle_reference=lifecycle_reference,
            lifecycle_state=lifecycle_state,
            reconciliation_reference=reconciliation_reference,
        )
        provenance_hash = _sha256(_canonical_json(canonical))
        candidate_reference = "autonomous_decision_" + provenance_hash[:24]
        idempotency_key = _sha256("autonomous-decision/v1|" + provenance_hash)
        generated_at = evaluated_at.isoformat()
        expires_at = (evaluated_at + timedelta(seconds=self.config.ttl_seconds)).isoformat()
        return AutonomousDecisionCandidate(
            schema_version=AUTONOMOUS_DECISION_SCHEMA_VERSION,
            candidate_reference=candidate_reference,
            generated_at=generated_at,
            expires_at=expires_at,
            operating_mode=inputs.runtime_context.mode,
            symbol_reference=inputs.runtime_context.symbol,
            intent=intent.value,
            direction=_normalized_direction(inputs.direction, intent),
            proposed_semantic_parameter_references=tuple(
                sorted({item for item in inputs.semantic_parameter_references if _safe_reference(item)})
            ),
            market_context_reference=_safe_or_empty(inputs.runtime_context.context_pack_id),
            knowledge_evidence_references=tuple(
                sorted({item for item in inputs.runtime_context.source_refs if _safe_reference(item)})
            ),
            reasoning_result_reference=_safe_or_empty(inputs.method_selection.result_id),
            score_result_reference=_safe_or_empty(inputs.score_report.score_report_id),
            risk_result_reference=(
                _safe_or_empty(inputs.risk_result.decision_id) if inputs.risk_result else ""
            ),
            lifecycle_observation_reference=lifecycle_reference,
            lifecycle_status=lifecycle_state,
            reconciliation_reference=reconciliation_reference,
            confidence_category=confidence,
            deterministic_eligibility_result=eligibility.value,
            blocked_reason_codes=tuple(blockers),
            provenance_hash=provenance_hash,
            decision_idempotency_key=idempotency_key,
        )

    def validate_candidate(
        self, candidate: AutonomousDecisionCandidate, *, now: datetime | None = None
    ) -> AutonomousDecisionValidationResult:
        issues: list[str] = []
        if candidate.schema_version != AUTONOMOUS_DECISION_SCHEMA_VERSION:
            issues.append("INVALID_SCHEMA_VERSION")
        if candidate.intent not in {item.value for item in AutonomousDecisionIntent}:
            issues.append("UNSUPPORTED_INTENT")
        if candidate.deterministic_eligibility_result not in {
            item.value for item in AutonomousDecisionEligibility
        }:
            issues.append("INVALID_ELIGIBILITY_RESULT")
        for name in (
            "candidate_reference",
            "generated_at",
            "expires_at",
            "operating_mode",
            "symbol_reference",
            "market_context_reference",
            "reasoning_result_reference",
            "score_result_reference",
            "lifecycle_observation_reference",
            "provenance_hash",
            "decision_idempotency_key",
        ):
            if not str(getattr(candidate, name) or "").strip():
                issues.append("MISSING_" + name.upper())
        eligible = (
            candidate.deterministic_eligibility_result
            == AutonomousDecisionEligibility.ELIGIBLE_CANDIDATE.value
        )
        if eligible and not candidate.risk_result_reference:
            issues.append("MISSING_RISK_RESULT_REFERENCE")
        if eligible and not candidate.knowledge_evidence_references:
            issues.append("MISSING_EVIDENCE_REFERENCES")
        if eligible and candidate.intent in {
            AutonomousDecisionIntent.OPEN_POSITION.value,
            AutonomousDecisionIntent.MODIFY_POSITION_PROTECTION.value,
            AutonomousDecisionIntent.CLOSE_POSITION.value,
        } and not candidate.proposed_semantic_parameter_references:
            issues.append("MISSING_SEMANTIC_PARAMETER_REFERENCES")
        if eligible and candidate.intent in {
            AutonomousDecisionIntent.OPEN_POSITION.value,
            AutonomousDecisionIntent.CLOSE_POSITION.value,
        } and not candidate.direction:
            issues.append("MISSING_DIRECTION")
        if candidate.direction and candidate.direction not in {"BUY", "SELL"}:
            issues.append("UNSUPPORTED_DIRECTION")
        if _expired(candidate.expires_at, _utc(now)):
            issues.append("CANDIDATE_EXPIRED")
        safety = (
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
        if any(safety):
            issues.append("EXECUTION_AUTHORITY_NOT_ALLOWED")
        if candidate.metadata_redacted is not True:
            issues.append("METADATA_NOT_REDACTED")
        public_payload = _canonical_json(candidate.to_public_dict()).lower()
        for marker in (
            "password",
            "credential",
            "api_key",
            "account_login",
            "execution_token",
            "ticket_id",
            "deal_id",
            "position_id",
        ):
            if marker in public_payload:
                issues.append("SENSITIVE_PUBLIC_MARKER")
        return AutonomousDecisionValidationResult(valid=not issues, issues=tuple(sorted(set(issues))))

    def run_once(
        self, inputs: AutonomousDecisionInputs, *, now: datetime | None = None
    ) -> AutonomousDecisionRunResult:
        persistence_safe = True
        journal_warning = ""
        forced: tuple[str, ...] = ()
        if not self.config.enabled:
            forced = ("ORCHESTRATOR_DISABLED",)
        try:
            self.journal.records()
        except AutonomousDecisionJournalError as exc:
            persistence_safe = False
            journal_warning = str(exc)
            forced = tuple(sorted(set(forced + (str(exc),))))
        candidate = self.build_candidate(inputs, now=now, forced_blockers=forced)
        validation = self.validate_candidate(candidate, now=now)
        appended = False
        if validation.valid and persistence_safe:
            try:
                appended = self.journal.append_idempotent(candidate)
            except AutonomousDecisionJournalError as exc:
                persistence_safe = False
                journal_warning = str(exc)
                candidate = self.build_candidate(
                    inputs,
                    now=now,
                    forced_blockers=tuple(sorted(set(forced + (str(exc),)))),
                )
                validation = self.validate_candidate(candidate, now=now)
        return AutonomousDecisionRunResult(
            candidate=candidate,
            validation=validation,
            journal_appended=appended,
            persistence_safe=persistence_safe,
            journal_warning=journal_warning,
        )


def autonomous_inputs_from_mapping(payload: Mapping[str, Any]) -> AutonomousDecisionInputs:
    context = _construct(RuntimeContextPack, _required_mapping(payload, "runtime_context"))
    method_data = dict(_required_mapping(payload, "method_selection"))
    method_data["candidate_assessments"] = [
        _construct(MethodCandidateAssessment, item)
        for item in method_data.get("candidate_assessments", [])
        if isinstance(item, Mapping)
    ]
    method = _construct(MethodSelectionResult, method_data)
    score = _construct(SignalScoreReport, _required_mapping(payload, "score_report"))
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
    lifecycle_status = _construct(
        MT5RuntimeSupervisorStatus, _required_mapping(payload, "lifecycle_status")
    )
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
    refs = payload.get("semantic_parameter_references", ())
    if not isinstance(refs, (list, tuple)):
        raise ValueError("semantic_parameter_references must be a list")
    return AutonomousDecisionInputs(
        runtime_context=context,
        method_selection=method,
        score_report=score,
        risk_result=risk,
        lifecycle_status=lifecycle_status,
        lifecycle_observation=observation,
        reconciliation_result=reconciliation,
        requested_intent=str(payload.get("requested_intent", "AUTO")),
        direction=str(payload.get("direction", "")),
        semantic_parameter_references=tuple(str(item) for item in refs),
        exposure_effect=str(payload.get("exposure_effect", "NONE")),
    )


def _input_blockers(
    inputs: AutonomousDecisionInputs,
    now: datetime,
    config: AutonomousDecisionConfig,
) -> list[str]:
    blockers: list[str] = []
    context = inputs.runtime_context
    method = inputs.method_selection
    score = inputs.score_report
    risk = inputs.risk_result
    if not context.context_pack_id or not method.result_id or not score.score_report_id:
        blockers.append("MISSING_REQUIRED_INPUT")
    if risk is None or not risk.decision_id:
        blockers.append("RISK_RESULT_UNAVAILABLE")
    for timestamp in (
        context.created_at,
        method.created_at,
        score.created_at,
        risk.created_at if risk else "",
    ):
        if not _fresh(timestamp, now, config.input_max_age_seconds):
            blockers.append("STALE_MARKET_CONTEXT")
            break
    symbols = {str(value) for value in (context.symbol, method.symbol, score.symbol) if value}
    broker_symbols = {
        str(value)
        for value in (
            context.broker_symbol,
            score.broker_symbol,
            risk.broker_symbol if risk else "",
        )
        if value
    }
    modes = {str(value) for value in (context.mode, method.mode, score.mode) if value}
    if not context.symbol or not context.broker_symbol:
        blockers.append("UNSUPPORTED_SYMBOL")
    if len(symbols) != 1 or len(broker_symbols) != 1 or len(modes) != 1:
        blockers.append("CONTEXT_REFERENCE_MISMATCH")
    if method.source_context_pack_id != context.context_pack_id:
        blockers.append("CONTEXT_REFERENCE_MISMATCH")
    if score.source_context_pack_id != context.context_pack_id:
        blockers.append("CONTEXT_REFERENCE_MISMATCH")
    if score.source_method_selection_id != method.result_id:
        blockers.append("CONTEXT_REFERENCE_MISMATCH")
    if risk and (
        risk.source_context_pack_id != context.context_pack_id
        or risk.source_method_selection_id != method.result_id
        or risk.source_score_report_id != score.score_report_id
    ):
        blockers.append("CONTEXT_REFERENCE_MISMATCH")
    if not context.source_refs or not method.source_refs or not score.source_refs:
        blockers.append("EVIDENCE_INSUFFICIENT")
    if context.blockers or method.blockers:
        blockers.append("STRUCTURED_INPUT_BLOCKED")
    if risk and (risk.action == "BLOCKED" or risk.blockers):
        blockers.append("RISK_RESULT_BLOCKED")
    if score.blockers:
        blockers.append("SCORING_RESULT_BLOCKED")
    if score.primary_method_id != method.primary_method_id:
        blockers.append("REASONING_SCORE_CONFLICT")
    primary = next(
        (item for item in method.candidate_assessments if item.method_id == method.primary_method_id),
        None,
    )
    if primary and primary.conflicts and score.final_context_score >= 0.70:
        blockers.append("REASONING_SCORE_CONFLICT")
    if inputs.lifecycle_status.supervisor_status not in {"HEALTHY", "DEGRADED"}:
        blockers.append("LIFECYCLE_UNAVAILABLE")
    if not inputs.lifecycle_status.bridge_available:
        blockers.append("LIFECYCLE_UNAVAILABLE")
    if not inputs.lifecycle_status.account_context_match:
        blockers.append("ACCOUNT_CONTEXT_MISMATCH")
    if inputs.lifecycle_status.discrepancy_count > 0:
        blockers.append("LIFECYCLE_AMBIGUOUS")
    lifecycle_counts = inputs.lifecycle_status.lifecycle_state_counts
    if any(
        lifecycle_counts.get(state, 0) > 0
        for state in (
            MT5LifecycleState.UNKNOWN.value,
            MT5LifecycleState.SUBMISSION_PENDING.value,
            MT5LifecycleState.RECONCILIATION_REQUIRED.value,
            MT5LifecycleState.INCONSISTENT.value,
        )
    ):
        blockers.append("LIFECYCLE_AMBIGUOUS")
    if inputs.lifecycle_observation is None and any(
        lifecycle_counts.get(state, 0) > 0
        for state in (
            MT5LifecycleState.ORDER_ACTIVE.value,
            MT5LifecycleState.POSITION_OPEN.value,
            MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
        )
    ):
        blockers.append("LIFECYCLE_TARGET_CONFLICT")
    if inputs.lifecycle_status.last_successful_cycle and not _fresh(
        inputs.lifecycle_status.last_successful_cycle, now, config.input_max_age_seconds
    ):
        blockers.append("LIFECYCLE_STALE")
    observation = inputs.lifecycle_observation
    if observation and not _fresh(
        observation.observation_timestamp, now, config.input_max_age_seconds
    ):
        blockers.append("LIFECYCLE_STALE")
    if observation and observation.discrepancy_reason:
        blockers.append("LIFECYCLE_AMBIGUOUS")
    if observation and observation.lifecycle_state in {
        MT5LifecycleState.UNKNOWN.value,
        MT5LifecycleState.SUBMISSION_PENDING.value,
        MT5LifecycleState.RECONCILIATION_REQUIRED.value,
        MT5LifecycleState.INCONSISTENT.value,
    }:
        blockers.append("LIFECYCLE_AMBIGUOUS")
    reconciliation = inputs.reconciliation_result
    if reconciliation and (
        reconciliation.resulting_execution_state == "RESULT_UNKNOWN"
        or reconciliation.status not in {"CONFIRMED", "REJECTED", "NO_MATCH"}
        or reconciliation.evidence_classification
        in {"AMBIGUOUS_MATCH", "QUERY_FAILED", "RESULT_UNKNOWN"}
    ):
        blockers.append("RECONCILIATION_UNRESOLVED")
    requested = inputs.requested_intent.strip().upper()
    if requested not in {"AUTO", *(item.value for item in AutonomousDecisionIntent)}:
        blockers.append("UNSUPPORTED_INTENT")
    if inputs.direction and inputs.direction.strip().upper() not in {"BUY", "SELL"}:
        blockers.append("UNSUPPORTED_DIRECTION")
    if inputs.exposure_effect.strip().upper() not in {"NONE", "UNCHANGED", "REDUCE"}:
        blockers.append("EXPOSURE_INCREASE_NOT_ALLOWED")
    references = (
        context.context_pack_id,
        method.result_id,
        score.score_report_id,
        risk.decision_id if risk else "",
        *context.source_refs,
        *inputs.semantic_parameter_references,
    )
    if any(value and not _safe_reference(value) for value in references):
        blockers.append("SENSITIVE_REFERENCE_NOT_ALLOWED")
    if any(
        marker in str(value).lower()
        for value in (*context.source_refs, *inputs.semantic_parameter_references)
        for marker in ("averaging_down", "martingale", "grid_strategy", "recovery_trade")
    ):
        blockers.append("PROHIBITED_EXPOSURE_BEHAVIOR")
    return blockers


def _classify(
    inputs: AutonomousDecisionInputs, blockers: Sequence[str]
) -> tuple[AutonomousDecisionIntent, AutonomousDecisionEligibility]:
    codes = set(blockers)
    review_codes = {
        "MISSING_REQUIRED_INPUT",
        "RISK_RESULT_UNAVAILABLE",
        "STALE_MARKET_CONTEXT",
        "CONTEXT_REFERENCE_MISMATCH",
        "REASONING_SCORE_CONFLICT",
        "LIFECYCLE_UNAVAILABLE",
        "LIFECYCLE_AMBIGUOUS",
        "LIFECYCLE_STALE",
        "ACCOUNT_CONTEXT_MISMATCH",
        "RECONCILIATION_UNRESOLVED",
        "UNSUPPORTED_INTENT",
        "UNSUPPORTED_DIRECTION",
        "EXPOSURE_INCREASE_NOT_ALLOWED",
        "DECISION_JOURNAL_CORRUPT",
        "DECISION_JOURNAL_CONFLICT",
        "DECISION_JOURNAL_UNAVAILABLE",
        "ORCHESTRATOR_DISABLED",
        "SENSITIVE_REFERENCE_NOT_ALLOWED",
        "UNSUPPORTED_SYMBOL",
        "PROHIBITED_EXPOSURE_BEHAVIOR",
    }
    if codes & review_codes:
        return (
            AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
            AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
        )
    if codes:
        return AutonomousDecisionIntent.NO_ACTION, AutonomousDecisionEligibility.NOT_ELIGIBLE

    requested = inputs.requested_intent.strip().upper()
    risk_action = inputs.risk_result.action if inputs.risk_result else "BLOCKED"
    observation = inputs.lifecycle_observation
    if requested == AutonomousDecisionIntent.NO_ACTION.value:
        return AutonomousDecisionIntent.NO_ACTION, AutonomousDecisionEligibility.NOT_ELIGIBLE
    if requested in {
        AutonomousDecisionIntent.CANCEL_PENDING_ORDER.value,
        AutonomousDecisionIntent.MODIFY_POSITION_PROTECTION.value,
        AutonomousDecisionIntent.CLOSE_POSITION.value,
    }:
        intent = AutonomousDecisionIntent(requested)
        if risk_action != "MANAGE_EXISTING_POSITION" or not _management_eligible(inputs, intent):
            return (
                AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
                AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
            )
        return intent, AutonomousDecisionEligibility.ELIGIBLE_CANDIDATE
    if requested == AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW.value:
        return (
            AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
            AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
        )
    if requested in {"AUTO", AutonomousDecisionIntent.OPEN_POSITION.value}:
        if risk_action == "REVIEW_READY":
            if not inputs.semantic_parameter_references or not inputs.direction:
                return (
                    AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
                    AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
                )
            if observation and observation.lifecycle_state in {
                MT5LifecycleState.ORDER_ACTIVE.value,
                MT5LifecycleState.POSITION_OPEN.value,
                MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
            }:
                return AutonomousDecisionIntent.NO_ACTION, AutonomousDecisionEligibility.NOT_ELIGIBLE
            return (
                AutonomousDecisionIntent.OPEN_POSITION,
                AutonomousDecisionEligibility.ELIGIBLE_CANDIDATE,
            )
        if risk_action in {"NO_TRADE", "WAIT", "BLOCKED"}:
            return AutonomousDecisionIntent.NO_ACTION, AutonomousDecisionEligibility.NOT_ELIGIBLE
        return (
            AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
            AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
        )
    return (
        AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW,
        AutonomousDecisionEligibility.HUMAN_REVIEW_REQUIRED,
    )


def _management_eligible(
    inputs: AutonomousDecisionInputs, intent: AutonomousDecisionIntent
) -> bool:
    observation = inputs.lifecycle_observation
    if observation is None:
        return False
    references = observation.protected_broker_references
    orders = references.get("orders", [])
    positions = references.get("positions", [])
    if intent is AutonomousDecisionIntent.CANCEL_PENDING_ORDER:
        return (
            observation.lifecycle_state == MT5LifecycleState.ORDER_ACTIVE.value
            and len(orders) == 1
            and not positions
            and inputs.exposure_effect.upper() == "NONE"
        )
    if observation.lifecycle_state not in {
        MT5LifecycleState.POSITION_OPEN.value,
        MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
    } or len(positions) != 1:
        return False
    if intent is AutonomousDecisionIntent.MODIFY_POSITION_PROTECTION:
        return bool(inputs.semantic_parameter_references) and inputs.exposure_effect.upper() == "UNCHANGED"
    return (
        bool(inputs.semantic_parameter_references)
        and bool(inputs.direction)
        and inputs.exposure_effect.upper() == "REDUCE"
    )


def _canonical_provenance(
    inputs: AutonomousDecisionInputs,
    *,
    intent: AutonomousDecisionIntent,
    eligibility: AutonomousDecisionEligibility,
    blockers: Sequence[str],
    confidence: str,
    lifecycle_reference: str,
    lifecycle_state: str,
    reconciliation_reference: str,
) -> dict[str, Any]:
    risk = inputs.risk_result
    return {
        "schema": AUTONOMOUS_DECISION_SCHEMA_VERSION,
        "operating_mode": inputs.runtime_context.mode,
        "symbol_reference": inputs.runtime_context.symbol,
        "requested_intent": inputs.requested_intent.strip().upper(),
        "direction": inputs.direction.strip().upper(),
        "exposure_effect": inputs.exposure_effect.strip().upper(),
        "semantic_parameter_references": sorted(set(inputs.semantic_parameter_references)),
        "market_context_reference": inputs.runtime_context.context_pack_id,
        "market_context_created_at": inputs.runtime_context.created_at,
        "knowledge_evidence_references": sorted(set(inputs.runtime_context.source_refs)),
        "reasoning_result_reference": inputs.method_selection.result_id,
        "reasoning_created_at": inputs.method_selection.created_at,
        "reasoning_primary_method": inputs.method_selection.primary_method_id,
        "reasoning_confidence": round(float(inputs.method_selection.confidence), 8),
        "score_result_reference": inputs.score_report.score_report_id,
        "score_created_at": inputs.score_report.created_at,
        "score_primary_method": inputs.score_report.primary_method_id,
        "score_value": round(float(inputs.score_report.final_context_score), 8),
        "score_grade": inputs.score_report.grade,
        "risk_result_reference": risk.decision_id if risk else "",
        "risk_created_at": risk.created_at if risk else "",
        "risk_action": risk.action if risk else "",
        "risk_blocker_codes": sorted(item.code for item in risk.blockers) if risk else [],
        "lifecycle_reference": lifecycle_reference,
        "lifecycle_state": lifecycle_state,
        "lifecycle_account_match": inputs.lifecycle_status.account_context_match,
        "lifecycle_discrepancy_count": inputs.lifecycle_status.discrepancy_count,
        "reconciliation_reference": reconciliation_reference,
        "reconciliation_state": (
            inputs.reconciliation_result.resulting_execution_state
            if inputs.reconciliation_result
            else ""
        ),
        "intent": intent.value,
        "eligibility": eligibility.value,
        "blocked_reason_codes": sorted(set(blockers)),
        "confidence_category": confidence,
    }


def _confidence_category(
    inputs: AutonomousDecisionInputs, intent: AutonomousDecisionIntent
) -> str:
    if intent is AutonomousDecisionIntent.REQUIRE_HUMAN_REVIEW:
        return "BLOCKED"
    risk_confidence = inputs.risk_result.confidence if inputs.risk_result else 0.0
    value = (
        float(inputs.method_selection.confidence)
        + float(inputs.score_report.final_context_score)
        + float(risk_confidence)
    ) / 3.0
    if value >= 0.75:
        return "HIGH"
    if value >= 0.55:
        return "MEDIUM"
    return "LOW"


def _lifecycle_reference(inputs: AutonomousDecisionInputs) -> tuple[str, str]:
    if inputs.lifecycle_observation:
        return (
            inputs.lifecycle_observation.observation_id,
            inputs.lifecycle_observation.lifecycle_state,
        )
    status = inputs.lifecycle_status
    reference_material = {
        "last_successful_cycle": status.last_successful_cycle,
        "records_inspected": status.records_inspected,
        "state_counts": dict(sorted(status.lifecycle_state_counts.items())),
        "health_reason": status.health_reason,
    }
    return "runtime_lifecycle_" + _sha256(_canonical_json(reference_material))[:24], "NO_ACTIVE_TARGET"


def _normalized_direction(direction: str, intent: AutonomousDecisionIntent) -> str:
    if intent not in {AutonomousDecisionIntent.OPEN_POSITION, AutonomousDecisionIntent.CLOSE_POSITION}:
        return ""
    return direction.strip().upper()


def _journal_row(candidate: AutonomousDecisionCandidate) -> dict[str, Any]:
    row = {
        "record_type": "AUTONOMOUS_DECISION_CANDIDATE",
        "candidate_reference": candidate.candidate_reference,
        "provenance_hash": candidate.provenance_hash,
        "decision_idempotency_key": candidate.decision_idempotency_key,
        "generated_at": candidate.generated_at,
        "expires_at": candidate.expires_at,
        "intent": candidate.intent,
        "eligibility_result": candidate.deterministic_eligibility_result,
        "blocked_reason_codes": list(candidate.blocked_reason_codes),
        "input_references": {
            "market_context": candidate.market_context_reference,
            "reasoning": candidate.reasoning_result_reference,
            "score": candidate.score_result_reference,
            "risk": candidate.risk_result_reference,
        },
        "lifecycle_reference": candidate.lifecycle_observation_reference,
        "reconciliation_reference": candidate.reconciliation_reference,
        "confidence_category": candidate.confidence_category,
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
    if row.get("record_type") != "AUTONOMOUS_DECISION_CANDIDATE":
        return False
    if row.get("intent") not in {item.value for item in AutonomousDecisionIntent}:
        return False
    if row.get("eligibility_result") not in {item.value for item in AutonomousDecisionEligibility}:
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


def _construct(cls, payload: Mapping[str, Any]):
    allowed = {item.name for item in fields(cls)}
    values = {key: value for key, value in payload.items() if key in allowed}
    return cls(**values)


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _fresh(value: str, now: datetime, max_age_seconds: int) -> bool:
    parsed = _parse_datetime(value)
    if parsed is None or parsed > now + timedelta(seconds=5):
        return False
    return now - parsed <= timedelta(seconds=max_age_seconds)


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


def _safe_reference(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and not any(
        marker in text
        for marker in (
            "password",
            "credential",
            "api_key",
            "secret",
            "account_login",
            "execution_token",
            "ticket_id",
            "deal_id",
            "position_id",
        )
    )


def _safe_or_empty(value: Any) -> str:
    return str(value) if _safe_reference(value) else ""
