from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, Inexact, ROUND_FLOOR, localcontext
import json
from pathlib import Path

import pytest

from scripts.test_historical_research_dataset import REQUEST, START, bars
from scripts.test_research_evidence_verification import research, setup_source
from scripts.test_research_proposal import ACCEPT, NOW, SCOPE, create
from scripts.test_research_readiness import provision
from scripts.test_research_result_review import fixture as one_hour
from src.services.trading.research import descriptive_computation as computation, descriptive_summary as summary
from src.services.trading.research.evidence_verification import HISTORICAL_EVALUATION_VERSION, HistoricalEvidenceVerifier
from src.services.trading.research.historical_dataset import canonical_bytes, checksum
from src.services.trading.research.input_package import prepare_research_input


def prepared(root):
    end = START + timedelta(hours=3)
    request = replace(REQUEST, end=end.isoformat())
    observations = bars(180)
    for index, row in enumerate(observations):
        value = Decimal(index % 60 + 1) / Decimal(10)
        row.update(low=4000.0, high=float(Decimal(4000) + value), open=4000.0, close=4000.0)
    source, ref = setup_source(root / "mt5", rows=observations, request=request)
    ref = ref.model_copy(update={"window_end": end, "status": "VALIDATED", "data_quality": "VERIFIED",
                                 "evaluation_version": HISTORICAL_EVALUATION_VERSION})
    owner = HistoricalEvidenceVerifier(SCOPE, (source,))
    proposal = create(research(ref), verify=owner)
    proposal = proposal.review(scope=SCOPE, revision_id=proposal.head.revision_id, decision=ACCEPT,
                               reviewed_at=NOW, verify_evidence=owner)
    binding, snapshot = provision(root, proposal, source)
    snapshot.with_name("binding.approved.json").write_bytes(canonical_bytes(binding))
    input_path = prepare_research_input(root, binding, now=NOW)
    approval = computation.DescriptiveComputationApproval(
        decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", proposal_id=proposal.proposal_id,
        revision_id=proposal.head.revision_id, scope=SCOPE, input_sha256=checksum(input_path.read_bytes()),
        algorithm=computation.ALGORITHM, output_directory=str(root / "results"),
    )
    result_path = computation.run_descriptive_computation(root, binding, input_sha256=approval.input_sha256, approval=approval)
    pins = {"input_sha256": approval.input_sha256, "result_sha256": checksum(result_path.read_bytes())}
    summary_approval = approval.model_copy(update={"algorithm": summary.ALGORITHM, "input_sha256": pins["result_sha256"]})
    return binding, pins, result_path, snapshot, summary_approval


def pure_source():
    return {"algorithm": computation.ALGORITHM, "dataset": {"timeframe": "M1"}, "row_count": 180,
            "window": {"start_inclusive": START.isoformat(), "end_exclusive": (START + timedelta(hours=3)).isoformat()},
            "rows": [{"time": int(START.timestamp()) + i * 60, "range": str(Decimal(i % 60 + 1) / 10)} for i in range(180)]}


def test_exact_hourly_statistics_and_ambient_context_independence():
    source = pure_source()
    before = canonical_bytes(source)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_FLOOR
        context.traps[Inexact] = True
        groups = summary.summarize_hourly_ranges(source)
    for index, group in enumerate(groups):
        assert group == {"start_inclusive": (START + timedelta(hours=index)).isoformat(),
                         "end_exclusive": (START + timedelta(hours=index + 1)).isoformat(), "count": 60,
                         "mean": "3.050000000000", "median": "3.05", "min": "0.1", "max": "6"}
    assert canonical_bytes(source) == before


@pytest.mark.parametrize("value,rounded", [("0.00000000003", "0.000000000000"),
                                           ("0.00000000009", "0.000000000002"),
                                           ("1", "0.016666666667")])
def test_mean_rounding_is_explicit_half_even(value, rounded):
    source = pure_source()
    for row in source["rows"]:
        row["range"] = "0"
    source["rows"][0]["range"] = value
    first = summary.summarize_hourly_ranges(source)[0]
    assert first["mean"] == rounded and first["median"] == "0"


