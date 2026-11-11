"""Approved historical prefix replay through Trading Core, not a new indicator engine."""
from bisect import bisect_right
from datetime import datetime
import math
from pathlib import Path
import platform

from ..market import indicators
from ..market.timeframes import timeframe_duration_seconds
from ..reasoning import strategy_evidence
from .data_integration import historical_requests, resolve_data_dependencies
from .descriptive_computation import DescriptiveComputationApproval
from .historical_dataset import canonical_bytes, checksum, load_dataset
from .input_package import _local, _publish, load_evaluation_input


ALGORITHM = "HISTORICAL_FEATURES_V1"
SCHEMA = "r1-research-features/v1"
MAX_PREFIX_WORK = 5_000_000
MAX_RESULT_CELLS = 100_000


def feature_plan(proposal) -> dict:
    supported, blocked = [], []
    development = proposal.head.content.development
    if development is None:
        return {"supported": [], "blocked": [], "blockers": ["RESEARCH_SPECIFICATION_REQUIRED"]}
    blockers = []
    for index, requirement in enumerate(development.specification.data_requirements):
        resolved = resolve_data_dependencies(requirement)
        blockers.extend(resolved["blockers"])
        declarations = {item.name: item for item in requirement.computations}
        for item in resolved["derived_computations"]:
            entry = {**item, "id": f"requirement_{index}:{item['name']}", "symbol": requirement.symbol,
                     "requirement_index": index, "parameters": dict(declarations[item["name"]].parameters)}
            (supported if item["status"] == "SUPPORTED_REGISTRY_CONTRACT" else blocked).append(entry)
    return {"supported": supported, "blocked": blocked, "blockers": list(dict.fromkeys(blockers))}


def _calculation_pin() -> str:
    return checksum(canonical_bytes({
        "adapter": checksum(Path(__file__).read_bytes()),
        "production_snapshot": checksum(Path(strategy_evidence.__file__).read_bytes()),
        "production_math": checksum(Path(indicators.__file__).read_bytes()),
        "python": platform.python_version(),
    }))


def inspect_feature_request(root, proposal, inputs, *, now: datetime) -> tuple[dict, list]:
    """Reverify approved inputs, without calculating features or publishing anything."""
    plan = feature_plan(proposal)
    requests, missing = historical_requests(proposal)
    if missing or plan["blockers"]:
        raise ValueError("RESEARCH_FEATURE_DEPENDENCIES_UNRESOLVED")
    if not plan["supported"]:
        raise ValueError("RESEARCH_FEATURE_NO_SUPPORTED_COMPUTATIONS")
    if {request.request_id for request, _, _ in inputs} != {request.request_id for request in requests} or len(inputs) != len(requests):
        raise ValueError("RESEARCH_FEATURE_INPUTS_INCOMPLETE")
    loaded, pins = [], []
    for request, source, pin in sorted(inputs, key=lambda row: row[0].request_id):
        package, payload = load_evaluation_input(root, proposal, request, source, pin, now=now)
        loaded.append((request, source, pin, package, payload))
        pins.append({"request_id": request.request_id, "input_sha256": pin,
                     "dataset_id": package["dataset_id"], "manifest_sha256": package["manifest_sha256"],
                     "data_sha256": package["data_sha256"], "symbol": request.export.canonical_symbol,
                     "timeframe": request.export.timeframe})
    request = {"algorithm": ALGORITHM, "proposal_id": proposal.proposal_id, "revision_id": proposal.head.revision_id,
               "proposal_sha256": checksum(proposal.to_json().encode()), "scope": proposal.scope.model_dump(mode="json"),
               "specification_id": proposal.head.content.development.specification.specification_id, "inputs": pins,
               "calculations": plan, "calculation_sha256": _calculation_pin()}
    return {**request, "request_sha256": checksum(canonical_bytes(request))}, loaded


