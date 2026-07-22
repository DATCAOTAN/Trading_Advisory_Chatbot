from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, TypeVar

from src.services.trading.execution.live_parameter_value_proposal.models import (
    ControlledLiveParameterValueProposal,
)
from src.services.trading.execution.live_value_approval_lock.models import (
    ApprovedSemanticExecutionParameters,
    HumanValueApprovalConfirmation,
    HumanValueApprovalLock,
)
from src.services.trading.execution.live_value_approval_lock.policy import HumanValueApprovalLockConfig
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import MT5PreSubmitGateReport
from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationReport,
    REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES,
)


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = 1_000_000
_SYNTHETIC_MODES = {"SYNTHETIC", "TEST_ONLY", "FIXTURE_ONLY", "SCHEMA_ONLY"}
EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE = "EXPORT PROTECTED MT5 REQUEST WITHOUT SUBMISSION"
_UNSAFE_TRUE_FLAGS = (
    "live_execution_allowed",
    "order_send_allowed",
    "execution_allowed",
    "executable",
    "order_sent",
    "real_mt5_payload_created",
    "broker_submittable_request_dict_created",
    "mt5_constants_used",
    "broker_submission_created",
    "executable_order_created",
    "raw_values_stored",
    "raw_value_stored",
    "real_mt5_payload_value_created",
    "broker_submittable_request_field_created",
    "mt5_constant_used",
    "executable_order_value",
    "broker_submission_value",
    "executable_value",
    "mt5_payload_value",
    "order_value",
)


class ProtectedRequestExportError(ValueError):
    pass


@dataclass(frozen=True)
class ProtectedRequestExportResult:
    request_reference_redacted: str
    semantic_hash_prefix: str
    account_fingerprint_redacted: str
    output_path: str
    validation_status: str = "VALID"


_Model = TypeVar("_Model")


