"""One trusted, operator-approved historical operation; no generated code or trading."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..market.timeframes import timeframe_duration_seconds
from .historical_dataset import canonical_bytes, checksum
from .input_package import ACCEPTED, FIELDS, SCHEMA as INPUT_SCHEMA, _local, _publish
from .proposal import Ref, ResearchProposal, ResearchScope


ALGORITHM = "HIGH_MINUS_LOW_V1"
SCHEMA = "r1-descriptive-result/v1"


class DescriptiveComputationApproval(BaseModel):
    """Trusted caller supplies this only after a separate exact operator decision."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    decision: Literal["APPROVED_FOR_DESCRIPTIVE_COMPUTATION"]
    proposal_id: Ref
    revision_id: Ref
    scope: ResearchScope
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    algorithm: Literal["HIGH_MINUS_LOW_V1", "HOURLY_RANGE_SUMMARY_V1", "HISTORICAL_FEATURES_V1", "HISTORICAL_SIGNALS_V1"]
    output_directory: str
    execution_allowed: Literal[False] = False
    generated_code_allowed: Literal[False] = False


def _validate_range_rows(rows: list[dict]) -> None:
    if not rows:
        raise ValueError("RESEARCH_RANGE_ROWS_INVALID")
    previous = None
    for row in rows:
        if (not isinstance(row, dict) or set(row) != set(FIELDS)
                or type(row["time"]) is not int or (previous is not None and row["time"] <= previous)):
            raise ValueError("RESEARCH_RANGE_ROWS_INVALID")
        if any(type(row[key]) not in {int, float} or not Decimal(str(row[key])).is_finite()
               for key in ("high", "low")):
            raise ValueError("RESEARCH_RANGE_NUMERIC_INVALID")
        if row["high"] < row["low"]:
            raise ValueError("RESEARCH_RANGE_NEGATIVE")
        previous = row["time"]


def calculate_bar_ranges(rows: list[dict]) -> list[dict]:
    """Pure decimal subtraction of canonical JSON prices, preserving input observations."""
    _validate_range_rows(rows)
    result = []
    for row in rows:
        high, low = (Decimal(str(row[key])) for key in ("high", "low"))
        # Enough precision for exact subtraction, independent of the process decimal context.
        with localcontext() as context:
            context.prec = max(high.adjusted(), low.adjusted()) - min(
                high.as_tuple().exponent, low.as_tuple().exponent,
            ) + 2
            result.append(row | {"range": format(high - low, "f")})
    return result


