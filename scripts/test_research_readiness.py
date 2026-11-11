from datetime import timedelta
import json
from pathlib import Path

import pytest

from scripts.test_historical_research_dataset import REQUEST, bars
from scripts.test_research_evidence_verification import research, setup_source
from scripts.test_research_proposal import ACCEPT, NOW, SCOPE, change, create
from src.orchestrator import RAGOrchestrator
from src.services.trading.research.evidence_verification import (
    HISTORICAL_EVALUATION_VERSION, HistoricalEvidenceVerifier, review_research_readiness,
)
from src.services.trading.research.historical_dataset import checksum
from src.services.trading.research.proposal import ResearchProposal


def provision(root, proposal, source):
    path = root / "readiness" / "proposal.json"
    path.parent.mkdir(exist_ok=True)
    payload = proposal.to_json().encode()
    path.write_bytes(payload)
    return {
        "trading_scope": proposal.scope.trading_scope, "account_ref": proposal.scope.account_ref,
        "proposal_id": proposal.proposal_id, "revision_id": proposal.head.revision_id,
        "proposal_sha256": checksum(payload), "dataset_id": source.folder.name,
        "manifest_sha256": source.manifest_checksum,
    }, path


def check(root, binding, scope=SCOPE.trading_scope):
    return review_research_readiness(root=root, binding=json.dumps(binding), trading_scope=scope, now=NOW)


def approved(root):
    source, reference = setup_source(root / "mt5")
    validated = reference.model_copy(update={
        "status": "VALIDATED", "data_quality": "VERIFIED", "evaluation_version": HISTORICAL_EVALUATION_VERSION,
    })
    verifier = HistoricalEvidenceVerifier(SCOPE, (source,))
    proposal = create(research(validated), verify=verifier)
    return proposal.review(scope=SCOPE, revision_id=proposal.head.revision_id, decision=ACCEPT,
                           reviewed_at=NOW, verify_evidence=verifier), source, verifier


def test_approved_revision_and_verified_dataset_remain_separate_on_fresh_inspection(tmp_path):
    proposal, source, _ = approved(tmp_path)
    pin, snapshot = provision(tmp_path, proposal, source)
    paths = (snapshot, source.folder / "manifest.json", source.folder / "data.jsonl")
    original = {path: path.read_bytes() for path in paths}
    result = check(tmp_path, pin)
    assert result["proposal"]["status"] == ACCEPT
    proof = result["evidence"]
    assert proof["outcome"] == "VERIFIED_FOR_DECLARED_SCOPE"
    assert (proof["integrity"], proof["provenance"], proof["coverage"]) == ("VALID", "APPROVED", "VERIFIED")
    assert (proof["symbol"], proof["timeframe"]) == ("XAUUSD", "M1")
    assert {path: path.read_bytes() for path in paths} == original
    assert str(tmp_path) not in repr(result) and SCOPE.account_ref not in repr(result)

    paths[-1].write_bytes(b"tampered")
    result = check(tmp_path, pin)
    assert result["proposal"]["status"] == ACCEPT
    assert result["evidence"]["outcome"] == "INVALID_OR_MISMATCHED"
    assert result["evidence"]["reason"] == "DATASET_CHECKSUM_MISMATCH"
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        ResearchProposal.replay(proposal.to_json(), scope=SCOPE)


