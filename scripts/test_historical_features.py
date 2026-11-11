"""Offline fixture evidence only; no broker, provider or actual market computation."""
import copy
from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from scripts.test_goal_research_workflow import app
from scripts.test_goal_historical_data_integration import setup, specification, acquire, approve, review
from src.config import Config
from src.services.trading.reasoning import strategy_evidence as core
from src.services.trading.research import historical_features as features
from src.services.trading.research.descriptive_computation import DescriptiveComputationApproval
from src.services.trading.research.historical_dataset import canonical_bytes, checksum


CASES = [
    ("EMA", {"period": 3}, "value"), ("SMA", {"period": 4}, "value"),
    ("RSI", {"period": 5}, "value"), ("ATR", {"period": 6}, "value"),
    ("MACD", {"fast_period": 3, "slow_period": 7, "signal_period": 2}, "signal"),
    ("BOLLINGER_BANDS", {"period": 5, "deviation": 1.7}, "lower"),
]


def declaration(indicator="EMA", parameters=None, output="value", name="feature"):
    return {"name": name, "indicator_id": indicator, "parameters": parameters or {"period": 3}, "output_field": output}


def configured(app, tmp_path, monkeypatch, *, computations=None, multi=False, costs=True, ready=True, signal_rules=None, confirmed=False):
    subject, db, history = setup(app, tmp_path, monkeypatch, costs=costs)
    view = subject.inspect_goal_research("A")
    payload = specification(costs=costs)
    if signal_rules is not None:
        payload["signal_rules"] = signal_rules
    requirement = payload["specification"]["data_requirements"][0]
    requirement.update(fields=[], lookback_bars=None, warmup_bars=None,
                       computations=computations or [declaration()])
    if multi:
        payload["specification"]["data_requirements"].append({**copy.deepcopy(requirement),
            "timeframe": "M15", "computations": [declaration(parameters={"period": 2}, name="slow")]})
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id,
                                 development_json=json.dumps(payload), confirmed_signal_rules=confirmed)
    if ready:
        for report in subject.inspect_goal_historical_data("A")["requests"]:
            view = subject.inspect_goal_research("A")
            subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, report["request_id"])
        for index in range(len(subject.inspect_goal_historical_data("A")["requests"])):
            view = subject.inspect_goal_research("A")
            report = subject.inspect_goal_historical_data("A")["requests"][index]
            subject.approve_goal_history("A", view["key"], view["proposal"].head.revision_id,
                                        report["request_id"], report["manifest_sha256"])
        review(subject)
        for report in subject.inspect_goal_historical_data("A")["requests"]:
            view = subject.inspect_goal_research("A")
            subject.prepare_goal_evaluation_input("A", view["key"], view["proposal"].head.revision_id,
                                                  report["request_id"], feature_only=not costs)
    return subject, db, history


def context(subject):
    proposal = subject.inspect_goal_research("A")["proposal"]
    record = subject._goal_research_context("A")[6]
    root = Config.DATA_DIR / "research"
    inputs = features.bound_feature_inputs(root, proposal, record)
    descriptor, loaded = features.inspect_feature_request(root, proposal, inputs, now=datetime.now(timezone.utc))
    return root, proposal, inputs, descriptor, loaded


def compute(subject, **kwargs):
    view = subject.inspect_goal_research("A")
    ready = subject.inspect_goal_research_features("A")
    return subject.compute_goal_research_features("A", view["key"], view["proposal"].head.revision_id,
                                                  ready["request"]["request_sha256"], **kwargs)


@pytest.mark.parametrize("indicator,parameters,output", CASES)
def test_exact_production_prefix_parity_and_continuous_oos_seed(app, tmp_path, monkeypatch, indicator, parameters, output):
    subject, _, _ = configured(app, tmp_path, monkeypatch, computations=[declaration(indicator, parameters, output)])
    _, _, _, descriptor, loaded = context(subject)
    actual = features.calculate_historical_features(loaded, descriptor["calculations"])
    series = actual["series"][0]
    package = loaded[0][3]
    history = [*package["partitions"]["IS"]["warmup_context_not_scored"],
               *package["partitions"]["IS"]["rows"], *package["partitions"]["OOS"]["rows"]]
    spec = core.IndicatorSpec(indicator, "M1", tuple(sorted(parameters.items())), "reference")
    for index, row in enumerate(series["rows"]):
        assert row["time"] == history[index]["time"] and row["completed_at"] == row["time"] + 60
        if index + 1 < series["warmup"]:
            assert row["status"] == "INSUFFICIENT_HISTORY" and row["value"] is None
        else:
            expected = core.calculate_indicator_snapshot((spec,), history[:index + 1])["indicators"]["reference"]
            assert row["value"] == expected["current" if output == "value" else output]
    assert actual["status"] == "COMPUTED"
    assert sum(row["partition"] == "IS" for row in series["rows"]) == 30
    assert sum(row["partition"] == "OOS" for row in series["rows"]) == 30


