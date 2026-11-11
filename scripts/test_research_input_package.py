from datetime import timedelta
import json
from pathlib import Path

import pytest

from scripts.test_historical_research_dataset import bars
from scripts.test_research_evidence_verification import research, setup_source
from scripts.test_research_proposal import ACCEPT, NOW, SCOPE, create
from scripts.test_research_readiness import provision
from src.services.trading.research import input_package
from src.services.trading.research.evidence_verification import HISTORICAL_EVALUATION_VERSION, HistoricalEvidenceVerifier
from src.services.trading.research.historical_dataset import canonical_bytes, checksum


def provision_input(root, *, accept=True):
    rows = bars()
    rows[0].update(high=4002.1234567890123, low=3999.123456789013)
    source, ref = setup_source(root / "mt5", rows=rows)
    ref = ref.model_copy(update={
        "status": "VALIDATED", "data_quality": "VERIFIED", "evaluation_version": HISTORICAL_EVALUATION_VERSION,
    })
    verifier = HistoricalEvidenceVerifier(SCOPE, (source,))
    proposal = create(research(ref), verify=verifier)
    if accept:
        proposal = proposal.review(scope=SCOPE, revision_id=proposal.head.revision_id, decision=ACCEPT,
                                   reviewed_at=NOW, verify_evidence=verifier)
    binding, snapshot = provision(root, proposal, source)
    path = snapshot.with_name("binding.approved.json")
    path.write_bytes(canonical_bytes(binding))
    return binding, snapshot, source.folder, rows


def test_package_is_reproducible_pinned_and_exactly_projected(tmp_path):
    binding, snapshot, folder, rows = provision_input(tmp_path)
    protected = (snapshot, snapshot.with_name("binding.approved.json"), folder / "manifest.json", folder / "data.jsonl")
    original = {path: path.read_bytes() for path in protected}
    path = input_package.prepare_research_input(tmp_path, binding, now=NOW)
    payload, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert input_package.prepare_research_input(tmp_path, binding, now=NOW + timedelta(days=1)) == path
    assert path.read_bytes() == payload and path.stat().st_mtime_ns == mtime
    assert path.name == f"research_input_{checksum(payload)}.json"
    assert list(path.parent.iterdir()) == [path]
    package = json.loads(payload)
    assert package["schema_version"] == "r1-research-input/v1" and package["execution_allowed"] is False
    assert package["scope"] == SCOPE.model_dump()
    assert {k: package["proposal"][k] for k in ("proposal_id", "revision_id")} == {
        k: binding[k] for k in ("proposal_id", "revision_id")
    }
    assert package["proposal"]["decision"] == ACCEPT
    assert package["proposal"]["export_sha256"] == checksum(original[snapshot])
    assert package["dataset"]["dataset_id"] == binding["dataset_id"]
    assert package["dataset"]["manifest_sha256"] == binding["manifest_sha256"]
    assert package["dataset"]["data_sha256"] == checksum(original[folder / "data.jsonl"])
    assert package["dataset"]["verification"] == "VERIFIED_FOR_DECLARED_SCOPE"
    assert package["window"] == {"start_inclusive": "2026-11-02T10:00:00+00:00",
                                 "end_exclusive": "2026-11-02T11:00:00+00:00"}
    assert package["timestamp_encoding"] == "UTC_UNIX_SECONDS" and package["row_count"] == 60
    assert package["rows"] == [{key: row[key] for key in ("time", "high", "low")} for row in rows]
    assert package["rows_sha256"] == checksum(canonical_bytes(package["rows"]))
    assert {path: path.read_bytes() for path in protected} == original


@pytest.mark.parametrize(("case", "reason"), [
    ("unapproved", "RESEARCH_INPUT_REVISION_NOT_ACCEPTED"),
    ("changed_binding", "RESEARCH_INPUT_APPROVED_BINDING_MISMATCH"),
    ("wrong_revision", "RESEARCH_INPUT_REVISION_MISMATCH"),
    ("wrong_scope", "RESEARCH_SCOPE_MISMATCH"),
    ("changed_snapshot", "RESEARCH_PROPOSAL_SNAPSHOT_STALE"),
    ("changed_manifest", "RESEARCH_SOURCE_PIN_MISMATCH"),
])
def test_approval_and_pins_fail_before_any_rows_are_read(tmp_path, monkeypatch, case, reason):
    binding, snapshot, folder, _ = provision_input(tmp_path, accept=case != "unapproved")
    binding_path = snapshot.with_name("binding.approved.json")
    if case == "changed_binding":
        binding_path.write_bytes(canonical_bytes(binding | {"manifest_sha256": "0" * 64}))
    elif case in {"wrong_revision", "wrong_scope"}:
        key, value = ("revision_id", "revision_" + "0" * 64) if case == "wrong_revision" else (
            "trading_scope", "trading_scope_" + "0" * 24,
        )
        binding[key] = value
        binding_path.write_bytes(canonical_bytes(binding))
    elif case == "changed_snapshot":
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
    elif case == "changed_manifest":
        path = folder / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest.pop("manifest_checksum")
        manifest["source_revision"] = "changed"
        manifest["manifest_checksum"] = checksum(canonical_bytes(manifest))
        path.write_bytes(canonical_bytes(manifest))
    read_bytes = Path.read_bytes

    def reject_data(path):
        assert path.name != "data.jsonl"
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_data)
    with pytest.raises(ValueError, match=reason):
        input_package.prepare_research_input(tmp_path, binding, now=NOW)
    assert not (tmp_path / "inputs").exists()


def test_changed_dataset_is_not_packaged(tmp_path):
    binding, _, folder, _ = provision_input(tmp_path)
    (folder / "data.jsonl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="DATASET_CHECKSUM_MISMATCH"):
        input_package.prepare_research_input(tmp_path, binding, now=NOW)
    assert not (tmp_path / "inputs").exists()


@pytest.mark.parametrize("case", ["missing", "duplicate", "out_of_order", "non_numeric", "symbol", "timeframe"])
def test_projection_rechecks_exact_window_and_market_scope(tmp_path, monkeypatch, case):
    binding, _, _, _ = provision_input(tmp_path)
    load = input_package.load_dataset

    def changed_projection(*args, **kwargs):
        manifest, rows = load(*args, **kwargs)
        if case == "missing":
            rows.pop()
        elif case == "duplicate":
            rows[0] = rows[1]
        elif case == "out_of_order":
            rows[0], rows[1] = rows[1], rows[0]
        elif case == "non_numeric":
            rows[0]["high"] = True
        elif case == "symbol":
            manifest["request"]["canonical_symbol"] = "EURUSD"
        elif case == "timeframe":
            manifest["request"]["timeframe"] = "H1"
        return manifest, rows

    monkeypatch.setattr(input_package, "load_dataset", changed_projection)
    reason = "MARKET_SCOPE_MISMATCH" if case in {"symbol", "timeframe"} else "CLOSED_BAR_WINDOW_INVALID"
    with pytest.raises(ValueError, match=reason):
        input_package.prepare_research_input(tmp_path, binding, now=NOW)
    assert not (tmp_path / "inputs").exists()


def test_tampered_package_is_detected_without_overwriting(tmp_path):
    binding, _, _, _ = provision_input(tmp_path)
    path = input_package.prepare_research_input(tmp_path, binding, now=NOW)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="RESEARCH_INPUT_EXISTING_PACKAGE_MISMATCH"):
        input_package.prepare_research_input(tmp_path, binding, now=NOW)
    assert path.read_bytes() == b"tampered"
    assert list(path.parent.iterdir()) == [path]
