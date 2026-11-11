import itertools
import json

import pytest

from scripts.test_structured_semantic_interpreter import ScriptedProvider, interpreted, semantic_payload
from src.config import Config
from src.orchestrator import RAGOrchestrator, _computational_specification_message
from src.pipelines.modules.router import RouterModule
from src.services.decision_context import DecisionContextBuilder
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import (
    ResolvedSemanticState, SemanticCompletionPatch, SemanticFieldUpdate, apply_semantic_completion,
)
from src.services.semantic.structured_interpreter import StructuredSemanticInterpreter
from src.services.semantic.structured_semantics import (
    AUTHORIZATION_MODE_MAP, COMPUTATIONAL_SPEC_FIELD, COMPUTATIONAL_SPEC_REFERENCE,
    StructuredSemanticResult, StructuredSemanticValidationError,
)
from src.services.trading.decision.conversational_authorization import project_conversational_trading_request
from src.services.trading.reasoning.strategy_evidence import project_resolved_semantic_strategy
from src.ui import tab_chatbot


FIELD = COMPUTATIONAL_SPEC_FIELD
RAW = "Specify a hysteretic price-volume estimator and use its retained state for re-entry."
SPEC = {
    "objective": "Retain price-volume pressure across flat bars",
    "algorithm": "Hysteretic price-volume estimator",
    "formula": "x[t] = alpha*x[t-1] + (1-alpha)*(close[t]-open[t])*sqrt(volume[t])",
    "steps": ["Read the closed M1 bar.", "Reset on session open; otherwise retain prior state."],
    "temporal_requirements": ["Only update once per closed bar.", "Clear state after a session break."],
    "parameters": [
        {"name": "alpha", "definition": "state retention", "value": 0.6, "minimum": 0, "maximum": 1, "unit": "fraction"},
        {"name": "offset", "value": "0.012500", "unit": "price"},
    ],
    "data_requirements": [
        {"dataset": "OHLCV", "fields": ["open", "close", "volume"], "symbol": "XAUUSD",
         "timeframe": "M1", "lookback_bars": 100, "warmup_bars": 40, "max_age_seconds": 75,
         "completeness": "No gaps in the current session", "usage": "EXECUTION_RELEVANT"},
        {"dataset": "OHLCV", "fields": ["close"], "symbol": "XAUUSD",
         "timeframe": "H1", "lookback_bars": 20, "warmup_bars": 0, "usage": "RESEARCH_ONLY"},
    ],
    "outputs": [{"name": "pressure", "unit": "score", "validity": "Finite; invalid before warm-up"}],
    "entry": ["pressure crosses zero", "H1 slope is positive"],
    "exit": ["pressure remains negative for three closed bars", "or session closes"],
    "reentry": ["Require a full reset after exit"],
    "management": ["Do not widen SL"],
}


def payload(spec=SPEC, *, explicit=None, **changes):
    if explicit is None:
        explicit = [f"{FIELD}.{name}" for name in spec if name != "configuration"]
        explicit += [f"{FIELD}.configuration.{axis}" for axis in spec.get("configuration", {})]
    return semantic_payload(**{
        "computational_specification": spec,
        "explicit_fields": explicit,
        "unresolved_fields": [],
        **changes,
    })


def assemble(source, previous=None):
    return QueryPlanAssembler().assemble(RAW, structured_semantics=source, previous_structured_context=previous)


def reload_state(plan):
    encoded = json.dumps(plan.as_dict())
    return ResolvedSemanticState.from_dict(json.loads(encoded)["semantic_context"])


def test_round_trip_novel_temporal_algorithm_preserves_rules_and_typed_mtf_data():
    result, provider = interpreted(RAW, payload())
    assert result.is_valid and len(provider.calls) == 1
    assert provider.calls[0][1] == Config.TRADING_REASONING_MAX_TOKENS
    plan = assemble(result.semantic)
    restored = reload_state(plan)
    assert plan.original_query == RAW
    assert restored.semantic.computational_specification.as_dict() == {
        "schema_version": "computational-specification/v1", **SPEC,
    }
    assert restored.semantic.computational_specification == plan.computational_specification
    summary = plan.constraints[FIELD]
    assert summary["specification_id"] == restored.semantic.computational_specification.specification_id
    assert summary["status"] == "SPECIFIED"
    assert summary["runtime_status"] == "UNSUPPORTED_DYNAMIC_COMPUTATION"
    assert summary["data_assessments"] == [
        {"availability": "NOT_CHECKED", "freshness": "NOT_CHECKED", "completeness": "NOT_CHECKED"}
    ] * 2
    assert dict(restored.field_sources)[f"{FIELD}.parameters[1].unit"] == "USER_EXPLICIT"
    assert not DecisionContextBuilder().requirement_planner.plan(plan).needs


@pytest.mark.parametrize("origin, mode, adaptation", tuple(itertools.product(
    ("USER_DEFINED", "AI_RESEARCHED"),
    ("ADVISORY", "HUMAN_CONFIRMED", "AUTONOMOUS"),
    ("FIXED", "ADAPTIVE_WITHIN_SCOPE", "RESEARCH_AND_REQUEST_APPROVAL"),
)))
def test_axes_are_independent_intent_never_authority(origin, mode, adaptation):
    axes = {"strategy_origin": origin, "authorization_mode": mode, "adaptation_policy": adaptation}
    plan = assemble(StructuredSemanticResult.from_payload(payload({**SPEC, "configuration": axes}, requested_mode="")))
    assert plan.computational_specification.configuration.model_dump() == axes
    assert plan.constraints["requested_mode"] == AUTHORIZATION_MODE_MAP[mode]
    assert plan.constraints["effective_mode"] == "advisory_only"
    assert not plan.requires_execution and not plan.constraints["execution_allowed"]
    assert project_conversational_trading_request(plan, conversation_id="g1") is None


