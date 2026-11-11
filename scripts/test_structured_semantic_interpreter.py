from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.structured_interpreter import StructuredSemanticInterpreter
from src.services.semantic.structured_semantics import (
    SEMANTIC_SCHEMA_VERSION,
    StructuredSemanticResult,
    StructuredSemanticValidationError,
)


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


@pytest.mark.parametrize("indicator_id", ("RSI", "EMA"))
def test_missing_supported_indicator_parameter_preserves_explicit_siblings(indicator_id):
    payload = semantic_payload(
        indicators=[{"indicator_id": indicator_id, "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": indicator_id, "operator": "GREATER_THAN", "value": 10}],
        unresolved_fields=["indicators[0].parameters.period"],
    )
    result, _provider = interpreted(f"buy when {indicator_id} M1 exceeds 10", payload)

    assert result.is_valid
    assert result.semantic.indicators[0].indicator_id == indicator_id
    assert result.semantic.indicators[0].parameters == ()
    assert result.semantic.indicators[0].timeframe == "M1"
    assert result.semantic.conditions[0].value == 10
    assert result.semantic.unresolved_fields == ("indicators[0].parameters.period",)


def test_explicit_indicator_period_remains_explicit():
    result, _provider = interpreted(
        "buy when RSI14 M1 exceeds 10",
        semantic_payload(
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            unresolved_fields=[],
        ),
    )

    assert result.is_valid
    assert result.semantic.indicators[0].parameters == (("period", 14.0),)
    assert result.semantic.unresolved_fields == ()


def test_prompt_uses_existing_indicator_contract_without_parameter_defaults():
    prompt = StructuredSemanticInterpreter._prompt("buy when RSI14 M1 exceeds 10")

    assert '"RSI": ["period"]' in prompt
    assert '"MACD": ["fast_period", "slow_period", "signal_period"]' in prompt
    assert "condition subject must exactly equal one indicator_id" in prompt
    assert "do not include an indicator_contract field in the output" in prompt
    assert "do not include an enum_contract field in the output" in prompt
    output_schema = json.loads(prompt.rsplit("Required exact output schema: ", 1)[1].split("\nUser message:", 1)[0])
    assert "indicator_contract" not in output_schema
    assert "enum_contract" not in output_schema
    assert output_schema["primary_intent"] == "string"
    assert output_schema["action"] == "string"
    assert output_schema["direction"] == "string"
    assert '"period": 14' not in prompt


def test_safe_structured_log_reports_shape_without_raw_message(capsys):
    message = "private operator wording RSI14 M1 above 10"
    result, _provider = interpreted(
        message,
        semantic_payload(
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            unresolved_fields=[],
        ),
    )

    output = capsys.readouterr().out

    assert result.is_valid
    assert "indicator_shapes=RSI(keys=period;types=float;timeframe=M1)" in output
    assert "condition_shapes=RSI(operator=GREATER_THAN;value_type=float)" in output
    assert "unresolved=-" in output
    assert "issues=-" in output
    assert message not in output


def test_invalid_primary_intent_logs_only_bounded_structural_diagnostic(capsys):
    payload = semantic_payload(primary_intent="TRADING", domain="private provider prose must stay hidden")
    raw = json.dumps(payload)
    provider = ScriptedProvider(raw)

    result = StructuredSemanticInterpreter(provider).interpret("private user input must stay hidden")
    output = capsys.readouterr().out

    assert result.issues == ("SEMANTIC_PRIMARY_INTENT_INVALID",)
    assert "[StructuredSemanticInvalid] semantic_validation_status=INVALID" in output
    assert "issue_codes=[SEMANTIC_PRIMARY_INTENT_INVALID]" in output
    assert "primary_intent_type=str" in output
    assert "primary_intent_raw=TRADING" in output
    assert "primary_intent_normalized" not in output
    assert raw not in output
    assert payload["domain"] not in output
    assert len(provider.calls) == result.provider_calls == 1


def test_invalid_non_scalar_primary_intent_logs_type_without_payload_dump(capsys):
    payload = semantic_payload(primary_intent={"unexpected": "STRATEGY"})
    raw = json.dumps(payload)
    provider = ScriptedProvider(raw)

    result = StructuredSemanticInterpreter(provider).interpret("meaningful message")
    output = capsys.readouterr().out

    assert result.issues == ("SEMANTIC_PRIMARY_INTENT_INVALID",)
    assert "primary_intent_type=dict" in output
    assert "primary_intent_raw=<non_scalar>" in output
    assert raw not in output
    assert "unexpected" not in output
    assert len(provider.calls) == result.provider_calls == 1