def _replay_series(package, step, computations):
    train, test = package["partitions"]["IS"], package["partitions"]["OOS"]
    history = [*train["warmup_context_not_scored"], *train["rows"], *test["rows"]]
    result, shared = [], {}
    for item in computations:
        key = (item["indicator_id"], tuple(sorted(item["parameters"].items())), item["formula_version"])
        if key not in shared:
            values = []
            spec = strategy_evidence.IndicatorSpec(item["indicator_id"], item["timeframe"],
                tuple(sorted(item["parameters"].items())), "research_feature")
            required = strategy_evidence.INDICATOR_REGISTRY[item["indicator_id"]].warmup(item["parameters"])
            for index, row in enumerate(history):
                output = {"time": row["time"], "completed_at": row["time"] + step,
                          "partition": "WARMUP_CONTEXT" if row["time"] < train["start_inclusive"] else
                                       "IS" if row["time"] < train["end_exclusive"] else "OOS"}
                if index + 1 < required:
                    values.append({**output, "status": "INSUFFICIENT_HISTORY", "computed": None})
                    continue
                # shortcut: bounded prefix replay preserves production seeding; batch only after parity proof if this budget is insufficient.
                try:
                    computed = strategy_evidence.calculate_indicator_snapshot((spec,), history[:index + 1])["indicators"][spec.output_alias]
                except (ValueError, OverflowError, ZeroDivisionError):
                    values.append({**output, "status": "PRODUCTION_INDICATOR_BLOCKED", "computed": None})
                    continue
                if computed.get("formula") != item["formula_version"] or computed.get("parameters") != item["parameters"]:
                    raise ValueError("RESEARCH_FEATURE_CALCULATION_CONTRACT_MISMATCH")
                values.append({**output, "status": "COMPUTED", "computed": computed})
            shared[key] = values
        rows = []
        component = "current" if item["output_field"] == "value" else item["output_field"]
        for index, row in enumerate(shared[key]):
            if index + 1 < item["warmup"]:
                rows.append({key: value for key, value in row.items() if key != "computed"} | {
                    "value": None, "status": "INSUFFICIENT_HISTORY"})
                continue
            value = row["computed"].get(component) if row["computed"] is not None else None
            if row["computed"] is not None and component not in row["computed"]:
                raise ValueError("RESEARCH_FEATURE_OUTPUT_COMPONENT_MISSING")
            valid = type(value) in {float, int} and math.isfinite(value)
            rows.append({key: value for key, value in row.items() if key != "computed"} | {
                "value": value if valid else None,
                "status": row["status"] if valid or row["computed"] is None else "INDICATOR_RESULT_INVALID"})
        result.append({**item, "seed_open_time": history[0]["time"], "rows": rows})
    return result


def calculate_historical_features(loaded, calculations) -> dict:
    """Pure bounded fixture-testable adapter; never evaluates arbitrary expressions."""
    work, cells, scored_count, grouped = 0, 0, 0, []
    for request, _, _, package, _ in loaded:
        items = [item for item in calculations["supported"] if
                 (item["symbol"], item["timeframe"]) == (request.export.canonical_symbol, request.export.timeframe)]
        count = sum(len(package["partitions"][part]["rows"]) for part in ("IS", "OOS")) + len(package["partitions"]["IS"]["warmup_context_not_scored"])
        unique = {(item["indicator_id"], tuple(sorted(item["parameters"].items())), item["formula_version"]) for item in items}
        work += len(unique) * count * (count + 1) // 2
        cells += count * len(items)
        scored_count += sum(len(package["partitions"][part]["rows"]) for part in ("IS", "OOS"))
        grouped.append((request, package, items))
    if work > MAX_PREFIX_WORK:
        raise ValueError("RESEARCH_FEATURE_PREFIX_BUDGET_EXCEEDED")
    if cells + scored_count * len(calculations["supported"]) > MAX_RESULT_CELLS:
        raise ValueError("RESEARCH_FEATURE_RESULT_BUDGET_EXCEEDED")
    series = [item for request, package, items in grouped for item in
              _replay_series(package, timeframe_duration_seconds(request.export.timeframe), items)]
    aligned = {}
    times = {item["id"]: [row["completed_at"] for row in item["rows"]] for item in series}
    for partition in ("IS", "OOS"):
        points = sorted({row["completed_at"] for item in series for row in item["rows"] if row["partition"] == partition})
        observations = []
        for point in points:
            values = {}
            for item in series:
                index = bisect_right(times[item["id"]], point) - 1
                row = item["rows"][index] if index >= 0 else None
                values[item["id"]] = {"value": row["value"] if row else None,
                    "source_open_time": row["time"] if row else None,
                    "source_completed_at": row["completed_at"] if row else None,
                    "status": row["status"] if row else "NO_COMPLETED_VALUE"}
            observations.append({"evaluation_time": point, "values": values})
        aligned[partition] = observations
    return {"series": series, "aligned_partitions": aligned, "blocked_computations": calculations["blocked"],
            "status": "PARTIAL" if calculations["blocked"] or any(
                row["value"] is None for item in series for row in item["rows"] if row["partition"] != "WARMUP_CONTEXT") else "COMPUTED",
            "history_semantics": "CONTIGUOUS_APPROVED_PREFIX_IS_HISTORY_IS_PAST_CONTEXT_FOR_OOS"}


