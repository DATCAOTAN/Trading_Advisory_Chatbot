from decimal import Decimal, localcontext
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.test_research_input_package import provision_input
from scripts.test_research_proposal import NOW, SCOPE
from src.services.trading.research import descriptive_computation as computation
from src.services.trading.research.historical_dataset import canonical_bytes, checksum
from src.services.trading.research.input_package import prepare_research_input


def prepared(root):
    binding, snapshot, folder, _ = provision_input(root)
    path = prepare_research_input(root, binding, now=NOW)
    approval = computation.DescriptiveComputationApproval(
        decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", proposal_id=binding["proposal_id"],
        revision_id=binding["revision_id"], scope=SCOPE, input_sha256=checksum(path.read_bytes()),
        algorithm=computation.ALGORITHM, output_directory=str(root / "results"),
    )
    return binding, snapshot, folder, path, approval


def run(root, binding, approval):
    return computation.run_descriptive_computation(
        root, binding, input_sha256=approval.input_sha256, approval=approval,
    )


@pytest.mark.parametrize("high,low,expected", [
    (0.3, 0.1, "0.2"), (4000.123456789012, 4000.1, "0.023456789012"),
    (2, 2, "0"), (2.0, 2.0, "0.0"), (1e20, 0.01, "99999999999999999999.99"),
    (1e-30, 1e-31, "0.0000000000000000000000000000009"),
])
def test_decimal_results_preserve_source_and_ignore_ambient_precision(high, low, expected):
    rows = [{"time": 60, "high": high, "low": low}]
    original = canonical_bytes(rows)
    with localcontext() as context:
        context.prec = 2
        result = computation.calculate_bar_ranges(rows)
    assert result == [rows[0] | {"range": expected}]
    assert canonical_bytes(rows) == original
    assert result[0] is not rows[0]


@pytest.mark.parametrize("rows,reason", [
    ([], "ROWS_INVALID"),
    ([{"time": 60, "high": 2}], "ROWS_INVALID"),
    ([{"time": 60, "high": 2, "low": True}], "NUMERIC_INVALID"),
    ([{"time": 60, "high": "2", "low": 1}], "NUMERIC_INVALID"),
    ([{"time": 60, "high": float("nan"), "low": 1}], "NUMERIC_INVALID"),
    ([{"time": 60, "high": 2, "low": float("inf")}], "NUMERIC_INVALID"),
    ([{"time": 60, "high": 1, "low": 2}], "NEGATIVE"),
    ([{"time": True, "high": 2, "low": 1}], "ROWS_INVALID"),
    ([{"time": 60, "high": 2, "low": 1}] * 2, "ROWS_INVALID"),
])
def test_invalid_rows_fail_closed(rows, reason):
    with pytest.raises(ValueError, match=reason):
        computation.calculate_bar_ranges(rows)


def test_result_is_bound_exact_reproducible_and_non_mutating(tmp_path):
    binding, snapshot, folder, source, approval = prepared(tmp_path)
    protected = [source, snapshot, snapshot.with_name("binding.approved.json"),
                 folder / "manifest.json", folder / "data.jsonl"]
    before = {path: path.read_bytes() for path in protected}
    path = run(tmp_path, binding, approval)
    payload, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert run(tmp_path, binding, approval) == path
    assert path.read_bytes() == payload and path.stat().st_mtime_ns == mtime
    assert path.name == f"research_result_{checksum(payload)}.json"
    assert list(path.parent.iterdir()) == [path]
    result, original = json.loads(payload), json.loads(before[source])
    assert result["schema_version"] == "r1-descriptive-result/v1"
    assert result["input_sha256"] == checksum(before[source])
    for key in ("proposal", "scope", "dataset", "window", "timestamp_encoding", "row_count"):
        assert result[key] == original[key]
    assert result["algorithm"] == computation.ALGORITHM and result["formula"] == "high - low"
    assert result["execution_allowed"] is result["generated_code_allowed"] is False
    assert result["range_unit"] == "SOURCE_PRICE_UNIT"
    assert result["range_encoding"] == "EXACT_DECIMAL_STRING"
    assert result["approval"] == approval.model_dump(mode="json", exclude={"output_directory"})
    for row, input_row in zip(result["rows"], original["rows"]):
        assert {k: row[k] for k in ("time", "high", "low")} == input_row
        with localcontext() as context:
            context.prec = 100
            assert Decimal(row["range"]) == Decimal(str(input_row["high"])) - Decimal(str(input_row["low"]))
    assert result["rows_sha256"] == checksum(canonical_bytes(result["rows"]))
    assert {path: path.read_bytes() for path in protected} == before


