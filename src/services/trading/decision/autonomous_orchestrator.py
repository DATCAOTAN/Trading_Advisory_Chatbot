from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
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
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport


AUTONOMOUS_DECISION_SCHEMA_VERSION = "autonomous-decision-candidate/v2"
AUTONOMOUS_DECISION_LEGACY_SCHEMA_VERSION = "autonomous-decision-candidate/v1"
OFFLINE_FIXTURE_MODE = "offline_fixture"
OFFLINE_FIXTURE_REFERENCE_PREFIX = "offline_fixture:"
AUTONOMOUS_LLM_PROPOSAL_SOURCE = "AUTONOMOUS_LLM"
OFFLINE_FIXTURE_PROPOSAL_SOURCE = "OFFLINE_FIXTURE"
MANUAL_OPERATOR_PROPOSAL_SOURCE = "MANUAL_OPERATOR"
PROPOSAL_SOURCES = {
    AUTONOMOUS_LLM_PROPOSAL_SOURCE,
    OFFLINE_FIXTURE_PROPOSAL_SOURCE,
    MANUAL_OPERATOR_PROPOSAL_SOURCE,
}


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


class AutonomousOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class AutonomousEntryIntent(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    PULLBACK = "PULLBACK"
    BREAKOUT = "BREAKOUT"
    STOP_LIMIT = "STOP_LIMIT"


class AutonomousOrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"
    BUY_STOP_LIMIT = "BUY_STOP_LIMIT"
    SELL_STOP_LIMIT = "SELL_STOP_LIMIT"


class AutonomousOrderAction(str, Enum):
    MARKET = "MARKET"
    PENDING = "PENDING"


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
class AutonomousOrderIntentProposal:
    symbol: str
    side: str
    entry_intent: str
    order_type: str
    proposed_action: str = ""
    entry_price: Any = field(default=None, repr=False)
    trigger_price: Any = field(default=None, repr=False)
    limit_price: Any = field(default=None, repr=False)
    stop_loss: Any = field(default=None, repr=False)
    take_profit: Any = field(default=None, repr=False)
    proposed_volume: Any = field(default=None, repr=False)
    risk_policy_reference: str = ""
    structured_reasoning: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class AutonomousOrderMarketSnapshot:
    snapshot_reference: str
    observed_at: str
    symbol: str
    bid: Any = field(repr=False)
    ask: Any = field(repr=False)
    provider_name: str = "mt5_bridge"
    broker_symbol: str = ""
    point: Any = field(default=None, repr=False)
    tick_size: Any = field(default=None, repr=False)
    digits: int | None = None
    minimum_distance_points: Any = field(default=None, repr=False)
    volume_min: Any = field(default=None, repr=False)
    volume_max: Any = field(default=None, repr=False)
    volume_step: Any = field(default=None, repr=False)
    tick_value: Any = field(default=None, repr=False)
    contract_size: Any = field(default=None, repr=False)
    source_refs: tuple[str, ...] = ()


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
    order_proposal: AutonomousOrderIntentProposal | None = None
    order_market_snapshot: AutonomousOrderMarketSnapshot | None = None
    timeframe_profile: tuple[str, ...] = ()
    account_context_reference: str = ""
    proposal_source: str = AUTONOMOUS_LLM_PROPOSAL_SOURCE
    proposal_source_reference: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    normalized_strategy_hash: str = ""
    reasoning_evidence_summary: str = ""


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
    side: str = ""
    entry_intent: str = ""
    order_type: str = ""
    action: str = ""
    advisory_action: str = ""
    entry_price: str = field(default="", repr=False)
    trigger_price: str = field(default="", repr=False)
    limit_price: str = field(default="", repr=False)
    stop_loss: str = field(default="", repr=False)
    take_profit: str = field(default="", repr=False)
    proposed_volume: str = field(default="", repr=False)
    risk_policy_reference: str = ""
    structured_reasoning: tuple[str, ...] = field(default=(), repr=False)
    market_snapshot_reference: str = ""
    market_snapshot_provenance_hash: str = ""
    market_recommendation: str = ""
    structured_order_hash: str = ""
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
    broker_symbol_reference: str = ""
    timeframe_profile: tuple[str, ...] = ()
    method_selection_summary: str = field(default="", repr=False)
    account_context_reference: str = ""
    proposal_source: str = AUTONOMOUS_LLM_PROPOSAL_SOURCE
    proposal_source_reference: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    normalized_strategy_hash: str = ""
    reasoning_evidence_summary: str = field(default="", repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_reference": self.candidate_reference,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "operating_mode": self.operating_mode,
            "symbol_reference": self.symbol_reference,
            "broker_symbol_reference": self.broker_symbol_reference,
            "proposal_source": self.proposal_source,
            "proposal_source_reference": self.proposal_source_reference,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_hash_prefix": self.normalized_strategy_hash[:12],
            "intent": self.intent,
            "direction_present": bool(self.direction),
            "side_present": bool(self.side),
            "entry_intent": self.entry_intent,
            "order_type": self.order_type,
            "action": self.action,
            "advisory_action_present": bool(self.advisory_action),
            "entry_price_present": bool(self.entry_price),
            "trigger_price_present": bool(self.trigger_price),
            "limit_price_present": bool(self.limit_price),
            "stop_loss_present": bool(self.stop_loss),
            "take_profit_present": bool(self.take_profit),
            "proposed_volume_present": bool(self.proposed_volume),
            "risk_policy_reference": self.risk_policy_reference,
            "structured_reasoning_count": len(self.structured_reasoning),
            "market_snapshot_reference": self.market_snapshot_reference,
            "market_snapshot_provenance_hash": self.market_snapshot_provenance_hash,
            "market_recommendation": self.market_recommendation,
            "structured_order_hash": self.structured_order_hash,
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

    def to_operator_review_dict(self) -> dict[str, Any]:
        """Return the bounded local projection used for human proposal review."""
        return {
            "schema_version": self.schema_version,
            "candidate_reference": self.candidate_reference,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "symbol": self.symbol_reference,
            "broker_symbol": self.broker_symbol_reference,
            "proposal_source": self.proposal_source,
            "proposal_source_reference": self.proposal_source_reference,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_hash_prefix": self.normalized_strategy_hash[:12],
            "reasoning_evidence_summary": self.reasoning_evidence_summary,
            "timeframe_profile": list(self.timeframe_profile),
            "method_selection_summary": self.method_selection_summary,
            "account_context_reference": self.account_context_reference,
            "intent": self.intent,
            "side": self.side,
            "entry_intent": self.entry_intent,
            "order_type": self.order_type,
            "action": self.action,
            "entry_price": self.entry_price,
            "trigger_price": self.trigger_price,
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "proposed_volume": self.proposed_volume,
            "risk_policy_present": bool(self.risk_policy_reference),
            "structured_reasoning_summary": _operator_review_reasoning(
                self.structured_reasoning
            ),
            "recommendation": self.market_recommendation,
            "execution_authority": False,
            "execution_permission_requested": False,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
        }

    def to_protected_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            payload[item.name] = list(value) if isinstance(value, tuple) else value
        return payload


def autonomous_candidate_has_offline_provenance(
    candidate: AutonomousDecisionCandidate,
) -> bool:
    return (
        candidate.operating_mode == OFFLINE_FIXTURE_MODE
        or candidate.market_snapshot_reference.startswith(OFFLINE_FIXTURE_REFERENCE_PREFIX)
    )


def autonomous_account_context_reference(account_id_hash: str) -> str:
    value = str(account_id_hash or "").strip()
    return "account_context_" + _sha256(value)[:24] if value else ""


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
    order_market_snapshot: AutonomousOrderMarketSnapshot | None = field(
        default=None, repr=False, compare=False
    )

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
        return self._records(include_protected=False)

    def _records(self, *, include_protected: bool) -> list[dict[str, Any]]:
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
            if (
                not isinstance(row, dict)
                or not self._required_keys.issubset(row)
                or set(row).difference(self._required_keys)
                - {
                    "protected_candidate",
                    "protected_market_snapshot",
                    "protected_runtime_evidence",
                }
            ):
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
            if not _journal_row_valid(row):
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
            key = str(row["decision_idempotency_key"])
            provenance = str(row["provenance_hash"])
            if key in seen and not hmac.compare_digest(seen[key], provenance):
                raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
            seen[key] = provenance
            if not include_protected:
                row = dict(row)
                row.pop("protected_candidate", None)
                row.pop("protected_market_snapshot", None)
                row.pop("protected_runtime_evidence", None)
            records.append(row)
        return records[-self.max_read_records :]

    def load_candidate(self, candidate_reference: str) -> AutonomousDecisionCandidate | None:
        matches = [
            row
            for row in self._records(include_protected=True)
            if hmac.compare_digest(
                str(row.get("candidate_reference", "")), str(candidate_reference or "")
            )
        ]
        if not matches:
            return None
        payload = matches[-1].get("protected_candidate")
        if not isinstance(payload, Mapping):
            return None
        try:
            candidate = _candidate_from_protected_dict(payload)
        except (TypeError, ValueError) as exc:
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT") from exc
        row = matches[-1]
        if not (
            hmac.compare_digest(candidate.candidate_reference, str(row["candidate_reference"]))
            and hmac.compare_digest(candidate.provenance_hash, str(row["provenance_hash"]))
            and hmac.compare_digest(
                candidate.decision_idempotency_key, str(row["decision_idempotency_key"])
            )
        ):
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
        return candidate

    def load_market_snapshot(
        self, candidate_reference: str
    ) -> AutonomousOrderMarketSnapshot | None:
        row = self._protected_row(candidate_reference)
        payload = row.get("protected_market_snapshot") if row else None
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
        try:
            return _market_snapshot_from_protected_dict(payload)
        except (TypeError, ValueError) as exc:
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT") from exc

    def load_runtime_evidence(self, candidate_reference: str) -> dict[str, Any] | None:
        row = self._protected_row(candidate_reference)
        payload = row.get("protected_runtime_evidence") if row else None
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CORRUPT")
        return dict(payload)

    def _protected_row(self, candidate_reference: str) -> dict[str, Any] | None:
        matches = [
            row
            for row in self._records(include_protected=True)
            if hmac.compare_digest(
                str(row.get("candidate_reference", "")), str(candidate_reference or "")
            )
        ]
        return matches[-1] if matches else None

    def append_idempotent(
        self,
        candidate: AutonomousDecisionCandidate,
        market_snapshot: AutonomousOrderMarketSnapshot | None = None,
        lifecycle_status: MT5RuntimeSupervisorStatus | None = None,
        reconciliation_result: MT5ReconciliationReceipt | None = None,
    ) -> bool:
        with self._exclusive_lock():
            protected_row = _journal_row(
                candidate,
                market_snapshot=market_snapshot,
                lifecycle_status=lifecycle_status,
                reconciliation_result=reconciliation_result,
            )
            for row in self._records(include_protected=True):
                if hmac.compare_digest(
                    str(row["decision_idempotency_key"]), candidate.decision_idempotency_key
                ):
                    if not hmac.compare_digest(str(row["provenance_hash"]), candidate.provenance_hash):
                        raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
                    for key in (
                        "protected_market_snapshot",
                        "protected_runtime_evidence",
                    ):
                        if key in protected_row and _canonical_json(
                            row.get(key)
                        ) != _canonical_json(protected_row.get(key)):
                            raise AutonomousDecisionJournalError("DECISION_JOURNAL_CONFLICT")
                    return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(protected_row, ensure_ascii=True, sort_keys=True) + "\n"
                    )
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
        structured_order = _resolve_order_proposal(
            inputs, evaluated_at, self.config.input_max_age_seconds
        )
        blockers = _input_blockers(inputs, evaluated_at, self.config)
        blockers.extend(structured_order["blockers"])
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
            structured_order=structured_order,
        )
        provenance_hash = _sha256(_canonical_json(canonical))
        candidate_reference = "autonomous_decision_" + provenance_hash[:24]
        idempotency_key = _sha256("autonomous-decision/v2|" + provenance_hash)
        generated_at = evaluated_at.isoformat()
        expires_at = (evaluated_at + timedelta(seconds=self.config.ttl_seconds)).isoformat()
        return AutonomousDecisionCandidate(
            schema_version=AUTONOMOUS_DECISION_SCHEMA_VERSION,
            candidate_reference=candidate_reference,
            generated_at=generated_at,
            expires_at=expires_at,
            operating_mode=inputs.runtime_context.mode,
            symbol_reference=inputs.runtime_context.symbol,
            broker_symbol_reference=inputs.runtime_context.broker_symbol,
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
            side=structured_order["side"],
            entry_intent=structured_order["entry_intent"],
            order_type=structured_order["order_type"],
            action=structured_order["action"],
            advisory_action=structured_order["advisory_action"],
            entry_price=structured_order["entry_price"],
            trigger_price=structured_order["trigger_price"],
            limit_price=structured_order["limit_price"],
            stop_loss=structured_order["stop_loss"],
            take_profit=structured_order["take_profit"],
            proposed_volume=structured_order["proposed_volume"],
            risk_policy_reference=structured_order["risk_policy_reference"],
            structured_reasoning=structured_order["structured_reasoning"],
            market_snapshot_reference=structured_order["market_snapshot_reference"],
            market_snapshot_provenance_hash=structured_order[
                "market_snapshot_provenance_hash"
            ],
            market_recommendation=structured_order["market_recommendation"],
            structured_order_hash=structured_order["structured_order_hash"],
            timeframe_profile=tuple(inputs.timeframe_profile),
            method_selection_summary=str(inputs.method_selection.reasoning_summary or "")[:500],
            account_context_reference=_safe_or_empty(inputs.account_context_reference),
            proposal_source=_proposal_source(inputs),
            proposal_source_reference=_safe_or_empty(inputs.proposal_source_reference),
            strategy_id=_safe_or_empty(inputs.strategy_id),
            strategy_version=_safe_or_empty(inputs.strategy_version),
            normalized_strategy_hash=(
                inputs.normalized_strategy_hash
                if _valid_hash(inputs.normalized_strategy_hash)
                else ""
            ),
            reasoning_evidence_summary=str(inputs.reasoning_evidence_summary or "")[:2000],
        )

    def validate_candidate(
        self, candidate: AutonomousDecisionCandidate, *, now: datetime | None = None
    ) -> AutonomousDecisionValidationResult:
        issues: list[str] = []
        if candidate.schema_version not in {
            AUTONOMOUS_DECISION_SCHEMA_VERSION,
            AUTONOMOUS_DECISION_LEGACY_SCHEMA_VERSION,
        }:
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
        if candidate.schema_version == AUTONOMOUS_DECISION_SCHEMA_VERSION:
            if not candidate.broker_symbol_reference:
                issues.append("MISSING_BROKER_SYMBOL_REFERENCE")
            elif (
                candidate.symbol_reference in {"XAUUSD", "BTCUSD"}
                and candidate.broker_symbol_reference != broker_symbol_for(candidate.symbol_reference)
            ):
                issues.append("BROKER_SYMBOL_REFERENCE_MISMATCH")
        if candidate.proposal_source not in PROPOSAL_SOURCES:
            issues.append("PROPOSAL_SOURCE_INVALID")
        if (
            candidate.proposal_source == MANUAL_OPERATOR_PROPOSAL_SOURCE
            and not candidate.proposal_source_reference
        ):
            issues.append("MANUAL_PROPOSAL_SOURCE_REFERENCE_MISSING")
        if candidate.proposal_source_reference and not _safe_reference(
            candidate.proposal_source_reference
        ):
            issues.append("PROPOSAL_SOURCE_REFERENCE_INVALID")
        strategy_values = (
            candidate.strategy_id,
            candidate.strategy_version,
            candidate.normalized_strategy_hash,
        )
        if any(strategy_values) and (
            not all(strategy_values)
            or not _safe_reference(candidate.strategy_id)
            or not _safe_reference(candidate.strategy_version)
            or not _valid_hash(candidate.normalized_strategy_hash)
        ):
            issues.append("STRATEGY_BINDING_INVALID")
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
        if candidate.side and candidate.side not in {item.value for item in AutonomousOrderSide}:
            issues.append("UNSUPPORTED_ORDER_SIDE")
        if candidate.entry_intent and candidate.entry_intent not in {
            item.value for item in AutonomousEntryIntent
        }:
            issues.append("UNSUPPORTED_ENTRY_INTENT")
        if candidate.order_type and candidate.order_type not in {
            item.value for item in AutonomousOrderType
        }:
            issues.append("UNSUPPORTED_ORDER_TYPE")
        if candidate.action and candidate.action not in {
            item.value for item in AutonomousOrderAction
        }:
            issues.append("UNSUPPORTED_ORDER_ACTION")
        if candidate.order_type:
            expected_action = _action_for_order_type(candidate.order_type)
            if candidate.action != expected_action:
                issues.append("ORDER_ACTION_NOT_DETERMINISTIC")
            expected_hash = _candidate_structured_order_hash(candidate)
            if not candidate.structured_order_hash or not hmac.compare_digest(
                candidate.structured_order_hash, expected_hash
            ):
                issues.append("STRUCTURED_ORDER_HASH_INVALID")
        elif candidate.structured_order_hash:
            issues.append("STRUCTURED_ORDER_WITHOUT_ORDER_TYPE")
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
        self,
        inputs: AutonomousDecisionInputs,
        *,
        now: datetime | None = None,
        require_actionable: bool = False,
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
        actionable = (
            candidate.intent == AutonomousDecisionIntent.OPEN_POSITION.value
            and candidate.deterministic_eligibility_result
            == AutonomousDecisionEligibility.ELIGIBLE_CANDIDATE.value
            and candidate.action in {item.value for item in AutonomousOrderAction}
        )
        if validation.valid and persistence_safe and (actionable or not require_actionable):
            try:
                if inputs.order_market_snapshot is None:
                    appended = self.journal.append_idempotent(candidate)
                else:
                    appended = self.journal.append_idempotent(
                        candidate,
                        market_snapshot=inputs.order_market_snapshot,
                        lifecycle_status=inputs.lifecycle_status,
                        reconciliation_result=inputs.reconciliation_result,
                    )
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
            order_market_snapshot=inputs.order_market_snapshot,
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
    proposal_data = payload.get("order_proposal")
    proposal = None
    if isinstance(proposal_data, Mapping):
        proposal_values = dict(proposal_data)
        reasoning = proposal_values.get("structured_reasoning", ())
        if not isinstance(reasoning, (list, tuple)):
            raise ValueError("structured_reasoning must be a list")
        proposal_values["structured_reasoning"] = tuple(str(item) for item in reasoning)
        if "proposed_action" not in proposal_values and "action" in proposal_values:
            proposal_values["proposed_action"] = proposal_values.pop("action")
        proposal = _construct(AutonomousOrderIntentProposal, proposal_values)
    snapshot_data = payload.get("order_market_snapshot")
    snapshot = None
    if isinstance(snapshot_data, Mapping):
        snapshot_values = dict(snapshot_data)
        snapshot_refs = snapshot_values.get("source_refs", ())
        if not isinstance(snapshot_refs, (list, tuple)):
            raise ValueError("order market source_refs must be a list")
        snapshot_values["source_refs"] = tuple(str(item) for item in snapshot_refs)
        snapshot = _construct(AutonomousOrderMarketSnapshot, snapshot_values)
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
        order_proposal=proposal,
        order_market_snapshot=snapshot,
        timeframe_profile=tuple(str(item) for item in payload.get("timeframe_profile", ())),
        account_context_reference=str(payload.get("account_context_reference", "")),
        proposal_source=str(
            payload.get("proposal_source", AUTONOMOUS_LLM_PROPOSAL_SOURCE)
        ),
        proposal_source_reference=str(payload.get("proposal_source_reference", "")),
    )



