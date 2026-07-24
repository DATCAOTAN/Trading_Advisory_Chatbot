from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TypeVar

from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_SCHEMA_VERSION,
    AutonomousDecisionCandidate,
    AutonomousDecisionConfig,
    AutonomousDecisionOrchestrator,
    AutonomousDecisionRunResult,
    AutonomousDecisionValidationResult,
    AutonomousOrderMarketSnapshot,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
    PENDING_EXECUTION_REQUEST_VERSION,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    ControlledPendingOrderContract,
    ControlledPendingOrderDryRunMapper,
    ControlledPendingOrderValidation,
    PendingOrderDryRunRequestDraft,
    SUPPORTED_PENDING_ORDER_TYPES,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
)
from src.services.trading.proposal.models import HumanConfirmedProposalIntent
from src.services.trading.review.models import HumanReviewArtifact


PENDING_CANDIDATE_HANDOFF_SCHEMA = "protected-pending-candidate-handoff/v1"
PENDING_ARTIFACT_BUNDLE_SCHEMA = "protected-pending-artifact-bundle/v1"
DEFAULT_PROTECTED_ROOT = Path("data/trading/protected_requests")
_MAX_FILE_BYTES = 1_000_000
_TUPLE_CANDIDATE_FIELDS = {
    "proposed_semantic_parameter_references",
    "knowledge_evidence_references",
    "blocked_reason_codes",
    "structured_reasoning",
}
_UNSAFE_TRUE_FLAGS = {
    "execution_authority",
    "execution_permission_requested",
    "live_submission_allowed",
    "live_execution_allowed",
    "order_send_allowed",
    "execution_allowed",
    "executable",
    "order_sent",
    "real_mt5_payload_created",
    "broker_submittable_request_dict_created",
    "mt5_constants_used",
    "bridge_request_created",
}


class PendingArtifactExportError(ValueError):
    """Fail-closed error carrying a deterministic public blocker code."""


@dataclass(frozen=True)
class PendingCandidateHandoffResult:
    candidate_reference_redacted: str
    schema_version: str
    order_type: str
    validation_status: str
    export_status: str
    artifact_path: str


@dataclass(frozen=True)
class PendingArtifactExportResult:
    artifact_reference_redacted: str
    schema_version: str
    pending_order_family: str
    validation_status: str
    blockers: tuple[str, ...]
    freshness_status: str
    account_context_match: bool
    export_status: str
    executable: bool
    order_send_allowed: bool
    artifact_path: str


