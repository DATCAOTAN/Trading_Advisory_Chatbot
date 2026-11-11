"""Typed dependency metadata only; no market acquisition or indicator execution."""
import copy
from dataclasses import replace
from datetime import timedelta
import json

import pytest
from pydantic import ValidationError

from scripts.test_goal_research_workflow import app
from scripts.test_goal_historical_data_integration import setup, specification
from src.services.semantic.structured_semantics import ComputationalDataRequirement, ComputationalSpecification
from src.services.trading.reasoning.strategy_evidence import INDICATOR_REGISTRY
from src.services.trading.research.data_integration import historical_requests, resolve_data_dependencies


PARAMETERS = {"EMA": {"period": 20}, "SMA": {"period": 20}, "RSI": {"period": 14},
              "ATR": {"period": 14}, "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
              "BOLLINGER_BANDS": {"period": 20, "deviation": 2}}


def indicator(name="output", indicator_id="EMA", **changes):
    result = {"name": name, "indicator_id": indicator_id, "parameters": PARAMETERS[indicator_id]}
    if len(INDICATOR_REGISTRY[indicator_id].output_fields) > 1:
        result["output_field"] = INDICATOR_REGISTRY[indicator_id].output_fields[0]
    return {**result, **changes}


def custom(name="range", **changes):
    return {"name": name, "definition": "high - low", "output_type": "FLOAT64",
            "inputs": [{"field": field, "kind": "RAW_MT5", "data_type": "FLOAT64"} for field in ("high", "low")],
            "lookback_bars": 1, "warmup_bars": 0, **changes}


def requirement(computations=(), **changes):
    payload = {"dataset": "OHLCV", "symbol": "XAUUSD", "timeframe": "M1", "usage": "RESEARCH_ONLY",
               "fields": [item["name"] for item in computations], "computations": list(computations), **changes}
    return ComputationalDataRequirement.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("code", PARAMETERS)
def test_supported_family_uses_registry_contract_without_running_computation(code, monkeypatch):
    from src.services.trading.reasoning import strategy_evidence
    def prohibited(*_args, **_kwargs):
        raise AssertionError("Indicator execution is not dependency resolution")
    monkeypatch.setattr(strategy_evidence, "_compute_indicator", prohibited)
    original = requirement([indicator(indicator_id=code)])
    before = original.model_dump_json()
    result = resolve_data_dependencies(original)
    contract = INDICATOR_REGISTRY[code]
    assert not result["blockers"]
    assert set(result["raw_fields"]) == {"time", *contract.required_fields}
    assert result["lookback"] == contract.minimum_bars
    assert result["warmup"] == contract.warmup(PARAMETERS[code])
    assert result["derived_computations"][0]["formula_version"] == contract.formula_version
    assert original.model_dump_json() == before and not result["execution_allowed"]


@pytest.mark.parametrize("field", ["EMA20", "RSI", "volume", "cloze"])
def test_names_are_never_parsed_into_parameters_or_raw_aliases(field):
    result = resolve_data_dependencies(requirement(fields=[field], lookback_bars=20, warmup_bars=50))
    assert f"DEPENDENCY_DECLARATION_REQUIRED:{field}" in result["blockers"]
    assert field not in result["raw_fields"]


@pytest.mark.parametrize("parameters", [{}, {"period": 1}, {"period": 501}, {"period": 2.5}, {"other": 14}])
def test_parameter_contract_rejects_missing_invalid_without_defaults(parameters):
    result = resolve_data_dependencies(requirement([indicator(parameters=parameters)]))
    assert "INDICATOR_PARAMETERS_INVALID_OR_MISSING:output" in result["blockers"]
    assert result["warmup"] is None
    assert "close" in result["raw_fields"]


@pytest.mark.parametrize("patch", [
    {"output_type": "UNKNOWN"}, {"parameters": {"period": True}}, {"parameters": {"period": "14"}},
    {"parameters": {"period": float("nan")}},
    {"inputs": [{"field": "close", "kind": "RAW_MT5"}]},
])
def test_strict_types_at_existing_g1_boundary(patch):
    with pytest.raises(ValidationError):
        requirement([custom(**patch)])