def test_multitimeframe_alignment_never_uses_future_or_resets_oos(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch, multi=True)
    _, _, _, descriptor, loaded = context(subject)
    before = features.calculate_historical_features(loaded, descriptor["calculations"])
    assert len(before["series"]) == 2
    for partition, rows in before["aligned_partitions"].items():
        for row in rows:
            assert all(value["source_completed_at"] <= row["evaluation_time"]
                       for value in row["values"].values() if value["source_completed_at"] is not None)
    changed = copy.deepcopy(loaded)
    for row in changed[0][3]["partitions"]["OOS"]["rows"]:
        row["close"] += 100
    after = features.calculate_historical_features(changed, descriptor["calculations"])
    assert before["aligned_partitions"]["IS"] == after["aligned_partitions"]["IS"]
    assert before["aligned_partitions"]["OOS"] != after["aligned_partitions"]["OOS"]


def test_shared_macd_components_reuse_one_core_calculation(app, tmp_path, monkeypatch):
    params = {"fast_period": 3, "slow_period": 7, "signal_period": 2}
    subject, _, _ = configured(app, tmp_path, monkeypatch, computations=[
        declaration("MACD", params, output, name=output) for output in ("line", "signal", "histogram")])
    _, _, _, descriptor, loaded = context(subject)
    calls, original = [], core.calculate_indicator_snapshot
    def counted(*args):
        calls.append(len(args[1]))
        return original(*args)
    monkeypatch.setattr(core, "calculate_indicator_snapshot", counted)
    result = features.calculate_historical_features(loaded, descriptor["calculations"])
    assert len(calls) == len(result["series"][0]["rows"]) - 26
    assert len(result["series"]) == 3


def test_costs_missing_does_not_block_feature_input_or_compute(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch, costs=False)
    root, proposal, inputs, descriptor, loaded = context(subject)
    assert loaded[0][3]["preparation_purpose"] == "FEATURE_INPUT_ONLY"
    assert loaded[0][3]["costs"]["missing"]
    report = subject.inspect_goal_historical_data("A")["requests"][0]
    with pytest.raises(ValueError, match="INPUT_NOT_READY"):
        subject.prepare_goal_evaluation_input("A", subject.inspect_goal_research("A")["key"],
                                             proposal.head.revision_id, report["request_id"])
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="OPERATOR_APPROVAL_REQUIRED"):
        compute(subject)
    result = compute(subject, approved=True)
    assert result["status"] == "PASS" and result["result"]["status"] == "COMPUTED"
    path = root / "results" / f"research_features_{result['result_sha256']}.json"
    assert checksum(path.read_bytes()) == result["result_sha256"]
    assert canonical_bytes(result["result"]) == path.read_bytes()
    assert all(path.read_bytes() == payload for path, payload in before.items())
    monkeypatch.setattr(features, "run_historical_features", lambda *a, **k: pytest.fail("duplicate computation"))
    assert compute(subject, approved=True)["result_sha256"] == result["result_sha256"]
    assert not result["result"]["execution_allowed"] and not result["result"]["strategy_evaluated"]


@pytest.mark.parametrize("target", ["input", "dataset", "manifest", "revision", "approval", "source"])
def test_tampered_or_unapproved_input_never_computes(app, tmp_path, monkeypatch, target):
    subject, db, _ = configured(app, tmp_path, monkeypatch)
    root, proposal, inputs, descriptor, loaded = context(subject)
    request, source, pin = inputs[0]
    if target == "input":
        (root / "inputs" / f"research_evaluation_input_{pin}.json").write_bytes(b"tampered fixture")
    elif target in {"dataset", "manifest"}:
        (source.folder / ("data.jsonl" if target == "dataset" else "manifest.json")).write_bytes(b"tampered fixture")
    elif target == "revision":
        inputs = [(replace(request, revision_id="wrong"), source, pin)]
    elif target == "source":
        record = next(iter(db.docs["A"]["research_proposals"].values()))
        next(iter(record["historical"].values())).pop("source_approval")
        with pytest.raises(ValueError, match="SOURCE_NOT_APPROVED"):
            features.bound_feature_inputs(root, proposal, record)
        return
    else:
        proposal = proposal.model_copy(update={"reviews": ()})
    monkeypatch.setattr(features, "calculate_historical_features", lambda *a: pytest.fail("unauthorized math"))
    approval = DescriptiveComputationApproval(decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", algorithm=features.ALGORITHM,
        proposal_id=proposal.proposal_id, revision_id=proposal.head.revision_id, scope=proposal.scope,
        input_sha256=descriptor["request_sha256"], output_directory=str((root / "results").absolute()))
    with pytest.raises((ValueError, OSError)):
        features.run_historical_features(root, proposal, inputs, approval=approval, now=datetime.now(timezone.utc))
    assert not list((root / "results").glob("*"))


