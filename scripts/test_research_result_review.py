import json
from pathlib import Path

import pytest

from scripts.test_descriptive_research_computation import prepared, run
from scripts.test_research_proposal import SCOPE
from src.services.trading.research import descriptive_computation as computation
from src.services.trading.research.historical_dataset import canonical_bytes, checksum


def fixture(root):
    binding, snapshot, folder, source, approval = prepared(root)
    result = run(root, binding, approval)
    pin = {"input_sha256": approval.input_sha256, "result_sha256": checksum(result.read_bytes())}
    return binding, pin, result, source, snapshot


def review(root, binding, pin, scope=SCOPE.trading_scope):
    return computation.review_research_result(
        root=root, binding=json.dumps(binding), result_binding=json.dumps(pin), trading_scope=scope,
    )


def test_verified_review_is_precise_read_only_and_never_computes(tmp_path, monkeypatch):
    binding, pin, result, source, snapshot = fixture(tmp_path)
    paths = [result, source, snapshot, snapshot.with_name("binding.approved.json")]
    before = {p: p.read_bytes() for p in paths}
    read_bytes = Path.read_bytes

    def read(path):
        assert path in paths, "Only approved artifacts may be read"
        return read_bytes(path)

    def forbidden(*args, **kwargs):
        pytest.fail("Review must not calculate, publish or mutate")

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    for name in ("calculate_bar_ranges", "run_descriptive_computation", "_publish"):
        monkeypatch.setattr(computation, name, forbidden)
    report = review(tmp_path, binding, pin)
    assert report["status"] == "VERIFIED" and report["result_sha256"] == pin["result_sha256"]
    original = json.loads(before[source])
    assert report["result"]["rows"] == json.loads(before[result])["rows"]
    assert len(report["observations"]) == 60
    for displayed, row, computed in zip(report["observations"], original["rows"], report["result"]["rows"]):
        assert displayed["UTC timestamp"].endswith("+00:00")
        assert displayed["High"] == str(row["high"])
        assert displayed["Low"] == str(row["low"])
        assert displayed["Range"] == computed["range"]
    assert {p: read_bytes(p) for p in paths} == before


def test_changed_result_is_rejected_before_parsing(tmp_path, monkeypatch):
    binding, pin, result, _, _ = fixture(tmp_path)
    result.write_bytes(b"do not parse this")
    loads = json.loads

    def guarded(raw):
        assert raw != b"do not parse this"
        return loads(raw)

    monkeypatch.setattr(json, "loads", guarded)
    assert review(tmp_path, binding, pin) == {"status": "BLOCKED", "reason": "RESEARCH_RESULT_CHECKSUM_MISMATCH"}


@pytest.mark.parametrize("case", ["missing", "inaccessible", "scope", "binding", "proposal", "input"])
def test_unavailable_or_changed_sources_do_not_leak_results(tmp_path, monkeypatch, case):
    binding, pin, result, source, snapshot = fixture(tmp_path)
    if case == "missing":
        result.unlink()
    elif case == "inaccessible":
        read = Path.read_bytes

        def inaccessible(path):
            if path == result:
                raise PermissionError("private path")
            return read(path)

        monkeypatch.setattr(Path, "read_bytes", inaccessible)
    elif case == "scope":
        binding["trading_scope"] = "trading_scope_" + "0" * 24
    elif case == "binding":
        snapshot.with_name("binding.approved.json").write_bytes(b"{}")
    elif case == "proposal":
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
    else:
        source.write_bytes(source.read_bytes() + b" ")
    report = review(tmp_path, binding, pin)
    assert report["status"] == "BLOCKED" and "result" not in report and "observations" not in report
    assert "private" not in str(report)


@pytest.mark.parametrize("case,reason", [
    ("schema", "SCHEMA_INVALID"), ("algorithm", "SCHEMA_INVALID"),
    ("input", "INPUT_MISMATCH"), ("proposal", "PROVENANCE_MISMATCH"),
    ("revision", "PROVENANCE_MISMATCH"), ("scope", "PROVENANCE_MISMATCH"),
    ("dataset", "PROVENANCE_MISMATCH"), ("approval", "APPROVAL_MISMATCH"),
    ("timestamp", "ROWS_INVALID"), ("missing_row", "ROWS_INVALID"),
    ("high", "ROWS_INVALID"), ("range_nan", "ROWS_INVALID"), ("range_negative", "ROWS_INVALID"),
])
def test_wrong_even_repinned_result_cannot_be_verified(tmp_path, case, reason):
    binding, pin, result, _, _ = fixture(tmp_path)
    payload = json.loads(result.read_bytes())
    if case in {"schema", "algorithm", "input"}:
        payload[{"schema": "schema_version", "algorithm": "algorithm", "input": "input_sha256"}[case]] = "wrong"
    elif case in {"proposal", "revision"}:
        payload["proposal"]["proposal_id" if case == "proposal" else "revision_id"] = "wrong"
    elif case == "scope":
        payload["scope"]["trading_scope"] = "trading_scope_" + "0" * 24
    elif case == "dataset":
        payload["dataset"]["dataset_id"] = "research_dataset_" + "0" * 24
    elif case == "approval":
        payload["approval"]["decision"] = "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"
    elif case == "timestamp":
        payload["rows"][1]["time"] = payload["rows"][0]["time"]
    elif case == "missing_row":
        payload["rows"].pop()
    elif case == "high":
        payload["rows"][0]["high"] = 1
    else:
        payload["rows"][0]["range"] = "NaN" if case == "range_nan" else "-1"
    payload["rows_sha256"] = checksum(canonical_bytes(payload["rows"]))
    raw = canonical_bytes(payload)
    pin["result_sha256"] = checksum(raw)
    (result.parent / f"research_result_{pin['result_sha256']}.json").write_bytes(raw)
    report = review(tmp_path, binding, pin)
    assert report["status"] == "BLOCKED" and reason in report["reason"]
    assert "result" not in report


