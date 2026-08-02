from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from src.services.trading.execution.mt5_bridge_write_skeleton.client import (
    MT5BridgeWriteSkeletonClient,
)
from tools.mt5_bridge.execution import (
    ProtectedExecutionJournal,
    ProtectedExecutionJournalError,
)


class MT5LifecycleState(str, Enum):
    UNKNOWN = "UNKNOWN"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    BROKER_ACCEPTED = "BROKER_ACCEPTED"
    ORDER_ACTIVE = "ORDER_ACTIVE"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_PARTIALLY_REDUCED = "POSITION_PARTIALLY_REDUCED"
    POSITION_CLOSED = "POSITION_CLOSED"
    BROKER_REJECTED = "BROKER_REJECTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    INCONSISTENT = "INCONSISTENT"


DISCREPANCY_REASONS = {
    "ACCOUNT_CONTEXT_CHANGED",
    "CONFIRMED_BROKER_EVIDENCE_ABSENT",
    "UNMATCHED_BROKER_POSITION",
    "DUPLICATE_BROKER_MATCH",
    "CONFLICTING_VOLUME_OR_DIRECTION",
    "POSITION_CLOSED_WITHOUT_CLOSING_DEAL",
    "STALE_SUBMISSION_STATE",
    "EXECUTION_JOURNAL_CORRUPT",
    "EXECUTION_JOURNAL_UNAVAILABLE",
    "LIFECYCLE_JOURNAL_CORRUPT",
    "LIFECYCLE_JOURNAL_UNAVAILABLE",
    "BRIDGE_UNAVAILABLE",
    "SNAPSHOT_INVALID",
    "EXECUTION_RECORD_INCOMPLETE",
}


@dataclass(frozen=True)
class MT5PositionSupervisorConfig:
    enabled: bool = True
    interval_seconds: float = 30.0
    history_window_seconds: int = 86_400
    stale_submission_seconds: int = 30
    execution_journal_path: str = "data/trading/execution_journal/mt5_controlled_execution.jsonl"
    lifecycle_journal_path: str = "data/trading/execution_journal/mt5_position_lifecycle.jsonl"
    bridge_url: str = "http://host.docker.internal:8765"
    bridge_timeout_seconds: float = 10.0
    auth_token: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("supervisor interval must be positive")
        if self.history_window_seconds <= 0 or self.history_window_seconds > 86_400:
            raise ValueError("history window must be between 1 and 86400 seconds")
        if self.stale_submission_seconds < 0:
            raise ValueError("stale submission threshold cannot be negative")
        if not self.execution_journal_path or not self.lifecycle_journal_path:
            raise ValueError("supervisor journal paths are required")

    @classmethod
    def from_config(cls) -> "MT5PositionSupervisorConfig":
        from src.config import Config

        return cls(
            enabled=Config.TRADING_MT5_POSITION_SUPERVISOR_ENABLED,
            interval_seconds=Config.TRADING_MT5_POSITION_SUPERVISOR_INTERVAL_SECONDS,
            history_window_seconds=Config.TRADING_MT5_POSITION_SUPERVISOR_HISTORY_WINDOW_SECONDS,
            stale_submission_seconds=Config.MT5_BRIDGE_RECONCILIATION_SUBMISSION_STALE_SECONDS,
            execution_journal_path=Config.TRADING_MT5_POSITION_SUPERVISOR_EXECUTION_JOURNAL_PATH,
            lifecycle_journal_path=Config.TRADING_MT5_POSITION_SUPERVISOR_LIFECYCLE_JOURNAL_PATH,
            bridge_url=Config.MT5_BRIDGE_URL,
            bridge_timeout_seconds=Config.TRADING_MT5_CONTROLLED_EXECUTION_HTTP_TIMEOUT_SECONDS,
            auth_token=Config.TRADING_MT5_CONTROLLED_EXECUTION_AUTH_TOKEN,
        )


