from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleObservation,
    MT5LifecycleState,
)


MANAGEMENT_REQUEST_VERSION = "controlled-mt5-management/v1"
MANDATE_MANAGEMENT_REQUEST_VERSION = "controlled-mt5-management/v2"


class MT5ManagementIntent(str, Enum):
    CANCEL_PENDING_ORDER = "CANCEL_PENDING_ORDER"
    MODIFY_POSITION_PROTECTION = "MODIFY_POSITION_PROTECTION"
    CLOSE_POSITION = "CLOSE_POSITION"


MANAGEMENT_CONFIRMATION_PHRASES = {
    MT5ManagementIntent.CANCEL_PENDING_ORDER.value: "CANCEL ONE CONTROLLED MT5 PENDING ORDER",
    MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value: "MODIFY PROTECTION FOR ONE CONTROLLED MT5 POSITION",
    MT5ManagementIntent.CLOSE_POSITION.value: "CLOSE ONE CONTROLLED MT5 POSITION",
}


@dataclass(frozen=True)
class MT5ManagementProposal:
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
    lifecycle_state: str = MT5LifecycleState.UNKNOWN.value
    lifecycle_observed_at: str = ""
    mutation_hash: str = ""
    idempotency_key: str = field(default="", repr=False)
    created_at: str = ""
    expires_at: str = ""

    @classmethod
    def from_lifecycle_observation(
        cls,
        observation: MT5LifecycleObservation | Mapping[str, Any],
        *,
        management_intent: str,
        expected_account_context_fingerprint: str,
        symbol: str,
        current_observed_volume: Any,
        idempotency_key: str,
        requested_resulting_volume: Any | None = None,
        requested_stop_loss: Any | None = None,
        requested_take_profit: Any | None = None,
        requested_deviation: int | None = None,
        ttl_seconds: int = 300,
        current_time: datetime | None = None,
    ) -> "MT5ManagementProposal":
        row = observation.to_protected_dict() if isinstance(observation, MT5LifecycleObservation) else dict(observation)
        _validate_observation_integrity(row)
        expected_fingerprint = _hash(expected_account_context_fingerprint)
        if not hmac.compare_digest(
            str(row.get("account_fingerprint_hash", "")), _sha256(expected_fingerprint)
        ):
            raise ValueError("ACCOUNT_CONTEXT_CHANGED")
        intent = _intent(management_intent)
        now = _utc(current_time)
        values = {
            "request_version": MANAGEMENT_REQUEST_VERSION,
            "management_intent": intent,
            "protected_execution_reference": _text(row.get("protected_execution_reference"), "PROTECTED_EXECUTION_REFERENCE"),
            "lifecycle_observation_reference": _text(row.get("observation_id"), "LIFECYCLE_OBSERVATION_REFERENCE"),
            "lifecycle_observation_hash": _hash(row.get("observation_hash")),
            "source_snapshot_reference": _text(row.get("source_snapshot_reference"), "SOURCE_SNAPSHOT_REFERENCE"),
            "expected_account_context_fingerprint": expected_fingerprint,
            "protected_broker_reference": _selected_broker_reference(row, intent),
            "symbol": _text(symbol, "SYMBOL", maximum=64),
            "current_observed_volume": _decimal_text(current_observed_volume, positive=True),
            "requested_resulting_volume": _optional_decimal_text(requested_resulting_volume),
            "requested_stop_loss": _optional_decimal_text(requested_stop_loss),
            "requested_take_profit": _optional_decimal_text(requested_take_profit),
            "requested_deviation": _optional_integer(requested_deviation),
            "lifecycle_state": _text(row.get("lifecycle_state"), "LIFECYCLE_STATE"),
            "lifecycle_observed_at": _timestamp(row.get("observation_timestamp"), "LIFECYCLE_OBSERVED_AT"),
            "idempotency_key": _text(idempotency_key, "IDEMPOTENCY_KEY"),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat(),
        }
        _validate_proposal_values(values, now=now)
        values["mutation_hash"] = _mutation_hash(values)
        return cls(**values)

    def as_protected_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_redacted_dict(self) -> dict[str, Any]:
        return _redacted(self.as_protected_dict())