@pytest.mark.parametrize("change", [{"parameters": {"period": 2.5}}, {"parameters": {}},
                                   {"output_field": "made_up"}])
def test_unsupported_parameters_or_outputs_fail_without_defaults(app, tmp_path, monkeypatch, change):
    subject, _, _ = configured(app, tmp_path, monkeypatch, computations=[{**declaration(), **change}], ready=False)
    report = subject.inspect_goal_research_features("A")
    assert report["status"] == "BLOCKED" and not report["supported"]
    assert report["blocked"][0]["status"] == "BLOCKED" and report["blockers"]
    assert not subject.research_history_client.calls


def test_custom_declared_computation_never_executed(app, tmp_path, monkeypatch):
    custom = {"name": "custom", "definition": "close * close, inert declaration only", "parameters": {},
              "inputs": [{"field": "close", "kind": "RAW_MT5", "data_type": "FLOAT64"}],
              "output_type": "FLOAT64", "lookback_bars": 2, "warmup_bars": 0}
    subject, _, _ = configured(app, tmp_path, monkeypatch, computations=[declaration(), custom])
    result = compute(subject, approved=True)
    assert result["status"] == "PASS" and result["result"]["status"] == "PARTIAL"
    assert result["result"]["blocked_computations"][0]["status"] == "DECLARED_UNVERIFIED"
    assert len(result["result"]["series"]) == 1