def test_stage_acceptance_does_not_grant_execution_or_read_package(tmp_path, monkeypatch):
    binding, _, _, source, approval = prepared(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Unapproved computation must not read files or calculate")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(computation, "calculate_bar_ranges", forbidden)
    for unauthorized in (None, approval.model_dump()):
        with pytest.raises(ValueError, match="OPERATOR_APPROVAL_REQUIRED"):
            computation.run_descriptive_computation(
                tmp_path, binding, input_sha256=approval.input_sha256, approval=unauthorized,
            )
    assert not (tmp_path / "results").exists()


@pytest.mark.parametrize("field,value", [
    ("proposal_id", "wrong_proposal"), ("revision_id", "wrong_revision"),
    ("scope", SCOPE.model_copy(update={"trading_scope": "trading_scope_" + "0" * 24})),
    ("input_sha256", "0" * 64), ("output_directory", "elsewhere"),
])
def test_approval_is_bound_to_one_operation_and_destination(tmp_path, field, value):
    binding, _, _, _, approval = prepared(tmp_path)
    changed = approval.model_copy(update={field: value})
    with pytest.raises(ValueError, match="APPROVAL_MISMATCH"):
        computation.run_descriptive_computation(
            tmp_path, binding, input_sha256=approval.input_sha256, approval=changed,
        )
    assert not (tmp_path / "results").exists()


def test_approval_cannot_grant_other_operations_or_trading(tmp_path):
    _, _, _, _, approval = prepared(tmp_path)
    for changes in ({"algorithm": "OTHER"}, {"decision": "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"},
                    {"execution_allowed": True}, {"generated_code_allowed": True}):
        with pytest.raises(ValidationError):
            computation.DescriptiveComputationApproval.model_validate(approval.model_dump() | changes)


@pytest.mark.parametrize("case,reason", [
    ("changed_input", "INPUT_CHECKSUM_MISMATCH"),
    ("changed_binding", "APPROVED_BINDING_MISMATCH"),
    ("changed_proposal", "PROPOSAL_SNAPSHOT_STALE"),
    ("unapproved_revision", "REVISION_NOT_ACCEPTED"),
])
def test_source_changes_rejected_before_calculation(tmp_path, monkeypatch, case, reason):
    binding, snapshot, _, path, approval = prepared(tmp_path)
    if case == "changed_input":
        path.write_bytes(path.read_bytes() + b" ")
    elif case == "changed_binding":
        snapshot.with_name("binding.approved.json").write_bytes(b"{}")
    elif case == "changed_proposal":
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
    else:
        proposal = json.loads(snapshot.read_bytes())
        proposal["reviews"] = []
        snapshot.write_bytes(canonical_bytes(proposal))
        binding["proposal_sha256"] = checksum(snapshot.read_bytes())
        snapshot.with_name("binding.approved.json").write_bytes(canonical_bytes(binding))

    def forbidden(*args):
        pytest.fail("Invalid binding must not calculate")

    monkeypatch.setattr(computation, "calculate_bar_ranges", forbidden)
    with pytest.raises(ValueError, match=reason):
        run(tmp_path, binding, approval)
    assert not (tmp_path / "results").exists()


@pytest.mark.parametrize("case,reason", [
    ("revision", "SCOPE_MISMATCH"), ("scope", "SCOPE_MISMATCH"),
    ("dataset", "DATASET_MISMATCH"), ("manifest", "DATASET_MISMATCH"),
    ("window", "CLOSED_BAR_WINDOW_INVALID"), ("missing_bar", "CLOSED_BAR_WINDOW_INVALID"),
    ("duplicate", "CLOSED_BAR_WINDOW_INVALID"), ("order", "CLOSED_BAR_WINDOW_INVALID"),
    ("missing_field", "ROWS_INVALID"), ("string_price", "NUMERIC_INVALID"),
    ("negative_range", "RANGE_NEGATIVE"), ("trading_authority", "SCOPE_MISMATCH"),
])
def test_even_explicitly_pinned_invalid_packages_fail_closed(tmp_path, case, reason):
    binding, _, _, path, approval = prepared(tmp_path)
    package = json.loads(path.read_bytes())
    if case == "revision":
        package["proposal"]["revision_id"] = "wrong_revision"
    elif case == "scope":
        package["scope"]["trading_scope"] = "trading_scope_" + "0" * 24
    elif case in {"dataset", "manifest"}:
        package["dataset"]["dataset_id" if case == "dataset" else "manifest_sha256"] = "wrong"
    elif case == "window":
        package["window"]["end_exclusive"] = "2026-11-02T12:00:00+00:00"
    elif case == "missing_bar":
        package["rows"].pop()
    elif case == "duplicate":
        package["rows"][1] = package["rows"][0]
    elif case == "order":
        package["rows"].reverse()
    elif case == "missing_field":
        del package["rows"][0]["high"]
    elif case == "string_price":
        package["rows"][0]["high"] = "4000"
    elif case == "negative_range":
        package["rows"][0]["high"] = package["rows"][0]["low"] - 1
    else:
        package["execution_allowed"] = True
    package["rows_sha256"] = checksum(canonical_bytes(package["rows"]))
    payload = canonical_bytes(package)
    new_pin = checksum(payload)
    (path.parent / f"research_input_{new_pin}.json").write_bytes(payload)
    approval = approval.model_copy(update={"input_sha256": new_pin})
    with pytest.raises(ValueError, match=reason):
        run(tmp_path, binding, approval)
    assert not (tmp_path / "results").exists()


def test_existing_result_is_not_overwritten(tmp_path):
    binding, _, _, _, approval = prepared(tmp_path)
    path = run(tmp_path, binding, approval)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="EXISTING_PACKAGE_MISMATCH"):
        run(tmp_path, binding, approval)
    assert path.read_bytes() == b"tampered"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("case", ["malformed", "not_object", "dataset_not_object", "nonfinite", "extra_field"])