def _load_approved_input(
    root: Path, expected_binding: dict, *, input_sha256: str, scope: ResearchScope,
    archive_binding_sha256: str | None = None,
):
    """Shared read-only checks for computation and subsequent result consumption."""
    root = _local(root.absolute())
    binding_path = _local(root / "readiness" / "binding.approved.json")
    proposal_path = _local(root / "readiness" / "proposal.json")
    if archive_binding_sha256 is not None:
        if not re.fullmatch(r"[a-f0-9]{64}", archive_binding_sha256):
            raise ValueError("RESEARCH_ARCHIVE_PIN_INVALID")
        archive = root / "readiness" / "archive"
        binding_path = _local(archive / f"binding_{archive_binding_sha256}.json")
        proposal_pin = expected_binding.get("proposal_sha256", "")
        if not isinstance(proposal_pin, str) or not re.fullmatch(r"[a-f0-9]{64}", proposal_pin):
            raise ValueError("RESEARCH_ARCHIVE_PIN_INVALID")
        proposal_path = _local(archive / f"proposal_{proposal_pin}.json")
    binding_bytes, proposal_bytes = binding_path.read_bytes(), proposal_path.read_bytes()
    if archive_binding_sha256 is not None and checksum(binding_bytes) != archive_binding_sha256:
        raise ValueError("RESEARCH_ARCHIVE_BINDING_CHECKSUM_MISMATCH")
    if json.loads(binding_bytes) != expected_binding:
        raise ValueError("RESEARCH_INPUT_APPROVED_BINDING_MISMATCH")
    proposal = ResearchProposal.replay_pinned_for_readiness(
        proposal_bytes, scope=scope, snapshot_checksum=expected_binding["proposal_sha256"],
    )
    head = proposal.head
    if (proposal.proposal_id != expected_binding["proposal_id"] or head.revision_id != expected_binding["revision_id"]
            or proposal.review_status(head.revision_id) != ACCEPTED):
        raise ValueError("RESEARCH_COMPUTATION_REVISION_NOT_ACCEPTED")
    if head.content.strategy is not None or len(head.content.evidence) != 1:
        raise ValueError("RESEARCH_INPUT_SCOPE_UNSUPPORTED")
    reference = head.content.evidence[0]
    if (reference.evidence_ref != expected_binding["dataset_id"] or reference.status != "VALIDATED"
            or reference.kind != "HISTORICAL_MARKET_DATA"
            or reference.window_start is None or reference.window_end is None):
        raise ValueError("RESEARCH_REVISION_EVIDENCE_MISMATCH")

    path = _local(root / "inputs" / f"research_input_{input_sha256}.json")
    payload = path.read_bytes()
    if checksum(payload) != input_sha256:
        raise ValueError("RESEARCH_INPUT_CHECKSUM_MISMATCH")
    try:
        package = json.loads(payload)
        canonical = canonical_bytes(package)
    except ValueError:
        raise ValueError("RESEARCH_INPUT_SCHEMA_INVALID") from None
    if not isinstance(package, dict) or canonical != payload:
        raise ValueError("RESEARCH_INPUT_SCHEMA_INVALID")
    if (package.get("schema_version") != INPUT_SCHEMA or package.get("execution_allowed") is not False
            or package.get("timestamp_encoding") != "UTC_UNIX_SECONDS" or package.get("fields") != list(FIELDS)
            or package.get("scope") != scope.model_dump(exclude_none=True)
            or package.get("proposal") != {
                "proposal_id": proposal.proposal_id, "revision_id": head.revision_id,
                "revision_fingerprint": head.content_fingerprint,
                "export_sha256": expected_binding["proposal_sha256"], "decision": ACCEPTED,
            }):
        raise ValueError("RESEARCH_INPUT_SCOPE_MISMATCH")
    dataset = package.get("dataset", {})
    if (not isinstance(dataset, dict) or dataset.get("dataset_id") != expected_binding["dataset_id"]
            or dataset.get("manifest_sha256") != expected_binding["manifest_sha256"]
            or dataset.get("verification") != "VERIFIED_FOR_DECLARED_SCOPE"
            or dataset.get("source") != reference.source_ref
            or dataset.get("timeframe") not in head.content.timeframes):
        raise ValueError("RESEARCH_INPUT_DATASET_MISMATCH")
    step = timeframe_duration_seconds(dataset["timeframe"])
    start, end = reference.window_start, reference.window_end
    rows = package.get("rows")
    if (package.get("window") != {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()}
            or start.microsecond or end.microsecond or int(start.timestamp()) % step or int(end.timestamp()) % step
            or not isinstance(rows, list) or type(package.get("row_count")) is not int
            or package["row_count"] != len(rows)
            or len(rows) != len(range(int(start.timestamp()), int(end.timestamp()), step))
            or any(not isinstance(row, dict) or type(row.get("time")) is not int or row["time"] != timestamp
                   for row, timestamp in zip(rows, range(int(start.timestamp()), int(end.timestamp()), step)))
            or package.get("rows_sha256") != checksum(canonical_bytes(rows))):
        raise ValueError("RESEARCH_INPUT_CLOSED_BAR_WINDOW_INVALID")

    return package, proposal, {path: payload, binding_path: binding_bytes, proposal_path: proposal_bytes}


def run_descriptive_computation(
    root: Path, expected_binding: dict, *, input_sha256: str,
    approval: DescriptiveComputationApproval | None = None,
) -> Path:
    """Run only the approved revision/package/operation at the approved destination."""
    if not isinstance(approval, DescriptiveComputationApproval):
        raise ValueError("RESEARCH_COMPUTATION_OPERATOR_APPROVAL_REQUIRED")
    root = _local(root.absolute())
    output = _local(root / "results")
    if (approval.input_sha256 != input_sha256 or approval.algorithm != ALGORITHM
            or approval.proposal_id != expected_binding.get("proposal_id")
            or approval.revision_id != expected_binding.get("revision_id")
            or approval.scope.model_dump(exclude_none=True) != {
                key: expected_binding[key] for key in ("trading_scope", "account_ref") if key in expected_binding
            } or approval.output_directory != str(output)):
        raise ValueError("RESEARCH_COMPUTATION_APPROVAL_MISMATCH")
    package, _, sources = _load_approved_input(root, expected_binding, input_sha256=input_sha256, scope=approval.scope)
    computed = calculate_bar_ranges(package["rows"])
    result = canonical_bytes({
        "schema_version": SCHEMA, "algorithm": ALGORITHM, "formula": "high - low",
        "execution_allowed": False, "generated_code_allowed": False,
        "approval": approval.model_dump(mode="json", exclude={"output_directory"}),
        "input_sha256": input_sha256, "proposal": package["proposal"], "scope": package["scope"],
        "dataset": package["dataset"], "window": package["window"], "timestamp_encoding": "UTC_UNIX_SECONDS",
        "range_encoding": "EXACT_DECIMAL_STRING", "range_unit": "SOURCE_PRICE_UNIT",
        "fields": [*FIELDS, "range"], "row_count": len(computed),
        "rows_sha256": checksum(canonical_bytes(computed)), "rows": computed,
    })
    if any(_local(path).read_bytes() != payload for path, payload in sources.items()):
        raise ValueError("RESEARCH_COMPUTATION_SOURCE_CHANGED")
    return _publish(output, result, prefix="research_result")


