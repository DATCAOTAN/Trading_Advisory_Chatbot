from types import SimpleNamespace

import pytest

from src.orchestrator import RAGOrchestrator
from src.pipelines.modules.router import RouterModule
from src.services.decision_context import DecisionContextBuilder
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import (
    ResolvedSemanticState,
    resolve_structured_semantics,
)
from src.ui import tab_chatbot
from src.services.semantic.structured_semantics import (
    SEMANTIC_SCHEMA_VERSION,
    StructuredSemanticResult,
)
from src.services.trading.decision import conversational_authorization
from src.services.trading.decision.conversational_authorization import (
    parse_conversational_trading_request,
)


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
        "indicators": [{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
        "requested_data": [],
        "conditions": [{"subject": "RSI", "operator": "GREATER_THAN", "value": 30}],
        "context_references": [],
        "requested_mode": "human_confirmed_live",
        "account_scope": "DEMO",
        "explicit_fields": ["action", "direction", "symbols[0]", "indicators[0]", "conditions[0]"],
        "unresolved_fields": [],
        "negated": False,
        "hypothetical": False,
    }
    payload.update(changes)
    return StructuredSemanticResult.from_payload(payload)


def request_from(source: StructuredSemanticResult, raw: str = "arbitrary raw wording", previous=None):
    plan = QueryPlanAssembler().assemble(
        raw,
        structured_semantics=source,
        previous_structured_context=previous,
    )
    request = parse_conversational_trading_request(
        raw,
        conversation_id="semantic-cutover",
        query_plan=plan,
    )
    assert request is not None
    return plan, request


@pytest.mark.parametrize(
    "raw",
    (
        "buy XAUUSD khi RSI14 M1 > 30",
        "RSI14 M1 XAUUSD vuot 30 thi buy",
        "buy gold when M1 RSI(14) exceeds 30",
    ),
)
def test_equivalent_structured_meaning_projects_without_raw_phrase_parsing(raw):
    _plan, request = request_from(semantic(), raw)

    assert request.trade_action == "OPEN_POSITION"
    assert request.trade_direction == "BUY"
    assert request.canonical_symbol == "XAUUSD"
    assert request.broker_symbol == "XAUUSDm"
    assert request.strategy.indicators[0].parameter_map() == {"period": 14.0}
    assert request.strategy.entry_rules[0].constants == (30.0,)


def test_missing_indicator_child_retains_typed_parent_and_rule_without_raw_reparse():
    _plan, request = request_from(
        semantic(
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=["indicators[0].parameters.period"],
        )
    )

    assert request.strategy.indicators[0].indicator_id == "RSI"
    assert request.strategy.indicators[0].timeframe == "M1"
    assert request.strategy.indicators[0].parameter_map() == {}
    assert request.strategy.entry_rules[0].operator == "GREATER_THAN"
    assert request.strategy.entry_rules[0].constants == (10.0,)
    assert "SEMANTIC_UNRESOLVED:indicators[0].parameters.period" in request.blockers
    assert "STRATEGY_INDICATORS_MISSING" not in request.blockers
    assert "ENTRY_RULE_MISSING" not in request.blockers


def test_resolved_context_inheritance_reaches_trading_projection_without_a_second_parser():
    previous = resolve_structured_semantics(semantic(symbols=["BTCUSD"], requested_mode=""))
    source = semantic(
        primary_intent="CONVERSATION",
        symbols=[],
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 30}],
        context_references=["previous_symbol", "previous_indicator"],
        requested_mode="human_confirmed_live",
    )

    _plan, request = request_from(source, "con M1 va buy khi > 30", previous)

    assert (request.canonical_symbol, request.broker_symbol) == ("BTCUSD", "BTCUSDm")
    assert request.strategy.indicators[0].parameter_map() == {"period": 14.0}
    assert request.strategy.indicators[0].timeframe == "M1"
    assert request.strategy.entry_rules[0].constants == (30.0,)


def test_persisted_resolved_state_round_trips_for_the_next_authoritative_turn():
    state = resolve_structured_semantics(semantic(symbols=["BTCUSD"]))

    assert ResolvedSemanticState.from_dict(state.as_dict()) == state
    assert tab_chatbot._latest_resolved_semantic_state(
        [{"role": "assistant", "resolved_semantic_state": state.as_dict()}]
    ) == state


