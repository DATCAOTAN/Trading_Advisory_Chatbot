"""Exact overlap checks and separately authorized three-hour range summaries."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, Inexact, Rounded, ROUND_HALF_EVEN, localcontext
import json
from pathlib import Path

from .descriptive_computation import ALGORITHM as SOURCE_ALGORITHM, DescriptiveComputationApproval, review_research_result
from .historical_dataset import canonical_bytes, checksum, utc
from .input_package import _local, _publish


ALGORITHM = "HOURLY_RANGE_SUMMARY_V1"
SCHEMA = "r1-hourly-range-summary/v1"
PRECISION = {"encoding": "DECIMAL_STRING", "mean_decimal_places": 12, "rounding": "ROUND_HALF_EVEN",
             "median": "EXACT_MIDPOINT_OF_SORTED_POSITIONS_30_AND_31", "min_max": "EXACT_SOURCE_VALUES"}


def compare_verified_overlap(left: dict, right: dict) -> dict:
    if left.get("status") != "VERIFIED" or right.get("status") != "VERIFIED":
        raise ValueError("RESEARCH_RESULT_REVIEW_REQUIRED")
    a, b = left["result"], right["result"]
    if (a["scope"] != b["scope"] or a["proposal"]["proposal_id"] != b["proposal"]["proposal_id"]
            or any(a["dataset"][key] != b["dataset"][key] for key in ("symbol", "broker_symbol", "timeframe"))
            or a["algorithm"] != SOURCE_ALGORITHM or b["algorithm"] != SOURCE_ALGORITHM):
        raise ValueError("RESEARCH_OVERLAP_SCOPE_MISMATCH")
    first = max(utc(a["window"]["start_inclusive"]), utc(b["window"]["start_inclusive"]))
    last = min(utc(a["window"]["end_exclusive"]), utc(b["window"]["end_exclusive"]))
    if first >= last or a["dataset"]["timeframe"] != "M1":
        raise ValueError("RESEARCH_OVERLAP_WINDOW_INVALID")
    by_a, by_b = ({row["time"]: row for row in result["rows"]} for result in (a, b))
    times = list(range(int(first.timestamp()), int(last.timestamp()), 60))
    if any(t not in by_a or t not in by_b for t in times):
        raise ValueError("RESEARCH_OVERLAP_COVERAGE_INVALID")
    differences = []
    matching = 0
    for timestamp in times:
        fields = {key: {"left": str(by_a[timestamp][key]), "right": str(by_b[timestamp][key])}
                  for key in ("high", "low", "range")
                  if Decimal(str(by_a[timestamp][key])) != Decimal(str(by_b[timestamp][key]))}
        if fields:
            differences.append({"utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), "fields": fields})
        else:
            matching += 1
    return {"status": "MATCH" if not differences else "DISCREPANCIES", "observations": len(times),
            "matching_observations": matching, "differences": differences,
            "start_inclusive": first.isoformat(), "end_exclusive": last.isoformat(),
            "left_result_sha256": left["result_sha256"], "right_result_sha256": right["result_sha256"]}


def summarize_hourly_ranges(source: dict) -> list[dict]:
    """Pure summary of already computed ranges; never recalculates high minus low."""
    if source.get("algorithm") != SOURCE_ALGORITHM or source.get("dataset", {}).get("timeframe") != "M1":
        raise ValueError("RESEARCH_SUMMARY_SOURCE_INVALID")
    start, end = (utc(source["window"][key]) for key in ("start_inclusive", "end_exclusive"))
    rows = source.get("rows")
    if (start.minute or start.second or start.microsecond or end != start + timedelta(hours=3)
            or type(source.get("row_count")) is not int or source["row_count"] != 180
            or not isinstance(rows, list) or len(rows) != 180):
        raise ValueError("RESEARCH_SUMMARY_WINDOW_INVALID")
    values = []
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or type(row.get("time")) is not int
                or row["time"] != int(start.timestamp()) + index * 60 or not isinstance(row.get("range"), str)):
            raise ValueError("RESEARCH_SUMMARY_OBSERVATION_INVALID")
        try:
            value = Decimal(row["range"])
        except InvalidOperation:
            raise ValueError("RESEARCH_SUMMARY_RANGE_INVALID") from None
        if not value.is_finite() or value < 0:
            raise ValueError("RESEARCH_SUMMARY_RANGE_INVALID")
        values.append(value)
    groups = []
    for index in range(3):
        ordered = sorted(values[index * 60:(index + 1) * 60])
        # Exact sums/midpoints and guard digits before the sole rounded statistic.
        precision = max(v.adjusted() for v in ordered) - min(-12, min(v.as_tuple().exponent for v in ordered)) + 16
        with localcontext() as context:
            context.prec = max(28, precision)
            context.rounding = ROUND_HALF_EVEN
            context.traps[Inexact] = context.traps[Rounded] = False
            mean = (sum(ordered, Decimal(0)) / Decimal(60)).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN)
            median = (ordered[29] + ordered[30]) / Decimal(2)
            groups.append({
                "start_inclusive": (start + timedelta(hours=index)).isoformat(),
                "end_exclusive": (start + timedelta(hours=index + 1)).isoformat(), "count": 60,
                "mean": format(mean, "f"), "median": format(median, "f"),
                "min": format(ordered[0], "f"), "max": format(ordered[-1], "f"),
            })
    return groups


def run_hourly_summary(
    root: Path, expected_binding: dict, result_binding: dict, *, approval: DescriptiveComputationApproval | None = None,
) -> Path:
    if not isinstance(approval, DescriptiveComputationApproval):
        raise ValueError("RESEARCH_COMPUTATION_OPERATOR_APPROVAL_REQUIRED")
    root = _local(root.absolute())
    if (approval.algorithm != ALGORITHM or approval.input_sha256 != result_binding.get("result_sha256")
            or approval.proposal_id != expected_binding.get("proposal_id")
            or approval.revision_id != expected_binding.get("revision_id")
            or approval.scope.model_dump(exclude_none=True) != {
                key: expected_binding[key] for key in ("trading_scope", "account_ref") if key in expected_binding
            } or approval.output_directory != str(root / "results")):
        raise ValueError("RESEARCH_COMPUTATION_APPROVAL_MISMATCH")
    review_args = dict(root=root, binding=json.dumps(expected_binding), result_binding=json.dumps(result_binding),
                       trading_scope=approval.scope.trading_scope)
    report = review_research_result(**review_args)
    if report["status"] != "VERIFIED":
        raise ValueError(report["reason"])
    source = report["result"]
    groups = summarize_hourly_ranges(source)
    payload = canonical_bytes({
        "schema_version": SCHEMA, "algorithm": ALGORITHM, "source_algorithm": SOURCE_ALGORITHM,
        "execution_allowed": False, "generated_code_allowed": False,
        "approval": approval.model_dump(mode="json", exclude={"output_directory"}),
        "source_result_sha256": result_binding["result_sha256"], "input_sha256": result_binding["input_sha256"],
        "proposal": source["proposal"], "scope": source["scope"], "dataset": source["dataset"], "window": source["window"],
        "precision_policy": PRECISION, "unit": "SOURCE_PRICE_UNIT", "group_count": 3,
        "groups_sha256": checksum(canonical_bytes(groups)), "groups": groups,
        "limitations": ["Descriptive historical ranges only; no predictive, profitability or statistical-significance claim."],
    })
    if review_research_result(**review_args) != report:
        raise ValueError("RESEARCH_SUMMARY_SOURCE_CHANGED")
    return _publish(root / "results", payload, prefix="research_summary")
