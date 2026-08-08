from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.services.trading.decision.conversational_authorization import (
    ConversationalTradingRequest,
)
from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.ui import tab_chatbot


def _request(*, action="OPEN_POSITION", blockers=(), strategy=None):
    return ConversationalTradingRequest(
        request_id="conversation_trade_" + "a" * 24,
        requested_mode="human_confirmed_live",
        confirmation_policy="CONFIRM_EVERY_TRADE",
        canonical_symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        timeframe_profile=operator_timeframe_profile("XAUUSD"),
        strategy_description="STRUCTURED_SEMANTIC_PROJECTION",
        account_scope="DEMO",
        mt5_authorization_required=True,
        mandate_required=False,
        allowed_next_action="BLOCKED" if blockers else "GRANT_MT5_DEMO_ACCESS",
        response_format="STRATEGY_COMPLETION_REQUIRED_CARD" if blockers else "MT5_ACCESS_CARD",
        trade_action=action,
        trade_direction="BUY" if action == "OPEN_POSITION" else "",
        blockers=tuple(blockers),
        strategy=strategy,
    )


class _SessionState(dict):
    __getattr__ = dict.__getitem__


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.session_state = _SessionState(current_session_id="conversation-ui")
        self.messages = []
        self.metrics = []

    def markdown(self, *_args, **_kwargs):
        pass

    def caption(self, value, *_args, **_kwargs):
        self.messages.append(("caption", str(value)))

    def info(self, value, *_args, **_kwargs):
        self.messages.append(("info", str(value)))

    def warning(self, value, *_args, **_kwargs):
        self.messages.append(("warning", str(value)))

    def success(self, value, *_args, **_kwargs):
        self.messages.append(("success", str(value)))

    def error(self, value, *_args, **_kwargs):
        self.messages.append(("error", str(value)))

    def columns(self, count):
        return [self] * count

    def metric(self, label, value, *_args, **_kwargs):
        self.metrics.append((label, value))

    def expander(self, *_args, **_kwargs):
        return _Context()


