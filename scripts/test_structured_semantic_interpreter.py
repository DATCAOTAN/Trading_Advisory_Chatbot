from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.semantic.structured_interpreter import StructuredSemanticInterpreter
from src.services.semantic.structured_semantics import SEMANTIC_SCHEMA_VERSION


class ScriptedProvider:
    def __init__(self, output: str):
        self.output = output
        self.calls: list[tuple[str, int, float]] = []

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        self.calls.append((prompt, max_tokens, temperature))
        return self.output


def semantic_payload(**changes):
    payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "primary_intent": "STRATEGY",
        "secondary_intents": [],
        "action": "OPEN_POSITION",
        "direction": "BUY",
        "subtype": "",
        "domain": "trading",
        "symbols": ["XAUUSDm"],
        "indicators": [{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        "requested_data": [],
        "conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        "context_references": [],
        "requested_mode": "",
        "account_scope": "",
        "explicit_fields": [
            "action",
            "direction",
            "symbols[0]",
            "indicators[0].indicator_id",
            "indicators[0].timeframe",
            "conditions[0]",
        ],
        "unresolved_fields": ["indicators[0].parameters.period"],
        "negated": False,
        "hypothetical": False,
    }
    payload.update(changes)
    return payload


def interpreted(message: str, payload: dict | None = None):
    provider = ScriptedProvider(json.dumps(payload or semantic_payload()))
    result = StructuredSemanticInterpreter(provider).interpret(message)
    return result, provider


@pytest.mark.parametrize(
    "message",
    (
        "hay buy khi RSI cua XAUUSDm khung M1 > 10",
        "buy XAUUSDm when RSI on M1 is above 10",
        "buy XAUUSDm khi RSI M1 > 10",
        "RSI M1 XAUUSDm > 10 thi buy",
    ),
)
def test_equivalent_phrasing_and_word_order_use_one_structured_boundary(message):
    result, provider = interpreted(message)

    assert result.is_valid
    assert result.semantic.action == "OPEN_POSITION"
    assert result.semantic.direction == "BUY"
    assert result.semantic.symbols == ("XAUUSDm",)
    assert result.semantic.indicators[0].indicator_id == "RSI"
    assert result.semantic.indicators[0].timeframe == "M1"
    assert result.semantic.conditions[0].operator == "GREATER_THAN"
    assert result.semantic.conditions[0].value == 10
    assert result.semantic.unresolved_fields == ("indicators[0].parameters.period",)
    assert result.provider_calls == len(provider.calls) == 1
    assert message in provider.calls[0][0]


def test_missing_indicator_child_preserves_explicit_siblings():
    result, _provider = interpreted("buy XAUUSDm when RSI on M1 exceeds 10")

    assert result.is_valid
    assert result.semantic.indicators == (result.semantic.indicators[0],)
    assert result.semantic.indicators[0].parameters == ()
    assert result.semantic.indicators[0].timeframe == "M1"
    assert result.semantic.conditions == (result.semantic.conditions[0],)
    assert result.semantic.conditions[0].value == 10


def test_missing_direction_is_valid_incomplete_semantics_not_structural_failure():
    result, _provider = interpreted(
        "open a position for XAUUSDm",
        semantic_payload(
            direction="",
            indicators=[],
            conditions=[],
            unresolved_fields=["direction"],
        ),
    )

    assert result.is_valid
    assert result.semantic.action == "OPEN_POSITION"
    assert result.semantic.direction == ""
    assert result.semantic.unresolved_fields == ("direction",)


@pytest.mark.parametrize(
    ("message", "payload", "expected"),
    (
        (
            "con do con M15?",
            semantic_payload(
                primary_intent="CONVERSATION",
                action="NONE",
                direction="",
                symbols=[],
                indicators=[],
                conditions=[],
                context_references=["previous_symbol", "previous_timeframe"],
                unresolved_fields=["symbols", "timeframes"],
            ),
            ("CONVERSATION", False, False),
        ),
        (
            "chi phan tich, dung giao dich",
            semantic_payload(
                primary_intent="ANALYSIS",
                action="ANALYZE",
                direction="",
                symbols=[],
                indicators=[],
                conditions=[],
                negated=True,
            ),
            ("ANALYSIS", True, False),
        ),
        (
            "neu toi buy thi sao?",
            semantic_payload(hypothetical=True),
            ("STRATEGY", False, True),
        ),
        (
            "RSI la gi?",
            semantic_payload(
                primary_intent="KNOWLEDGE",
                action="EXPLAIN",
                direction="",
                symbols=[],
                indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": ""}],
                conditions=[],
                unresolved_fields=[],
            ),
            ("KNOWLEDGE", False, False),
        ),
        (
            "RSI14 M1 BTCUSD hien tai bao nhieu?",
            semantic_payload(
                primary_intent="MARKET_DATA",
                action="ANALYZE",
                direction="",
                symbols=["BTCUSD"],
                indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
                requested_data=["current_indicator_value"],
                conditions=[],
                unresolved_fields=[],
            ),
            ("MARKET_DATA", False, False),
        ),
        (
            "giai thich CPI va RSI14 BTCUSD hien tai",
            semantic_payload(
                primary_intent="MARKET_DATA",
                secondary_intents=["KNOWLEDGE"],
                action="ANALYZE",
                direction="",
                symbols=["BTCUSD"],
                indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": ""}],
                requested_data=["current_indicator_value", "macro_explanation"],
                conditions=[],
                unresolved_fields=[],
            ),
            ("MARKET_DATA", False, False),
        ),
    ),
)
def test_reference_negation_concept_current_and_mixed_intents_are_preserved(message, payload, expected):
    result, provider = interpreted(message, payload)

    assert result.is_valid
    assert (result.semantic.primary_intent, result.semantic.negated, result.semantic.hypothetical) == expected
    assert result.provider_calls == len(provider.calls) == 1
    assert "execution_authority" not in result.semantic.as_dict()


@pytest.mark.parametrize(
    "raw",
    (
        "Here is the result: {}",
        json.dumps([]),
        json.dumps({**semantic_payload(), "unexpected": True}),
        json.dumps({**semantic_payload(), "conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": "10"}]}),
        json.dumps({**semantic_payload(), "action": "EXECUTE"}),
        json.dumps({**semantic_payload(), "execution_allowed": True}),
    ),
)
def test_structurally_invalid_or_authority_bearing_output_fails_closed_once(raw):
    provider = ScriptedProvider(raw)
    result = StructuredSemanticInterpreter(provider).interpret("meaningful message")

    assert not result.is_valid
    assert result.status == "INVALID"
    assert result.semantic is None
    assert result.provider_calls == len(provider.calls) == 1


