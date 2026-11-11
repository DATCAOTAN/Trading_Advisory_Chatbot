"""Prepare one approved R1 historical input; never evaluate its hypothesis."""

from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from ..market.timeframes import timeframe_duration_seconds
from .evidence_verification import ApprovedHistoricalSource, HistoricalEvidenceVerifier
from .historical_dataset import canonical_bytes, checksum, load_dataset
from .proposal import ResearchProposal, ResearchScope


SCHEMA = "r1-research-input/v1"
FIELDS = ("time", "high", "low")
ACCEPTED = "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"


def _local(path: Path) -> Path:
    if path.resolve() != path.absolute():
        raise ValueError("RESEARCH_INPUT_PATH_NOT_LOCAL")
    return path


def _publish(directory: Path, payload: bytes, *, prefix: str = "research_input") -> Path:
    _local(directory).mkdir(exist_ok=True)
    path = directory / f"{prefix}_{checksum(payload)}.json"
    temporary = None
    try:
        with NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # Publish complete bytes without replacing an existing entry.
        except FileExistsError:
            if not _local(path).is_file() or path.read_bytes() != payload:
                raise ValueError("RESEARCH_INPUT_EXISTING_PACKAGE_MISMATCH") from None
    finally:
        if temporary is not None:
            temporary.unlink()
    return path


def prepare_research_input(root: Path, expected_binding: dict, *, now: datetime) -> Path:
    """Project one pinned, approved revision into a content-addressed local package."""
    binding_path = _local(root / "readiness" / "binding.approved.json")
    snapshot = _local(root / "readiness" / "proposal.json")
    binding_bytes = binding_path.read_bytes()
    binding = json.loads(binding_bytes)
    if not isinstance(binding, dict) or binding != expected_binding:
        raise ValueError("RESEARCH_INPUT_APPROVED_BINDING_MISMATCH")
    dataset_id = binding.get("dataset_id")
    manifest_pin = binding.get("manifest_sha256")
    if not (isinstance(dataset_id, str) and re.fullmatch(r"research_dataset_[a-f0-9]{24}", dataset_id)
            and isinstance(manifest_pin, str) and re.fullmatch(r"[a-f0-9]{64}", manifest_pin)):
        raise ValueError("RESEARCH_SOURCE_NOT_APPROVED")
    scope = ResearchScope(trading_scope=binding["trading_scope"], account_ref=binding.get("account_ref"))
    proposal_bytes = snapshot.read_bytes()
    proposal = ResearchProposal.replay_pinned_for_readiness(
        proposal_bytes, scope=scope, snapshot_checksum=binding["proposal_sha256"],
    )
    head = proposal.head
    if proposal.proposal_id != binding["proposal_id"] or head.revision_id != binding["revision_id"]:
        raise ValueError("RESEARCH_INPUT_REVISION_MISMATCH")
    if proposal.review_status(head.revision_id) != ACCEPTED:
        raise ValueError("RESEARCH_INPUT_REVISION_NOT_ACCEPTED")
    if head.content.strategy is not None or not head.content.hypothesis.strip() or len(head.content.evidence) != 1:
        raise ValueError("RESEARCH_INPUT_SCOPE_UNSUPPORTED")
    reference = head.content.evidence[0]
    if (reference.evidence_ref != dataset_id or reference.kind != "HISTORICAL_MARKET_DATA"
            or reference.status != "VALIDATED" or reference.window_start is None or reference.window_end is None):
        raise ValueError("RESEARCH_REVISION_EVIDENCE_MISMATCH")

    folder = root / "mt5" / dataset_id
    for path in (folder / "manifest.json", folder / "data.jsonl"):
        if not _local(path).is_file():
            raise ValueError("RESEARCH_SOURCE_UNAVAILABLE")
    verifier = HistoricalEvidenceVerifier(scope, (ApprovedHistoricalSource(folder, manifest_pin, scope),))
    proof = verifier.inspect(proposal, revision_id=head.revision_id, reference=reference, now=now)
    if proof.outcome != "VERIFIED_FOR_DECLARED_SCOPE":
        raise ValueError(proof.reason)

    # Pin the read used for projection too, not just the earlier verification.
    manifest, rows = load_dataset(folder, expected_manifest_checksum=manifest_pin)
    request = manifest["request"]
    if (manifest["dataset_id"] != dataset_id or request["kind"] != "bars"
            or (request["canonical_symbol"], request["timeframe"]) != (proof.symbol, proof.timeframe)):
        raise ValueError("RESEARCH_INPUT_MARKET_SCOPE_MISMATCH")
    step = timeframe_duration_seconds(request["timeframe"])
    start, end = reference.window_start, reference.window_end
    first, last = int(start.timestamp()), int(end.timestamp())
    expected = range(first, last, step)
    selected = [{key: row[key] for key in FIELDS} for row in rows if first <= row["time"] < last]
    if len(selected) != len(expected) or any(
        type(row["time"]) is not int or row["time"] != timestamp
        or any(type(row[key]) not in {int, float} or not math.isfinite(row[key]) for key in ("high", "low"))
        for row, timestamp in zip(selected, expected)
    ):
        raise ValueError("RESEARCH_INPUT_CLOSED_BAR_WINDOW_INVALID")
    payload = canonical_bytes({
        "schema_version": SCHEMA, "execution_allowed": False,
        "scope": scope.model_dump(exclude_none=True),
        "proposal": {"proposal_id": proposal.proposal_id, "revision_id": head.revision_id,
                     "revision_fingerprint": head.content_fingerprint, "export_sha256": binding["proposal_sha256"],
                     "decision": ACCEPTED},
        "dataset": {"dataset_id": dataset_id, "manifest_sha256": manifest_pin,
                    "data_sha256": manifest["data_checksum"], "source": manifest["source"],
                    "account_environment": manifest["account_environment"], "verification": proof.outcome,
                    "symbol": request["canonical_symbol"], "broker_symbol": request["broker_symbol"],
                    "timeframe": request["timeframe"]},
        "window": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "fields": FIELDS, "timestamp_encoding": "UTC_UNIX_SECONDS",
        "row_count": len(selected), "rows_sha256": checksum(canonical_bytes(selected)), "rows": selected,
    })
    if _local(binding_path).read_bytes() != binding_bytes or _local(snapshot).read_bytes() != proposal_bytes:
        raise ValueError("RESEARCH_INPUT_APPROVAL_CHANGED")
    return _publish(root / "inputs", payload)


