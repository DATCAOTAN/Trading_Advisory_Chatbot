from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from tools.mt5_bridge.execution import (
    ProtectedExecutionJournal,
    ProtectedExecutionJournalError,
    _authenticated,
    _sha256,
)


RECONCILIATION_REQUEST_VERSION = "mt5-execution-reconciliation/v1"
EVIDENCE_CLASSIFICATIONS = {
    "UNIQUE_CONFIRMED_MATCH",
    "AMBIGUOUS_MATCH",
    "NO_MATCH",
    "QUERY_FAILED",
    "ACCOUNT_CONTEXT_CHANGED",
    "RECORD_NOT_ELIGIBLE",
}


@dataclass(frozen=True)
class ReconciliationConfig:
    enabled: bool = True
    auth_token: str = field(default="", repr=False)
    max_window_seconds: int = 86_400
    reserved_stale_seconds: int = 300
    submission_stale_seconds: int = 30
    journal_path: str = "data/trading/execution_journal/mt5_controlled_execution.jsonl"

    @classmethod
    def from_env(cls) -> "ReconciliationConfig":
        return cls(
            enabled=_env_bool("MT5_BRIDGE_RECONCILIATION_ENABLED", True),
            auth_token=os.getenv("MT5_BRIDGE_EXECUTION_TOKEN", ""),
            max_window_seconds=_env_int("MT5_BRIDGE_RECONCILIATION_MAX_WINDOW_SECONDS", 86_400),
            reserved_stale_seconds=_env_int("MT5_BRIDGE_RECONCILIATION_RESERVED_STALE_SECONDS", 300),
            submission_stale_seconds=_env_int("MT5_BRIDGE_RECONCILIATION_SUBMISSION_STALE_SECONDS", 30),
            journal_path=os.getenv(
                "MT5_BRIDGE_EXECUTION_JOURNAL_PATH",
                "data/trading/execution_journal/mt5_controlled_execution.jsonl",
            ).strip(),
        )