@dataclass(frozen=True)
class MT5ControlledManagementRequest:
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
    lifecycle_state: str = MT5LifecycleState.UNKNOWN.value
    lifecycle_observed_at: str = ""
    mutation_hash: str = ""
    idempotency_key: str = field(default="", repr=False)
    created_at: str = ""
    expires_at: str = ""
    human_confirmation_reference: str = ""
    human_confirmation_phrase: str = field(default="", repr=False)
    human_confirmation_timestamp: str = ""
    authorization_source: str = "HUMAN_CONFIRMATION"
    mandate_authorization_reference: str = ""
    mandate_authorization_hash: str = ""
    semantic_management_intent: str = ""
    strategy_reference: str = ""
    evaluation_reference: str = ""
    policy_reference: str = ""
    integrity_hash: str = ""

    @classmethod
    def confirm(
        cls,
        proposal: MT5ManagementProposal,
        *,
        typed_confirmation: str,
        current_time: datetime | None = None,
    ) -> "MT5ControlledManagementRequest":
        now = _utc(current_time)
        values = proposal.as_protected_dict()
        _validate_proposal_values(values, now=now)
        if not hmac.compare_digest(proposal.mutation_hash, _mutation_hash(values)):
            raise ValueError("MANAGEMENT_MUTATION_HASH_MISMATCH")
        phrase = str(typed_confirmation or "").strip()
        if not hmac.compare_digest(phrase, management_confirmation_phrase(proposal.management_intent)):
            raise ValueError("MANAGEMENT_CONFIRMATION_INVALID")
        confirmation_timestamp = now.isoformat()
        values.update(
            human_confirmation_reference=_confirmation_reference(
                phrase,
                proposal.management_intent,
                proposal.protected_broker_reference,
                proposal.expected_account_context_fingerprint,
                proposal.lifecycle_observation_reference,
                proposal.mutation_hash,
                confirmation_timestamp,
            ),
            human_confirmation_phrase=phrase,
            human_confirmation_timestamp=confirmation_timestamp,
        )
        values["integrity_hash"] = _request_integrity_hash(values)
        return cls(**values)

    @classmethod
    def from_mandate_authorization(
        cls,
        proposal: MT5ManagementProposal,
        authorization: Any,
        *,
        current_time: datetime | None = None,
    ) -> "MT5ControlledManagementRequest":
        now = _utc(current_time)
        values = proposal.as_protected_dict()
        _validate_proposal_values(values, now=now)
        if not hmac.compare_digest(proposal.mutation_hash, _mutation_hash(values)):
            raise ValueError("MANAGEMENT_MUTATION_HASH_MISMATCH")
        expected = (
            authorization.authorization_source,
            authorization.management_mutation_hash,
            authorization.protected_execution_reference,
            authorization.lifecycle_observation_reference,
            authorization.lifecycle_observation_hash,
            authorization.backend_management_intent,
        )
        actual = (
            "STANDING_MANDATE",
            proposal.mutation_hash,
            proposal.protected_execution_reference,
            proposal.lifecycle_observation_reference,
            proposal.lifecycle_observation_hash,
            proposal.management_intent,
        )
        if (
            not authorization.integrity_valid()
            or not hmac.compare_digest(_sha256(_canonical_json(expected)), _sha256(_canonical_json(actual)))
        ):
            raise ValueError("MANDATE_MANAGEMENT_BINDING_MISMATCH")
        values.update(
            request_version=MANDATE_MANAGEMENT_REQUEST_VERSION,
            human_confirmation_reference="",
            human_confirmation_phrase="",
            human_confirmation_timestamp="",
            authorization_source="STANDING_MANDATE",
            mandate_authorization_reference=authorization.authorization_id,
            mandate_authorization_hash=authorization.artifact_hash,
            semantic_management_intent=authorization.management_intent,
            strategy_reference=authorization.strategy_reference,
            evaluation_reference=authorization.evaluation_reference,
            policy_reference=authorization.policy_reference,
        )
        values["integrity_hash"] = _request_integrity_hash(values)
        return cls(**values)

    def validate(self, current_time: datetime | None = None) -> None:
        values = self.as_protected_dict()
        proposal_values = dict(values)
        proposal_values["request_version"] = MANAGEMENT_REQUEST_VERSION
        _validate_proposal_values(proposal_values, now=_utc(current_time))
        if not hmac.compare_digest(self.mutation_hash, _mutation_hash(values)):
            raise ValueError("MANAGEMENT_MUTATION_HASH_MISMATCH")
        created = _parse_timestamp(self.created_at, "MANAGEMENT_CREATED_AT")
        expires = _parse_timestamp(self.expires_at, "MANAGEMENT_EXPIRES_AT")
        now = _utc(current_time)
        maximum_age = max(1.0, (expires - created).total_seconds())
        if self.authorization_source == "HUMAN_CONFIRMATION":
            if self.request_version != MANAGEMENT_REQUEST_VERSION:
                raise ValueError("MANAGEMENT_REQUEST_VERSION_INVALID")
            if not hmac.compare_digest(self.human_confirmation_phrase, management_confirmation_phrase(self.management_intent)):
                raise ValueError("MANAGEMENT_CONFIRMATION_INVALID")
            expected = _confirmation_reference(
                self.human_confirmation_phrase,
                self.management_intent,
                self.protected_broker_reference,
                self.expected_account_context_fingerprint,
                self.lifecycle_observation_reference,
                self.mutation_hash,
                self.human_confirmation_timestamp,
            )
            if not hmac.compare_digest(self.human_confirmation_reference, expected):
                raise ValueError("MANAGEMENT_CONFIRMATION_INVALID")
            confirmed = _parse_timestamp(self.human_confirmation_timestamp, "CONFIRMATION_TIMESTAMP")
            if confirmed < created - timedelta(seconds=1) or (now - confirmed).total_seconds() > maximum_age:
                raise ValueError("MANAGEMENT_CONFIRMATION_EXPIRED")
        elif self.authorization_source == "STANDING_MANDATE":
            if self.request_version != MANDATE_MANAGEMENT_REQUEST_VERSION:
                raise ValueError("MANAGEMENT_REQUEST_VERSION_INVALID")
            for name in (
                "mandate_authorization_reference",
                "semantic_management_intent",
                "strategy_reference",
                "evaluation_reference",
                "policy_reference",
            ):
                _text(getattr(self, name), name.upper())
            _hash(self.mandate_authorization_hash)
            if any((self.human_confirmation_reference, self.human_confirmation_phrase, self.human_confirmation_timestamp)):
                raise ValueError("MANAGEMENT_AUTHORIZATION_SOURCE_INVALID")
        else:
            raise ValueError("MANAGEMENT_AUTHORIZATION_SOURCE_INVALID")
        if not hmac.compare_digest(self.integrity_hash, _request_integrity_hash(values)):
            raise ValueError("MANAGEMENT_INTEGRITY_MISMATCH")

    def as_protected_dict(self) -> dict[str, Any]:
        values = asdict(self)
        if self.request_version == MANAGEMENT_REQUEST_VERSION:
            for name in (
                "authorization_source",
                "mandate_authorization_reference",
                "mandate_authorization_hash",
                "semantic_management_intent",
                "strategy_reference",
                "evaluation_reference",
                "policy_reference",
            ):
                values.pop(name)
        return values

    def as_redacted_dict(self) -> dict[str, Any]:
        return _redacted(self.as_protected_dict())


