from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.config import Config
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)


DEFAULT_MONITOR_JOURNAL_PATH = (
    "data/trading/execution_journal/autonomous_candidate_monitor.jsonl"
)

_FORBIDDEN_FLAGS = (
    "TRADING_AUTONOMOUS_POLICY_GATE_ENABLED",
    "TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED",
    "TRADING_AUTONOMOUS_MANAGEMENT_ELIGIBILITY_ENABLED",
    "TRADING_EXECUTION_LIVE_ENABLED",
    "TRADING_EXECUTION_AUTONOMOUS_ENABLED",
    "TRADING_MT5_LIVE_EXECUTION_ENABLED",
    "TRADING_MT5_ORDER_SEND_ENABLED",
    "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION",
    "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND",
    "TRADING_MT5_LIVE_ADAPTER_ENABLED",
    "TRADING_MT5_CONTROLLED_EXECUTION_ENABLED",
    "TRADING_MT5_PENDING_SUBMISSION_ENABLED",
    "TRADING_MT5_PENDING_LIMIT_ENABLED",
    "TRADING_MT5_PENDING_STOP_ENABLED",
    "TRADING_MT5_PENDING_STOP_LIMIT_ENABLED",
    "TRADING_MT5_CONTROLLED_MANAGEMENT_ENABLED",
    "TRADING_MT5_MANAGEMENT_CANCEL_ALLOWED",
    "TRADING_MT5_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED",
    "TRADING_MT5_MANAGEMENT_POSITION_CLOSE_ALLOWED",
)


class AutonomousCandidateMonitorError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutonomousCandidateMonitorResult:
    status: str
    symbol: str
    broker_symbol: str = ""
    timeframes: tuple[str, ...] = ()
    closed_bar_time: str = ""
    candidate_reference: str = ""
    intent: str = ""
    blocker: str = ""
    validation_valid: bool = False
    generation_count: int = 0
    proposal_provider_max_invocations: int = 0
    execution_authority: bool = False
    export_called: bool = False
    submission_called: bool = False
    order_send_called: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "timeframes": list(self.timeframes),
            "closed_bar_time": self.closed_bar_time,
            "candidate_reference": self.candidate_reference,
            "intent": self.intent,
            "blocker": self.blocker,
            "validation_valid": self.validation_valid,
            "generation_count": self.generation_count,
            "proposal_provider_max_invocations": self.proposal_provider_max_invocations,
            "execution_authority": False,
            "export_called": False,
            "submission_called": False,
            "order_send_called": False,
        }