@dataclass(frozen=True)
class MT5LifecycleObservation:
    observation_id: str
    protected_execution_reference: str
    lifecycle_state: str
    previous_lifecycle_state: str
    observation_timestamp: str
    account_fingerprint_hash: str
    evidence_classification: str
    protected_broker_references: dict[str, list[str]]
    discrepancy_reason: str
    source_snapshot_reference: str
    observation_hash: str
    metadata_redacted: bool = True
    record_type: str = "LIFECYCLE_OBSERVATION"

    def to_protected_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MT5RuntimeSupervisorStatus:
    supervisor_status: str = "NOT_STARTED"
    last_successful_cycle: str | None = None
    last_cycle_duration_ms: float = 0.0
    lifecycle_state_counts: dict[str, int] = field(default_factory=dict)
    discrepancy_count: int = 0
    bridge_available: bool = False
    account_context_match: bool = False
    account_fingerprint_prefix: str = ""
    records_inspected: int = 0
    observations_appended: int = 0
    active_position_count: int = 0
    trades_today: int = 0
    loss_today: str = "0"
    terminal_trade_allowed: bool = False
    account_trade_allowed: bool = False
    mandate_limit_evidence_available: bool = False
    health_reason: str = "NOT_STARTED"
    live_submission_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    automatic_retry_allowed: bool = False
    kill_switch_engaged: bool = True
    metadata_redacted: bool = True

    def to_safe_dict(self) -> dict[str, Any]:
        return asdict(self)


class MT5LifecycleJournalError(RuntimeError):
    """Fail-closed lifecycle persistence error with a public-safe reason."""


