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
    def __init__(self, button_keys=()):
        self.session_state = _SessionState(current_session_id="conversation-ui")
        self.messages = []
        self.metrics = []
        self.button_keys = set(button_keys)
        self.reruns = 0

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

    def button(self, *_args, **kwargs):
        return kwargs.get("key") in self.button_keys

    def rerun(self):
        self.reruns += 1


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


@pytest.mark.parametrize(
    "runtime_artifacts",
    (
        {"query_plan": {"semantic_context": {}, "primary_intent": "market_state_analysis"}},
        {"is_bounded_response": True, "semantic_provider_calls": 0},
    ),
)
def test_central_runtime_result_blocks_ui_raw_reparse(monkeypatch, runtime_artifacts):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy UI fallback called")

    monkeypatch.setattr(tab_chatbot, "resolve_conversational_context", unexpected)
    monkeypatch.setattr(tab_chatbot, "parse_conversational_trading_request", unexpected)

    request, context = tab_chatbot._trading_request_from_runtime_artifacts(
        runtime_artifacts,
        user_query="trade-like text with invalid structured output",
        conversation_id="conversation-ui",
        messages=[],
    )

    assert request is None
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


def test_open_request_without_typed_strategy_keeps_completion_blocker_visible(monkeypatch):
    request = _request(blockers=("STALE_REQUEST_BLOCKER",))
    streamlit = _FakeStreamlit()
    rendered = []
    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr(tab_chatbot, "_render_editable_trade_draft", lambda value, **_kwargs: rendered.append(value))

    tab_chatbot._render_conversational_trading_authorization(None, request)

    assert rendered == []
    assert ("warning", "Completion blockers: STALE_REQUEST_BLOCKER") in streamlit.messages


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


@pytest.mark.parametrize(
    "unresolved_fields",
    (
        ("indicators[0].parameters.period",),
        (
            "indicators[0].parameters.fast_period",
            "indicators[0].parameters.slow_period",
            "indicators[0].parameters.signal_period",
        ),
    ),
)
def test_incomplete_semantics_skip_evidence_acquisition_before_planning(monkeypatch, unresolved_fields):
    request = _request(
        blockers=tuple(f"SEMANTIC_UNRESOLVED:{field}" for field in unresolved_fields),
        strategy=SimpleNamespace(semantic_unresolved_fields=unresolved_fields),
    )

    def unexpected(*_args, **_kwargs):
        pytest.fail("incomplete semantics must not enter evidence acquisition")

    monkeypatch.setattr(tab_chatbot, "plan_strategy_data", unexpected)
    monkeypatch.setattr(tab_chatbot.ProviderRegistry, "build_provider", unexpected)

    evidence, status = tab_chatbot._load_trade_draft_evidence(request)

    assert evidence is None
    assert status == "NOT_ATTEMPTED_PREREQUISITE_UNRESOLVED"


def test_complete_semantics_attempt_evidence_planning_once(monkeypatch):
    strategy = SimpleNamespace(semantic_unresolved_fields=(), timeframes=("M1",))
    request = _request(strategy=strategy)
    calls = []
    provider = SimpleNamespace(get_account=lambda: calls.append("account") or "account")
    plan = SimpleNamespace(candle_counts=lambda: {"M1": 100})

    class FeatureService:
        def __init__(self, *, bundle_builder):
            calls.append(("service", bundle_builder))

        def build_features(self, *args, **kwargs):
            calls.append(("features", args, kwargs))
            return "features"

    class AuthorityService:
        def status(self, *, refresh_runtime):
            calls.append(("authority", refresh_runtime))
            return {"account_environment": "DEMO"}

        def close(self):
            calls.append("close")

    monkeypatch.setattr(tab_chatbot, "plan_strategy_data", lambda value: calls.append(("plan", value)) or plan)
    monkeypatch.setattr(tab_chatbot.ProviderRegistry, "build_provider", lambda: provider)
    monkeypatch.setattr(tab_chatbot, "MarketSnapshotBundleBuilder", lambda value: ("bundle", value))
    monkeypatch.setattr(tab_chatbot, "LiveFeatureService", FeatureService)
    monkeypatch.setattr(tab_chatbot, "TradingAuthorityOperatorService", AuthorityService)
    monkeypatch.setattr(tab_chatbot, "market_evidence_from_live_result", lambda *args, **kwargs: "evidence")

    evidence, status = tab_chatbot._load_trade_draft_evidence(request)

    assert (evidence, status) == ("evidence", "")
    assert [item for item in calls if isinstance(item, tuple) and item[0] == "plan"] == [("plan", strategy)]
    assert "account" in calls
    assert ("authority", False) in calls
    assert "close" in calls