@pytest.mark.parametrize("case", ["missing", "duplicate", "reverse", "boundary", "start", "window", "timeframe",
                                  "nan", "negative", "numeric", "absent", "boolean_count"])
def test_invalid_groups_reject_missing_or_unsupported_observations(case):
    source = pure_source()
    if case == "missing":
        source["rows"].pop()
    elif case == "duplicate":
        source["rows"][60]["time"] = source["rows"][59]["time"]
    elif case == "reverse":
        source["rows"].reverse()
    elif case == "boundary":
        source["rows"][59]["time"] += 60
    elif case == "start":
        source["window"]["start_inclusive"] = (START + timedelta(minutes=1)).isoformat()
    elif case == "window":
        source["window"]["end_exclusive"] = (START + timedelta(hours=4)).isoformat()
    elif case == "timeframe":
        source["dataset"]["timeframe"] = "M15"
    elif case == "boolean_count":
        source["row_count"] = True
    elif case == "absent":
        del source["rows"][0]["range"]
    else:
        source["rows"][0]["range"] = {"nan": "NaN", "negative": "-1", "numeric": 1}[case]
    with pytest.raises(ValueError):
        summary.summarize_hourly_ranges(source)


def test_gated_fixture_summary_is_reproducible_and_bound(tmp_path, monkeypatch):
    binding, pins, result, snapshot, approval = prepared(tmp_path)
    source = json.loads(result.read_bytes())
    protected = [result, snapshot, snapshot.with_name("binding.approved.json"),
                 tmp_path / "inputs" / f"research_input_{pins['input_sha256']}.json"]
    before = {path: path.read_bytes() for path in protected}

    def forbidden(*args, **kwargs):
        pytest.fail("Summary must never rerun high-minus-low")

    monkeypatch.setattr(computation, "calculate_bar_ranges", forbidden)
    monkeypatch.setattr(computation, "run_descriptive_computation", forbidden)
    path = summary.run_hourly_summary(tmp_path, binding, pins, approval=approval)
    payload, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert summary.run_hourly_summary(tmp_path, binding, pins, approval=approval) == path
    assert path.read_bytes() == payload and path.stat().st_mtime_ns == mtime
    assert path.name == f"research_summary_{checksum(payload)}.json"
    record = json.loads(payload)
    assert record["schema_version"] == summary.SCHEMA and record["algorithm"] == summary.ALGORITHM
    assert record["precision_policy"] == summary.PRECISION
    assert record["source_result_sha256"] == pins["result_sha256"] and record["input_sha256"] == pins["input_sha256"]
    assert record["proposal"] == source["proposal"] and record["scope"] == source["scope"]
    assert record["dataset"] == source["dataset"] and record["window"] == source["window"]
    assert record["group_count"] == 3 and record["groups_sha256"] == checksum(canonical_bytes(record["groups"]))
    assert record["execution_allowed"] is record["generated_code_allowed"] is False
    assert {path: path.read_bytes() for path in protected} == before
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="EXISTING_PACKAGE_MISMATCH"):
        summary.run_hourly_summary(tmp_path, binding, pins, approval=approval)
    assert path.read_bytes() == b"tampered"