def test_validation_diagnostic_keeps_valid_semantics_and_strict_rejection_unchanged(capsys):
    valid_result, valid_provider = interpreted("buy XAUUSDm", semantic_payload())
    valid_output = capsys.readouterr().out
    invalid_raw = json.dumps(semantic_payload(primary_intent="TRADING"))

    with pytest.raises(StructuredSemanticValidationError, match="SEMANTIC_PRIMARY_INTENT_INVALID"):
        StructuredSemanticResult.from_json(invalid_raw)

    assert valid_result.is_valid
    assert "[StructuredSemanticInvalid]" not in valid_output
    assert len(valid_provider.calls) == valid_result.provider_calls == 1


def test_prompt_does_not_suggest_conventional_indicator_parameters():
    prompt = StructuredSemanticInterpreter._prompt("buy when RSI M1 exceeds 10")

    assert '"parameters": {}' in prompt
    assert '"period": 14' not in prompt
    assert "do not use conventional defaults" in prompt


def test_prompt_separates_indicator_knowledge_from_position_management():
    prompt = StructuredSemanticInterpreter._prompt("arbitrary concept wording")

    assert "definitions, explanations, or comparisons" in prompt
    assert "KNOWLEDGE with action EXPLAIN" in prompt
    assert "indicator name alone does not make the request position management" in prompt


@pytest.mark.parametrize(
    "message,requested_data",
    (
        ("tổng lời lổ hiện tại", ["pnl"]),
        ("tong loi lo hien tai", ["pnl"]),
        ("lời lổ hiện tại", ["pnl"]),
        ("pnl hien tai", ["pnl"]),
        ("vị thế hiện tai", ["positions"]),
        ("sl tp hien tai", ["stop_loss", "take_profit"]),
        ("lich su giao dich hien tai", ["trade_history"]),
    ),
)
def test_noisy_trade_state_language_keeps_the_position_read_contract(message, requested_data):
    result, provider = interpreted(
        message,
        semantic_payload(
            primary_intent="POSITION_MANAGEMENT",
            action="EXPLAIN",
            direction="",
            domain="trading",
            symbols=[],
            indicators=[],
            requested_data=requested_data,
            conditions=[],
            requested_mode="advisory_only",
            explicit_fields=["primary_intent", "action", "requested_data"],
            unresolved_fields=[],
        ),
    )
    plan = QueryPlanAssembler().assemble(message, structured_semantics=result.semantic)

    assert result.is_valid
    assert result.semantic.primary_intent == "POSITION_MANAGEMENT"
    assert plan.primary_intent == "position_state_read"
    assert plan.requires_execution is False
    assert len(provider.calls) == 1
    assert message in provider.calls[0][0]


@pytest.mark.parametrize("message", ("P/L là gì?", "ATR là gì?", "Lạm phát ảnh hưởng gì đến vàng?"))
def test_conceptual_financial_questions_remain_knowledge(message):
    result, provider = interpreted(
        message,
        semantic_payload(
            primary_intent="KNOWLEDGE",
            action="EXPLAIN",
            direction="",
            subtype="concept",
            domain="finance",
            symbols=[],
            indicators=[],
            requested_data=[],
            conditions=[],
            requested_mode="advisory_only",
            explicit_fields=["primary_intent", "action"],
            unresolved_fields=[],
        ),
    )
    plan = QueryPlanAssembler().assemble(message, structured_semantics=result.semantic)

    assert result.is_valid
    assert result.semantic.primary_intent == "KNOWLEDGE"
    assert plan.primary_intent == "book_concept_explanation"
    assert len(provider.calls) == 1


def test_prompt_requires_noise_tolerance_without_keyword_routing():
    prompt = StructuredSemanticInterpreter._prompt("tổng lời lổ hiện tại")

    assert "minor spelling errors" in prompt
    assert "missing or incorrect diacritics" in prompt
    assert "noisy multilingual wording" in prompt
    assert "must not change an otherwise clear intent family" in prompt


def test_prompt_requires_scalar_optional_semantic_labels():
    prompt = StructuredSemanticInterpreter._prompt("arbitrary strategy wording")

    assert "Subtype and domain must each be one short string" in prompt
    assert "never an object or list" in prompt
    assert "use an empty string when no canonical value applies" in prompt


