from __future__ import annotations

from dataclasses import replace

import pytest

from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.resolved_semantics import (
    SemanticCompletionPatch,
    SemanticFieldUpdate,
    resolve_structured_semantics,
)
from src.services.semantic.structured_semantics import (
    SEMANTIC_SCHEMA_VERSION,
    StructuredSemanticResult,
    StructuredSemanticValidationError,
)
from src.services.trading.decision.conversational_authorization import (
    apply_strategy_completion,
    build_strategy_completion_state,
    project_conversational_trading_request,
)
from src.services.trading.reasoning.strategy_evidence import validate_strategy
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraftService,
    TradeDraftError,
)
from src.ui import tab_chatbot


def _semantic(*, parameters=None, timeframe="", unresolved=(), direction="BUY"):
    indicator = {"indicator_id": "RSI"}
    if parameters is not None:
        indicator["parameters"] = parameters
    if timeframe:
        indicator["timeframe"] = timeframe
    return StructuredSemanticResult.from_payload(
        {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "primary_intent": "STRATEGY",
            "secondary_intents": [],
            "action": "OPEN_POSITION",
            "direction": direction,
            "subtype": "",
            "domain": "trading",
            "symbols": ["BTCUSD"],
            "indicators": [indicator],
            "requested_data": [],
            "conditions": [
                {"subject": "RSI", "operator": "GREATER_THAN", "value": 10}
            ],
            "context_references": [],
            "requested_mode": "",
            "account_scope": "DEMO",
            "explicit_fields": [
                "action",
                "direction",
                "symbols[0]",
                "indicators[0].indicator_id",
                "conditions[0]",
            ],
            "unresolved_fields": list(unresolved),
            "negated": False,
            "hypothetical": False,
        }
    )


def _artifacts(semantic):
    state = resolve_structured_semantics(semantic)
    plan = QueryPlanAssembler().assemble(
        "raw wording is not reparsed",
        structured_semantics=semantic,
    )
    request = project_conversational_trading_request(plan, conversation_id="completion-family")
    assert request is not None
    return state, request, build_strategy_completion_state(request, state)


@pytest.mark.parametrize(
    ("parameters", "timeframe", "expected"),
    (
        (None, "", {"indicators[0].parameters.period", "indicators[0].timeframe"}),
        (None, "H1", {"indicators[0].parameters.period"}),
        ({"period": 14}, "", {"indicators[0].timeframe"}),
    ),
)
def test_partial_indicator_children_preserve_known_strategy_siblings(
    parameters, timeframe, expected
):
    _state, request, completion = _artifacts(
        _semantic(parameters=parameters, timeframe=timeframe)
    )

    assert completion is not None
    assert set(completion.unresolved_fields) == expected
    assert completion.action == "OPEN_POSITION"
    assert completion.direction == "BUY"
    assert completion.canonical_symbol == "BTCUSD"
    assert completion.broker_symbol == "BTCUSDm"
    assert completion.strategy.indicators[0].indicator_id == "RSI"
    assert completion.strategy.entry_rules[0].operator == "GREATER_THAN"
    assert completion.strategy.entry_rules[0].constants == (10.0,)
    assert request.requested_mode == "human_confirmed_live"
    assert completion.executable is False
    assert completion.execution_allowed is False


def test_complete_strategy_skips_completion_state_and_is_valid():
    _state, request, completion = _artifacts(
        _semantic(parameters={"period": 14}, timeframe="H1")
    )

    assert completion is None
    assert request.strategy is not None
    assert validate_strategy(request.strategy) == ()
    assert request.timeframe_profile == ("H1",)


def test_accepting_one_suggestion_preserves_remaining_unresolved_sibling():
    state, request, completion = _artifacts(_semantic())
    period = next(
        item for item in completion.suggestions if item.field_path.endswith("parameters.period")
    )

    updated, updated_state = apply_strategy_completion(
        request,
        state,
        SemanticCompletionPatch(
            (
                SemanticFieldUpdate(
                    period.field_path,
                    period.value,
                    "USER_CONFIRMED_SUGGESTION",
                ),
            )
        ),
    )

    assert updated.strategy.indicators[0].parameter_map() == {"period": 14.0}
    assert updated.strategy.semantic_unresolved_fields == ("indicators[0].timeframe",)
    assert dict(updated_state.field_sources)[period.field_path] == "USER_CONFIRMED_SUGGESTION"
    assert updated.requested_mode == "human_confirmed_live"
    assert updated.allowed_next_action == "BLOCKED"
    assert type(updated).from_public_dict(updated.to_public_dict()) == updated


