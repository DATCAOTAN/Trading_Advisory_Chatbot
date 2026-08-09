from types import SimpleNamespace

import pytest

from src.orchestrator import _bind_selected_position_context
from src.services.semantic.resolved_semantics import (
    ResolvedSemanticState,
    resolve_structured_semantics,
)
from src.services.semantic.structured_semantics import StructuredSemanticResult
from src.ui import tab_chatbot


POSITION_REFERENCE = "a" * 64
OTHER_PROTECTED_REFERENCE = "b" * 64


def _semantic(*, action="NONE", references=(), symbol="BTCUSD"):
    return StructuredSemanticResult(
        primary_intent="TRADE_LIFECYCLE",
        secondary_intents=(),
        action=action,
        direction="",
        subtype="POSITION_STATUS",
        domain="TRADING",
        symbols=(symbol,) if symbol else (),
        indicators=(),
        requested_data=("position_status",),
        conditions=(),
        context_references=tuple(references),
        requested_mode="advisory_only",
        account_scope="DEMO",
        explicit_fields=("action", "symbols") if symbol else ("action",),
        unresolved_fields=(),
        negated=False,
        hypothetical=False,
    )


def _state():
    return resolve_structured_semantics(_semantic())


def _position_payload():
    return {
        "schema_version": "position-read-model/v1",
        "blockers": [],
        "open_positions": [],
        "pending_orders": [],
        "history": [],
    }


def _management_payload():
    return {
        "schema_version": "human-confirmed-management-proposal/v1",
        "proposal_id": "management_proposal_test",
        "blockers": [],
    }


def _trading_payload():
    return {
        "intent_type": "TRADING_AUTHORIZATION_REQUEST",
        "execution_authority": False,
        "executable": False,
    }