def test_missing_conflicting_and_suggested_facts_are_distinct():
    path = f"{FIELD}.configuration.authorization_mode"
    spec = {"algorithm": "X", "configuration": {"authorization_mode": "AUTONOMOUS"},
            "parameters": [{"name": "alpha", "value": 2, "minimum": 0, "maximum": 1}]}
    plan = assemble(StructuredSemanticResult.from_payload(payload(spec, explicit=[
        f"{FIELD}.algorithm", f"{FIELD}.parameters[0].name",
    ], unresolved_fields=[f"{FIELD}.parameters[0].unit", f"{FIELD}.configuration.strategy_origin"])))
    summary = plan.constraints[FIELD]
    assert summary["status"] == "NEEDS_CLARIFICATION"
    assert {f"{FIELD}.formula_or_steps", f"{FIELD}.data_requirements"} <= set(summary["missing_information"])
    assert summary["conflicting_fields"] == [f"{FIELD}.parameters[0].range"]
    assert summary["configuration_status"] == {
        "strategy_origin": "UNRESOLVED", "authorization_mode": "LLM_SUGGESTION", "adaptation_policy": "UNSPECIFIED",
    }
    assert plan.constraints["requested_mode"] == ""
    sources = dict(reload_state(plan).field_sources)
    assert sources[path] == "LLM_SUGGESTION"
    assert sources[f"{FIELD}.parameters[0].name"] == "USER_EXPLICIT"
    assert sources[f"{FIELD}.parameters[0].unit"] == "UNRESOLVED"
    assert plan.computational_specification.parameters[0].value == 2


def test_explicit_inheritance_and_trusted_confirmation_do_not_invent_siblings():
    path = f"{FIELD}.configuration.adaptation_policy"
    spec = {**SPEC, "configuration": {"adaptation_policy": "FIXED"}}
    state = reload_state(assemble(StructuredSemanticResult.from_payload(payload(
        spec, explicit=[f"{FIELD}.{name}" for name in SPEC],
    ))))
    with pytest.raises(ValueError, match="COMPUTATIONAL_SUGGESTION_MISMATCH"):
        apply_semantic_completion(state, SemanticCompletionPatch((
            SemanticFieldUpdate(path, "ADAPTIVE_WITHIN_SCOPE", "USER_CONFIRMED_SUGGESTION"),
        )))
    confirmed = apply_semantic_completion(state, SemanticCompletionPatch((
        SemanticFieldUpdate(path, "FIXED", "USER_CONFIRMED_SUGGESTION"),
    )))
    assert dict(state.field_sources)[path] == "LLM_SUGGESTION"
    assert dict(confirmed.field_sources)[path] == "USER_CONFIRMED_SUGGESTION"
    confirmed = ResolvedSemanticState.from_dict(json.loads(json.dumps(confirmed.as_dict())))
    followup = StructuredSemanticResult.from_payload(payload(
        {"formula": "new expression", "configuration": {"authorization_mode": "HUMAN_CONFIRMED"}},
        context_references=[COMPUTATIONAL_SPEC_REFERENCE], requested_mode="",
    ))
    plan = assemble(followup, confirmed)
    assert plan.computational_specification.formula == "new expression"
    assert plan.computational_specification.configuration.model_dump() == {
        "strategy_origin": None, "authorization_mode": "HUMAN_CONFIRMED", "adaptation_policy": "FIXED",
    }
    assert dict(reload_state(plan).field_sources)[path] == "CONVERSATION_INHERITED"
    assert plan.computational_specification.specification_id != state.semantic.computational_specification.specification_id
    without_ref = assemble(StructuredSemanticResult.from_payload(payload({"algorithm": "Different"})), confirmed)
    assert without_ref.computational_specification.configuration is None
    assert without_ref.computational_specification.formula is None


def test_partial_data_and_parameter_rows_preserve_values_and_mark_missing_children():
    plan = assemble(StructuredSemanticResult.from_payload(payload({
        **SPEC,
        "parameters": [{"value": 0, "unit": "price"}],
        "data_requirements": [{"symbol": "XAUUSD", "timeframe": "M15", "fields": ["close"]}],
        "outputs": [{"validity": "finite"}],
    })))
    assert plan.computational_specification.parameters[0].value == 0
    assert plan.computational_specification.data_requirements[0].timeframe == "M15"
    assert plan.computational_specification.outputs[0].validity == "finite"
    assert plan.constraints[FIELD]["missing_information"] == [
        f"{FIELD}.parameters[0].name", f"{FIELD}.data_requirements[0].dataset",
        f"{FIELD}.data_requirements[0].usage", f"{FIELD}.outputs[0].name",
    ]


def test_reference_only_without_prior_spec_does_not_fall_through_to_legacy():
    source = StructuredSemanticResult.from_payload(semantic_payload(
        context_references=[COMPUTATIONAL_SPEC_REFERENCE], unresolved_fields=[],
    ))
    plan = assemble(source)
    assert plan.constraints[FIELD]["status"] == "NEEDS_CLARIFICATION"
    assert f"context_references.{COMPUTATIONAL_SPEC_REFERENCE}" in plan.constraints[FIELD]["missing_information"]
    assert not plan.requested_indicators
    assert project_conversational_trading_request(plan, conversation_id="g1") is None