def prepare_evaluation_input(root: Path, proposal: ResearchProposal, request, source: ApprovedHistoricalSource, *, now: datetime) -> Path:
    """Partition approved real observations; do not simulate signals, fills or performance."""
    from .data_integration import historical_requests, inspect_historical_data

    if proposal.review_status(proposal.head.revision_id) != ACCEPTED:
        raise ValueError("RESEARCH_INPUT_REVISION_NOT_ACCEPTED")
    if request not in historical_requests(proposal)[0]:
        raise ValueError("RESEARCH_INPUT_REVISION_MISMATCH")
    reference = next((item for item in proposal.head.content.evidence if item.evidence_ref == source.folder.name), None)
    if reference is None or reference.status != "VALIDATED":
        raise ValueError("RESEARCH_REVISION_EVIDENCE_MISMATCH")
    proof = HistoricalEvidenceVerifier(proposal.scope, (source,)).inspect(
        proposal, revision_id=proposal.head.revision_id, reference=reference, now=now)
    if proof.outcome != "VERIFIED_FOR_DECLARED_SCOPE":
        raise ValueError(proof.reason)
    approval = {"dataset_id": source.folder.name, "manifest_sha256": source.manifest_checksum,
                "scope": proposal.scope.model_dump(mode="json"), "purpose": "READ_ONLY_HISTORICAL_RESEARCH"}
    report = inspect_historical_data(root, proposal, request,
        {"status": "ACQUIRED", **approval, "source_approval": approval})
    if report["blockers"]:
        raise ValueError(report["blockers"][0])
    manifest, rows = load_dataset(_local(source.folder), expected_manifest_checksum=source.manifest_checksum)
    first, split, last = (int(utc_value.timestamp()) for utc_value in (
        datetime.fromisoformat(request.start), datetime.fromisoformat(request.split), datetime.fromisoformat(request.end)))
    step = timeframe_duration_seconds(request.export.timeframe)
    partitions = {}
    for name, start, end in (("IS", first, split), ("OOS", split, last)):
        selected = [{field: row[field] for field in request.fields} for row in rows if start <= row["time"] < end]
        context = [{field: row[field] for field in request.fields} for row in rows
                   if start - request.warmup * step <= row["time"] < start]
        partitions[name] = {"start_inclusive": start, "end_exclusive": end,
                            "rows": selected, "warmup_context_not_scored": context, "row_count": len(selected)}
    payload = canonical_bytes({
        "schema_version": "r1-evaluation-input/v1", "execution_allowed": False,
        "proposal_id": proposal.proposal_id, "revision_id": proposal.head.revision_id,
        "proposal_sha256": checksum(proposal.to_json().encode()), "specification_id": proposal.head.content.development.specification.specification_id,
        "dataset_id": manifest["dataset_id"], "manifest_sha256": source.manifest_checksum,
        "data_sha256": manifest["data_checksum"], "source": manifest["source"],
        "scope": proposal.scope.model_dump(mode="json"), "fields": request.fields,
        "timestamp_encoding": "UTC_UNIX_SECONDS", "costs": report["costs"], "partitions": partitions,
        "research_computation_authorized": False, "strategy_evaluated": False,
    })
    return _publish(root / "inputs", payload, prefix="research_evaluation_input")