def test_accepting_both_suggestions_completes_without_reparsing_or_authority():
    state, request, completion = _artifacts(_semantic())
    patch = SemanticCompletionPatch(
        tuple(
            SemanticFieldUpdate(
                item.field_path,
                item.value,
                "USER_CONFIRMED_SUGGESTION",
            )
            for item in completion.suggestions
        )
    )

    updated, updated_state = apply_strategy_completion(request, state, patch)

    assert updated.strategy.semantic_unresolved_fields == ()
    assert validate_strategy(updated.strategy) == ()
    assert updated.timeframe_profile == ("M1",)
    assert updated.response_format == "MT5_ACCESS_CARD"
    assert updated.to_public_dict()["execution_authority"] is False
    assert updated.to_public_dict()["executable"] is False
    assert updated_state.semantic.unresolved_fields == ()


def test_manual_edit_overrides_suggestion_and_keeps_explicit_provenance():
    state, request, _completion = _artifacts(
        _semantic(timeframe="H1", unresolved=("indicators[0].parameters.period",))
    )

    updated, updated_state = apply_strategy_completion(
        request,
        state,
        SemanticCompletionPatch(
            (
                SemanticFieldUpdate(
                    "indicators[0].parameters.period",
                    21.0,
                    "USER_EXPLICIT",
                ),
            )
        ),
    )

    assert updated.strategy.indicators[0].parameter_map() == {"period": 21.0}
    assert dict(updated_state.field_sources)["indicators[0].parameters.period"] == "USER_EXPLICIT"


def test_valid_context_inheritance_keeps_distinct_provenance():
    previous = resolve_structured_semantics(
        _semantic(parameters={"period": 14}, timeframe="H1")
    )
    current = replace(
        _semantic(parameters=None, timeframe=""),
        context_references=("previous_indicator",),
    )

    state = resolve_structured_semantics(current, previous)

    assert state.indicators[0].parameters == (("period", 14.0),)
    assert state.indicators[0].timeframe == "H1"
    assert dict(state.field_sources)["indicators[0].parameters.period"] == "CONVERSATION_INHERITED"
    assert dict(state.field_sources)["indicators[0].timeframe"] == "CONVERSATION_INHERITED"


def test_field_provenance_keeps_llm_suggestion_distinct_from_user_sources():
    semantic = replace(
        _semantic(),
        explicit_fields=("symbols[0]", "indicators[0].indicator_id", "conditions[0]"),
    )

    state, _request, completion = _artifacts(semantic)
    sources = dict(state.field_sources)

    assert sources["action"] == "LLM_SUGGESTION"
    assert sources["direction"] == "LLM_SUGGESTION"
    assert next(
        item for item in completion.suggestions if item.field_path.endswith("parameters.period")
    ).source == "STRATEGY_POLICY"


def test_operational_profile_never_completes_semantic_timeframe():
    _state, request, completion = _artifacts(_semantic(parameters={"period": 14}))

    assert completion.strategy.indicators[0].timeframe == ""
    assert "indicators[0].timeframe" in completion.unresolved_fields
    assert completion.operational_timeframe_profile == ("M1", "H1", "H4")
    assert request.timeframe_profile == ("M1", "H1", "H4")


def test_provider_missing_children_are_partial_but_invalid_values_and_shapes_fail_closed():
    _state, request, completion = _artifacts(_semantic())
    assert completion is not None
    assert request.strategy is not None

    _state, invalid_request, _completion = _artifacts(
        _semantic(parameters={"period": -1}, timeframe="M1")
    )
    assert invalid_request.strategy is None
    assert "INDICATOR_PARAMETER_OUT_OF_RANGE" in invalid_request.blockers

    payload = _semantic().as_dict()
    payload["indicators"][0]["unexpected"] = "blocked"
    with pytest.raises(StructuredSemanticValidationError, match="INDICATOR_FIELDS_INVALID"):
        StructuredSemanticResult.from_payload(payload)


