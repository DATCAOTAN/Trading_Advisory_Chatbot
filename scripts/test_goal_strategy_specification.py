"""Offline contract/UI coverage; fixture provider output is not live research evidence."""
import copy
import json

import pytest
from pydantic import ValidationError

from scripts.test_goal_research_workflow import app, generate
from src.services.trading.research.proposal import ResearchContent, ResearchDevelopment, ResearchProposal


SPEC = {
    "specification": {
        "objective": "Test whether completed-bar dispersion explains session differences.",
        "formula": "D(t) = abs(close(t) - median(close(t-7:t-1)))",
        "steps": ["Calculate the custom dispersion on closed bars only."],
        "parameters": [{"name": "history", "value": 7, "unit": "closed bars"}],
        "entry": ["Enter only after D(t) exceeds its prior-window median; evaluate at close."],
        "exit": ["Exit after one completed observation interval."],
        "reentry": ["No overlapping observations."],
        "data_requirements": [{"dataset": "OHLCV", "fields": ["time", "close"], "symbol": "XAUUSD",
                               "timeframe": "M1", "lookback_bars": 1000, "warmup_bars": 7,
                               "completeness": "Consecutive closed bars", "usage": "RESEARCH_ONLY"}],
        "temporal_requirements": ["No future samples; chronological IS before OOS."],
        "configuration": {"strategy_origin": "AI_RESEARCHED", "authorization_mode": "ADVISORY"},
        "unsupported": ["Custom dispersion is an inert specification, not a runtime indicator."],
    },
    "in_sample": "First chronological block; exact dates require source approval.",
    "out_of_sample": "Strictly later disjoint block; exact dates not selected.",
    "evaluation_criteria": ["Compare predeclared session distributions after costs."],
    "rejection_criteria": ["Reject if held-out distributions do not differ."],
    "missing_information": ["Approved dataset and precise IS/OOS dates", "Unknown risk budget stays unknown"],
}


def develop(subject):
    view = generate(subject)
    subject.research_hypothesis_provider.output = json.dumps(SPEC)
    return view, subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)


def test_saved_hypothesis_to_g1_revision_strict_reload_and_plan(app):
    subject, db, _ = app
    before, after = develop(subject)
    proposal = after["proposal"]
    assert proposal.proposal_id == before["proposal"].proposal_id
    assert proposal.revisions[0] == before["proposal"].head
    assert proposal.brief == before["proposal"].brief
    assert proposal.head.author == "AI_SUGGESTED" and not proposal.execution_allowed
    assert proposal.head.content.strategy is None and not proposal.reviews
    assert proposal.head.content.development.specification.formula == SPEC["specification"]["formula"]
    assert proposal.brief.goal.max_risk_per_trade_pct is None
    assert proposal.review_status(proposal.head.revision_id) == "EVIDENCE_PENDING"
    review = proposal.head.content.development.review()
    assert "transaction_costs" in review["missing_information"]
    assert review["data_status"] == "NOT_CHECKED" and not review["execution_allowed"]
    assert review["runtime_status"] == "UNSUPPORTED_DYNAMIC_COMPUTATION"
    assert ResearchProposal.replay(proposal.to_json(), scope=proposal.scope) == proposal
    assert len(subject.research_hypothesis_provider.calls) == 2
    assert "JSON" in subject.research_hypothesis_provider.calls[-1][0]
    assert "All rule arrays contain STRINGS" in subject.research_hypothesis_provider.calls[-1][0]
    assert "research_proposals" in db.docs["A"] and "research_proposals" not in db.docs["B"]


def test_legacy_r1_serialization_unchanged_when_development_absent():
    assert ResearchContent(hypothesis="old").model_dump(mode="json") == {
        "hypothesis": "old", "strategy": None, "timeframes": [], "evidence": [], "limitations": [],
    }


@pytest.mark.parametrize("field,value", [
    ("authorization_mode", "AUTONOMOUS"), ("strategy_origin", "USER_DEFINED"),
    ("adaptation_policy", "ADAPTIVE_WITHIN_SCOPE"),
])
def test_no_provider_authority_or_origin_override(app, field, value):
    subject, _, _ = app
    view = generate(subject)
    payload = copy.deepcopy(SPEC)
    payload["specification"]["configuration"][field] = value
    subject.research_hypothesis_provider.output = json.dumps(payload)
    with pytest.raises(ValueError, match="SPECIFICATION_INVALID"):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


