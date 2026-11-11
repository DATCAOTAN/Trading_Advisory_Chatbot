"""Deterministic context resolution for validated structured semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import re
from typing import Any, Iterable, Mapping, get_args

from src.services.semantic.structured_semantics import (
    COMPUTATIONAL_SPEC_FIELD,
    COMPUTATIONAL_SPEC_REFERENCE,
    ComputationalSpecification,
    ResearchGoal,
    SemanticCondition,
    SemanticIndicator,
    SpecificationConfiguration,
    StructuredSemanticResult,
    TradeParameter,
    TradeParameters,
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
_RESEARCH_FACT_SOURCES = frozenset({"USER_EXPLICIT", "USER_CONFIRMED_SUGGESTION", "CONVERSATION_INHERITED"})
RESEARCH_SOURCE_CAPABILITIES = {
    "market_data": ("market_snapshot", "ohlcv"),
    "private_knowledge": ("static_knowledge",),
    "general_knowledge": ("market_knowledge",),
}
_DIRECT_TRADE_ACTIONS = frozenset({"OPEN_POSITION", "CLOSE_POSITION", "MANAGE_POSITION"})
OHLCV_INTEGER_FIELDS = frozenset({"lookback_bars", "warmup_bars", "max_age_seconds"})


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
    value: str | int | float | bool
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

    if state.semantic.computational_specification is not None:
        return _apply_computational_completion(state, patch)

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


def _computational_completion_target(values: dict, path: str) -> tuple[dict, str]:
    parts = path.split(".")
    key = parts[-1]
    if parts[0] == COMPUTATIONAL_SPEC_FIELD:
        if len(parts) == 2 and key in {"objective", "algorithm", "formula"}:
            return values, key
        if len(parts) == 3 and parts[1] == "configuration" and key in SpecificationConfiguration.model_fields:
            return values.setdefault("configuration", {}), key
        if len(parts) == 3:
            match = re.fullmatch(r"(parameters|data_requirements)\[(0|[1-9][0-9]?)]", parts[1])
            if match:
                section, index = match[1], int(match[2])
                rows = values.get(section, [])
                if index < len(rows):
                    row = rows[index]
                    if (section, key) == ("parameters", "value") or (
                        section == "data_requirements"
                        and (key == "timeframe" or key in OHLCV_INTEGER_FIELDS)
                        and (row.get("dataset") or "").upper() == "OHLCV"
                    ):
                        return row, key
    raise ValueError("SEMANTIC_COMPLETION_FIELD_INVALID")


def computational_completion_choices(state: ResolvedSemanticState, missing: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Project only supported missing leaves, not arbitrary client-selected paths."""
    spec = state.semantic.computational_specification
    if spec is None or f"context_references.{COMPUTATIONAL_SPEC_REFERENCE}" in state.unresolved_fields:
        return {}
    values, sources = spec.as_dict(), dict(state.field_sources)
    gaps = dict.fromkeys(missing)
    result = {}
    for gap in gaps:
        path = f"{COMPUTATIONAL_SPEC_FIELD}.formula" if gap == f"{COMPUTATIONAL_SPEC_FIELD}.formula_or_steps" else gap
        if sources.get(path) in _RESEARCH_FACT_SOURCES:
            continue
        try:
            target, key = _computational_completion_target(values, path)
        except ValueError:
            continue
        parent = path.rsplit(".", 1)[0]
        if key == "value" and (
            not target.get("name") or any(f"{parent}.{part}" in gaps for part in ("name", "minimum", "maximum"))
        ):
            continue
        if (key == "timeframe" or key in OHLCV_INTEGER_FIELDS) and f"{parent}.dataset" in gaps:
            continue
        choices = ()
        if path.startswith(f"{COMPUTATIONAL_SPEC_FIELD}.configuration."):
            literal, _ = get_args(SpecificationConfiguration.model_fields[key].annotation)
            choices = get_args(literal)
        elif key == "timeframe":
            choices = SUPPORTED_TIMEFRAMES
        result[path] = choices
    return result