def _draft(*, revision=2, blockers=(), warnings=()):
    field = lambda value, source="SYSTEM_CALCULATED": SimpleNamespace(value=value, source=source)
    return SimpleNamespace(
        draft_id="editable_trade_draft_test",
        revision=revision,
        market_evidence_timestamp="2026-08-08T00:00:00+00:00",
        symbol=field({"canonical_symbol": "XAUUSD", "broker_symbol": "XAUUSDm", "timeframes": ("M1", "H1", "H4")}),
        direction=field("BUY", "USER_EXPLICIT"),
        action=field("OPEN_POSITION", "USER_EXPLICIT"),
        entry=field({"rules": (), "reference_price": None}),
        stop=field({"method": "ATR_MULTIPLE", "price": None, "atr_multiplier": None}),
        target=field({"method": "REWARD_RISK_RATIO", "price": None, "reward_risk_ratio": None}),
        risk=field({"fraction": None}),
        sizing=field({"method": "ACCOUNT_RISK_FRACTION", "proposed_volume": None, "actual_risk_amount": None, "actual_risk_fraction": None}),
        mode=field("human_confirmed_live", "CONVERSATION_INHERITED"),
        confirmation_policy=field("CONFIRM_EVERY_TRADE", "CONVERSATION_INHERITED"),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def _install_draft_renderer(monkeypatch, request, draft):
    streamlit = _FakeStreamlit()

    class Store:
        def __init__(self):
            pass

        def latest_for_conversation(self, _conversation_id):
            return SimpleNamespace(source_request_id=request.request_id)

    class Service:
        def __init__(self, *, store):
            self.store = store

        def build_or_load(self, *_args, **_kwargs):
            return draft

    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr(tab_chatbot, "EditableTradeDraftStore", Store)
    monkeypatch.setattr(tab_chatbot, "EditableTradeDraftService", Service)
    monkeypatch.setattr(tab_chatbot, "_render_trade_draft_patch_form", lambda *_args, **_kwargs: None)
    return streamlit


@pytest.mark.parametrize("family", ("knowledge", "current_market"))
def test_authoritative_non_trading_results_skip_ui_raw_fallback(monkeypatch, family):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy UI fallback called")

    monkeypatch.setattr(tab_chatbot, "resolve_conversational_context", unexpected)
    monkeypatch.setattr(tab_chatbot, "parse_conversational_trading_request", unexpected)

    request, context = tab_chatbot._trading_request_from_runtime_artifacts(
        {"query_plan": {"semantic_context": {"input": {"primary_intent": family}}}},
        user_query="authoritative result",
        conversation_id="conversation-ui",
        messages=[],
    )

    assert request is None
    assert context is None


def test_authoritative_trading_result_skips_ui_raw_fallback(monkeypatch):
    request = _request()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy UI fallback called")

    monkeypatch.setattr(tab_chatbot, "resolve_conversational_context", unexpected)
    monkeypatch.setattr(tab_chatbot, "parse_conversational_trading_request", unexpected)

    resolved, context = tab_chatbot._trading_request_from_runtime_artifacts(
        {
            "query_plan": {"semantic_context": {"input": {"primary_intent": "STRATEGY"}}},
            "trading_request": request.to_public_dict(),
        },
        user_query="ignored raw wording",
        conversation_id="conversation-ui",
        messages=[],
    )

    assert resolved == request
    assert context is None


def test_legacy_fallback_remains_only_for_absent_authoritative_plan(monkeypatch):
    request = _request()
    context = SimpleNamespace()
    calls = []
    monkeypatch.setattr(
        tab_chatbot,
        "resolve_conversational_context",
        lambda query, previous: calls.append((query, previous)) or context,
    )
    monkeypatch.setattr(
        tab_chatbot,
        "parse_conversational_trading_request",
        lambda *_args, **_kwargs: request,
    )

    resolved, fallback_context = tab_chatbot._trading_request_from_runtime_artifacts(
        None,
        user_query="legacy compatible request",
        conversation_id="conversation-ui",
        messages=[],
    )

    assert resolved == request
    assert fallback_context is context
    assert calls == [("legacy compatible request", None)]


def test_open_request_routes_directly_to_draft_without_rendering_request_blockers(monkeypatch):
    request = _request(blockers=("STALE_REQUEST_BLOCKER",))
    streamlit = _FakeStreamlit()
    rendered = []
    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr(tab_chatbot, "_render_editable_trade_draft", lambda value: rendered.append(value))

    tab_chatbot._render_conversational_trading_authorization(None, request)

    assert rendered == [request]
    assert not any("STALE_REQUEST_BLOCKER" in value for _kind, value in streamlit.messages)


def test_non_draft_request_keeps_its_current_request_blocker_visible(monkeypatch):
    request = _request(action="CLOSE_POSITION", blockers=("CURRENT_REQUEST_BLOCKER",))
    streamlit = _FakeStreamlit()
    monkeypatch.setattr(tab_chatbot, "st", streamlit)

    tab_chatbot._render_conversational_trading_authorization(None, request)

    assert ("warning", "Completion blockers: CURRENT_REQUEST_BLOCKER") in streamlit.messages


def test_latest_draft_revision_and_blockers_are_the_rendered_draft_truth(monkeypatch):
    request = _request(blockers=("STALE_REQUEST_BLOCKER",))
    streamlit = _install_draft_renderer(
        monkeypatch,
        request,
        _draft(revision=2, blockers=("CURRENT_DRAFT_BLOCKER",)),
    )
    monkeypatch.setattr(tab_chatbot, "_render_autonomous_decision_review_card", lambda *_args, **_kwargs: pytest.fail("candidate UI called"))

    tab_chatbot._render_editable_trade_draft(request)

    assert ("Revision", 2) in streamlit.metrics
    assert ("warning", "Draft blockers: CURRENT_DRAFT_BLOCKER") in streamlit.messages
    assert not any("STALE_REQUEST_BLOCKER" in value for _kind, value in streamlit.messages)


def test_semantic_missing_child_is_presented_separately_from_draft_blockers(monkeypatch):
    request = _request(
        blockers=("SEMANTIC_UNRESOLVED:indicators[0].parameters.period",),
        strategy=SimpleNamespace(semantic_unresolved_fields=("indicators[0].parameters.period",)),
    )
    streamlit = _install_draft_renderer(monkeypatch, request, _draft())

    tab_chatbot._render_editable_trade_draft(request)

    assert (
        "info",
        "Semantic input unresolved: indicators[0].parameters.period",
    ) in streamlit.messages
    assert not any("SEMANTIC_UNRESOLVED" in value for _kind, value in streamlit.messages if _kind == "warning")
