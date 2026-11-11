import pytest

from scripts.test_structured_semantic_interpreter import interpreted, semantic_payload
from scripts.test_trading_semantic_cutover import request_from, semantic
from src.orchestrator import RAGOrchestrator
from src.pipelines.modules.router import RouterModule
from src.services.decision_context import DecisionContextBuilder
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import ResolvedSemanticState, resolve_structured_semantics
from src.services.semantic.structured_semantics import StructuredSemanticResult, StructuredSemanticValidationError
from src.services.trading.decision.conversational_authorization import project_conversational_trading_request
from src.ui import tab_chatbot


def goal_payload(**changes):
    goal = changes.get("research_goal", {"objective": "Seek weekly profitability", "horizon": "weekly"})
    return semantic_payload(
        **{
            "primary_intent": "STRATEGY_RESEARCH",
            "action": "ANALYZE",
            "direction": "",
            "indicators": [],
            "conditions": [],
            "account_scope": "DEMO",
            "requested_mode": "autonomous_live",
            "requested_data": ["market_data", "private_knowledge", "general_knowledge"],
            "research_goal": goal,
            "explicit_fields": ["requested_mode", "account_scope", "requested_data", "symbols[0]"]
            + [f"research_goal.{field}" for field in goal],
            "unresolved_fields": [],
            **changes,
        }
    )


@pytest.mark.parametrize("raw, changes", [
    ("Phân tích cách tạo lợi nhuận trên XAUUSD từ dữ liệu và tài liệu của tôi.", {"requested_mode": "advisory_only"}),
    ("Hãy tự trade XAUUSD sao cho mỗi tuần có lời.", {}),
    ("Research weekly gold returns on DEMO, risk no more than 1% per trade.", {
        "research_goal": {"objective": "Seek weekly profitability", "horizon": "weekly", "max_risk_per_trade_pct": 1},
    }),
    ("bot tự trade gold cho có lời mỗi tuần, dùng private docs nha", {}),
    ("Nếu bot tự kiếm lời mỗi tuần thì sao? Đừng giao dịch.", {"negated": True, "hypothetical": True}),
])
def test_research_terminates_before_trading_or_data_acquisition(raw, changes, monkeypatch):
    result, provider = interpreted(raw, goal_payload(**changes))
    assert result.is_valid
    assert len(provider.calls) == 1
    assert "STRATEGY_RESEARCH" in provider.calls[0][0]
    assert raw in provider.calls[0][0]

    def forbidden(*args, **kwargs):
        pytest.fail("research reached an operational boundary")

    builder = DecisionContextBuilder()
    monkeypatch.setattr(builder.requirement_planner, "plan", forbidden)
    monkeypatch.setattr("src.orchestrator.project_conversational_trading_request", forbidden)
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.router_module = RouterModule()
    orchestrator.decision_context_builder = builder
    orchestrator._interpret_structured_semantics = lambda _: result
    orchestrator._context_acquisition_executor = forbidden
    stream, sources, intent, artifacts = orchestrator.query_financial_advisor(raw)
    brief = artifacts["research_brief"]
    answer = "".join(stream)
    assert intent == "RESEARCH_BRIEF" and not sources
    assert brief["strategy_status"] == "STRATEGY_NOT_ESTABLISHED"
    assert brief["status"] == "RESEARCH_REQUIRED"
    assert brief["effective_mode"] == "advisory_only"
    assert brief["requested_mode"] == changes.get("requested_mode", "autonomous_live")
    assert brief["symbols"] == ["XAUUSD"] and brief["account_scope"] == "DEMO"
    assert brief["execution_allowed"] is False
    assert {"market_snapshot", "ohlcv", "static_knowledge", "market_knowledge"} == set(brief["research_capabilities"])
    assert "Trading is not authorized" in answer and "not a guarantee" in answer
    if "research_goal" in changes:
        assert brief["goal"]["max_risk_per_trade_pct"] == 1 and "1%" in answer
    assert "trading_request" not in artifacts
    assert tab_chatbot._trading_request_from_runtime_artifacts(
        artifacts, user_query=raw, conversation_id="research", messages=[]
    ) == (None, None)