def test_provider_declared_null_children_are_missing_but_unbound_null_stays_invalid():
    payload = _semantic().as_dict()
    payload["indicators"][0]["parameters"] = {"period": None}
    payload["indicators"][0]["timeframe"] = None
    payload["unresolved_fields"] = [
        "indicators[0].parameters.period",
        "indicators[0].timeframe",
    ]

    semantic = StructuredSemanticResult.from_payload(payload)

    assert semantic.indicators[0].parameters == ()
    assert semantic.indicators[0].timeframe == ""
    assert semantic.unresolved_fields == (
        "indicators[0].parameters.period",
        "indicators[0].timeframe",
    )

    payload["unresolved_fields"] = []
    with pytest.raises(StructuredSemanticValidationError, match="INDICATOR_PARAMETERS_INVALID"):
        StructuredSemanticResult.from_payload(payload)


def test_incomplete_strategy_routes_to_completion_not_draft_or_candidate(monkeypatch):
    state, request, completion = _artifacts(_semantic())
    rendered = []
    monkeypatch.setattr(
        tab_chatbot,
        "_render_strategy_completion_form",
        lambda current, semantic, value: rendered.append((current, semantic, value)),
    )
    monkeypatch.setattr(
        tab_chatbot,
        "_render_editable_trade_draft",
        lambda *_args, **_kwargs: pytest.fail("Draft must not render"),
    )
    monkeypatch.setattr(
        tab_chatbot,
        "_render_autonomous_decision_review_card",
        lambda *_args, **_kwargs: pytest.fail("Candidate controls must not render"),
    )

    tab_chatbot._render_conversational_trading_authorization(None, request, state)

    assert rendered == [(request, state, completion)]


def test_domain_draft_owner_rejects_incomplete_semantics_before_store_access():
    _state, request, _completion = _artifacts(_semantic())

    with pytest.raises(TradeDraftError, match="STRATEGY_COMPLETION_REQUIRED"):
        EditableTradeDraftService(store=object()).build_or_load(
            request,
            conversation_id="completion-family",
            evidence=None,
        )


def test_completion_patch_cannot_overwrite_a_known_sibling():
    state, request, _completion = _artifacts(
        _semantic(parameters={"period": 14}, timeframe="")
    )

    with pytest.raises(ValueError, match="STRATEGY_COMPLETION_FIELD_NOT_UNRESOLVED"):
        apply_strategy_completion(
            request,
            state,
            SemanticCompletionPatch(
                (
                    SemanticFieldUpdate(
                        "indicators[0].parameters.period",
                        21.0,
                        "USER_EXPLICIT",
                    ),
                )
            ),
        )


def test_completion_form_persists_typed_request_and_state_without_candidate(monkeypatch):
    state, request, completion = _artifacts(_semantic())
    persisted = []

    class Form:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Session(dict):
        __getattr__ = dict.__getitem__

    class Streamlit:
        session_state = Session(
            current_session_id="completion-family",
            messages=[],
        )
        reran = False

        def markdown(self, *_args, **_kwargs):
            pass

        def caption(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

        def info(self, *_args, **_kwargs):
            pass

        def success(self, *_args, **_kwargs):
            pass

        def error(self, *_args, **_kwargs):
            pass

        def form(self, *_args, **_kwargs):
            return Form()

        def selectbox(self, label, options, **_kwargs):
            return next(value for value in options if "suggested" in value)

        def text_input(self, *_args, **_kwargs):
            return ""

        def form_submit_button(self, *_args, **_kwargs):
            return True

        def rerun(self):
            self.reran = True

    class History:
        def append_message(self, session_id, message, *, include_vector_memory):
            persisted.append((session_id, message, include_vector_memory))

    streamlit = Streamlit()
    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr("src.services.history_service.HistoryService", History)
    monkeypatch.setattr(
        tab_chatbot,
        "_render_editable_trade_draft",
        lambda *_args, **_kwargs: pytest.fail("Draft is rendered only after rerun"),
    )

    tab_chatbot._render_strategy_completion_form(request, state, completion)

    assert streamlit.reran is True
    assert len(streamlit.session_state.messages) == 1
    saved = streamlit.session_state.messages[0]
    completed = type(request).from_public_dict(saved["trading_request"])
    assert completed.strategy.semantic_unresolved_fields == ()
    assert completed.strategy.indicators[0].parameter_map() == {"period": 14.0}
    assert completed.strategy.indicators[0].timeframe == "M1"
    assert persisted == [("completion-family", saved, False)]