_ORDER_TYPE_SEMANTICS = {
    AutonomousOrderType.BUY.value: (
        AutonomousOrderSide.BUY.value,
        AutonomousEntryIntent.IMMEDIATE.value,
        AutonomousOrderAction.MARKET.value,
    ),
    AutonomousOrderType.SELL.value: (
        AutonomousOrderSide.SELL.value,
        AutonomousEntryIntent.IMMEDIATE.value,
        AutonomousOrderAction.MARKET.value,
    ),
    AutonomousOrderType.BUY_LIMIT.value: (
        AutonomousOrderSide.BUY.value,
        AutonomousEntryIntent.PULLBACK.value,
        AutonomousOrderAction.PENDING.value,
    ),
    AutonomousOrderType.SELL_LIMIT.value: (
        AutonomousOrderSide.SELL.value,
        AutonomousEntryIntent.PULLBACK.value,
        AutonomousOrderAction.PENDING.value,
    ),
    AutonomousOrderType.BUY_STOP.value: (
        AutonomousOrderSide.BUY.value,
        AutonomousEntryIntent.BREAKOUT.value,
        AutonomousOrderAction.PENDING.value,
    ),
    AutonomousOrderType.SELL_STOP.value: (
        AutonomousOrderSide.SELL.value,
        AutonomousEntryIntent.BREAKOUT.value,
        AutonomousOrderAction.PENDING.value,
    ),
    AutonomousOrderType.BUY_STOP_LIMIT.value: (
        AutonomousOrderSide.BUY.value,
        AutonomousEntryIntent.STOP_LIMIT.value,
        AutonomousOrderAction.PENDING.value,
    ),
    AutonomousOrderType.SELL_STOP_LIMIT.value: (
        AutonomousOrderSide.SELL.value,
        AutonomousEntryIntent.STOP_LIMIT.value,
        AutonomousOrderAction.PENDING.value,
    ),
}