def test_prompt_preserves_missing_indicator_children_as_unresolved():
    prompt = StructuredSemanticInterpreter._prompt("arbitrary incomplete indicator wording")

    assert "omit the parameter key" in prompt
    assert "empty parameters object or empty timeframe string" in prompt
    assert "add its field path to unresolved_fields" in prompt
    assert "never use null, placeholder text" in prompt


def test_prompt_separates_direct_trade_instructions_from_advisory_questions():
    prompt = StructuredSemanticInterpreter._prompt("arbitrary direct or advisory wording")

    assert "direct instruction to open, buy, sell" in prompt
    assert "action OPEN_POSITION" in prompt
    assert "question asking whether the user should buy or sell remains ANALYSIS" in prompt
    assert "trade autonomously or continue trading without per-trade confirmation" in prompt
    assert "requested_mode to autonomous_live" in prompt
    assert "requested_mode to human_confirmed_live" in prompt
    assert "requested_mode to advisory_only" in prompt
    assert "grants no execution authority" in prompt


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


@pytest.mark.parametrize(
    ("changes", "expected"),
    (
        ({"unexpected": True}, "SEMANTIC_OUTPUT_FIELDS_INVALID"),
        ({"execution_authority": True}, "SEMANTIC_OUTPUT_AUTHORITY_FIELD_FORBIDDEN"),
        ({"action": "EXECUTE"}, "SEMANTIC_ACTION_INVALID"),
        ({"schema_version": "structured-semantic/v0"}, "SEMANTIC_SCHEMA_VERSION_INVALID"),
        ({"conditions": {"subject": "RSI"}}, "SEMANTIC_CONDITIONS_INVALID"),
        ({"conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": "10"}]}, "CONDITION_VALUE_INVALID"),
        ({"conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": True}]}, "CONDITION_VALUE_INVALID"),
        ({"indicators": [{"indicator_id": "RSI", "parameters": {"period": "14"}, "timeframe": "M1"}]}, "INDICATOR_PARAMETERS_INVALID"),
    ),
)
def test_pydantic_boundary_rejects_invalid_untrusted_payloads(changes, expected):
    payload = semantic_payload(**changes)

    with pytest.raises(StructuredSemanticValidationError, match=expected):
        StructuredSemanticResult.from_payload(payload)


@pytest.mark.parametrize("value", (10, 10.5))
def test_pydantic_boundary_accepts_json_integer_and_float_numbers(value):
    semantic = StructuredSemanticResult.from_payload(
        semantic_payload(conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": value}])
    )

    assert semantic.conditions[0].value == float(value)


@pytest.mark.parametrize("raw_value", ("NaN", "Infinity", "-Infinity"))
def test_pydantic_boundary_rejects_non_finite_json_numbers(raw_value):
    raw = json.dumps(semantic_payload()).replace('"value": 10', f'"value": {raw_value}')

    with pytest.raises(StructuredSemanticValidationError, match="SEMANTIC_OUTPUT_INVALID_JSON"):
        StructuredSemanticResult.from_json(raw)


def test_pydantic_boundary_preserves_partial_semantic_siblings_and_round_trip():
    payload = semantic_payload(
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        unresolved_fields=["indicators[0].parameters.period"],
    )

    semantic = StructuredSemanticResult.from_payload(payload)

    assert semantic.indicators[0].parameters == ()
    assert semantic.indicators[0].timeframe == "M1"
    assert semantic.conditions[0].value == 10.0
    assert semantic.unresolved_fields == ("indicators[0].parameters.period",)
    assert StructuredSemanticResult.from_payload(semantic.as_dict()) == semantic


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
    contract_path = root / "src/services/semantic/structured_semantics.py"
    contract = contract_path.read_text(encoding="utf-8")
    pydantic_paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "src").rglob("*.py")
        if "pydantic" in path.read_text(encoding="utf-8").lower()
    )

    assert "QueryPlan" not in source + contract
    assert "CapabilityRegistry" not in source + contract
    assert "import re" not in source + contract
    assert "MetaTrader5" not in source + contract
    assert "trading.research" not in source + contract
    assert "from pydantic import" in contract
    # R1 validates research records and separate computation approval, not LLM semantics.
    assert pydantic_paths == [
        "src/services/semantic/structured_semantics.py",
        "src/services/trading/research/descriptive_computation.py",
        "src/services/trading/research/proposal.py",
    ]