@pytest.mark.parametrize(("case", "outcome", "reason"), [
    ("verified", "VERIFIED_FOR_DECLARED_SCOPE", "RESEARCH_HISTORICAL_BAR_WINDOW_VERIFIED"),
    ("window", "PARTIAL_OR_LIMITED", "RESEARCH_COVERAGE_INSUFFICIENT"),
    ("gap", "PARTIAL_OR_LIMITED", "RESEARCH_COVERAGE_INSUFFICIENT"),
    ("timeframe", "INVALID_OR_MISMATCHED", "RESEARCH_MARKET_SCOPE_MISMATCH"),
    ("symbol", "INVALID_OR_MISMATCHED", "RESEARCH_MARKET_SCOPE_MISMATCH"),
    ("unavailable", "SOURCE_UNAVAILABLE", "RESEARCH_SOURCE_UNAVAILABLE"),
])
def test_missing_proposal_acceptance_does_not_promote_or_disable_data_verification(tmp_path, case, outcome, reason):
    from dataclasses import replace

    source, ref = setup_source(
        tmp_path / "mt5", rows=bars()[1:] if case == "gap" else None,
        request=replace(REQUEST, canonical_symbol="EURUSD") if case == "symbol" else REQUEST,
    )
    if case == "window":
        ref = ref.model_copy(update={"window_start": ref.window_start - timedelta(minutes=1)})
    proposal = create(research(ref, "H1" if case == "timeframe" else "M1"))
    pin, _ = provision(tmp_path, proposal, source)
    if case == "unavailable":
        (source.folder / "manifest.json").unlink()
    report = check(tmp_path, pin)
    assert report["proposal"]["status"] == "EVIDENCE_PENDING"
    assert report["proposal"]["reason"] == "RESEARCH_REVISION_NOT_ACCEPTED"
    assert report["evidence"]["outcome"] == outcome and report["evidence"]["reason"] == reason
    if case == "window":
        assert report["evidence"]["coverage"] == "VERIFIED"  # Whole artifact quality is not window coverage.
    if case == "gap":
        assert report["evidence"]["coverage"] == "PARTIAL"


def test_missing_source_approval_and_bad_manifest_pin_do_not_read_dataset_rows(tmp_path, monkeypatch):
    proposal, source, _ = approved(tmp_path)
    pin, _ = provision(tmp_path, proposal, source)
    read_bytes = Path.read_bytes

    def forbid_rows(path):
        assert path.name != "data.jsonl", "unapproved rows were read"
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", forbid_rows)
    missing_pin = check(tmp_path, pin | {"manifest_sha256": None})
    assert missing_pin["proposal"]["status"] == ACCEPT
    assert missing_pin["evidence"]["reason"] == "RESEARCH_SOURCE_NOT_APPROVED"
    assert check(tmp_path, pin | {"manifest_sha256": "0" * 64})["evidence"]["reason"] == "RESEARCH_SOURCE_PIN_MISMATCH"
    assert check(tmp_path, pin | {"dataset_id": "../arbitrary"})["evidence"]["reason"] == "RESEARCH_SOURCE_NOT_APPROVED"


def test_no_binding_or_wrong_conversation_never_opens_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("unexpected snapshot access"))
    no_binding = review_research_readiness(root=tmp_path, binding="", trading_scope=SCOPE.trading_scope, now=NOW)
    assert no_binding["proposal"]["reason"] == "RESEARCH_PROPOSAL_NOT_CONFIGURED"
    assert no_binding["evidence"]["outcome"] == "NOT_CHECKED"
    assert check(tmp_path, {"trading_scope": "other"})["proposal"]["reason"] == "RESEARCH_SCOPE_MISMATCH"
    assert check(tmp_path, {"trading_scope": SCOPE.trading_scope})["proposal"]["reason"] == "RESEARCH_BINDING_INVALID"


def test_wrong_stale_missing_or_cross_conversation_proposals_do_not_check_evidence(tmp_path, monkeypatch):
    proposal, source, verifier = approved(tmp_path)
    newer = change(proposal, proposal.head.content.model_copy(update={"limitations": ("New revision",)}), verify=verifier)
    pin, snapshot = provision(tmp_path, newer, source)
    monkeypatch.setattr(HistoricalEvidenceVerifier, "inspect", lambda *_, **__: pytest.fail("unexpected evidence read"))
    for params, scope, expected in (
        (pin, "trading_scope_" + "0" * 24, "RESEARCH_SCOPE_MISMATCH"),
        (pin | {"account_ref": None}, SCOPE.trading_scope, "RESEARCH_SCOPE_MISMATCH"),
        (pin | {"revision_id": proposal.head.revision_id}, SCOPE.trading_scope, "RESEARCH_REVIEW_STALE"),
        (pin | {"revision_id": "revision_" + "0" * 64}, SCOPE.trading_scope, "RESEARCH_REVISION_NOT_FOUND"),
        (pin | {"proposal_id": "proposal_" + "0" * 64}, SCOPE.trading_scope, "RESEARCH_PROPOSAL_ID_MISMATCH"),
        (pin | {"proposal_sha256": "0" * 64}, SCOPE.trading_scope, "RESEARCH_PROPOSAL_SNAPSHOT_STALE"),
    ):
        result = check(tmp_path, params, scope)
        assert result["proposal"]["reason"] == expected and result["evidence"]["outcome"] == "NOT_CHECKED"
        assert "revision_id" not in result["proposal"]
    snapshot.unlink()
    assert check(tmp_path, pin)["proposal"]["reason"] == "RESEARCH_PROPOSAL_UNAVAILABLE"