@pytest.mark.parametrize("change", [
    {"execution_allowed": True}, {"approval": "APPROVED"}, {"specification": {"data_requirements": [{"lookback_bars": 0}]}},
    {"transaction_costs": [{"name": "spread", "value": float("inf")}]},
])
def test_invalid_output_never_persists_or_grants_authority(app, change):
    subject, _, _ = app
    view = generate(subject)
    subject.research_hypothesis_provider.output = json.dumps({**SPEC, **change})
    with pytest.raises(ValueError):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


def test_edit_revision_idempotency_and_changed_hypothesis_invalidates_spec(app):
    subject, _, _ = app
    _, view = develop(subject)
    initial = view["proposal"]
    payload = copy.deepcopy(SPEC)
    payload["specification"]["entry"] = ["User-edited completed-bar entry rule."]
    updated = subject.develop_goal_research("A", view["key"], initial.head.revision_id,
                                           development_json=json.dumps(payload))["proposal"]
    assert updated.head.author == "USER_AUTHORED" and updated.brief == initial.brief
    assert len(updated.revisions) == 3 and updated.revisions[:2] == initial.revisions
    again = subject.develop_goal_research("A", view["key"], updated.head.revision_id,
                                         development_json=json.dumps(payload))["proposal"]
    assert again == updated
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        subject.develop_goal_research("A", view["key"], initial.head.revision_id,
                                     development_json=json.dumps(payload))
    changed = subject.revise_goal_research("A", view["key"], updated.head.revision_id, "A different hypothesis.")["proposal"]
    assert changed.head.content.development is None
    assert changed.revisions[-2].content.development is not None
    assert len(subject.research_hypothesis_provider.calls) == 2


def test_empty_partial_conflicting_specs_remain_visible_and_not_ready():
    partial = ResearchDevelopment.model_validate_json('{"specification": {"conflicts": ["Exit policy unresolved"]}}')
    review = partial.review()
    assert review["status"] == "NEEDS_CLARIFICATION"
    assert "specification.entry" in review["missing_information"]
    assert review["conflicts"] == ["Exit policy unresolved"]
    payload = copy.deepcopy(SPEC)
    payload["transaction_costs"] = [{"name": "commission", "value": 0, "unit": "USD/lot"}]
    assert "transaction_costs[0].name_value_unit" not in ResearchDevelopment.model_validate_json(json.dumps(payload)).review()["missing_information"]
    payload["specification"]["parameters"][0]["maximum"] = 2
    assert "computational_specification.parameters[0].range" in ResearchDevelopment.model_validate_json(json.dumps(payload)).review()["conflicts"]


@pytest.mark.parametrize("patch,outcome,reason", [
    ({"lookback_bars": 60, "warmup_bars": 0}, "VERIFIED_FOR_DECLARED_SCOPE", "RESEARCH_HISTORICAL_BAR_WINDOW_VERIFIED"),
    ({"lookback_bars": 1000}, "PARTIAL_OR_LIMITED", "RESEARCH_SPECIFICATION_COVERAGE_INSUFFICIENT"),
    ({"lookback_bars": 60, "warmup_bars": 2**63}, "PARTIAL_OR_LIMITED", "RESEARCH_SPECIFICATION_COVERAGE_INSUFFICIENT"),
    ({"fields": ["unavailable_order_flow"]}, "PENDING_VERIFICATION", "RESEARCH_SPECIFICATION_DATA_REQUIREMENTS_NOT_VERIFIED"),
    ({"timeframe": "H1"}, "INVALID_OR_MISMATCHED", "RESEARCH_MARKET_SCOPE_MISMATCH"),
])
def test_r2_checks_actual_specification_data_not_only_old_hypothesis(tmp_path, patch, outcome, reason):
    from scripts.test_research_evidence_verification import setup_source, inspect, research
    from scripts.test_research_proposal import SCOPE, create
    from src.services.trading.research.evidence_verification import HistoricalEvidenceVerifier
    source, reference = setup_source(tmp_path)
    payload = copy.deepcopy(SPEC)
    payload["specification"]["data_requirements"][0].update(patch)
    content = ResearchContent.model_validate({**research(reference).model_dump(),
        "development": ResearchDevelopment.model_validate_json(json.dumps(payload))})
    proposal = create(content)
    result = inspect(HistoricalEvidenceVerifier(SCOPE, (source,)), proposal, reference)
    assert result.outcome == outcome and result.reason == reason
    assert not proposal.reviews and not proposal.execution_allowed


