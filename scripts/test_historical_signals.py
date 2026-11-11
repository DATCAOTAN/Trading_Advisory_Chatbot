"""Bounded offline software fixtures, never live market or broker evidence."""
import copy
from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from scripts.test_goal_research_workflow import app
from scripts.test_historical_features import configured, compute
from src.config import Config
from src.services.trading.research import historical_signals as signals
from src.services.trading.research.descriptive_computation import DescriptiveComputationApproval
from src.services.trading.research.historical_dataset import canonical_bytes, checksum
from src.services.trading.research.proposal import ResearchSignalRule


LEFT, RIGHT = "requirement_0:feature", "requirement_0:other"


def rule(operator="GREATER_THAN", *, action="ENTRY", name="entry", right=None, constants=None, **changes):
    return {"name": name, "action": action, "conditions": [{"operator": operator, "left": LEFT, "right": right,
        "constants": constants if constants is not None else ([] if right or operator in {"RISING", "FALLING"} else [1])}],
        "combination": "ALL", "timing": "COMPLETED_BAR_CLOSE", "evaluation_timeframe": "M1", **changes}


def pure_features(left=(0., 2., 3., 0., 3.), right=None):
    series = []
    for name, values in ((LEFT, left), (RIGHT, right if right is not None else [1.] * len(left))):
        series.append({"id": name, "timeframe": "M1", "rows": [
            {"time": i * 60, "completed_at": (i + 1) * 60, "partition": "IS" if i < 3 else "OOS",
             "value": value, "status": "COMPUTED" if value is not None else "INSUFFICIENT_HISTORY"}
            for i, value in enumerate(values)]})
    return {"series": series}


def contract(*rules):
    return {"supported": [ResearchSignalRule.model_validate_json(json.dumps(item)).model_dump(mode="json") for item in rules],
            "unresolved": []}


def ready(app, tmp_path, monkeypatch, **kwargs):
    subject, db, history = configured(app, tmp_path, monkeypatch, signal_rules=[rule()], confirmed=True, **kwargs)
    compute(subject, approved=True)
    return subject, db, history


def evaluate(subject, **kwargs):
    view = subject.inspect_goal_research("A")
    request = subject.inspect_goal_research_signals("A")["request"]
    return subject.evaluate_goal_research_signals("A", view["key"], view["proposal"].head.revision_id,
                                                request["request_sha256"], **kwargs)


@pytest.mark.parametrize("operator,expected", [
    ("GREATER_THAN", [False, True, True, False, True]), ("LESS_THAN", [True, False, False, True, False]),
    ("BETWEEN", [True, True, True, True, True]), ("RISING", [None, True, True, False, True]),
    ("FALLING", [None, False, False, True, False]),
    ("CROSSES_ABOVE", [None, True, False, False, True]), ("CROSSES_BELOW", [None, False, False, True, False]),
])
def test_core_level_edge_and_rearm_semantics(operator, expected):
    item = rule(operator, right=RIGHT if operator.startswith("CROSSES") else None,
                constants=[0, 3] if operator == "BETWEEN" else None)
    result = signals.evaluate_historical_signals(pure_features(), contract(item))
    rows = result["partitions"]["IS"] + result["partitions"]["OOS"]
    assert [row["triggered"] for row in rows] == expected
    if operator == "CROSSES_ABOVE":
        assert rows[2]["conditions"][0]["signal_state"] == "WAITING_FOR_REARM"
        assert rows[3]["conditions"][0]["signal_state"] == "REARMED"
        assert rows[4]["conditions"][0]["signal_state"] == "TRIGGERED"


@pytest.mark.parametrize("combination,expected", [("ALL", [False, False, False, False, False]),
                                              ("ANY", [True, True, True, True, True])])
def test_multiple_conditions_and_independent_exit_signals(combination, expected):
    entry = rule(combination=combination)
    entry["conditions"].append({"operator": "LESS_THAN", "left": LEFT, "constants": [1]})
    result = signals.evaluate_historical_signals(pure_features(), contract(entry, rule("LESS_THAN", action="EXIT", name="exit")))
    rows = result["partitions"]["IS"] + result["partitions"]["OOS"]
    assert [row["triggered"] for row in rows if row["action"] == "ENTRY"] == expected
    assert sum(part["exit_signals"] for part in result["summary"].values()) == 2


