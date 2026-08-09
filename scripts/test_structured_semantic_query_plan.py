from __future__ import annotations

import pytest

from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import FIELD_SOURCES, resolve_structured_semantics
from src.services.semantic.structured_semantics import SEMANTIC_SCHEMA_VERSION, StructuredSemanticResult
from src.services.semantic.context_requirements import ContextRequirementPlanner


def semantic(**changes) -> StructuredSemanticResult:
    payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "primary_intent": "STRATEGY",
        "secondary_intents": [],
        "action": "OPEN_POSITION",
        "direction": "BUY",
        "subtype": "",
        "domain": "trading",
        "symbols": ["XAUUSDm"],
        "indicators": [{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"}],
        "requested_data": [],
        "conditions": [],
        "context_references": [],
        "requested_mode": "",
        "account_scope": "",
        "explicit_fields": ["symbols[0]", "indicators[0]"],
        "unresolved_fields": [],
        "negated": False,
        "hypothetical": False,
    }
    payload.update(changes)
    return StructuredSemanticResult.from_payload(payload)


def test_current_explicit_timeframe_overrides_valid_context_and_preserves_siblings():
    previous = resolve_structured_semantics(semantic(symbols=["BTCUSD"], indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"}]))
    current = semantic(
        primary_intent="CONVERSATION",
        action="NONE",
        direction="",
        symbols=[],
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M15"}],
        context_references=["previous_symbol", "previous_indicator"],
    )

    state = resolve_structured_semantics(current, previous)
    plan = QueryPlanAssembler().assemble("con M15?", structured_semantics=current, previous_structured_context=previous)

    assert state.canonical_symbols == ("BTCUSD",)
    assert state.indicators[0].parameters == (("period", 14.0),)
    assert state.indicators[0].timeframe == "M15"
    assert dict(state.field_sources)["symbols[0]"] == "CONVERSATION_INHERITED"
    assert dict(state.field_sources)["indicators[0].timeframe"] == "USER_EXPLICIT"
    assert plan.entities.symbols == ["BTCUSD"]
    assert plan.entities.timeframes == ["M15"]
    assert plan.requested_indicators[0].parameter_map() == {"period": 14.0}


def test_missing_indicator_child_preserves_indicator_condition_and_unresolved_field():
    incomplete = semantic(
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        unresolved_fields=["indicators[0].parameters.period"],
    )

    plan = QueryPlanAssembler().assemble("irrelevant legacy wording", structured_semantics=incomplete)

    assert plan.primary_intent == "conversational_strategy_request"
    assert plan.user_action_intent == "consider_entry"
    assert plan.requested_indicators == []
    assert plan.semantic_context["indicators"] == [
        {"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}
    ]
    assert plan.semantic_context["conditions"] == [
        {"subject": "RSI", "operator": "GREATER_THAN", "value": 10.0}
    ]
    assert "unresolved:indicators[0].parameters.period" in plan.ambiguity
    assert all("INDICATOR_MISSING" not in value and "ENTRY_RULE_MISSING" not in value for value in plan.ambiguity)


def test_position_management_structured_semantics_use_trade_capabilities_not_unknown_fallback():
    source = semantic(
        primary_intent="POSITION_MANAGEMENT",
        action="OPEN_POSITION",
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        unresolved_fields=["indicators[0].parameters.period"],
    )

    plan = QueryPlanAssembler().assemble("raw wording must not override structured semantics", structured_semantics=source)
    requirements = ContextRequirementPlanner().plan(plan)

    assert plan.primary_intent == "trade_opportunity_analysis"
    assert plan.current_market_request is True
    assert plan.constraints["semantic_action"] == "OPEN_POSITION"
    assert plan.semantic_context["input"]["primary_intent"] == "POSITION_MANAGEMENT"
    assert "unresolved:indicators[0].parameters.period" in plan.ambiguity
    assert {need.capability for need in requirements.required_needs} == {
        "market_snapshot",
        "ohlcv",
        "economic_event",
    }
    assert all(need.target != "general" for need in requirements.needs)


def test_valid_structured_semantics_skip_weaker_raw_router_classifier_and_decomposer():
    class UnexpectedRawSemanticParser:
        def route(self, *_args):
            raise AssertionError("legacy router called")

        def classify(self, *_args):
            raise AssertionError("legacy answer-mode classifier called")

        def decompose(self, *_args):
            raise AssertionError("legacy decomposer called")

    parser = UnexpectedRawSemanticParser()
    plan = QueryPlanAssembler(parser, parser, parser).assemble(
        "explain RSI from a book",
        structured_semantics=semantic(
            primary_intent="MARKET_DATA",
            action="ANALYZE",
            direction="",
            symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            requested_data=["current_indicator_value"],
        ),
    )

    assert plan.primary_intent == "market_state_analysis"
    assert plan.entities.symbols == ["BTCUSD"]
    assert plan.current_market_request is True
    assert plan.source_signals["decomposition"]["reason"] == "structured_semantics"


def test_unrelated_previous_context_never_leaks_without_a_reference():
    previous = resolve_structured_semantics(semantic(symbols=["BTCUSD"]))
    independent = semantic(
        primary_intent="KNOWLEDGE",
        action="EXPLAIN",
        direction="",
        symbols=[],
        indicators=[],
    )

    state = resolve_structured_semantics(independent, previous)

    assert state.canonical_symbols == ()
    assert state.indicators == ()
    assert state.unresolved_fields == ()


def test_missing_referenced_context_stays_unresolved_without_a_guess():
    state = resolve_structured_semantics(
        semantic(
            primary_intent="CONVERSATION",
            action="NONE",
            direction="",
            symbols=[],
            indicators=[],
            context_references=["previous_symbol", "previous_indicator"],
        )
    )

    assert state.canonical_symbols == ()
    assert "context_references.previous_symbol" in state.unresolved_fields
    assert "context_references.previous_indicator" in state.unresolved_fields


def test_missing_referenced_indicator_in_another_context_stays_unresolved():
    previous = resolve_structured_semantics(
        semantic(indicators=[{"indicator_id": "EMA", "parameters": {"period": 20}, "timeframe": "H1"}])
    )
    state = resolve_structured_semantics(
        semantic(
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
            context_references=["previous_indicator"],
            unresolved_fields=["indicators[0].parameters.period"],
        ),
        previous,
    )

    assert state.indicators[0].parameters == ()
    assert "context_references.previous_indicator" in state.unresolved_fields


def test_mixed_semantics_survive_authoritative_query_plan_projection():
    source = semantic(
        primary_intent="MARKET_DATA",
        secondary_intents=["KNOWLEDGE"],
        action="ANALYZE",
        direction="",
        symbols=["BTCUSD"],
        indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
        requested_data=["current_indicator_value", "concept_explanation"],
    )

    plan = QueryPlanAssembler().assemble("raw text must not decide intent", structured_semantics=source)

    assert plan.primary_intent == "market_state_analysis"
    assert plan.secondary_intents == ["book_concept_explanation"]
    assert plan.conceptual_request is True
    assert plan.semantic_context["input"]["primary_intent"] == "MARKET_DATA"
    assert plan.semantic_context["input"]["secondary_intents"] == ["KNOWLEDGE"]


def test_structured_market_plan_reuses_existing_context_requirement_planner():
    plan = QueryPlanAssembler().assemble(
        "raw text cannot select the profile",
        structured_semantics=semantic(
            primary_intent="MARKET_DATA",
            action="ANALYZE",
            direction="",
            symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            requested_data=["current_indicator_value"],
        ),
    )
    requirements = ContextRequirementPlanner().plan(plan)

    assert {item.capability for item in requirements.required_needs} == {
        "market_snapshot",
        "ohlcv",
        "technical_snapshot",
    }
    assert next(item for item in requirements.needs if item.capability == "ohlcv").parameters["timeframe"] == "M1"


@pytest.mark.parametrize(
    ("query", "expected_primary"),
    [
        ("What is RSI?", "book_concept_explanation"),
        ("What is driving gold now?", "market_state_analysis"),
    ],
)
def test_legacy_assembly_remains_the_bounded_fallback_without_structured_semantics(query, expected_primary):
    plan = QueryPlanAssembler().assemble(query)

    assert plan.primary_intent == expected_primary
    assert plan.semantic_context == {}


def test_resolution_and_query_planning_never_grant_execution_authority():
    source = semantic(requested_mode="autonomous_live")
    plan = QueryPlanAssembler().assemble("buy now", structured_semantics=source)

    assert {
        "USER_EXPLICIT",
        "USER_CONFIRMED_SUGGESTION",
        "LLM_SUGGESTION",
        "CONVERSATION_INHERITED",
    } <= FIELD_SOURCES
    assert plan.requires_execution is False
    assert plan.constraints["execution_allowed"] is False
    assert "execution_allowed" not in plan.semantic_context["input"]
