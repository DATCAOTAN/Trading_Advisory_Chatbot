from types import SimpleNamespace

import pytest

from src.orchestrator import RAGOrchestrator
from src.pipelines.modules.router import RouteAction, RouterModule
from src.services.decision_context import DecisionContextBuilder
from src.services.semantic.context_execution import ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.structured_semantics import SEMANTIC_SCHEMA_VERSION, StructuredSemanticResult


def semantic(**changes):
    payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "primary_intent": "KNOWLEDGE",
        "secondary_intents": [],
        "action": "EXPLAIN",
        "direction": "",
        "subtype": "",
        "domain": "",
        "symbols": [],
        "indicators": [],
        "requested_data": [],
        "conditions": [],
        "context_references": [],
        "requested_mode": "",
        "account_scope": "",
        "explicit_fields": [],
        "unresolved_fields": [],
        "negated": False,
        "hypothetical": False,
    }
    payload.update(changes)
    return StructuredSemanticResult.from_payload(payload)


def plan_and_requirements(source):
    plan = QueryPlanAssembler().assemble("raw wording must not route this request", structured_semantics=source)
    return plan, ContextRequirementPlanner().plan(plan)


@pytest.mark.parametrize(
    ("source", "expected", "absent"),
    [
        (
            semantic(subtype="RSI", domain="technical_analysis"),
            {"static_knowledge"},
            {"market_snapshot", "ohlcv", "technical_snapshot"},
        ),
        (
            semantic(
                primary_intent="MARKET_DATA",
                action="ANALYZE",
                symbols=["BTCUSD"],
                indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
                requested_data=["current_indicator_value"],
            ),
            {"market_snapshot", "ohlcv", "technical_snapshot"},
            {"static_knowledge", "official_report", "market_knowledge"},
        ),
        (
            semantic(subtype="CPI", domain="macro"),
            {"official_report"},
            {"market_snapshot", "ohlcv", "technical_snapshot", "economic_event"},
        ),
        (
            semantic(
                primary_intent="ANALYSIS",
                secondary_intents=["KNOWLEDGE"],
                action="ANALYZE",
                subtype="CPI",
                domain="macro",
                symbols=["XAUUSD"],
                indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"}],
            ),
            {"official_report", "economic_event", "market_snapshot", "ohlcv", "technical_snapshot"},
            set(),
        ),
    ],
)
def test_structured_semantics_route_capabilities_without_raw_keyword_branches(source, expected, absent):
    plan, requirements = plan_and_requirements(source)
    capabilities = {need.capability for need in requirements.needs}

    assert expected <= capabilities
    assert not (absent & capabilities)
    assert len([need.key() for need in requirements.needs]) == len({need.key() for need in requirements.needs})
    assert plan.requires_execution is False
    assert plan.constraints["execution_allowed"] is False


def test_partial_indicator_semantics_stay_unresolved_without_inventing_a_period():
    plan, requirements = plan_and_requirements(
        semantic(
            primary_intent="MARKET_DATA",
            action="ANALYZE",
            symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}],
            unresolved_fields=["indicators[0].parameters.period"],
        )
    )

    assert plan.entities.symbols == ["BTCUSD"]
    assert plan.entities.timeframes == ["M1"]
    assert plan.requested_indicators == []
    assert "unresolved:indicators[0].parameters.period" in plan.ambiguity
    assert "technical_snapshot" in {need.capability for need in requirements.needs}
    assert all(need.required is False for need in requirements.needs if need.capability == "technical_snapshot")


def test_requested_mode_does_not_change_information_requirements_or_execution_permission():
    base = semantic(
        primary_intent="MARKET_DATA",
        action="ANALYZE",
        symbols=["BTCUSD"],
        indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
    )
    advisory_plan, advisory_requirements = plan_and_requirements(base)
    autonomous_plan, autonomous_requirements = plan_and_requirements(
        semantic(
            primary_intent="MARKET_DATA",
            action="ANALYZE",
            symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
            requested_mode="autonomous_live",
        )
    )

    assert {need.key() for need in advisory_requirements.needs} == {need.key() for need in autonomous_requirements.needs}
    assert advisory_plan.constraints["execution_allowed"] is False
    assert autonomous_plan.constraints["execution_allowed"] is False


def test_structured_social_uses_cheap_exit_without_legacy_router_call(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy router called")

    monkeypatch.setattr("src.pipelines.modules.router.OldIntentRouter.classify", unexpected)

    action, response = RouterModule.process_structured("SOCIAL", "hello")

    assert action == RouteAction.EARLY_EXIT
    assert response is not None


def test_retrieval_rewrite_is_capability_driven():
    _, knowledge_requirements = plan_and_requirements(semantic(subtype="RSI"))
    _, market_requirements = plan_and_requirements(
        semantic(
            primary_intent="MARKET_DATA",
            action="ANALYZE",
            symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "M1"}],
        )
    )

    assert RAGOrchestrator._requires_retrieval_rewrite(knowledge_requirements) is True
    assert RAGOrchestrator._requires_retrieval_rewrite(market_requirements) is False


def test_decision_context_reuses_authoritative_plan_without_raw_reparsing():
    class UnexpectedRawParser:
        def route(self, *_args):
            raise AssertionError("legacy router called")

        def classify(self, *_args):
            raise AssertionError("legacy answer-mode classifier called")

        def decompose(self, *_args):
            raise AssertionError("legacy decomposer called")

    plan, requirements = plan_and_requirements(semantic(subtype="RSI"))
    parser = UnexpectedRawParser()
    builder = DecisionContextBuilder(
        intent_router=parser,
        answer_mode_classifier=parser,
        query_plan_assembler=QueryPlanAssembler(parser, parser, parser),
    )
    execution_plan = ContextExecutionPlanner(builder.capability_registry).plan(requirements)

    context = builder.build(
        original_query="legacy wording must not be reparsed",
        query_plan=plan,
        context_requirements=requirements,
        context_execution_plan=execution_plan,
        acquisition_batch_result=SimpleNamespace(results=[], task_context_views=[]),
    )

    assert context.query_plan["plan_id"] == plan.plan_id
    assert context.answer_mode["reason"] == "validated structured semantic projection"


def test_legacy_query_plan_fallback_remains_available_without_structured_semantics():
    plan = QueryPlanAssembler().assemble("What is RSI?")

    assert plan.semantic_context == {}
    assert plan.primary_intent == "book_concept_explanation"