@pytest.mark.parametrize("declarations,reason", [
    ([indicator(timeframe="H1")], "DEPENDENCY_TIMEFRAME_CONFLICT"),
    ([indicator(output_type="INT64")], "DEPENDENCY_OUTPUT_TYPE_CONFLICT"),
    ([indicator(inputs=[{"field": "high", "kind": "RAW_MT5", "data_type": "FLOAT64"}])], "REGISTRY_INPUT_DECLARATION_CONFLICT"),
    ([indicator(), indicator()], "COMPUTATION_NAME_CONFLICT"),
    ([indicator(name="close")], "COMPUTATION_NAME_CONFLICT"),
    ([custom(inputs=[])], "CUSTOM_DEPENDENCY_DECLARATION_INCOMPLETE"),
    ([custom(inputs=[{"field": "not_a_bar_field", "kind": "RAW_MT5", "data_type": "FLOAT64"}])], "RAW_MT5_FIELD_INVALID"),
    ([custom(inputs=[{"field": "close", "kind": "RAW_MT5", "data_type": "INT64"}])], "DEPENDENCY_INPUT_TYPE_CONFLICT"),
    ([custom(inputs=[{"field": "missing", "kind": "DERIVED", "data_type": "FLOAT64"}])], "DERIVED_INPUT_UNDECLARED"),
    ([custom(inputs=[{"field": "range", "kind": "DERIVED", "data_type": "FLOAT64"}])], "DEPENDENCY_CYCLE"),
    ([custom(name="a", inputs=[{"field": "b", "kind": "DERIVED", "data_type": "FLOAT64"}]),
      custom(name="b", inputs=[{"field": "a", "kind": "DERIVED", "data_type": "FLOAT64"}])], "DEPENDENCY_CYCLE"),
    ([indicator(indicator_id="MACD", output_field=None)], "INDICATOR_OUTPUT_INVALID_OR_MISSING"),
    ([indicator(indicator_id="MACD", parameters={"fast_period": 26, "slow_period": 12, "signal_period": 9})], "INDICATOR_PARAMETERS_INVALID_OR_MISSING"),
    ([indicator(), custom(inputs=[{"field": "output", "kind": "DERIVED", "data_type": "FLOAT64"}])], "DECLARED_CONTEXT_BELOW_DEPENDENCY_MINIMUM"),
])
def test_bounded_conflict_and_missing_family(declarations, reason):
    result = resolve_data_dependencies(requirement(declarations))
    assert any(item.startswith(reason) for item in result["blockers"])
    assert not result["execution_allowed"]


def test_custom_declared_dependencies_are_not_an_implementation_or_computed_result():
    result = resolve_data_dependencies(requirement([custom()]))
    assert not result["blockers"] and result["raw_fields"] == ["time", "high", "low"]
    assert result["unsupported_computations"] == ["range"]
    assert result["derived_computations"][0]["status"] == "DECLARED_UNVERIFIED"
    assert "result" not in result and result["warmup"] == 0
    nested = requirement([indicator(), custom(inputs=[{"field": "output", "kind": "DERIVED", "data_type": "FLOAT64"}],
                                               lookback_bars=2, warmup_bars=60)])
    report = resolve_data_dependencies(nested)
    assert not report["blockers"] and report["raw_fields"] == ["time", "close"]


def test_explicit_counts_are_not_silently_increased_or_overwritten():
    source = requirement([indicator()], lookback_bars=100, warmup_bars=0)
    before = source.model_dump_json()
    result = resolve_data_dependencies(source)
    assert result["required_warmup"] == 60 and result["warmup"] == 0
    assert "DECLARED_WARMUP_BELOW_DEPENDENCY_MINIMUM" in result["blockers"]
    assert source.model_dump_json() == before


