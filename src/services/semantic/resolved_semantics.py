"""Deterministic context resolution for validated structured semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
from typing import Any, Iterable, Mapping

from src.services.semantic.structured_semantics import (
    SemanticCondition,
    SemanticIndicator,
    StructuredSemanticResult,
)
from src.services.trading.market.timeframes import (
    SUPPORTED_TIMEFRAMES,
    normalize_timeframe,
    resolve_symbol,
)


FIELD_SOURCES = frozenset(
    {
        "USER_EXPLICIT",
        "USER_CONFIRMED_SUGGESTION",
        "LLM_SUGGESTION",
        "CONVERSATION_INHERITED",
        "STRATEGY_POLICY",
        "MARKET_CALCULATED",
        "SYSTEM_CALCULATED",
        "ACCOUNT_CALCULATED",
        "POLICY_DEFAULT",
        "UNRESOLVED",
    }
)
_PREVIOUS_SYMBOL = "previous_symbol"
_PREVIOUS_INDICATOR = "previous_indicator"
_PREVIOUS_TIMEFRAME = "previous_timeframe"
_PREVIOUS_POSITION = frozenset({"previous_position", "previous_order"})
_DIRECT_TRADE_ACTIONS = frozenset({"OPEN_POSITION", "CLOSE_POSITION", "MANAGE_POSITION"})


@dataclass(frozen=True)
class ResolvedSemanticState:
    """Validated semantic facts after deterministic, reference-only inheritance."""

    semantic: StructuredSemanticResult
    canonical_symbols: tuple[str, ...]
    broker_symbols: tuple[str, ...]
    unresolved_symbols: tuple[str, ...]
    indicators: tuple[SemanticIndicator, ...]
    conditions: tuple[SemanticCondition, ...]
    field_sources: tuple[tuple[str, str], ...]
    unresolved_fields: tuple[str, ...]

    @property
    def timeframes(self) -> tuple[str, ...]:
        return _dedupe(indicator.timeframe for indicator in self.indicators if indicator.timeframe)

    def as_dict(self) -> dict[str, object]:
        return {
            "input": self.semantic.as_dict(),
            "canonical_symbols": list(self.canonical_symbols),
            "broker_symbols": list(self.broker_symbols),
            "unresolved_symbols": list(self.unresolved_symbols),
            "indicators": [indicator.as_dict() for indicator in self.indicators],
            "conditions": [condition.as_dict() for condition in self.conditions],
            "timeframes": list(self.timeframes),
            "field_sources": dict(self.field_sources),
            "unresolved_fields": list(self.unresolved_fields),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolvedSemanticState":
        expected = {
            "input",
            "canonical_symbols",
            "broker_symbols",
            "unresolved_symbols",
            "indicators",
            "conditions",
            "timeframes",
            "field_sources",
            "unresolved_fields",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID")
        field_sources = payload["field_sources"]
        if not isinstance(field_sources, Mapping):
            raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID")
        try:
            state = cls(
                semantic=StructuredSemanticResult.from_payload(payload["input"]),
                canonical_symbols=_text_values(payload["canonical_symbols"]),
                broker_symbols=_text_values(payload["broker_symbols"]),
                unresolved_symbols=_text_values(payload["unresolved_symbols"]),
                indicators=tuple(SemanticIndicator.from_payload(item) for item in _items(payload["indicators"])),
                conditions=tuple(SemanticCondition.from_payload(item) for item in _items(payload["conditions"])),
                field_sources=tuple(
                    (str(field), str(source))
                    for field, source in field_sources.items()
                    if str(field).strip() and str(source) in FIELD_SOURCES
                ),
                unresolved_fields=_text_values(payload["unresolved_fields"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID") from exc
        if len(state.field_sources) != len(field_sources):
            raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID")
        return state


@dataclass(frozen=True)
class SemanticFieldUpdate:
    """One explicit, typed update to an unresolved strategy child field."""

    field_path: str
    value: str | float
    source: str

    def __post_init__(self) -> None:
        if self.source not in {"USER_EXPLICIT", "USER_CONFIRMED_SUGGESTION"}:
            raise ValueError("SEMANTIC_COMPLETION_SOURCE_INVALID")


@dataclass(frozen=True)
class SemanticCompletionPatch:
    updates: tuple[SemanticFieldUpdate, ...]

    def __post_init__(self) -> None:
        paths = tuple(update.field_path for update in self.updates)
        if not paths or len(set(paths)) != len(paths):
            raise ValueError("SEMANTIC_COMPLETION_PATCH_INVALID")


def apply_semantic_completion(
    state: ResolvedSemanticState,
    patch: SemanticCompletionPatch,
) -> ResolvedSemanticState:
    """Apply form values without reparsing user language or inventing siblings."""

    indicators = list(state.indicators)
    sources = dict(state.field_sources)
    unresolved = list(state.unresolved_fields)
    for update in patch.updates:
        match = re.fullmatch(
            r"indicators\[(\d+)]\.(timeframe|parameters\.([A-Za-z][A-Za-z0-9_]*))",
            update.field_path,
        )
        if match is None or int(match.group(1)) >= len(indicators):
            raise ValueError("SEMANTIC_COMPLETION_FIELD_INVALID")
        index = int(match.group(1))
        indicator = indicators[index]
        child = match.group(2)
        if child == "timeframe":
            timeframe = normalize_timeframe(str(update.value).strip())
            if timeframe not in SUPPORTED_TIMEFRAMES:
                raise ValueError("SEMANTIC_COMPLETION_TIMEFRAME_INVALID")
            indicators[index] = replace(indicator, timeframe=timeframe)
        else:
            if isinstance(update.value, bool) or not isinstance(update.value, (int, float)):
                raise ValueError("SEMANTIC_COMPLETION_PARAMETER_INVALID")
            number = float(update.value)
            if not math.isfinite(number):
                raise ValueError("SEMANTIC_COMPLETION_PARAMETER_INVALID")
            parameters = dict(indicator.parameters)
            parameters[str(match.group(3))] = number
            indicators[index] = replace(
                indicator,
                parameters=tuple(sorted(parameters.items())),
            )
        sources[update.field_path] = update.source
        parent = f"indicators[{index}].parameters" if child.startswith("parameters.") else ""
        unresolved = [
            field for field in unresolved if field not in {update.field_path, parent}
        ]

    semantic = replace(
        state.semantic,
        indicators=tuple(indicators),
        unresolved_fields=tuple(unresolved),
        explicit_fields=_dedupe(
            (*state.semantic.explicit_fields, *(item.field_path for item in patch.updates))
        ),
    )
    return replace(
        state,
        semantic=semantic,
        indicators=tuple(indicators),
        field_sources=tuple(sources.items()),
        unresolved_fields=tuple(unresolved),
    )


def resolve_structured_semantics(
    semantic: StructuredSemanticResult,
    previous: ResolvedSemanticState | None = None,
) -> ResolvedSemanticState:
    """Resolve configured aliases and explicit conversational references only."""

    field_sources: list[tuple[str, str]] = []
    unresolved = list(semantic.unresolved_fields)
    semantic = _resolve_management_reference(semantic, previous, unresolved, field_sources)
    references = set(semantic.context_references)

    for field_name, value in (
        ("action", semantic.action),
        ("direction", semantic.direction),
        ("requested_mode", semantic.requested_mode),
    ):
        if value:
            field_sources.append(
                (
                    field_name,
                    "USER_EXPLICIT"
                    if field_name in semantic.explicit_fields
                    else "LLM_SUGGESTION",
                )
            )

    canonical_symbols, broker_symbols, unresolved_symbols = _resolve_symbols(
        semantic.symbols,
        previous if not semantic.symbols and _PREVIOUS_SYMBOL in references and previous and previous.canonical_symbols else None,
        field_sources,
    )
    unresolved.extend(f"symbols[{index}]" for index in range(len(unresolved_symbols)))
    if _PREVIOUS_SYMBOL in references and not semantic.symbols and not (previous and previous.canonical_symbols):
        unresolved.append(f"context_references.{_PREVIOUS_SYMBOL}")

    indicators = _resolve_indicators(semantic, previous, references, field_sources, unresolved)
    conditions = tuple(semantic.conditions)
    field_sources.extend((f"conditions[{index}]", "USER_EXPLICIT") for index in range(len(conditions)))

    for index, indicator in enumerate(indicators):
        if indicator.timeframe:
            continue
        unresolved.append(f"indicators[{index}].timeframe")
        field_sources.append((f"indicators[{index}].timeframe", "UNRESOLVED"))

    for field_name in semantic.unresolved_fields:
        field_sources.append((field_name, "UNRESOLVED"))

    return ResolvedSemanticState(
        semantic=semantic,
        canonical_symbols=canonical_symbols,
        broker_symbols=broker_symbols,
        unresolved_symbols=unresolved_symbols,
        indicators=indicators,
        conditions=conditions,
        field_sources=tuple(field_sources),
        unresolved_fields=_dedupe(unresolved),
    )


def resolve_operating_mode(semantic: StructuredSemanticResult) -> str:
    """Resolve mode from validated semantic facts without granting execution authority."""

    if semantic.negated or semantic.hypothetical:
        return "advisory_only"
    if (
        semantic.requested_mode == "autonomous_live"
        and "requested_mode" in semantic.explicit_fields
    ):
        return "autonomous_live"
    if semantic.action in _DIRECT_TRADE_ACTIONS:
        return "human_confirmed_live"
    return "advisory_only"


def _resolve_management_reference(
    semantic: StructuredSemanticResult,
    previous: ResolvedSemanticState | None,
    unresolved: list[str],
    field_sources: list[tuple[str, str]],
) -> StructuredSemanticResult:
    placeholders = _PREVIOUS_POSITION & set(semantic.context_references)
    if not placeholders:
        return semantic
    inherited = next(
        (
            value
            for value in (previous.semantic.context_references if previous else ())
            if re.fullmatch(r"[0-9a-fA-F]{64}", value)
        ),
        "",
    )
    references = tuple(
        inherited if value in placeholders and inherited else value
        for value in semantic.context_references
        if value not in placeholders or inherited
    )
    for placeholder in sorted(placeholders):
        field = f"context_references.{placeholder}"
        if inherited:
            field_sources.append((field, "CONVERSATION_INHERITED"))
        else:
            unresolved.append(field)
            field_sources.append((field, "UNRESOLVED"))
    return replace(semantic, context_references=references)


def _resolve_symbols(
    symbols: tuple[str, ...],
    inherited: ResolvedSemanticState | None,
    field_sources: list[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if not symbols and inherited is not None:
        field_sources.extend((f"symbols[{index}]", "CONVERSATION_INHERITED") for index in range(len(inherited.canonical_symbols)))
        return inherited.canonical_symbols, inherited.broker_symbols, inherited.unresolved_symbols

    canonical: list[str] = []
    broker: list[str] = []
    unresolved: list[str] = []
    for index, raw_symbol in enumerate(symbols):
        resolution = resolve_symbol(raw_symbol)
        field_sources.append((f"symbols[{index}]", "USER_EXPLICIT"))
        if resolution.status == "RESOLVED":
            canonical.append(resolution.canonical_symbol)
            broker.append(resolution.broker_symbol)
        else:
            unresolved.append(resolution.raw_symbol)
    return _dedupe(canonical), _dedupe(broker), _dedupe(unresolved)


def _resolve_indicators(
    semantic: StructuredSemanticResult,
    previous: ResolvedSemanticState | None,
    references: set[str],
    field_sources: list[tuple[str, str]],
    unresolved: list[str],
) -> tuple[SemanticIndicator, ...]:
    current = semantic.indicators
    inherit_indicator = _PREVIOUS_INDICATOR in references
    inherit_timeframe = _PREVIOUS_TIMEFRAME in references
    if not current:
        if inherit_indicator and previous is not None:
            field_sources.extend((f"indicators[{index}]", "CONVERSATION_INHERITED") for index in range(len(previous.indicators)))
            return previous.indicators
        if inherit_indicator and previous is None:
            unresolved.append(f"context_references.{_PREVIOUS_INDICATOR}")
        return ()

    previous_by_id = {indicator.indicator_id.upper(): indicator for indicator in (previous.indicators if previous else ())}
    resolved: list[SemanticIndicator] = []
    for index, indicator in enumerate(current):
        indicator_id = indicator.indicator_id.upper()
        prior = previous_by_id.get(indicator_id)
        parameters = dict(indicator.parameters)
        if (inherit_indicator or inherit_timeframe) and prior is None:
            unresolved.append(
                f"context_references.{_PREVIOUS_INDICATOR if inherit_indicator else _PREVIOUS_TIMEFRAME}"
            )
        if inherit_indicator and prior is not None:
            parameters = {**dict(prior.parameters), **parameters}
        timeframe = _resolved_timeframe(indicator.timeframe, prior, inherit_indicator or inherit_timeframe)
        if indicator.timeframe and timeframe == "":
            unresolved.append(f"indicators[{index}].timeframe")
        resolved.append(SemanticIndicator(indicator_id=indicator_id, parameters=tuple(sorted(parameters.items())), timeframe=timeframe))
        field_sources.append((f"indicators[{index}].indicator_id", "USER_EXPLICIT"))
        field_sources.append((f"indicators[{index}].timeframe", "USER_EXPLICIT" if indicator.timeframe else "CONVERSATION_INHERITED" if timeframe else "UNRESOLVED"))
        for name in parameters:
            source = "USER_EXPLICIT" if name in dict(indicator.parameters) else "CONVERSATION_INHERITED"
            field_sources.append((f"indicators[{index}].parameters.{name}", source))
    return tuple(resolved)


def _resolved_timeframe(raw: str, previous: SemanticIndicator | None, may_inherit: bool) -> str:
    if raw:
        normalized = normalize_timeframe(raw)
        return normalized if normalized in SUPPORTED_TIMEFRAMES else ""
    if may_inherit and previous is not None:
        return previous.timeframe
    return ""


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value.upper()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return tuple(output)


def _items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID")
    return value


def _text_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("RESOLVED_SEMANTIC_STATE_INVALID")
    return tuple(item.strip() for item in value)