@dataclass(frozen=True)
class MT5ControlledManagementReceipt:
    status: str
    management_intent: str
    idempotency_status: str
    management_applied: bool
    reconciliation_required: bool
    lifecycle_update_required: bool
    order_sent: bool
    ticket_present: bool
    deal_present: bool
    position_present: bool
    reason: str = ""
    ticket: Any = None
    deal: Any = None
    position: Any = None
    metadata_redacted: bool = True

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MT5ControlledManagementReceipt":
        return cls(
            status=str(payload.get("status", "BLOCKED")),
            management_intent=str(payload.get("management_intent", "UNKNOWN")),
            idempotency_status=str(payload.get("idempotency_status", "NOT_RESERVED")),
            management_applied=payload.get("management_applied") is True,
            reconciliation_required=payload.get("reconciliation_required") is True,
            lifecycle_update_required=payload.get("lifecycle_update_required") is True,
            order_sent=payload.get("order_sent") is True,
            ticket_present=payload.get("ticket_present") is True,
            deal_present=payload.get("deal_present") is True,
            position_present=payload.get("position_present") is True,
            reason=str(payload.get("reason", "")),
            ticket=None,
            deal=None,
            position=None,
            metadata_redacted=True,
        )


def management_confirmation_phrase(management_intent: str) -> str:
    return MANAGEMENT_CONFIRMATION_PHRASES[_intent(management_intent)]