def computational_completion_value(path: str, answer: str) -> str | int | float | bool:
    answer = answer.strip()
    if not answer:
        raise ValueError("Enter a value for the selected field.")
    if len(answer) > 1200:
        raise ValueError("The answer is too long for a specification field.")
    key = path.rsplit(".", 1)[-1]
    if key in OHLCV_INTEGER_FIELDS:
        if re.fullmatch(r"-?[0-9]+", answer) is None:
            unit = "seconds" if key == "max_age_seconds" else "bars"
            raise ValueError(f"Enter one whole number of {unit}, without units or decimals.")
        return int(answer)
    if not path.endswith(".value"):
        return answer
    try:
        value = json.loads(answer)
    except (ValueError, RecursionError):
        raise ValueError('Enter one JSON number, true/false, or quoted text (for example "price").') from None
    if type(value) not in {str, int, float, bool} or (isinstance(value, float) and not math.isfinite(value)):
        raise ValueError("Enter one finite number, boolean, or quoted text; not a list, object, or null.")
    return value


def _apply_computational_completion(
    state: ResolvedSemanticState, patch: SemanticCompletionPatch,
) -> ResolvedSemanticState:
    spec = state.semantic.computational_specification
    assert spec is not None
    values = spec.as_dict()
    sources = dict(state.field_sources)
    unresolved = list(state.unresolved_fields)
    for update in patch.updates:
        target, key = _computational_completion_target(values, update.field_path)
        if update.source == "USER_CONFIRMED_SUGGESTION" and (
            sources.get(update.field_path) != "LLM_SUGGESTION"
            or type(target.get(key)) is not type(update.value)
            or target.get(key) != update.value
        ):
            raise ValueError("COMPUTATIONAL_SUGGESTION_MISMATCH")
        value = update.value
        if key == "timeframe" and (not isinstance(value, str) or value not in SUPPORTED_TIMEFRAMES):
            raise ValueError("Select one supported OHLCV timeframe.")
        if key in OHLCV_INTEGER_FIELDS:
            if type(value) is not int:
                raise ValueError("Enter one whole number.")
            # BSON stores signed 64-bit integers; this is not a market limit.
            if not -(1 << 63) <= value < (1 << 63):
                raise ValueError("The value is outside the supported 64-bit integer range.")
        if key == "value" and any(target.get(bound) is not None for bound in ("minimum", "maximum")):
            if type(value) not in {int, float}:
                raise ValueError("This parameter has numeric bounds and needs a number.")
            lower, upper = target.get("minimum"), target.get("maximum")
            if (lower is not None and value < lower) or (upper is not None and value > upper):
                raise ValueError("The value is outside the parameter's recorded bounds.")
        target[key] = value
        sources[update.field_path] = update.source
        resolved = {update.field_path}
        if key == "formula":
            resolved.add(f"{COMPUTATIONAL_SPEC_FIELD}.formula_or_steps")
        unresolved = [field for field in unresolved if field not in resolved]
    spec = ComputationalSpecification.from_completion_fields(values)
    return replace(
        state,
        semantic=replace(
            state.semantic, computational_specification=spec, unresolved_fields=tuple(unresolved),
        ),
        field_sources=tuple(sources.items()),
        unresolved_fields=tuple(unresolved),
    )


