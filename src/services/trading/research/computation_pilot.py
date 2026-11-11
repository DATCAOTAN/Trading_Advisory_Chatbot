"""G2 trusted-host contracts. This module cannot invoke a provider or launch code."""

from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
import json
import math

from src.services.semantic.structured_semantics import ComputationalSpecification
from src.services.trading.market.timeframes import timeframe_duration_seconds

from .evidence_verification import ApprovedHistoricalSource, HistoricalEvidenceVerifier
from .historical_dataset import canonical_bytes, checksum, load_dataset
from .proposal import EvidenceReference, ResearchProposal


ISOLATION_GATE = "G2_ISOLATION_APPROVAL_REQUIRED"
ALGORITHM = "VOLUME_WEIGHTED_CLOSE_LOCATION_V1"
INPUT_FIELDS = ("time", "high", "low", "close", "tick_volume")
OUTPUT_FIELDS = ("time", "value")
MAX_SOURCE_BYTES = 8192
CODEGEN_MAX_TOKENS = 1600
MAX_BARS = 120


def pilot_specification(symbol: str, timeframe: str, window: int = 5) -> ComputationalSpecification:
    if type(window) is not int or not 2 <= window <= 30:
        raise ValueError("G2_WINDOW_INVALID")
    if not timeframe_duration_seconds(timeframe) or not symbol:
        raise ValueError("G2_MARKET_SCOPE_INVALID")
    return ComputationalSpecification.model_validate({
        "objective": "Measure rolling close location weighted by observed tick volume.",
        "algorithm": ALGORITHM,
        "formula": "sum(volume * (2*close-high-low)/(high-low)) / sum(volume) over the trailing window",
        "temporal_requirements": ["Only use the current and earlier completed bars."],
        "parameters": [{"name": "window", "value": window, "minimum": 2, "maximum": 30, "unit": "bars"}],
        "data_requirements": [{
            "dataset": "OHLCV", "fields": list(INPUT_FIELDS), "symbol": symbol,
            "timeframe": timeframe, "lookback_bars": 30, "warmup_bars": window - 1,
            "completeness": "Contiguous completed bars", "usage": "RESEARCH_ONLY",
        }],
        "outputs": [{
            "name": "value", "unit": "ratio",
            "validity": "Finite [-1,1]; null before warm-up or if total volume is zero. Flat bars contribute zero to numerator.",
        }],
    })


@dataclass(frozen=True)
class PreparedComputation:
    job_id: str
    specification: ComputationalSpecification
    dataset_id: str
    manifest_checksum: str
    dataset_checksum: str
    source: str
    symbol: str
    timeframe: str
    window_start: str
    window_end: str
    input_checksum: str
    input_bytes: bytes = field(repr=False)
    coverage: str = field(default="VERIFIED_FOR_DECLARED_SCOPE", init=False)
    status: str = field(default=ISOLATION_GATE, init=False)

    @property
    def codegen_prompt(self) -> str:
        return (
            'Return one JSON object {"source":"..."} defining pure Python compute(bars, window). '
            "Use standard library math only; no I/O, subprocess, environment access or network. "
            "Bars are oldest first. Return a list of {time,value} rows in that order, including nulls. "
            "Do not include markdown or any tool request. Specification: "
            + canonical_bytes(self.specification.as_dict()).decode("utf-8")
        )


def prepare_pilot(
    specification: ComputationalSpecification,
    approved_source: ApprovedHistoricalSource,
    proposal: ResearchProposal,
    reference: EvidenceReference,
    *,
    now: datetime,
) -> PreparedComputation:
    """Accept one independently pinned, contiguous bar window from the R2 owner."""
    if len(specification.parameters) != 1 or len(specification.data_requirements) != 1:
        raise ValueError("G2_PILOT_SPECIFICATION_UNSUPPORTED")
    window = specification.parameters[0].value
    requirement = specification.data_requirements[0]
    if specification != pilot_specification(requirement.symbol or "", requirement.timeframe or "", window):
        raise ValueError("G2_PILOT_SPECIFICATION_UNSUPPORTED")
    proof = HistoricalEvidenceVerifier(proposal.scope, (approved_source,)).inspect(
        proposal, revision_id=proposal.head.revision_id, reference=reference, now=now,
    )
    if proof.outcome != "VERIFIED_FOR_DECLARED_SCOPE":
        raise ValueError(proof.reason)
    if (proof.symbol, proof.timeframe) != (requirement.symbol, requirement.timeframe):
        raise ValueError("G2_DATA_REQUIREMENT_SCOPE_MISMATCH")

    # Recheck the independent pin after loading the exact bytes used for the copy.
    manifest, rows = load_dataset(approved_source.folder)
    if manifest["manifest_checksum"] != approved_source.manifest_checksum:
        raise ValueError("RESEARCH_SOURCE_PIN_MISMATCH")
    start, end = reference.window_start, reference.window_end
    assert start is not None and end is not None
    step = timeframe_duration_seconds(requirement.timeframe)
    count = int((end - start).total_seconds()) // step
    if count < requirement.lookback_bars + requirement.warmup_bars:
        raise ValueError("G2_LOOKBACK_OR_WARMUP_INSUFFICIENT")
    if count > MAX_BARS:
        raise ValueError("G2_PILOT_WINDOW_TOO_LARGE")
    selected = [
        {key: row[key] for key in INPUT_FIELDS} for row in rows
        if start.timestamp() <= row["time"] and row["time"] + step <= end.timestamp()
    ]
    if len(selected) != count or any(
        type(row[key]) not in {int, float} or not math.isfinite(row[key])
        for row in selected for key in INPUT_FIELDS
    ):
        raise ValueError("G2_CLOSED_BAR_INPUT_INVALID")
    payload = canonical_bytes(selected)
    input_checksum = checksum(payload)
    material = {
        "specification_id": specification.specification_id, "manifest_checksum": manifest["manifest_checksum"],
        "input_checksum": input_checksum, "research_revision": proof.revision_fingerprint,
    }
    return PreparedComputation(
        "g2_job_" + checksum(canonical_bytes(material)), specification, manifest["dataset_id"],
        manifest["manifest_checksum"], manifest["data_checksum"], manifest["source"],
        proof.symbol, proof.timeframe, start.isoformat(), end.isoformat(), input_checksum, payload,
    )