def resolve_autonomous_order_action(order_type: str) -> str:
    normalized = str(order_type or "").strip().upper()
    semantics = _ORDER_TYPE_SEMANTICS.get(normalized)
    if semantics is None:
        raise ValueError("unsupported autonomous order type")
    return semantics[2]


def autonomous_market_snapshot_provenance_hash(
    snapshot: AutonomousOrderMarketSnapshot,
) -> str:
    """Return the canonical provenance hash used by structured order candidates."""
    return _sha256(_canonical_json(_market_snapshot_material(snapshot)))


def autonomous_symbol_metadata_hash(snapshot: AutonomousOrderMarketSnapshot) -> str:
    material = {
        key: value
        for key, value in _market_snapshot_material(snapshot).items()
        if key
        in {
            "symbol",
            "broker_symbol",
            "point",
            "tick_size",
            "digits",
            "minimum_distance_points",
            "volume_min",
            "volume_max",
            "volume_step",
            "tick_value",
            "contract_size",
        }
    }
    return _sha256(_canonical_json(material))


def validate_autonomous_candidate_order_snapshot(
    candidate: AutonomousDecisionCandidate,
    snapshot: AutonomousOrderMarketSnapshot,
    *,
    now: datetime,
    maximum_age_seconds: int,
) -> AutonomousDecisionValidationResult:
    """Independently recheck the protected order against its bound snapshot."""
    issues: list[str] = []
    if not hmac.compare_digest(
        candidate.market_snapshot_reference, snapshot.snapshot_reference
    ):
        issues.append("MARKET_SNAPSHOT_REFERENCE_MISMATCH")
    snapshot_hash = autonomous_market_snapshot_provenance_hash(snapshot)
    if not hmac.compare_digest(candidate.market_snapshot_provenance_hash, snapshot_hash):
        issues.append("MARKET_SNAPSHOT_HASH_MISMATCH")
    if candidate.symbol_reference != snapshot.symbol:
        issues.append("MARKET_SNAPSHOT_SYMBOL_MISMATCH")
    if (
        candidate.broker_symbol_reference != snapshot.broker_symbol
        or candidate.broker_symbol_reference != broker_symbol_for(candidate.symbol_reference)
    ):
        issues.append("BROKER_SYMBOL_REFERENCE_MISMATCH")
    if not snapshot.source_refs:
        issues.append("MARKET_SNAPSHOT_SOURCE_REFS_MISSING")
    if not _fresh(snapshot.observed_at, _utc(now), maximum_age_seconds):
        issues.append("MARKET_SNAPSHOT_STALE")

    material = _market_snapshot_material(snapshot)
    bid = _positive_decimal_or_none(material["bid"])
    ask = _positive_decimal_or_none(material["ask"])
    point = _positive_decimal_or_none(material["point"])
    tick_size = _positive_decimal_or_none(material["tick_size"])
    minimum_points = _positive_decimal_or_none(
        material["minimum_distance_points"], allow_zero=True
    )
    volume_min = _positive_decimal_or_none(material["volume_min"])
    volume_max = _positive_decimal_or_none(material["volume_max"])
    volume_step = _positive_decimal_or_none(material["volume_step"])
    tick_value = _positive_decimal_or_none(material["tick_value"])
    contract_size = _positive_decimal_or_none(material["contract_size"])
    if bid is None or ask is None or ask < bid:
        issues.append("MARKET_BID_ASK_INVALID")
    if any(
        value is None
        for value in (
            point,
            tick_size,
            minimum_points,
            volume_min,
            volume_max,
            volume_step,
            tick_value,
            contract_size,
        )
    ) or not isinstance(snapshot.digits, int) or isinstance(snapshot.digits, bool):
        issues.append("SYMBOL_METADATA_MISSING_OR_INVALID")

    volume = _positive_decimal_or_none(candidate.proposed_volume)
    if volume is None:
        issues.append("PROPOSED_VOLUME_INVALID")
    elif volume_min is not None and volume_max is not None and volume_step is not None:
        if volume < volume_min:
            issues.append("PROPOSED_VOLUME_BELOW_MINIMUM")
        if volume > volume_max:
            issues.append("PROPOSED_VOLUME_ABOVE_MAXIMUM")
        if (volume - volume_min) % volume_step != 0:
            issues.append("PROPOSED_VOLUME_STEP_MISMATCH")

    resolved = {
        "order_type": candidate.order_type,
        "side": candidate.side,
        "action": candidate.action,
        "entry_price": candidate.entry_price,
        "trigger_price": candidate.trigger_price,
        "limit_price": candidate.limit_price,
        "stop_loss": candidate.stop_loss,
        "take_profit": candidate.take_profit,
        "market_recommendation": candidate.market_recommendation,
    }
    if bid is not None and ask is not None and point is not None and minimum_points is not None:
        _validate_order_prices(
            resolved,
            bid=bid,
            ask=ask,
            minimum_distance=point * minimum_points,
            tick_size=tick_size,
            digits=snapshot.digits,
            blockers=issues,
        )
    return AutonomousDecisionValidationResult(
        valid=not issues, issues=tuple(dict.fromkeys(issues))
    )


