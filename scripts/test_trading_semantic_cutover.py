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
from src.services.trading.reasoning.strategy_evidence import strategy_identity
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraftService,
    EditableTradeDraftStore,
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
    assert type(request).from_public_dict(request.to_public_dict()) == request


@pytest.mark.parametrize(
    ("indicator_id", "parameters", "unresolved_fields"),
    (
        ("RSI", {}, ("indicators[0].parameters.period",)),
        (
            "MACD",
            {},
            (
                "indicators[0].parameters.fast_period",
                "indicators[0].parameters.slow_period",
                "indicators[0].parameters.signal_period",
            ),
        ),
    ),
)
def test_incomplete_indicator_semantics_defer_draft_evidence_without_cascades(
    tmp_path,
    indicator_id,
    parameters,
    unresolved_fields,
):
    _plan, request = request_from(
        semantic(
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": indicator_id, "parameters": parameters, "timeframe": "M1"}],
            conditions=[{"subject": indicator_id, "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=list(unresolved_fields),
        )
    )

    draft = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    ).build_or_load(request, conversation_id="semantic-evidence", evidence=None)

    assert set(f"SEMANTIC_UNRESOLVED:{field}" for field in unresolved_fields) <= set(draft.blockers)
    assert not {
        "MARKET_EVIDENCE_UNAVAILABLE",
        "STRUCTURE_EVIDENCE_UNAVAILABLE",
        "TARGET_CALCULATION_DEPENDENCY_MISSING",
        "ACCOUNT_RISK_BASIS_UNAVAILABLE",
        "TICK_VALUE_UNAVAILABLE",
        "DEMO_ACCOUNT_SCOPE_REQUIRED",
    } & set(draft.blockers)
    assert "EVIDENCE_NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED" in draft.warnings
    assert draft.executable is False
    assert draft.execution_authority is False


def test_explicit_rsi_period_reloads_after_an_incomplete_prior_turn():
    previous = resolve_structured_semantics(
        semantic(
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=["indicators[0].parameters.period"],
        )
    )
    _plan, request = request_from(
        semantic(
            primary_intent="TRADE_LIFECYCLE",
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=[],
        ),
        previous=previous,
    )

    assert request.strategy.semantic_unresolved_fields == ()
    assert request.strategy.indicators[0].parameter_map() == {"period": 14.0}
    assert type(request).from_public_dict(request.to_public_dict()) == request


@pytest.mark.parametrize(
    ("indicator_id", "parameters", "unresolved_fields"),
    (
        ("RSI", {"period": 14}, ()),
        ("EMA", {"period": 20}, ()),
        ("MACD", {"fast_period": 12, "slow_period": 26, "signal_period": 9}, ()),
        ("RSI", {}, ("indicators[0].parameters.period",)),
        ("MACD", {"fast_period": 12, "slow_period": 26}, ("indicators[0].parameters.signal_period",)),
    ),
)
def test_typed_strategy_and_public_request_round_trip_preserve_indicator_contract(
    indicator_id,
    parameters,
    unresolved_fields,
):
    _plan, request = request_from(
        semantic(
            primary_intent="TRADE_LIFECYCLE",
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": indicator_id, "parameters": parameters, "timeframe": "M1"}],
            conditions=[{"subject": indicator_id, "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=list(unresolved_fields),
        )
    )

    strategy = request.strategy
    assert strategy is not None
    assert type(strategy).from_dict(strategy.as_dict()) == strategy
    assert type(request).from_public_dict(request.to_public_dict()) == request
    assert strategy_identity(strategy) == strategy.identity
    assert strategy.indicators[0].parameter_map() == {
        name: float(value) for name, value in parameters.items()
    }
    assert strategy.semantic_unresolved_fields == unresolved_fields


def test_invalid_structured_strategy_is_not_published_for_public_reload():
    _plan, request = request_from(
        semantic(
            primary_intent="TRADE_LIFECYCLE",
            symbols=["BTCUSDm"],
            indicators=[
                {
                    "indicator_id": "RSI",
                    "parameters": {"period": 14, "unsupported_parameter": 10},
                    "timeframe": "M1",
                }
            ],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=[],
        )
    )

    assert request.strategy is None
    assert "INDICATOR_PARAMETER_INVALID" in request.blockers
    assert type(request).from_public_dict(request.to_public_dict()) == request
    assert request.to_public_dict()["executable"] is False


def test_explicit_valid_parameter_reconciles_conflicting_unresolved_field():
    _plan, request = request_from(
        semantic(
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=["indicators[0].parameters.period"],
        )
    )

    assert request.strategy is not None
    assert request.strategy.semantic_unresolved_fields == ()
    assert "SEMANTIC_UNRESOLVED:indicators[0].parameters.period" not in request.blockers
    assert "INDICATOR_PARAMETER_INVALID" not in request.blockers
    assert type(request).from_public_dict(request.to_public_dict()) == request


def test_ambiguous_condition_subject_remains_unresolved():
    _plan, request = request_from(
        semantic(
            indicators=[
                {"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"},
                {"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"},
            ],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        )
    )

    assert request.strategy is not None
    assert request.strategy.entry_rules == ()
    assert request.strategy.semantic_unresolved_fields == ("conditions[0].subject_binding",)
    assert "SEMANTIC_UNRESOLVED:conditions[0].subject_binding" in request.blockers


@pytest.mark.parametrize(
    ("indicator_id", "unresolved_fields"),
    (
        ("RSI", ("indicators[0].parameters.period",)),
        (
            "MACD",
            (
                "indicators[0].parameters.fast_period",
                "indicators[0].parameters.slow_period",
                "indicators[0].parameters.signal_period",
            ),
        ),
    ),
)
def test_projection_marks_registry_required_indicator_children_unresolved_when_provider_omits_them(
    indicator_id,
    unresolved_fields,
):
    _plan, request = request_from(
        semantic(
            primary_intent="POSITION_MANAGEMENT",
            indicators=[{"indicator_id": indicator_id, "parameters": {}, "timeframe": "M1"}],
            conditions=[{"subject": indicator_id, "operator": "GREATER_THAN", "value": 10}],
        )
    )

    assert request.trade_action == "OPEN_POSITION"
    assert request.trade_direction == "BUY"
    assert request.strategy.indicators[0].parameter_map() == {}
    assert request.strategy.entry_rules[0].constants == (10.0,)
    assert request.strategy.semantic_unresolved_fields == unresolved_fields
    assert set(f"SEMANTIC_UNRESOLVED:{field}" for field in unresolved_fields) <= set(request.blockers)
    assert "INDICATOR_PARAMETER_INVALID" not in request.blockers
    assert type(request).from_public_dict(request.to_public_dict()) == request


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


@pytest.mark.parametrize(
    ("semantic_changes", "expected_mode"),
    (
        (
            {
                "primary_intent": "STRATEGY",
                "action": "ANALYZE",
                "requested_mode": "human_confirmed_live",
            },
            "advisory_only",
        ),
        ({"action": "OPEN_POSITION", "requested_mode": "advisory_only"}, "human_confirmed_live"),
        ({"action": "OPEN_POSITION", "direction": "SELL", "requested_mode": ""}, "human_confirmed_live"),
        ({"action": "CLOSE_POSITION", "direction": "", "requested_mode": ""}, "human_confirmed_live"),
        ({"action": "MANAGE_POSITION", "direction": "", "requested_mode": ""}, "human_confirmed_live"),
        (
            {
                "requested_mode": "autonomous_live",
                "explicit_fields": [
                    "action",
                    "direction",
                    "symbols[0]",
                    "indicators[0]",
                    "conditions[0]",
                    "requested_mode",
                ],
            },
            "autonomous_live",
        ),
    ),
)
def test_mode_is_deterministic_and_does_not_change_strategy_facts(
    semantic_changes, expected_mode
):
    source = semantic(**semantic_changes)
    plan, request = request_from(source)

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
    assert request.requested_mode == expected_mode
    assert plan.constraints["requested_mode"] == expected_mode
    assert plan.constraints["requested_mode_evidence"] == source.requested_mode
    assert request.confirmation_policy == {
        "advisory_only": "NO_EXECUTION",
        "human_confirmed_live": "CONFIRM_EVERY_TRADE",
        "autonomous_live": "STANDING_MANDATE",
    }[expected_mode]
    assert request.to_public_dict()["execution_authority"] is False


def test_negated_direct_action_remains_advisory_and_non_executable():
    plan, request = request_from(
        semantic(action="OPEN_POSITION", requested_mode="human_confirmed_live", negated=True)
    )

    assert plan.constraints["requested_mode"] == "advisory_only"
    assert request.requested_mode == "advisory_only"
    assert request.confirmation_policy == "NO_EXECUTION"
    assert request.to_public_dict()["execution_authority"] is False
    assert request.to_public_dict()["executable"] is False


def test_unmarked_autonomous_mode_evidence_cannot_override_direct_trade_policy():
    plan, request = request_from(semantic(requested_mode="autonomous_live"))

    assert plan.constraints["requested_mode_evidence"] == "autonomous_live"
    assert request.requested_mode == "human_confirmed_live"
    assert request.mandate_required is False


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
    source = semantic(
        primary_intent="POSITION_MANAGEMENT",
        indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
        unresolved_fields=["indicators[0].parameters.period"],
    )

    class RecordingExecutor:
        def __init__(self):
            self.calls = []

        def execute(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(results=[], task_context_views=[])

    executor = RecordingExecutor()
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.decision_context_builder = DecisionContextBuilder()
    orchestrator.router_module = RouterModule()
    orchestrator.context_acquisition_executor = executor
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
    assert artifacts["trading_request"]["executable"] is False
    assert artifacts["query_plan"]["primary_intent"] == "trade_opportunity_analysis"
    assert artifacts["query_plan"]["semantic_context"]["input"] == source.as_dict()
    assert executor.calls and executor.calls[0]["query_plan"].primary_intent == "trade_opportunity_analysis"