def _validate_proposal_values(values: Mapping[str, Any], *, now: datetime) -> None:
    if values.get("request_version") != MANAGEMENT_REQUEST_VERSION:
        raise ValueError("MANAGEMENT_REQUEST_VERSION_INVALID")
    intent = _intent(values.get("management_intent"))
    state = _text(values.get("lifecycle_state"), "LIFECYCLE_STATE")
    allowed = {
        MT5ManagementIntent.CANCEL_PENDING_ORDER.value: {MT5LifecycleState.ORDER_ACTIVE.value},
        MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value: {
            MT5LifecycleState.POSITION_OPEN.value,
            MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
        },
        MT5ManagementIntent.CLOSE_POSITION.value: {
            MT5LifecycleState.POSITION_OPEN.value,
            MT5LifecycleState.POSITION_PARTIALLY_REDUCED.value,
        },
    }
    if state not in allowed[intent]:
        raise ValueError("MANAGEMENT_LIFECYCLE_NOT_ELIGIBLE")
    for name in ("protected_execution_reference", "lifecycle_observation_reference", "source_snapshot_reference", "symbol", "idempotency_key"):
        _text(values.get(name), name.upper())
    for name in ("lifecycle_observation_hash", "expected_account_context_fingerprint", "protected_broker_reference"):
        _hash(values.get(name))
    current = Decimal(_decimal_text(values.get("current_observed_volume"), positive=True))
    resulting_text = _optional_decimal_text(values.get("requested_resulting_volume"))
    stop_loss = _optional_decimal_text(values.get("requested_stop_loss"))
    take_profit = _optional_decimal_text(values.get("requested_take_profit"))
    deviation = _optional_integer(values.get("requested_deviation"))
    if intent == MT5ManagementIntent.CANCEL_PENDING_ORDER.value:
        if resulting_text not in {None, "0"} or any(value is not None for value in (stop_loss, take_profit, deviation)):
            raise ValueError("MANAGEMENT_VALUES_INVALID")
    elif intent == MT5ManagementIntent.MODIFY_POSITION_PROTECTION.value:
        if resulting_text is None or Decimal(resulting_text) != current:
            raise ValueError("POSITION_VOLUME_INCREASE_NOT_ALLOWED")
        if stop_loss is None and take_profit is None:
            raise ValueError("PROTECTION_VALUES_REQUIRED")
        if deviation is not None:
            raise ValueError("MANAGEMENT_VALUES_INVALID")
    else:
        if resulting_text is None:
            raise ValueError("CLOSE_VOLUME_INVALID")
        resulting = Decimal(resulting_text)
        if resulting < 0 or resulting >= current or current - resulting <= 0:
            raise ValueError("CLOSE_VOLUME_INVALID")
        if stop_loss is not None or take_profit is not None or deviation is None or deviation < 0 or deviation > 1000:
            raise ValueError("MANAGEMENT_VALUES_INVALID")
    observed = _parse_timestamp(values.get("lifecycle_observed_at"), "LIFECYCLE_OBSERVED_AT")
    expires = _parse_timestamp(values.get("expires_at"), "MANAGEMENT_EXPIRES_AT")
    created = _parse_timestamp(values.get("created_at"), "MANAGEMENT_CREATED_AT")
    age = (now - observed).total_seconds()
    maximum_age = max(1.0, (expires - created).total_seconds())
    if age < -30 or age > maximum_age or now > expires or created > now + timedelta(seconds=30):
        raise ValueError("LIFECYCLE_OBSERVATION_STALE")