def test_conflicting_authorization_requests_are_reported_without_a_mapping():
    spec = {**SPEC, "configuration": {"authorization_mode": "AUTONOMOUS"}}
    explicit = [f"{FIELD}.configuration.authorization_mode", "requested_mode"]
    plan = assemble(StructuredSemanticResult.from_payload(payload(
        spec, explicit=explicit, requested_mode="human_confirmed_live",
    )))
    assert plan.constraints[FIELD]["configuration_status"]["authorization_mode"] == "CONFLICTING"
    assert plan.constraints[FIELD]["conflicting_fields"] == [f"{FIELD}.configuration.authorization_mode"]
    assert plan.constraints["requested_mode"] == "" and not plan.requires_execution
    answer = _computational_specification_message(plan)
    _, _, dispute = answer.partition("**Conflicting or ambiguous requirements**")
    assert "authorization mode: AUTONOMOUS" in dispute and r"human\_confirmed\_live" in dispute


@pytest.mark.parametrize("extra", [
    {"executable": True},
    {"configuration": {"strategy_origin": "SYSTEM_PROPOSED"}},
    {"data_requirements": [{"dataset": "OHLCV", "availability": "AVAILABLE"}]},
    {"schema_version": "computational-specification/v99"},
])
def test_nested_payload_cannot_claim_authority_or_data_evidence(extra):
    with pytest.raises(StructuredSemanticValidationError, match="COMPUTATIONAL_SPECIFICATION_INVALID"):
        StructuredSemanticResult.from_payload(payload({**SPEC, **extra}))


def test_dynamic_projection_stops_before_legacy_strategy_or_acquisition(monkeypatch):
    # The base fixture includes a valid RSI rule and OPEN_POSITION; neither may become a fallback.
    result, provider = interpreted(RAW, payload())
    plan = assemble(result.semantic)
    assert not plan.requested_indicators
    assert project_resolved_semantic_strategy(
        plan.semantic_context, canonical_symbol="XAUUSD", requested_mode="autonomous_live",
        confirmation_policy="STANDING_MANDATE", account_scope="DEMO", request_id="g1",
    ) is None
    builder = DecisionContextBuilder()

    def forbidden(*_args, **_kwargs):
        pytest.fail("specification reached an operational boundary")

    monkeypatch.setattr(builder.requirement_planner, "plan", forbidden)
    monkeypatch.setattr("src.orchestrator.project_conversational_trading_request", forbidden)
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.router_module = RouterModule()
    orchestrator.decision_context_builder = builder
    orchestrator._interpret_structured_semantics = lambda _: result
    orchestrator._context_acquisition_executor = forbidden
    stream, sources, intent, artifacts = orchestrator.query_financial_advisor(RAW)
    assert intent == "COMPUTATIONAL_SPECIFICATION" and not sources
    answer = "".join(stream)
    assert "trading is not authorized" in answer
    assert "Specified for review. Not ready to run." in answer
    assert "Hysteretic price-volume estimator" in answer
    assert "value: 0.6; minimum: 0; maximum: 1; unit: fraction" in answer
    assert "timeframe: H1; lookback bars: 20; warmup bars: 0" in answer
    assert "Require a full reset after exit" in answer
    assert "**Missing information**" not in answer and "?" not in answer
    assert "SPECIFICATION REVIEW" in tab_chatbot._render_badge(intent)
    assert artifacts["query_plan"]["constraints"]["execution_allowed"] is False
    assert artifacts["provider_calls"] == len(provider.calls) == 1
    assert artifacts["retrieval_rewrite_calls"] == 0
    assert "trading_request" not in artifacts
    assert tab_chatbot._trading_request_from_runtime_artifacts(
        artifacts, user_query=RAW, conversation_id="g1", messages=[],
    ) == (None, None)
    legacy = project_conversational_trading_request(
        assemble(StructuredSemanticResult.from_payload(semantic_payload())), conversation_id="g1",
    )
    messages = [{"trading_request": legacy.to_public_dict()}]
    assert tab_chatbot._latest_trading_authorization(messages)[0] is not None
    assert tab_chatbot._latest_trading_authorization([*messages, {"intent": intent}]) == (None, None)


def test_specification_review_keeps_known_siblings_and_questions_only_missing_fields():
    partial = {**SPEC, "parameters": [{"name": "offset", "value": 0, "unit": "price"}],
               "data_requirements": [{"dataset": "OHLCV", "fields": ["close"], "symbol": "XAUUSD",
                                      "usage": "RESEARCH_ONLY", "lookback_bars": 100}]}
    source = StructuredSemanticResult.from_payload(payload(
        partial, unresolved_fields=[f"{FIELD}.parameters[0].unit"],
    ))
    answer = _computational_specification_message(assemble(source))
    assert "Clarification needed" in answer
    assert "name: offset; value: 0" in answer
    assert "unit: price" not in answer
    assert "What is the parameter 1 unit?" in answer
    assert "What is the data requirement 1 timeframe?" in answer
    assert answer.count("?") == 2


