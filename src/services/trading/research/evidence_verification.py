"""Read-only verification against explicitly approved Sprint 11 artifacts."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Literal

from ..market.timeframes import timeframe_duration_seconds
from .historical_dataset import SCHEMA, load_dataset, utc
from .proposal import EvidenceReference, ResearchProposal, ResearchRevision, ResearchScope


MT5_SOURCE = "MT5_AUTHENTICATED_LOCAL_TERMINAL"
HISTORICAL_EVALUATION_VERSION = SCHEMA.replace("/", ":")


@dataclass(frozen=True)
class ApprovedHistoricalSource:
    # Path and manifest pin come from a trusted source owner, not from a proposal.
    folder: Path
    manifest_checksum: str
    scope: ResearchScope


@dataclass(frozen=True)
class EvidenceVerification:
    proposal_id: str
    revision_id: str
    revision_fingerprint: str
    scope: ResearchScope
    reference: EvidenceReference
    verified_at: datetime
    outcome: Literal[
        "VERIFIED_FOR_DECLARED_SCOPE", "PARTIAL_OR_LIMITED", "PENDING_VERIFICATION",
        "INVALID_OR_MISMATCHED", "SOURCE_UNAVAILABLE",
    ]
    reason: str
    integrity: Literal["NOT_CHECKED", "VALID", "INVALID"] = "NOT_CHECKED"
    provenance: Literal["NOT_CHECKED", "APPROVED", "MISMATCH"] = "NOT_CHECKED"
    coverage: str = "NOT_CHECKED"
    symbol: str | None = None
    timeframe: str | None = None
    limitations: tuple[str, ...] = ()
    claim_support: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    strategy_performance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class HistoricalEvidenceVerifier:
    def __init__(self, scope: ResearchScope, sources: tuple[ApprovedHistoricalSource, ...]):
        self._scope = scope
        self._sources = {source.folder.name: source for source in sources if source.scope == scope}
        if len(self._sources) != sum(source.scope == scope for source in sources):
            raise ValueError("RESEARCH_SOURCE_APPROVAL_CONFLICT")

    def inspect(
        self, proposal: ResearchProposal, *, revision_id: str, reference: EvidenceReference, now: datetime,
    ) -> EvidenceVerification:
        if proposal.scope != self._scope:
            raise ValueError("RESEARCH_SCOPE_MISMATCH")
        revision = next((item for item in proposal.revisions if item.revision_id == revision_id), None)
        if revision is None or reference not in revision.content.evidence:
            raise ValueError("RESEARCH_REVISION_EVIDENCE_MISMATCH")
        return self._inspect(proposal, revision, reference, utc(now))

    def verify_revision(
        self, proposal: ResearchProposal, revision: ResearchRevision, item: EvidenceReference,
    ) -> bool:
        return self.inspect(
            proposal, revision_id=revision.revision_id, reference=item, now=datetime.now(timezone.utc),
        ).outcome == "VERIFIED_FOR_DECLARED_SCOPE"

    def _inspect(
        self, proposal: ResearchProposal, revision: ResearchRevision, reference: EvidenceReference, now: datetime,
    ) -> EvidenceVerification:
        result = EvidenceVerification(
            proposal.proposal_id, revision.revision_id, revision.content_fingerprint, proposal.scope,
            reference, now, "PENDING_VERIFICATION", "RESEARCH_EVIDENCE_OWNER_UNAVAILABLE",
        )
        if reference.kind != "HISTORICAL_MARKET_DATA":
            return result
        invalid = replace(result, outcome="INVALID_OR_MISMATCHED")
        if reference.source_ref != MT5_SOURCE:
            return replace(invalid, reason="RESEARCH_SOURCE_IDENTITY_MISMATCH")
        source = self._sources.get(reference.evidence_ref)
        if source is None:
            return replace(result, outcome="SOURCE_UNAVAILABLE", reason="RESEARCH_SOURCE_NOT_APPROVED")
        try:
            manifest, rows = load_dataset(
                source.folder, require_verified=False, expected_manifest_checksum=source.manifest_checksum,
            )
            if (
                manifest.get("source") != MT5_SOURCE
                or manifest.get("account_environment") != "DEMO" or manifest.get("execution_authority") is not False
                or manifest.get("artifact_type") != "RESEARCH_DATASET"
            ):
                return replace(invalid, integrity="VALID", provenance="MISMATCH",
                               reason="RESEARCH_SOURCE_PROVENANCE_MISMATCH")
            request = manifest["request"]
            acquired = utc(manifest["acquired_at"])
            start, end = utc(request["start"]), utc(request["end"])
            if not end <= acquired <= now:
                return replace(invalid, integrity="INVALID", reason="RESEARCH_SOURCE_TIME_INVALID")
        except (FileNotFoundError, PermissionError):
            return replace(result, outcome="SOURCE_UNAVAILABLE", reason="RESEARCH_SOURCE_UNAVAILABLE")
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError) as exc:
            code = str(exc) if type(exc) is ValueError and str(exc) in {
                "DATASET_MANIFEST_INTEGRITY_INVALID", "DATASET_CHECKSUM_MISMATCH",
                "DATASET_IDENTITY_MISMATCH", "DATASET_QUALITY_MISMATCH", "UTC_AWARE_DATETIME_REQUIRED",
                "RESEARCH_SOURCE_PIN_MISMATCH",
            } else "RESEARCH_SOURCE_ARTIFACT_INVALID"
            return replace(invalid, integrity="INVALID", reason=code)

        quality = manifest["quality"]
        verified_source = replace(
            result, integrity="VALID", provenance="APPROVED", coverage=quality["status"],
            symbol=request["canonical_symbol"], timeframe=request["timeframe"],
            limitations=tuple(quality["limitations"]),
        )
        if quality["status"] == "INVALID":
            return replace(verified_source, outcome="INVALID_OR_MISMATCHED", reason="RESEARCH_SOURCE_DATA_INVALID")
        strategy = revision.content.strategy
        symbols = (strategy.canonical_symbol,) if strategy else proposal.brief.symbols
        timeframes = strategy.timeframes if strategy else revision.content.timeframes
        if not symbols or not timeframes or reference.window_start is None:
            return replace(verified_source, reason="RESEARCH_HYPOTHESIS_SCOPE_INCOMPLETE")
        if verified_source.symbol not in symbols or verified_source.timeframe not in timeframes:
            return replace(verified_source, outcome="INVALID_OR_MISMATCHED", reason="RESEARCH_MARKET_SCOPE_MISMATCH")
        required_start, required_end = reference.window_start, reference.window_end
        limited = replace(verified_source, outcome="PARTIAL_OR_LIMITED", reason="RESEARCH_COVERAGE_INSUFFICIENT")
        if quality["status"] != "VERIFIED" or request["kind"] != "bars" or not start <= required_start < required_end <= end:
            return limited
        step = timeframe_duration_seconds(verified_source.timeframe)
        first, last = required_start.timestamp(), required_end.timestamp()
        if first % step or last % step:
            return replace(verified_source, outcome="INVALID_OR_MISMATCHED", reason="RESEARCH_WINDOW_NOT_ALIGNED")
        if sum(first <= row["time"] < last for row in rows) != (last - first) / step:
            return limited
        if reference.status == "VALIDATED" and (
            reference.data_quality != "VERIFIED" or reference.evaluation_version != HISTORICAL_EVALUATION_VERSION
        ):
            return replace(verified_source, outcome="INVALID_OR_MISMATCHED", reason="RESEARCH_EVIDENCE_CLAIM_MISMATCH")
        return replace(verified_source, outcome="VERIFIED_FOR_DECLARED_SCOPE", reason="RESEARCH_HISTORICAL_BAR_WINDOW_VERIFIED")


def review_research_readiness(*, root: Path, binding: str, trading_scope: str, now: datetime) -> dict:
    """Inspect one trusted host binding; neither paths nor approvals come from chat."""
    proposal_state = {"status": "NOT_CHECKED", "reason": "RESEARCH_PROPOSAL_NOT_CONFIGURED"}
    evidence_state = {"outcome": "NOT_CHECKED", "reason": "RESEARCH_REVISION_NOT_VERIFIED"}
    report = {"proposal": proposal_state, "evidence": evidence_state}
    if not binding:
        return report
    try:
        pin = json.loads(binding)
        if not isinstance(pin, dict):
            raise ValueError
        if pin.get("trading_scope") != trading_scope:
            proposal_state["reason"] = "RESEARCH_SCOPE_MISMATCH"
            return report
        scope = ResearchScope(trading_scope=trading_scope, account_ref=pin.get("account_ref"))
        if not all(isinstance(pin.get(key), str) and re.fullmatch(pattern, pin[key]) for key, pattern in (
            ("proposal_id", r"proposal_[a-f0-9]{64}"),
            ("revision_id", r"revision_[a-f0-9]{64}"),
            ("proposal_sha256", r"[a-f0-9]{64}"),
        )):
            raise ValueError
    except (TypeError, ValueError, RecursionError):
        proposal_state["reason"] = "RESEARCH_BINDING_INVALID"
        return report

    snapshot = root / "readiness" / "proposal.json"
    try:
        if snapshot.resolve() != snapshot.absolute():
            raise ValueError("RESEARCH_PROPOSAL_PATH_NOT_LOCAL")
        if not snapshot.is_file():
            raise FileNotFoundError
        payload = snapshot.read_bytes()
        proposal = ResearchProposal.replay_pinned_for_readiness(
            payload, scope=scope, snapshot_checksum=pin["proposal_sha256"],
        )
        if proposal.proposal_id != pin["proposal_id"]:
            raise ValueError("RESEARCH_PROPOSAL_ID_MISMATCH")
        status = proposal.review_status(pin["revision_id"])
    except (OSError, RuntimeError):
        proposal_state["reason"] = "RESEARCH_PROPOSAL_UNAVAILABLE"
        return report
    except ValueError as exc:
        proposal_state["reason"] = str(exc)
        return report
    if status == "SUPERSEDED":
        proposal_state.update(status=status, reason="RESEARCH_REVIEW_STALE")
        return report

    head = proposal.head
    accepted = status == "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"
    proposal_state.update(
        status=status, reason="RESEARCH_REVISION_ACCEPTED" if accepted else "RESEARCH_REVISION_NOT_ACCEPTED",
        readiness=head.review_readiness(), revision_id=head.revision_id,
    )

    dataset_id, manifest_pin = pin.get("dataset_id"), pin.get("manifest_sha256")
    if not (isinstance(dataset_id, str) and re.fullmatch(r"research_dataset_[a-f0-9]{24}", dataset_id)
            and isinstance(manifest_pin, str) and re.fullmatch(r"[a-f0-9]{64}", manifest_pin)):
        evidence_state.update(outcome="SOURCE_UNAVAILABLE", reason="RESEARCH_SOURCE_NOT_APPROVED")
        return report
    references = [item for item in head.content.evidence
                  if item.kind == "HISTORICAL_MARKET_DATA" and item.evidence_ref == dataset_id]
    if len(references) != 1:
        evidence_state["reason"] = "RESEARCH_REVISION_EVIDENCE_MISMATCH"
        return report
    reference = references[0]
    folder = root / "mt5" / dataset_id
    try:
        for path in (folder, folder / "manifest.json", folder / "data.jsonl"):
            if path.resolve() != path.absolute() or (path != folder and path.exists() and not path.is_file()):
                evidence_state["reason"] = "RESEARCH_SOURCE_PATH_NOT_LOCAL"
                return report
        owner = HistoricalEvidenceVerifier(scope, (ApprovedHistoricalSource(folder, manifest_pin, scope),))
        result = owner.inspect(proposal, revision_id=head.revision_id, reference=reference, now=now)
    except (OSError, RuntimeError, ValueError):
        evidence_state["reason"] = "RESEARCH_EVIDENCE_VERIFICATION_FAILED"
        return report
    # Do not return evidence from a snapshot replaced while the verifier was reading.
    try:
        unchanged = snapshot.resolve() == snapshot.absolute() and snapshot.is_file() and snapshot.read_bytes() == payload
    except (OSError, RuntimeError):
        unchanged = False
    if not unchanged:
        proposal_state.clear()
        proposal_state.update(status="NOT_CHECKED", reason="RESEARCH_PROPOSAL_SNAPSHOT_STALE")
        return report
    evidence_state.update(
        outcome=result.outcome, reason=result.reason, integrity=result.integrity,
        provenance=result.provenance, coverage=result.coverage, symbol=result.symbol,
        timeframe=result.timeframe, limitations=result.limitations,
        checked_at=result.verified_at.isoformat(),
        window=(reference.window_start.isoformat(), reference.window_end.isoformat()) if reference.window_start else None,
    )
    return report