def export_protected_request(
    *,
    proposal_artifact: str | Path,
    approval_artifact: str | Path,
    lock_artifact: str | Path,
    final_validation_artifact: str | Path,
    final_validation_report_artifact: str | Path,
    pre_submit_artifact: str | Path,
    account_fingerprint_artifact: str | Path,
    account_fingerprint_submit_artifact: str | Path,
    human_confirmation_artifact: str | Path,
    output: str | Path,
    expected_confirmation_phrase: str,
    max_age_seconds: int = 300,
    current_time: datetime | None = None,
) -> ProtectedRequestExportResult:
    now = current_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ProtectedRequestExportError("current time must include timezone information")
    if max_age_seconds <= 0:
        raise ProtectedRequestExportError("max artifact age must be positive")

    proposal_payload = _load_json_mapping(proposal_artifact)
    approval_payload = _load_json_mapping(approval_artifact)
    lock_payload = _load_json_mapping(lock_artifact)
    final_payload = _load_json_mapping(final_validation_artifact)
    final_report_payload = _load_json_mapping(final_validation_report_artifact)
    pre_submit_payload = _load_json_mapping(pre_submit_artifact)
    account_payload = _load_json_mapping(account_fingerprint_artifact)
    account_submit_payload = _load_json_mapping(account_fingerprint_submit_artifact)
    confirmation_payload = _load_json_mapping(human_confirmation_artifact)

    for payload in (
        proposal_payload,
        approval_payload,
        lock_payload,
        final_payload,
        final_report_payload,
        pre_submit_payload,
    ):
        _reject_synthetic_artifact(payload)

    proposal = _load_model(ControlledLiveParameterValueProposal, proposal_payload, omit={"value_slots"})
    approval = _load_model(HumanValueApprovalConfirmation, approval_payload)
    protected_parameters_payload = lock_payload.get("approved_semantic_parameters")
    if not isinstance(protected_parameters_payload, Mapping):
        raise ProtectedRequestExportError("approval lock is schema-only or lacks protected semantic values")
    try:
        protected_parameters = ApprovedSemanticExecutionParameters.from_protected_dict(
            protected_parameters_payload
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtectedRequestExportError("approved semantic values failed integrity validation") from exc
    approval_lock = _load_model(
        HumanValueApprovalLock,
        lock_payload,
        omit={"approved_semantic_parameters", "slot_locks"},
        overrides={"approved_semantic_parameters": protected_parameters},
    )
    final_validation = _load_model(
        MT5RequestDictFinalValidationBoundary,
        final_payload,
        omit={"validated_fields"},
    )
    final_report = _load_model(
        MT5RequestDictFinalValidationReport,
        final_report_payload,
        ignore={"concrete_value_created"},
    )
    pre_submit_report = _load_model(MT5PreSubmitGateReport, pre_submit_payload)

    _validate_freshness(proposal.created_at, proposal.expires_at, now, max_age_seconds, "proposal")
    _validate_freshness(approval.created_at, approval.expires_at, now, max_age_seconds, "approval")
    _validate_freshness(
        approval_lock.created_at, approval_lock.expires_at, now, max_age_seconds, "approval lock"
    )
    _validate_freshness(
        final_validation.created_at,
        final_validation.expires_at,
        now,
        max_age_seconds,
        "final validation",
    )
    _validate_recent(final_report.created_at, now, max_age_seconds, "final validation report")
    _validate_recent(pre_submit_report.created_at, now, max_age_seconds, "pre-submit report")

    semantic_hash = protected_parameters.canonical_values_hash
    if not proposal.human_value_approval_allowed or proposal.blockers:
        raise ProtectedRequestExportError("proposal is not approved for human value review")
    if not proposal.source_refs or not proposal.idempotency_key or not proposal.artifact_hash:
        raise ProtectedRequestExportError("proposal references are incomplete")
    expected_approval_phrase = HumanValueApprovalLockConfig.from_config().expected_phrase
    if (
        approval.phrase_valid is not True
        or approval.blockers
        or not hmac.compare_digest(approval.phrase, expected_approval_phrase)
        or not hmac.compare_digest(approval.expected_phrase, expected_approval_phrase)
    ):
        raise ProtectedRequestExportError("human value approval is invalid")
    if approval.action != "APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY":
        raise ProtectedRequestExportError("human value approval action is not approved")
    if approval.review_state != "HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY":
        raise ProtectedRequestExportError("human value approval review state is not approved")
    if not approval.source_refs:
        raise ProtectedRequestExportError("approval references are incomplete")
    if approval.approved_semantic_values_hash != semantic_hash:
        raise ProtectedRequestExportError("approval semantic hash mismatch")
    if approval_lock.status != "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION":
        raise ProtectedRequestExportError("approval lock is not locked")
    if approval_lock.confirmation_phrase_valid is not True or approval_lock.blockers:
        raise ProtectedRequestExportError("approval lock confirmation is invalid")
    if approval_lock.source_value_proposal_id != proposal.proposal_id:
        raise ProtectedRequestExportError("proposal and approval lock references do not match")
    if approval_lock.confirmation_id != approval.confirmation_id:
        raise ProtectedRequestExportError("approval and lock references do not match")
    if not approval_lock.source_refs or not approval_lock.idempotency_key:
        raise ProtectedRequestExportError("approval lock references are incomplete")
    if approval_lock.artifact_hash != semantic_hash:
        raise ProtectedRequestExportError("approval lock artifact hash mismatch")
    if not approval_lock.approved_semantic_integrity_valid():
        raise ProtectedRequestExportError("approval lock semantic integrity failed")
    if protected_parameters.approved_at != approval.created_at:
        raise ProtectedRequestExportError("approval timestamp mismatch")
    if protected_parameters.locked_at != approval_lock.created_at:
        raise ProtectedRequestExportError("lock timestamp mismatch")

    _validate_final_validation(final_validation, final_report, final_payload, semantic_hash)
    _validate_pre_submit(pre_submit_report, final_validation, final_report)
    for label, payload in (
        ("proposal", proposal_payload),
        ("approval lock", lock_payload),
        ("final validation", final_payload),
        ("final validation report", final_report_payload),
        ("pre-submit report", pre_submit_payload),
    ):
        _reject_unsafe_flags(payload, label)

    fingerprint = _validate_account_artifact(account_payload, now, max_age_seconds, "account fingerprint")
    submit_fingerprint = _validate_account_artifact(
        account_submit_payload, now, max_age_seconds, "submit account fingerprint"
    )
    if not hmac.compare_digest(fingerprint, submit_fingerprint):
        raise ProtectedRequestExportError("account fingerprint mismatch")
    phrase = _validate_export_confirmation(
        confirmation_payload,
        fingerprint,
        expected_confirmation_phrase,
        now,
        max_age_seconds,
        proposal_reference=proposal.proposal_id,
        approval_lock_reference=approval_lock.approval_lock_id,
        final_validation_reference=final_validation.final_validation_id,
        semantic_hash=semantic_hash,
    )

    try:
        request = MT5ControlledExecutionRequest.from_artifacts(
            approval_lock,
            final_validation,
            final_report,
            pre_submit_report,
            expected_account_context_fingerprint=fingerprint,
            human_confirmation_phrase=phrase,
            execution_permission_requested=False,
        )
    except ValueError as exc:
        raise ProtectedRequestExportError("controlled request artifact validation failed") from exc

    protected_request = request.as_protected_dict()
    _write_protected_json(output, protected_request)
    request_digest = hashlib.sha256(
        json.dumps(protected_request, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return ProtectedRequestExportResult(
        request_reference_redacted=f"{request_digest[:12]}...",
        semantic_hash_prefix=semantic_hash[:12],
        account_fingerprint_redacted=f"{fingerprint[:12]}...",
        output_path=str(Path(output).resolve()),
    )


def _load_json_mapping(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_file() or path.is_symlink():
        raise ProtectedRequestExportError("required artifact is missing or not a regular file")
    if path.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise ProtectedRequestExportError("artifact exceeds the protected export size limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtectedRequestExportError("artifact is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise ProtectedRequestExportError("artifact JSON must be an object")
    return payload


def _load_model(
    model_type: type[_Model],
    payload: Mapping[str, Any],
    *,
    omit: set[str] | None = None,
    ignore: set[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> _Model:
    omit = omit or set()
    ignore = ignore or set()
    overrides = overrides or {}
    model_fields = {item.name for item in fields(model_type)}
    unknown = set(payload) - model_fields - ignore
    if unknown:
        raise ProtectedRequestExportError("artifact contains fields outside its model contract")
    values = {name: value for name, value in payload.items() if name in model_fields and name not in omit}
    values.update(overrides)
    try:
        return model_type(**values)
    except (TypeError, ValueError) as exc:
        raise ProtectedRequestExportError("artifact does not match its model contract") from exc


def _validate_final_validation(boundary, report, payload, semantic_hash: str) -> None:
    required = set(REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES)
    validated = set(boundary.validated_field_categories)
    fields_payload = payload.get("validated_fields")
    if not isinstance(fields_payload, list) or len(fields_payload) != len(required):
        raise ProtectedRequestExportError("required final validation fields are missing")
    for item in fields_payload:
        if not isinstance(item, Mapping):
            raise ProtectedRequestExportError("final validation field is invalid")
        if item.get("field_category") not in required or item.get("validation_passed") is not True:
            raise ProtectedRequestExportError("final validation field did not pass")
        if item.get("schema_only") is not True or item.get("value_redacted") is not True:
            raise ProtectedRequestExportError("final validation field contract is unsafe")
        _reject_unsafe_flags(item, "final validation field")
        if item.get("concrete_value_created") is True or item.get(
            "broker_submittable_request_field_created"
        ) is True:
            raise ProtectedRequestExportError("final validation field contains a concrete value")
    if validated != required or boundary.missing_field_categories or boundary.invalid_field_categories:
        raise ProtectedRequestExportError("final validation field categories are incomplete")
    if (
        boundary.status != "FINAL_VALIDATION_PASSED"
        or boundary.bridge_write_skeleton_check_allowed is not True
        or boundary.approved_semantic_values_required is not True
        or boundary.approved_semantic_values_present is not True
        or boundary.approved_semantic_values_verified is not True
        or boundary.approved_semantic_values_hash != semantic_hash
        or boundary.artifact_hash != semantic_hash
        or not boundary.source_dry_run_request_dict_id
        or not boundary.source_dry_run_request_dict_validation_report_id
        or boundary.blockers
        or not boundary.source_refs
        or not boundary.idempotency_key
    ):
        raise ProtectedRequestExportError("final validation does not verify approved semantic values")
    if (
        report.valid is not True
        or report.source_final_validation_id != boundary.final_validation_id
        or report.bridge_write_skeleton_check_allowed is not True
        or report.validated_fields_count != len(required)
        or report.missing_fields_count != 0
        or report.invalid_fields_count != 0
        or report.blockers
        or not report.source_refs
    ):
        raise ProtectedRequestExportError("final validation report is invalid")


def _validate_pre_submit(report, final_validation, final_report) -> None:
    if (
        report.valid is not True
        or report.status not in {"PASSED_DISABLED_PRE_SUBMIT_CHECK", "READY_FOR_CONTROLLED_DEMO_INTEGRATION"}
        or report.controlled_demo_integration_workflow_allowed is not True
        or report.live_submission_allowed is not False
        or report.source_final_validation_id != final_validation.final_validation_id
        or report.source_final_validation_report_id != final_report.validation_report_id
        or report.bridge_write_skeleton_reachable is not True
        or report.bridge_write_skeleton_status != "BLOCKED"
        or report.kill_switch_engaged is not True
        or report.idempotency_status != "CHECK_REGISTERED"
        or not report.source_refs
    ):
        raise ProtectedRequestExportError("pre-submit artifact is not valid for protected export")


def _validate_account_artifact(payload, now, max_age_seconds: int, label: str) -> str:
    if payload.get("status") != "OK" or payload.get("redacted") is not True:
        raise ProtectedRequestExportError(f"{label} is not a redacted successful capture")
    fingerprint = str(payload.get("account_context_fingerprint", "")).strip().lower()
    if not _HASH_PATTERN.fullmatch(fingerprint):
        raise ProtectedRequestExportError(f"{label} is invalid")
    captured_at = payload.get("captured_at") or payload.get("created_at")
    _validate_recent(captured_at, now, max_age_seconds, label)
    forbidden = {"login", "password", "auth_token", "account_id", "account_login"}
    if forbidden.intersection(payload):
        raise ProtectedRequestExportError(f"{label} contains forbidden account data")
    return fingerprint


def _validate_export_confirmation(
    payload,
    fingerprint,
    expected_phrase,
    now,
    max_age_seconds,
    *,
    proposal_reference,
    approval_lock_reference,
    final_validation_reference,
    semantic_hash,
) -> str:
    allowed = {
        "created_at",
        "expires_at",
        "phrase",
        "phrase_valid",
        "expected_account_context_fingerprint",
        "metadata_redacted",
        "proposal_reference",
        "approval_lock_reference",
        "final_validation_reference",
        "approved_semantic_values_hash",
        "purpose",
        "non_executable",
    }
    if set(payload) != allowed:
        raise ProtectedRequestExportError("export confirmation fields do not match the contract")
    _validate_freshness(
        payload.get("created_at"),
        payload.get("expires_at"),
        now,
        max_age_seconds,
        "export confirmation",
    )
    phrase = str(payload.get("phrase", "")).strip()
    if (
        payload.get("phrase_valid") is not True
        or payload.get("purpose") != "export_only"
        or payload.get("non_executable") is not True
        or payload.get("metadata_redacted") is not True
        or not hmac.compare_digest(phrase, str(expected_phrase or ""))
        or not hmac.compare_digest(
            str(payload.get("expected_account_context_fingerprint", "")).lower(), fingerprint
        )
        or not hmac.compare_digest(str(payload.get("proposal_reference", "")), proposal_reference)
        or not hmac.compare_digest(
            str(payload.get("approval_lock_reference", "")), approval_lock_reference
        )
        or not hmac.compare_digest(
            str(payload.get("final_validation_reference", "")), final_validation_reference
        )
        or not hmac.compare_digest(
            str(payload.get("approved_semantic_values_hash", "")), semantic_hash
        )
    ):
        raise ProtectedRequestExportError("export confirmation is invalid")
    return phrase


def _validate_freshness(created_at, expires_at, now, max_age_seconds: int, label: str) -> None:
    _validate_recent(created_at, now, max_age_seconds, label)
    expiry = _parse_timestamp(expires_at, f"{label} expiry")
    if now >= expiry:
        raise ProtectedRequestExportError(f"{label} is stale")


def _validate_recent(value, now, max_age_seconds: int, label: str) -> None:
    created = _parse_timestamp(value, f"{label} timestamp")
    if created > now + timedelta(seconds=5) or now - created > timedelta(seconds=max_age_seconds):
        raise ProtectedRequestExportError(f"{label} is stale")


def _parse_timestamp(value, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtectedRequestExportError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ProtectedRequestExportError(f"{label} must include timezone information")
    return parsed.astimezone(timezone.utc)

def _reject_unsafe_flags(payload: Mapping[str, Any], label: str) -> None:
    if any(payload.get(name) is True for name in _UNSAFE_TRUE_FLAGS):
        raise ProtectedRequestExportError(f"{label} contains an enabled execution flag")
    if payload.get("hard_live_block_required") is False:
        raise ProtectedRequestExportError(f"{label} disables the hard live block")


def _reject_synthetic_artifact(payload: Mapping[str, Any]) -> None:
    if payload.get("synthetic") is True or payload.get("test_only") is True:
        raise ProtectedRequestExportError("synthetic artifacts are not allowed")
    if str(payload.get("mode", "")).upper() in _SYNTHETIC_MODES:
        raise ProtectedRequestExportError("synthetic or schema-only artifacts are not allowed")


def _write_protected_json(path_value: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path_value).expanduser()
    if not path.parent.is_dir() or path.exists() or path.is_symlink():
        raise ProtectedRequestExportError("output path must be new and its parent must exist")
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProtectedRequestExportError("protected request could not be written") from exc