def test_verifier_failure_and_snapshot_change_during_inspection_do_not_publish_data(tmp_path, monkeypatch):
    proposal, source, _ = approved(tmp_path)
    pin, snapshot = provision(tmp_path, proposal, source)
    inspect = HistoricalEvidenceVerifier.inspect

    def unavailable(*args, **kwargs):
        raise PermissionError("private detail")

    monkeypatch.setattr(HistoricalEvidenceVerifier, "inspect", unavailable)
    assert check(tmp_path, pin)["evidence"] == {
        "outcome": "NOT_CHECKED", "reason": "RESEARCH_EVIDENCE_VERIFICATION_FAILED",
    }

    def replaces_snapshot(*args, **kwargs):
        result = inspect(*args, **kwargs)
        snapshot.unlink()
        return result

    monkeypatch.setattr(HistoricalEvidenceVerifier, "inspect", replaces_snapshot)
    report = check(tmp_path, pin)
    assert report["proposal"]["reason"] == "RESEARCH_PROPOSAL_SNAPSHOT_STALE"
    assert report["evidence"]["outcome"] == "NOT_CHECKED"


@pytest.mark.parametrize("limited", [False, True])
def test_streamlit_readiness_is_on_demand_separate_and_not_replayed(tmp_path, monkeypatch, limited):
    from streamlit.testing.v1 import AppTest
    from src.config import Config
    from src.services import history_service
    from src.ui import tab_dashboard, tab_evaluation_dashboard, tab_settings

    root = tmp_path / "research"
    if limited:
        source, ref = setup_source(root / "mt5", rows=bars()[1:])
        proposal = create(research(ref))
    else:
        proposal, source, _ = approved(root)
    pin, _ = provision(root, proposal, source)
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("RESEARCH_READINESS_BINDING", json.dumps(pin))
    calls = []
    inspect = HistoricalEvidenceVerifier.inspect

    def count(*args, **kwargs):
        calls.append(kwargs["revision_id"])
        return inspect(*args, **kwargs)

    class History:
        def get_all_sessions(self):
            return [{"_id": "semantic-cutover", "title": "Original"}, {"_id": "other", "title": "Other"}]

        def load_history(self, session_id):
            return []

    monkeypatch.setattr(HistoricalEvidenceVerifier, "inspect", count)
    monkeypatch.setattr(history_service, "HistoryService", History)
    for tab in (tab_dashboard, tab_evaluation_dashboard, tab_settings):
        monkeypatch.setattr(tab, "render", lambda *_: None)
    app = AppTest.from_file("src/app.py")
    app.session_state["current_session_id"] = "semantic-cutover"
    app.session_state["messages"] = []
    app.session_state["orchestrator"] = RAGOrchestrator.__new__(RAGOrchestrator)
    app.run()
    assert not app.exception and not calls
    next(button for button in app.button if button.label == "Inspect existing research revision").click().run()
    assert not app.exception and calls == [proposal.head.revision_id]
    status = "EVIDENCE_PENDING" if limited else ACCEPT
    outcome = "PARTIAL_OR_LIMITED" if limited else "VERIFIED_FOR_DECLARED_SCOPE"
    assert any(status in node.value for node in app.text)
    assert any(outcome in node.value for node in app.text)
    if limited:
        assert any("RESEARCH_COVERAGE_INSUFFICIENT" in node.value for node in app.text)
    assert not app.session_state["messages"]
    app.run()
    assert not any(outcome in node.value for node in app.text)
    next(button for button in app.button if button.label == "Other").click().run()
    next(button for button in app.button if button.label == "Inspect existing research revision").click().run()
    assert not app.exception and calls == [proposal.head.revision_id]
    assert any("RESEARCH_SCOPE_MISMATCH" in node.value for node in app.text)
    assert not any(status in node.value for node in app.text)