def _empty_structured_order() -> dict[str, Any]:
    return {
        "side": "",
        "entry_intent": "",
        "order_type": "",
        "action": "",
        "advisory_action": "",
        "entry_price": "",
        "trigger_price": "",
        "limit_price": "",
        "stop_loss": "",
        "take_profit": "",
        "proposed_volume": "",
        "risk_policy_reference": "",
        "structured_reasoning": (),
        "market_snapshot_reference": "",
        "market_snapshot_provenance_hash": "",
        "market_recommendation": "",
        "structured_order_hash": "",
        "blockers": [],
    }


def _resolve_order_proposal(
    inputs: AutonomousDecisionInputs,
    now: datetime,
    maximum_age_seconds: int,
) -> dict[str, Any]:
    resolved = _empty_structured_order()
    proposal = inputs.order_proposal
    if proposal is None:
        return resolved

    blockers: list[str] = resolved["blockers"]
    resolved.update(
        {
            "side": str(proposal.side or "").strip().upper(),
            "entry_intent": str(proposal.entry_intent or "").strip().upper(),
            "order_type": str(proposal.order_type or "").strip().upper(),
            "advisory_action": str(proposal.proposed_action or "").strip().upper(),
            "risk_policy_reference": _safe_or_empty(proposal.risk_policy_reference),
            "structured_reasoning": tuple(
                str(item).strip() for item in proposal.structured_reasoning if str(item).strip()
            ),
        }
    )
    for name in (
        "entry_price",
        "trigger_price",
        "limit_price",
        "stop_loss",
        "take_profit",
        "proposed_volume",
    ):
        text, _, valid = _canonical_decimal(getattr(proposal, name))
        resolved[name] = text
        if text and not valid:
            blockers.append("INVALID_" + name.upper())

    if proposal.symbol != inputs.runtime_context.symbol:
        blockers.append("ORDER_PROPOSAL_SYMBOL_MISMATCH")
    semantics = _ORDER_TYPE_SEMANTICS.get(resolved["order_type"])
    if semantics is None:
        blockers.append("UNSUPPORTED_ORDER_TYPE")
    else:
        expected_side, expected_entry_intent, action = semantics
        resolved["action"] = action
        if resolved["side"] != expected_side:
            blockers.append("ORDER_SIDE_MISMATCH")
        if resolved["entry_intent"] != expected_entry_intent:
            blockers.append("ENTRY_INTENT_MISMATCH")
        if inputs.direction.strip().upper() != expected_side:
            blockers.append("ORDER_DIRECTION_MISMATCH")
        if resolved["advisory_action"] and resolved["advisory_action"] != action:
            blockers.append("ADVISORY_ACTION_CONTRADICTS_RESOLVED_ACTION")
    if resolved["advisory_action"] and resolved["advisory_action"] not in {
        item.value for item in AutonomousOrderAction
    }:
        blockers.append("UNSUPPORTED_ADVISORY_ACTION")
    if not resolved["risk_policy_reference"]:
        blockers.append("RISK_POLICY_REFERENCE_MISSING")
    if (
        not resolved["structured_reasoning"]
        and _proposal_source(inputs) != MANUAL_OPERATOR_PROPOSAL_SOURCE
    ):
        blockers.append("STRUCTURED_REASONING_MISSING")
    volume = _decimal_or_none(resolved["proposed_volume"])
    if volume is not None and volume <= 0:
        blockers.append("INVALID_PROPOSED_VOLUME")

    snapshot = inputs.order_market_snapshot
    bid = ask = None
    minimum_distance = Decimal("0")
    tick_size = None
    if snapshot is None:
        blockers.append("ORDER_MARKET_SNAPSHOT_MISSING")
    else:
        resolved["market_snapshot_reference"] = _safe_or_empty(snapshot.snapshot_reference)
        market_material = _market_snapshot_material(snapshot)
        resolved["market_snapshot_provenance_hash"] = (
            autonomous_market_snapshot_provenance_hash(snapshot)
        )
        if not resolved["market_snapshot_reference"] or not snapshot.source_refs:
            blockers.append("MARKET_SNAPSHOT_PROVENANCE_MISSING")
        if any(not _safe_reference(item) for item in snapshot.source_refs):
            blockers.append("SENSITIVE_REFERENCE_NOT_ALLOWED")
        if snapshot.symbol != inputs.runtime_context.symbol:
            blockers.append("MARKET_SNAPSHOT_SYMBOL_MISMATCH")
        if snapshot.symbol in {"XAUUSD", "BTCUSD"} and (
            not snapshot.broker_symbol
            or snapshot.broker_symbol != inputs.runtime_context.broker_symbol
            or snapshot.broker_symbol != broker_symbol_for(snapshot.symbol)
        ):
            blockers.append("MARKET_SNAPSHOT_BROKER_SYMBOL_MISMATCH")
        if not _fresh(snapshot.observed_at, now, maximum_age_seconds):
            blockers.append("MARKET_SNAPSHOT_STALE")
        bid = _decimal_or_none(market_material["bid"])
        ask = _decimal_or_none(market_material["ask"])
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            blockers.append("MARKET_BID_ASK_INVALID")
        point = _positive_decimal_or_none(market_material["point"])
        tick_size = _positive_decimal_or_none(market_material["tick_size"])
        distance_points = _positive_decimal_or_none(
            market_material["minimum_distance_points"], allow_zero=True
        )
        if snapshot.point not in (None, "") and point is None:
            blockers.append("MARKET_POINT_INVALID")
        if snapshot.tick_size not in (None, "") and tick_size is None:
            blockers.append("MARKET_TICK_SIZE_INVALID")
        if (
            snapshot.minimum_distance_points not in (None, "")
            and distance_points is None
        ):
            blockers.append("MARKET_MINIMUM_DISTANCE_INVALID")
        if snapshot.digits is not None and (
            not isinstance(snapshot.digits, int) or isinstance(snapshot.digits, bool)
            or snapshot.digits < 0
        ):
            blockers.append("MARKET_DIGITS_INVALID")
        volume_min = _positive_decimal_or_none(market_material["volume_min"])
        volume_max = _positive_decimal_or_none(market_material["volume_max"])
        volume_step = _positive_decimal_or_none(market_material["volume_step"])
        tick_value = _positive_decimal_or_none(market_material["tick_value"])
        contract_size = _positive_decimal_or_none(market_material["contract_size"])
        if (
            snapshot.symbol == "BTCUSD"
            or _proposal_source(inputs) == MANUAL_OPERATOR_PROPOSAL_SOURCE
        ) and any(
            value is None
            for value in (
                point, tick_size, distance_points, volume_min, volume_max,
                volume_step, tick_value, contract_size,
            )
        ):
            blockers.append("BROKER_SYMBOL_METADATA_MISSING")
        if volume is not None and volume_min is not None and volume < volume_min:
            blockers.append("PROPOSED_VOLUME_BELOW_MINIMUM")
        if volume is not None and volume_max is not None and volume > volume_max:
            blockers.append("PROPOSED_VOLUME_ABOVE_MAXIMUM")
        if (
            volume is not None and volume_min is not None and volume_step is not None
            and (volume - volume_min) % volume_step != 0
        ):
            blockers.append("PROPOSED_VOLUME_STEP_MISMATCH")
        if point is not None and distance_points is not None:
            minimum_distance = point * distance_points

    if semantics is not None:
        _validate_order_prices(
            resolved,
            bid=bid,
            ask=ask,
            minimum_distance=minimum_distance,
            tick_size=tick_size,
            digits=(snapshot.digits if snapshot else None),
            blockers=blockers,
        )
    hash_material = {key: value for key, value in resolved.items() if key not in {
        "blockers", "structured_order_hash"
    }}
    resolved["structured_order_hash"] = _sha256(_canonical_json(hash_material))
    return resolved