def run_historical_features(root, proposal, inputs, *, approval=None, now: datetime):
    if not isinstance(approval, DescriptiveComputationApproval):
        raise ValueError("RESEARCH_COMPUTATION_OPERATOR_APPROVAL_REQUIRED")
    descriptor, loaded = inspect_feature_request(root, proposal, inputs, now=now)
    output = _local(root.absolute() / "results")
    if (approval.algorithm != ALGORITHM or approval.input_sha256 != descriptor["request_sha256"]
            or approval.proposal_id != proposal.proposal_id or approval.revision_id != proposal.head.revision_id
            or approval.scope != proposal.scope or approval.output_directory != str(output)):
        raise ValueError("RESEARCH_COMPUTATION_APPROVAL_MISMATCH")
    computed = calculate_historical_features(loaded, descriptor["calculations"])
    for _, source, pin, package, payload in loaded:
        if _local(root / "inputs" / f"research_evaluation_input_{pin}.json").read_bytes() != payload:
            raise ValueError("RESEARCH_COMPUTATION_SOURCE_CHANGED")
        manifest, _ = load_dataset(source.folder, expected_manifest_checksum=package["manifest_sha256"])
        if manifest["data_checksum"] != package["data_sha256"]:
            raise ValueError("RESEARCH_COMPUTATION_SOURCE_CHANGED")
    if descriptor["calculation_sha256"] != _calculation_pin():
        raise ValueError("RESEARCH_FEATURE_CALCULATION_CHANGED")
    return _publish(output, canonical_bytes({"schema_version": SCHEMA, **descriptor, **computed,
        "approval": approval.model_dump(mode="json", exclude={"output_directory"}),
        "execution_allowed": False, "generated_code_allowed": False, "strategy_evaluated": False,
        "numeric_encoding": "PRODUCTION_FLOAT64_JSON_ROUNDTRIP"}), prefix="research_features")


def bound_feature_inputs(root, proposal, record):
    from .data_integration import approved_sources, matching_history

    requests, missing = historical_requests(proposal)
    if missing or not requests:
        raise ValueError("RESEARCH_FEATURE_DEPENDENCIES_UNRESOLVED")
    sources = {item.folder.name: item for item in approved_sources(root, record, proposal.scope)}
    result = []
    for request in requests:
        _, item = matching_history(record, request)
        package = item.get("input_package") if item else None
        if not package or package.get("revision_id") != proposal.head.revision_id:
            raise ValueError("RESEARCH_FEATURE_INPUT_PREPARATION_REQUIRED")
        source = sources.get(item.get("dataset_id"))
        if source is None:
            raise ValueError("RESEARCH_SOURCE_NOT_APPROVED")
        result.append((request, source, package["sha256"]))
    return result


def load_feature_result(root, descriptor, result_sha256):
    import json
    import re

    if not isinstance(result_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", result_sha256):
        raise ValueError("RESEARCH_FEATURE_RESULT_PIN_INVALID")
    payload = _local(root / "results" / f"research_features_{result_sha256}.json").read_bytes()
    if checksum(payload) != result_sha256:
        raise ValueError("RESEARCH_FEATURE_RESULT_CHECKSUM_MISMATCH")
    result = json.loads(payload)
    if (result.get("schema_version") != SCHEMA or result.get("request_sha256") != descriptor["request_sha256"]
            or any(result.get(key) != value for key, value in descriptor.items())
            or result.get("execution_allowed") is not False or result.get("generated_code_allowed") is not False
            or result.get("strategy_evaluated") is not False):
        raise ValueError("RESEARCH_FEATURE_RESULT_BINDING_MISMATCH")
    return result