def test_research_round_trip_and_explicit_followup_override():
    initial = resolve_structured_semantics(StructuredSemanticResult.from_payload(goal_payload(
        research_goal={"objective": "Seek profitability", "horizon": "weekly", "max_risk_per_trade_pct": 1},
    )))
    reloaded = ResolvedSemanticState.from_dict(initial.as_dict())
    followup = StructuredSemanticResult.from_payload(goal_payload(
        symbols=[], account_scope="", requested_mode="", requested_data=[],
        research_goal={"horizon": "monthly", "max_drawdown_pct": 5},
        explicit_fields=["research_goal.horizon"], context_references=["previous_research_goal"],
        unresolved_fields=["research_goal.max_risk_per_trade_pct"],
    ))
    plan = QueryPlanAssembler().assemble("Tiếp tục mục tiêu, đổi sang kỳ tháng",
                                         structured_semantics=followup, previous_structured_context=reloaded)
    brief = plan.constraints["research_brief"]
    assert brief["goal"]["horizon"] == "monthly"
    assert brief["goal"]["objective"] == "Seek profitability"
    assert "max_drawdown_pct" not in brief["goal"]
    assert "max_risk_per_trade_pct" not in brief["goal"]
    assert brief["missing_information"] == ["research_goal.max_risk_per_trade_pct"]
    assert brief["symbols"] == ["XAUUSD"]
    assert brief["field_sources"]["research_goal.objective"] == "CONVERSATION_INHERITED"
    assert brief["field_sources"]["research_goal.horizon"] == "USER_EXPLICIT"
    assert brief["requested_mode"] == ""
    assert project_conversational_trading_request(plan, conversation_id="research") is None


@pytest.mark.parametrize("risk", [True, "1%", -1, 101, float("inf")])
def test_goal_rejects_invalid_risk_values(risk):
    with pytest.raises(StructuredSemanticValidationError):
        StructuredSemanticResult.from_payload(goal_payload(research_goal={"max_risk_per_trade_pct": risk}))


def test_nested_authority_fields_are_rejected():
    with pytest.raises(StructuredSemanticValidationError):
        StructuredSemanticResult.from_payload(goal_payload(research_goal={"execution_allowed": True}))


def test_missing_strategy_blocks_mandate_even_in_legacy_structured_shape():
    _, request = request_from(semantic(
        action="NONE", direction="", indicators=[], conditions=[],
        requested_mode="autonomous_live", explicit_fields=["requested_mode"],
    ))
    assert request.strategy is None
    assert request.allowed_next_action == "BLOCKED"
    assert request.response_format != "STANDING_MANDATE_CARD"
    assert "STRATEGY_NOT_ESTABLISHED" in request.blockers


def test_research_history_does_not_resurface_an_old_trade_card():
    _, request = request_from(semantic())
    trade = {"role": "assistant", "trading_request": request.to_public_dict()}
    research = {"role": "assistant", "intent": "RESEARCH_BRIEF"}
    assert tab_chatbot._latest_trading_authorization([trade, research]) == (None, None)
    assert tab_chatbot._latest_trading_authorization([trade, research, trade])[0] == request


def test_unresolved_research_never_inherits_a_trade_or_invents_rules():
    previous = resolve_structured_semantics(semantic())
    source = StructuredSemanticResult.from_payload(goal_payload(
        action="OPEN_POSITION", direction="BUY",
        indicators=[{"indicator_id": "RSI"}],
        conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 50}],
        symbols=[], research_goal={}, explicit_fields=["requested_mode"],
        context_references=["previous_research_goal"],
        unresolved_fields=["indicators[0].parameters.period"],
    ))
    plan = QueryPlanAssembler().assemble("Continue the previous research goal",
                                         structured_semantics=source, previous_structured_context=previous)
    assert plan.semantic_context["conditions"] == plan.semantic_context["indicators"] == []
    assert plan.constraints["research_brief"]["missing_information"] == [
        "context_references.previous_research_goal", "research_goal.objective", "symbols",
    ]
    assert project_conversational_trading_request(plan, conversation_id="research") is None