def _validate_order_prices(
    resolved: Mapping[str, Any],
    *,
    bid: Decimal | None,
    ask: Decimal | None,
    minimum_distance: Decimal,
    tick_size: Decimal | None,
    digits: int | None,
    blockers: list[str],
) -> None:
    order_type = str(resolved["order_type"])
    entry = _decimal_or_none(resolved["entry_price"])
    trigger = _decimal_or_none(resolved["trigger_price"])
    limit = _decimal_or_none(resolved["limit_price"])
    stop_loss = _decimal_or_none(resolved["stop_loss"])
    take_profit = _decimal_or_none(resolved["take_profit"])
    action = str(resolved["action"])

    if action == AutonomousOrderAction.MARKET.value:
        if entry is not None or trigger is not None or limit is not None:
            blockers.append("MARKET_PRICE_FIELDS_NOT_ALLOWED")
    elif order_type in {
        AutonomousOrderType.BUY_STOP_LIMIT.value,
        AutonomousOrderType.SELL_STOP_LIMIT.value,
    }:
        if trigger is None:
            blockers.append("REQUIRED_TRIGGER_PRICE_MISSING")
        if limit is None:
            blockers.append("REQUIRED_LIMIT_PRICE_MISSING")
        if entry is not None:
            blockers.append("STOP_LIMIT_ENTRY_PRICE_NOT_ALLOWED")
    else:
        if entry is None:
            blockers.append("REQUIRED_ENTRY_PRICE_MISSING")
        if trigger is not None or limit is not None:
            blockers.append("UNEXPECTED_TRIGGER_OR_LIMIT_PRICE")

    price_fields = {
        "ENTRY_PRICE": entry,
        "TRIGGER_PRICE": trigger,
        "LIMIT_PRICE": limit,
        "STOP_LOSS": stop_loss,
        "TAKE_PROFIT": take_profit,
    }
    for name, value in price_fields.items():
        if value is None:
            continue
        if value <= 0:
            blockers.append("INVALID_" + name)
        if tick_size is not None and value % tick_size != 0:
            blockers.append(name + "_NOT_ON_TICK_SIZE")
        if isinstance(digits, int) and digits >= 0 and -value.as_tuple().exponent > digits:
            blockers.append(name + "_EXCEEDS_DIGITS")

    recommendation = ""
    if bid is not None and ask is not None:
        if order_type == AutonomousOrderType.BUY_LIMIT.value and entry is not None:
            recommendation = _validate_pending_relation(
                ask - entry, minimum_distance, "BUY_LIMIT_PRICE_NOT_BELOW_ASK", blockers
            )
        elif order_type == AutonomousOrderType.SELL_LIMIT.value and entry is not None:
            recommendation = _validate_pending_relation(
                entry - bid, minimum_distance, "SELL_LIMIT_PRICE_NOT_ABOVE_BID", blockers
            )
        elif order_type == AutonomousOrderType.BUY_STOP.value and entry is not None:
            recommendation = _validate_pending_relation(
                entry - ask, minimum_distance, "BUY_STOP_PRICE_NOT_ABOVE_ASK", blockers
            )
        elif order_type == AutonomousOrderType.SELL_STOP.value and entry is not None:
            recommendation = _validate_pending_relation(
                bid - entry, minimum_distance, "SELL_STOP_PRICE_NOT_BELOW_BID", blockers
            )
        elif order_type == AutonomousOrderType.BUY_STOP_LIMIT.value and trigger is not None:
            recommendation = _validate_pending_relation(
                trigger - ask, minimum_distance, "BUY_STOP_LIMIT_TRIGGER_NOT_ABOVE_ASK", blockers
            )
            if limit is not None and limit >= trigger:
                blockers.append("BUY_STOP_LIMIT_LIMIT_NOT_BELOW_TRIGGER")
        elif order_type == AutonomousOrderType.SELL_STOP_LIMIT.value and trigger is not None:
            recommendation = _validate_pending_relation(
                bid - trigger, minimum_distance, "SELL_STOP_LIMIT_TRIGGER_NOT_BELOW_BID", blockers
            )
            if limit is not None and limit <= trigger:
                blockers.append("SELL_STOP_LIMIT_LIMIT_NOT_ABOVE_TRIGGER")
    if recommendation:
        resolved["market_recommendation"] = recommendation

    reference_price = (
        ask if order_type == AutonomousOrderType.BUY.value else
        bid if order_type == AutonomousOrderType.SELL.value else
        limit if "STOP_LIMIT" in order_type else entry
    )
    side = str(resolved["side"])
    if reference_price is not None:
        if side == AutonomousOrderSide.BUY.value:
            if stop_loss is not None and stop_loss >= reference_price:
                blockers.append("BUY_STOP_LOSS_NOT_BELOW_REFERENCE")
            if take_profit is not None and take_profit <= reference_price:
                blockers.append("BUY_TAKE_PROFIT_NOT_ABOVE_REFERENCE")
        elif side == AutonomousOrderSide.SELL.value:
            if stop_loss is not None and stop_loss <= reference_price:
                blockers.append("SELL_STOP_LOSS_NOT_ABOVE_REFERENCE")
            if take_profit is not None and take_profit >= reference_price:
                blockers.append("SELL_TAKE_PROFIT_NOT_BELOW_REFERENCE")


