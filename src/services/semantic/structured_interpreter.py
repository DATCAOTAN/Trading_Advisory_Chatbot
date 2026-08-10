"""One-call structured semantic interpretation over the existing reasoning provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.config import Config
from src.services.semantic.structured_semantics import (
    ACTION_VALUES,
    ACCOUNT_SCOPES,
    DIRECTION_VALUES,
    PRIMARY_INTENTS,
    RESULT_FIELDS,
    REQUESTED_MODES,
    SEMANTIC_SCHEMA_VERSION,
    StructuredSemanticResult,
    StructuredSemanticValidationError,
)
from src.services.trading.reasoning.llm_adapter import ProjectLLMReasoningProvider
from src.services.trading.reasoning.strategy_evidence import INDICATOR_REGISTRY


@dataclass(frozen=True)
class StructuredSemanticInterpretation:
    status: str
    semantic: StructuredSemanticResult | None
    issues: tuple[str, ...]
    provider_calls: int
    latency_ms: int
    provider: str
    model: str

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID" and self.semantic is not None


class StructuredSemanticInterpreter:
    """Converts raw language to non-authoritative semantic facts with one provider call."""

    def __init__(self, provider: Any | None = None):
        self.provider = provider

    def interpret(self, message: str) -> StructuredSemanticInterpretation:
        provider_name = str(getattr(Config, "TRADING_REASONING_LLM_PROVIDER", "") or "")
        model = str(getattr(Config, "TRADING_REASONING_MODEL", "") or "")
        if not str(message or "").strip():
            return self._invalid("SEMANTIC_MESSAGE_EMPTY", provider_name, model, 0, 0)
        if not self.provider and not bool(getattr(Config, "TRADING_REASONING_LLM_ENABLED", False)):
            return self._invalid("SEMANTIC_PROVIDER_DISABLED", provider_name, model, 0, 0)

        started = perf_counter()
        try:
            provider = self.provider or ProjectLLMReasoningProvider(provider_name, structured_json=True)
            raw = provider.complete(
                self._prompt(message),
                max_tokens=int(Config.TRADING_REASONING_MAX_TOKENS),
                temperature=float(Config.TRADING_REASONING_TEMPERATURE),
            )
            semantic = StructuredSemanticResult.from_json(raw)
        except StructuredSemanticValidationError as exc:
            return self._invalid(
                str(exc),
                provider_name,
                model,
                1,
                _elapsed_ms(started),
                diagnostic=_safe_validation_diagnostic(raw, str(exc)),
            )
        except Exception as exc:  # Deliberate provider boundary: fail closed without raw output logging.
            return self._invalid(f"SEMANTIC_PROVIDER_{type(exc).__name__.upper()}", provider_name, model, 1, _elapsed_ms(started))

        result = StructuredSemanticInterpretation(
            status="VALID",
            semantic=semantic,
            issues=(),
            provider_calls=1,
            latency_ms=_elapsed_ms(started),
            provider=provider_name,
            model=model,
        )
        self._log(result)
        return result

    @staticmethod
    def _prompt(message: str) -> str:
        indicator_contract = {
            indicator_id: list(definition.parameters)
            for indicator_id, definition in sorted(INDICATOR_REGISTRY.items())
        }
        enum_contract = {
            "primary_intent": sorted(PRIMARY_INTENTS),
            "action": sorted(ACTION_VALUES),
            "direction": sorted(DIRECTION_VALUES),
            "requested_mode": sorted(REQUESTED_MODES),
            "account_scope": sorted(ACCOUNT_SCOPES),
        }
        schema = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "primary_intent": "string",
            "secondary_intents": ["zero or more primary intent values"],
            "action": "string",
            "direction": "string",
            "subtype": "string",
            "domain": "string",
            "symbols": ["raw or normalized user symbol references"],
            "indicators": [{"indicator_id": "string", "parameters": {}, "timeframe": "M1"}],
            "requested_data": ["string"],
            "conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            "context_references": ["previous_symbol"],
            "requested_mode": "string",
            "account_scope": "string",
            "explicit_fields": ["field paths explicitly present in the message"],
            "unresolved_fields": ["field paths that remain incomplete"],
            "negated": False,
            "hypothetical": False,
        }
        return (
            "Return one JSON object only. Interpret meaning but never validate broker, market, account, "
            "pricing, permissions, or execution. Do not include any execution-authority field. "
            "Keep missing child fields in unresolved_fields while preserving explicit sibling facts. "
            "Classify definitions, explanations, or comparisons of financial concepts and indicators as "
            "KNOWLEDGE with action EXPLAIN; an indicator name alone does not make the request position management. "
            "Classify a direct instruction to open, buy, sell, or define a conditional entry as STRATEGY or "
            "TRADE_LIFECYCLE with action OPEN_POSITION, preserving explicit direction and incomplete fields. "
            "When the user explicitly asks the system to trade autonomously or continue trading without "
            "per-trade confirmation, set requested_mode to autonomous_live and include requested_mode in "
            "explicit_fields. For a direct trade instruction without that autonomous request, set "
            "requested_mode to human_confirmed_live. For advisory analysis, set requested_mode to "
            "advisory_only. Mode classification describes user intent only and grants no execution authority. "
            "A question asking whether the user should buy or sell remains ANALYSIS and does not request a trade. "
            "Classify read-only questions about existing positions, pending orders, current or realized P/L, "
            "entry or current price, SL/TP, volume, open or close time, trade history, lifecycle state, or "
            "stored trade provenance as POSITION_MANAGEMENT with action NONE or EXPLAIN; list the requested "
            "facts in requested_data. Do not classify such reads as STRATEGY unless the user asks to create "
            "or change a strategy. "
            "Classify direct human management commands as POSITION_MANAGEMENT. Use action MANAGE_POSITION "
            "for CANCEL_PENDING_ORDER, MODIFY_POSITION_PROTECTION, and PARTIAL_CLOSE; use action CLOSE_POSITION "
            "for CLOSE_POSITION. Put that exact management intent in subtype. Represent explicit management "
            "numbers only as conditions with operator EQUAL and subjects requested_stop_loss, "
            "requested_take_profit, close_fraction, close_amount, or resulting_volume. Normalize close_fraction "
            "to a ratio greater than 0 and at most 1. Use context_references for an explicit protected target "
            "reference or previous_position/previous_order; never invent a target or a management number. "
            "Only include indicator parameters explicitly present in the message or referenced context; "
            "do not use conventional defaults. Do not invent indicator parameters. When an indicator parameter or "
            "timeframe is missing, omit the parameter key, use an empty parameters object or empty timeframe string, "
            "and add its field path to unresolved_fields; never use null, placeholder text, an object, or a list as "
            "the missing scalar value. The following is a reference-only "
            "indicator contract; do not include an indicator_contract field in the output: "
            + json.dumps(indicator_contract, ensure_ascii=False, sort_keys=True)
            + ". The following is a reference-only enum contract; do not include an enum_contract field in the output: "
            + json.dumps(enum_contract, ensure_ascii=False, sort_keys=True)
            + ". Scalar enum fields must each contain exactly one matching string. Use only the indicator IDs and "
            "parameter keys from the indicator contract. Subtype and domain must each be one short string, never "
            "an object or list; use an empty string when no canonical value applies. "
            "For indicator analysis, a condition subject must exactly "
            "equal one indicator_id in indicators; management conditions use only the management subjects listed "
            "above. Do not append a period, timeframe, or output alias. Required exact output schema: "
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            + "\nUser message:\n"
            + str(message)
        )

    def _invalid(
        self,
        issue: str,
        provider: str,
        model: str,
        provider_calls: int,
        latency_ms: int,
        diagnostic: str = "",
    ) -> StructuredSemanticInterpretation:
        result = StructuredSemanticInterpretation(
            status="INVALID",
            semantic=None,
            issues=(issue,),
            provider_calls=provider_calls,
            latency_ms=latency_ms,
            provider=provider,
            model=model,
        )
        self._log(result, diagnostic=diagnostic)
        return result

    @staticmethod
    def _log(result: StructuredSemanticInterpretation, *, diagnostic: str = "") -> None:
        if diagnostic:
            print(f"[StructuredSemanticInvalid] {diagnostic}")
        semantic = result.semantic
        indicator_shapes = ";".join(
            f"{item.indicator_id}(keys={','.join(name for name, _ in item.parameters) or '-'};"
            f"types={','.join(type(value).__name__ for _, value in item.parameters) or '-'};"
            f"timeframe={item.timeframe or '-'})"
            for item in (semantic.indicators if semantic else ())
        ) or "-"
        condition_shapes = ";".join(
            f"{item.subject}(operator={item.operator};value_type={type(item.value).__name__})"
            for item in (semantic.conditions if semantic else ())
        ) or "-"
        unresolved = ",".join(semantic.unresolved_fields if semantic else ()) or "-"
        print(
            "[StructuredSemantic] "
            f"schema={SEMANTIC_SCHEMA_VERSION} provider={result.provider or 'disabled'} "
            f"status={result.status} primary_intent={semantic.primary_intent if semantic else ''} "
            f"indicator_shapes={indicator_shapes} condition_shapes={condition_shapes} "
            f"unresolved={unresolved} "
            f"issues={','.join(result.issues) or '-'} "
            f"provider_calls={result.provider_calls} latency_ms={result.latency_ms}"
        )


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)


def _safe_validation_diagnostic(raw: Any, issue: str) -> str:
    """Reports only bounded enum-shape facts from rejected provider JSON."""
    payload = _json_object_or_none(raw)
    top_level_keys = sorted(key for key in (payload or {}) if key in RESULT_FIELDS)
    primary_intent = (payload or {}).get("primary_intent", _MISSING)
    primary_type, primary_raw, primary_normalized = _safe_primary_intent(primary_intent)
    normalized = f" primary_intent_normalized={primary_normalized}" if primary_normalized else ""
    return (
        f"semantic_validation_status=INVALID issue_codes=[{issue}] "
        f"top_level_keys=[{','.join(top_level_keys)}] "
        f"primary_intent_raw={primary_raw} primary_intent_type={primary_type}{normalized}"
    )


_MISSING = object()


def _json_object_or_none(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _safe_primary_intent(value: Any) -> tuple[str, str, str]:
    if value is _MISSING:
        return "missing", "<missing>", ""
    if not isinstance(value, str):
        return type(value).__name__, "<non_scalar>", ""
    if len(value) > 64:
        return "str", "<redacted_over_limit>", ""

    normalized = value.strip().upper()
    if normalized in PRIMARY_INTENTS:
        return "str", value, normalized if normalized != value else ""
    if value and all("A" <= character <= "Z" or character.isdigit() or character == "_" for character in value):
        return "str", value, ""
    return "str", "<redacted_non_enum_scalar>", ""
