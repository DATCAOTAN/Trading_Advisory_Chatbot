from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from tools.mt5_bridge.execution import (
    ProtectedExecutionJournal,
    ProtectedExecutionJournalError,
    _authenticated,
    _env_bool,
    _env_float,
    _env_int,
    _isolated_order_send,
)
from tools.mt5_bridge.mt5_client import protection_reference_hash


MANAGEMENT_REQUEST_VERSION = "controlled-mt5-management/v1"
MANAGEMENT_INTENTS = {
    "CANCEL_PENDING_ORDER",
    "MODIFY_POSITION_PROTECTION",
    "CLOSE_POSITION",
}
CONFIRMATION_PHRASES = {
    "CANCEL_PENDING_ORDER": "CANCEL ONE CONTROLLED MT5 PENDING ORDER",
    "MODIFY_POSITION_PROTECTION": "MODIFY PROTECTION FOR ONE CONTROLLED MT5 POSITION",
    "CLOSE_POSITION": "CLOSE ONE CONTROLLED MT5 POSITION",
}
ELIGIBLE_STATES = {
    "CANCEL_PENDING_ORDER": {"ORDER_ACTIVE"},
    "MODIFY_POSITION_PROTECTION": {"POSITION_OPEN", "POSITION_PARTIALLY_REDUCED"},
    "CLOSE_POSITION": {"POSITION_OPEN", "POSITION_PARTIALLY_REDUCED"},
}


@dataclass(frozen=True)
class ControlledManagementConfig:
    enabled: bool = False
    hard_block: bool = True
    kill_switch_engaged: bool = True
    global_kill_switch_engaged: bool = True
    cancel_allowed: bool = False
    protection_modification_allowed: bool = False
    position_close_allowed: bool = False
    order_send_enabled: bool = False
    live_execution_enabled: bool = False
    auth_token: str = field(default="", repr=False)
    max_request_age_seconds: int = 300
    submit_timeout_seconds: float = 5.0
    history_window_seconds: int = 86_400
    journal_path: str = "data/trading/execution_journal/mt5_controlled_execution.jsonl"
    lifecycle_journal_path: str = "data/trading/execution_journal/mt5_position_lifecycle.jsonl"

    @classmethod
    def from_env(cls) -> "ControlledManagementConfig":
        return cls(
            enabled=_env_bool("MT5_BRIDGE_CONTROLLED_MANAGEMENT_ENABLED", False),
            hard_block=_env_bool("MT5_BRIDGE_CONTROLLED_MANAGEMENT_HARD_BLOCK", True),
            kill_switch_engaged=_env_bool("MT5_BRIDGE_MANAGEMENT_KILL_SWITCH", True),
            global_kill_switch_engaged=_env_bool("MT5_BRIDGE_EXECUTION_KILL_SWITCH", True),
            cancel_allowed=_env_bool("MT5_BRIDGE_MANAGEMENT_CANCEL_ALLOWED", False),
            protection_modification_allowed=_env_bool(
                "MT5_BRIDGE_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED", False
            ),
            position_close_allowed=_env_bool("MT5_BRIDGE_MANAGEMENT_POSITION_CLOSE_ALLOWED", False),
            order_send_enabled=_env_bool("MT5_BRIDGE_ORDER_SEND_ENABLED", False),
            live_execution_enabled=_env_bool("MT5_BRIDGE_LIVE_EXECUTION_ENABLED", False),
            auth_token=os.getenv("MT5_BRIDGE_EXECUTION_TOKEN", ""),
            max_request_age_seconds=_env_int("MT5_BRIDGE_MANAGEMENT_MAX_REQUEST_AGE_SECONDS", 300),
            submit_timeout_seconds=_env_float("MT5_BRIDGE_EXECUTION_TIMEOUT_SECONDS", 5.0),
            history_window_seconds=_env_int("MT5_BRIDGE_RECONCILIATION_MAX_WINDOW_SECONDS", 86_400),
            journal_path=os.getenv(
                "MT5_BRIDGE_EXECUTION_JOURNAL_PATH",
                "data/trading/execution_journal/mt5_controlled_execution.jsonl",
            ).strip(),
            lifecycle_journal_path=os.getenv(
                "MT5_BRIDGE_POSITION_LIFECYCLE_JOURNAL_PATH",
                "data/trading/execution_journal/mt5_position_lifecycle.jsonl",
            ).strip(),
        )