@dataclass(frozen=True)
class ProtectedReconciliationRequest:
    request_version: str
    protected_execution_reference: str
    correlation_identity: str = field(repr=False)
    correlation_tag: str
    expected_account_context_fingerprint: str
    symbol_reference: str
    expected_order_type: str
    expected_volume: str = field(repr=False)
    submission_window_start: str
    submission_window_end: str
    canonical_semantic_hash: str
    approval_reference: str
    lock_reference: str
    source_artifact_reference: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ProtectedReconciliationRequest":
        required = {
            "request_version",
            "protected_execution_reference",
            "correlation_identity",
            "correlation_tag",
            "expected_account_context_fingerprint",
            "symbol_reference",
            "expected_order_type",
            "expected_volume",
            "submission_window_start",
            "submission_window_end",
            "canonical_semantic_hash",
            "approval_reference",
            "lock_reference",
            "source_artifact_reference",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("RECONCILIATION_SCHEMA_INVALID")
        order_type = _text(payload["expected_order_type"], "ORDER_TYPE").upper()
        if order_type not in {"BUY", "SELL"}:
            raise ValueError("RECONCILIATION_ORDER_TYPE_INVALID")
        return cls(
            request_version=_text(payload["request_version"], "REQUEST_VERSION"),
            protected_execution_reference=_text(
                payload["protected_execution_reference"], "EXECUTION_REFERENCE"
            ),
            correlation_identity=_hash(payload["correlation_identity"]),
            correlation_tag=_text(payload["correlation_tag"], "CORRELATION_TAG", maximum=31),
            expected_account_context_fingerprint=_hash(
                payload["expected_account_context_fingerprint"]
            ),
            symbol_reference=_text(payload["symbol_reference"], "SYMBOL"),
            expected_order_type=order_type,
            expected_volume=_decimal_text(payload["expected_volume"], positive=True),
            submission_window_start=_text(payload["submission_window_start"], "WINDOW_START"),
            submission_window_end=_text(payload["submission_window_end"], "WINDOW_END"),
            canonical_semantic_hash=_hash(payload["canonical_semantic_hash"]),
            approval_reference=_text(payload["approval_reference"], "APPROVAL_REFERENCE"),
            lock_reference=_text(payload["lock_reference"], "LOCK_REFERENCE"),
            source_artifact_reference=_text(
                payload["source_artifact_reference"], "SOURCE_REFERENCE"
            ),
        )

    def reconciliation_reference(self) -> str:
        payload = {
            "version": self.request_version,
            "execution_reference": self.protected_execution_reference,
            "correlation_identity": self.correlation_identity,
            "window_start": self.submission_window_start,
            "window_end": self.submission_window_end,
        }
        digest = _sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return "mt5_reconciliation_" + digest[:24]


class ControlledMT5ReconciliationService:
    def __init__(
        self,
        client: Any,
        *,
        config: ReconciliationConfig | None = None,
        journal: ProtectedExecutionJournal | None = None,
    ):
        self.client = client
        self.config = config or ReconciliationConfig.from_env()
        self.journal = journal or ProtectedExecutionJournal(self.config.journal_path)

    def handle(self, payload: Mapping[str, Any], provided_token: str) -> tuple[dict[str, Any], int]:
        if not _authenticated(provided_token, self.config.auth_token):
            return _blocked("AUTHENTICATION_FAILED"), 401
        if not self.config.enabled:
            return _blocked("RECONCILIATION_DISABLED"), 403
        try:
            request = ProtectedReconciliationRequest.from_payload(payload)
            if request.request_version != RECONCILIATION_REQUEST_VERSION:
                raise ValueError("RECONCILIATION_VERSION_INVALID")
            start, end = _validated_window(
                request.submission_window_start,
                request.submission_window_end,
                self.config.max_window_seconds,
            )
            record = self.journal.execution_record(request.correlation_identity)
            if record is None:
                raise ValueError("EXECUTION_RECORD_NOT_FOUND")
            self._validate_record(request, record)
            context = self._validated_account_context(request.expected_account_context_fingerprint)
            original_state = str(record["state"])
            state_age = _age_seconds(str(record["state_created_at"]))
            recovery_state = None
            recovery_reason = ""
            if original_state == "RESERVED" and state_age >= self.config.reserved_stale_seconds:
                recovery_state = "RESERVATION_ABANDONED"
                recovery_reason = "STALE_RESERVED_WITHOUT_SUBMISSION_STARTED"
            elif (
                original_state == "SUBMISSION_STARTED"
                and state_age >= self.config.submission_stale_seconds
            ):
                recovery_state = "RESULT_UNKNOWN"
                recovery_reason = "STALE_SUBMISSION_STARTED"

            reference = request.reconciliation_reference()
            existing, started = self.journal.begin_reconciliation(
                reference,
                request.correlation_identity,
                recovery_state=recovery_state,
                recovery_reason=recovery_reason,
            )
            if not started:
                return _public_receipt(existing), 200

            current_state = recovery_state or original_state
            if current_state == "RESERVATION_ABANDONED":
                completed = self.journal.complete_reconciliation(
                    reference,
                    request.correlation_identity,
                    reconciliation_status="INCONCLUSIVE",
                    evidence_classification="RECORD_NOT_ELIGIBLE",
                    original_execution_state=original_state,
                    resulting_execution_state=current_state,
                    retry_decision="NEW_REQUEST_REQUIRED",
                    reasons=[recovery_reason],
                    account_fingerprint=context["account_context_fingerprint"],
                )
                return _public_receipt(completed), 200
            if current_state == "RESERVED" or current_state == "SUBMISSION_STARTED":
                return _public_receipt(existing, original_state=original_state), 200
            if current_state != "RESULT_UNKNOWN":
                completed = self.journal.complete_reconciliation(
                    reference,
                    request.correlation_identity,
                    reconciliation_status="NOT_REQUIRED",
                    evidence_classification="RECORD_NOT_ELIGIBLE",
                    original_execution_state=original_state,
                    resulting_execution_state=current_state,
                    retry_decision="RETRY_PROHIBITED",
                    reasons=["EXECUTION_STATE_NOT_RECONCILABLE"],
                    account_fingerprint=context["account_context_fingerprint"],
                )
                return _public_receipt(completed), 200

            try:
                evidence = self.client.reconciliation_evidence(start, end)
            except Exception:
                evidence = {"status": "QUERY_FAILED", "orders": [], "deals": [], "positions": []}
            match = _match_evidence(request, evidence)
            status = {
                "UNIQUE_CONFIRMED_MATCH": "CONFIRMED",
                "QUERY_FAILED": "FAILED",
            }.get(match["classification"], "INCONCLUSIVE")
            resulting_state = (
                "RESULT_CONFIRMED"
                if match["classification"] == "UNIQUE_CONFIRMED_MATCH"
                else "RESULT_UNKNOWN"
            )
            completed = self.journal.complete_reconciliation(
                reference,
                request.correlation_identity,
                reconciliation_status=status,
                evidence_classification=match["classification"],
                original_execution_state=original_state,
                resulting_execution_state=resulting_state,
                retry_decision="RETRY_PROHIBITED",
                reasons=match["reasons"],
                account_fingerprint=context["account_context_fingerprint"],
                protected_broker_references=match["protected_broker_references"],
            )
            return _public_receipt(completed), 200
        except ValueError as exc:
            reason = str(exc) if str(exc).isupper() else "RECONCILIATION_INVALID"
            return _blocked(reason), 403
        except ProtectedExecutionJournalError as exc:
            return _blocked(str(exc)), 409
        except RuntimeError:
            return _blocked("RECONCILIATION_STATE_CONFLICT"), 409

    def _validate_record(
        self, request: ProtectedReconciliationRequest, record: Mapping[str, Any]
    ) -> None:
        protected = record.get("protected_execution", {})
        expected = {
            "protected_execution_reference": request.protected_execution_reference,
            "correlation_identity": request.correlation_identity,
            "correlation_tag": request.correlation_tag,
            "canonical_semantic_hash": request.canonical_semantic_hash,
            "approval_reference": request.approval_reference,
            "lock_reference": request.lock_reference,
            "source_artifact_reference": request.source_artifact_reference,
            "symbol": request.symbol_reference,
            "order_type": request.expected_order_type,
            "volume": request.expected_volume,
        }
        for key, value in expected.items():
            if not hmac.compare_digest(str(protected.get(key, "")), str(value)):
                raise ValueError("RECONCILIATION_INTEGRITY_MISMATCH")

    def _validated_account_context(self, expected_fingerprint: str) -> dict[str, Any]:
        context = self.client.execution_context()
        if (
            context.get("status") != "OK"
            or context.get("terminal_connected") is not True
        ):
            raise ValueError("RECONCILIATION_QUERY_UNAVAILABLE")
        actual = str(context.get("account_context_fingerprint", ""))
        if not actual or not hmac.compare_digest(actual, expected_fingerprint):
            raise ValueError("ACCOUNT_CONTEXT_CHANGED")
        return context


def _match_evidence(
    request: ProtectedReconciliationRequest, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    if evidence.get("status") != "OK":
        return _match("QUERY_FAILED", ["MT5_HISTORY_QUERY_FAILED"])
    orders = [row for row in evidence.get("orders", []) if _row_matches(request, row, "order")]
    deals = [row for row in evidence.get("deals", []) if _row_matches(request, row, "deal")]
    positions = [row for row in evidence.get("positions", []) if _row_matches(request, row, "position")]
    if not orders and not deals and not positions:
        return _match("NO_MATCH", ["NO_BROKER_EVIDENCE_IN_BOUNDED_WINDOW"])

    orders_by_id = {str(row.get("ticket")): row for row in orders if row.get("ticket") is not None}
    positions_by_id = {
        str(row.get("ticket")): row for row in positions if row.get("ticket") is not None
    }
    groups: dict[str, dict[str, Any]] = {}
    for deal in deals:
        order_id = str(deal.get("order") or "")
        deal_id = str(deal.get("ticket") or "")
        key = order_id or "deal:" + deal_id
        group = groups.setdefault(key, {"deals": [], "order": None, "positions": []})
        group["deals"].append(deal)
        if order_id in orders_by_id:
            group["order"] = orders_by_id[order_id]
        position_id = str(deal.get("position_id") or "")
        if position_id in positions_by_id:
            group["positions"].append(positions_by_id[position_id])

    candidates = []
    expected_volume = Decimal(request.expected_volume)
    for group in groups.values():
        total_volume = sum((Decimal(str(row.get("volume", "0"))) for row in group["deals"]), Decimal(0))
        tagged = any(request.correlation_tag in str(row.get("comment", "")) for row in group["deals"])
        linked = group["order"] is not None or bool(group["positions"])
        if total_volume == expected_volume and (linked or tagged):
            candidates.append(group)

    if len(candidates) != 1:
        return _match(
            "AMBIGUOUS_MATCH",
            ["MULTIPLE_OR_WEAK_BROKER_EVIDENCE"],
        )
    candidate = candidates[0]
    broker_refs = {
        "orders": [candidate["order"].get("ticket")] if candidate["order"] else [],
        "deals": [row.get("ticket") for row in candidate["deals"]],
        "positions": [row.get("ticket") for row in candidate["positions"]],
    }
    return _match(
        "UNIQUE_CONFIRMED_MATCH",
        ["SYMBOL_DIRECTION_VOLUME_TIME_AND_RELATIONSHIP_MATCH"],
        broker_refs,
    )


def _row_matches(
    request: ProtectedReconciliationRequest, row: Mapping[str, Any], row_kind: str
) -> bool:
    if str(row.get("symbol", "")) != request.symbol_reference:
        return False
    if str(row.get("direction", "")).upper() != request.expected_order_type:
        return False
    if row_kind == "position":
        return True
    try:
        volume = Decimal(str(row.get("volume", "")))
    except InvalidOperation:
        return False
    return volume > 0


def _match(
    classification: str,
    reasons: list[str],
    protected_broker_references: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if classification not in EVIDENCE_CLASSIFICATIONS:
        raise ValueError("invalid evidence classification")
    return {
        "classification": classification,
        "reasons": reasons,
        "protected_broker_references": dict(protected_broker_references or {}),
    }


def _public_receipt(
    row: Mapping[str, Any], *, original_state: str | None = None
) -> dict[str, Any]:
    protected = row.get("protected_broker_references", {})
    return {
        "status": row.get("reconciliation_status", "PENDING"),
        "reconciliation_reference": row.get("reconciliation_reference", ""),
        "evidence_classification": row.get("evidence_classification", "RECORD_NOT_ELIGIBLE"),
        "original_execution_state": row.get("original_execution_state", original_state or "UNKNOWN"),
        "resulting_execution_state": row.get("resulting_execution_state", original_state or "UNKNOWN"),
        "retry_decision": row.get("retry_decision", "RETRY_PROHIBITED"),
        "order_reference_present": bool(protected.get("orders")),
        "deal_reference_present": bool(protected.get("deals")),
        "position_reference_present": bool(protected.get("positions")),
        "live_submission_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "automatic_retry_allowed": False,
        "order_sent": False,
        "ticket": None,
        "deal": None,
        "position": None,
        "metadata_redacted": True,
    }


def _blocked(reason: str) -> dict[str, Any]:
    payload = _public_receipt({"reconciliation_status": "BLOCKED"})
    payload["reason"] = reason
    if reason in EVIDENCE_CLASSIFICATIONS:
        payload["evidence_classification"] = reason
    return payload


def _validated_window(start_value: str, end_value: str, maximum_seconds: int):
    start = _timestamp(start_value)
    end = _timestamp(end_value)
    seconds = (end - start).total_seconds()
    if seconds <= 0 or seconds > max(1, maximum_seconds):
        raise ValueError("RECONCILIATION_WINDOW_INVALID")
    now = datetime.now(timezone.utc)
    if end > now.replace(microsecond=now.microsecond) and (end - now).total_seconds() > 30:
        raise ValueError("RECONCILIATION_WINDOW_INVALID")
    return start, end


def _age_seconds(value: str) -> float:
    return max(0.0, (datetime.now(timezone.utc) - _timestamp(value)).total_seconds())


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("RECONCILIATION_TIMESTAMP_INVALID") from exc


def _decimal_text(value: Any, *, positive: bool = False) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("RECONCILIATION_VOLUME_INVALID") from exc
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        raise ValueError("RECONCILIATION_VOLUME_INVALID")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _text(value: Any, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"RECONCILIATION_{name}_INVALID")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"RECONCILIATION_{name}_INVALID")
    return text


def _hash(value: Any) -> str:
    text = _text(value, "HASH", maximum=64).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("RECONCILIATION_HASH_INVALID")
    return text


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