class AutonomousCandidateMonitorJournal:
    _required = {
        "event_id",
        "created_at",
        "profile_id",
        "symbol",
        "broker_symbol",
        "timeframes",
        "closed_bar_time",
        "phase",
        "status",
        "candidate_reference",
        "intent",
        "blocker",
        "validation_valid",
        "generation_count",
        "execution_authority",
        "export_called",
        "submission_called",
        "order_send_called",
        "metadata_redacted",
        "record_hash",
    }

    def __init__(self, path: str | Path = DEFAULT_MONITOR_JOURNAL_PATH):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_UNAVAILABLE") from exc
        records: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict) or set(row) != self._required:
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT")
            expected = _record_hash({key: value for key, value in row.items() if key != "record_hash"})
            if not hmac.compare_digest(str(row["record_hash"]), expected):
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT")
            records.append(row)
        return records

    def latest(self, profile_id: str | None = None) -> dict[str, Any] | None:
        records = self.records()
        if profile_id:
            records = [row for row in records if row["profile_id"] == profile_id]
        return records[-1] if records else None

    def claim(
        self,
        *,
        profile_id: str,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
    ) -> bool:
        with self._exclusive_lock():
            if any(
                row["profile_id"] == profile_id
                and row["closed_bar_time"] == closed_bar_time
                for row in self.records()
            ):
                return False
            self._append(
                _row(
                    profile_id=profile_id,
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    timeframes=timeframes,
                    closed_bar_time=closed_bar_time,
                    phase="STARTED",
                    status="STARTED",
                )
            )
            return True

    def complete(self, result: AutonomousCandidateMonitorResult) -> None:
        profile_id = monitor_profile_id(result.symbol, result.timeframes)
        with self._exclusive_lock():
            matching = [
                row
                for row in self.records()
                if row["profile_id"] == profile_id
                and row["closed_bar_time"] == result.closed_bar_time
            ]
            if not matching or matching[0]["phase"] != "STARTED":
                raise AutonomousCandidateMonitorError("MONITOR_CLAIM_MISSING")
            if any(row["phase"] == "COMPLETED" for row in matching):
                return
            self._append(
                _row(
                    profile_id=profile_id,
                    symbol=result.symbol,
                    broker_symbol=result.broker_symbol,
                    timeframes=result.timeframes,
                    closed_bar_time=result.closed_bar_time,
                    phase="COMPLETED",
                    status=result.status,
                    candidate_reference=result.candidate_reference,
                    intent=result.intent,
                    blocker=result.blocker,
                    validation_valid=result.validation_valid,
                    generation_count=result.generation_count,
                )
            )

    def _append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_UNAVAILABLE") from exc

    def _exclusive_lock(self):
        journal = self

        class LockContext:
            def __enter__(self):
                journal.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.fd = os.open(
                        journal.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                except (FileExistsError, OSError) as exc:
                    raise AutonomousCandidateMonitorError(
                        "MONITOR_JOURNAL_UNAVAILABLE"
                    ) from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                journal.lock_path.unlink(missing_ok=True)

        return LockContext()


class AutonomousCandidateMonitor:
    def __init__(
        self,
        *,
        feature_service: Any,
        input_assembler: Any,
        decision_orchestrator: Any | None = None,
        journal: AutonomousCandidateMonitorJournal | None = None,
    ) -> None:
        self.feature_service = feature_service
        self.input_assembler = input_assembler
        self.decision_orchestrator = decision_orchestrator or AutonomousDecisionOrchestrator()
        self.journal = journal or AutonomousCandidateMonitorJournal()

    def run_once(
        self, *, symbol: str, timeframes: Iterable[str]
    ) -> AutonomousCandidateMonitorResult:
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_timeframes = tuple(str(item).strip().upper() for item in timeframes if str(item).strip())
        if not normalized_symbol or not normalized_timeframes:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_PROFILE_INVALID",
            )
        enabled = [name for name in _FORBIDDEN_FLAGS if bool(getattr(Config, name, False))]
        if enabled:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_EXECUTION_PERMISSION_ENABLED",
            )
        try:
            feature_result = self.feature_service.build_features(
                normalized_symbol, normalized_timeframes, 2
            )
            quality = str(getattr(feature_result.quality_report, "status", "")).upper()
            snapshot = feature_result.bundle.timeframes.get(normalized_timeframes[0])
            closed_bar_time = snapshot.bars[-1].timestamp if snapshot and snapshot.bars else ""
            broker_symbol = str(feature_result.bundle.broker_symbol or "")
        except Exception:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_MARKET_SNAPSHOT_UNAVAILABLE",
            )
        if quality != "COMPLETE" or not closed_bar_time:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, broker_symbol, normalized_timeframes,
                closed_bar_time, blocker="MONITOR_MARKET_INPUT_NOT_FRESH",
            )

        profile_id = monitor_profile_id(normalized_symbol, normalized_timeframes)
        if not self.journal.claim(
            profile_id=profile_id,
            symbol=normalized_symbol,
            broker_symbol=broker_symbol,
            timeframes=normalized_timeframes,
            closed_bar_time=closed_bar_time,
        ):
            latest = self.journal.latest(profile_id)
            return AutonomousCandidateMonitorResult(
                "NO_NEW_BAR" if latest and latest["phase"] == "COMPLETED" else "RESULT_UNKNOWN",
                normalized_symbol,
                broker_symbol,
                normalized_timeframes,
                closed_bar_time,
                blocker=("" if latest and latest["phase"] == "COMPLETED" else "MONITOR_PREVIOUS_ATTEMPT_INCOMPLETE"),
            )

        result = self._generate(normalized_symbol, broker_symbol, normalized_timeframes, closed_bar_time)
        self.journal.complete(result)
        return result

    def _generate(
        self,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
    ) -> AutonomousCandidateMonitorResult:
        try:
            inputs = self.input_assembler.build(symbol=symbol, timeframes=timeframes)
            run_result = self.decision_orchestrator.run_once(inputs)
            if not isinstance(run_result, AutonomousDecisionRunResult):
                raise TypeError("invalid orchestrator result")
            if not run_result.validation.valid or not run_result.persistence_safe:
                blocker = run_result.journal_warning or (
                    run_result.validation.issues[0]
                    if run_result.validation.issues
                    else "MONITOR_RESULT_INVALID"
                )
                return AutonomousCandidateMonitorResult(
                    "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                    intent=run_result.candidate.intent, blocker=blocker,
                    generation_count=1, proposal_provider_max_invocations=1,
                )
            return AutonomousCandidateMonitorResult(
                "GENERATED", symbol, broker_symbol, timeframes, closed_bar_time,
                candidate_reference=run_result.candidate.candidate_reference,
                intent=run_result.candidate.intent, validation_valid=True,
                generation_count=1, proposal_provider_max_invocations=1,
            )
        except OperatorCandidateInputError as exc:
            no_action = exc.blockers == ("STRUCTURED_PROPOSAL_NOT_AVAILABLE",)
            return AutonomousCandidateMonitorResult(
                "NO_ACTION" if no_action else "BLOCKED",
                symbol, broker_symbol, timeframes, closed_bar_time,
                intent="NO_ACTION" if no_action else "",
                blocker=str(exc), generation_count=1,
                proposal_provider_max_invocations=1,
            )
        except Exception:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                blocker="MONITOR_GENERATION_FAILED", generation_count=1,
                proposal_provider_max_invocations=1,
            )


def monitor_profile_id(symbol: str, timeframes: Iterable[str]) -> str:
    material = str(symbol).upper() + "|" + ",".join(str(item).upper() for item in timeframes)
    return "monitor_profile_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _row(
    *,
    profile_id: str,
    symbol: str,
    broker_symbol: str,
    timeframes: tuple[str, ...],
    closed_bar_time: str,
    phase: str,
    status: str,
    candidate_reference: str = "",
    intent: str = "",
    blocker: str = "",
    validation_valid: bool = False,
    generation_count: int = 0,
) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": "monitor_event_" + hashlib.sha256(
            f"{profile_id}|{closed_bar_time}|{phase}|{created_at}".encode("utf-8")
        ).hexdigest()[:20],
        "created_at": created_at,
        "profile_id": profile_id,
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "timeframes": list(timeframes),
        "closed_bar_time": closed_bar_time,
        "phase": phase,
        "status": status,
        "candidate_reference": candidate_reference,
        "intent": intent,
        "blocker": blocker,
        "validation_valid": validation_valid,
        "generation_count": generation_count,
        "execution_authority": False,
        "export_called": False,
        "submission_called": False,
        "order_send_called": False,
        "metadata_redacted": True,
    }
    payload["record_hash"] = _record_hash(payload)
    return payload


def _record_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