class MT5LifecycleJournal:
    _process_lock = threading.Lock()
    _required_keys = {
        "record_type",
        "observation_id",
        "protected_execution_reference",
        "lifecycle_state",
        "previous_lifecycle_state",
        "observation_timestamp",
        "account_fingerprint_hash",
        "evidence_classification",
        "protected_broker_references",
        "discrepancy_reason",
        "source_snapshot_reference",
        "observation_hash",
        "metadata_redacted",
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def observations(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_UNAVAILABLE") from exc
        rows: list[dict[str, Any]] = []
        latest: dict[str, str] = {}
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict) or set(row) != self._required_keys:
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_CORRUPT")
            reference = str(row.get("protected_execution_reference", ""))
            state = str(row.get("lifecycle_state", ""))
            previous = str(row.get("previous_lifecycle_state", ""))
            if (
                row.get("record_type") != "LIFECYCLE_OBSERVATION"
                or row.get("metadata_redacted") is not True
                or state not in {item.value for item in MT5LifecycleState}
                or previous not in {item.value for item in MT5LifecycleState}
                or not reference
                or previous != latest.get(reference, MT5LifecycleState.UNKNOWN.value)
                or not _valid_hash(row.get("account_fingerprint_hash"), allow_empty=True)
                or not _protected_references_valid(row.get("protected_broker_references"))
            ):
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_CORRUPT")
            expected_hash = _observation_hash(row)
            if not hmac.compare_digest(str(row.get("observation_hash", "")), expected_hash):
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_CORRUPT")

            latest[reference] = state
            rows.append(row)
        return rows

    def latest_by_execution(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in self.observations():
            latest[row["protected_execution_reference"]] = row
        return latest

    def append_if_changed(self, observation: MT5LifecycleObservation) -> bool:
        with self._exclusive_lock():
            latest = self.latest_by_execution().get(observation.protected_execution_reference)
            if latest and latest["observation_hash"] == observation.observation_hash:
                return False
            if observation.previous_lifecycle_state != (
                latest["lifecycle_state"] if latest else MT5LifecycleState.UNKNOWN.value
            ):
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_CONFLICT")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(observation.to_protected_dict(), ensure_ascii=True, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_UNAVAILABLE") from exc
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
                    raise MT5LifecycleJournalError("LIFECYCLE_JOURNAL_UNAVAILABLE") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    journal.lock_path.unlink()
                finally:
                    journal._process_lock.release()

        return LockContext()


@dataclass(frozen=True)
class _Classification:
    state: MT5LifecycleState
    evidence: str
    discrepancy: str
    broker_references: dict[str, list[str]]
    matched_position_hashes: frozenset[str] = frozenset()


class MT5PositionLifecycleSupervisor:
    _registry_lock = threading.Lock()
    _active_paths: set[str] = set()
    _cycle_locks: dict[str, threading.Lock] = {}

    def __init__(
        self,
        config: MT5PositionSupervisorConfig | None = None,
        *,
        bridge_client: Any | None = None,
        execution_journal: ProtectedExecutionJournal | None = None,
        lifecycle_journal: MT5LifecycleJournal | None = None,
    ):
        self.config = config or MT5PositionSupervisorConfig.from_config()
        self.bridge_client = bridge_client or MT5BridgeWriteSkeletonClient(
            self.config.bridge_url, timeout_seconds=self.config.bridge_timeout_seconds
        )
        self.execution_journal = execution_journal or ProtectedExecutionJournal(
            self.config.execution_journal_path
        )
        self.lifecycle_journal = lifecycle_journal or MT5LifecycleJournal(
            self.config.lifecycle_journal_path
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = MT5RuntimeSupervisorStatus()
        path_key = str(Path(self.config.lifecycle_journal_path).resolve()).lower()
        self._path_key = path_key
        with self._registry_lock:
            self._cycle_lock = self._cycle_locks.setdefault(path_key, threading.Lock())

    def status(self) -> MT5RuntimeSupervisorStatus:
        return self._status

    def start(self) -> None:
        if not self.config.enabled:
            self._status = MT5RuntimeSupervisorStatus(
                supervisor_status="DISABLED", health_reason="SUPERVISOR_DISABLED"
            )
            return
        with self._registry_lock:
            if self._path_key in self._active_paths:
                raise RuntimeError("supervisor already active for lifecycle journal")
            self._active_paths.add(self._path_key)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="mt5-position-supervisor", daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout_seconds))
            if self._thread.is_alive():
                raise RuntimeError("supervisor did not stop cleanly")
        with self._registry_lock:
            self._active_paths.discard(self._path_key)
        self._thread = None

    def run_once(self) -> MT5RuntimeSupervisorStatus:
        started = perf_counter()
        if not self.config.enabled:
            self._status = MT5RuntimeSupervisorStatus(
                supervisor_status="DISABLED", health_reason="SUPERVISOR_DISABLED"
            )
            return self._status
        if not self._cycle_lock.acquire(blocking=False):
            self._status = MT5RuntimeSupervisorStatus(
                supervisor_status="CYCLE_SKIPPED_OVERLAP",
                health_reason="OVERLAPPING_CYCLE_PREVENTED",
            )
            return self._status
        try:
            return self._run_cycle(started)
        finally:
            self._cycle_lock.release()

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                status = self.run_once()
                if status.supervisor_status == "PERSISTENCE_UNSAFE":
                    break
                self._stop_event.wait(self.config.interval_seconds)
        finally:
            with self._registry_lock:
                self._active_paths.discard(self._path_key)

    def _run_cycle(self, started: float) -> MT5RuntimeSupervisorStatus:
        try:
            latest = self.lifecycle_journal.latest_by_execution()
        except MT5LifecycleJournalError as exc:
            return self._set_failure(started, "PERSISTENCE_UNSAFE", str(exc))
        try:
            records = self.execution_journal.execution_records()
        except ProtectedExecutionJournalError as exc:
            reason = str(exc)
            if reason not in {"EXECUTION_JOURNAL_CORRUPT", "EXECUTION_JOURNAL_UNAVAILABLE"}:
                reason = "EXECUTION_JOURNAL_CORRUPT"
            return self._set_failure(started, "PERSISTENCE_UNSAFE", reason)
        tags = [
            str(record.get("protected_execution", {}).get("correlation_tag", ""))
            for record in records
        ]
        tags = list(dict.fromkeys(tag for tag in tags if tag))[:100]
        try:
            snapshot = self.bridge_client.lifecycle_snapshot(
                self.config.history_window_seconds, tags, self.config.auth_token
            )
        except Exception:
            return self._bridge_failure(started, latest, "BRIDGE_UNAVAILABLE")
        try:
            _validate_snapshot(snapshot)
        except ValueError:
            return self._bridge_failure(started, latest, "SNAPSHOT_INVALID")
        if snapshot.get("status") != "OK" or snapshot.get("terminal_connected") is not True:
            return self._bridge_failure(started, latest, "BRIDGE_UNAVAILABLE")

        counts: Counter[str] = Counter()
        discrepancies = 0
        appended = 0
        matched_positions: set[str] = set()
        account_matches: list[bool] = []
        for record in records:
            classification = _classify_record(record, snapshot, self.config.stale_submission_seconds)
            reference = _execution_reference(record)
            previous = latest.get(reference, {}).get("lifecycle_state", MT5LifecycleState.UNKNOWN.value)
            observation = _make_observation(reference, previous, classification, snapshot)
            if self.lifecycle_journal.append_if_changed(observation):
                appended += 1
                latest[reference] = observation.to_protected_dict()
            counts[classification.state.value] += 1
            discrepancies += int(bool(classification.discrepancy))
            matched_positions.update(classification.matched_position_hashes)
            account_matches.append(
                hmac.compare_digest(
                    str(record.get("account_context_fingerprint", "")),
                    str(snapshot.get("account_context_fingerprint", "")),
                )
            )

        if not records or all(account_matches):
            unmatched_positions = snapshot.get("positions", [])
        else:
            unmatched_positions = []
        for position in unmatched_positions:
            position_hash = str(position.get("broker_reference_hash", ""))
            if position_hash and position_hash not in matched_positions:
                classification = _Classification(
                    MT5LifecycleState.INCONSISTENT,
                    "UNMATCHED_POSITION",
                    "UNMATCHED_BROKER_POSITION",
                    {"orders": [], "deals": [], "positions": [position_hash]},
                    frozenset({position_hash}),
                )
                reference = "unmatched_position_" + position_hash[:24]
                previous = latest.get(reference, {}).get("lifecycle_state", MT5LifecycleState.UNKNOWN.value)
                observation = _make_observation(reference, previous, classification, snapshot)
                if self.lifecycle_journal.append_if_changed(observation):
                    appended += 1
                    latest[reference] = observation.to_protected_dict()
                counts[classification.state.value] += 1
                discrepancies += 1

        completed_at = _now()
        self._status = MT5RuntimeSupervisorStatus(
            supervisor_status="HEALTHY" if discrepancies == 0 else "DEGRADED",
            last_successful_cycle=completed_at,
            last_cycle_duration_ms=(perf_counter() - started) * 1000,
            lifecycle_state_counts=dict(sorted(counts.items())),
            discrepancy_count=discrepancies,
            bridge_available=True,
            account_context_match=all(account_matches) if account_matches else True,
            account_fingerprint_prefix=str(snapshot.get("account_context_fingerprint", ""))[:12],
            records_inspected=len(records),
            observations_appended=appended,
            active_position_count=int(snapshot.get("active_position_count", 0)),
            trades_today=int(snapshot.get("trades_today", 0)),
            loss_today=str(snapshot.get("loss_today", "0")),
            terminal_trade_allowed=snapshot.get("terminal_trade_allowed") is True,
            account_trade_allowed=snapshot.get("account_trade_allowed") is True,
            mandate_limit_evidence_available=all(
                key in snapshot
                for key in ("active_position_count", "trades_today", "loss_today")
            ),
            health_reason="OK" if discrepancies == 0 else "DISCREPANCIES_DETECTED",
        )
        return self._status

    def _bridge_failure(
        self, started: float, latest: Mapping[str, Mapping[str, Any]], reason: str
    ) -> MT5RuntimeSupervisorStatus:
        reference = "runtime_bridge_health"
        previous = latest.get(reference, {}).get("lifecycle_state", MT5LifecycleState.UNKNOWN.value)
        classification = _Classification(
            MT5LifecycleState.INCONSISTENT,
            "QUERY_FAILED",
            reason,
            {"orders": [], "deals": [], "positions": []},
        )
        snapshot = {
            "account_context_fingerprint": "",
            "snapshot_reference": "bridge_unavailable",
        }
        try:
            self.lifecycle_journal.append_if_changed(
                _make_observation(reference, previous, classification, snapshot)
            )
        except MT5LifecycleJournalError as exc:
            return self._set_failure(started, "PERSISTENCE_UNSAFE", str(exc))
        return self._set_failure(started, "BLOCKED", reason, bridge_available=False)

    def _set_failure(
        self, started: float, status: str, reason: str, *, bridge_available: bool = False
    ) -> MT5RuntimeSupervisorStatus:
        self._status = MT5RuntimeSupervisorStatus(
            supervisor_status=status,
            last_cycle_duration_ms=(perf_counter() - started) * 1000,
            discrepancy_count=1,
            bridge_available=bridge_available,
            health_reason=reason,
        )
        return self._status