def _validate_pending_relation(
    distance: Decimal,
    minimum_distance: Decimal,
    wrong_side_reason: str,
    blockers: list[str],
) -> str:
    if distance <= 0:
        blockers.append(wrong_side_reason)
        return "MARKET_ORDER_REVIEW_RECOMMENDED"
    if minimum_distance > 0 and distance <= minimum_distance:
        blockers.append("PENDING_PRICE_INSIDE_MINIMUM_DISTANCE")
        return "MARKET_ORDER_REVIEW_RECOMMENDED"
    return "PENDING_PRICE_RELATION_VALID"


def _market_snapshot_material(snapshot: AutonomousOrderMarketSnapshot) -> dict[str, Any]:
    values = {}
    for name in (
        "bid", "ask", "point", "tick_size", "minimum_distance_points",
        "volume_min", "volume_max", "volume_step", "tick_value", "contract_size",
    ):
        text, _, _ = _canonical_decimal(getattr(snapshot, name))
        values[name] = text
    return {
        "snapshot_reference": snapshot.snapshot_reference,
        "observed_at": snapshot.observed_at,
        "symbol": snapshot.symbol,
        "broker_symbol": snapshot.broker_symbol,
        "provider_name": snapshot.provider_name,
        "bid": values["bid"],
        "ask": values["ask"],
        "point": values["point"],
        "tick_size": values["tick_size"],
        "digits": snapshot.digits,
        "minimum_distance_points": values["minimum_distance_points"],
        "volume_min": values["volume_min"],
        "volume_max": values["volume_max"],
        "volume_step": values["volume_step"],
        "tick_value": values["tick_value"],
        "contract_size": values["contract_size"],
        "source_refs": sorted(set(snapshot.source_refs)),
    }


