from pathlib import Path

import pytest

from src.services.evidence.evidence_pipeline import EvidenceSelector
from src.orchestrator import RAGOrchestrator
from src.services.decision_context import DecisionContextBuilder
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.conversational_context import (
    ConversationalIntentContext,
    resolve_conversational_context,
)
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.trading.decision.conversational_authorization import (
    parse_conversational_trading_request,
)
from src.ui import tab_chatbot


@pytest.mark.parametrize(
    ("query", "family", "response_format"),
    (
        ("What is the current EMA 20 value for BTCUSDm on H1?", "current_market", "MARKET_EVIDENCE_RESPONSE"),
        ("What is EMA and how is it calculated?", "concept", "CONCEPT_EXPLANATION_RESPONSE"),
        ("Trade BTCUSD automatically within my mandate on demo.", "autonomous", "STANDING_MANDATE_CARD"),
        ("Trade BTCUSD but ask before every trade on demo.", "authorization", "MT5_ACCESS_CARD"),
        ("Only analyze BTCUSD; do not trade.", "advisory", "CLARIFICATION_OR_BLOCKER_RESPONSE"),
    ),
)
def test_intent_family_selects_one_central_response_format(query, family, response_format):
    context = resolve_conversational_context(query)

    assert family in context.intent_families
    assert context.response_format == response_format
    assert context.as_dict()["execution_authority"] is False


def test_two_turn_strategy_inherits_symbol_and_latest_timeframe_without_book_fallback():
    first = resolve_conversational_context(
        "What are the current EMA 20 and RSI 14 values for BTCUSDm on H1?"
    )
    second = resolve_conversational_context(
        "hay giao dich khi RSI 14 khung M1 > 10",
        first,
    )
    request = parse_conversational_trading_request(
        "hay giao dich khi RSI 14 khung M1 > 10",
        conversation_id="intent-seed",
        context=second,
    )
    plan = QueryPlanAssembler().assemble(
        "hay giao dich khi RSI 14 khung M1 > 10",
        conversational_context=second,
    )

    assert first.response_format == "MARKET_EVIDENCE_RESPONSE"
    assert (second.canonical_symbol, second.broker_symbol) == ("BTCUSD", "BTCUSDm")
    assert second.timeframes == ("M1",)
    assert second.requested_mode == "human_confirmed_live"
    assert second.confirmation_policy == "CONFIRM_EVERY_TRADE"
    assert second.response_format == "STRATEGY_COMPLETION_REQUIRED_CARD"
    assert request.strategy.entry_rules[0].operator == "GREATER_THAN"
    assert request.strategy.entry_rules[0].constants == (10.0,)
    assert request.strategy.entry_rules[0].left == "rsi_14_m1"
    assert "STRATEGY_DIRECTION_MISSING" in request.blockers
    assert plan.primary_intent == "conversational_strategy_request"
    assert plan.entities.symbols == ["BTCUSD"]
    assert plan.entities.timeframes == ["M1"]
    assert EvidenceSelector.required_roles(plan.primary_intent, "") == ["knowledge_or_data"]
    assert "direct_book_passage" not in plan.constraints


def test_unicode_seed_uses_the_same_contract_without_phrase_special_case():
    first = resolve_conversational_context(
        "EMA 20 v\u00e0 RSI 14 hi\u1ec7n t\u1ea1i c\u1ee7a BTCUSDm tr\u00ean H1 l\u00e0 bao nhi\u00eau?"
    )
    second = resolve_conversational_context(
        "h\u00e3y giao d\u1ecbch khi RSI 14 khung M1 > 10",
        first,
    )

    assert first.intent_families == ("current_market",)
    assert (second.canonical_symbol, second.broker_symbol) == ("BTCUSD", "BTCUSDm")
    assert second.timeframes == ("M1",)
    assert second.response_format == "STRATEGY_COMPLETION_REQUIRED_CARD"


def test_latest_explicit_symbol_and_timeframe_override_inherited_values():
    previous = resolve_conversational_context(
        "Current RSI 14 for XAUUSDm on M15"
    )
    current = resolve_conversational_context(
        "Current RSI 14 for BTCUSDm on H4",
        previous,
    )

    assert current.canonical_symbol == "BTCUSD"
    assert current.broker_symbol == "BTCUSDm"
    assert current.timeframes == ("H4",)