def test_missing_values_are_unknown_no_old_valid_fallback_or_gap_cross():
    result = signals.evaluate_historical_signals(pure_features(left=(0., 2., None, 3., 0.)),
                                                  contract(rule("CROSSES_ABOVE", right=RIGHT)))
    rows = result["partitions"]["IS"] + result["partitions"]["OOS"]
    assert [row["triggered"] for row in rows] == [None, True, None, None, False]
    assert rows[3]["conditions"][0]["sources"][LEFT]["previous"]["value"] is None
    assert result["status"] == "PARTIAL"


def test_oos_boundary_is_not_a_rearm_reset_and_future_values_do_not_leak():
    features = pure_features(left=(0., 2., 3., 4., 5.))
    before = signals.evaluate_historical_signals(features, contract(rule("CROSSES_ABOVE", right=RIGHT)))
    assert before["partitions"]["OOS"][0]["triggered"] is False
    assert before["partitions"]["OOS"][0]["conditions"][0]["signal_state"] == "WAITING_FOR_REARM"
    features["series"][0]["rows"][-1]["value"] = -100
    after = signals.evaluate_historical_signals(features, contract(rule("CROSSES_ABOVE", right=RIGHT)))
    assert before["partitions"]["IS"] == after["partitions"]["IS"]
    assert before["partitions"]["OOS"][:-1] == after["partitions"]["OOS"][:-1]


def test_multi_timeframe_previous_clock_prevents_repeated_slow_edge():
    features = pure_features(left=[1.5] * 35, right=[1.5] * 35)
    slow = "requirement_1:slow"
    features["series"].append({"id": slow, "timeframe": "M15", "rows": [
        {"time": point - 900, "completed_at": point, "partition": "WARMUP_CONTEXT" if point == 0 else "IS",
         "value": value, "status": "COMPUTED"} for point, value in ((0, 0.), (900, 1.), (1800, 2.))]})
    item = rule("CROSSES_ABOVE", right=RIGHT)
    item["conditions"][0]["left"] = slow
    result = signals.evaluate_historical_signals(features, contract(item))
    rows = result["partitions"]["IS"] + result["partitions"]["OOS"]
    assert [row["signal_time"] for row in rows if row["triggered"] is True] == [1800]
    for row in rows:
        for source in row["conditions"][0]["sources"].values():
            assert source["current"]["source_completed_at"] <= row["signal_time"]
            if source["previous"]["source_completed_at"] is not None:
                assert source["previous"]["source_completed_at"] <= row["signal_time"] - 60


@pytest.mark.parametrize("change,blocker", [
    ({"timing": None}, "SIGNAL_TIMING_REQUIRED"), ({"evaluation_timeframe": None}, "SIGNAL_EVALUATION_CLOCK_UNAVAILABLE"),
    ({"timing": "NEXT_BAR_OPEN"}, "SIGNAL_TIMING_UNSUPPORTED"),
    ({"combination": None}, "SIGNAL_CONDITIONS_AND_COMBINATION_REQUIRED"),
    ({"conditions": [{"left": LEFT, "operator": "CUSTOM_RULE"}]}, "SIGNAL_OPERATOR_UNSUPPORTED_OR_MISSING"),
    ({"conditions": [{"left": "not_declared", "operator": "GREATER_THAN", "constants": [0]}]}, "SIGNAL_VERIFIED_FEATURE_REFERENCE_REQUIRED"),
    ({"conditions": [{"left": LEFT, "operator": "CROSSES_ABOVE", "constants": [0]}]}, "SIGNAL_CROSS_RIGHT_OPERAND_REQUIRED"),
    ({"conditions": [{"left": LEFT, "operator": "BETWEEN", "constants": [3, 1]}]}, "SIGNAL_CONSTANTS_INVALID_OR_MISSING"),
])
def test_unresolved_contract_never_guesses_free_text_or_defaults(app, tmp_path, monkeypatch, change, blocker):
    subject, _, _ = configured(app, tmp_path, monkeypatch, signal_rules=[rule(**change)], confirmed=True, ready=False)
    report = subject.inspect_goal_research_signals("A")
    assert report["status"] == "BLOCKED" and report["reason"] == "RESEARCH_SIGNAL_RULES_UNRESOLVED"
    assert blocker in report["unresolved"][0]["blockers"] and not report["supported"]
    assert not subject.research_history_client.calls


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf")])
def test_strict_numeric_constants(value):
    with pytest.raises(ValidationError):
        ResearchSignalRule.model_validate_json(json.dumps(rule(constants=[value])))