@pytest.mark.parametrize(
    ("family", "artifacts", "expected"),
    (
        ("greeting", {}, tab_chatbot.PRESENTATION_TEXT),
        ("static_concept", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("current_market", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("advisory_analysis", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("mixed_knowledge_market", {"query_plan": {"child_plans": [{}, {}]}}, tab_chatbot.PRESENTATION_TEXT),
        ("complete_strategy", {"trading_request": _trading_payload()}, tab_chatbot.PRESENTATION_TRADING_REQUEST),
        ("incomplete_strategy", {"trading_request": _trading_payload()}, tab_chatbot.PRESENTATION_TRADING_REQUEST),
        ("completion_form", {"trading_request": _trading_payload()}, tab_chatbot.PRESENTATION_TRADING_REQUEST),
        ("draft", {"trading_request": _trading_payload()}, tab_chatbot.PRESENTATION_TRADING_REQUEST),
        ("candidate_review", {"trading_request": _trading_payload()}, tab_chatbot.PRESENTATION_TRADING_REQUEST),
        ("open_positions", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("pending_orders", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("pnl", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("history", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("provenance", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("management_target", {"management_proposal": _management_payload()}, tab_chatbot.PRESENTATION_MANAGEMENT),
        ("management_missing_target", {"management_proposal": _management_payload()}, tab_chatbot.PRESENTATION_MANAGEMENT),
        ("autonomous_status", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("knowledge_in_autonomous_mode", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("position_read_in_autonomous_mode", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("timeframe_continuation", {"query_plan": {}}, tab_chatbot.PRESENTATION_TEXT),
        ("position_continuation", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("stale_position", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("ambiguous_position", {"position_read_model": _position_payload()}, tab_chatbot.PRESENTATION_POSITION_READ),
        ("typed_blocker", {"blockers": ["PROVIDER_UNAVAILABLE"]}, tab_chatbot.PRESENTATION_BLOCKER),
    ),
)
def test_behavior_families_dispatch_from_canonical_artifacts(family, artifacts, expected):
    assert family
    assert tab_chatbot._runtime_presentation(artifacts)[0] == expected


def test_management_is_the_single_primary_presentation_for_composite_runtime_artifact():
    artifacts = {
        "position_read_model": _position_payload(),
        "management_proposal": _management_payload(),
    }

    kind, payload = tab_chatbot._runtime_presentation(artifacts)

    assert kind == tab_chatbot.PRESENTATION_MANAGEMENT
    assert payload == artifacts["management_proposal"]


def test_message_stores_only_the_selected_typed_presentation():
    message = {}
    artifacts = {
        "position_read_model": _position_payload(),
        "management_proposal": _management_payload(),
    }

    tab_chatbot._store_runtime_presentation(message, artifacts)

    assert message["presentation_kind"] == tab_chatbot.PRESENTATION_MANAGEMENT
    assert message["management_proposal"] == artifacts["management_proposal"]
    assert "position_read_model" not in message


def test_runtime_renderer_invokes_only_the_selected_component(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        tab_chatbot,
        "_render_position_read_card",
        lambda payload: rendered.append(("position", payload)),
    )
    monkeypatch.setattr(
        tab_chatbot,
        "_render_management_proposal_card",
        lambda payload: rendered.append(("management", payload)),
    )

    tab_chatbot._render_runtime_presentation(
        {
            "position_read_model": _position_payload(),
            "management_proposal": _management_payload(),
        }
    )

    assert rendered == [("management", _management_payload())]


def test_response_gate_preserves_typed_missing_context():
    kind, payload = tab_chatbot._runtime_presentation(
        {
            "response_gate": {
                "normal_synthesis_allowed": False,
                "missing_context": ["market_snapshot:BTCUSD", "ohlcv:BTCUSD:H1"],
            }
        }
    )

    assert kind == tab_chatbot.PRESENTATION_BLOCKER
    assert payload["blockers"] == ["market_snapshot:BTCUSD", "ohlcv:BTCUSD:H1"]


def test_authoritative_selected_position_is_bound_for_typed_continuation():
    previous = resolve_structured_semantics(
        _semantic(references=(OTHER_PROTECTED_REFERENCE,))
    )
    plan = SimpleNamespace(semantic_context=previous.as_dict())
    model = SimpleNamespace(
        status="AVAILABLE",
        blockers=(),
        selected_position=SimpleNamespace(protected_reference=POSITION_REFERENCE),
    )

    assert _bind_selected_position_context(plan, model) is True
    bound = ResolvedSemanticState.from_dict(plan.semantic_context)
    assert bound.semantic.context_references == (
        POSITION_REFERENCE,
        OTHER_PROTECTED_REFERENCE,
    )
    continuation = resolve_structured_semantics(
        _semantic(action="MANAGE_POSITION", references=("previous_position",), symbol=""),
        bound,
    )

    assert continuation.semantic.context_references == (POSITION_REFERENCE,)
    assert "context_references.previous_position" not in continuation.unresolved_fields


@pytest.mark.parametrize(
    "model",
    (
        SimpleNamespace(status="BLOCKED", blockers=("STALE_POSITION_REFERENCE",), selected_position=None),
        SimpleNamespace(status="AVAILABLE", blockers=("AMBIGUOUS_POSITION_REFERENCE",), selected_position=None),
        SimpleNamespace(status="AVAILABLE", blockers=(), selected_position=None),
    ),
)
def test_stale_ambiguous_or_missing_selection_is_never_bound(model):
    original = _state().as_dict()
    plan = SimpleNamespace(semantic_context=original)

    assert _bind_selected_position_context(plan, model) is False
    assert plan.semantic_context == original


def test_authoritative_runtime_artifact_never_enters_ui_raw_parser(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("raw UI semantic parser called")

    monkeypatch.setattr(tab_chatbot, "resolve_conversational_context", unexpected)
    monkeypatch.setattr(tab_chatbot, "parse_conversational_trading_request", unexpected)

    request, context = tab_chatbot._trading_request_from_runtime_artifacts(
        {"query_plan": {"primary_intent": "position_state_read"}},
        user_query="arbitrary wording",
        conversation_id="conversation-s9",
        messages=[],
    )

    assert request is None
    assert context is None
