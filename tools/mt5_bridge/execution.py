from __future__ import annotations

import hashlib
import hmac
import json
import os
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.mt5_bridge.mt5_client import mt5


REQUEST_VERSION = "controlled-mt5-execution/v1"
SEMANTIC_SCHEMA_VERSION = "approved-semantic-execution-parameters/v1"
SEMANTIC_FIELDS = (
    "action", "symbol", "volume", "order_type", "price", "stop_loss",
    "take_profit", "deviation", "magic", "comment", "idempotency", "audit",
)
IDEMPOTENCY_STATES = {
    "RESERVED", "SUBMISSION_STARTED", "RESULT_CONFIRMED", "RESULT_REJECTED", "RESULT_UNKNOWN",
    "RESERVATION_ABANDONED",
}
IDEMPOTENCY_TRANSITIONS = {
    "RESERVED": {"SUBMISSION_STARTED", "RESULT_REJECTED", "RESERVATION_ABANDONED"},
    "SUBMISSION_STARTED": {"RESULT_CONFIRMED", "RESULT_REJECTED", "RESULT_UNKNOWN"},
    "RESULT_UNKNOWN": {"RESULT_CONFIRMED"},
}
MANAGEMENT_STATES = {
    "RESERVED", "MANAGEMENT_STARTED", "RESULT_CONFIRMED", "RESULT_REJECTED", "RESULT_UNKNOWN",
}
MANAGEMENT_TRANSITIONS = {
    "RESERVED": {"MANAGEMENT_STARTED", "RESULT_REJECTED"},
    "MANAGEMENT_STARTED": {"RESULT_CONFIRMED", "RESULT_REJECTED", "RESULT_UNKNOWN"},
    "RESULT_UNKNOWN": {"RESULT_CONFIRMED"},
}


class ProtectedExecutionJournalError(RuntimeError):
    """Fail-closed protected persistence error with a public-safe reason."""


@dataclass(frozen=True)
class ControlledExecutionConfig:
    enabled: bool = False
    hard_block: bool = True
    kill_switch_engaged: bool = True
    order_send_enabled: bool = False
    live_execution_enabled: bool = False
    auth_token: str = field(default="", repr=False)
    confirmation_phrase: str = "SUBMIT CONTROLLED MT5 ORDER"
    max_request_age_seconds: int = 300
    submit_timeout_seconds: float = 5.0
    journal_path: str = "data/trading/execution_journal/mt5_controlled_execution.jsonl"

    @classmethod
    def from_env(cls) -> "ControlledExecutionConfig":
        return cls(
            enabled=_env_bool("MT5_BRIDGE_CONTROLLED_EXECUTION_ENABLED", False),
            hard_block=_env_bool("MT5_BRIDGE_CONTROLLED_EXECUTION_HARD_BLOCK", True),
            kill_switch_engaged=_env_bool("MT5_BRIDGE_EXECUTION_KILL_SWITCH", True),
            order_send_enabled=_env_bool("MT5_BRIDGE_ORDER_SEND_ENABLED", False),
            live_execution_enabled=_env_bool("MT5_BRIDGE_LIVE_EXECUTION_ENABLED", False),
            auth_token=os.getenv("MT5_BRIDGE_EXECUTION_TOKEN", ""),
            confirmation_phrase=os.getenv(
                "MT5_BRIDGE_EXECUTION_CONFIRMATION_PHRASE", "SUBMIT CONTROLLED MT5 ORDER"
            ).strip(),
            max_request_age_seconds=_env_int("MT5_BRIDGE_EXECUTION_MAX_REQUEST_AGE_SECONDS", 300),
            submit_timeout_seconds=_env_float("MT5_BRIDGE_EXECUTION_TIMEOUT_SECONDS", 5.0),
            journal_path=os.getenv(
                "MT5_BRIDGE_EXECUTION_JOURNAL_PATH",
                "data/trading/execution_journal/mt5_controlled_execution.jsonl",
            ).strip(),
        )