def test_full_connected_artifact_approval_idempotency_and_no_mutation(app, tmp_path, monkeypatch):
    subject, db, _ = ready(app, tmp_path, monkeypatch, costs=False)
    root = Config.DATA_DIR / "research"
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    proposal_before = subject.inspect_goal_research("A")["proposal"].to_json()
    with pytest.raises(ValueError, match="OPERATOR_APPROVAL_REQUIRED"):
        evaluate(subject)
    result = evaluate(subject, approved=True)
    assert result["status"] == "PASS" and result["result"]["summary"]["IS"]["entry_signals"] == 30
    assert result["result"]["summary"]["OOS"]["entry_signals"] == 30
    artifact = root / "results" / f"research_signals_{result['result_sha256']}.json"
    assert checksum(artifact.read_bytes()) == result["result_sha256"]
    assert canonical_bytes(result["result"]) == artifact.read_bytes()
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert subject.inspect_goal_research("A")["proposal"].to_json() == proposal_before
    assert not any(result["result"][name] for name in ("execution_allowed", "strategy_evaluated", "fills_simulated", "generated_code_allowed"))
    monkeypatch.setattr(signals, "run_historical_signals", lambda *a, **k: pytest.fail("duplicate execution"))
    assert evaluate(subject, approved=True)["result_sha256"] == result["result_sha256"]
    assert "research_proposals" not in db.docs["B"]


def test_artifact_is_reproducible_no_overwrite_and_approval_is_operation_specific(app, tmp_path, monkeypatch):
    subject, _, _ = ready(app, tmp_path, monkeypatch)
    proposal = subject.inspect_goal_research("A")["proposal"]
    record = subject._goal_research_context("A")[6]
    root = Config.DATA_DIR / "research"
    now = datetime.now(timezone.utc)
    descriptor, _ = signals.inspect_signal_request(root, proposal, record, now=now)
    approval = DescriptiveComputationApproval(decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION",
        proposal_id=proposal.proposal_id, revision_id=proposal.head.revision_id, scope=proposal.scope,
        input_sha256=descriptor["request_sha256"], algorithm=signals.ALGORITHM, output_directory=str(root / "results"))
    with pytest.raises(ValueError, match="APPROVAL_MISMATCH"):
        signals.run_historical_signals(root, proposal, record, now=now,
            approval=approval.model_copy(update={"algorithm": "HISTORICAL_FEATURES_V1"}))
    path = signals.run_historical_signals(root, proposal, record, now=now, approval=approval)
    before = path.read_bytes()
    assert signals.run_historical_signals(root, proposal, record, now=now, approval=approval) == path
    assert path.read_bytes() == before
    path.write_bytes(b"conflicting bytes")
    with pytest.raises(ValueError, match="EXISTING_PACKAGE_MISMATCH"):
        signals.run_historical_signals(root, proposal, record, now=now, approval=approval)
    assert path.read_bytes() == b"conflicting bytes"


def test_no_implicit_rule_confirmation_or_feature_computation(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch, signal_rules=[rule()], confirmed=False)
    assert subject.inspect_goal_research_signals("A")["reason"] == "RESEARCH_SIGNAL_USER_REVIEW_REQUIRED"
    view = subject.inspect_goal_research("A")
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id,
        development_json=view["proposal"].head.content.development.model_dump_json(), confirmed_signal_rules=True)
    assert subject.inspect_goal_research_signals("A")["reason"] == "RESEARCH_VERIFIED_FEATURE_RESULT_REQUIRED"
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


def test_missing_clock_bar_does_not_bridge_crossing():
    features = pure_features(left=(0., 0., 3., 4., 5.))
    for series in features["series"]:
        del series["rows"][1]
    report = signals.evaluate_historical_signals(features, contract(rule("CROSSES_ABOVE", right=RIGHT)))
    row = report["partitions"]["IS"][-1]
    assert row["signal_time"] == 180 and row["triggered"] is None
    assert row["conditions"][0]["sources"][LEFT]["previous"]["status"] == "PREVIOUS_CLOCK_BAR_UNAVAILABLE"


@pytest.mark.parametrize("target", ["feature", "input", "dataset", "review", "missing_feature"])
def test_tampered_binding_blocked_before_evaluation(app, tmp_path, monkeypatch, target):
    subject, db, _ = ready(app, tmp_path, monkeypatch)
    root = Config.DATA_DIR / "research"
    view = subject.inspect_goal_research("A")
    record = db.docs["A"]["research_proposals"][view["key"]]
    if target == "review":
        record["signal_rules_review"]["revision_id"] = "foreign_revision"
    elif target == "missing_feature":
        record.pop("feature_run")
    else:
        if target == "feature":
            path = root / "results" / f"research_features_{record['feature_run']['result_sha256']}.json"
        elif target == "input":
            path = Config.DATA_DIR / next(iter(record["historical"].values()))["input_package"]["path"]
        else:
            path = root / "mt5" / next(iter(record["historical"].values()))["dataset_id"] / "data.jsonl"
        path.write_bytes(b"tampered fixture only")
    monkeypatch.setattr(signals, "evaluate_historical_signals", lambda *a: pytest.fail("unverified calculation"))
    report = subject.inspect_goal_research_signals("A")
    assert report["status"] == "BLOCKED" and "result" not in report


