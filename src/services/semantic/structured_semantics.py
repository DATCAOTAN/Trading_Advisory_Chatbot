"""Strict, non-authoritative semantic facts extracted from user language."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


SEMANTIC_SCHEMA_VERSION = "structured-semantic/v1"
PRIMARY_INTENTS = frozenset(
    {
        "SOCIAL",
        "SYSTEM",
        "OUT_OF_SCOPE",
        "KNOWLEDGE",
        "MARKET_DATA",
        "ANALYSIS",
        "STRATEGY",
        "TRADE_LIFECYCLE",
        "POSITION_MANAGEMENT",
        "CONVERSATION",
    }
)
ACTION_VALUES = frozenset(
    {"NONE", "ANALYZE", "EXPLAIN", "OPEN_POSITION", "CLOSE_POSITION", "MANAGE_POSITION"}
)
DIRECTION_VALUES = frozenset({"", "BUY", "SELL"})
REQUESTED_MODES = frozenset({"", "advisory_only", "human_confirmed_live", "autonomous_live"})
RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "primary_intent",
        "secondary_intents",
        "action",
        "direction",
        "subtype",
        "domain",
        "symbols",
        "indicators",
        "requested_data",
        "conditions",
        "context_references",
        "requested_mode",
        "explicit_fields",
        "unresolved_fields",
        "negated",
        "hypothetical",
    }
)
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {"execution_authority", "execution_allowed", "executable", "order_send_allowed", "submission_allowed"}
)


class StructuredSemanticValidationError(ValueError):
    """A provider response cannot safely cross the semantic boundary."""


@dataclass(frozen=True)
class SemanticIndicator:
    indicator_id: str
    parameters: tuple[tuple[str, float], ...] = ()
    timeframe: str = ""

    @classmethod
    def from_payload(cls, payload: Any) -> "SemanticIndicator":
        value = _object(payload, "INDICATOR_INVALID")
        _exact_keys(value, {"indicator_id", "parameters", "timeframe"}, "INDICATOR_FIELDS_INVALID")
        return cls(
            indicator_id=_text(value["indicator_id"], "INDICATOR_ID_INVALID"),
            parameters=_numbers(value["parameters"], "INDICATOR_PARAMETERS_INVALID"),
            timeframe=_optional_text(value["timeframe"], "INDICATOR_TIMEFRAME_INVALID"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "parameters": dict(self.parameters),
            "timeframe": self.timeframe,
        }


@dataclass(frozen=True)
class SemanticCondition:
    subject: str
    operator: str
    value: float

    @classmethod
    def from_payload(cls, payload: Any) -> "SemanticCondition":
        item = _object(payload, "CONDITION_INVALID")
        _exact_keys(item, {"subject", "operator", "value"}, "CONDITION_FIELDS_INVALID")
        return cls(
            subject=_text(item["subject"], "CONDITION_SUBJECT_INVALID"),
            operator=_text(item["operator"], "CONDITION_OPERATOR_INVALID"),
            value=_number(item["value"], "CONDITION_VALUE_INVALID"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "operator": self.operator, "value": self.value}


@dataclass(frozen=True)
class StructuredSemanticResult:
    """Meaning only: downstream policy, context, and execution remain authoritative."""

    primary_intent: str
    secondary_intents: tuple[str, ...]
    action: str
    direction: str
    subtype: str
    domain: str
    symbols: tuple[str, ...]
    indicators: tuple[SemanticIndicator, ...]
    requested_data: tuple[str, ...]
    conditions: tuple[SemanticCondition, ...]
    context_references: tuple[str, ...]
    requested_mode: str
    explicit_fields: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    negated: bool
    hypothetical: bool
    schema_version: str = SEMANTIC_SCHEMA_VERSION

    @classmethod
    def from_json(cls, raw: str) -> "StructuredSemanticResult":
        if not isinstance(raw, str):
            raise StructuredSemanticValidationError("SEMANTIC_OUTPUT_NOT_TEXT")
        try:
            payload = json.loads(raw.strip(), parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            raise StructuredSemanticValidationError("SEMANTIC_OUTPUT_INVALID_JSON") from exc
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: Any) -> "StructuredSemanticResult":
        value = _object(payload, "SEMANTIC_OUTPUT_NOT_OBJECT")
        if FORBIDDEN_AUTHORITY_FIELDS & set(value):
            raise StructuredSemanticValidationError("SEMANTIC_OUTPUT_AUTHORITY_FIELD_FORBIDDEN")
        _exact_keys(value, RESULT_FIELDS, "SEMANTIC_OUTPUT_FIELDS_INVALID")
        if value["schema_version"] != SEMANTIC_SCHEMA_VERSION:
            raise StructuredSemanticValidationError("SEMANTIC_SCHEMA_VERSION_INVALID")

        primary_intent = _enum(value["primary_intent"], PRIMARY_INTENTS, "SEMANTIC_PRIMARY_INTENT_INVALID")
        secondary = _enum_list(value["secondary_intents"], PRIMARY_INTENTS, "SEMANTIC_SECONDARY_INTENTS_INVALID")
        action = _enum(value["action"], ACTION_VALUES, "SEMANTIC_ACTION_INVALID")
        direction = _enum(value["direction"], DIRECTION_VALUES, "SEMANTIC_DIRECTION_INVALID")
        requested_mode = _enum(
            value["requested_mode"],
            REQUESTED_MODES,
            "SEMANTIC_REQUESTED_MODE_INVALID",
            normalize_upper=False,
        )

        return cls(
            primary_intent=primary_intent,
            secondary_intents=secondary,
            action=action,
            direction=direction,
            subtype=_optional_text(value["subtype"], "SEMANTIC_SUBTYPE_INVALID"),
            domain=_optional_text(value["domain"], "SEMANTIC_DOMAIN_INVALID"),
            symbols=_text_list(value["symbols"], "SEMANTIC_SYMBOLS_INVALID"),
            indicators=tuple(SemanticIndicator.from_payload(item) for item in _list(value["indicators"], "SEMANTIC_INDICATORS_INVALID")),
            requested_data=_text_list(value["requested_data"], "SEMANTIC_REQUESTED_DATA_INVALID"),
            conditions=tuple(SemanticCondition.from_payload(item) for item in _list(value["conditions"], "SEMANTIC_CONDITIONS_INVALID")),
            context_references=_text_list(value["context_references"], "SEMANTIC_CONTEXT_REFERENCES_INVALID"),
            requested_mode=requested_mode,
            explicit_fields=_text_list(value["explicit_fields"], "SEMANTIC_EXPLICIT_FIELDS_INVALID"),
            unresolved_fields=_text_list(value["unresolved_fields"], "SEMANTIC_UNRESOLVED_FIELDS_INVALID"),
            negated=_bool(value["negated"], "SEMANTIC_NEGATED_INVALID"),
            hypothetical=_bool(value["hypothetical"], "SEMANTIC_HYPOTHETICAL_INVALID"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_intent": self.primary_intent,
            "secondary_intents": list(self.secondary_intents),
            "action": self.action,
            "direction": self.direction,
            "subtype": self.subtype,
            "domain": self.domain,
            "symbols": list(self.symbols),
            "indicators": [item.as_dict() for item in self.indicators],
            "requested_data": list(self.requested_data),
            "conditions": [item.as_dict() for item in self.conditions],
            "context_references": list(self.context_references),
            "requested_mode": self.requested_mode,
            "explicit_fields": list(self.explicit_fields),
            "unresolved_fields": list(self.unresolved_fields),
            "negated": self.negated,
            "hypothetical": self.hypothetical,
        }


def _object(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StructuredSemanticValidationError(code)
    return value


def _exact_keys(payload: Mapping[str, Any], expected: set[str] | frozenset[str], code: str) -> None:
    if set(payload) != set(expected):
        raise StructuredSemanticValidationError(code)


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise StructuredSemanticValidationError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructuredSemanticValidationError(code)
    return value.strip()


def _optional_text(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise StructuredSemanticValidationError(code)
    return value.strip()


def _text_list(value: Any, code: str) -> tuple[str, ...]:
    return tuple(_text(item, code) for item in _list(value, code))


def _enum(value: Any, allowed: frozenset[str], code: str, *, normalize_upper: bool = True) -> str:
    text = _optional_text(value, code)
    if normalize_upper:
        text = text.upper()
    if text not in allowed:
        raise StructuredSemanticValidationError(code)
    return text


def _enum_list(value: Any, allowed: frozenset[str], code: str) -> tuple[str, ...]:
    items = tuple(_enum(item, allowed, code) for item in _list(value, code))
    if len(set(items)) != len(items):
        raise StructuredSemanticValidationError(code)
    return items


def _numbers(value: Any, code: str) -> tuple[tuple[str, float], ...]:
    payload = _object(value, code)
    values = tuple(sorted((_text(key, code), _number(item, code)) for key, item in payload.items()))
    if len({key for key, _ in values}) != len(values):
        raise StructuredSemanticValidationError(code)
    return values


def _number(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise StructuredSemanticValidationError(code)
    return float(value)


def _bool(value: Any, code: str) -> bool:
    if not isinstance(value, bool):
        raise StructuredSemanticValidationError(code)
    return value


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-finite JSON values are invalid")