def write_pending_candidate_handoff(
    *,
    run_result: AutonomousDecisionRunResult,
    review_artifact: HumanReviewArtifact,
    confirmation_intent: HumanConfirmedProposalIntent,
    output_dir: str | Path,
    confirmation_phrase: str,
    current_time: datetime | None = None,
    protected_root: str | Path = DEFAULT_PROTECTED_ROOT,
) -> PendingCandidateHandoffResult:
    """Persist an explicit protected snapshot of the already-produced typed candidate."""
    now = _utc(current_time)
    _require_export_phrase(confirmation_phrase)
    if not isinstance(run_result, AutonomousDecisionRunResult):
        raise PendingArtifactExportError("AUTHORITATIVE_TYPED_RUN_RESULT_REQUIRED")
    candidate = run_result.candidate
    snapshot = run_result.order_market_snapshot
    if snapshot is None:
        raise PendingArtifactExportError("MARKET_SNAPSHOT_REQUIRED")
    if candidate.schema_version != AUTONOMOUS_DECISION_SCHEMA_VERSION:
        raise PendingArtifactExportError("PENDING_CANDIDATE_SCHEMA_V2_REQUIRED")
    if candidate.action != "PENDING" or candidate.order_type not in SUPPORTED_PENDING_ORDER_TYPES:
        raise PendingArtifactExportError("PENDING_CANDIDATE_REQUIRED")
    if not run_result.validation.valid or run_result.validation.issues:
        raise PendingArtifactExportError("CANDIDATE_VALIDATION_BLOCKED")

    validator = _candidate_validator(protected_root)
    validation = validator.validate_candidate(candidate, now=now)
    if not validation.valid or validation.issues:
        raise PendingArtifactExportError(_first_blocker(validation.issues, "CANDIDATE_INVALID"))
    _validate_review_bindings(candidate, review_artifact, confirmation_intent)
    _require_fresh(candidate.expires_at, now, "CANDIDATE_EXPIRED", expiry=True)
    _require_fresh(snapshot.observed_at, now, "MARKET_SNAPSHOT_STALE")
    _require_fresh(review_artifact.created_at, now, "HUMAN_REVIEW_STALE")
    _require_fresh(confirmation_intent.created_at, now, "CONFIRMATION_STALE")

    source_material = {
        "candidate": asdict(candidate),
        "validation": asdict(validation),
        "market_snapshot": asdict(snapshot),
        "review_artifact": review_artifact.as_dict(),
        "confirmation_intent": confirmation_intent.as_dict(),
    }
    source_binding_hash = _digest(source_material)
    payload = {
        "schema_version": PENDING_CANDIDATE_HANDOFF_SCHEMA,
        "created_at": now.isoformat(),
        "candidate_reference": candidate.candidate_reference,
        "source_binding_hash": source_binding_hash,
        "export_confirmation_reference": _digest(
            {
                "phrase": EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
                "candidate_reference": candidate.candidate_reference,
                "source_binding_hash": source_binding_hash,
            }
        ),
        **source_material,
        "execution_authority": False,
        "execution_permission_requested": False,
        "live_submission_allowed": False,
        "order_send_allowed": False,
        "executable": False,
        "order_sent": False,
        "metadata_redacted": True,
    }
    root = _protected_root(protected_root)
    directory = _protected_path(output_dir, root)
    target = directory / f"pending-candidate-{candidate.candidate_reference[-24:]}.json"
    status = _write_json_idempotent(target, payload, conflict_code="CANDIDATE_HANDOFF_CONFLICT")
    return PendingCandidateHandoffResult(
        candidate_reference_redacted=_redact(candidate.candidate_reference),
        schema_version=PENDING_CANDIDATE_HANDOFF_SCHEMA,
        order_type=candidate.order_type,
        validation_status="VALID",
        export_status=status,
        artifact_path=_relative_path(target, root),
    )