@pytest.mark.parametrize("binding,pin", [("", ""), ("{}", ""), ("[]", "{}"), ("{", "{}"),
                                        ("{}", '{"input_sha256":"../outside","result_sha256":"bad"}')])
def test_unconfigured_and_untrusted_paths_never_read_files(tmp_path, monkeypatch, binding, pin):
    def forbidden(*args):
        pytest.fail("Invalid binding must not read artifacts")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    report = computation.review_research_result(root=tmp_path, binding=binding, result_binding=pin,
                                               trading_scope=SCOPE.trading_scope)
    assert report["status"] in {"NOT_CHECKED", "BLOCKED"} and "result" not in report


def test_binding_change_during_review_prevents_presentation(tmp_path, monkeypatch):
    binding, pin, _, _, snapshot = fixture(tmp_path)
    load = computation._load_approved_input

    def changed(*args, **kwargs):
        loaded = load(*args, **kwargs)
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        return loaded

    monkeypatch.setattr(computation, "_load_approved_input", changed)
    assert review(tmp_path, binding, pin) == {"status": "BLOCKED", "reason": "RESEARCH_RESULT_REVIEW_STALE"}


def test_current_revision_must_still_have_recorded_stage_approval(tmp_path):
    binding, pin, _, _, snapshot = fixture(tmp_path)
    proposal = json.loads(snapshot.read_bytes())
    proposal["reviews"] = []
    snapshot.write_bytes(canonical_bytes(proposal))
    binding["proposal_sha256"] = checksum(snapshot.read_bytes())
    snapshot.with_name("binding.approved.json").write_bytes(canonical_bytes(binding))
    assert review(tmp_path, binding, pin) == {
        "status": "BLOCKED", "reason": "RESEARCH_COMPUTATION_REVISION_NOT_ACCEPTED",
    }


def test_streamlit_review_rerun_tamper_and_conversation_isolation(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.config import Config
    from src.orchestrator import RAGOrchestrator
    from src.services import history_service
    from src.ui import tab_dashboard, tab_evaluation_dashboard, tab_settings

    binding, pin, result, _, _ = fixture(tmp_path / "research")
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("RESEARCH_READINESS_BINDING", json.dumps(binding))
    monkeypatch.setenv("RESEARCH_RESULT_BINDING", json.dumps(pin))

    class History:
        def get_all_sessions(self):
            return [{"_id": "semantic-cutover", "title": "Original"}, {"_id": "other", "title": "Other"}]

        def load_history(self, session_id):
            return []

    monkeypatch.setattr(history_service, "HistoryService", History)
    for tab in (tab_dashboard, tab_evaluation_dashboard, tab_settings):
        monkeypatch.setattr(tab, "render", lambda *_: None)

    def forbidden(*args, **kwargs):
        pytest.fail("UI must not compute")

    monkeypatch.setattr(computation, "calculate_bar_ranges", forbidden)
    monkeypatch.setattr(computation, "run_descriptive_computation", forbidden)
    app = AppTest.from_file("src/app.py")
    app.session_state["current_session_id"] = "semantic-cutover"
    app.session_state["messages"] = []
    app.session_state["orchestrator"] = RAGOrchestrator.__new__(RAGOrchestrator)
    app.run()
    assert not app.exception and not app.dataframe
    next(b for b in app.button if b.label == "Inspect verified result").click().run()
    assert not app.exception and len(app.dataframe) == 1
    assert any("VERIFIED |" in node.value for node in app.text)
    displayed = app.dataframe[0].value
    assert len(displayed) == 60 and displayed.iloc[0]["UTC timestamp"].endswith("+00:00")
    assert isinstance(displayed.iloc[0]["Range"], str)
    assert any(pin["result_sha256"] in node.value for node in app.text)
    app.run()
    assert not app.dataframe
    next(b for b in app.button if b.label == "Other").click().run()
    next(b for b in app.button if b.label == "Inspect verified result").click().run()
    assert not app.exception and not app.dataframe
    assert any("RESEARCH_SCOPE_MISMATCH" in node.value for node in app.text)
    next(b for b in app.button if b.label == "Original").click().run()
    result.write_bytes(b"tampered")
    next(b for b in app.button if b.label == "Inspect verified result").click().run()
    assert not app.exception and not app.dataframe
    assert any("RESEARCH_RESULT_CHECKSUM_MISMATCH" in node.value for node in app.text)
    monkeypatch.setattr(History, "get_all_sessions", lambda *_: [])
    next(b for b in app.button if b.label == "Inspect verified result").click().run()
    assert not app.dataframe and any("conversation is unavailable" in node.value for node in app.warning)