def test_output_round_trip_is_strict_and_numeric_fields_cannot_be_strings():
    payload = semantic_payload()
    result, _provider = interpreted("buy XAUUSDm", payload)

    assert result.semantic.as_dict() == payload


def test_disabled_default_provider_fails_closed_before_provider_construction(monkeypatch):
    from src.services.semantic import structured_interpreter

    monkeypatch.setattr(structured_interpreter.Config, "TRADING_REASONING_LLM_ENABLED", False)
    result = StructuredSemanticInterpreter().interpret("buy XAUUSDm")

    assert not result.is_valid
    assert result.issues == ("SEMANTIC_PROVIDER_DISABLED",)
    assert result.provider_calls == 0


def test_provider_failure_does_not_retry_or_fall_back():
    class FailingProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
            self.calls += 1
            raise RuntimeError("unavailable")

    provider = FailingProvider()
    result = StructuredSemanticInterpreter(provider).interpret("buy XAUUSDm")

    assert not result.is_valid
    assert result.issues == ("SEMANTIC_PROVIDER_RUNTIMEERROR",)
    assert result.provider_calls == provider.calls == 1


def test_boundary_is_not_a_queryplan_capability_or_regex_authority():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/services/semantic/structured_interpreter.py").read_text(encoding="utf-8")
    contract = (root / "src/services/semantic/structured_semantics.py").read_text(encoding="utf-8")

    assert "QueryPlan" not in source + contract
    assert "CapabilityRegistry" not in source + contract
    assert "import re" not in source + contract
    assert "MetaTrader5" not in source + contract
