"""Offline software contracts. Fixture candles are not real MT5 acceptance evidence."""
from base64 import b64encode
import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import threading

import pytest
from pydantic import ValidationError

from scripts.test_goal_research_workflow import app, generate
from scripts.test_goal_strategy_specification import SPEC
from scripts.test_historical_research_dataset import bars, CONTRACT, START
from src.config import Config
from src.services.trading.research.data_integration import (
    approved_sources, cost_readiness, historical_requests, matching_history, receive_history_export,
)
from src.services.trading.research.historical_dataset import HistoricalDataRequest, checksum, persist_dataset
from src.services.trading.research.proposal import HistoricalEvaluationWindow
from src.services.trading.market.timeframes import timeframe_duration_seconds


def specification(*, window=True, costs=True):
    payload = copy.deepcopy(SPEC)
    payload["specification"]["data_requirements"][0].update(fields=["close", "spread"], lookback_bars=20, warmup_bars=5)
    if window:
        payload["historical_window"] = {"start": START.isoformat(), "end": (START + timedelta(hours=1)).isoformat(),
            "split": (START + timedelta(minutes=30)).isoformat(), "session_policy": "CONTINUOUS_UTC_V1"}
    if costs:
        payload["transaction_costs"] = [{"name": name, "value": 0, "unit": "USD/trade",
            "definition": "Explicit fixture-only research assumption, not broker evidence."}
            for name in ("spread", "commission", "swap", "slippage")]
    return payload


class HistoryClient:
    def __init__(self, root):
        self.root, self.calls, self.environment = root, [], "DEMO"
        self.callback = lambda: None

    def account_context(self):
        return {"status": "OK", "account_environment": self.environment}

    def export_research_history(self, payload, token):
        self.calls.append(copy.deepcopy(payload))
        self.callback()
        request = HistoricalDataRequest(**payload)
        start = datetime.fromisoformat(request.start)
        step = timeframe_duration_seconds(request.timeframe)
        count = int((datetime.fromisoformat(request.end) - start).total_seconds() // step)
        rows = bars(count, start)
        for index, row in enumerate(rows):
            row["time"] = int(start.timestamp()) + index * step
        folder, manifest = persist_dataset(self.root, request, rows, contract=CONTRACT,
            acquired_at=(START + timedelta(days=1)).isoformat())
        return {"status": "EXPORTED", "execution_allowed": False,
                "manifest": (folder / "manifest.json").read_text(),
                "data_base64": b64encode((folder / "data.jsonl").read_bytes()).decode()}


def setup(app, tmp_path, monkeypatch, *, window=True, costs=True):
    subject, db, history = app
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path / "app")
    view = generate(subject)
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id,
                                 development_json=json.dumps(specification(window=window, costs=costs)))
    subject.research_history_client = HistoryClient(tmp_path / "host")
    return subject, db, history


def acquire(subject):
    view = subject.inspect_goal_research("A")
    request = subject.inspect_goal_historical_data("A")["requests"][0]
    return subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, request["request_id"])


def approve(subject):
    view = subject.inspect_goal_research("A")
    report = subject.inspect_goal_historical_data("A")["requests"][0]
    return subject.approve_goal_history("A", view["key"], view["proposal"].head.revision_id,
                                       report["request_id"], report["manifest_sha256"])


def review(subject):
    view = subject.inspect_goal_research("A")
    return subject.review_goal_research("A", view["key"], view["proposal"].head.revision_id)


def prepare(subject):
    view = subject.inspect_goal_research("A")
    report = subject.inspect_goal_historical_data("A")["requests"][0]
    return subject.prepare_goal_evaluation_input("A", view["key"], view["proposal"].head.revision_id, report["request_id"])


@pytest.mark.parametrize("patch", [
    {"start": "2026-11-02T10:00:00"}, {"end": START.isoformat()},
    {"split": START.isoformat()}, {"split": (START + timedelta(hours=2)).isoformat()},
    {"session_policy": "IMPLICIT_SESSIONS"},
])
def test_typed_window_rejects_naive_overlap_and_invalid_policy(patch):
    payload = specification()["historical_window"]
    with pytest.raises((ValueError, ValidationError)):
        HistoricalEvaluationWindow.model_validate_json(json.dumps({**payload, **patch}))


