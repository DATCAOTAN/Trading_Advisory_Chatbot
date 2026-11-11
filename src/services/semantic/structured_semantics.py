"""Strict, non-authoritative semantic facts extracted from user language."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError


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
        "STRATEGY_RESEARCH",
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
ACCOUNT_SCOPES = frozenset({"", "DEMO", "REAL"})
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
        "account_scope",
        "explicit_fields",
        "unresolved_fields",
        "negated",
        "hypothetical",
        "research_goal",
        "trade_parameters",
        "computational_specification",
    }
)
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {"execution_authority", "execution_allowed", "executable", "order_send_allowed", "submission_allowed"}
)


class StructuredSemanticValidationError(ValueError):
    """A provider response cannot safely cross the semantic boundary."""


def _invalid(code: str) -> None:
    raise PydanticCustomError(code.lower(), code)


def _required_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(code)
    return value.strip()


def _optional_text(value: Any, code: str) -> str:
    if not isinstance(value, str):
        _invalid(code)
    return value.strip()


def _enum_value(value: Any, allowed: frozenset[str], code: str, *, normalize_upper: bool = True) -> str:
    text = _optional_text(value, code)
    if normalize_upper:
        text = text.upper()
    if text not in allowed:
        _invalid(code)
    return text


def _text_list(value: Any, code: str) -> list[str]:
    if not isinstance(value, list):
        _invalid(code)
    return [_required_text(item, code) for item in value]


def _enum_list(value: Any, allowed: frozenset[str], code: str) -> list[str]:
    items = _text_list(value, code)
    normalized = [_enum_value(item, allowed, code) for item in items]
    if len(set(normalized)) != len(normalized):
        _invalid(code)
    return normalized


def _finite_number(value: int | float) -> int | float:
    if not math.isfinite(float(value)):
        raise ValueError("non-finite numeric values are invalid")
    return value


StrictFiniteNumber = Annotated[StrictInt | StrictFloat, AfterValidator(_finite_number)]


class _StrictSemanticPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResearchGoal(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    objective: str = Field(default="", max_length=300)
    horizon: str = Field(default="", max_length=80)
    max_risk_per_trade_pct: StrictFiniteNumber | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: StrictFiniteNumber | None = Field(default=None, ge=0, le=100)


class TradeParameter(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True)

    value: Annotated[str, Field(max_length=64)] | StrictFiniteNumber | None = None
    unit: str = Field(default="", max_length=32)


class TradeParameters(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True)

    stop_loss: TradeParameter | None = None
    take_profit: TradeParameter | None = None
    risk: TradeParameter | None = None
    volume: TradeParameter | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def owns_path(cls, path: str) -> bool:
        parts = path.split(".", 2)
        return len(parts) >= 2 and parts[0] == "trade_parameters" and parts[1] in cls.model_fields


COMPUTATIONAL_SPEC_VERSION = "computational-specification/v1"
COMPUTATIONAL_SPEC_FIELD = "computational_specification"
COMPUTATIONAL_SPEC_REFERENCE = "previous_computational_specification"
AUTHORIZATION_MODE_MAP = {
    "ADVISORY": "advisory_only",
    "HUMAN_CONFIRMED": "human_confirmed_live",
    "AUTONOMOUS": "autonomous_live",
}
SpecText = Annotated[str, Field(min_length=1, max_length=1200)]
SpecLabel = Annotated[str, Field(min_length=1, max_length=100)]
SpecValue = StrictFiniteNumber | SpecText | StrictBool


class SpecificationConfiguration(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True)

    strategy_origin: Literal["USER_DEFINED", "AI_RESEARCHED"] | None = None
    authorization_mode: Literal["ADVISORY", "HUMAN_CONFIRMED", "AUTONOMOUS"] | None = None
    adaptation_policy: Literal["FIXED", "ADAPTIVE_WITHIN_SCOPE", "RESEARCH_AND_REQUEST_APPROVAL"] | None = None


class ComputationalParameter(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: SpecLabel | None = None
    definition: SpecText | None = None
    value: SpecValue | None = None
    minimum: StrictFiniteNumber | None = None
    maximum: StrictFiniteNumber | None = None
    unit: SpecLabel | None = None


class ComputationalDataRequirement(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    dataset: SpecLabel | None = None
    fields: tuple[SpecLabel, ...] = Field(default=(), strict=False, max_length=16)
    symbol: SpecLabel | None = None
    timeframe: SpecLabel | None = None
    lookback_bars: int | None = Field(default=None, gt=0)
    warmup_bars: int | None = Field(default=None, ge=0)
    max_age_seconds: int | None = Field(default=None, gt=0)
    completeness: SpecText | None = None
    usage: Literal["RESEARCH_ONLY", "EXECUTION_RELEVANT"] | None = None


class ComputationalDataAssessment(_StrictSemanticPayload):
    """Evidence status, separate from the requirements extracted by the model."""

    model_config = ConfigDict(frozen=True)

    availability: Literal["NOT_CHECKED", "AVAILABLE", "UNAVAILABLE", "INSUFFICIENT_COVERAGE"] = "NOT_CHECKED"
    freshness: Literal["NOT_CHECKED", "FRESH", "STALE"] = "NOT_CHECKED"
    completeness: Literal["NOT_CHECKED", "COMPLETE", "INCOMPLETE"] = "NOT_CHECKED"


class ComputationalOutput(_StrictSemanticPayload):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: SpecLabel | None = None
    unit: SpecLabel | None = None
    validity: SpecText | None = None


class ComputationalSpecification(_StrictSemanticPayload):
    """Versioned description of a computation; expressions are inert text."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["computational-specification/v1"] = COMPUTATIONAL_SPEC_VERSION
    objective: SpecText | None = None
    algorithm: SpecLabel | None = None
    formula: SpecText | None = None
    steps: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    temporal_requirements: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    parameters: tuple[ComputationalParameter, ...] = Field(default=(), strict=False, max_length=12)
    data_requirements: tuple[ComputationalDataRequirement, ...] = Field(default=(), strict=False, max_length=12)
    outputs: tuple[ComputationalOutput, ...] = Field(default=(), strict=False, max_length=12)
    entry: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    exit: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    reentry: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    management: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    configuration: SpecificationConfiguration | None = None
    conflicts: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)
    unsupported: tuple[SpecText, ...] = Field(default=(), strict=False, max_length=12)

    @classmethod
    def from_completion_fields(cls, fields: dict[str, Any]) -> ComputationalSpecification:
        try:
            return cls.model_validate(fields)
        except ValidationError as exc:
            raise ValueError(exc.errors(include_input=False)[0]["msg"]) from None

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, **self.model_dump(mode="json", exclude_defaults=True)}

    @property
    def specification_id(self) -> str:
        canonical = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return "computational_spec_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _PydanticSemanticIndicatorPayload(_StrictSemanticPayload):
    indicator_id: str
    parameters: dict[str, StrictFiniteNumber] = Field(default_factory=dict)
    timeframe: str = ""

    @field_validator("indicator_id", mode="before")
    @classmethod
    def _validate_indicator_id(cls, value: Any) -> str:
        return _required_text(value, "INDICATOR_ID_INVALID")

    @field_validator("parameters", mode="after")
    @classmethod
    def _validate_parameters(cls, value: dict[str, int | float]) -> dict[str, float]:
        normalized = {
            _required_text(key, "INDICATOR_PARAMETERS_INVALID"): float(number)
            for key, number in value.items()
        }
        if len(normalized) != len(value):
            _invalid("INDICATOR_PARAMETERS_INVALID")
        return normalized

    @field_validator("timeframe", mode="before")
    @classmethod
    def _validate_timeframe(cls, value: Any) -> str:
        return _optional_text(value, "INDICATOR_TIMEFRAME_INVALID")

    def to_internal(self) -> "SemanticIndicator":
        return SemanticIndicator(
            indicator_id=self.indicator_id,
            parameters=tuple(sorted(self.parameters.items())),
            timeframe=self.timeframe,
        )