def _classify_record(
    record: Mapping[str, Any], snapshot: Mapping[str, Any], stale_seconds: int
) -> _Classification:
    protected = record.get("protected_execution", {})
    required = {
        "protected_execution_reference",
        "correlation_identity",
        "correlation_tag",
        "symbol",
        "order_type",
        "volume",
    }
    if not isinstance(protected, Mapping) or any(not protected.get(key) for key in required):
        return _inconsistent("EXECUTION_RECORD_INCOMPLETE")
    if not hmac.compare_digest(
        str(record.get("account_context_fingerprint", "")),
        str(snapshot.get("account_context_fingerprint", "")),
    ):
        return _inconsistent("ACCOUNT_CONTEXT_CHANGED")
    symbol = str(protected["symbol"])
    direction = str(protected["order_type"]).upper()
    tag = str(protected["correlation_tag"])
    try:
        expected_volume = Decimal(str(protected["volume"]))
    except InvalidOperation:
        return _inconsistent("EXECUTION_RECORD_INCOMPLETE")

    active_orders = _matching_rows(snapshot.get("active_orders", []), symbol, direction, tag)
    recent_orders = _matching_rows(snapshot.get("recent_orders", []), symbol, direction, tag)
    entry_deals = [
        row
        for row in _matching_rows(snapshot.get("recent_deals", []), symbol, direction, tag)
        if row.get("entry") in {"IN", "INOUT", "UNKNOWN"}
    ]
    positions = _matching_rows(snapshot.get("positions", []), symbol, direction, tag)
    same_symbol = [row for row in snapshot.get("positions", []) if row.get("symbol") == symbol]
    if any(str(row.get("direction", "")).upper() != direction for row in same_symbol):
        return _inconsistent("CONFLICTING_VOLUME_OR_DIRECTION")
    if len(active_orders) > 1 or len(positions) > 1:
        return _inconsistent("DUPLICATE_BROKER_MATCH", active_orders, entry_deals, positions)

    state = str(record.get("state", "UNKNOWN"))
    if state in {"RESERVED", "SUBMISSION_STARTED"}:
        if _is_stale(record.get("state_created_at"), stale_seconds):
            return _classification(
                MT5LifecycleState.RECONCILIATION_REQUIRED,
                "STALE_SUBMISSION",
                "STALE_SUBMISSION_STATE",
                active_orders,
                entry_deals,
                positions,
            )
        return _classification(
            MT5LifecycleState.SUBMISSION_PENDING,
            "SUBMISSION_NOT_TERMINAL",
            "",
            active_orders,
            entry_deals,
            positions,
        )
    if state == "RESULT_UNKNOWN":
        return _classification(
            MT5LifecycleState.RECONCILIATION_REQUIRED,
            "RESULT_UNKNOWN",
            "",
            active_orders,
            entry_deals,
            positions,
        )
    if state in {"RESULT_REJECTED", "RESERVATION_ABANDONED"}:
        if active_orders or recent_orders or entry_deals or positions:
            return _inconsistent("CONFLICTING_VOLUME_OR_DIRECTION", active_orders, entry_deals, positions)
        return _classification(
            MT5LifecycleState.BROKER_REJECTED,
            "EXECUTION_REJECTED",
            "",
            [],
            [],
            [],
        )
    if state != "RESULT_CONFIRMED":
        return _classification(MT5LifecycleState.UNKNOWN, "STATE_NOT_CLASSIFIED", "", [], [], [])

    if positions:
        current_volume = _volume(positions[0])
        if current_volume <= 0 or current_volume > expected_volume:
            return _inconsistent("CONFLICTING_VOLUME_OR_DIRECTION", active_orders, entry_deals, positions)
        lifecycle = (
            MT5LifecycleState.POSITION_PARTIALLY_REDUCED
            if current_volume < expected_volume
            else MT5LifecycleState.POSITION_OPEN
        )
        return _classification(lifecycle, "UNIQUE_POSITION_MATCH", "", active_orders, entry_deals, positions)
    if active_orders:
        if _volume(active_orders[0]) != expected_volume:
            return _inconsistent("CONFLICTING_VOLUME_OR_DIRECTION", active_orders, entry_deals, positions)
        return _classification(
            MT5LifecycleState.ORDER_ACTIVE,
            "UNIQUE_ACTIVE_ORDER_MATCH",
            "",
            active_orders,
            entry_deals,
            positions,
        )
    position_links = {
        str(row.get("position_reference_hash", "")) for row in entry_deals if row.get("position_reference_hash")
    }
    closing_deals = [
        row
        for row in snapshot.get("recent_deals", [])
        if row.get("entry") in {"OUT", "INOUT"}
        and str(row.get("position_reference_hash", "")) in position_links
    ]
    if entry_deals and closing_deals:
        return _classification(
            MT5LifecycleState.POSITION_CLOSED,
            "LINKED_CLOSING_DEAL",
            "",
            recent_orders,
            entry_deals + closing_deals,
            [],
        )
    if entry_deals:
        return _classification(
            MT5LifecycleState.INCONSISTENT,
            "POSITION_EVIDENCE_INCOMPLETE",
            "POSITION_CLOSED_WITHOUT_CLOSING_DEAL",
            recent_orders,
            entry_deals,
            [],
        )
    if recent_orders:
        statuses = {str(row.get("order_status", "")) for row in recent_orders}
        if "REJECTED" in statuses:
            return _classification(
                MT5LifecycleState.BROKER_REJECTED,
                "BROKER_ORDER_REJECTED",
                "",
                recent_orders,
                [],
                [],
            )
        evidence = (
            "BROKER_ORDER_CANCELLED"
            if "CANCELLED" in statuses
            else "BROKER_ORDER_EXPIRED"
            if "EXPIRED" in statuses
            else "BROKER_ORDER_HISTORY_MATCH"
        )
        return _classification(
            MT5LifecycleState.BROKER_ACCEPTED,
            evidence,
            "",
            recent_orders,
            [],
            [],
        )
    return _inconsistent("CONFIRMED_BROKER_EVIDENCE_ABSENT")