def review_research_result(
    *, root: Path, binding: str, result_binding: str, trading_scope: str,
    archive_binding_sha256: str | None = None,
) -> dict:
    """Inspect one host-pinned result without executing or rechecking its arithmetic."""
    if not binding or not result_binding:
        return {"status": "NOT_CHECKED", "reason": "RESEARCH_RESULT_NOT_CONFIGURED"}
    try:
        pin, result_pin = json.loads(binding), json.loads(result_binding)
        if not isinstance(pin, dict) or not isinstance(result_pin, dict) or set(result_pin) != {"input_sha256", "result_sha256"}:
            raise ValueError("RESEARCH_RESULT_BINDING_INVALID")
        if pin.get("trading_scope") != trading_scope:
            raise ValueError("RESEARCH_SCOPE_MISMATCH")
        if any(not isinstance(result_pin[key], str) or not re.fullmatch(r"[a-f0-9]{64}", result_pin[key])
               for key in result_pin):
            raise ValueError("RESEARCH_RESULT_BINDING_INVALID")
        scope = ResearchScope(trading_scope=trading_scope, account_ref=pin.get("account_ref"))
        root = _local(root.absolute())
        path = _local(root / "results" / f"research_result_{result_pin['result_sha256']}.json")
        try:
            payload = path.read_bytes()
        except OSError:
            return {"status": "BLOCKED", "reason": "RESEARCH_RESULT_UNAVAILABLE"}
        if checksum(payload) != result_pin["result_sha256"]:
            raise ValueError("RESEARCH_RESULT_CHECKSUM_MISMATCH")
        result = json.loads(payload)
        if not isinstance(result, dict) or canonical_bytes(result) != payload:
            raise ValueError("RESEARCH_RESULT_SCHEMA_INVALID")
        if (result.get("schema_version") != SCHEMA or result.get("algorithm") != ALGORITHM
                or result.get("formula") != "high - low" or result.get("execution_allowed") is not False
                or result.get("generated_code_allowed") is not False
                or result.get("fields") != [*FIELDS, "range"]
                or result.get("range_encoding") != "EXACT_DECIMAL_STRING"
                or result.get("range_unit") != "SOURCE_PRICE_UNIT"):
            raise ValueError("RESEARCH_RESULT_SCHEMA_INVALID")
        if result.get("input_sha256") != result_pin["input_sha256"]:
            raise ValueError("RESEARCH_RESULT_INPUT_MISMATCH")
        package, proposal, sources = _load_approved_input(
            root, pin, input_sha256=result_pin["input_sha256"], scope=scope,
            archive_binding_sha256=archive_binding_sha256,
        )
        expected_approval = DescriptiveComputationApproval(
            decision="APPROVED_FOR_DESCRIPTIVE_COMPUTATION", proposal_id=pin["proposal_id"],
            revision_id=pin["revision_id"], scope=scope, input_sha256=result_pin["input_sha256"],
            algorithm=ALGORITHM, output_directory=str(root / "results"),
        ).model_dump(mode="json", exclude={"output_directory"})
        if result.get("approval") != expected_approval:
            raise ValueError("RESEARCH_RESULT_APPROVAL_MISMATCH")
        for key in ("proposal", "scope", "dataset", "window", "timestamp_encoding", "row_count"):
            if result.get(key) != package[key] or type(result.get(key)) is not type(package[key]):
                raise ValueError("RESEARCH_RESULT_PROVENANCE_MISMATCH")
        _validate_range_rows(package["rows"])
        rows = result.get("rows")
        if (not isinstance(rows, list) or len(rows) != package["row_count"]
                or result.get("rows_sha256") != checksum(canonical_bytes(rows))):
            raise ValueError("RESEARCH_RESULT_ROWS_INVALID")
        for row, original in zip(rows, package["rows"]):
            if (not isinstance(row, dict) or set(row) != {*FIELDS, "range"}
                    or any(type(row[key]) is not type(original[key]) or row[key] != original[key] for key in FIELDS)
                    or not isinstance(row["range"], str) or not Decimal(row["range"]).is_finite()
                    or Decimal(row["range"]) < 0):
                raise ValueError("RESEARCH_RESULT_ROWS_INVALID")
        sources[path] = payload
        if any(_local(source).read_bytes() != raw for source, raw in sources.items()):
            raise ValueError("RESEARCH_RESULT_REVIEW_STALE")
        return {
            "status": "VERIFIED", "reason": "RESEARCH_RESULT_PIN_AND_PROVENANCE_VERIFIED",
            "objective": proposal.head.content.hypothesis, "result_sha256": result_pin["result_sha256"],
            "result": result,
            "observations": [{"UTC timestamp": datetime.fromtimestamp(row["time"], timezone.utc).isoformat(),
                              "High": str(row["high"]), "Low": str(row["low"]), "Range": row["range"]} for row in rows],
        }
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError, InvalidOperation, RecursionError):
        return {"status": "BLOCKED", "reason": "RESEARCH_RESULT_SCHEMA_INVALID"}
    except (OSError, RuntimeError):
        return {"status": "BLOCKED", "reason": "RESEARCH_INPUT_OR_APPROVAL_UNAVAILABLE"}
    except ValueError as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