def test_specification_review_separates_disputed_values_and_reports_unsupported_requirements():
    conflicting = {**SPEC, "parameters": [{"name": "alpha", "value": 2, "minimum": 0, "maximum": 1}],
                   "conflicts": ["Update on both bar open and bar close"],
                   "unsupported": ["Cross-venue order flow"]}
    answer = _computational_specification_message(assemble(StructuredSemanticResult.from_payload(payload(conflicting))))
    recorded, _, dispute = answer.partition("**Conflicting or ambiguous requirements**")
    assert "name: alpha" in recorded and "value: 2" not in recorded
    assert "value: 2; minimum: 0; maximum: 1" in dispute
    assert "What value and bounds should parameter 1 use?" in dispute
    assert "Update on both bar open and bar close" in dispute
    assert "**Unsupported requirements**\n- Cross-venue order flow" in dispute


def test_specification_review_never_promotes_unconfirmed_values_or_renders_active_markdown():
    spec = {**SPEC, "formula": "![remote](https://example.invalid/image)\n**fake heading**"}
    source = StructuredSemanticResult.from_payload(payload(
        spec, explicit=[f"{FIELD}.{name}" for name in SPEC if name != "formula"],
    ))
    answer = _computational_specification_message(assemble(source))
    confirmed, _, suggestions = answer.partition("**Unconfirmed values**")
    assert "Review needed" in confirmed and "fake heading" not in confirmed
    assert "remote" in suggestions and "![remote]" not in suggestions
    assert "**fake heading**" not in suggestions
    assert "**Missing information**" not in answer and "?" not in answer


def test_empty_specification_and_stale_reference_never_borrow_a_previous_specification():
    old = reload_state(assemble(StructuredSemanticResult.from_payload(payload())))
    empty = assemble(StructuredSemanticResult.from_payload(payload({})), old)
    answer = _computational_specification_message(empty)
    assert "None recorded." in answer and "What is the formula or steps?" in answer
    assert "Hysteretic" not in answer and "Do not widen SL" not in answer

    reference = StructuredSemanticResult.from_payload(semantic_payload(
        context_references=[COMPUTATIONAL_SPEC_REFERENCE], unresolved_fields=[],
    ))
    assert "What is the previous specification in this conversation?" in _computational_specification_message(
        assemble(reference),
    )
    inherited = _computational_specification_message(assemble(reference, old))
    assert "Hysteretic price-volume estimator (from this conversation)" in inherited


def test_ordinary_turn_does_not_show_a_specification_from_previous_context():
    old = reload_state(assemble(StructuredSemanticResult.from_payload(payload())))
    result, _ = interpreted("Hello", semantic_payload(primary_intent="SOCIAL", action="NONE"))
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.router_module = RouterModule()
    orchestrator._interpret_structured_semantics = lambda _: result
    stream, _, intent, artifacts = orchestrator.query_financial_advisor("Hello", previous_structured_context=old)
    assert intent == "EARLY_EXIT" and "Hysteretic" not in "".join(stream)
    assert "query_plan" not in artifacts


@pytest.mark.parametrize("old_intent", ["COMPUTATIONAL_SPECIFICATION", "FINANCIAL_RAG"])
def test_streamlit_fallback_to_existing_conversation_reloads_history(monkeypatch, old_intent):
    from streamlit.testing.v1 import AppTest
    from src.services import history_service
    from src.ui import tab_dashboard, tab_evaluation_dashboard, tab_settings

    old_plan = assemble(StructuredSemanticResult.from_payload(payload()))
    old_trade = project_conversational_trading_request(
        assemble(StructuredSemanticResult.from_payload(semantic_payload())), conversation_id="deleted",
    )
    old = {"role": "assistant", "intent": old_intent, "content": "Old conversation only"}
    if old_intent == "COMPUTATIONAL_SPECIFICATION":
        old["resolved_semantic_state"] = old_plan.semantic_context
    else:
        old["trading_request"] = old_trade.to_public_dict()
    loaded = []
    appended = []

    class History:
        def get_all_sessions(self):
            return [{"_id": "replacement", "title": "Replacement"}]

        def load_history(self, session_id):
            loaded.append(session_id)
            return [{"role": "assistant", "content": "Replacement conversation only"}]

        def append_message(self, session_id, message, **kwargs):
            appended.append((session_id, message))

    monkeypatch.setattr(history_service, "HistoryService", History)
    monkeypatch.setattr(tab_chatbot, "record_journal_review", lambda *_, **__: None)
    monkeypatch.setattr(tab_chatbot, "_render_conversational_trading_authorization",
                        lambda *_: pytest.fail("stale trade card rendered"))
    for tab in (tab_dashboard, tab_evaluation_dashboard, tab_settings):
        monkeypatch.setattr(tab, "render", lambda *_: None)
    provider = ScriptedProvider(json.dumps(payload(
        {"algorithm": "New calculation"}, context_references=[COMPUTATIONAL_SPEC_REFERENCE],
    )))
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.router_module = RouterModule()
    orchestrator.decision_context_builder = DecisionContextBuilder()
    orchestrator.structured_semantic_interpreter = StructuredSemanticInterpreter(provider)
    app = AppTest.from_file("src/app.py")
    app.session_state["current_session_id"] = "deleted"
    app.session_state["messages"] = [old]
    app.session_state["orchestrator"] = orchestrator
    app.run()
    assert not app.exception
    assert loaded == ["replacement"]
    assert app.session_state["current_session_id"] == "replacement"
    messages = app.session_state["messages"]
    assert [message["content"] for message in messages] == ["Replacement conversation only"]
    assert tab_chatbot._latest_resolved_semantic_state(messages) is None
    assert tab_chatbot._latest_trading_authorization(messages) == (None, None)
    app.chat_input[0].set_value("Continue the previous computation with a new calculation").run()
    assert not app.exception and not app.error and len(provider.calls) == 1
    assert [session_id for session_id, _ in appended] == ["replacement", "replacement"]
    _, answer = appended[-1]
    assert answer["intent"] == "COMPUTATIONAL_SPECIFICATION"
    assert "New calculation" in answer["content"] and "previous specification in this conversation" in answer["content"]
    assert "Hysteretic" not in answer["content"] and "trading_request" not in answer
    assert any("Computational specification review" in node.value for node in app.markdown)