def export_pending_artifact_bundle(
    *,
    candidate_artifact: str | Path,
    account_context_artifact: str | Path,
    output_dir: str | Path,
    confirmation_phrase: str,
    current_time: datetime | None = None,
    protected_root: str | Path = DEFAULT_PROTECTED_ROOT,
) -> PendingArtifactExportResult:
    """Build and export the existing pending protected request without execution permission."""
    now = _utc(current_time)
    _require_export_phrase(confirmation_phrase)
    root = _protected_root(protected_root)
    handoff_path = _protected_path(candidate_artifact, root, must_exist=True)
    account_path = _protected_path(account_context_artifact, root, must_exist=True)
    handoff = _load_json(handoff_path)
    _validate_handoff_payload(handoff, now)

    candidate = _load_model(
        AutonomousDecisionCandidate,
        _mapping(handoff, "candidate"),
        tuple_fields=_TUPLE_CANDIDATE_FIELDS,
    )
    validation = _load_model(
        AutonomousDecisionValidationResult,
        _mapping(handoff, "validation"),
        tuple_fields={"issues", "warnings"},
    )
    snapshot = _load_model(
        AutonomousOrderMarketSnapshot,
        _mapping(handoff, "market_snapshot"),
        tuple_fields={"source_refs"},
    )
    review = _load_model(HumanReviewArtifact, _mapping(handoff, "review_artifact"))
    confirmation = _load_model(
        HumanConfirmedProposalIntent, _mapping(handoff, "confirmation_intent")
    )
    account = _load_model(ProtectedAccountContextCapture, _load_json(account_path))
    if validation.valid is not True or validation.issues:
        raise PendingArtifactExportError("CANDIDATE_VALIDATION_BLOCKED")

    mapper = ControlledPendingOrderDryRunMapper(_candidate_validator(root))
    dry_run = mapper.build(
        candidate=candidate,
        market_snapshot=snapshot,
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account,
        expected_account_context_fingerprint=account.account_context_fingerprint,
        now=now,
    )
    if not dry_run.validation.valid or dry_run.request_draft is None:
        raise PendingArtifactExportError(
            _first_blocker(dry_run.validation.blockers, "PENDING_VALIDATION_BLOCKED")
        )
    try:
        request = MT5ControlledExecutionRequest.from_pending_artifacts(
            dry_run.contract,
            dry_run.validation,
            dry_run.request_draft,
            None,
            expected_account_context_fingerprint=account.account_context_fingerprint,
            human_confirmation_phrase=confirmation_phrase.strip(),
            execution_permission_requested=False,
            validation_only=True,
            now=now,
        )
    except ValueError as exc:
        raise PendingArtifactExportError(str(exc) or "PENDING_REQUEST_INVALID") from exc

    contract_payload = dry_run.contract.to_protected_dict()
    draft_payload = asdict(dry_run.request_draft)
    request_payload = request.as_protected_dict()
    _require_non_executable(contract_payload)
    _require_non_executable(request_payload)
    if request.request_version != PENDING_EXECUTION_REQUEST_VERSION:
        raise PendingArtifactExportError("PENDING_REQUEST_SCHEMA_INVALID")
    source_binding_hash = _digest(
        {
            "handoff_source_binding_hash": handoff["source_binding_hash"],
            "account_context_fingerprint": account.account_context_fingerprint,
            "confirmation_reference": request.human_confirmation_reference,
        }
    )
    output = _protected_path(output_dir, root)
    if output.exists():
        existing = validate_pending_artifact_bundle(output, protected_root=root)
        existing_manifest = _load_json(output / "manifest.json")
        if existing_manifest.get("source_binding_hash") != source_binding_hash:
            raise PendingArtifactExportError("PENDING_ARTIFACT_CONFLICT")
        return PendingArtifactExportResult(
            artifact_reference_redacted=existing.artifact_reference_redacted,
            schema_version=existing.schema_version,
            pending_order_family=existing.pending_order_family,
            validation_status=existing.validation_status,
            blockers=existing.blockers,
            freshness_status=existing.freshness_status,
            account_context_match=existing.account_context_match,
            export_status="IDEMPOTENT",
            executable=False,
            order_send_allowed=False,
            artifact_path=existing.artifact_path,
        )

    file_payloads = {
        "pending-contract.json": contract_payload,
        "pending-draft.json": draft_payload,
        "controlled-request.json": request_payload,
    }
    manifest = {
        "schema_version": PENDING_ARTIFACT_BUNDLE_SCHEMA,
        "created_at": now.isoformat(),
        "request_schema_version": PENDING_EXECUTION_REQUEST_VERSION,
        "candidate_reference": candidate.candidate_reference,
        "contract_reference": dry_run.contract.contract_reference,
        "draft_reference": dry_run.request_draft.draft_reference,
        "source_binding_hash": source_binding_hash,
        "files": {name: _digest(payload) for name, payload in file_payloads.items()},
        "validation_status": "VALID",
        "freshness_status": "VALID",
        "account_context_match": True,
        "execution_authority": False,
        "execution_permission_requested": False,
        "live_submission_allowed": False,
        "order_send_allowed": False,
        "executable": False,
        "order_sent": False,
        "metadata_redacted": True,
    }
    _write_bundle_atomic(output, file_payloads, manifest)
    verified = validate_pending_artifact_bundle(output, protected_root=root)
    return PendingArtifactExportResult(
        artifact_reference_redacted=verified.artifact_reference_redacted,
        schema_version=verified.schema_version,
        pending_order_family=verified.pending_order_family,
        validation_status=verified.validation_status,
        blockers=verified.blockers,
        freshness_status=verified.freshness_status,
        account_context_match=verified.account_context_match,
        export_status="CREATED",
        executable=False,
        order_send_allowed=False,
        artifact_path=verified.artifact_path,
    )