def test_missing_window_blocks_only_acquisition_cost_editor_and_revisions_still_work(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch, window=False, costs=False)
    report = subject.inspect_goal_historical_data("A")
    assert not report["requests"] and "historical_window.start" in report["blockers"]
    assert report["costs"]["missing"] == ["spread", "commission", "swap", "slippage"]
    assert not subject.research_history_client.calls
    assert subject.inspect_goal_research("A")["proposal"].head.content.development is not None


@pytest.mark.parametrize("patch,code", [
    ({"warmup_bars": None}, "warmup_bars"), ({"lookback_bars": 1000}, "LOOKBACK_EXCEEDS_DECLARED_WINDOW"),
    ({"timeframe": "M2"}, "TIMEFRAME_OR_WINDOW_ALIGNMENT_INVALID"),
    ({"dataset": "TICKS"}, "OHLCV_RESEARCH_ONLY_REQUIRED"),
])
def test_projection_preserves_constraints_and_reports_unsupported_requests(app, tmp_path, monkeypatch, patch, code):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    payload = specification()
    payload["specification"]["data_requirements"][0].update(patch)
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    report = subject.inspect_goal_historical_data("A")
    assert any(code in item for item in report["blockers"]) and not report["requests"]


def test_read_only_export_pending_approval_correct_counts_no_duplicate_calls(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    before = subject.inspect_goal_research("A")["proposal"]
    request = historical_requests(before)[0][0]
    assert request.export.start == (START - timedelta(minutes=5)).isoformat()
    assert request.fields == ("time", "close", "spread")
    result = acquire(subject)["requests"][0]
    assert result["research_bar_count"] == 60 and result["warmup_bar_count"] == 5
    assert result["partition_counts"] == {"IS": 30, "OOS": 30}
    assert result["approval"] == "NOT_APPROVED" and "RESEARCH_SOURCE_NOT_APPROVED" in result["blockers"]
    assert subject.inspect_goal_research("A")["proposal"] == before
    acquire(subject)
    assert len(subject.research_history_client.calls) == 1
    with pytest.raises(ValueError, match="SOURCE_NOT_APPROVED"):
        prepare(subject)


def test_source_approval_r2_and_proposal_acceptance_are_separate(app, tmp_path, monkeypatch):
    subject, db, _ = setup(app, tmp_path, monkeypatch)
    acquire(subject)
    before = subject.inspect_goal_research("A")["proposal"]
    report = approve(subject)["requests"][0]
    after = subject.inspect_goal_research("A")["proposal"]
    assert report["R2"]["outcome"] == "VERIFIED_FOR_DECLARED_SCOPE"
    assert report["proposal_decision"] == "READY_FOR_REVIEW" and not after.reviews
    assert after.head.content.evidence[0].status == "VALIDATED"
    assert after.revisions[:-1] == before.revisions
    assert not after.execution_allowed and "research_proposals" not in db.docs["B"]
    with pytest.raises(ValueError, match="REVISION_NOT_ACCEPTED"):
        prepare(subject)
    review(subject)
    assert subject.inspect_goal_research("A")["proposal"].review_status(after.head.revision_id) == "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"


def test_approved_partition_is_reproducible_disjoint_and_has_unscored_context(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    acquire(subject)
    approve(subject)
    review(subject)
    result = prepare(subject)["requests"][0]
    path = Config.DATA_DIR / result["input_package"]["path"]
    before = path.read_bytes()
    package = json.loads(before)
    train, test = package["partitions"]["IS"], package["partitions"]["OOS"]
    assert train["row_count"] == test["row_count"] == 30
    assert len(train["warmup_context_not_scored"]) == len(test["warmup_context_not_scored"]) == 5
    assert not {r["time"] for r in train["rows"]} & {r["time"] for r in test["rows"]}
    assert max(r["time"] for r in test["warmup_context_not_scored"]) < min(r["time"] for r in test["rows"])
    assert not package["execution_allowed"] and not package["research_computation_authorized"] and not package["strategy_evaluated"]
    prepare(subject)
    assert path.read_bytes() == before and checksum(before) == result["input_package"]["sha256"]
    from dataclasses import replace
    from src.services.trading.research.input_package import prepare_evaluation_input
    view = subject.inspect_goal_research("A")
    request = historical_requests(view["proposal"])[0][0]
    record = subject._goal_research_context("A")[6]
    source = approved_sources(Config.DATA_DIR / "research", record, view["proposal"].scope)[0]
    with pytest.raises(ValueError, match="REVISION_MISMATCH"):
        prepare_evaluation_input(Config.DATA_DIR / "research", view["proposal"],
            replace(request, split=(START + timedelta(minutes=15)).isoformat()), source, now=datetime.now(timezone.utc))
    path.write_bytes(b"tampered output fixture")
    with pytest.raises(ValueError, match="EXISTING_PACKAGE_MISMATCH"):
        prepare(subject)


@pytest.mark.parametrize("environment", ["REAL", "UNKNOWN", ""])
def test_non_demo_never_reaches_export(app, tmp_path, monkeypatch, environment):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    subject.research_history_client.environment = environment
    result = acquire(subject)["requests"][0]
    assert result["acquisition"] == "FAILED" and "DEMO_ACCOUNT_REQUIRED" in result["blockers"]
    assert not subject.research_history_client.calls
    acquire(subject)
    assert not subject.research_history_client.calls


def test_stale_foreign_deleted_and_concurrent_requests_fail_closed(app, tmp_path, monkeypatch):
    subject, db, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    request = historical_requests(view["proposal"])[0][0]
    with pytest.raises(ValueError, match="BRIEF_STALE"):
        subject.acquire_goal_history("B", view["key"], view["proposal"].head.revision_id, request.request_id)
    with pytest.raises(ValueError, match="HISTORICAL_REQUEST_STALE"):
        subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, "f" * 64)
    subject.research_history_client.callback = lambda: subject.revise_goal_research(
        "A", view["key"], view["proposal"].head.revision_id, "Changed during network read.")
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        acquire(subject)
    assert subject.inspect_goal_research("A")["proposal"].head.content.development is None
    assert "historical" in next(iter(db.docs["A"]["research_proposals"].values()))
    del db.docs["A"]
    with pytest.raises(ValueError, match="CONVERSATION_UNAVAILABLE"):
        subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, request.request_id)