def test_legacy_strategy_does_not_emit_optional_spec_or_change_identity_on_reload():
    source = StructuredSemanticResult.from_payload(semantic_payload())
    plan = assemble(source)
    assert FIELD not in source.as_dict() and FIELD not in plan.constraints
    request = project_conversational_trading_request(plan, conversation_id="legacy")
    assert request.strategy.indicators[0].indicator_id == "RSI"
    identity = request.strategy.identity
    again = assemble(reload_state(plan).semantic)
    assert project_conversational_trading_request(again, conversation_id="legacy").strategy.identity == identity


def _completion_subject(spec, *, unresolved=(), **changes):
    source = StructuredSemanticResult.from_payload(payload(spec, unresolved_fields=list(unresolved), **changes))
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.decision_context_builder = DecisionContextBuilder()
    return orchestrator, reload_state(assemble(source))


def test_typed_completion_updates_only_one_field_and_rerenders_canonical_review():
    timeframe, value = f"{FIELD}.data_requirements[0].timeframe", f"{FIELD}.parameters[0].value"
    data = [{key: item for key, item in SPEC["data_requirements"][0].items() if key != "timeframe"}]
    parameters = [{"name": "alpha", "minimum": 0, "maximum": 1}, SPEC["parameters"][1]]
    subject, state = _completion_subject({**SPEC, "data_requirements": data, "parameters": parameters}, unresolved=[value])
    fields, unsupported = subject.computational_specification_completion_fields(state)
    assert set(fields) == {timeframe, value} and not unsupported
    assert "H1" in fields[timeframe][1]
    message = subject.complete_computational_specification(state, timeframe, "H1")
    updated = ResolvedSemanticState.from_dict(message["resolved_semantic_state"])
    expected = state.semantic.computational_specification.as_dict()
    expected["data_requirements"][0]["timeframe"] = "H1"
    assert updated.semantic.computational_specification.as_dict() == expected
    assert dict(updated.field_sources) == {**dict(state.field_sources), timeframe: "USER_EXPLICIT"}
    assert "timeframe: H1" in message["content"] and "What is the parameter 1 value?" in message["content"]
    assert subject.computational_specification_completion_fields(updated)[0].keys() == {value}

    message = subject.complete_computational_specification(updated, value, "0")
    completed = ResolvedSemanticState.from_dict(message["resolved_semantic_state"])
    plan = QueryPlanAssembler().assemble_resolved(RAW, completed)
    assert plan.computational_specification.parameters[0].value == 0
    assert plan.constraints[FIELD]["status"] == "SPECIFIED"
    assert plan.constraints[FIELD]["data_assessments"][0]["availability"] == "NOT_CHECKED"
    assert not plan.constraints["execution_allowed"] and not plan.requires_execution
    assert project_conversational_trading_request(plan, conversation_id="complete") is None
    assert subject.computational_specification_completion_fields(completed) == ({}, [])
    assert "Specified for review. Not ready to run." in message["content"]
    with pytest.raises(ValueError, match="no longer missing"):
        subject.complete_computational_specification(completed, value, "0")


@pytest.mark.parametrize(("answer", "reason"), [
    ("", "Enter a value"), ("0.2 or 0.3", "one JSON"), ("null", "not a list, object, or null"),
    ("NaN", "finite number"), ('"0.5"', "numeric bounds"), ("true", "numeric bounds"),
    ("2", "outside"), ("-1", "outside"),
])
def test_typed_parameter_completion_rejects_bad_or_ambiguous_answers(answer, reason):
    field = f"{FIELD}.parameters[0].value"
    subject, state = _completion_subject(
        {**SPEC, "parameters": [{"name": "alpha", "minimum": 0, "maximum": 1}]}, unresolved=[field],
    )
    with pytest.raises(ValueError, match=reason):
        subject.complete_computational_specification(state, field, answer)
    assert state.semantic.computational_specification.parameters[0].value is None
    assert field in state.unresolved_fields


def test_typed_completion_honors_enum_and_contextual_conflict_without_granting_mode():
    field = f"{FIELD}.configuration.authorization_mode"
    subject, state = _completion_subject(
        SPEC, unresolved=[field], requested_mode="human_confirmed_live",
        explicit=[*(f"{FIELD}.{name}" for name in SPEC), "requested_mode"],
    )
    assert "AUTONOMOUS" in subject.computational_specification_completion_fields(state)[0][field][1]
    with pytest.raises(ValueError, match="supported values"):
        subject.complete_computational_specification(state, field, "autonomous or human")
    with pytest.raises(ValueError, match="conflicts with recorded requirements"):
        subject.complete_computational_specification(state, field, "AUTONOMOUS")
    assert state.semantic.computational_specification.configuration is None
    message = subject.complete_computational_specification(state, field, "HUMAN_CONFIRMED")
    plan = QueryPlanAssembler().assemble_resolved(RAW, ResolvedSemanticState.from_dict(message["resolved_semantic_state"]))
    assert plan.constraints["requested_mode"] == "human_confirmed_live"
    assert plan.constraints["effective_mode"] == "advisory_only"
    assert not plan.constraints["execution_allowed"] and "trading_request" not in message