def validate_pending_artifact_bundle(
    output_dir: str | Path,
    *,
    protected_root: str | Path = DEFAULT_PROTECTED_ROOT,
) -> PendingArtifactExportResult:
    root = _protected_root(protected_root)
    output = _protected_path(output_dir, root, must_exist=True)
    manifest = _load_json(output / "manifest.json")
    if manifest.get("schema_version") != PENDING_ARTIFACT_BUNDLE_SCHEMA:
        raise PendingArtifactExportError("PENDING_MANIFEST_SCHEMA_INVALID")
    if manifest.get("request_schema_version") != PENDING_EXECUTION_REQUEST_VERSION:
        raise PendingArtifactExportError("PENDING_REQUEST_SCHEMA_INVALID")
    _require_non_executable(manifest)
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {
        "pending-contract.json",
        "pending-draft.json",
        "controlled-request.json",
    }:
        raise PendingArtifactExportError("PENDING_MANIFEST_FILES_INVALID")
    payloads: dict[str, dict[str, Any]] = {}
    for name, expected_hash in files.items():
        payload = _load_json(output / name)
        if not hmac.compare_digest(str(expected_hash), _digest(payload)):
            raise PendingArtifactExportError("PENDING_ARTIFACT_HASH_MISMATCH")
        payloads[name] = payload

    contract = _load_model(
        ControlledPendingOrderContract,
        payloads["pending-contract.json"],
        tuple_fields={"blocker_codes", "source_refs"},
    )
    if not contract.integrity_valid() or contract.validation_status != "VALID":
        raise PendingArtifactExportError("PENDING_CONTRACT_INTEGRITY_INVALID")
    draft = _load_draft(payloads["pending-draft.json"], contract)
    if not draft.integrity_valid(contract):
        raise PendingArtifactExportError("PENDING_DRAFT_INTEGRITY_INVALID")
    request = payloads["controlled-request.json"]
    if (
        request.get("request_version") != PENDING_EXECUTION_REQUEST_VERSION
        or request.get("canonical_semantic_hash") != contract.canonical_integrity_hash
        or request.get("approved_semantic_parameters") != contract.to_protected_dict()
        or request.get("execution_permission_requested") is not False
        or request.get("pre_submit_validation_valid") is not False
    ):
        raise PendingArtifactExportError("PENDING_REQUEST_BINDING_INVALID")
    _require_non_executable(contract.to_protected_dict())
    _require_non_executable(request)
    reference = _digest(manifest)
    return PendingArtifactExportResult(
        artifact_reference_redacted=_redact(reference),
        schema_version=PENDING_EXECUTION_REQUEST_VERSION,
        pending_order_family=_pending_family(contract.order_type),
        validation_status="VALID",
        blockers=(),
        freshness_status=str(manifest.get("freshness_status", "UNKNOWN")),
        account_context_match=manifest.get("account_context_match") is True,
        export_status="VALIDATED",
        executable=False,
        order_send_allowed=False,
        artifact_path=_relative_path(output, root),
    )


def _validate_handoff_payload(payload: Mapping[str, Any], now: datetime) -> None:
    if payload.get("schema_version") != PENDING_CANDIDATE_HANDOFF_SCHEMA:
        raise PendingArtifactExportError("PENDING_HANDOFF_SCHEMA_INVALID")
    _require_non_executable(payload)
    material = {
        key: payload.get(key)
        for key in (
            "candidate",
            "validation",
            "market_snapshot",
            "review_artifact",
            "confirmation_intent",
        )
    }
    source_binding_hash = str(payload.get("source_binding_hash", ""))
    if not hmac.compare_digest(source_binding_hash, _digest(material)):
        raise PendingArtifactExportError("PENDING_HANDOFF_INTEGRITY_INVALID")
    candidate = material["candidate"]
    if not isinstance(candidate, dict) or payload.get("candidate_reference") != candidate.get("candidate_reference"):
        raise PendingArtifactExportError("PENDING_HANDOFF_REFERENCE_MISMATCH")
    expected_confirmation_reference = _digest(
        {
            "phrase": EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
            "candidate_reference": payload.get("candidate_reference"),
            "source_binding_hash": source_binding_hash,
        }
    )
    if not hmac.compare_digest(
        str(payload.get("export_confirmation_reference", "")),
        expected_confirmation_reference,
    ):
        raise PendingArtifactExportError("PENDING_HANDOFF_CONFIRMATION_MISMATCH")
    _require_fresh(str(payload.get("created_at", "")), now, "PENDING_HANDOFF_STALE")


def _validate_review_bindings(candidate, review, confirmation) -> None:
    required = {candidate.candidate_reference, candidate.provenance_hash, candidate.structured_order_hash}
    if (
        review.review_status != "READY_FOR_REVIEW"
        or review.blockers
        or review.symbol != candidate.symbol_reference
        or not required.issubset(set(review.source_refs))
    ):
        raise PendingArtifactExportError("HUMAN_REVIEW_CANDIDATE_BINDING_MISMATCH")
    if (
        confirmation.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
        or confirmation.human_confirmation_state != "CONFIRMED_PROPOSAL_WORKFLOW"
        or confirmation.proposal_workflow_allowed is not True
        or confirmation.dry_run_only is not True
        or confirmation.executable is not False
        or confirmation.source_review_artifact_id != review.artifact_id
        or not confirmation.artifact_hash
        or not required.issubset(set(confirmation.source_refs))
        or not confirmation.confirmation_phrase_required
        or not hmac.compare_digest(
            confirmation.confirmation_phrase_required,
            confirmation.confirmation_phrase_received,
        )
    ):
        raise PendingArtifactExportError("CONFIRMATION_CANDIDATE_BINDING_MISMATCH")