def test_complete_semantics_preserve_real_evidence_failure(monkeypatch):
    strategy = SimpleNamespace(semantic_unresolved_fields=(), timeframes=("M1",))
    request = _request(strategy=strategy)

    class FeatureService:
        def __init__(self, **_kwargs):
            pass

        def build_features(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(tab_chatbot, "plan_strategy_data", lambda _value: SimpleNamespace(candle_counts=lambda: {"M1": 100}))
    monkeypatch.setattr(tab_chatbot.ProviderRegistry, "build_provider", lambda: object())
    monkeypatch.setattr(tab_chatbot, "MarketSnapshotBundleBuilder", lambda value: value)
    monkeypatch.setattr(tab_chatbot, "LiveFeatureService", FeatureService)

    evidence, status = tab_chatbot._load_trade_draft_evidence(request)

    assert evidence is None
    assert status == "EVIDENCE_ACQUISITION_FAILED"


def test_draft_render_never_constructs_candidate_without_explicit_button(monkeypatch):
    request = _request()
    streamlit = _install_draft_renderer(monkeypatch, request, _draft())

    class UnexpectedCandidateService:
        def __init__(self, *_args, **_kwargs):
            pytest.fail("candidate service must require an explicit button action")

    monkeypatch.setattr(tab_chatbot, "EditableTradeDraftCandidateService", UnexpectedCandidateService)

    tab_chatbot._render_editable_trade_draft(request, orchestrator=SimpleNamespace(live_service=object()))

    assert not any("Candidate created" in value for _kind, value in streamlit.messages)


def test_explicit_draft_button_binds_current_id_and_revision_to_candidate_service(monkeypatch):
    request = _request()
    draft = _draft(revision=4)
    key = f"editable_draft_{draft.draft_id}_{draft.revision}_create_candidate"
    streamlit = _install_draft_renderer(monkeypatch, request, draft)
    streamlit.button_keys.add(key)
    calls = []

    class Authority:
        def status(self, *, refresh_runtime):
            assert refresh_runtime is False
            return {
                "mode": "human_confirmed_live",
                "account_environment": "DEMO",
                "mode_integrity_valid": True,
            }

        def close(self):
            pass

    class CandidateService:
        def __init__(self, *_args):
            pass

        def create(self, draft_id, revision, **kwargs):
            calls.append((draft_id, revision, kwargs))
            return SimpleNamespace(
                status="DRAFT_NOT_ELIGIBLE",
                blocker="MARKET_DATA_STALE",
                run_result=None,
            )

    monkeypatch.setattr(tab_chatbot, "TradingAuthorityOperatorService", Authority)
    monkeypatch.setattr(tab_chatbot, "AuthoritativeAutonomousInputAssembler", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(tab_chatbot, "AutonomousDecisionOrchestrator", lambda: object())
    monkeypatch.setattr(tab_chatbot, "EditableTradeDraftCandidateService", CandidateService)

    tab_chatbot._render_editable_trade_draft(
        request, orchestrator=SimpleNamespace(live_service=object())
    )

    assert len(calls) == 1
    assert calls[0][0:2] == (draft.draft_id, draft.revision)
    assert calls[0][2]["strategy"] is request.strategy
    assert ("warning", "Candidate creation blocked: MARKET_DATA_STALE") in streamlit.messages


def test_explicit_market_refresh_reuses_evidence_and_revision_services(monkeypatch):
    request = _request()
    draft = _draft(revision=4)
    key = f"editable_draft_{draft.draft_id}_{draft.revision}_refresh_market_evidence"
    streamlit = _FakeStreamlit(button_keys=(key,))
    refreshed = _draft(revision=5)
    evidence = object()
    calls = []

    class Service:
        def apply_patch(self, draft_id, patch, *, evidence):
            calls.append((draft_id, patch, evidence))
            return refreshed

    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr(
        tab_chatbot, "_load_trade_draft_evidence", lambda value: (evidence, "")
    )
    cleared = []
    monkeypatch.setattr(
        tab_chatbot,
        "clear_autonomous_decision_run_result",
        lambda session: cleared.append(session),
    )

    tab_chatbot._render_trade_draft_refresh_action(Service(), draft, request)

    assert len(calls) == 1
    assert calls[0][0] == draft.draft_id
    assert calls[0][1].expected_revision == draft.revision
    assert all(
        getattr(calls[0][1], name) is None
        for name in (
            "stop_loss", "stop_method", "atr_multiplier", "take_profit",
            "target_method", "reward_risk_ratio", "risk_fraction",
            "requested_volume", "direction",
        )
    )
    assert calls[0][2] is evidence
    assert cleared == [streamlit.session_state]
    assert streamlit.reruns == 1
    assert streamlit.session_state[
        f"editable_draft_{draft.draft_id}_market_refresh_result"
    ]["validation"] == "VALID_NON_EXECUTABLE"

    streamlit.button_keys.clear()
    tab_chatbot._render_trade_draft_refresh_action(Service(), refreshed, request)
    assert any(
        kind == "success"
        and "Market evidence refreshed" in message
        and "revision: 4 -> 5" in message
        and "Draft validation: VALID_NON_EXECUTABLE" in message
        for kind, message in streamlit.messages
    )


def test_market_refresh_failure_creates_no_revision_or_candidate(monkeypatch):
    request = _request()
    draft = _draft(revision=4)
    key = f"editable_draft_{draft.draft_id}_{draft.revision}_refresh_market_evidence"
    streamlit = _FakeStreamlit(button_keys=(key,))

    class Service:
        def apply_patch(self, *_args, **_kwargs):
            pytest.fail("refresh must stop before revision creation")

    monkeypatch.setattr(tab_chatbot, "st", streamlit)
    monkeypatch.setattr(
        tab_chatbot,
        "_load_trade_draft_evidence",
        lambda _value: (None, "EVIDENCE_ACQUISITION_FAILED"),
    )

    tab_chatbot._render_trade_draft_refresh_action(Service(), draft, request)

    assert streamlit.reruns == 0
    assert (
        "warning",
        "Market evidence refresh blocked: EVIDENCE_ACQUISITION_FAILED",
    ) in streamlit.messages


def test_matching_draft_candidate_renders_existing_review_controls_without_acting(monkeypatch):
    request = _request()
    draft = _draft(revision=4)
    _install_draft_renderer(monkeypatch, request, draft)
    candidate = SimpleNamespace(
        candidate_reference="candidate-draft-bound",
        proposal_source="EDITABLE_TRADE_DRAFT",
        proposal_source_reference="draft-bound-reference",
        operating_mode="human_confirmed_live",
    )
    calls = []
    monkeypatch.setattr(tab_chatbot, "draft_candidate_source_reference", lambda _draft: "draft-bound-reference")
    monkeypatch.setattr(
        tab_chatbot,
        "get_autonomous_decision_run_result",
        lambda _session: SimpleNamespace(candidate=candidate, validation=SimpleNamespace()),
    )
    monkeypatch.setattr(tab_chatbot, "render_autonomous_candidate_review_card", lambda *_args: None)
    monkeypatch.setattr(tab_chatbot, "_operator_candidate_review_controller", lambda: "controller")
    monkeypatch.setattr(
        tab_chatbot,
        "render_autonomous_candidate_confirmation_controls",
        lambda reference, controller, **kwargs: calls.append((reference, controller, kwargs)),
    )

    tab_chatbot._render_editable_trade_draft(request, orchestrator=SimpleNamespace(live_service=object()))

    assert calls == [
        (
            "candidate-draft-bound",
            "controller",
            {"key_prefix": "editable_draft_editable_trade_draft_test_4_"},
        )
    ]