def test_stale_foreign_concurrent_deleted_and_running_claims(app, tmp_path, monkeypatch):
    subject, db, history = ready(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    args = (view["key"], view["proposal"].head.revision_id, subject.inspect_goal_research_signals("A")["request"]["request_sha256"])
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.evaluate_goal_research_signals("B", *args, approved=True)
    with pytest.raises(ValueError, match="SIGNAL_APPROVAL_STALE"):
        subject.evaluate_goal_research_signals("A", *args[:2], "0" * 64, approved=True)
    with history.research_generation_lock(view["key"]):
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            subject.evaluate_goal_research_signals("A", *args, approved=True)
    record = db.docs["A"]["research_proposals"][view["key"]]
    record["signal_run"] = {"status": "RUNNING", "request_sha256": args[-1]}
    with pytest.raises(ValueError, match="NO_AUTO_RETRY"):
        evaluate(subject, approved=True, retry=True)
    del db.docs["A"]
    with pytest.raises(ValueError, match="CONVERSATION_UNAVAILABLE"):
        subject.evaluate_goal_research_signals("A", *args, approved=True)


def signal_page(subject, db):
    from streamlit.testing.v1 import AppTest
    page = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
_render_goal_research(st.session_state.subject)
''')
    page.session_state.subject = subject
    page.session_state.current_session_id = "A"
    page.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    page.run()
    return page


def test_streamlit_typed_rule_edit_and_confirmation(app, tmp_path, monkeypatch):
    subject, db, _ = configured(app, tmp_path, monkeypatch, ready=False)
    before = subject.inspect_goal_research("A")["proposal"]
    page = signal_page(subject, db)
    save = "Save and confirm typed rule revision"
    assert next(b for b in page.button if b.label == save).disabled
    next(c for c in page.checkbox if c.label.startswith("I confirm these typed rules")).set_value(True).run()
    editor = next(t for t in page.text_area if t.label == "Typed signal rules (JSON array)")
    editor.set_value(json.dumps([rule()]))
    next(b for b in page.button if b.label == save).click().run()
    assert not page.exception
    after = subject.inspect_goal_research("A")["proposal"]
    assert after.revisions[:-1] == before.revisions
    assert after.head.content.development.specification == before.head.content.development.specification
    assert after.head.content.development.signal_rules[0].name == "entry"
    assert subject.inspect_goal_research_signals("A")["reason"] == "RESEARCH_FEATURE_INPUT_PREPARATION_REQUIRED"
    assert not subject.research_history_client.calls


def test_changed_specification_invalidates_rule_confirmation(app, tmp_path, monkeypatch):
    subject, _, _ = ready(app, tmp_path, monkeypatch)
    evaluate(subject, approved=True)
    view = subject.inspect_goal_research("A")
    proposal = view["proposal"]
    development = proposal.head.content.development.model_dump(mode="json")
    development["specification"]["data_requirements"][0]["computations"][0]["parameters"]["period"] = 4
    subject.develop_goal_research("A", view["key"], proposal.head.revision_id, development_json=json.dumps(development))
    report = subject.inspect_goal_research_signals("A")
    assert report["reason"] == "RESEARCH_SIGNAL_USER_REVIEW_REQUIRED" and "result" not in report


def test_streamlit_explicit_signal_action_reload_and_conversation_isolation(app, tmp_path, monkeypatch):
    subject, db, _ = ready(app, tmp_path, monkeypatch)
    page = signal_page(subject, db)
    assert not page.exception
    assert next(b for b in page.button if b.label == "Evaluate historical signals").disabled
    next(c for c in page.checkbox if c.label.startswith("I authorize only these pinned historical signals")).set_value(True).run()
    next(b for b in page.button if b.label == "Evaluate historical signals").click().run()
    assert not page.exception and len(page.dataframe) == 3
    page.run()
    assert not page.exception and not any(b.label == "Evaluate historical signals" for b in page.button)
    page.session_state.current_session_id = "B"
    page.session_state.messages = copy.deepcopy(db.docs["B"]["messages"])
    page.run()
    assert not page.exception and not page.dataframe