@pytest.mark.parametrize(
    ("query", "blocker"),
    (
        ("Trade when RSI 14 on H1 > 55", "SYMBOL_REQUIRED"),
        ("Trade UNKNOWNUSDm when RSI 14 on H1 > 55", "SYMBOL_UNRESOLVED"),
        ("Trade BTCUSD when RSI 14 on M2 > 55", "TIMEFRAME_UNSUPPORTED"),
    ),
)
def test_missing_or_invalid_context_blocks_without_default_fallback(query, blocker):
    previous = resolve_conversational_context("Current RSI 14 for XAUUSDm on M15")
    context = resolve_conversational_context(query, previous if "UNKNOWN" in query or "M2" in query else None)

    assert blocker in context.blockers
    if blocker in {"SYMBOL_REQUIRED", "SYMBOL_UNRESOLVED"}:
        assert context.canonical_symbol != "XAUUSD"
    if blocker == "TIMEFRAME_UNSUPPORTED":
        assert context.timeframes == ("M2",)
        assert context.timeframes != previous.timeframes


def test_missing_symbol_completion_request_round_trips_without_default_symbol():
    context = resolve_conversational_context("Trade when RSI 14 on H1 > 55")
    request = parse_conversational_trading_request(
        "Trade when RSI 14 on H1 > 55",
        conversation_id="missing-symbol",
        context=context,
    )

    restored = type(request).from_public_dict(request.to_public_dict())
    assert restored.canonical_symbol == ""
    assert restored.broker_symbol == ""
    assert "SYMBOL_REQUIRED" in restored.blockers


def test_mixed_market_and_concept_keeps_both_evidence_needs():
    context = resolve_conversational_context(
        "What is EMA and what is the current EMA 20 value for BTCUSDm on H1?"
    )
    plan = QueryPlanAssembler().assemble(
        "What is EMA and what is the current EMA 20 value for BTCUSDm on H1?",
        conversational_context=context,
    )
    requirements = ContextRequirementPlanner().plan(plan)

    assert set(context.intent_families) >= {"concept", "current_market"}
    assert plan.primary_intent == "market_state_analysis"
    assert plan.conceptual_request is True
    assert {item.capability for item in requirements.needs} >= {
        "market_snapshot",
        "ohlcv",
        "static_knowledge",
    }


def test_complete_strategy_stays_non_executable_and_selects_mode_card():
    context = resolve_conversational_context(
        "Buy BTCUSD on H1 when RSI 14 > 55 with risk 1%, stop loss ATR 14, "
        "take profit 2R, volume 0.01, ask before every trade on demo."
    )
    request = parse_conversational_trading_request(
        "Buy BTCUSD on H1 when RSI 14 > 55 with risk 1%, stop loss ATR 14, "
        "take profit 2R, volume 0.01, ask before every trade on demo.",
        conversation_id="complete-strategy",
        context=context,
    )

    assert context.blockers == ()
    assert context.response_format == "MT5_ACCESS_CARD"
    assert request.to_public_dict()["executable"] is False
    assert request.allowed_next_action == "GRANT_MT5_DEMO_ACCESS"


def test_multiple_indicators_keep_local_timeframes_and_crossover_rule():
    query = (
        "Buy BTCUSD when EMA 20 H1 crosses above EMA 50 H1 and RSI 14 M15 > 55 "
        "with risk 1%, stop loss ATR 14 H1, take profit 2R, volume 0.01, "
        "ask before every trade on demo."
    )
    context = resolve_conversational_context(query)
    request = parse_conversational_trading_request(
        query,
        conversation_id="multi-timeframe-strategy",
        context=context,
    )

    indicator_bindings = {
        (item.indicator_id, int(item.parameter_map()["period"]), item.timeframe)
        for item in request.strategy.indicators
    }
    assert {
        ("EMA", 20, "H1"),
        ("EMA", 50, "H1"),
        ("RSI", 14, "M15"),
        ("ATR", 14, "H1"),
    } <= indicator_bindings
    assert any(
        rule.operator == "CROSSES_ABOVE"
        and rule.left == "ema_20_h1"
        and rule.right == "ema_50_h1"
        for rule in request.strategy.entry_rules
    )
    assert any(
        rule.operator == "GREATER_THAN"
        and rule.left == "rsi_14_m15"
        and rule.constants == (55.0,)
        for rule in request.strategy.entry_rules
    )


