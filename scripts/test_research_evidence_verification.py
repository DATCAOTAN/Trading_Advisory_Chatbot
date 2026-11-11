from dataclasses import replace
from datetime import timedelta
import json

import pytest

from scripts.test_historical_research_dataset import REQUEST, START, bars, save
from scripts.test_research_proposal import ACCEPT, NOW, SCOPE, change, create
from src.services.trading.research.evidence_verification import (
    HISTORICAL_EVALUATION_VERSION, MT5_SOURCE, ApprovedHistoricalSource, HistoricalEvidenceVerifier,
)
from src.services.trading.research.historical_dataset import canonical_bytes, checksum
from src.services.trading.research.proposal import EvidenceReference, ResearchContent, ResearchProposal


def setup_source(tmp_path, *, rows=None, request=REQUEST):
    folder, manifest = save(tmp_path, rows=rows, request=request)
    source = ApprovedHistoricalSource(folder, manifest["manifest_checksum"], SCOPE)
    reference = EvidenceReference(
        source_ref=MT5_SOURCE, evidence_ref=folder.name, kind="HISTORICAL_MARKET_DATA",
        stance="CONTEXT", window_start=START, window_end=START + timedelta(hours=1),
    )
    return source, reference


def research(reference, timeframe="M1"):
    return ResearchContent(hypothesis="Study historical bar ranges", timeframes=(timeframe,), evidence=(reference,))


def inspect(verifier, proposal, reference):
    return verifier.inspect(proposal, revision_id=proposal.head.revision_id, reference=reference, now=NOW)


def test_verified_source_attaches_to_exact_revision_without_acceptance(tmp_path):
    source, ref = setup_source(tmp_path)
    owner = HistoricalEvidenceVerifier(SCOPE, (source,))
    original = create(research(ref))
    proof = inspect(owner, original, ref)
    assert proof.outcome == "VERIFIED_FOR_DECLARED_SCOPE"
    assert (proof.provenance, proof.integrity, proof.coverage) == ("APPROVED", "VALID", "VERIFIED")
    assert (proof.claim_support, proof.strategy_performance) == ("NOT_ASSESSED", "NOT_ASSESSED")
    assert proof == inspect(owner, original, ref)
    assert proof.scope == SCOPE and proof.proposal_id == original.proposal_id
    assert proof.revision_fingerprint == original.head.content_fingerprint
    assert proof.symbol == "XAUUSD" and proof.timeframe == "M1"
    assert original.review_status(original.head.revision_id) == "EVIDENCE_PENDING"
    assert "4000.123" not in repr(proof) and str(source.folder) not in repr(proof)

    verified = ref.model_copy(update={
        "status": "VALIDATED", "data_quality": "VERIFIED", "evaluation_version": HISTORICAL_EVALUATION_VERSION,
    })
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        change(original, research(verified), verify=lambda *args: True)
    updated = change(original, research(verified), verify=owner)
    assert updated.revisions[0] == original.head and updated.reviews == ()
    assert updated.review_status(updated.head.revision_id) == "READY_FOR_REVIEW"
    assert updated.execution_allowed is False and updated.head.execution_allowed is False
    new_proof = inspect(owner, updated, verified)
    assert new_proof.revision_id == updated.head.revision_id != proof.revision_id
    assert new_proof.revision_fingerprint != proof.revision_fingerprint
    assert change(updated, research(verified), parent=original.head.revision_id, verify=owner) is updated
    assert ResearchProposal.replay(updated.to_json(), scope=SCOPE, verify_evidence=owner) == updated
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        change(updated, ResearchContent(hypothesis="Different hypothesis", timeframes=("M1",), evidence=(verified,)))
    with pytest.raises(ValueError, match="RESEARCH_REVISION_CONFLICT"):
        change(updated, research(ref, "H1"), parent=original.head.revision_id, verify=owner)
    with pytest.raises(ValueError, match="RESEARCH_REVISION_EVIDENCE_MISMATCH"):
        inspect(owner, updated, ref)
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        change(updated, research(verified, "H1"), verify=owner)

    (source.folder / "data.jsonl").write_bytes(b"tampered")
    assert inspect(owner, updated, verified).reason == "DATASET_CHECKSUM_MISMATCH"
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        updated.review(scope=SCOPE, revision_id=updated.head.revision_id, decision=ACCEPT,
                       reviewed_at=NOW + timedelta(minutes=3), verify_evidence=owner)
    assert updated.reviews == ()
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        ResearchProposal.replay(updated.to_json(), scope=SCOPE, verify_evidence=owner)


