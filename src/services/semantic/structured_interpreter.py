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
    REQUESTED_MODES,
    SEMANTIC_SCHEMA_VERSION,
    StructuredSemanticResult,
    StructuredSemanticValidationError,
)
from src.services.trading.reasoning.llm_adapter import ProjectLLMReasoningProvider


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
            return self._invalid(str(exc), provider_name, model, 1, _elapsed_ms(started))
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
        schema = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "primary_intent": sorted(PRIMARY_INTENTS),
            "secondary_intents": ["zero or more primary intent values"],
            "action": sorted(ACTION_VALUES),
            "direction": sorted(DIRECTION_VALUES),
            "subtype": "string",
            "domain": "string",
            "symbols": ["raw or normalized user symbol references"],
            "indicators": [{"indicator_id": "string", "parameters": {}, "timeframe": "M1"}],
            "requested_data": ["string"],
            "conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            "context_references": ["previous_symbol"],
            "requested_mode": sorted(REQUESTED_MODES),
            "account_scope": sorted(ACCOUNT_SCOPES),
            "explicit_fields": ["field paths explicitly present in the message"],
            "unresolved_fields": ["field paths that remain incomplete"],
            "negated": False,
            "hypothetical": False,
        }
        return (
            "Return one JSON object only. Interpret meaning but never validate broker, market, account, "
            "pricing, permissions, or execution. Do not include any execution-authority field. "
            "Keep missing child fields in unresolved_fields while preserving explicit sibling facts. "
            "Only include indicator parameters explicitly present in the message or referenced context; "
            "do not use conventional defaults. Do not invent indicator parameters. Required exact schema: "
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
        self._log(result)
        return result

    @staticmethod
    def _log(result: StructuredSemanticInterpretation) -> None:
        semantic = result.semantic
        print(
            "[StructuredSemantic] "
            f"schema={SEMANTIC_SCHEMA_VERSION} provider={result.provider or 'disabled'} "
            f"status={result.status} primary_intent={semantic.primary_intent if semantic else ''} "
            f"unresolved_count={len(semantic.unresolved_fields) if semantic else 0} "
            f"provider_calls={result.provider_calls} latency_ms={result.latency_ms}"
        )


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