def _validate_observation_integrity(row: Mapping[str, Any]) -> None:
    if row.get("record_type") != "LIFECYCLE_OBSERVATION" or row.get("metadata_redacted") is not True:
        raise ValueError("LIFECYCLE_OBSERVATION_INVALID")
    if row.get("discrepancy_reason"):
        raise ValueError("LIFECYCLE_OBSERVATION_INELIGIBLE")
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
    if not hmac.compare_digest(str(row.get("observation_hash", "")), _sha256(_canonical_json(stable))):
        raise ValueError("LIFECYCLE_OBSERVATION_INVALID")


def _selected_broker_reference(row: Mapping[str, Any], intent: str) -> str:
    references = row.get("protected_broker_references")
    if not isinstance(references, Mapping):
        raise ValueError("PROTECTED_BROKER_REFERENCE_INVALID")
    key = "orders" if intent == MT5ManagementIntent.CANCEL_PENDING_ORDER.value else "positions"
    selected = references.get(key)
    if not isinstance(selected, list) or len(selected) != 1:
        raise ValueError("PROTECTED_BROKER_REFERENCE_AMBIGUOUS")
    return _hash(selected[0])


def _redacted(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "request_version": values.get("request_version"),
        "management_intent": values.get("management_intent"),
        "protected_execution_reference": values.get("protected_execution_reference"),
        "lifecycle_observation_reference": values.get("lifecycle_observation_reference"),
        "source_snapshot_reference": values.get("source_snapshot_reference"),
        "symbol": values.get("symbol"),
        "lifecycle_state": values.get("lifecycle_state"),
        "mutation_hash": values.get("mutation_hash"),
        "integrity_hash": values.get("integrity_hash"),
        "human_confirmation_reference": values.get("human_confirmation_reference"),
        "authorization_source": values.get("authorization_source", "HUMAN_CONFIRMATION"),
        "mandate_authorization_reference": values.get("mandate_authorization_reference"),
        "semantic_management_intent": values.get("semantic_management_intent"),
        "strategy_reference": values.get("strategy_reference"),
        "evaluation_reference": values.get("evaluation_reference"),
        "policy_reference": values.get("policy_reference"),
        "expected_account_fingerprint_prefix": str(values.get("expected_account_context_fingerprint", ""))[:12],
        "broker_reference_redacted": True,
        "management_values_redacted": True,
        "metadata_redacted": True,
    }


def _mutation_hash(values: Mapping[str, Any]) -> str:
    keys = (
        "request_version", "management_intent", "protected_execution_reference",
        "lifecycle_observation_reference", "lifecycle_observation_hash", "source_snapshot_reference",
        "expected_account_context_fingerprint", "protected_broker_reference", "symbol",
        "current_observed_volume", "requested_resulting_volume", "requested_stop_loss",
        "requested_take_profit", "requested_deviation", "lifecycle_state", "lifecycle_observed_at",
        "idempotency_key", "created_at", "expires_at",
    )
    material = {key: values.get(key) for key in keys}
    if material["request_version"] == MANDATE_MANAGEMENT_REQUEST_VERSION:
        material["request_version"] = MANAGEMENT_REQUEST_VERSION
    return _sha256(_canonical_json(material))


def _request_integrity_hash(values: Mapping[str, Any]) -> str:
    return _sha256(_canonical_json({key: value for key, value in values.items() if key != "integrity_hash"}))


def _confirmation_reference(phrase: str, intent: str, broker_reference: str, account_fingerprint: str, observation_reference: str, mutation_hash: str, timestamp: str) -> str:
    return _sha256("|".join((phrase, intent, broker_reference, account_fingerprint, observation_reference, mutation_hash, timestamp)))


def _intent(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text not in MANAGEMENT_CONFIRMATION_PHRASES:
        raise ValueError("MANAGEMENT_INTENT_INVALID")
    return text


def _optional_decimal_text(value: Any) -> str | None:
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


def _timestamp(value: Any, name: str) -> str:
    return _parse_timestamp(value, name).isoformat()


def _parse_timestamp(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"{name}_INVALID") from exc
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("CURRENT_TIME_INVALID")
    return now.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