def test_mixed_concept_strategy_keeps_both_analysis_responsibilities():
    query = "Explain EMA crossover and use EMA 20 H1 crosses above EMA 50 H1 to trade BTCUSD."
    context = resolve_conversational_context(query)
    plan = QueryPlanAssembler().assemble(query, conversational_context=context)

    assert set(context.intent_families) >= {"concept", "strategy"}
    assert plan.conceptual_request is True
    assert {"strategy_normalization", "strategy_completeness"} <= set(plan.requested_analysis)


@pytest.mark.parametrize(
    ("query", "mode", "policy"),
    (
        ("Trade BTCUSD on demo and ask before every trade.", "human_confirmed_live", "CONFIRM_EVERY_TRADE"),
        ("Trade BTCUSD automatically under my mandate on demo.", "autonomous_live", "STANDING_MANDATE"),
        ("Trade BTCUSD automatically but ask before every trade on demo.", "human_confirmed_live", "CONFIRM_EVERY_TRADE"),
        ("Only analyze BTCUSD; do not trade.", "advisory_only", "NO_EXECUTION"),
    ),
)
def test_mode_policy_is_deterministic_and_conflicts_choose_human_confirmation(query, mode, policy):
    context = resolve_conversational_context(query)

    assert context.requested_mode == mode
    assert context.confirmation_policy == policy


def test_context_round_trip_and_implementation_have_no_router_llm():
    context = resolve_conversational_context("Current ATR 14 for BTCUSDm on H4")

    assert ConversationalIntentContext.from_dict(context.as_dict()) == context
    source = Path("src/services/semantic/conversational_context.py").read_text(encoding="utf-8")
    assert "LLMClient" not in source
    assert "order_send(" not in source

    tampered = context.as_dict()
    tampered["broker_symbol"] = "XAUUSDm"
    with pytest.raises(ValueError, match="CONVERSATIONAL_SYMBOL_BINDING_INVALID"):
        ConversationalIntentContext.from_dict(tampered)


def test_incomplete_strategy_returns_bounded_card_before_provider_or_retrieval():
    previous = resolve_conversational_context("Current RSI 14 for BTCUSDm on H1")
    context = resolve_conversational_context("Trade when RSI 14 on M1 > 10", previous)
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.decision_context_builder = DecisionContextBuilder()

    stream, sources, intent, artifacts = orchestrator.query_financial_advisor(
        "Trade when RSI 14 on M1 > 10",
        conversational_context=context,
    )

    assert "NON_EXECUTABLE" in "".join(stream)
    assert sources == []
    assert intent == "FINANCIAL_RAG"
    assert artifacts["provider_calls"] == 0
    assert artifacts["query_plan"]["primary_intent"] == "conversational_strategy_request"
    assert artifacts["decision_context"]["static_knowledge_required"] is False
    assert artifacts["decision_context"]["market_data_required"] is False


def test_streamlit_reload_uses_persisted_context_and_renders_completion_card(monkeypatch):
    context = resolve_conversational_context("Trade BTCUSD when RSI 14 on M1 > 10")
    request = parse_conversational_trading_request(
        "Trade BTCUSD when RSI 14 on M1 > 10",
        conversation_id="ui-completion",
        context=context,
    )
    rendered = []
    for name in ("markdown", "caption", "info", "warning"):
        monkeypatch.setattr(
            tab_chatbot.st,
            name,
            lambda value, *args, _name=name, **kwargs: rendered.append((_name, value)),
        )

    restored = tab_chatbot._latest_conversational_context(
        [{"role": "assistant", "conversational_context": context.as_dict()}]
    )
    tab_chatbot._render_conversational_trading_authorization(None, request)

    assert restored == context
    assert any("Strategy Completion Required" in str(value) for _, value in rendered)
    assert any("STRATEGY_DIRECTION_MISSING" in str(value) for _, value in rendered)


def test_unrelated_chat_turn_keeps_latest_trading_request_without_pairing_new_semantics():
    context = resolve_conversational_context(
        "Trade BTCUSD automatically when RSI 14 on M1 exceeds 10 on demo"
    )
    request = parse_conversational_trading_request(
        "Trade BTCUSD automatically when RSI 14 on M1 exceeds 10 on demo",
        conversation_id="runtime-continuity",
        context=context,
    )
    messages = [
        {
            "role": "assistant",
            "trading_request": request.to_public_dict(),
        },
        {
            "role": "assistant",
            "content": "An unrelated knowledge answer",
            "resolved_semantic_state": {"newer": "unrelated"},
        },
    ]

    restored_request, restored_state = tab_chatbot._latest_trading_authorization(
        messages
    )

    assert restored_request == request
    assert restored_state is None