def test_r2_uses_current_developed_timeframe_not_old_hypothesis_metadata(tmp_path):
    from scripts.test_research_evidence_verification import setup_source, inspect, research
    from scripts.test_research_proposal import SCOPE, create
    from src.services.trading.research.evidence_verification import HistoricalEvidenceVerifier
    source, reference = setup_source(tmp_path)
    payload = copy.deepcopy(SPEC)
    payload["specification"]["data_requirements"][0].update(lookback_bars=60, warmup_bars=0)
    proposal = create(ResearchContent.model_validate({**research(reference, "H1").model_dump(),
        "development": ResearchDevelopment.model_validate_json(json.dumps(payload))}))
    result = inspect(HistoricalEvidenceVerifier(SCOPE, (source,)), proposal, reference)
    assert result.outcome == "VERIFIED_FOR_DECLARED_SCOPE"
    assert proposal.head.content.timeframes == ("H1",)


def test_wrong_market_stale_concurrent_deleted_and_cross_conversation(app):
    subject, db, _ = app
    view = generate(subject)
    payload = copy.deepcopy(SPEC)
    payload["specification"]["data_requirements"][0]["symbol"] = "EURUSD"
    with pytest.raises(ValueError, match="SCOPE_CONFLICT"):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id,
                                     development_json=json.dumps(payload))
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.develop_goal_research("B", view["key"], view["proposal"].head.revision_id)
    subject.research_hypothesis_provider.output = json.dumps(SPEC)
    subject.research_hypothesis_provider.callback = lambda: subject.revise_goal_research(
        "A", view["key"], view["proposal"].head.revision_id, "Concurrent user edit.")
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    assert subject.inspect_goal_research("A")["proposal"].head.content.hypothesis == "Concurrent user edit."
    del db.docs["A"]
    with pytest.raises(ValueError):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)


def test_active_generation_and_provider_failure_leave_saved_revision_intact(app):
    subject, _, history = app
    view = generate(subject)
    with history.research_generation_lock(view["key"]):
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    def unavailable():
        raise RuntimeError("RESEARCH_PROVIDER_UNAVAILABLE")
    subject.research_hypothesis_provider.callback = unavailable
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


def test_provider_schema_failure_reports_only_safe_field_and_type(app):
    subject, _, _ = app
    view = generate(subject)
    payload = copy.deepcopy(SPEC)
    payload["specification"]["private_untrusted_payload"] = "never expose this value"
    subject.research_hypothesis_provider.output = json.dumps(payload)
    with pytest.raises(ValueError) as exc:
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    assert str(exc.value) == "RESEARCH_SPECIFICATION_INVALID_SPECIFICATION_EXTRA"
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


def test_streamlit_develop_edit_refresh_switch_and_no_extra_provider_calls(app):
    from streamlit.testing.v1 import AppTest
    subject, db, _ = app
    generate(subject)
    subject.research_hypothesis_provider.output = json.dumps(SPEC)
    page = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
_render_goal_research(st.session_state.subject)
''')
    page.session_state.subject = subject
    page.session_state.current_session_id = "A"
    page.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    page.run()
    next(b for b in page.button if b.label == "Develop testable strategy").click().run()
    assert not page.exception
    editor = next(t for t in page.text_area if t.label.startswith("Edit structured"))
    assert json.loads(editor.value)["specification"]["formula"] == SPEC["specification"]["formula"]
    payload = json.loads(editor.value)
    payload["out_of_sample"] = "User-defined later chronological block."
    editor.set_value(json.dumps(payload))
    next(b for b in page.button if b.label == "Save specification revision").click().run()
    page.run()
    assert not page.exception
    assert subject.inspect_goal_research("A")["proposal"].head.content.development.out_of_sample == payload["out_of_sample"]
    assert len(subject.research_hypothesis_provider.calls) == 2
    page.session_state.current_session_id = "B"
    page.session_state.messages = copy.deepcopy(db.docs["B"]["messages"])
    page.run()
    assert not page.exception and not page.text_area