def _matching_rows(rows: Any, symbol: str, direction: str, tag: str) -> list[Mapping[str, Any]]:
    candidates = [
        row
        for row in rows or []
        if isinstance(row, Mapping)
        and str(row.get("symbol", "")) == symbol
        and str(row.get("direction", "")).upper() == direction
    ]
    tagged = [row for row in candidates if tag in row.get("matched_correlation_tags", [])]
    return tagged or candidates


def _classification(
    state: MT5LifecycleState,
    evidence: str,
    discrepancy: str,
    orders: list[Mapping[str, Any]],
    deals: list[Mapping[str, Any]],
    positions: list[Mapping[str, Any]],
) -> _Classification:
    references = {
        "orders": sorted({str(row.get("broker_reference_hash")) for row in orders if row.get("broker_reference_hash")}),
        "deals": sorted({str(row.get("broker_reference_hash")) for row in deals if row.get("broker_reference_hash")}),
        "positions": sorted({str(row.get("broker_reference_hash")) for row in positions if row.get("broker_reference_hash")}),
    }
    return _Classification(
        state,
        evidence,
        discrepancy,
        references,
        frozenset(references["positions"]),
    )


def _inconsistent(
    reason: str,
    orders: list[Mapping[str, Any]] | None = None,
    deals: list[Mapping[str, Any]] | None = None,
    positions: list[Mapping[str, Any]] | None = None,
) -> _Classification:
    return _classification(
        MT5LifecycleState.INCONSISTENT,
        "CONFLICTING_OR_MISSING_EVIDENCE",
        reason,
        orders or [],
        deals or [],
        positions or [],
    )