@dataclass(frozen=True)
class ProtectedBridgeManagementRequest:
    request_version: str
    management_intent: str
    protected_execution_reference: str
    lifecycle_observation_reference: str
    lifecycle_observation_hash: str
    source_snapshot_reference: str
    expected_account_context_fingerprint: str = field(repr=False)
    protected_broker_reference: str = field(repr=False)
    symbol: str
    current_observed_volume: str = field(repr=False)
    requested_resulting_volume: str | None = field(default=None, repr=False)
    requested_stop_loss: str | None = field(default=None, repr=False)
    requested_take_profit: str | None = field(default=None, repr=False)
    requested_deviation: int | None = field(default=None, repr=False)
    lifecycle_state: str = "UNKNOWN"
    lifecycle_observed_at: str = ""
    mutation_hash: str = ""
    idempotency_key: str = field(default="", repr=False)
    created_at: str = ""
    expires_at: str = ""
    human_confirmation_reference: str = ""
    human_confirmation_phrase: str = field(default="", repr=False)
    human_confirmation_timestamp: str = ""
    integrity_hash: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ProtectedBridgeManagementRequest":
        required = set(cls.__dataclass_fields__)
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("MANAGEMENT_SCHEMA_INVALID")
        return cls(
            request_version=_text(payload["request_version"], "REQUEST_VERSION"),
            management_intent=_intent(payload["management_intent"]),
            protected_execution_reference=_text(payload["protected_execution_reference"], "EXECUTION_REFERENCE"),
            lifecycle_observation_reference=_text(payload["lifecycle_observation_reference"], "OBSERVATION_REFERENCE"),
            lifecycle_observation_hash=_hash(payload["lifecycle_observation_hash"]),
            source_snapshot_reference=_text(payload["source_snapshot_reference"], "SNAPSHOT_REFERENCE"),
            expected_account_context_fingerprint=_hash(payload["expected_account_context_fingerprint"]),
            protected_broker_reference=_hash(payload["protected_broker_reference"]),
            symbol=_text(payload["symbol"], "SYMBOL", maximum=64),
            current_observed_volume=_decimal_text(payload["current_observed_volume"], positive=True),
            requested_resulting_volume=_optional_decimal(payload["requested_resulting_volume"]),
            requested_stop_loss=_optional_decimal(payload["requested_stop_loss"]),
            requested_take_profit=_optional_decimal(payload["requested_take_profit"]),
            requested_deviation=_optional_integer(payload["requested_deviation"]),
            lifecycle_state=_text(payload["lifecycle_state"], "LIFECYCLE_STATE"),
            lifecycle_observed_at=_text(payload["lifecycle_observed_at"], "LIFECYCLE_TIMESTAMP"),
            mutation_hash=_hash(payload["mutation_hash"]),
            idempotency_key=_text(payload["idempotency_key"], "IDEMPOTENCY_KEY"),
            created_at=_text(payload["created_at"], "CREATED_AT"),
            expires_at=_text(payload["expires_at"], "EXPIRES_AT"),
            human_confirmation_reference=_hash(payload["human_confirmation_reference"]),
            human_confirmation_phrase=_text(payload["human_confirmation_phrase"], "CONFIRMATION_PHRASE"),
            human_confirmation_timestamp=_text(payload["human_confirmation_timestamp"], "CONFIRMATION_TIMESTAMP"),
            integrity_hash=_hash(payload["integrity_hash"]),
        )

    def protected_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class ControlledMT5ManagementService:
    def __init__(
        self,
        client: Any,
        *,
        config: ControlledManagementConfig | None = None,
        mt5_module: Any = None,
        journal: ProtectedExecutionJournal | None = None,
    ):
        from tools.mt5_bridge.mt5_client import mt5

        self.client = client
        self.config = config or ControlledManagementConfig.from_env()
        self.mt5 = mt5 if mt5_module is None else mt5_module
        self.journal = journal or ProtectedExecutionJournal(self.config.journal_path)

    def handle(self, payload: Mapping[str, Any], provided_token: str) -> tuple[dict[str, Any], int]:
        if not _authenticated(provided_token, self.config.auth_token):
            return _blocked("AUTHENTICATION_FAILED"), 401
        try:
            request = ProtectedBridgeManagementRequest.from_payload(payload)
            self._validate_config(request.management_intent)
            self._validate_integrity(request)
            execution = self.journal.execution_record_by_reference(
                request.protected_execution_reference
            )
            if execution is None:
                raise ValueError("EXECUTION_RECORD_NOT_FOUND")
            observation = _read_lifecycle_observation(
                self.config.lifecycle_journal_path,
                request.lifecycle_observation_reference,
            )
            self._validate_sources(request, execution, observation)
            first_context = self._validated_account_context(
                request.expected_account_context_fingerprint
            )
            target = self.client.resolve_management_target(
                "order" if request.management_intent == "CANCEL_PENDING_ORDER" else "position",
                request.protected_broker_reference,
                request.symbol,
            )
            self._validate_target(request, target)
            mapped = self._map_request(request, target)
            request_hash = _sha256(_canonical_json(payload))
            if not self.journal.reserve_management(
                request.idempotency_key,
                request_hash,
                first_context["account_context_fingerprint"],
                protected_management={
                    "protected_management_reference": "mt5_management_" + request.integrity_hash[:24],
                    "management_intent": request.management_intent,
                    "protected_execution_reference": request.protected_execution_reference,
                    "lifecycle_observation_reference": request.lifecycle_observation_reference,
                    "protected_broker_reference": request.protected_broker_reference,
                    "protected_broker_identifier": target["ticket"],
                    "symbol": request.symbol,
                    "previous_lifecycle_state": request.lifecycle_state,
                    "requested_state_hash": request.mutation_hash,
                    "source_snapshot_reference": request.source_snapshot_reference,
                },
            ):
                return _blocked(
                    "IDEMPOTENCY_DUPLICATE",
                    intent=request.management_intent,
                    idempotency_status="DUPLICATE_BLOCKED",
                ), 409
            try:
                second_context = self._validated_account_context(
                    request.expected_account_context_fingerprint
                )
            except ValueError:
                self.journal.transition_management(
                    request.idempotency_key,
                    "RESULT_REJECTED",
                    reason="ACCOUNT_CONTEXT_CHANGED",
                )
                return _blocked("ACCOUNT_CONTEXT_CHANGED", intent=request.management_intent), 409
            if not hmac.compare_digest(
                first_context["account_context_fingerprint"],
                second_context["account_context_fingerprint"],
            ):
                self.journal.transition_management(
                    request.idempotency_key,
                    "RESULT_REJECTED",
                    reason="ACCOUNT_CONTEXT_CHANGED",
                )
                return _blocked("ACCOUNT_CONTEXT_CHANGED", intent=request.management_intent), 409
            self.journal.transition_management(request.idempotency_key, "MANAGEMENT_STARTED")
            return self._submit_and_reconcile(request, mapped, target, execution)
        except ProtectedExecutionJournalError as exc:
            return _blocked(str(exc)), 409
        except (TypeError, ValueError, RuntimeError) as exc:
            return _blocked(_safe_reason(exc)), 403

    def _validate_config(self, intent: str) -> None:
        intent_allowed = {
            "CANCEL_PENDING_ORDER": self.config.cancel_allowed,
            "MODIFY_POSITION_PROTECTION": self.config.protection_modification_allowed,
            "CLOSE_POSITION": self.config.position_close_allowed,
        }[intent]
        if (
            not self.config.enabled
            or self.config.hard_block
            or self.config.kill_switch_engaged
            or self.config.global_kill_switch_engaged
            or not intent_allowed
            or not self.config.order_send_enabled
            or not self.config.live_execution_enabled
        ):
            raise ValueError("MANAGEMENT_DISABLED")
        if not self.config.auth_token:
            raise ValueError("AUTHENTICATION_FAILED")

    def _validate_integrity(self, request: ProtectedBridgeManagementRequest) -> None:
        if request.request_version != MANAGEMENT_REQUEST_VERSION:
            raise ValueError("MANAGEMENT_REQUEST_VERSION_INVALID")
        values = request.protected_dict()
        if not hmac.compare_digest(request.mutation_hash, _mutation_hash(values)):
            raise ValueError("MANAGEMENT_MUTATION_HASH_MISMATCH")
        phrase = CONFIRMATION_PHRASES[request.management_intent]
        if not hmac.compare_digest(request.human_confirmation_phrase, phrase):
            raise ValueError("MANAGEMENT_CONFIRMATION_INVALID")
        expected_confirmation = _sha256(
            "|".join(
                (
                    phrase,
                    request.management_intent,
                    request.protected_broker_reference,
                    request.expected_account_context_fingerprint,
                    request.lifecycle_observation_reference,
                    request.mutation_hash,
                    request.human_confirmation_timestamp,
                )
            )
        )
        if not hmac.compare_digest(request.human_confirmation_reference, expected_confirmation):
            raise ValueError("MANAGEMENT_CONFIRMATION_INVALID")
        if not hmac.compare_digest(request.integrity_hash, _request_integrity_hash(values)):
            raise ValueError("MANAGEMENT_INTEGRITY_MISMATCH")
        now = datetime.now(timezone.utc)
        observed = _parse_timestamp(request.lifecycle_observed_at)
        created = _parse_timestamp(request.created_at)
        confirmed = _parse_timestamp(request.human_confirmation_timestamp)
        expires = _parse_timestamp(request.expires_at)
        if (
            (now - observed).total_seconds() > self.config.max_request_age_seconds
            or now > expires
            or created > now + timedelta(seconds=30)
            or confirmed > now + timedelta(seconds=30)
            or confirmed < created - timedelta(seconds=1)
            or (now - confirmed).total_seconds() > self.config.max_request_age_seconds
        ):
            raise ValueError("LIFECYCLE_OBSERVATION_STALE")
        _validate_intent_values(request)

    def _validate_sources(
        self,
        request: ProtectedBridgeManagementRequest,
        execution: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> None:
        protected = execution.get("protected_execution", {})
        if execution.get("state") != "RESULT_CONFIRMED":
            raise ValueError("EXECUTION_RECORD_NOT_ELIGIBLE")
        expected_execution = {
            "protected_execution_reference": request.protected_execution_reference,
            "symbol": request.symbol,
        }
        if any(
            not hmac.compare_digest(str(protected.get(key, "")), str(value))
            for key, value in expected_execution.items()
        ):
            raise ValueError("MANAGEMENT_SOURCE_MISMATCH")
        if not hmac.compare_digest(
            str(execution.get("account_context_fingerprint", "")),
            request.expected_account_context_fingerprint,
        ):
            raise ValueError("ACCOUNT_CONTEXT_CHANGED")
        if observation.get("discrepancy_reason"):
            raise ValueError("LIFECYCLE_OBSERVATION_INELIGIBLE")
        expected_observation = {
            "observation_id": request.lifecycle_observation_reference,
            "observation_hash": request.lifecycle_observation_hash,
            "protected_execution_reference": request.protected_execution_reference,
            "lifecycle_state": request.lifecycle_state,
            "source_snapshot_reference": request.source_snapshot_reference,
            "observation_timestamp": request.lifecycle_observed_at,
            "account_fingerprint_hash": _sha256(request.expected_account_context_fingerprint),
        }
        if any(
            not hmac.compare_digest(str(observation.get(key, "")), str(value))
            for key, value in expected_observation.items()
        ):
            raise ValueError("LIFECYCLE_OBSERVATION_MISMATCH")
        if request.lifecycle_state not in ELIGIBLE_STATES[request.management_intent]:
            raise ValueError("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE")
        key = "orders" if request.management_intent == "CANCEL_PENDING_ORDER" else "positions"
        references = observation.get("protected_broker_references", {}).get(key, [])
        if references != [request.protected_broker_reference]:
            raise ValueError("PROTECTED_BROKER_REFERENCE_AMBIGUOUS")

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
            raise ValueError("ACCOUNT_CONTEXT_CHANGED")
        return context

    def _validate_target(
        self, request: ProtectedBridgeManagementRequest, target: Mapping[str, Any]
    ) -> None:
        if target.get("status") != "OK" or target.get("match_count") != 1:
            raise ValueError("PROTECTED_BROKER_TARGET_NOT_UNIQUE")
        expected_kind = "order" if request.management_intent == "CANCEL_PENDING_ORDER" else "position"
        if target.get("target_kind") != expected_kind:
            raise ValueError("PROTECTED_BROKER_TARGET_MISMATCH")
        if not hmac.compare_digest(
            str(target.get("broker_reference_hash", "")),
            request.protected_broker_reference,
        ) or not hmac.compare_digest(str(target.get("symbol", "")), request.symbol):
            raise ValueError("PROTECTED_BROKER_TARGET_MISMATCH")
        current = Decimal(_decimal_text(target.get("volume"), positive=True))
        if current != Decimal(request.current_observed_volume):
            raise ValueError("OBSERVED_VOLUME_CHANGED")
        _validate_target_values(request, target)

    def _map_request(
        self, request: ProtectedBridgeManagementRequest, target: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self.mt5 is None:
            raise ValueError("MT5_PACKAGE_UNAVAILABLE")
        if request.management_intent == "CANCEL_PENDING_ORDER":
            _require_constants(self.mt5, "TRADE_ACTION_REMOVE")
            return {"action": self.mt5.TRADE_ACTION_REMOVE, "order": target["ticket"]}
        if request.management_intent == "MODIFY_POSITION_PROTECTION":
            _require_constants(self.mt5, "TRADE_ACTION_SLTP")
            return {
                "action": self.mt5.TRADE_ACTION_SLTP,
                "position": target["ticket"],
                "symbol": request.symbol,
                "sl": float(Decimal(
                    request.requested_stop_loss
                    if request.requested_stop_loss is not None
                    else str(target.get("stop_loss", "0"))
                )),
                "tp": float(Decimal(
                    request.requested_take_profit
                    if request.requested_take_profit is not None
                    else str(target.get("take_profit", "0"))
                )),
            }
        _require_constants(self.mt5, "TRADE_ACTION_DEAL", "ORDER_TYPE_BUY", "ORDER_TYPE_SELL")
        direction = str(target.get("direction", ""))
        close_type = self.mt5.ORDER_TYPE_SELL if direction == "BUY" else self.mt5.ORDER_TYPE_BUY
        close_volume = Decimal(request.current_observed_volume) - Decimal(
            request.requested_resulting_volume or "0"
        )
        price = target.get("bid") if direction == "BUY" else target.get("ask")
        if price is None or Decimal(str(price)) <= 0:
            raise ValueError("MT5_PRICE_UNAVAILABLE")
        return {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": target["ticket"],
            "symbol": request.symbol,
            "volume": float(close_volume),
            "type": close_type,
            "price": float(price),
            "deviation": request.requested_deviation,
        }

    def _submit_and_reconcile(
        self,
        request: ProtectedBridgeManagementRequest,
        mapped: Mapping[str, Any],
        target: Mapping[str, Any],
        execution: Mapping[str, Any],
    ) -> tuple[dict[str, Any], int]:
        result_data: dict[str, Any] = {}
        accepted = False
        unknown_reason = ""
        try:
            result = _isolated_order_send(self.mt5, dict(mapped), self.config.submit_timeout_seconds)
            if result is None:
                unknown_reason = "NO_RESULT"
            else:
                result_data = result._asdict() if hasattr(result, "_asdict") else dict(vars(result))
                accepted_codes = {
                    getattr(self.mt5, name, object())
                    for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED")
                }
                accepted = result_data.get("retcode") in accepted_codes
        except Exception as exc:
            unknown_reason = type(exc).__name__
        if not accepted and not unknown_reason:
            self.journal.transition_management(
                request.idempotency_key,
                "RESULT_REJECTED",
                reason="BROKER_REJECTED",
                retcode=result_data.get("retcode"),
                order=result_data.get("order"),
                deal=result_data.get("deal"),
                position=target.get("ticket"),
            )
            return _receipt(
                "REJECTED", request.management_intent, "RESULT_REJECTED", reason="BROKER_REJECTED"
            ), 200
        evidence = self._reconcile(request, execution, target)
        confirmed = evidence["confirmed"] is True
        state = "RESULT_CONFIRMED" if confirmed else "RESULT_UNKNOWN"
        self.journal.transition_management(
            request.idempotency_key,
            state,
            reason="" if confirmed else (unknown_reason or evidence["reason"]),
            retcode=result_data.get("retcode"),
            order=result_data.get("order"),
            deal=result_data.get("deal"),
            position=target.get("ticket"),
            reconciliation_status=evidence["status"],
            requested_state_hash=request.mutation_hash,
        )
        return _receipt(
            "ACCEPTED" if confirmed else "UNKNOWN",
            request.management_intent,
            state,
            management_applied=confirmed,
            reconciliation_required=not confirmed,
            order_sent=accepted,
            ticket_present=bool(result_data.get("order")),
            deal_present=bool(result_data.get("deal")),
            position_present=bool(target.get("ticket")),
            reason="" if confirmed else (unknown_reason or evidence["reason"]),
        ), 200

    def _reconcile(
        self,
        request: ProtectedBridgeManagementRequest,
        execution: Mapping[str, Any],
        target: Mapping[str, Any],
    ) -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        tag = str(execution.get("protected_execution", {}).get("correlation_tag", ""))
        try:
            snapshot = self.client.lifecycle_snapshot(
                end - timedelta(seconds=max(1, self.config.history_window_seconds)),
                end,
                [tag] if tag else [],
            )
        except Exception:
            return {"confirmed": False, "status": "QUERY_FAILED", "reason": "RECONCILIATION_QUERY_FAILED"}
        if snapshot.get("status") != "OK":
            return {"confirmed": False, "status": "QUERY_FAILED", "reason": "RECONCILIATION_QUERY_FAILED"}
        ref = request.protected_broker_reference
        active_orders = [row for row in snapshot.get("active_orders", []) if row.get("broker_reference_hash") == ref]
        positions = [row for row in snapshot.get("positions", []) if row.get("broker_reference_hash") == ref]
        if request.management_intent == "CANCEL_PENDING_ORDER":
            confirmed = not active_orders
        elif request.management_intent == "MODIFY_POSITION_PROTECTION":
            expected = protection_reference_hash(
                request.symbol,
                request.requested_stop_loss
                if request.requested_stop_loss is not None
                else target.get("stop_loss", "0"),
                request.requested_take_profit
                if request.requested_take_profit is not None
                else target.get("take_profit", "0"),
            )
            confirmed = len(positions) == 1 and positions[0].get("protection_reference_hash") == expected
        else:
            resulting = Decimal(request.requested_resulting_volume or "0")
            if resulting > 0:
                confirmed = len(positions) == 1 and Decimal(str(positions[0].get("volume", "-1"))) == resulting
            else:
                closing = [
                    row
                    for row in snapshot.get("recent_deals", [])
                    if row.get("position_reference_hash") == ref and row.get("entry") in {"OUT", "INOUT"}
                ]
                confirmed = not positions and len(closing) == 1
        return {
            "confirmed": confirmed,
            "status": "CONFIRMED" if confirmed else "INCONCLUSIVE",
            "reason": "" if confirmed else "MANAGEMENT_EVIDENCE_INCONCLUSIVE",
        }


def _read_lifecycle_observation(path: str, observation_id: str) -> dict[str, Any]:
    journal = Path(path)
    if not journal.exists():
        raise ValueError("LIFECYCLE_JOURNAL_MISSING")
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("LIFECYCLE_JOURNAL_UNAVAILABLE") from exc
    found = None
    latest: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("LIFECYCLE_JOURNAL_CORRUPT") from exc
        if not isinstance(row, dict) or row.get("record_type") != "LIFECYCLE_OBSERVATION" or row.get("metadata_redacted") is not True:
            raise ValueError("LIFECYCLE_JOURNAL_CORRUPT")
        reference = str(row.get("protected_execution_reference", ""))
        previous = latest.get(reference, "UNKNOWN")
        if row.get("previous_lifecycle_state") != previous:
            raise ValueError("LIFECYCLE_JOURNAL_CORRUPT")
        stable = {
            key: row.get(key)
            for key in (
                "protected_execution_reference", "lifecycle_state", "account_fingerprint_hash",
                "evidence_classification", "protected_broker_references", "discrepancy_reason",
                "source_snapshot_reference",
            )
        }
        if not hmac.compare_digest(str(row.get("observation_hash", "")), _sha256(_canonical_json(stable))):
            raise ValueError("LIFECYCLE_JOURNAL_CORRUPT")
        latest[reference] = str(row.get("lifecycle_state", ""))
        if row.get("observation_id") == observation_id:
            found = row
    if found is None:
        raise ValueError("LIFECYCLE_OBSERVATION_NOT_FOUND")
    return found


def _validate_intent_values(request: ProtectedBridgeManagementRequest) -> None:
    current = Decimal(request.current_observed_volume)
    resulting = Decimal(request.requested_resulting_volume) if request.requested_resulting_volume is not None else None
    if request.lifecycle_state not in ELIGIBLE_STATES[request.management_intent]:
        raise ValueError("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE")
    if request.management_intent == "CANCEL_PENDING_ORDER":
        if resulting not in {None, Decimal(0)} or any(value is not None for value in (request.requested_stop_loss, request.requested_take_profit, request.requested_deviation)):
            raise ValueError("MANAGEMENT_VALUES_INVALID")
    elif request.management_intent == "MODIFY_POSITION_PROTECTION":
        if resulting != current:
            raise ValueError("POSITION_VOLUME_INCREASE_NOT_ALLOWED")
        if request.requested_stop_loss is None and request.requested_take_profit is None:
            raise ValueError("PROTECTION_VALUES_REQUIRED")
        if request.requested_deviation is not None:
            raise ValueError("MANAGEMENT_VALUES_INVALID")
    else:
        if resulting is None or resulting < 0 or resulting >= current:
            raise ValueError("CLOSE_VOLUME_INVALID")
        if request.requested_deviation is None or not 0 <= request.requested_deviation <= 1000:
            raise ValueError("MANAGEMENT_VALUES_INVALID")


def _validate_target_values(request: ProtectedBridgeManagementRequest, target: Mapping[str, Any]) -> None:
    current = Decimal(request.current_observed_volume)
    if request.management_intent == "MODIFY_POSITION_PROTECTION":
        direction = str(target.get("direction", ""))
        bid = Decimal(str(target.get("bid", "0")))
        ask = Decimal(str(target.get("ask", "0")))
        distance = Decimal(str(target.get("minimum_stop_distance", "0")))
        sl = Decimal(request.requested_stop_loss or "0")
        tp = Decimal(request.requested_take_profit or "0")
        if direction == "BUY":
            invalid = (sl and sl >= bid - distance) or (tp and tp <= bid + distance)
        elif direction == "SELL":
            invalid = (sl and sl <= ask + distance) or (tp and tp >= ask - distance)
        else:
            invalid = True
        if invalid:
            raise ValueError("PROTECTION_VALUES_INVALID")
    if request.management_intent == "CLOSE_POSITION":
        if str(target.get("direction", "")) not in {"BUY", "SELL"}:
            raise ValueError("PROTECTED_BROKER_TARGET_MISMATCH")
        resulting = Decimal(request.requested_resulting_volume or "0")
        close_volume = current - resulting
        step = Decimal(str(target.get("volume_step", "0")))
        minimum = Decimal(str(target.get("volume_min", "0")))
        if close_volume <= 0 or close_volume > current or (minimum and close_volume < minimum):
            raise ValueError("CLOSE_VOLUME_INVALID")
        if step and close_volume % step != 0:
            raise ValueError("CLOSE_VOLUME_INVALID")


def _mutation_hash(values: Mapping[str, Any]) -> str:
    keys = (
        "request_version", "management_intent", "protected_execution_reference",
        "lifecycle_observation_reference", "lifecycle_observation_hash", "source_snapshot_reference",
        "expected_account_context_fingerprint", "protected_broker_reference", "symbol",
        "current_observed_volume", "requested_resulting_volume", "requested_stop_loss",
        "requested_take_profit", "requested_deviation", "lifecycle_state", "lifecycle_observed_at",
        "idempotency_key", "created_at", "expires_at",
    )
    return _sha256(_canonical_json({key: values.get(key) for key in keys}))


def _request_integrity_hash(values: Mapping[str, Any]) -> str:
    return _sha256(_canonical_json({key: value for key, value in values.items() if key != "integrity_hash"}))


def _receipt(
    status: str,
    intent: str,
    idempotency_status: str,
    *,
    management_applied: bool = False,
    reconciliation_required: bool = False,
    order_sent: bool = False,
    ticket_present: bool = False,
    deal_present: bool = False,
    position_present: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "management_intent": intent,
        "idempotency_status": idempotency_status,
        "management_applied": management_applied,
        "reconciliation_required": reconciliation_required,
        "lifecycle_update_required": status in {"ACCEPTED", "UNKNOWN"},
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "order_sent": order_sent,
        "ticket": None,
        "deal": None,
        "position": None,
        "ticket_present": ticket_present,
        "deal_present": deal_present,
        "position_present": position_present,
        "reason": reason,
        "metadata_redacted": True,
    }


def _blocked(reason: str, *, intent: str = "UNKNOWN", idempotency_status: str = "NOT_RESERVED") -> dict[str, Any]:
    return _receipt("BLOCKED", intent, idempotency_status, reason=reason)


def _safe_reason(exc: Exception) -> str:
    reason = str(exc).strip().upper()
    allowed = {
        "MANAGEMENT_DISABLED", "AUTHENTICATION_FAILED", "MANAGEMENT_SCHEMA_INVALID",
        "MANAGEMENT_REQUEST_VERSION_INVALID", "MANAGEMENT_MUTATION_HASH_MISMATCH",
        "MANAGEMENT_CONFIRMATION_INVALID", "MANAGEMENT_INTEGRITY_MISMATCH",
        "LIFECYCLE_OBSERVATION_STALE", "LIFECYCLE_OBSERVATION_INELIGIBLE",
        "LIFECYCLE_OBSERVATION_MISMATCH", "LIFECYCLE_OBSERVATION_NOT_FOUND",
        "LIFECYCLE_JOURNAL_MISSING", "LIFECYCLE_JOURNAL_UNAVAILABLE",
        "LIFECYCLE_JOURNAL_CORRUPT", "MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE",
        "PROTECTED_BROKER_REFERENCE_AMBIGUOUS", "PROTECTED_BROKER_TARGET_NOT_UNIQUE",
        "PROTECTED_BROKER_TARGET_MISMATCH", "EXECUTION_RECORD_NOT_FOUND",
        "EXECUTION_RECORD_NOT_ELIGIBLE", "MANAGEMENT_SOURCE_MISMATCH",
        "ACCOUNT_CONTEXT_CHANGED", "MT5_TRADING_CAPABILITY_UNAVAILABLE",
        "OBSERVED_VOLUME_CHANGED", "POSITION_VOLUME_INCREASE_NOT_ALLOWED",
        "PROTECTION_VALUES_REQUIRED", "PROTECTION_VALUES_INVALID", "CLOSE_VOLUME_INVALID",
        "MANAGEMENT_VALUES_INVALID", "MT5_PACKAGE_UNAVAILABLE", "MT5_CONSTANTS_UNAVAILABLE",
        "MT5_PRICE_UNAVAILABLE", "EXECUTION_JOURNAL_CORRUPT", "EXECUTION_JOURNAL_UNAVAILABLE",
    }
    return reason if reason in allowed else "MANAGEMENT_REQUEST_INVALID"


def _require_constants(module: Any, *names: str) -> None:
    if any(not hasattr(module, name) for name in names):
        raise ValueError("MT5_CONSTANTS_UNAVAILABLE")


def _intent(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text not in MANAGEMENT_INTENTS:
        raise ValueError("MANAGEMENT_INTENT_INVALID")
    return text


def _optional_decimal(value: Any) -> str | None:
    return None if value is None else _decimal_text(value)


def _decimal_text(value: Any, *, positive: bool = False) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("MANAGEMENT_NUMERIC_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("MANAGEMENT_NUMERIC_INVALID") from exc
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        raise ValueError("MANAGEMENT_NUMERIC_INVALID")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _optional_integer(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("MANAGEMENT_INTEGER_INVALID")
    return value


def _hash(value: Any) -> str:
    text = _text(value, "HASH", maximum=64).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("HASH_INVALID")
    return text


def _text(value: Any, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name}_INVALID")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{name}_INVALID")
    return text


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("LIFECYCLE_OBSERVATION_STALE") from exc
    return parsed.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