def _canonical_decimal(value: Any) -> tuple[str, Decimal | None, bool]:
    if value is None or value == "":
        return "", None, True
    if isinstance(value, bool):
        return str(value), None, False
    raw = str(value).strip()
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return raw, None, False
    if not parsed.is_finite():
        return raw, None, False
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    return canonical or "0", parsed, True


def _decimal_or_none(value: Any) -> Decimal | None:
    _, parsed, valid = _canonical_decimal(value)
    return parsed if valid else None


def _positive_decimal_or_none(value: Any, *, allow_zero: bool = False) -> Decimal | None:
    parsed = _decimal_or_none(value)
    if parsed is None or parsed < 0 or (parsed == 0 and not allow_zero):
        return None
    return parsed


def _candidate_structured_order_hash(candidate: AutonomousDecisionCandidate) -> str:
    material = {
        "side": candidate.side,
        "entry_intent": candidate.entry_intent,
        "order_type": candidate.order_type,
        "action": candidate.action,
        "advisory_action": candidate.advisory_action,
        "entry_price": candidate.entry_price,
        "trigger_price": candidate.trigger_price,
        "limit_price": candidate.limit_price,
        "stop_loss": candidate.stop_loss,
        "take_profit": candidate.take_profit,
        "proposed_volume": candidate.proposed_volume,
        "risk_policy_reference": candidate.risk_policy_reference,
        "structured_reasoning": candidate.structured_reasoning,
        "market_snapshot_reference": candidate.market_snapshot_reference,
        "market_snapshot_provenance_hash": candidate.market_snapshot_provenance_hash,
        "market_recommendation": candidate.market_recommendation,
    }
    return _sha256(_canonical_json(material))