def test_unsupported_missing_leaf_is_not_offered_or_written():
    field = f"{FIELD}.data_requirements[0].completeness"
    subject, state = _completion_subject(SPEC, unresolved=[field])
    fields, unsupported = subject.computational_specification_completion_fields(state)
    assert field not in fields and unsupported == ["data requirement 1 completeness"]
    with pytest.raises(ValueError, match="not supported"):
        subject.complete_computational_specification(state, field, "100")


def _ohlcv_completion_subject(*keys):
    first = {key: value for key, value in SPEC["data_requirements"][0].items() if key not in keys}
    return _completion_subject(
        {**SPEC, "data_requirements": [first, SPEC["data_requirements"][1]]},
        unresolved=[f"{FIELD}.data_requirements[0].{key}" for key in keys if key != "lookback_bars"],
    )


def test_ohlcv_counts_complete_independently_and_preserve_requirement_identity():
    subject, state = _ohlcv_completion_subject("lookback_bars", "warmup_bars")
    lookback, warmup = (f"{FIELD}.data_requirements[0].{key}" for key in ("lookback_bars", "warmup_bars"))
    assert subject.computational_specification_completion_fields(state) == ({
        warmup: ("Data requirement 1 warmup bars", ()), lookback: ("Data requirement 1 lookback bars", ()),
    }, [])
    initial = state.semantic.computational_specification.as_dict()
    message = subject.complete_computational_specification(state, lookback, "1")
    updated = ResolvedSemanticState.from_dict(message["resolved_semantic_state"])
    expected = {**initial, "data_requirements": [{**initial["data_requirements"][0], "lookback_bars": 1},
                                                  initial["data_requirements"][1]]}
    assert updated.semantic.computational_specification.as_dict() == expected
    assert dict(updated.field_sources) == {**dict(state.field_sources), lookback: "USER_EXPLICIT"}
    assert subject.computational_specification_completion_fields(updated)[0].keys() == {warmup}
    with pytest.raises(ValueError, match="no longer missing"):
        subject.complete_computational_specification(updated, lookback, "2")

    # The specification does not impose a lookback/warmup ordering.
    message = subject.complete_computational_specification(updated, warmup, "40")
    final = ResolvedSemanticState.from_dict(message["resolved_semantic_state"])
    expected["data_requirements"][0]["warmup_bars"] = 40
    assert final.semantic.computational_specification.as_dict() == expected
    assert dict(final.field_sources) == {**dict(updated.field_sources), warmup: "USER_EXPLICIT"}
    assert state.semantic.computational_specification.as_dict() == initial
    plan = QueryPlanAssembler().assemble_resolved(RAW, final)
    assert plan.constraints[FIELD]["specification_id"] == final.semantic.computational_specification.specification_id
    assert plan.constraints[FIELD]["status"] == "SPECIFIED"
    assert plan.constraints[FIELD]["data_assessments"][0]["availability"] == "NOT_CHECKED"
    assert not plan.constraints["execution_allowed"] and not plan.requires_execution
    assert project_conversational_trading_request(plan, conversation_id="coverage") is None
    assert "lookback bars: 1" in message["content"] and "warmup bars: 40" in message["content"]


@pytest.mark.parametrize(("key", "value"), [
    ("lookback_bars", 1), ("warmup_bars", 0),
    ("lookback_bars", (1 << 63) - 1), ("warmup_bars", (1 << 63) - 1),
    ("max_age_seconds", 1), ("max_age_seconds", (1 << 63) - 1),
])
def test_ohlcv_integer_boundaries_remain_integers_and_fit_persistence(key, value):
    from bson import BSON

    subject, state = _ohlcv_completion_subject(key)
    message = subject.complete_computational_specification(state, f"{FIELD}.data_requirements[0].{key}", str(value))
    stored = BSON.encode(message).decode()["resolved_semantic_state"]
    count = getattr(ResolvedSemanticState.from_dict(stored).semantic.computational_specification.data_requirements[0], key)
    assert type(count) is int and count == value


@pytest.mark.parametrize(("key", "answer", "reason"), [
    ("lookback_bars", "", "Enter a value"),
    ("lookback_bars", "0", "greater than 0"),
    ("lookback_bars", "-1", "greater than 0"),
    ("warmup_bars", "-1", "greater than or equal to 0"),
    ("lookback_bars", "1.0", "whole number"),
    ("warmup_bars", "0.5", "whole number"),
    ("lookback_bars", "true", "whole number"),
    ("warmup_bars", '"0"', "whole number"),
    ("warmup_bars", "1e2", "whole number"),
    ("lookback_bars", "10 or 20", "whole number"),
    ("lookback_bars", "10 bars", "whole number"),
    ("lookback_bars", str(1 << 63), "64-bit"),
    ("warmup_bars", str(1 << 63), "64-bit"),
    ("max_age_seconds", "", "Enter a value"),
    ("max_age_seconds", "0", "greater than 0"),
    ("max_age_seconds", "-1", "greater than 0"),
    ("max_age_seconds", "1.5", "whole number of seconds"),
    ("max_age_seconds", "true", "whole number of seconds"),
    ("max_age_seconds", '"75"', "whole number of seconds"),
    ("max_age_seconds", "7e1", "whole number of seconds"),
    ("max_age_seconds", "75 seconds", "whole number of seconds"),
    ("max_age_seconds", "60 or 75", "whole number of seconds"),
    ("max_age_seconds", str(1 << 63), "64-bit"),
])
def test_invalid_ohlcv_integer_does_not_change_the_specification(key, answer, reason):
    subject, state = _ohlcv_completion_subject(key)
    field = f"{FIELD}.data_requirements[0].{key}"
    original = state.as_dict()
    with pytest.raises(ValueError, match=reason):
        subject.complete_computational_specification(state, field, answer)
    assert state.as_dict() == original


