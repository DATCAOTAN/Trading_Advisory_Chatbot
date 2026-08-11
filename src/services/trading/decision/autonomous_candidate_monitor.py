from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.config import Config
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
    autonomous_monitor_permissions_coherent,
)
DEFAULT_MONITOR_JOURNAL_PATH = (
    "data/trading/execution_journal/autonomous_candidate_monitor.jsonl"
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
    account_scope: str = ""
    coordinator_status: str = ""
    authorization_source: str = ""
    pre_submit_ready: bool = False
    strategy_evaluation: Mapping[str, Any] = field(default_factory=dict, repr=False)

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
            "account_scope": self.account_scope,
            "coordinator_status": self.coordinator_status,
            "authorization_source": self.authorization_source,
            "pre_submit_ready": bool(self.pre_submit_ready),
            "strategy_evaluation": dict(self.strategy_evaluation or {}),
        }


class AutonomousCandidateMonitorJournal:
    _required = {
        "event_id",
        "created_at",
        "profile_id",
        "account_scope",
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
        "coordinator_status",
        "authorization_source",
        "pre_submit_ready",
        "strategy_evaluation",
        "execution_authority",
        "export_called",
        "submission_called",
        "order_send_called",
        "metadata_redacted",
        "record_hash",
    }
    _legacy_required = _required - {
        "account_scope",
        "coordinator_status",
        "authorization_source",
        "pre_submit_ready",
        "strategy_evaluation",
    }
    _previous_required = _required - {"strategy_evaluation"}

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
            if not isinstance(row, dict):
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT")
            keys = frozenset(row)
            if keys not in {
                frozenset(self._required),
                frozenset(self._previous_required),
                frozenset(self._legacy_required),
            }:
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT")
            expected = _record_hash({key: value for key, value in row.items() if key != "record_hash"})
            if not hmac.compare_digest(str(row["record_hash"]), expected):
                raise AutonomousCandidateMonitorError("MONITOR_JOURNAL_CORRUPT")
            row.setdefault("account_scope", "legacy")
            row.setdefault("coordinator_status", row.get("status", ""))
            row.setdefault("authorization_source", "")
            row.setdefault("pre_submit_ready", False)
            row.setdefault("strategy_evaluation", {})
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
        account_scope: str,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
        strategy_reference: str = "legacy",
    ) -> bool:
        with self._exclusive_lock():
            rows = self.records()
            def same_profile(row):
                return row["profile_id"] == profile_id or (
                    row["account_scope"] == "legacy"
                    and row["symbol"] == symbol
                    and tuple(row["timeframes"]) == timeframes
                )

            duplicate = any(
                same_profile(row)
                and row["closed_bar_time"] == closed_bar_time
                for row in rows
            )
            unresolved = any(
                same_profile(row)
                and row["phase"] == "STARTED"
                and not any(
                    same_profile(completed)
                    and completed["closed_bar_time"] == row["closed_bar_time"]
                    and completed["phase"] == "COMPLETED"
                    for completed in rows
                )
                for row in rows
            )
            if duplicate or unresolved:
                return False
            self._append(
                _row(
                    profile_id=profile_id,
                    account_scope=account_scope,
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    timeframes=timeframes,
                    closed_bar_time=closed_bar_time,
                    strategy_evaluation={"strategy_reference": strategy_reference},
                    phase="STARTED",
                    status="STARTED",
                )
            )
            return True

    def complete(self, result: AutonomousCandidateMonitorResult) -> None:
        profile_id = monitor_profile_id(
            result.symbol,
            result.timeframes,
            result.account_scope,
            str((result.strategy_evaluation or {}).get("strategy_reference") or "legacy"),
        )
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
                    account_scope=result.account_scope,
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
                    coordinator_status=result.coordinator_status,
                    authorization_source=result.authorization_source,
                    pre_submit_ready=result.pre_submit_ready,
                    strategy_evaluation=result.strategy_evaluation or {},
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
        completed_bar_handler: Any,
        journal: AutonomousCandidateMonitorJournal | None = None,
    ) -> None:
        self.feature_service = feature_service
        self.completed_bar_handler = completed_bar_handler
        self.journal = journal or AutonomousCandidateMonitorJournal()

    def run_once(
        self,
        *,
        symbol: str,
        timeframes: Iterable[str],
        account_scope: str,
        strategy_reference: str = "legacy",
    ) -> AutonomousCandidateMonitorResult:
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_account_scope = str(account_scope or "").strip().lower()
        normalized_timeframes = tuple(str(item).strip().upper() for item in timeframes if str(item).strip())
        normalized_strategy_reference = str(strategy_reference or "").strip()
        if (
            not normalized_symbol
            or not normalized_timeframes
            or not normalized_account_scope
            or not normalized_strategy_reference
        ):
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_PROFILE_INVALID", account_scope=normalized_account_scope,
            )
        permission_config = MT5LiveAdapterPreSubmitConfig.from_config(Config)
        if not autonomous_monitor_permissions_coherent(permission_config, Config):
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_PERMISSION_STATE_INCOHERENT", account_scope=normalized_account_scope,
            )
        try:
            feature_result = self.feature_service.build_features(
                normalized_symbol,
                normalized_timeframes,
                Config.MARKET_DEFAULT_CANDLE_COUNT,
            )
            quality = str(getattr(feature_result.quality_report, "status", "")).upper()
            snapshot = feature_result.bundle.timeframes.get(normalized_timeframes[0])
            closed_bar_time = snapshot.bars[-1].timestamp if snapshot and snapshot.bars else ""
            broker_symbol = str(feature_result.bundle.broker_symbol or "")
        except Exception:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, timeframes=normalized_timeframes,
                blocker="MONITOR_MARKET_SNAPSHOT_UNAVAILABLE", account_scope=normalized_account_scope,
            )
        if quality != "COMPLETE" or not closed_bar_time:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, broker_symbol, normalized_timeframes,
                closed_bar_time, blocker="MONITOR_MARKET_INPUT_NOT_FRESH",
                account_scope=normalized_account_scope,
            )

        profile_id = monitor_profile_id(
            normalized_symbol,
            normalized_timeframes,
            normalized_account_scope,
            normalized_strategy_reference,
        )
        if not self.journal.claim(
            profile_id=profile_id,
            account_scope=normalized_account_scope,
            symbol=normalized_symbol,
            broker_symbol=broker_symbol,
            timeframes=normalized_timeframes,
            closed_bar_time=closed_bar_time,
            strategy_reference=normalized_strategy_reference,
        ):
            latest = self.journal.latest(profile_id)
            return AutonomousCandidateMonitorResult(
                "NO_NEW_BAR" if latest and latest["phase"] == "COMPLETED" else "RESULT_UNKNOWN",
                normalized_symbol,
                broker_symbol,
                normalized_timeframes,
                closed_bar_time,
                blocker=("" if latest and latest["phase"] == "COMPLETED" else "MONITOR_PREVIOUS_ATTEMPT_INCOMPLETE"),
                account_scope=normalized_account_scope,
            )

        try:
            result = self.completed_bar_handler(
                symbol=normalized_symbol,
                broker_symbol=broker_symbol,
                timeframes=normalized_timeframes,
                closed_bar_time=closed_bar_time,
                account_scope=normalized_account_scope,
            )
            if not isinstance(result, AutonomousCandidateMonitorResult):
                raise TypeError("invalid completed-bar handler result")
        except Exception:
            result = AutonomousCandidateMonitorResult(
                "BLOCKED", normalized_symbol, broker_symbol, normalized_timeframes,
                closed_bar_time, blocker="MONITOR_COORDINATOR_FAILED",
                account_scope=normalized_account_scope,
            )
        if not result.strategy_evaluation:
            result = replace(
                result,
                strategy_evaluation={
                    "strategy_reference": normalized_strategy_reference
                },
            )
        self.journal.complete(result)
        return result


def monitor_profile_id(
    symbol: str,
    timeframes: Iterable[str],
    account_scope: str = "legacy",
    strategy_reference: str = "legacy",
) -> str:
    material = (
        str(account_scope).lower()
        + "|"
        + str(symbol).upper()
        + "|"
        + ",".join(str(item).upper() for item in timeframes)
        + "|"
        + str(strategy_reference)
    )
    return "monitor_profile_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _row(
    *,
    profile_id: str,
    account_scope: str,
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
    coordinator_status: str = "",
    authorization_source: str = "",
    pre_submit_ready: bool = False,
    strategy_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": "monitor_event_" + hashlib.sha256(
            f"{profile_id}|{closed_bar_time}|{phase}|{created_at}".encode("utf-8")
        ).hexdigest()[:20],
        "created_at": created_at,
        "profile_id": profile_id,
        "account_scope": account_scope,
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
        "coordinator_status": coordinator_status,
        "authorization_source": authorization_source,
        "pre_submit_ready": bool(pre_submit_ready),
        "strategy_evaluation": dict(strategy_evaluation or {}),
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