@pytest.mark.parametrize("case,reason", [
    ("missing", "RESEARCH_SOURCE_UNAVAILABLE"),
    ("malformed", "RESEARCH_SOURCE_ARTIFACT_INVALID"),
    ("unsupported", "DATASET_MANIFEST_INTEGRITY_INVALID"),
    ("naive_time", "UTC_AWARE_DATETIME_REQUIRED"),
    ("new_pin", "RESEARCH_SOURCE_PIN_MISMATCH"),
])
def test_source_failures_are_redacted(tmp_path, case, reason):
    source, ref = setup_source(tmp_path)
    path = source.folder / "manifest.json"
    if case == "missing":
        path.unlink()
    elif case == "malformed":
        path.write_text("private body not JSON", encoding="utf-8")
    else:
        manifest = json.loads(path.read_bytes())
        manifest.pop("manifest_checksum")
        if case == "unsupported":
            manifest["schema_version"] = "unknown"
        elif case == "naive_time":
            manifest["acquired_at"] = "2026-11-03T10:00:00"
        else:
            manifest["source_revision"] = "changed"
        manifest["manifest_checksum"] = checksum(canonical_bytes(manifest))
        path.write_bytes(canonical_bytes(manifest))
        if case != "new_pin":
            source = replace(source, manifest_checksum=manifest["manifest_checksum"])
    outcome = inspect(HistoricalEvidenceVerifier(SCOPE, (source,)), create(research(ref)), ref)
    assert outcome.reason == reason
    assert outcome.outcome == ("SOURCE_UNAVAILABLE" if case == "missing" else "INVALID_OR_MISMATCHED")
    assert "private body" not in repr(outcome)


@pytest.mark.parametrize("case", ["gap", "window", "symbol", "timeframe"])
def test_coverage_and_hypothesis_scope_are_separate_from_integrity(tmp_path, case):
    request = replace(REQUEST, canonical_symbol="EURUSD") if case == "symbol" else REQUEST
    source, ref = setup_source(tmp_path, rows=bars()[1:] if case == "gap" else None, request=request)
    if case == "window":
        ref = ref.model_copy(update={"window_start": START - timedelta(minutes=1)})
    proposal = create(research(ref, "H1" if case == "timeframe" else "M1"))
    result = inspect(HistoricalEvidenceVerifier(SCOPE, (source,)), proposal, ref)
    assert result.integrity == "VALID"
    if case in {"gap", "window"}:
        assert result.outcome == "PARTIAL_OR_LIMITED" and result.reason == "RESEARCH_COVERAGE_INSUFFICIENT"
        assert result.coverage == ("PARTIAL" if case == "gap" else "VERIFIED")
    else:
        assert result.outcome == "INVALID_OR_MISMATCHED" and result.reason == "RESEARCH_MARKET_SCOPE_MISMATCH"


def test_scope_reference_and_unsupported_evidence_fail_closed(tmp_path):
    source, ref = setup_source(tmp_path)
    for scope in (SCOPE.model_copy(update={"account_ref": None}),
                  SCOPE.model_copy(update={"trading_scope": "trading_scope_" + "a" * 24})):
        proposal = create(research(ref))
        with pytest.raises(ValueError, match="RESEARCH_SCOPE_MISMATCH"):
            inspect(HistoricalEvidenceVerifier(scope, (source,)), proposal, ref)
        assert inspect(HistoricalEvidenceVerifier(SCOPE, (replace(source, scope=scope),)), proposal, ref).outcome == "SOURCE_UNAVAILABLE"
    owner = HistoricalEvidenceVerifier(SCOPE, (source,))
    proposal = create(research(ref))
    with pytest.raises(ValueError, match="RESEARCH_REVISION_EVIDENCE_MISMATCH"):
        owner.inspect(proposal, revision_id="revision_other", reference=ref, now=NOW)
    with pytest.raises(ValueError, match="RESEARCH_REVISION_EVIDENCE_MISMATCH"):
        inspect(owner, proposal, ref.model_copy(update={"evidence_ref": "other"}))
    for kind in ("MARKET_OBSERVATION", "KNOWLEDGE", "MT5_TESTER"):
        # The observation window ended days ago. R2 never admits this as current evidence.
        pending = ref.model_copy(update={"kind": kind})
        assert inspect(owner, create(research(pending)), pending).outcome == "PENDING_VERIFICATION"
        if kind != "MT5_TESTER":
            forged = EvidenceReference(**(pending.model_dump() | {
                "status": "VALIDATED", "data_quality": "VERIFIED", "evaluation_version": "claimed",
            }))
            with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
                create(research(forged), verify=owner)
    with pytest.raises(ValueError):
        EvidenceReference(**(ref.model_dump() | {"private_document": "private body"}))