def _action_for_order_type(order_type: str) -> str:
    try:
        return resolve_autonomous_order_action(order_type)
    except ValueError:
        return ""

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
    proposal_source = _proposal_source(inputs)
    if proposal_source not in PROPOSAL_SOURCES:
        blockers.append("PROPOSAL_SOURCE_INVALID")
    if (
        proposal_source == MANUAL_OPERATOR_PROPOSAL_SOURCE
        and not inputs.proposal_source_reference
    ):
        blockers.append("MANUAL_PROPOSAL_SOURCE_REFERENCE_MISSING")
    references = (
        context.context_pack_id,
        method.result_id,
        score.score_report_id,
        risk.decision_id if risk else "",
        inputs.proposal_source_reference,
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


def _proposal_source(inputs: AutonomousDecisionInputs) -> str:
    value = str(inputs.proposal_source or "").strip().upper()
    if value:
        return value
    if inputs.runtime_context.mode == OFFLINE_FIXTURE_MODE:
        return OFFLINE_FIXTURE_PROPOSAL_SOURCE
    return AUTONOMOUS_LLM_PROPOSAL_SOURCE


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
    structured_order: Mapping[str, Any],
) -> dict[str, Any]:
    risk = inputs.risk_result
    return {
        "schema": AUTONOMOUS_DECISION_SCHEMA_VERSION,
        "operating_mode": inputs.runtime_context.mode,
        "symbol_reference": inputs.runtime_context.symbol,
        "broker_symbol_reference": inputs.runtime_context.broker_symbol,
        "timeframe_profile": list(inputs.timeframe_profile),
        "method_selection_summary": str(inputs.method_selection.reasoning_summary or "")[:500],
        "account_context_reference": inputs.account_context_reference,
        "proposal_source": _proposal_source(inputs),
        "proposal_source_reference": inputs.proposal_source_reference,
        "strategy_id": inputs.strategy_id,
        "strategy_version": inputs.strategy_version,
        "normalized_strategy_hash": inputs.normalized_strategy_hash,
        "reasoning_evidence_summary": inputs.reasoning_evidence_summary,
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
        "structured_order": {
            key: structured_order[key]
            for key in (
                "side",
                "entry_intent",
                "order_type",
                "action",
                "advisory_action",
                "entry_price",
                "trigger_price",
                "limit_price",
                "stop_loss",
                "take_profit",
                "proposed_volume",
                "risk_policy_reference",
                "structured_reasoning",
                "market_snapshot_reference",
                "market_snapshot_provenance_hash",
                "market_recommendation",
                "structured_order_hash",
            )
        },
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
    return autonomous_lifecycle_status_reference(inputs.lifecycle_status), "NO_ACTIVE_TARGET"


def autonomous_lifecycle_status_reference(status: MT5RuntimeSupervisorStatus) -> str:
    reference_material = {
        "last_successful_cycle": status.last_successful_cycle,
        "records_inspected": status.records_inspected,
        "state_counts": dict(sorted(status.lifecycle_state_counts.items())),
        "health_reason": status.health_reason,
    }
    return "runtime_lifecycle_" + _sha256(_canonical_json(reference_material))[:24]


def _normalized_direction(direction: str, intent: AutonomousDecisionIntent) -> str:
    if intent not in {AutonomousDecisionIntent.OPEN_POSITION, AutonomousDecisionIntent.CLOSE_POSITION}:
        return ""
    return direction.strip().upper()


def _journal_row(
    candidate: AutonomousDecisionCandidate,
    *,
    market_snapshot: AutonomousOrderMarketSnapshot | None = None,
    lifecycle_status: MT5RuntimeSupervisorStatus | None = None,
    reconciliation_result: MT5ReconciliationReceipt | None = None,
) -> dict[str, Any]:
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
        "protected_candidate": candidate.to_protected_dict(),
    }
    if market_snapshot is not None:
        row["protected_market_snapshot"] = asdict(market_snapshot)
    if lifecycle_status is not None:
        row["protected_runtime_evidence"] = {
            "lifecycle_status": asdict(lifecycle_status),
            "reconciliation_result": (
                asdict(reconciliation_result) if reconciliation_result is not None else None
            ),
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


def _candidate_from_protected_dict(payload: Mapping[str, Any]) -> AutonomousDecisionCandidate:
    allowed = {item.name for item in fields(AutonomousDecisionCandidate)}
    optional_v2 = {
        "strategy_id",
        "strategy_version",
        "normalized_strategy_hash",
        "reasoning_evidence_summary",
    }
    if frozenset(payload) not in {
        frozenset(allowed),
        frozenset(allowed - optional_v2),
    }:
        raise ValueError("candidate payload fields do not match")
    values = dict(payload)
    for name in (
        "strategy_id",
        "strategy_version",
        "normalized_strategy_hash",
        "reasoning_evidence_summary",
    ):
        values.setdefault(name, "")
    for name in (
        "proposed_semantic_parameter_references",
        "knowledge_evidence_references",
        "blocked_reason_codes",
        "structured_reasoning",
        "timeframe_profile",
    ):
        raw = values.get(name)
        if not isinstance(raw, (list, tuple)):
            raise ValueError("candidate tuple field is invalid")
        values[name] = tuple(str(item) for item in raw)
    return AutonomousDecisionCandidate(**values)


def _market_snapshot_from_protected_dict(
    payload: Mapping[str, Any],
) -> AutonomousOrderMarketSnapshot:
    allowed = {item.name for item in fields(AutonomousOrderMarketSnapshot)}
    if set(payload) != allowed:
        raise ValueError("market snapshot payload fields do not match")
    values = dict(payload)
    raw_refs = values.get("source_refs")
    if not isinstance(raw_refs, (list, tuple)):
        raise ValueError("market snapshot source refs are invalid")
    values["source_refs"] = tuple(str(item) for item in raw_refs)
    return AutonomousOrderMarketSnapshot(**values)


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


def _operator_review_reasoning(values: Sequence[str]) -> list[str]:
    sensitive_markers = (
        "password",
        "credential",
        "api_key",
        "token",
        "account_login",
        "account login",
        "ticket_id",
        "deal_id",
        "position_id",
    )
    summaries: list[str] = []
    for value in values[:8]:
        summary = str(value or "").strip()
        if not summary:
            continue
        if any(marker in summary.lower() for marker in sensitive_markers):
            summaries.append("[REDACTED]")
        else:
            summaries.append(summary[:240])
    return summaries


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