def test_tampered_dataset_is_not_approved_and_old_approval_survives_revisions(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    report = acquire(subject)["requests"][0]
    view = subject.inspect_goal_research("A")
    with pytest.raises(ValueError, match="APPROVAL_STALE"):
        subject.approve_goal_history("A", view["key"], view["proposal"].head.revision_id, report["request_id"], "0" * 64)
    approve(subject)
    approved = subject.inspect_goal_research("A")["proposal"]
    subject.revise_goal_research("A", view["key"], approved.head.revision_id, "New hypothesis, no inherited specification.")
    reloaded = subject.inspect_goal_research("A")["proposal"]
    assert reloaded.revisions[-2] == approved.head and reloaded.head.content.development is None
    assert not reloaded.reviews and reloaded.head.content.evidence[0].status == "PENDING"


def test_no_implicit_cost_values_or_split(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch, costs=False)
    view = subject.inspect_goal_research("A")
    payload = specification(costs=False)
    payload["historical_window"]["split"] = None
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    result = acquire(subject)["requests"][0]
    assert result["research_bar_count"] == 60
    assert result["is_oos"] == "MISSING_SPLIT" and result["costs"]["status"] == "MISSING"
    assert "RESEARCH_IS_OOS_SPLIT_REQUIRED" in result["blockers"]
    approve(subject)
    review(subject)
    with pytest.raises(ValueError):
        prepare(subject)
    assert not (Config.DATA_DIR / "research/inputs").exists()


def test_alignment_failure_does_not_replace_confirmed_window(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    payload = specification()
    payload["historical_window"]["split"] = (START + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="WINDOW_NOT_ALIGNED"):
        subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    assert subject.inspect_goal_research("A")["proposal"] == view["proposal"]


@pytest.mark.parametrize("tamper", ["data", "manifest", "request", "path", "authority"])
def test_transport_integrity_mismatch_is_not_imported(app, tmp_path, monkeypatch, tamper):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    request = historical_requests(subject.inspect_goal_research("A")["proposal"])[0][0]
    response = subject.research_history_client.export_research_history(asdict(request.export), "")
    manifest = json.loads(response["manifest"])
    if tamper == "data":
        response["data_base64"] = b64encode(b"changed bytes").decode()
    elif tamper == "manifest":
        manifest["record_count"] += 1
    elif tamper == "request":
        manifest["request"]["broker_symbol"] = "wrong"
    elif tamper == "path":
        manifest["dataset_id"] = "../outside"
    else:
        response["execution_allowed"] = True
    response["manifest"] = json.dumps(manifest)
    with pytest.raises(ValueError):
        receive_history_export(Config.DATA_DIR / "research", response, request.export)
    assert not list((Config.DATA_DIR / "research/mt5").glob("research_dataset_*"))


def test_actual_gap_and_unavailable_derived_field_remain_blocked(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    request = historical_requests(subject.inspect_goal_research("A")["proposal"])[0][0]
    rows = bars(65, START - timedelta(minutes=5))
    rows.pop(20)
    folder, manifest = persist_dataset(tmp_path / "partial", request.export, rows, contract=CONTRACT,
        acquired_at=(START + timedelta(days=1)).isoformat())
    response = {"status": "EXPORTED", "execution_allowed": False, "manifest": (folder / "manifest.json").read_text(),
                "data_base64": b64encode((folder / "data.jsonl").read_bytes()).decode()}
    subject.research_history_client.export_research_history = lambda *_: response
    report = acquire(subject)["requests"][0]
    assert report["coverage"]["missing_expected_bars"] == 1 and report["coverage"]["gap_intervals_first_100"]
    assert report["coverage"]["status"] == "PARTIAL" and "RESEARCH_COVERAGE_INSUFFICIENT" in report["blockers"]
    with pytest.raises(ValueError, match="PRIMARY_RESEARCH_REQUIRES_VERIFIED_DATA"):
        approve(subject)


def test_missing_local_source_is_reported_without_paths_or_automatic_reacquisition(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    report = acquire(subject)["requests"][0]
    (Config.DATA_DIR / "research/mt5" / report["dataset_id"] / "data.jsonl").unlink()
    missing = subject.inspect_goal_historical_data("A")["requests"][0]
    assert missing["coverage"] == "SOURCE_UNAVAILABLE" and missing["blockers"] == ["RESEARCH_SOURCE_UNAVAILABLE"]
    assert len(subject.research_history_client.calls) == 1


def test_explicit_retry_only_and_source_receipt_integrity(app, tmp_path, monkeypatch):
    subject, db, history = setup(app, tmp_path, monkeypatch)
    subject.research_history_client.environment = "UNKNOWN"
    acquire(subject)
    subject.research_history_client.environment = "DEMO"
    acquire(subject)
    assert not subject.research_history_client.calls
    view = subject.inspect_goal_research("A")
    request = historical_requests(view["proposal"])[0][0]
    with history.research_generation_lock(view["key"]):
        with pytest.raises(ValueError, match="GENERATION_ACTIVE"):
            subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, request.request_id, retry=True)
    subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, request.request_id, retry=True)
    assert len(subject.research_history_client.calls) == 1
    approve(subject)
    record = db.docs["A"]["research_proposals"][view["key"]]
    entry = next(iter(record["historical"].values()))
    entry["source_approval"]["data_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="APPROVAL_INVALID"):
        subject.inspect_goal_research("A")


def test_multiple_timeframes_require_independent_sources_without_duplicate_acquisition(app, tmp_path, monkeypatch):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    view = subject.inspect_goal_research("A")
    payload = specification()
    payload["specification"]["data_requirements"].append({**payload["specification"]["data_requirements"][0],
        "timeframe": "M15", "lookback_bars": 4, "warmup_bars": 1})
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    for index in range(2):
        view = subject.inspect_goal_research("A")
        report = subject.inspect_goal_historical_data("A")["requests"][index]
        subject.acquire_goal_history("A", view["key"], view["proposal"].head.revision_id, report["request_id"])
    approve(subject)
    with pytest.raises(ValueError, match="REQUIRED_SOURCES_INCOMPLETE"):
        review(subject)
    view = subject.inspect_goal_research("A")
    report = subject.inspect_goal_historical_data("A")["requests"][1]
    subject.approve_goal_history("A", view["key"], view["proposal"].head.revision_id,
                                report["request_id"], report["manifest_sha256"])
    reports = review(subject)["requests"]
    assert all(r["R2"]["outcome"] == "VERIFIED_FOR_DECLARED_SCOPE" for r in reports)
    assert len(subject.research_history_client.calls) == 2
    assert prepare(subject)["requests"][0]["input_package"]["sha256"]


def test_authenticated_http_route_reuses_exporter_and_rejects_bad_requests(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer
    from src.services.trading.execution.mt5_bridge_write_skeleton.client import MT5BridgeWriteSkeletonClient
    from tools.mt5_bridge import server, export_research_history
    client = HistoryClient(tmp_path / "host")
    def exported(request):
        response = client.export_research_history(asdict(request), "fixture-token")
        manifest = json.loads(response["manifest"])
        return client.root / manifest["dataset_id"], manifest
    monkeypatch.setattr(export_research_history, "export_history", exported)
    monkeypatch.setenv("MT5_BRIDGE_EXECUTION_TOKEN", "fixture-token")
    from scripts.test_historical_research_dataset import REQUEST
    http = ThreadingHTTPServer(("127.0.0.1", 0), server.MT5BridgeHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        bridge = MT5BridgeWriteSkeletonClient(f"http://127.0.0.1:{http.server_port}")
        assert bridge.export_research_history(asdict(REQUEST), "wrong")["reason"] == "AUTHENTICATION_FAILED"
        assert not client.calls
        assert bridge.export_research_history({}, "fixture-token")["reason"] == "HISTORICAL_REQUEST_INVALID"
        assert not client.calls
        response = bridge.export_research_history(asdict(REQUEST), "fixture-token")
        assert response["status"] == "EXPORTED" and len(client.calls) == 1
    finally:
        http.shutdown()
        http.server_close()
        thread.join(2)


def test_streamlit_missing_fields_editors_no_automatic_network_or_approval(app, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    subject, db, _ = setup(app, tmp_path, monkeypatch, window=False, costs=False)
    page = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
_render_goal_research(st.session_state.subject)
''')
    page.session_state.subject = subject
    page.session_state.current_session_id = "A"
    page.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    page.run()
    assert not page.exception and not subject.research_history_client.calls
    assert any("historical_window.start" in warning.value for warning in page.warning)
    assert any(t.label == "Commission source / assumption" and not t.value for t in page.text_input)
    for label, value in (("Evaluation start (UTC, inclusive)", START.isoformat()),
                         ("Evaluation end (UTC, exclusive)", (START + timedelta(hours=1)).isoformat()),
                         ("IS/OOS boundary (UTC)", (START + timedelta(minutes=30)).isoformat())):
        next(t for t in page.text_input if t.label == label).set_value(value)
    next(s for s in page.selectbox if s.label == "Historical session policy").select("CONTINUOUS_UTC_V1")
    next(b for b in page.button if b.label == "Save historical window revision").click().run()
    assert not page.exception
    assert next(b for b in page.button if b.label == "Acquire historical DEMO data").disabled
    next(c for c in page.checkbox if c.label == "I request this exact read-only DEMO historical export").set_value(True).run()
    next(b for b in page.button if b.label == "Acquire historical DEMO data").click().run()
    assert not page.exception and len(subject.research_history_client.calls) == 1
    assert next(b for b in page.button if b.label == "Approve dataset source and verify R2").disabled
    page.run()
    assert len(subject.research_history_client.calls) == 1


def test_streamlit_costs_editable_without_dates_and_no_implicit_zero(app, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    subject, db, _ = setup(app, tmp_path, monkeypatch, window=False, costs=False)
    page = AppTest.from_string('''
import streamlit as st
from src.ui.tab_chatbot import _render_goal_research
_render_goal_research(st.session_state.subject)
''')
    page.session_state.subject = subject
    page.session_state.current_session_id = "A"
    page.session_state.messages = copy.deepcopy(db.docs["A"]["messages"])
    page.run()
    for name in ("Spread", "Commission", "Swap", "Slippage"):
        assert next(t for t in page.text_input if t.label == name + " value").value == ""
        next(t for t in page.text_input if t.label == name + " value").set_value("0")
        next(t for t in page.text_input if t.label == name + " unit").set_value("USD/trade")
        next(t for t in page.text_input if t.label == name + " source / assumption").set_value("Explicit test assumption only.")
    next(b for b in page.button if b.label == "Save cost assumptions revision").click().run()
    assert not page.exception
    report = subject.inspect_goal_historical_data("A")
    assert report["costs"]["status"] == "DECLARED_ASSUMPTIONS_NOT_BROKER_VERIFIED"
    assert all(c["value"] == 0 and c["provenance"] == "USER_AUTHORED" for c in report["costs"]["assumptions"].values())
    assert not report["requests"] and not subject.research_history_client.calls


def test_ai_cost_suggestions_do_not_become_confirmed_by_an_unrelated_window_edit(app, tmp_path, monkeypatch):
    subject, _, _ = app
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path / "app")
    view = generate(subject)
    payload = specification()
    subject.research_hypothesis_provider.output = json.dumps(payload)
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id)
    view = subject.inspect_goal_research("A")
    assert len(cost_readiness(view["proposal"])["missing"]) == 4
    payload["historical_window"]["split"] = (START + timedelta(minutes=20)).isoformat()
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    assert all(name.endswith(".source_confirmation") for name in cost_readiness(subject.inspect_goal_research("A")["proposal"])["missing"])


@pytest.mark.parametrize("field", ["costs", "split"])
def test_downstream_revisions_reuse_raw_data_but_not_old_approval_or_input_package(app, tmp_path, monkeypatch, field):
    subject, _, _ = setup(app, tmp_path, monkeypatch)
    acquire(subject)
    first_approval = approve(subject)["requests"][0]["approved_scope"]
    review(subject)
    old = prepare(subject)["requests"][0]["input_package"]
    view = subject.inspect_goal_research("A")
    payload = view["proposal"].head.content.development.model_dump(mode="json")
    if field == "costs":
        payload["transaction_costs"][0]["value"] = 1
    else:
        payload["historical_window"]["split"] = (START + timedelta(minutes=20)).isoformat()
    subject.develop_goal_research("A", view["key"], view["proposal"].head.revision_id, development_json=json.dumps(payload))
    report = subject.inspect_goal_historical_data("A")["requests"][0]
    assert report["acquisition"] == "ACQUIRED" and report["approval"] == "SOURCE_APPROVED_ONLY"
    assert report["proposal_decision"] == "EVIDENCE_PENDING" and "input_package" not in report
    acquire(subject)
    assert len(subject.research_history_client.calls) == 1
    assert approve(subject)["requests"][0]["approved_scope"] == first_approval
    review(subject)
    new = prepare(subject)["requests"][0]["input_package"]
    assert new["sha256"] != old["sha256"] and (Config.DATA_DIR / old["path"]).is_file()