@dataclass(frozen=True)
class GeneratedSource:
    job_id: str
    specification_id: str
    manifest_checksum: str
    input_checksum: str
    source_checksum: str
    source: str = field(repr=False)
    artifact_version: str = field(default="g2-generated-source/v1", init=False)
    status: str = field(default="GENERATED_UNVERIFIED", init=False)
    output_fields: tuple[str, ...] = field(default=OUTPUT_FIELDS, init=False)


def capture_source_reply(job: PreparedComputation, reply: str) -> GeneratedSource:
    """Validate the bounded reply envelope and hash source as inert UTF-8 bytes."""
    if type(reply) is not str or len(reply) > 2 * MAX_SOURCE_BYTES:
        raise ValueError("G2_SOURCE_REPLY_INVALID")
    try:
        parsed = json.loads(reply)
        if type(parsed) is not dict or set(parsed) != {"source"} or type(parsed["source"]) is not str:
            raise ValueError
        source = parsed["source"]
        encoded = source.encode("utf-8")
        if not source.strip() or len(encoded) > MAX_SOURCE_BYTES or "\0" in source:
            raise ValueError
    except (ValueError, RecursionError):
        raise ValueError("G2_SOURCE_REPLY_INVALID") from None
    return GeneratedSource(
        job.job_id, job.specification.specification_id, job.manifest_checksum,
        job.input_checksum, checksum(encoded), source,
    )


def _oracle(rows: list[dict], window: int) -> list[float | None]:
    weighted = []
    for row in rows:
        high, low, close = (Fraction(str(row[key])) for key in ("high", "low", "close"))
        volume = row["tick_volume"]
        weighted.append((volume, volume * (2 * close - high - low) / (high - low) if high != low else 0))
    result = [None] * min(window - 1, len(rows))
    for end in range(window, len(rows) + 1):
        items = weighted[end - window:end]
        volume = sum(item[0] for item in items)
        result.append(float(sum(item[1] for item in items) / volume) if volume else None)
    return result


def check_output_vectors(
    job: PreparedComputation, *, full: list, replay: list, prefixes: tuple[list, ...],
) -> None:
    """Check claimed vectors only. Success cannot attest that any worker ran."""
    if checksum(job.input_bytes) != job.input_checksum:
        raise ValueError("G2_INPUT_CHECKSUM_MISMATCH")
    rows = json.loads(job.input_bytes)
    expected = _oracle(rows, job.specification.parameters[0].value)
    if len(prefixes) != len(rows) - 1:
        raise ValueError("G2_PREFIX_EVIDENCE_MISSING")
    for vector, length in ((full, len(rows)), (replay, len(rows)), *((item, i) for i, item in enumerate(prefixes, 1))):
        if type(vector) is not list or len(vector) != length:
            raise ValueError("G2_OUTPUT_SHAPE_INVALID")
        for row, target, output in zip(rows, expected, vector):
            if (
                type(output) is not dict or set(output) != set(OUTPUT_FIELDS)
                or type(output["time"]) is not int or output["time"] != row["time"]
            ):
                raise ValueError("G2_OUTPUT_SHAPE_INVALID")
            value = output["value"]
            if target is None:
                if value is not None:
                    raise ValueError("G2_WARMUP_OR_MISSING_VALUE_INVALID")
            elif (
                type(value) not in {int, float} or not -1 <= value <= 1
                or not math.isclose(value, target, rel_tol=1e-10, abs_tol=1e-12)
            ):
                raise ValueError("G2_NUMERICAL_VERIFICATION_FAILED")
    if replay != full or any(prefix != full[:i] for i, prefix in enumerate(prefixes, 1)):
        raise ValueError("G2_REPLAY_OR_PREFIX_MISMATCH")