def _make_observation(
    reference: str,
    previous: str,
    classification: _Classification,
    snapshot: Mapping[str, Any],
) -> MT5LifecycleObservation:
    timestamp = _now()
    row = {
        "protected_execution_reference": reference,
        "lifecycle_state": classification.state.value,
        "previous_lifecycle_state": previous,
        "account_fingerprint_hash": _sha256(str(snapshot.get("account_context_fingerprint", "")))
        if snapshot.get("account_context_fingerprint")
        else "",
        "evidence_classification": classification.evidence,
        "protected_broker_references": classification.broker_references,
        "discrepancy_reason": classification.discrepancy,
        "source_snapshot_reference": str(snapshot.get("snapshot_reference", "")),
    }
    digest = _observation_hash(row)
    return MT5LifecycleObservation(
        observation_id="mt5_lifecycle_observation_" + _sha256(digest + previous + timestamp)[:24],
        observation_timestamp=timestamp,
        observation_hash=digest,
        **row,
    )


def _observation_hash(row: Mapping[str, Any]) -> str:
    stable = {
        key: row.get(key)
        for key in (
            "protected_execution_reference",
            "lifecycle_state",
            "account_fingerprint_hash",
            "evidence_classification",
            "protected_broker_references",
            "discrepancy_reason",
            "source_snapshot_reference",
        )
    }
    return _sha256(json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _execution_reference(record: Mapping[str, Any]) -> str:
    reference = str(record.get("protected_execution", {}).get("protected_execution_reference", ""))
    if reference:
        return reference
    return "invalid_execution_" + _sha256(str(record.get("idempotency_key_hash", "")))[:24]


def _validate_snapshot(snapshot: Any) -> None:
    if not isinstance(snapshot, Mapping) or snapshot.get("metadata_redacted") is not True:
        raise ValueError("snapshot invalid")
    for key in ("active_orders", "recent_orders", "recent_deals", "positions"):
        rows = snapshot.get(key)
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("snapshot invalid")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("snapshot invalid")
            forbidden = {"ticket", "deal", "position", "login", "comment", "account_login"}
            if forbidden.intersection(row):
                raise ValueError("snapshot contains unredacted fields")
            for reference_key in (
                "broker_reference_hash",
                "order_reference_hash",
                "position_reference_hash",
            ):
                if not _valid_hash(row.get(reference_key), allow_empty=True):
                    raise ValueError("snapshot reference invalid")
    if snapshot.get("status") == "OK":
        if not _valid_hash(snapshot.get("account_context_fingerprint")):
            raise ValueError("snapshot fingerprint invalid")
        if not str(snapshot.get("snapshot_reference", "")):
            raise ValueError("snapshot reference missing")
        if any(
            key in snapshot
            for key in ("active_position_count", "trades_today", "loss_today")
        ):
            try:
                if not all(
                    key in snapshot
                    for key in ("active_position_count", "trades_today", "loss_today")
                ) or int(snapshot["active_position_count"]) < 0 or int(
                    snapshot["trades_today"]
                ) < 0 or Decimal(str(snapshot["loss_today"])) < 0:
                    raise ValueError("snapshot aggregate invalid")
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("snapshot aggregate invalid") from exc


def _protected_references_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"orders", "deals", "positions"}:
        return False
    return all(
        isinstance(items, list) and all(_valid_hash(item) for item in items)
        for items in value.values()
    )


def _valid_hash(value: Any, allow_empty: bool = False) -> bool:
    text = str(value or "")
    if allow_empty and not text:
        return True
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def _volume(row: Mapping[str, Any]) -> Decimal:
    try:
        return Decimal(str(row.get("volume", "0")))
    except InvalidOperation:
        return Decimal(0)


def _is_stale(value: Any, threshold_seconds: int) -> bool:
    try:
        created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() >= threshold_seconds
    except (TypeError, ValueError):
        return True


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