class _PydanticSemanticConditionPayload(_StrictSemanticPayload):
    subject: str
    operator: str
    value: StrictFiniteNumber

    @field_validator("subject", mode="before")
    @classmethod
    def _validate_subject(cls, value: Any) -> str:
        return _required_text(value, "CONDITION_SUBJECT_INVALID")

    @field_validator("operator", mode="before")
    @classmethod
    def _validate_operator(cls, value: Any) -> str:
        return _required_text(value, "CONDITION_OPERATOR_INVALID")

    def to_internal(self) -> "SemanticCondition":
        return SemanticCondition(subject=self.subject, operator=self.operator, value=float(self.value))


_TEXT_LIST_ERROR_CODES = {
    "symbols": "SEMANTIC_SYMBOLS_INVALID",
    "requested_data": "SEMANTIC_REQUESTED_DATA_INVALID",
    "context_references": "SEMANTIC_CONTEXT_REFERENCES_INVALID",
    "explicit_fields": "SEMANTIC_EXPLICIT_FIELDS_INVALID",
    "unresolved_fields": "SEMANTIC_UNRESOLVED_FIELDS_INVALID",
}


class _PydanticStructuredSemanticPayload(_StrictSemanticPayload):
    schema_version: str
    primary_intent: str
    secondary_intents: list[str]
    action: str
    direction: str
    subtype: str
    domain: str
    symbols: list[str]
    indicators: list[_PydanticSemanticIndicatorPayload]
    requested_data: list[str]
    conditions: list[_PydanticSemanticConditionPayload]
    context_references: list[str]
    requested_mode: str
    account_scope: str
    explicit_fields: list[str]
    unresolved_fields: list[str]
    negated: StrictBool
    hypothetical: StrictBool
    research_goal: ResearchGoal | None = None
    trade_parameters: TradeParameters | None = None
    computational_specification: ComputationalSpecification | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _validate_schema_version(cls, value: Any) -> str:
        if value != SEMANTIC_SCHEMA_VERSION:
            _invalid("SEMANTIC_SCHEMA_VERSION_INVALID")
        return value

    @field_validator("primary_intent", mode="before")
    @classmethod
    def _validate_primary_intent(cls, value: Any) -> str:
        return _enum_value(value, PRIMARY_INTENTS, "SEMANTIC_PRIMARY_INTENT_INVALID")

    @field_validator("secondary_intents", mode="before")
    @classmethod
    def _validate_secondary_intents(cls, value: Any) -> list[str]:
        return _enum_list(value, PRIMARY_INTENTS, "SEMANTIC_SECONDARY_INTENTS_INVALID")

    @field_validator("action", mode="before")
    @classmethod
    def _validate_action(cls, value: Any) -> str:
        return _enum_value(value, ACTION_VALUES, "SEMANTIC_ACTION_INVALID")

    @field_validator("direction", mode="before")
    @classmethod
    def _validate_direction(cls, value: Any) -> str:
        return _enum_value(value, DIRECTION_VALUES, "SEMANTIC_DIRECTION_INVALID")

    @field_validator("subtype", mode="before")
    @classmethod
    def _validate_subtype(cls, value: Any) -> str:
        return _optional_text(value, "SEMANTIC_SUBTYPE_INVALID")

    @field_validator("domain", mode="before")
    @classmethod
    def _validate_domain(cls, value: Any) -> str:
        return _optional_text(value, "SEMANTIC_DOMAIN_INVALID")

    @field_validator(*_TEXT_LIST_ERROR_CODES, mode="before")
    @classmethod
    def _validate_text_lists(cls, value: Any, info: ValidationInfo) -> list[str]:
        return _text_list(value, _TEXT_LIST_ERROR_CODES[info.field_name])

    @field_validator("indicators", mode="before")
    @classmethod
    def _validate_indicators_shape(cls, value: Any) -> list[Any]:
        if not isinstance(value, list):
            _invalid("SEMANTIC_INDICATORS_INVALID")
        return value

    @field_validator("conditions", mode="before")
    @classmethod
    def _validate_conditions_shape(cls, value: Any) -> list[Any]:
        if not isinstance(value, list):
            _invalid("SEMANTIC_CONDITIONS_INVALID")
        return value

    @field_validator("requested_mode", mode="before")
    @classmethod
    def _validate_requested_mode(cls, value: Any) -> str:
        return _enum_value(value, REQUESTED_MODES, "SEMANTIC_REQUESTED_MODE_INVALID", normalize_upper=False)

    @field_validator("account_scope", mode="before")
    @classmethod
    def _validate_account_scope(cls, value: Any) -> str:
        return _enum_value(value, ACCOUNT_SCOPES, "SEMANTIC_ACCOUNT_SCOPE_INVALID")

    @field_validator("negated", mode="before")
    @classmethod
    def _validate_negated(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            _invalid("SEMANTIC_NEGATED_INVALID")
        return value

    @field_validator("hypothetical", mode="before")
    @classmethod
    def _validate_hypothetical(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            _invalid("SEMANTIC_HYPOTHETICAL_INVALID")
        return value

    def to_internal(self) -> "StructuredSemanticResult":
        return StructuredSemanticResult(
            schema_version=self.schema_version,
            primary_intent=self.primary_intent,
            secondary_intents=tuple(self.secondary_intents),
            action=self.action,
            direction=self.direction,
            subtype=self.subtype,
            domain=self.domain,
            symbols=tuple(self.symbols),
            indicators=tuple(item.to_internal() for item in self.indicators),
            requested_data=tuple(self.requested_data),
            conditions=tuple(item.to_internal() for item in self.conditions),
            context_references=tuple(self.context_references),
            requested_mode=self.requested_mode,
            account_scope=self.account_scope,
            explicit_fields=tuple(self.explicit_fields),
            unresolved_fields=tuple(self.unresolved_fields),
            negated=self.negated,
            hypothetical=self.hypothetical,
            research_goal=self.research_goal,
            trade_parameters=self.trade_parameters,
            computational_specification=self.computational_specification,
        )


@dataclass(frozen=True)
class SemanticIndicator:
    indicator_id: str
    parameters: tuple[tuple[str, float], ...] = ()
    timeframe: str = ""

    @classmethod
    def from_payload(cls, payload: Any) -> "SemanticIndicator":
        return _validate_payload(_PydanticSemanticIndicatorPayload, payload, "INDICATOR_INVALID").to_internal()

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
        return _validate_payload(_PydanticSemanticConditionPayload, payload, "CONDITION_INVALID").to_internal()

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
    account_scope: str
    explicit_fields: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    negated: bool
    hypothetical: bool
    schema_version: str = SEMANTIC_SCHEMA_VERSION
    research_goal: ResearchGoal | None = None
    trade_parameters: TradeParameters | None = None
    computational_specification: ComputationalSpecification | None = None

    @property
    def has_computational_request(self) -> bool:
        return self.computational_specification is not None or COMPUTATIONAL_SPEC_REFERENCE in self.context_references

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
        if not isinstance(payload, dict):
            raise StructuredSemanticValidationError("SEMANTIC_OUTPUT_NOT_OBJECT")
        if FORBIDDEN_AUTHORITY_FIELDS & set(payload):
            raise StructuredSemanticValidationError("SEMANTIC_OUTPUT_AUTHORITY_FIELD_FORBIDDEN")
        return _validate_payload(
            _PydanticStructuredSemanticPayload,
            _normalize_declared_missing_indicator_children(payload),
            "SEMANTIC_OUTPUT_NOT_OBJECT",
        ).to_internal()

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
            "account_scope": self.account_scope,
            "explicit_fields": list(self.explicit_fields),
            "unresolved_fields": list(self.unresolved_fields),
            "negated": self.negated,
            "hypothetical": self.hypothetical,
            **({"research_goal": self.research_goal.model_dump(exclude_none=True)}
               if self.research_goal is not None else {}),
            **({"trade_parameters": self.trade_parameters.as_dict()} if self.trade_parameters is not None else {}),
            **({COMPUTATIONAL_SPEC_FIELD: self.computational_specification.as_dict()}
               if self.computational_specification is not None else {}),
        }


def _validate_payload(model: type[_StrictSemanticPayload], payload: Any, object_code: str) -> Any:
    if not isinstance(payload, dict):
        raise StructuredSemanticValidationError(object_code)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise StructuredSemanticValidationError(_validation_error_code(exc)) from exc


def _validation_error_code(exc: ValidationError) -> str:
    error = exc.errors()[0]
    message = str(error.get("msg") or "")
    if message.endswith(("_INVALID", "_FORBIDDEN")):
        return message

    location = tuple(error.get("loc") or ())
    root = str(location[0]) if location else ""
    if root == COMPUTATIONAL_SPEC_FIELD:
        return "COMPUTATIONAL_SPECIFICATION_INVALID"
    if error.get("type") in {"missing", "extra_forbidden"}:
        if root == "indicators":
            return "INDICATOR_FIELDS_INVALID" if len(location) > 1 else "SEMANTIC_INDICATORS_INVALID"
        if root == "conditions":
            return "CONDITION_FIELDS_INVALID" if len(location) > 1 else "SEMANTIC_CONDITIONS_INVALID"
        return "SEMANTIC_OUTPUT_FIELDS_INVALID"
    if root == "indicators":
        if len(location) < 2:
            return "SEMANTIC_INDICATORS_INVALID"
        if len(location) < 3:
            return "INDICATOR_INVALID"
        return {
            "indicator_id": "INDICATOR_ID_INVALID",
            "parameters": "INDICATOR_PARAMETERS_INVALID",
            "timeframe": "INDICATOR_TIMEFRAME_INVALID",
        }.get(str(location[2]), "INDICATOR_FIELDS_INVALID")
    if root == "conditions":
        if len(location) < 2:
            return "SEMANTIC_CONDITIONS_INVALID"
        if len(location) < 3:
            return "CONDITION_INVALID"
        return {
            "subject": "CONDITION_SUBJECT_INVALID",
            "operator": "CONDITION_OPERATOR_INVALID",
            "value": "CONDITION_VALUE_INVALID",
        }.get(str(location[2]), "CONDITION_FIELDS_INVALID")
    return {
        "schema_version": "SEMANTIC_SCHEMA_VERSION_INVALID",
        "primary_intent": "SEMANTIC_PRIMARY_INTENT_INVALID",
        "secondary_intents": "SEMANTIC_SECONDARY_INTENTS_INVALID",
        "action": "SEMANTIC_ACTION_INVALID",
        "direction": "SEMANTIC_DIRECTION_INVALID",
        "subtype": "SEMANTIC_SUBTYPE_INVALID",
        "domain": "SEMANTIC_DOMAIN_INVALID",
        "symbols": "SEMANTIC_SYMBOLS_INVALID",
        "requested_data": "SEMANTIC_REQUESTED_DATA_INVALID",
        "context_references": "SEMANTIC_CONTEXT_REFERENCES_INVALID",
        "requested_mode": "SEMANTIC_REQUESTED_MODE_INVALID",
        "account_scope": "SEMANTIC_ACCOUNT_SCOPE_INVALID",
        "explicit_fields": "SEMANTIC_EXPLICIT_FIELDS_INVALID",
        "unresolved_fields": "SEMANTIC_UNRESOLVED_FIELDS_INVALID",
        "negated": "SEMANTIC_NEGATED_INVALID",
        "hypothetical": "SEMANTIC_HYPOTHETICAL_INVALID",
    }.get(root, "SEMANTIC_OUTPUT_FIELDS_INVALID")


def _normalize_declared_missing_indicator_children(payload: dict[str, Any]) -> dict[str, Any]:
    unresolved = payload.get("unresolved_fields")
    indicators = payload.get("indicators")
    if not isinstance(unresolved, list) or not isinstance(indicators, list):
        return payload

    unresolved_paths = {item for item in unresolved if isinstance(item, str)}
    normalized_indicators: list[Any] = []
    changed = False
    for index, indicator in enumerate(indicators):
        if not isinstance(indicator, dict):
            normalized_indicators.append(indicator)
            continue
        normalized = dict(indicator)
        parameters = normalized.get("parameters")
        if isinstance(parameters, dict):
            normalized_parameters = dict(parameters)
            parent_path = f"indicators[{index}].parameters"
            for name, value in parameters.items():
                child_path = f"{parent_path}.{name}"
                if value is None and (child_path in unresolved_paths or parent_path in unresolved_paths):
                    normalized_parameters.pop(name)
                    changed = True
            normalized["parameters"] = normalized_parameters
        timeframe_path = f"indicators[{index}].timeframe"
        if normalized.get("timeframe") is None and timeframe_path in unresolved_paths:
            normalized.pop("timeframe", None)
            changed = True
        normalized_indicators.append(normalized)
    return {**payload, "indicators": normalized_indicators} if changed else payload


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-finite JSON values are invalid")