@pytest.mark.parametrize("key", ["lookback_bars", "max_age_seconds"])
@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_ohlcv_integer_contract_rejects_noninteger_typed_patches(key, value):
    _, state = _ohlcv_completion_subject(key)
    patch = SemanticCompletionPatch((
        SemanticFieldUpdate(f"{FIELD}.data_requirements[0].{key}", value, "USER_EXPLICIT"),
    ))
    with pytest.raises(ValueError, match="whole number"):
        apply_semantic_completion(state, patch)


def test_ohlcv_counts_require_identified_dataset_and_warmup_is_optional():
    path = f"{FIELD}.data_requirements[0]"
    row = {"dataset": "OHLCV", "symbol": "XAUUSD", "timeframe": "M1", "fields": ["close"], "usage": "RESEARCH_ONLY"}
    subject, state = _completion_subject({**SPEC, "data_requirements": [row]})
    assert subject.computational_specification_completion_fields(state)[0].keys() == {f"{path}.lookback_bars"}
    for dataset, gaps in (
        ("OHLCV", [f"{path}.dataset", f"{path}.warmup_bars", f"{path}.max_age_seconds"]),
        ("OTHER", [f"{path}.lookback_bars", f"{path}.warmup_bars", f"{path}.max_age_seconds"]),
    ):
        subject, state = _completion_subject({**SPEC, "data_requirements": [{**row, "dataset": dataset}]}, unresolved=gaps)
        assert not subject.computational_specification_completion_fields(state)[0]


def test_max_age_is_only_offered_when_unresolved_and_preserves_sibling_provenance():
    field = f"{FIELD}.data_requirements[0].max_age_seconds"
    spec = {**SPEC, "data_requirements": [
        {key: value for key, value in SPEC["data_requirements"][0].items() if key != "max_age_seconds"},
        SPEC["data_requirements"][1],
    ]}
    for candidate in (spec, SPEC):
        subject, state = _completion_subject(candidate)
        assert field not in subject.computational_specification_completion_fields(state)[0]
        with pytest.raises(ValueError, match="no longer missing"):
            subject.complete_computational_specification(state, field, "75")

    subject, state = _completion_subject(spec, unresolved=[field])
    message = subject.complete_computational_specification(state, field, "75")
    updated = ResolvedSemanticState.from_dict(message["resolved_semantic_state"])
    assert updated.semantic.computational_specification.as_dict() == {
        "schema_version": "computational-specification/v1", **SPEC,
    }
    assert dict(updated.field_sources) == {**dict(state.field_sources), field: "USER_EXPLICIT"}
    assert field not in updated.unresolved_fields
    plan = QueryPlanAssembler().assemble_resolved(RAW, updated)
    assert plan.constraints[FIELD]["status"] == "SPECIFIED"
    assert plan.constraints[FIELD]["data_assessments"][0]["freshness"] == "NOT_CHECKED"
    assert not plan.constraints["execution_allowed"] and "trading_request" not in message
    assert "max age seconds: 75" in message["content"]


@pytest.mark.parametrize(("second_key", "second_answer"), [("warmup_bars", "0"), ("max_age_seconds", "75")])
def test_concurrent_ohlcv_answers_use_the_same_compare_and_append_boundary(second_key, second_answer):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from types import SimpleNamespace
    from unittest.mock import Mock

    from src.services.history_service import HistoryService

    subject, state = _ohlcv_completion_subject("lookback_bars", second_key)
    review = {"intent": "COMPUTATIONAL_SPECIFICATION", "resolved_semantic_state": state.as_dict()}
    messages = [review]
    barrier, lock = Barrier(2), Lock()

    def update_one(selector, update, *, upsert):
        assert not upsert
        assert selector == {"_id": "coverage", "messages.0": {"$eq": review}, "messages.1": {"$exists": False}}
        with lock:  # Model the single-document atomic match and append.
            if len(messages) != 1:
                return SimpleNamespace(modified_count=0)
            messages.append(update["$push"]["messages"])
            return SimpleNamespace(modified_count=1)

    service = object.__new__(HistoryService)
    service.sessions_col, service.redis_client = SimpleNamespace(update_one=update_one), Mock()

    def submit(entry):
        key, answer = entry
        message = subject.complete_computational_specification(state, f"{FIELD}.data_requirements[0].{key}", answer)
        barrier.wait(timeout=5)
        return service.append_message_if_current("coverage", 1, review, message)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, (("lookback_bars", "1"), (second_key, second_answer)))) == [False, True]
    assert len(messages) == 2
    final = ResolvedSemanticState.from_dict(messages[-1]["resolved_semantic_state"])
    assert len(subject.computational_specification_completion_fields(final)[0]) == 1
    assert not service.append_message_if_current("coverage", 1, review, messages[-1])