def _load_draft(payload: Mapping[str, Any], contract: ControlledPendingOrderContract) -> PendingOrderDryRunRequestDraft:
    draft = _load_model(PendingOrderDryRunRequestDraft, payload)
    _require_non_executable(payload)
    return draft


def _candidate_validator(protected_root: str | Path) -> AutonomousDecisionOrchestrator:
    return AutonomousDecisionOrchestrator(
        AutonomousDecisionConfig(journal_path=str(Path(protected_root) / ".validation-only-unused.jsonl"))
    )


def _require_export_phrase(value: str) -> None:
    if str(value or "").strip() != EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE:
        raise PendingArtifactExportError("EXPORT_ONLY_CONFIRMATION_INVALID")


def _require_fresh(value: str, now: datetime, code: str, *, expiry: bool = False) -> None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise PendingArtifactExportError(code) from exc
    if expiry:
        invalid = parsed <= now
    else:
        invalid = parsed > now or (now - parsed).total_seconds() > 300
    if invalid:
        raise PendingArtifactExportError(code)


def _require_non_executable(payload: Mapping[str, Any]) -> None:
    for key in _UNSAFE_TRUE_FLAGS:
        if payload.get(key) is True:
            raise PendingArtifactExportError("EXECUTION_FLAG_NOT_ALLOWED")


def _mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PendingArtifactExportError("PENDING_HANDOFF_CONTENT_INVALID")
    return value


_Model = TypeVar("_Model")


def _load_model(model_type: type[_Model], payload: Mapping[str, Any], tuple_fields: set[str] | None = None) -> _Model:
    names = {item.name for item in fields(model_type)}
    if set(payload) != names:
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_MODEL_MISMATCH")
    values = dict(payload)
    for name in tuple_fields or set():
        values[name] = tuple(values.get(name) or ())
    try:
        return model_type(**values)
    except (TypeError, ValueError) as exc:
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_MODEL_MISMATCH") from exc


def _write_bundle_atomic(output: Path, file_payloads: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        for name, payload in file_payloads.items():
            _write_new_file(temporary / name, payload)
        _write_new_file(temporary / "manifest.json", manifest)
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _write_json_idempotent(target: Path, payload: Mapping[str, Any], *, conflict_code: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _load_json(target) == payload:
            return "IDEMPOTENT"
        existing = _load_json(target)
        source_material = {
            key: existing.get(key)
            for key in (
                "candidate",
                "validation",
                "market_snapshot",
                "review_artifact",
                "confirmation_intent",
            )
        }
        existing_binding = str(existing.get("source_binding_hash", ""))
        if (
            existing_binding == payload.get("source_binding_hash")
            and hmac.compare_digest(existing_binding, _digest(source_material))
        ):
            return "IDEMPOTENT"
        raise PendingArtifactExportError(conflict_code)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        _write_new_file(temporary, payload)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return "CREATED"


def _write_new_file(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_FILE_BYTES:
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_MISSING_OR_INVALID")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_JSON_INVALID")
    return value


def _protected_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _protected_path(value: str | Path, root: Path, *, must_exist: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PendingArtifactExportError("OUTPUT_OUTSIDE_PROTECTED_ROOT") from exc
    if must_exist and not path.exists():
        raise PendingArtifactExportError("PROTECTED_ARTIFACT_MISSING_OR_INVALID")
    return path


def _relative_path(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root)).replace("\\", "/")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _redact(value: str) -> str:
    text = str(value)
    return f"{text[:12]}..." if text else ""


def _first_blocker(values: Any, fallback: str) -> str:
    return str(next(iter(values), fallback))


def _pending_family(order_type: str) -> str:
    if order_type.endswith("STOP_LIMIT"):
        return "STOP_LIMIT"
    if order_type.endswith("LIMIT"):
        return "LIMIT"
    if order_type.endswith("STOP"):
        return "STOP"
    return "UNKNOWN"


def _utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(timezone.utc)
    if selected.tzinfo is None:
        raise PendingArtifactExportError("TIMEZONE_REQUIRED")
    return selected.astimezone(timezone.utc)