def bind_authoritative_position_reference(
    state: ResolvedSemanticState,
    protected_reference: str,
) -> ResolvedSemanticState:
    """Bind one broker-authoritative selection for a later typed continuation."""

    reference = str(protected_reference or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", reference):
        raise ValueError("POSITION_REFERENCE_INVALID")
    references = (reference,) + tuple(
        value
        for value in state.semantic.context_references
        if value.lower() != reference
    )
    sources = dict(state.field_sources)
    sources["context_references.selected_position"] = "SYSTEM_CALCULATED"
    return replace(
        state,
        semantic=replace(state.semantic, context_references=_dedupe(references)),
        field_sources=tuple(sources.items()),
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
    if semantic.has_computational_request:
        prior = previous if COMPUTATIONAL_SPEC_REFERENCE in references else None
        if COMPUTATIONAL_SPEC_REFERENCE in references and (not prior or not prior.semantic.computational_specification):
            unresolved.append(f"context_references.{COMPUTATIONAL_SPEC_REFERENCE}")
        semantic = _resolve_computational_specification(semantic, prior, field_sources)
    research_previous = None
    if semantic.primary_intent == "STRATEGY_RESEARCH":
        if "previous_research_goal" in references:
            if previous and previous.semantic.primary_intent == "STRATEGY_RESEARCH":
                research_previous = previous
            else:
                unresolved.append("context_references.previous_research_goal")
        semantic = _resolve_research_goal(semantic, research_previous, field_sources)

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

    symbol_previous = previous if _PREVIOUS_SYMBOL in references and previous and previous.canonical_symbols else None
    if semantic.primary_intent == "STRATEGY_RESEARCH":
        symbol_previous = None if "symbols" in semantic.explicit_fields else research_previous or symbol_previous
    canonical_symbols, broker_symbols, unresolved_symbols = _resolve_symbols(
        semantic.symbols,
        symbol_previous if not semantic.symbols else None,
        field_sources,
    )
    unresolved.extend(f"symbols[{index}]" for index in range(len(unresolved_symbols)))
    if _PREVIOUS_SYMBOL in references and not semantic.symbols and not (previous and previous.canonical_symbols):
        unresolved.append(f"context_references.{_PREVIOUS_SYMBOL}")

    indicators = _resolve_indicators(semantic, previous, references, field_sources, unresolved)
    if semantic.action == "OPEN_POSITION":
        explicit = set(semantic.explicit_fields)
        reuse = (
            "previous_trade_parameters" in references and previous is not None
            and previous.semantic.action == semantic.action and previous.semantic.direction == semantic.direction
            and previous.semantic.account_scope == semantic.account_scope
            and resolve_operating_mode(previous.semantic) == resolve_operating_mode(semantic)
            and bool(canonical_symbols) and canonical_symbols == previous.canonical_symbols
        )
        prior = previous.semantic.trade_parameters if reuse else None
        prior_sources = dict(previous.field_sources) if prior is not None else {}
        if "previous_trade_parameters" in references and prior is None:
            unresolved.append("context_references.previous_trade_parameters")
        parameters = {}
        for name in TradeParameters.model_fields:
            path = f"trade_parameters.{name}"
            value = getattr(semantic.trade_parameters, name, None)
            if any(field == path or field.startswith(path + ".") for field in unresolved) or (
                path in explicit and value is None
            ):
                parameters[name] = value or TradeParameter()
                field_sources.append((path, "UNRESOLVED"))
            elif value is not None:
                parameters[name] = value if path in explicit else TradeParameter()
                field_sources.append((path, "USER_EXPLICIT" if path in explicit else "UNRESOLVED"))
            elif prior_sources.get(path) in _RESEARCH_FACT_SOURCES and getattr(prior, name, None) is not None:
                parameters[name] = getattr(prior, name)
                field_sources.append((path, "CONVERSATION_INHERITED"))
        if parameters:
            semantic = replace(semantic, trade_parameters=TradeParameters(**parameters))
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

    if (
        semantic.has_computational_request
        or semantic.primary_intent == "STRATEGY_RESEARCH" or semantic.negated or semantic.hypothetical
    ):
        return "advisory_only"
    if (
        semantic.requested_mode == "autonomous_live"
        and "requested_mode" in semantic.explicit_fields
    ):
        return "autonomous_live"
    if semantic.action in _DIRECT_TRADE_ACTIONS:
        return "human_confirmed_live"
    return "advisory_only"


def _resolve_computational_specification(
    semantic: StructuredSemanticResult,
    previous: ResolvedSemanticState | None,
    field_sources: list[tuple[str, str]],
) -> StructuredSemanticResult:
    current = (semantic.computational_specification or ComputationalSpecification()).as_dict()
    prior_spec = previous.semantic.computational_specification if previous else None
    prior = prior_spec.as_dict() if prior_spec is not None else {}
    prior_sources = dict(previous.field_sources) if previous else {}
    explicit = set(semantic.explicit_fields)
    unresolved = set(semantic.unresolved_fields)

    def is_within(path, parent):
        return path == parent or path.startswith((parent + ".", parent + "["))

    def mark_sources(path, value, source):
        if any(is_within(path, field) for field in unresolved):
            source = "UNRESOLVED"
        elif path in explicit:
            source = "USER_EXPLICIT"
        field_sources.append((path, source))
        if isinstance(value, dict):
            for child, item in value.items():
                mark_sources(f"{path}.{child}", item, source)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                mark_sources(f"{path}[{index}]", item, source)

    def resolve_sections(current_values, prior_values, prefix):
        result = {}
        for name in dict.fromkeys((*current_values, *prior_values)):
            if name == "schema_version":
                continue
            path = f"{prefix}.{name}"
            if name == "configuration" and prefix == COMPUTATIONAL_SPEC_FIELD:
                axes = resolve_sections(current_values.get(name, {}), prior_values.get(name, {}), path)
                if axes:
                    result[name] = axes
                continue
            has_explicit = any(is_within(field, path) for field in explicit)
            blocked = any(is_within(path, field) or is_within(field, path) for field in unresolved)
            if name in current_values and (has_explicit or blocked):
                result[name] = current_values[name]
                source = "LLM_SUGGESTION"
            elif (
                not blocked and not has_explicit and name in prior_values
                and prior_sources.get(path) in _RESEARCH_FACT_SOURCES
                and not any(
                    is_within(child, path) and source not in _RESEARCH_FACT_SOURCES
                    for child, source in prior_sources.items()
                )
                and name not in {"conflicts", "unsupported"}
            ):
                result[name] = prior_values[name]
                source = "CONVERSATION_INHERITED"
            elif name in current_values:
                result[name] = current_values[name]
                source = "LLM_SUGGESTION"
            else:
                continue
            mark_sources(path, result[name], source)
        return result

    values = resolve_sections(current, prior, COMPUTATIONAL_SPEC_FIELD)
    return replace(semantic, computational_specification=ComputationalSpecification.model_validate(values))


def _resolve_research_goal(
    semantic: StructuredSemanticResult,
    previous: ResolvedSemanticState | None,
    field_sources: list[tuple[str, str]],
) -> StructuredSemanticResult:
    prior_sources = dict(previous.field_sources) if previous else {}
    explicit = set(semantic.explicit_fields)
    unresolved = set(semantic.unresolved_fields)
    current = (semantic.research_goal or ResearchGoal()).model_dump(exclude_none=True)
    prior = (
        previous.semantic.research_goal.model_dump(exclude_none=True)
        if previous and previous.semantic.research_goal is not None else {}
    )
    goal = {}
    for field in ResearchGoal.model_fields:
        path = f"research_goal.{field}"
        value = current.get(field)
        if path in explicit and value is not None and value != "":
            goal[field] = value
            field_sources.append((path, "USER_EXPLICIT"))
        elif path not in explicit | unresolved and field in prior and prior_sources.get(path) in _RESEARCH_FACT_SOURCES:
            goal[field] = prior[field]
            field_sources.append((path, "CONVERSATION_INHERITED"))
    context = {}
    for field, empty in (("account_scope", ""), ("requested_data", ())):
        if field in explicit:
            context[field] = getattr(semantic, field)
            field_sources.append((field, "USER_EXPLICIT"))
        elif previous and field not in unresolved and prior_sources.get(field) in _RESEARCH_FACT_SOURCES:
            context[field] = getattr(previous.semantic, field)
            field_sources.append((field, "CONVERSATION_INHERITED"))
        else:
            context[field] = empty
    context["requested_data"] = tuple(dict.fromkeys(
        source for source in context["requested_data"] if source in RESEARCH_SOURCE_CAPABILITIES
    ))
    return replace(
        semantic, action="ANALYZE", direction="", indicators=(), conditions=(),
        research_goal=ResearchGoal(**goal), **context,
    )


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