def test_authoritative_query_plan_wins_even_when_all_legacy_parsers_would_fail(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("raw trading parser called")

    monkeypatch.setattr(conversational_authorization, "resolve_conversational_context", unexpected)
    monkeypatch.setattr(conversational_authorization, "normalize_trade_instruction", unexpected)
    monkeypatch.setattr(conversational_authorization, "parse_conversational_strategy", unexpected)

    _plan, request = request_from(semantic(), "only analyze this unrelated text")

    assert request.trade_action == "OPEN_POSITION"
    assert request.strategy.entry_rules[0].constants == (30.0,)


@pytest.mark.parametrize(
    ("changes", "expected_blocker"),
    (
        ({"negated": True}, "NEGATED_TRADE_ACTION"),
        ({"hypothetical": True}, "HYPOTHETICAL_TRADE_ACTION"),
    ),
)
def test_negated_and_hypothetical_trade_meaning_cannot_become_actionable(changes, expected_blocker):
    _plan, request = request_from(semantic(**changes))

    assert request.trade_action == ""
    assert request.trade_direction == ""
    assert request.allowed_next_action == "BLOCKED"
    assert expected_blocker in request.blockers
    assert request.to_public_dict()["executable"] is False


@pytest.mark.parametrize("mode", ("advisory_only", "human_confirmed_live", "autonomous_live"))
def test_mode_changes_policy_not_structured_strategy_facts(mode):
    _plan, request = request_from(semantic(requested_mode=mode))

    assert request.strategy.indicators[0].as_dict() == {
        "indicator_id": "RSI",
        "timeframe": "M1",
        "parameters": {"period": 14.0},
        "output_alias": "rsi_14_m1",
    }
    assert request.strategy.entry_rules[0].as_dict() == {
        "operator": "GREATER_THAN",
        "left": "rsi_14_m1",
        "right": "",
        "constants": [30.0],
    }
    assert request.requested_mode == mode
    assert request.to_public_dict()["execution_authority"] is False


def test_multiple_supported_conditions_survive_projection_without_a_strategy_dsl():
    _plan, request = request_from(
        semantic(
            indicators=[
                {"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"},
                {"indicator_id": "EMA", "parameters": {"period": 20}, "timeframe": "M1"},
            ],
            conditions=[
                {"subject": "RSI", "operator": "GREATER_THAN", "value": 30},
                {"subject": "EMA", "operator": "GREATER_THAN", "value": 1},
            ],
        )
    )

    assert len(request.strategy.entry_rules) == 2
    assert {rule.left for rule in request.strategy.entry_rules} == {"rsi_14_m1", "ema_20_m1"}


def test_supported_close_lifecycle_semantics_are_projected_without_mutation():
    _plan, request = request_from(
        semantic(
            primary_intent="TRADE_LIFECYCLE",
            action="CLOSE_POSITION",
            direction="",
            indicators=[],
            conditions=[],
        )
    )

    assert request.trade_action == "CLOSE_POSITION"
    assert request.to_public_dict()["execution_authority"] is False
    assert request.to_public_dict()["executable"] is False


def test_legacy_fallback_remains_available_without_an_authoritative_plan():
    request = parse_conversational_trading_request(
        "Trade BTCUSD but ask before every trade on demo.",
        conversation_id="legacy-cutover",
    )

    assert request is not None
    assert request.canonical_symbol == "BTCUSD"
    assert request.requested_mode == "human_confirmed_live"


def test_orchestrator_uses_one_structured_interpretation_and_returns_the_same_projection():
    source = semantic()
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.decision_context_builder = DecisionContextBuilder()
    orchestrator.router_module = RouterModule()
    orchestrator.structured_semantic_interpreter = SimpleNamespace(
        interpret=lambda _message: SimpleNamespace(
            is_valid=True,
            semantic=source,
            provider_calls=1,
        )
    )

    stream, sources, intent, artifacts = orchestrator.query_financial_advisor(
        "raw text must not be parsed again",
        session_id="orchestrator-cutover",
    )

    assert "NON_EXECUTABLE" in "".join(stream)
    assert sources == []
    assert intent == "FINANCIAL_RAG"
    assert artifacts["semantic_provider_calls"] == artifacts["provider_calls"] == 1
    assert artifacts["trading_request"]["execution_authority"] is False
    assert artifacts["query_plan"]["semantic_context"]["input"] == source.as_dict()