def test_shared_dependencies_group_same_market_but_keep_timeframes_separate(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    payload = specification()
    payload["specification"]["data_requirements"] = [requirement([indicator(name="trend")]).model_dump(mode="json"),
        requirement([indicator(name="range", indicator_id="ATR")]).model_dump(mode="json")]
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    current = subject.inspect_goal_research("A")["proposal"]
    requests, blockers = historical_requests(current)
    assert not blockers and len(requests) == 1
    assert requests[0].fields == ("time", "close", "high", "low") and requests[0].warmup == 60
    assert requests[0].export.timeframe == "M1"
    view = subject.inspect_goal_research("A")
    payload["specification"]["data_requirements"][1]["timeframe"] = "M15"
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    current = subject.inspect_goal_research("A")["proposal"]
    requests, blockers = historical_requests(current)
    assert not blockers and {r.export.timeframe for r in requests} == {"M1", "M15"}
    assert current.brief == view["proposal"].brief
    assert current.head.content.development.historical_window == view["proposal"].head.content.development.historical_window
    assert current.head.content.development.transaction_costs == view["proposal"].head.content.development.transaction_costs
    assert not subject.research_history_client.calls and not current.reviews and not current.execution_allowed


def test_conflicting_same_timeframe_requirement_cannot_be_hidden_by_a_valid_sibling(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    payload = specification()
    payload["specification"]["data_requirements"] = [requirement([indicator(name="first")]).model_dump(mode="json"),
        requirement([indicator(name="second")], warmup_bars=0).model_dump(mode="json")]
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    requests, blockers = historical_requests(subject.inspect_goal_research("A")["proposal"])
    assert not requests and any("WARMUP_BELOW_DEPENDENCY_MINIMUM" in code for code in blockers)
    assert not subject.research_history_client.calls


def test_r2_verifies_resolved_raw_dependencies_not_indicator_columns(tmp_path):
    from scripts.test_research_evidence_verification import setup_source, research, inspect
    from scripts.test_research_proposal import SCOPE, create
    from scripts.test_historical_research_dataset import REQUEST, START, bars
    from src.services.trading.research.evidence_verification import HistoricalEvidenceVerifier
    from src.services.trading.research.proposal import ResearchContent, ResearchDevelopment
    earlier = START - timedelta(hours=1)
    source, ref = setup_source(tmp_path, rows=bars(120, earlier), request=replace(REQUEST, start=earlier.isoformat()))
    development = ResearchDevelopment.model_validate_json(json.dumps({"specification": {
        "data_requirements": [requirement([indicator()]).model_dump(mode="json")]}}))
    proposal = create(ResearchContent.model_validate({**research(ref).model_dump(), "development": development}))
    proof = inspect(HistoricalEvidenceVerifier(SCOPE, (source,)), proposal, ref)
    assert proof.outcome == "VERIFIED_FOR_DECLARED_SCOPE"
    assert proof.strategy_performance == "NOT_ASSESSED" and not proposal.reviews


def test_legacy_raw_specification_hash_payload_is_preserved():
    payload = {"dataset": "OHLCV", "fields": ["close"], "symbol": "XAUUSD", "timeframe": "M1",
               "lookback_bars": 20, "warmup_bars": 5, "usage": "RESEARCH_ONLY"}
    parsed = ComputationalDataRequirement.model_validate_json(json.dumps(payload))
    dumped = parsed.model_dump(mode="json")
    assert "computations" not in dumped
    assert resolve_data_dependencies(parsed)["raw_fields"] == ["time", "close"]
    spec = ComputationalSpecification.model_validate_json(json.dumps({"data_requirements": [payload]}))
    assert spec.as_dict()["data_requirements"] == [payload]
    assert "fields" in resolve_data_dependencies(requirement(fields=[], lookback_bars=20, warmup_bars=0))["blockers"]


def test_ui_dependency_projection_is_read_only_and_isolated(app, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    subject, db, _ = setup(app, tmp_path, monkeypatch, window=False)
    view = subject.inspect_goal_research("A")
    payload = specification(window=False)
    payload["specification"]["data_requirements"] = [requirement([custom()]).model_dump(mode="json")]
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    page = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
_render_goal_research(st.session_state.subject)
''')
    page.session_state.subject = subject
    page.session_state.current_session_id = "A"
    page.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    page.run()
    assert not page.exception
    assert any(expander.label == "Raw data and derived computation dependencies" for expander in page.expander)
    projection = subject.inspect_goal_historical_data("A")
    assert projection["dependencies"][0]["unsupported_computations"] == ["range"]
    assert not projection["requests"] and not subject.research_history_client.calls
    page.session_state.current_session_id = "B"
    page.session_state.messages = copy.deepcopy(db.docs["B"]["messages"])
    page.run()
    assert not page.exception and not page.text_area