def test_resource_budget_fails_before_production_math(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    _, _, _, descriptor, loaded = context(subject)
    monkeypatch.setattr(features, "MAX_PREFIX_WORK", 1)
    monkeypatch.setattr(core, "calculate_indicator_snapshot", lambda *a: pytest.fail("budget exceeded before math"))
    with pytest.raises(ValueError, match="PREFIX_BUDGET_EXCEEDED"):
        features.calculate_historical_features(loaded, descriptor["calculations"])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reverse", "nan", "future", "wrong_partition"])
def test_rehashed_invalid_package_is_not_trusted(app, tmp_path, monkeypatch, mutation):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    root, proposal, inputs, _, loaded = context(subject)
    package = copy.deepcopy(loaded[0][3])
    rows = package["partitions"]["IS"]["rows"]
    if mutation == "missing":
        rows[0].pop("close")
    elif mutation == "duplicate":
        rows[1]["time"] = rows[0]["time"]
    elif mutation == "reverse":
        rows.reverse()
    elif mutation == "nan":
        rows[0]["close"] = None
    elif mutation == "future":
        rows[0]["time"] += 1000000
    else:
        package["partitions"]["OOS"]["rows"].append(rows[0])
    payload = canonical_bytes(package)
    pin = checksum(payload)
    (root / "inputs" / f"research_evaluation_input_{pin}.json").write_bytes(payload)
    request, source, _ = inputs[0]
    with pytest.raises(ValueError, match="EVALUATION_INPUT_MISMATCH"):
        features.inspect_feature_request(root, proposal, [(request, source, pin)], now=datetime.now(timezone.utc))


def test_distinct_declared_warmups_and_invalid_core_results_are_explicit(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch, computations=[
        declaration(name="short"), {**declaration(name="long"), "warmup_bars": 15}])
    _, _, _, descriptor, loaded = context(subject)
    result = features.calculate_historical_features(loaded, descriptor["calculations"])
    assert result["series"][0]["rows"][10]["value"] is not None
    assert result["series"][1]["rows"][10]["status"] == "INSUFFICIENT_HISTORY"
    monkeypatch.setattr(core, "calculate_indicator_snapshot", lambda *a: (_ for _ in ()).throw(ValueError("INDICATOR_RESULT_INVALID")))
    result = features.calculate_historical_features(loaded, descriptor["calculations"])
    assert result["status"] == "PARTIAL"
    assert all(row["value"] is None for item in result["series"] for row in item["rows"])
    assert result["series"][0]["rows"][-1]["status"] == "PRODUCTION_INDICATOR_BLOCKED"


@pytest.mark.parametrize("field,value", [("algorithm", "HIGH_MINUS_LOW_V1"), ("input_sha256", "0" * 64),
                                       ("revision_id", "wrong_revision"), ("output_directory", "wrong_directory")])
def test_wrong_computation_approval_is_rejected_before_math(app, tmp_path, monkeypatch, field, value):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    root, proposal, inputs, descriptor, _ = context(subject)
    payload = dict(decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", algorithm=features.ALGORITHM,
        proposal_id=proposal.proposal_id, revision_id=proposal.head.revision_id, scope=proposal.scope,
        input_sha256=descriptor["request_sha256"], output_directory=str((root / "results").absolute()))
    payload[field] = value
    approval = DescriptiveComputationApproval(**payload)
    monkeypatch.setattr(features, "calculate_historical_features", lambda *a: pytest.fail("unauthorized math"))
    with pytest.raises(ValueError, match="APPROVAL_MISMATCH"):
        features.run_historical_features(root, proposal, inputs, approval=approval, now=datetime.now(timezone.utc))


def test_reproducible_artifact_no_overwrite_and_stale_revision_hides_result(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    root, proposal, inputs, descriptor, _ = context(subject)
    approval = DescriptiveComputationApproval(decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", algorithm=features.ALGORITHM,
        proposal_id=proposal.proposal_id, revision_id=proposal.head.revision_id, scope=proposal.scope,
        input_sha256=descriptor["request_sha256"], output_directory=str((root / "results").absolute()))
    first = features.run_historical_features(root, proposal, inputs, approval=approval, now=datetime.now(timezone.utc))
    payload = first.read_bytes()
    second = features.run_historical_features(root, proposal, inputs, approval=approval, now=datetime.now(timezone.utc))
    assert first == second and second.read_bytes() == payload
    first.write_bytes(b"tampered fixture output")
    with pytest.raises(ValueError, match="EXISTING_PACKAGE_MISMATCH"):
        features.run_historical_features(root, proposal, inputs, approval=approval, now=datetime.now(timezone.utc))
    assert first.read_bytes() == b"tampered fixture output"
    first.write_bytes(payload)
    compute(subject, approved=True)
    view = subject.inspect_goal_research("A")
    subject.revise_goal_research("A", view["key"], proposal.head.revision_id, "New fixture hypothesis requires its own specification.")
    assert "result" not in subject.inspect_goal_research_features("A")


def test_concurrent_revision_change_cannot_publish_as_current(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    original = features.run_historical_features
    def changed(*args, **kwargs):
        path = original(*args, **kwargs)
        view = subject.inspect_goal_research("A")
        subject.revise_goal_research("A", view["key"], view["proposal"].head.revision_id, "Changed while math was running.")
        return path
    monkeypatch.setattr(features, "run_historical_features", changed)
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        compute(subject, approved=True)
    assert "result" not in subject.inspect_goal_research_features("A")


def test_stale_foreign_deleted_and_running_claim_fail_closed(app, tmp_path, monkeypatch):
    subject, db, history = configured(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    ready = subject.inspect_goal_research_features("A")
    args = (view["key"], view["proposal"].head.revision_id, ready["request"]["request_sha256"])
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.compute_goal_research_features("B", *args, approved=True)
    with pytest.raises(ValueError, match="APPROVAL_STALE"):
        subject.compute_goal_research_features("A", *args[:2], "0" * 64, approved=True)
    with history.research_generation_lock(view["key"]):
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            subject.compute_goal_research_features("A", *args, approved=True)
    record = db.docs["A"]["research_proposals"][view["key"]]
    record["feature_run"] = {"status": "RUNNING", "request_sha256": args[-1]}
    with pytest.raises(ValueError, match="NO_AUTO_RETRY"):
        subject.compute_goal_research_features("A", *args, approved=True, retry=True)
    del db.docs["A"]
    with pytest.raises(ValueError, match="CONVERSATION_UNAVAILABLE"):
        subject.compute_goal_research_features("A", *args, approved=True)


def test_failure_visible_sanitized_and_explicit_retry_only(app, tmp_path, monkeypatch):
    subject, _, _ = configured(app, tmp_path, monkeypatch)
    original = features.run_historical_features
    def fail(*a, **k):
        raise RuntimeError("private fixture path must not leak")
    monkeypatch.setattr(features, "run_historical_features", fail)
    failed = compute(subject, approved=True)
    assert failed["status"] == "FAILED" and failed["reason"] == "RESEARCH_FEATURE_CALCULATION_FAILED"
    with pytest.raises(ValueError, match="NO_AUTO_RETRY"):
        compute(subject, approved=True)
    monkeypatch.setattr(features, "run_historical_features", original)
    assert compute(subject, approved=True, retry=True)["status"] == "PASS"


def test_streamlit_explicit_approval_results_rerun_and_conversation_isolation(app, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    subject, db, _ = configured(app, tmp_path, monkeypatch, costs=False)
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
    assert next(b for b in page.button if b.label == "Compute research features").disabled
    next(c for c in page.checkbox if c.label.startswith("I authorize only these pinned")).set_value(True).run()
    next(b for b in page.button if b.label == "Compute research features").click().run()
    assert not page.exception and len(page.dataframe) == 1
    page.run()
    assert not page.exception and not any(b.label == "Compute research features" for b in page.button)
    page.session_state.current_session_id = "B"
    page.session_state.messages = copy.deepcopy(db.docs["B"]["messages"])
    page.run()
    assert not page.exception and not page.dataframe