def test_no_summary_reads_or_computation_without_exact_authorization(tmp_path, monkeypatch):
    binding, pins, _, _, approval = prepared(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Unapproved summary cannot read or compute")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(summary, "summarize_hourly_ranges", forbidden)
    for unauthorized in (None, approval.model_dump()):
        with pytest.raises(ValueError, match="OPERATOR_APPROVAL_REQUIRED"):
            summary.run_hourly_summary(tmp_path, binding, pins, approval=unauthorized)
    for changes in ({"algorithm": computation.ALGORITHM}, {"revision_id": "wrong"}, {"input_sha256": "0" * 64},
                    {"scope": SCOPE.model_copy(update={"trading_scope": "trading_scope_" + "0" * 24})}):
        with pytest.raises(ValueError, match="APPROVAL_MISMATCH"):
            summary.run_hourly_summary(tmp_path, binding, pins, approval=approval.model_copy(update=changes))
    with pytest.raises(ValueError, match="APPROVAL_MISMATCH"):
        computation.run_descriptive_computation(tmp_path, binding, input_sha256=approval.input_sha256, approval=approval)


@pytest.mark.parametrize("case", ["result", "binding", "stale"])
def test_tamper_and_changed_authority_never_publish_summary(tmp_path, monkeypatch, case):
    binding, pins, path, snapshot, approval = prepared(tmp_path)
    if case == "result":
        path.write_bytes(b"tampered")
    elif case == "binding":
        snapshot.with_name("binding.approved.json").write_bytes(b"{}")
    else:
        summarize = summary.summarize_hourly_ranges

        def changes(source):
            result = summarize(source)
            snapshot.write_bytes(snapshot.read_bytes() + b" ")
            return result

        monkeypatch.setattr(summary, "summarize_hourly_ranges", changes)
    with pytest.raises(ValueError):
        summary.run_hourly_summary(tmp_path, binding, pins, approval=approval)
    assert not list((tmp_path / "results").glob("research_summary_*"))


def test_archived_review_is_explicit_pinned_and_not_a_current_fallback(tmp_path):
    binding, pins, _, _, snapshot = one_hour(tmp_path)
    binding_bytes = snapshot.with_name("binding.approved.json").read_bytes()
    archive_pin = checksum(binding_bytes)
    archive = tmp_path / "readiness" / "archive"
    archive.mkdir()
    (archive / f"proposal_{binding['proposal_sha256']}.json").write_bytes(snapshot.read_bytes())
    archived_binding = archive / f"binding_{archive_pin}.json"
    archived_binding.write_bytes(binding_bytes)
    snapshot.write_bytes(b"{}")
    snapshot.with_name("binding.approved.json").write_bytes(b"{}")
    args = dict(root=tmp_path, binding=json.dumps(binding), result_binding=json.dumps(pins), trading_scope=SCOPE.trading_scope)
    assert computation.review_research_result(**args)["status"] == "BLOCKED"
    report = computation.review_research_result(**args, archive_binding_sha256=archive_pin)
    assert report["status"] == "VERIFIED"
    assert computation.review_research_result(**args, archive_binding_sha256="../outside")["status"] == "BLOCKED"
    archived_binding.write_bytes(b"tampered")
    assert computation.review_research_result(**args, archive_binding_sha256=archive_pin)["reason"] == "RESEARCH_ARCHIVE_BINDING_CHECKSUM_MISMATCH"


def test_decimal_overlap_reports_differences_without_changing_either_source(tmp_path):
    _, _, path, _, _ = prepared(tmp_path)
    right = {"status": "VERIFIED", "result_sha256": "a" * 64, "result": json.loads(path.read_bytes())}
    left = deepcopy(right)
    left["result_sha256"] = "b" * 64
    left["result"]["rows"] = left["result"]["rows"][60:120]
    left["result"]["window"] = {"start_inclusive": (START + timedelta(hours=1)).isoformat(),
                                  "end_exclusive": (START + timedelta(hours=2)).isoformat()}
    left["result"]["rows"][0]["range"] = "0.10"
    report = summary.compare_verified_overlap(left, right)
    assert report["status"] == "MATCH" and report["matching_observations"] == report["observations"] == 60
    left["result"]["rows"][0]["range"] = "0.2"
    before = deepcopy((left, right))
    report = summary.compare_verified_overlap(left, right)
    assert report["status"] == "DISCREPANCIES" and report["matching_observations"] == 59
    assert len(report["differences"]) == 1 and set(report["differences"][0]["fields"]) == {"range"}
    assert (left, right) == before
    with pytest.raises(ValueError, match="REVIEW_REQUIRED"):
        summary.compare_verified_overlap(left | {"status": "BLOCKED"}, right)
    left["result"]["scope"] = {"trading_scope": "trading_scope_" + "0" * 24}
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        summary.compare_verified_overlap(left, right)