@dataclass(frozen=True)
class ProtectedBridgeExecutionRequest:
    request_version: str
    approved_semantic_parameters: Mapping[str, Any] = field(repr=False)
    canonical_semantic_hash: str
    approval_value_hash: str
    lock_value_hash: str
    approval_reference: str
    lock_reference: str
    source_artifact_reference: str
    approval_timestamp: str
    lock_timestamp: str
    human_confirmation_reference: str
    human_confirmation_phrase: str = field(repr=False)
    pre_submit_validation_reference: str
    pre_submit_validation_valid: bool
    idempotency_key: str = field(repr=False)
    expected_account_context_fingerprint: str
    execution_permission_requested: bool

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ProtectedBridgeExecutionRequest":
        required = {
            "request_version", "approved_semantic_parameters", "canonical_semantic_hash",
            "approval_value_hash", "lock_value_hash", "approval_reference", "lock_reference",
            "source_artifact_reference", "approval_timestamp", "lock_timestamp",
            "human_confirmation_reference", "human_confirmation_phrase",
            "pre_submit_validation_reference", "pre_submit_validation_valid", "idempotency_key",
            "expected_account_context_fingerprint", "execution_permission_requested",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("controlled execution request schema is invalid")
        protected = payload.get("approved_semantic_parameters")
        if not isinstance(protected, Mapping):
            raise ValueError("approved semantic parameters are invalid")
        return cls(
            request_version=_required_text(payload["request_version"], "request_version"),
            approved_semantic_parameters=dict(protected),
            canonical_semantic_hash=_required_hash(payload["canonical_semantic_hash"]),
            approval_value_hash=_required_hash(payload["approval_value_hash"]),
            lock_value_hash=_required_hash(payload["lock_value_hash"]),
            approval_reference=_required_text(payload["approval_reference"], "approval_reference"),
            lock_reference=_required_text(payload["lock_reference"], "lock_reference"),
            source_artifact_reference=_required_text(payload["source_artifact_reference"], "source_artifact_reference"),
            approval_timestamp=_required_text(payload["approval_timestamp"], "approval_timestamp"),
            lock_timestamp=_required_text(payload["lock_timestamp"], "lock_timestamp"),
            human_confirmation_reference=_required_hash(payload["human_confirmation_reference"]),
            human_confirmation_phrase=_required_text(payload["human_confirmation_phrase"], "human_confirmation_phrase"),
            pre_submit_validation_reference=_required_text(payload["pre_submit_validation_reference"], "pre_submit_validation_reference"),
            pre_submit_validation_valid=payload["pre_submit_validation_valid"] is True,
            idempotency_key=_required_text(payload["idempotency_key"], "idempotency_key"),
            expected_account_context_fingerprint=_required_hash(payload["expected_account_context_fingerprint"]),
            execution_permission_requested=payload["execution_permission_requested"] is True,
        )


class ProtectedExecutionJournal:
    _process_lock = threading.Lock()

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def reserve(
        self,
        idempotency_key: str,
        request_hash: str,
        account_fingerprint: str,
        protected_execution: Mapping[str, Any] | None = None,
    ) -> bool:
        key_hash = _sha256(idempotency_key)
        with self._exclusive_lock():
            if any(row.get("idempotency_key_hash") == key_hash for row in self._read_rows()):
                return False
            row = {
                "state": "RESERVED",
                "created_at": _now(),
                "idempotency_key_hash": key_hash,
                "request_hash": request_hash,
                "account_context_fingerprint": account_fingerprint,
                "metadata_redacted": True,
            }
            if protected_execution:
                row["protected_execution"] = dict(protected_execution)
            self._append_unlocked(row)
            return True

    def reserve_management(
        self,
        idempotency_key: str,
        request_hash: str,
        account_fingerprint: str,
        protected_management: Mapping[str, Any],
    ) -> bool:
        key_hash = _sha256(idempotency_key)
        with self._exclusive_lock():
            if any(row.get("idempotency_key_hash") == key_hash for row in self._read_rows()):
                return False
            self._append_unlocked(
                {
                    "record_type": "MANAGEMENT",
                    "state": "RESERVED",
                    "created_at": _now(),
                    "idempotency_key_hash": key_hash,
                    "request_hash": request_hash,
                    "account_context_fingerprint": account_fingerprint,
                    "protected_management": dict(protected_management),
                    "metadata_redacted": True,
                }
            )
            return True

    def transition(self, idempotency_key: str, state: str, **protected_result: Any) -> None:
        if state not in IDEMPOTENCY_STATES:
            raise ValueError("invalid idempotency state")
        key_hash = _sha256(idempotency_key)
        with self._exclusive_lock():
            previous_states = [
                item.get("state")
                for item in self._read_rows()
                if item.get("idempotency_key_hash") == key_hash
            ]
            previous_state = previous_states[-1] if previous_states else None
            if state not in IDEMPOTENCY_TRANSITIONS.get(previous_state, set()):
                raise RuntimeError("invalid idempotency state transition")
            row = {
                "state": state,
                "created_at": _now(),
                "idempotency_key_hash": key_hash,
                "metadata_redacted": True,
            }
            if protected_result:
                row["protected_result"] = protected_result
            self._append_unlocked(row)

    def transition_management(
        self, idempotency_key: str, state: str, **protected_result: Any
    ) -> None:
        if state not in MANAGEMENT_STATES:
            raise ValueError("invalid management idempotency state")
        key_hash = _sha256(idempotency_key)
        with self._exclusive_lock():
            previous_states = [
                row.get("state")
                for row in self._read_rows()
                if row.get("record_type") == "MANAGEMENT"
                and row.get("idempotency_key_hash") == key_hash
            ]
            previous_state = previous_states[-1] if previous_states else None
            if state not in MANAGEMENT_TRANSITIONS.get(previous_state, set()):
                raise RuntimeError("invalid management idempotency state transition")
            row = {
                "record_type": "MANAGEMENT",
                "state": state,
                "created_at": _now(),
                "idempotency_key_hash": key_hash,
                "metadata_redacted": True,
            }
            if protected_result:
                row["protected_result"] = protected_result
            self._append_unlocked(row)

    def execution_record(self, correlation_identity: str) -> dict[str, Any] | None:
        rows = self._read_rows()
        reservation = next(
            (
                row
                for row in rows
                if row.get("protected_execution", {}).get("correlation_identity")
                == correlation_identity
            ),
            None,
        )
        if reservation is None:
            return None
        key_hash = reservation.get("idempotency_key_hash")
        state_rows = [
            row
            for row in rows
            if row.get("idempotency_key_hash") == key_hash and row.get("state")
        ]
        latest = state_rows[-1]
        return {
            "idempotency_key_hash": key_hash,
            "account_context_fingerprint": reservation.get("account_context_fingerprint"),
            "protected_execution": dict(reservation.get("protected_execution", {})),
            "state": latest.get("state"),
            "state_created_at": latest.get("created_at"),
        }

    def execution_record_by_reference(self, protected_execution_reference: str) -> dict[str, Any] | None:
        for record in self.execution_records():
            if hmac.compare_digest(
                str(record.get("protected_execution", {}).get("protected_execution_reference", "")),
                str(protected_execution_reference),
            ):
                return record
        return None

    def management_record(self, idempotency_key: str) -> dict[str, Any] | None:
        key_hash = _sha256(idempotency_key)
        rows = [
            row
            for row in self._read_rows()
            if row.get("record_type") == "MANAGEMENT"
            and row.get("idempotency_key_hash") == key_hash
        ]
        if not rows:
            return None
        reservation = rows[0]
        latest = rows[-1]
        return {
            "idempotency_key_hash": key_hash,
            "account_context_fingerprint": reservation.get("account_context_fingerprint"),
            "protected_management": dict(reservation.get("protected_management", {})),
            "state": latest.get("state"),
            "state_created_at": latest.get("created_at"),
            "protected_result": dict(latest.get("protected_result", {})),
        }

    def execution_records(self) -> list[dict[str, Any]]:
        """Return validated latest records without weakening journal integrity."""
        rows = self._read_rows()
        records: list[dict[str, Any]] = []
        for reservation in (
            row for row in rows if row.get("state") == "RESERVED" and row.get("protected_execution")
        ):
            key_hash = reservation["idempotency_key_hash"]
            state_rows = [
                row
                for row in rows
                if row.get("idempotency_key_hash") == key_hash and row.get("state")
            ]
            latest = state_rows[-1]
            correlation_identity = reservation["protected_execution"].get("correlation_identity", "")
            reconciliations = [
                row
                for row in rows
                if row.get("record_type") == "RECONCILIATION"
                and row.get("correlation_identity") == correlation_identity
                and row.get("reconciliation_status") != "PENDING"
            ]
            records.append(
                {
                    "idempotency_key_hash": key_hash,
                    "account_context_fingerprint": reservation.get("account_context_fingerprint"),
                    "protected_execution": dict(reservation.get("protected_execution", {})),
                    "state": latest.get("state"),
                    "state_created_at": latest.get("created_at"),
                    "protected_result": dict(latest.get("protected_result", {})),
                    "latest_reconciliation": dict(reconciliations[-1]) if reconciliations else None,
                }
            )
        return records

    def begin_reconciliation(
        self,
        reconciliation_reference: str,
        correlation_identity: str,
        *,
        recovery_state: str | None = None,
        recovery_reason: str = "",
    ) -> tuple[dict[str, Any], bool]:
        with self._exclusive_lock():
            rows = self._read_rows()
            existing = [
                row
                for row in rows
                if row.get("reconciliation_reference") == reconciliation_reference
            ]
            if existing:
                completed = [
                    row for row in existing if row.get("reconciliation_status") != "PENDING"
                ]
                if completed:
                    return completed[-1], False
                return existing[-1], True
            reservation = next(
                (
                    row
                    for row in rows
                    if row.get("protected_execution", {}).get("correlation_identity")
                    == correlation_identity
                ),
                None,
            )
            if reservation is None:
                raise ValueError("EXECUTION_RECORD_NOT_FOUND")
            key_hash = reservation["idempotency_key_hash"]
            if recovery_state:
                self._append_state_transition_unlocked(
                    rows,
                    key_hash,
                    recovery_state,
                    {"recovery_reason": recovery_reason},
                )
            row = {
                "record_type": "RECONCILIATION",
                "reconciliation_reference": reconciliation_reference,
                "correlation_identity": correlation_identity,
                "reconciliation_status": "PENDING",
                "created_at": _now(),
                "metadata_redacted": True,
            }
            self._append_unlocked(row)
            return row, True

    def complete_reconciliation(
        self,
        reconciliation_reference: str,
        correlation_identity: str,
        *,
        reconciliation_status: str,
        evidence_classification: str,
        original_execution_state: str,
        resulting_execution_state: str,
        retry_decision: str,
        reasons: list[str],
        account_fingerprint: str,
        protected_broker_references: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._exclusive_lock():
            rows = self._read_rows()
            completed = [
                row
                for row in rows
                if row.get("reconciliation_reference") == reconciliation_reference
                and row.get("reconciliation_status") != "PENDING"
            ]
            if completed:
                return completed[-1]
            reservation = next(
                (
                    row
                    for row in rows
                    if row.get("protected_execution", {}).get("correlation_identity")
                    == correlation_identity
                ),
                None,
            )
            if reservation is None:
                raise ValueError("EXECUTION_RECORD_NOT_FOUND")
            key_hash = reservation["idempotency_key_hash"]
            state_rows = [
                row
                for row in rows
                if row.get("idempotency_key_hash") == key_hash and row.get("state")
            ]
            current_state = state_rows[-1]["state"]
            if resulting_execution_state != current_state:
                self._append_state_transition_unlocked(
                    rows,
                    key_hash,
                    resulting_execution_state,
                    {
                        "reconciliation_reference": reconciliation_reference,
                        "protected_broker_references": dict(protected_broker_references or {}),
                    },
                )
            row = {
                "record_type": "RECONCILIATION",
                "reconciliation_reference": reconciliation_reference,
                "correlation_identity": correlation_identity,
                "reconciliation_status": reconciliation_status,
                "evidence_classification": evidence_classification,
                "original_execution_state": original_execution_state,
                "resulting_execution_state": resulting_execution_state,
                "retry_decision": retry_decision,
                "reasons": list(reasons),
                "account_context_fingerprint": account_fingerprint,
                "protected_broker_references": dict(protected_broker_references or {}),
                "created_at": _now(),
                "metadata_redacted": True,
            }
            self._append_unlocked(row)
            return row

    def _append_state_transition_unlocked(
        self,
        rows: list[dict[str, Any]],
        key_hash: str,
        state: str,
        protected_result: Mapping[str, Any],
    ) -> None:
        if state not in IDEMPOTENCY_STATES:
            raise ValueError("invalid idempotency state")
        previous_states = [
            row.get("state")
            for row in rows
            if row.get("idempotency_key_hash") == key_hash and row.get("state")
        ]
        previous_state = previous_states[-1] if previous_states else None
        if state not in IDEMPOTENCY_TRANSITIONS.get(previous_state, set()):
            raise RuntimeError("invalid idempotency state transition")
        self._append_unlocked(
            {
                "state": state,
                "created_at": _now(),
                "idempotency_key_hash": key_hash,
                "protected_result": dict(protected_result),
                "metadata_redacted": True,
            }
        )

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_UNAVAILABLE") from exc
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT") from exc
            if not isinstance(row, dict):
                raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
            rows.append(row)
        self._validate_rows(rows)
        return rows

    @staticmethod
    def _validate_rows(rows: list[dict[str, Any]]) -> None:
        states_by_key: dict[str, list[str]] = {}
        management_states_by_key: dict[str, list[str]] = {}
        for row in rows:
            if row.get("record_type") == "RECONCILIATION":
                if not row.get("reconciliation_reference") or not row.get("reconciliation_status"):
                    raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
                continue
            if row.get("record_type") == "MANAGEMENT":
                state = row.get("state")
                key_hash = row.get("idempotency_key_hash")
                if (
                    state not in MANAGEMENT_STATES
                    or not isinstance(key_hash, str)
                    or len(key_hash) != 64
                    or row.get("metadata_redacted") is not True
                ):
                    raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
                previous = management_states_by_key.setdefault(key_hash, [])
                if not previous:
                    if state != "RESERVED" or not row.get("protected_management"):
                        raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
                elif state not in MANAGEMENT_TRANSITIONS.get(previous[-1], set()):
                    raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
                previous.append(state)
                continue
            state = row.get("state")
            key_hash = row.get("idempotency_key_hash")
            if state not in IDEMPOTENCY_STATES or not isinstance(key_hash, str) or len(key_hash) != 64:
                raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
            previous = states_by_key.setdefault(key_hash, [])
            if not previous:
                if state != "RESERVED":
                    raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
            elif state not in IDEMPOTENCY_TRANSITIONS.get(previous[-1], set()):
                raise ProtectedExecutionJournalError("EXECUTION_JOURNAL_CORRUPT")
            previous.append(state)

    def _append_unlocked(self, row: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _exclusive_lock(self):
        journal = self

        class LockContext:
            def __enter__(self):
                journal._process_lock.acquire()
                journal.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.fd = os.open(journal.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError as exc:
                    journal._process_lock.release()
                    raise RuntimeError("execution journal reservation is locked") from exc
                return self

            def __exit__(self, exc_type, exc, traceback):
                os.close(self.fd)
                try:
                    journal.lock_path.unlink()
                finally:
                    journal._process_lock.release()

        return LockContext()


class ControlledMT5ExecutionService:
    def __init__(
        self,
        client: Any,
        *,
        config: ControlledExecutionConfig | None = None,
        mt5_module: Any = None,
        journal: ProtectedExecutionJournal | None = None,
    ):
        self.client = client
        self.config = config or ControlledExecutionConfig.from_env()
        self.mt5 = mt5 if mt5_module is None else mt5_module
        self.journal = journal or ProtectedExecutionJournal(self.config.journal_path)

    def handle(self, payload: Mapping[str, Any], provided_token: str) -> tuple[dict[str, Any], int]:
        if not _authenticated(provided_token, self.config.auth_token):
            return _blocked("AUTHENTICATION_FAILED"), 401
        try:
            request = ProtectedBridgeExecutionRequest.from_payload(payload)
            self._validate_config()
            values = self._validate_integrity(request)
            first_context = self._validated_account_context(request.expected_account_context_fingerprint)
            self._validate_mapping(values)
            request_hash = _sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
            correlation = execution_correlation(request)
            if not self.journal.reserve(
                request.idempotency_key,
                request_hash,
                first_context["account_context_fingerprint"],
                protected_execution={
                    **correlation,
                    "canonical_semantic_hash": request.canonical_semantic_hash,
                    "approval_reference": request.approval_reference,
                    "lock_reference": request.lock_reference,
                    "source_artifact_reference": request.source_artifact_reference,
                    "symbol": values["symbol"],
                    "order_type": values["order_type"],
                    "volume": _decimal_text(values["volume"]),
                    "submission_window_start": request.lock_timestamp,
                },
            ):
                return _blocked("IDEMPOTENCY_DUPLICATE", idempotency_status="DUPLICATE_BLOCKED"), 409
            mt5_request = self._map_request(values)
            try:
                second_context = self._validated_account_context(
                    request.expected_account_context_fingerprint
                )
            except ValueError:
                self.journal.transition(
                    request.idempotency_key,
                    "RESULT_REJECTED",
                    reason="ACCOUNT_CONTEXT_CHANGED",
                )
                return _blocked("ACCOUNT_CONTEXT_CHANGED"), 409
            if second_context["account_context_fingerprint"] != first_context["account_context_fingerprint"]:
                self.journal.transition(request.idempotency_key, "RESULT_REJECTED", reason="ACCOUNT_CONTEXT_CHANGED")
                return _blocked("ACCOUNT_CONTEXT_CHANGED"), 409
            self.journal.transition(request.idempotency_key, "SUBMISSION_STARTED")
            return self._submit_once(request, mt5_request)
        except (TypeError, ValueError, RuntimeError) as exc:
            return _blocked(_safe_reason(exc)), 403

    def _validate_config(self) -> None:
        if (
            not self.config.enabled
            or self.config.hard_block
            or self.config.kill_switch_engaged
            or not self.config.order_send_enabled
            or not self.config.live_execution_enabled
        ):
            raise ValueError("EXECUTION_DISABLED")
        if not self.config.auth_token:
            raise ValueError("AUTHENTICATION_FAILED")

    def _validate_integrity(self, request: ProtectedBridgeExecutionRequest) -> dict[str, Any]:
        if request.request_version != REQUEST_VERSION:
            raise ValueError("REQUEST_VERSION_INVALID")
        protected = dict(request.approved_semantic_parameters)
        required = set(SEMANTIC_FIELDS) | {
            "schema_version", "approval_artifact_ref", "lock_artifact_ref", "source_artifact_ref",
            "approved_at", "locked_at", "canonical_values_hash",
        }
        if set(protected) != required or protected.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
            raise ValueError("SEMANTIC_SCHEMA_INVALID")
        values = _canonical_values({name: protected[name] for name in SEMANTIC_FIELDS})
        calculated = _semantic_hash(protected, values)
        hashes = {
            calculated,
            str(protected.get("canonical_values_hash", "")),
            request.canonical_semantic_hash,
            request.approval_value_hash,
            request.lock_value_hash,
        }
        if len(hashes) != 1:
            raise ValueError("SEMANTIC_HASH_MISMATCH")
        pairs = (
            (protected.get("approval_artifact_ref"), request.approval_reference),
            (protected.get("lock_artifact_ref"), request.lock_reference),
            (protected.get("source_artifact_ref"), request.source_artifact_reference),
            (protected.get("approved_at"), request.approval_timestamp),
            (protected.get("locked_at"), request.lock_timestamp),
        )
        if any(left != right for left, right in pairs):
            raise ValueError("APPROVAL_LOCK_REFERENCE_MISMATCH")
        if values["idempotency"] != request.idempotency_key:
            raise ValueError("IDEMPOTENCY_MISMATCH")
        if not request.pre_submit_validation_valid or not request.execution_permission_requested:
            raise ValueError("PRE_SUBMIT_VALIDATION_REQUIRED")
        expected_confirmation_ref = _sha256(
            f"{request.human_confirmation_phrase}|{request.idempotency_key}|{request.expected_account_context_fingerprint}"
        )
        if not hmac.compare_digest(request.human_confirmation_reference, expected_confirmation_ref):
            raise ValueError("HUMAN_CONFIRMATION_INVALID")
        if not hmac.compare_digest(request.human_confirmation_phrase, self.config.confirmation_phrase):
            raise ValueError("HUMAN_CONFIRMATION_INVALID")
        _validate_freshness(request.lock_timestamp, self.config.max_request_age_seconds)
        return values

    def _validated_account_context(self, expected_fingerprint: str) -> dict[str, Any]:
        context = self.client.execution_context()
        if (
            context.get("status") != "OK"
            or context.get("terminal_connected") is not True
            or context.get("terminal_trade_allowed") is not True
            or context.get("account_trade_allowed") is not True
        ):
            raise ValueError("MT5_TRADING_CAPABILITY_UNAVAILABLE")
        actual = str(context.get("account_context_fingerprint", ""))
        if not actual or not hmac.compare_digest(actual, expected_fingerprint):
            raise ValueError("ACCOUNT_CONTEXT_MISMATCH")
        return context

    def _validate_mapping(self, values: Mapping[str, Any]) -> None:
        if values["action"] != "MARKET" or values["order_type"] not in {"BUY", "SELL"}:
            raise ValueError("UNSUPPORTED_SEMANTIC_MAPPING")
        if values["volume"] <= 0 or values["deviation"] > 1000 or values["magic"] > 2_147_483_647:
            raise ValueError("UNSUPPORTED_SEMANTIC_MAPPING")
        if len(values["comment"]) > 31:
            raise ValueError("UNSUPPORTED_SEMANTIC_MAPPING")
        if self.mt5 is None:
            raise ValueError("MT5_PACKAGE_UNAVAILABLE")
        required_constants = ["TRADE_ACTION_DEAL", "ORDER_TYPE_BUY", "ORDER_TYPE_SELL"]
        if any(not hasattr(self.mt5, name) for name in required_constants):
            raise ValueError("MT5_CONSTANTS_UNAVAILABLE")

    def _map_request(self, values: Mapping[str, Any]) -> dict[str, Any]:
        order_type_name = "ORDER_TYPE_BUY" if values["order_type"] == "BUY" else "ORDER_TYPE_SELL"
        return {
            "action": getattr(self.mt5, "TRADE_ACTION_DEAL"),
            "symbol": values["symbol"],
            "volume": float(values["volume"]),
            "type": getattr(self.mt5, order_type_name),
            "price": float(values["price"]),
            "sl": float(values["stop_loss"]),
            "tp": float(values["take_profit"]),
            "deviation": values["deviation"],
            "magic": values["magic"],
            "comment": values["comment"],
        }

    def _submit_once(
        self, request: ProtectedBridgeExecutionRequest, mt5_request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], int]:
        try:
            result = _isolated_order_send(self.mt5, dict(mt5_request), self.config.submit_timeout_seconds)
        except Exception as exc:
            self.journal.transition(request.idempotency_key, "RESULT_UNKNOWN", reason=type(exc).__name__)
            return _receipt("UNKNOWN", "RESULT_UNKNOWN"), 200
        if result is None:
            self.journal.transition(request.idempotency_key, "RESULT_UNKNOWN", reason="NO_RESULT")
            return _receipt("UNKNOWN", "RESULT_UNKNOWN"), 200
        result_data = result._asdict() if hasattr(result, "_asdict") else dict(vars(result))
        accepted_retcodes = {
            getattr(self.mt5, name, object())
            for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED")
        }
        accepted = result_data.get("retcode") in accepted_retcodes
        state = "RESULT_CONFIRMED" if accepted else "RESULT_REJECTED"
        status = "ACCEPTED" if accepted else "REJECTED"
        protected = {
            "retcode": result_data.get("retcode"),
            "order": result_data.get("order"),
            "deal": result_data.get("deal"),
            "comment": str(result_data.get("comment", ""))[:128],
        }
        self.journal.transition(request.idempotency_key, state, **protected)
        return _receipt(
            status,
            state,
            order_sent=accepted,
            ticket_present=bool(result_data.get("order")),
            deal_present=bool(result_data.get("deal")),
        ), 200


def _isolated_order_send(mt5_module: Any, mt5_request: dict[str, Any], timeout_seconds: float) -> Any:
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, mt5_module.order_send(mt5_request)))
        except Exception as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(max(0.1, timeout_seconds))
    if thread.is_alive():
        raise TimeoutError("MT5 submission result is unknown")
    ok, value = result_queue.get_nowait()
    if ok:
        return value
    raise value


def execution_correlation(request: ProtectedBridgeExecutionRequest) -> dict[str, str]:
    key_hash = _sha256(request.idempotency_key)
    identity = _sha256(
        "|".join(
            (
                "controlled-execution-correlation/v1",
                key_hash,
                request.canonical_semantic_hash,
                request.approval_reference,
                request.lock_reference,
                request.source_artifact_reference,
            )
        )
    )
    return {
        "protected_execution_reference": "mt5_execution_" + identity[:24],
        "correlation_identity": identity,
        "correlation_tag": "mt5r" + identity[:12],
    }


def _semantic_hash(protected: Mapping[str, Any], values: Mapping[str, Any]) -> str:
    payload = {
        "schema_version": protected["schema_version"],
        "approval_artifact_ref": protected["approval_artifact_ref"],
        "lock_artifact_ref": protected["lock_artifact_ref"],
        "source_artifact_ref": protected["source_artifact_ref"],
        "approved_at": protected["approved_at"],
        "locked_at": protected["locked_at"],
        "values": {
            name: _decimal_text(values[name]) if isinstance(values[name], Decimal) else values[name]
            for name in SEMANTIC_FIELDS
        },
    }
    return _sha256(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def _canonical_values(values: Mapping[str, Any]) -> dict[str, Any]:
    if set(values) != set(SEMANTIC_FIELDS):
        raise ValueError("SEMANTIC_SCHEMA_INVALID")
    action = _required_text(values["action"], "action").upper()
    order_type = _required_text(values["order_type"], "order_type").upper()
    if action != "MARKET" or order_type not in {"BUY", "SELL"}:
        raise ValueError("UNSUPPORTED_SEMANTIC_MAPPING")
    return {
        "action": action,
        "symbol": _required_text(values["symbol"], "symbol"),
        "volume": _decimal(values["volume"], positive=True),
        "order_type": order_type,
        "price": _decimal(values["price"]),
        "stop_loss": _decimal(values["stop_loss"]),
        "take_profit": _decimal(values["take_profit"]),
        "deviation": _integer(values["deviation"]),
        "magic": _integer(values["magic"]),
        "comment": _required_text(values["comment"], "comment", maximum=64),
        "idempotency": _required_text(values["idempotency"], "idempotency"),
        "audit": _required_text(values["audit"], "audit"),
    }


def _decimal(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("SEMANTIC_NUMERIC_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("SEMANTIC_NUMERIC_INVALID") from exc
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        raise ValueError("SEMANTIC_NUMERIC_INVALID")
    return number.normalize() if number else Decimal(0)


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("SEMANTIC_INTEGER_INVALID")
    return value


def _required_text(value: Any, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name.upper()}_INVALID")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{name.upper()}_INVALID")
    return text


def _required_hash(value: Any) -> str:
    text = _required_text(value, "hash", maximum=64).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("HASH_INVALID")
    return text


def _validate_freshness(value: str, max_age_seconds: int) -> None:
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("LOCK_TIMESTAMP_INVALID") from exc
    age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    if age < -30 or age > max(1, max_age_seconds):
        raise ValueError("APPROVAL_EXPIRED")


def _authenticated(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(str(provided), str(expected))


def _receipt(
    status: str,
    idempotency_status: str,
    *,
    order_sent: bool = False,
    ticket_present: bool = False,
    deal_present: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "idempotency_status": idempotency_status,
        "live_execution_allowed": bool(order_sent),
        "order_send_allowed": bool(order_sent),
        "execution_allowed": bool(order_sent),
        "order_sent": bool(order_sent),
        "ticket": None,
        "deal": None,
        "ticket_present": bool(ticket_present),
        "deal_present": bool(deal_present),
        "metadata_redacted": True,
    }


def _blocked(reason: str, *, idempotency_status: str = "NOT_RESERVED") -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": reason,
        "idempotency_status": idempotency_status,
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "order_sent": False,
        "ticket": None,
        "deal": None,
        "ticket_present": False,
        "deal_present": False,
        "metadata_redacted": True,
    }


def _safe_reason(exc: Exception) -> str:
    value = str(exc).strip().upper()
    allowed = {
        "EXECUTION_DISABLED", "AUTHENTICATION_FAILED", "REQUEST_VERSION_INVALID",
        "SEMANTIC_SCHEMA_INVALID", "SEMANTIC_HASH_MISMATCH", "APPROVAL_LOCK_REFERENCE_MISMATCH",
        "IDEMPOTENCY_MISMATCH", "PRE_SUBMIT_VALIDATION_REQUIRED", "HUMAN_CONFIRMATION_INVALID",
        "LOCK_TIMESTAMP_INVALID", "APPROVAL_EXPIRED", "MT5_TRADING_CAPABILITY_UNAVAILABLE",
        "ACCOUNT_CONTEXT_MISMATCH", "ACCOUNT_CONTEXT_CHANGED", "UNSUPPORTED_SEMANTIC_MAPPING",
        "MT5_PACKAGE_UNAVAILABLE", "EXECUTION_JOURNAL_CORRUPT",
        "EXECUTION_JOURNAL_UNAVAILABLE",
    }
    return value if value in allowed else "INVALID_REQUEST"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