def test_invalid_input_schema_fails_before_publication(tmp_path, case):
    binding, _, _, path, approval = prepared(tmp_path)
    package = json.loads(path.read_bytes())
    if case == "malformed":
        payload = b"{"
    elif case == "not_object":
        payload = b"[]"
    elif case == "dataset_not_object":
        package["dataset"] = []
        payload = canonical_bytes(package)
    elif case == "nonfinite":
        package["rows"][0]["high"] = float("nan")
        payload = json.dumps(package).encode()
    else:
        package["rows"][0]["extra"] = "not approved"
        package["rows_sha256"] = checksum(canonical_bytes(package["rows"]))
        payload = canonical_bytes(package)
    pin = checksum(payload)
    (path.parent / f"research_input_{pin}.json").write_bytes(payload)
    approval = approval.model_copy(update={"input_sha256": pin})
    with pytest.raises(ValueError):
        run(tmp_path, binding, approval)
    assert not (tmp_path / "results").exists()


def test_changed_approval_during_computation_does_not_publish(tmp_path, monkeypatch):
    binding, snapshot, _, _, approval = prepared(tmp_path)
    calculate = computation.calculate_bar_ranges

    def changed(rows):
        result = calculate(rows)
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        return result

    monkeypatch.setattr(computation, "calculate_bar_ranges", changed)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        run(tmp_path, binding, approval)
    assert not (tmp_path / "results").exists()