def test_formula_can_satisfy_the_formula_or_steps_gap_without_inventing_steps():
    gap = f"{FIELD}.formula_or_steps"
    spec = {key: value for key, value in SPEC.items() if key not in {"formula", "steps"}}
    subject, state = _completion_subject(spec, unresolved=[gap])
    field = f"{FIELD}.formula"
    assert subject.computational_specification_completion_fields(state)[0].keys() == {field}
    result = subject.complete_computational_specification(state, field, "close minus open")
    updated = ResolvedSemanticState.from_dict(result["resolved_semantic_state"])
    assert not updated.unresolved_fields and not updated.semantic.unresolved_fields
    assert updated.semantic.computational_specification.formula == "close minus open"
    assert not updated.semantic.computational_specification.steps


def test_unnamed_parameter_is_not_a_safe_target():
    field = f"{FIELD}.parameters[0].value"
    subject, state = _completion_subject({**SPEC, "parameters": [{}]}, unresolved=[field])
    assert not subject.computational_specification_completion_fields(state)[0]
    with pytest.raises(ValueError, match="not supported"):
        subject.complete_computational_specification(state, field, "0")


def test_typed_completion_enforces_the_field_specific_length():
    spec = {key: value for key, value in SPEC.items() if key != "algorithm"}
    subject, state = _completion_subject(spec)
    with pytest.raises(ValueError, match="at most 100 characters"):
        subject.complete_computational_specification(state, f"{FIELD}.algorithm", "x" * 101)
    assert state.semantic.computational_specification.algorithm is None


@pytest.mark.parametrize(("outcome", "key"), [
    ("saved", "value"), ("saved", "lookback_bars"), ("saved", "warmup_bars"),
    ("invalid", "lookback_bars"), ("stale", "lookback_bars"), ("deleted", "lookback_bars"),
    ("deleted_only", "warmup_bars"), ("switched", "warmup_bars"),
    ("saved", "max_age_seconds"), ("invalid", "max_age_seconds"),
    ("stale", "max_age_seconds"), ("switched", "max_age_seconds"),
])
def test_streamlit_applies_only_to_the_current_persisted_review(monkeypatch, outcome, key):
    from streamlit.testing.v1 import AppTest
    from src.services import history_service
    from src.ui import tab_dashboard, tab_evaluation_dashboard, tab_settings

    if key == "value":
        field = f"{FIELD}.parameters[0].value"
        subject, state = _completion_subject({**SPEC, "parameters": [{"name": "offset"}]}, unresolved=[field])
        label = "Parameter 1 value"
    else:
        subject, state = _ohlcv_completion_subject(key)
        label = "Data requirement 1 " + key.replace("_", " ")
    review = {
        "role": "assistant", "intent": "COMPUTATIONAL_SPECIFICATION",
        "content": "Initial review", "resolved_semantic_state": state.as_dict(),
    }
    stored = {"active": [review], "other": [{"role": "assistant", "content": "Different conversation"}]}
    if outcome == "stale":
        stored["active"].append({"role": "user", "content": "Newer request in another tab"})
    calls = []

    class History:
        def get_all_sessions(self):
            return [{"_id": key, "title": key} for key in stored]

        def load_history(self, session_id):
            return list(stored[session_id])

        def append_message_if_current(self, session_id, count, expected, message):
            calls.append((session_id, count, expected))
            messages = stored.get(session_id)
            if messages is None or len(messages) != count or messages[-1] != expected:
                return False
            messages.append(message)
            return True

    monkeypatch.setattr(history_service, "HistoryService", History)
    for tab in (tab_dashboard, tab_evaluation_dashboard, tab_settings):
        monkeypatch.setattr(tab, "render", lambda *_: None)
    app = AppTest.from_file("src/app.py")
    app.session_state["current_session_id"] = "active"
    app.session_state["messages"] = [review]
    app.session_state["orchestrator"] = subject
    app.run()
    assert not app.exception
    if outcome == "switched":
        next(button for button in app.button if button.label == "other").click().run()
        app.run()
        assert not app.exception and not calls and app.session_state["current_session_id"] == "other"
        assert not any(button.label == "Apply clarification" for button in app.button)
        return
    submit = next(button for button in app.button if button.label == "Apply clarification")
    if outcome.startswith("deleted"):
        del stored["active"]
    if outcome == "deleted_only":
        del stored["other"]
    answer = "1.5" if outcome == "invalid" else {"lookback_bars": "1", "max_age_seconds": "75"}.get(key, "0")
    next(widget for widget in app.text_input if widget.label == label).set_value(answer)
    submit.click().run()
    assert not app.exception
    if outcome == "saved":
        assert calls == [("active", 1, review)]
        assert len(stored["active"]) == 2
        assert "Specified for review" in stored["active"][-1]["content"]
        assert f"{key.replace('_', ' ')}: {answer}" in stored["active"][-1]["content"]
        assert any("Specified for review" in item.value for item in app.markdown)
        app.run()
        assert len(calls) == 1
        assert not any(button.label == "Apply clarification" for button in app.button)
    elif outcome == "invalid":
        assert not calls and stored["active"] == [review]
        assert any("whole number" in item.value for item in app.warning)
    elif outcome in {"stale", "deleted_only"}:
        assert calls == [("active", 1, review)]
        assert any("stale" in item.value for item in app.warning)
        assert len(stored.get("active", [])) == (2 if outcome == "stale" else 0)
    else:
        assert not calls and app.session_state["current_session_id"] == "other"
        assert not any(button.label == "Apply clarification" for button in app.button)
