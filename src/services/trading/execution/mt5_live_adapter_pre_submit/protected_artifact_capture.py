from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.config import Config
from src.services.trading.execution import (
    ControlledLiveParameterValueProposalService,
    DryRunConfirmationService,
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
    EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE,
    HumanReviewedLiveParameterDraftService,
    HumanValueApprovalLockService,
    LiveExecutionPreflightService,
    LiveOrderContractFinalReviewService,
    LiveOrderContractParameterizationService,
    LiveOrderContractSkeletonService,
    LiveOrderIntentService,
    LiveOrderParameterPolicyService,
    LiveOrderParameterSourceBoundaryService,
    LivePermissionGateService,
    LivePermissionPolicy,
    MT5ExecutionSkeletonService,
    MT5OrderRequestDryRunPayloadValidationService,
    MT5RequestDraftFinalApprovalService,
    MT5RequestDraftService,
    PreMT5OrderRequestMappingService,
    SimulatedExecutionService,
)
from src.services.trading.execution.live_design import LiveExecutionDesignSpecService
from src.services.trading.execution.live_value_approval_lock.confirmation import (
    HumanValueApprovalConfirmationService,
)
from src.services.trading.execution.live_value_approval_lock.models import (
    APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES,
    ApprovedSemanticExecutionParameters,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_export import (
    EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE,
    ProtectedRequestExportError,
    export_protected_request,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.service import (
    MT5LiveAdapterPreSubmitService,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.builder import (
    MT5RequestDictDryRunBuilder,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.gate import (
    MT5RequestDictDryRunBuilderGate,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.policy import (
    MT5RequestDictDryRunBuilderConfig,
)
from src.services.trading.execution.mt5_request_dict_final_validation.builder import (
    MT5RequestDictFinalValidationBuilder,
)
from src.services.trading.execution.mt5_request_dict_final_validation.gate import (
    MT5RequestDictFinalValidationGate,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import (
    MT5RequestDictFinalValidationConfig,
)
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder
from src.services.trading.market.live_feature_service import LiveFeatureService
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider
from src.services.trading.market.regime_detector import MarketRegimeDetector
from src.services.trading.proposal import (
    HumanProposalConfirmationService,
    ProposalBoundaryPolicy,
    ProposalDraftService,
)
from src.services.trading.reasoning import MethodSelectorService
from src.services.trading.review import HumanReviewArtifactBuilder, HumanReviewFormatter
from src.services.trading.scoring import SignalScoringEngine
from src.services.trading.calendar import CalendarContextBuilder, ForexFactoryCalendarProvider
from src.services.trading.decision import TradeDecisionPolicyEngine


PROTECTED_ARTIFACT_FILENAMES = {
    "proposal_artifact": "proposal.json",
    "approval_artifact": "approval-confirmation.json",
    "lock_artifact": "approval-lock.json",
    "final_validation_artifact": "final-validation.json",
    "final_validation_report_artifact": "final-validation-report.json",
    "pre_submit_artifact": "pre-submit-report.json",
    "account_fingerprint_artifact": "account-context-first.json",
    "account_fingerprint_submit_artifact": "account-context-second.json",
    "human_confirmation_artifact": "human-confirmation.json",
}
MANIFEST_FILENAME = "manifest.json"
_MAX_OPERATOR_INPUT_BYTES = 64_000
_SCHEMA_ONLY_VALUE_MARKERS = {
    "REFERENCE_ONLY",
    "VALUE_NOT_CREATED",
    "VALUE_REDACTED",
    "SCHEMA_ONLY",
    "REDACTED",
}


class ProtectedArtifactCaptureError(ValueError):
    pass


@dataclass(frozen=True)
class ProtectedArtifactCaptureResult:
    capture_reference_redacted: str
    semantic_hash_prefix: str
    account_fingerprint_redacted: str
    artifact_count: int
    bundle_path: str
    status: str = "PROTECTED_ARTIFACT_BUNDLE_COMPLETE"


@dataclass(frozen=True)
class ProtectedAccountContextCapture:
    status: str
    account_context_fingerprint: str
    account_id_hash: str
    server_redacted: str
    currency: object
    trade_mode: object
    redacted: bool
    captured_at: str
    account_environment: str = "UNKNOWN"

    @classmethod
    def from_read_only_payload(
        cls, payload: Mapping[str, Any], captured_at: datetime
    ) -> "ProtectedAccountContextCapture":
        fingerprint = str(payload.get("account_context_fingerprint", "")).strip().lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ProtectedArtifactCaptureError("account context fingerprint is invalid")
        forbidden = {"login", "password", "auth_token", "account_id", "account_login"}
        if forbidden.intersection(payload):
            raise ProtectedArtifactCaptureError("account context contains forbidden account data")
        return cls(
            status="OK",
            account_context_fingerprint=fingerprint,
            account_id_hash=str(payload.get("account_id_hash", "")),
            server_redacted=str(payload.get("server_redacted", "")),
            currency=payload.get("currency"),
            trade_mode=payload.get("trade_mode"),
            redacted=True,
            captured_at=captured_at.isoformat(),
            account_environment=str(
                payload.get("account_environment", "UNKNOWN")
            ).upper(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "account_context_fingerprint": self.account_context_fingerprint,
            "account_id_hash": self.account_id_hash,
            "server_redacted": self.server_redacted,
            "currency": self.currency,
            "trade_mode": self.trade_mode,
            "redacted": self.redacted,
            "captured_at": self.captured_at,
            "account_environment": self.account_environment,
        }


@dataclass(frozen=True)
class ProtectedExportConfirmation:
    created_at: str
    expires_at: str
    phrase: str = field(repr=False)
    phrase_valid: bool = True
    expected_account_context_fingerprint: str = ""
    metadata_redacted: bool = True
    proposal_reference: str = ""
    approval_lock_reference: str = ""
    final_validation_reference: str = ""
    approved_semantic_values_hash: str = ""
    purpose: str = "export_only"
    non_executable: bool = True

    @classmethod
    def confirm(
        cls,
        phrase: str,
        fingerprint: str,
        lock,
        proposal,
        final_validation,
        created_at: datetime,
        ttl_seconds: int,
    ) -> "ProtectedExportConfirmation":
        expected = EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE
        if not hmac.compare_digest(str(phrase or "").strip(), expected):
            raise ProtectedArtifactCaptureError("export confirmation is invalid")
        if not lock.approved_semantic_integrity_valid() or final_validation.artifact_hash != lock.artifact_hash:
            raise ProtectedArtifactCaptureError("export confirmation references are inconsistent")
        references = (
            str(proposal.proposal_id),
            str(lock.approval_lock_id),
            str(final_validation.final_validation_id),
        )
        if not all(references):
            raise ProtectedArtifactCaptureError("export confirmation references are missing")
        return cls(
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(seconds=ttl_seconds)).isoformat(),
            phrase=expected,
            expected_account_context_fingerprint=fingerprint,
            proposal_reference=references[0],
            approval_lock_reference=references[1],
            final_validation_reference=references[2],
            approved_semantic_values_hash=lock.approved_semantic_values_hash,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "phrase": self.phrase,
            "phrase_valid": self.phrase_valid,
            "expected_account_context_fingerprint": self.expected_account_context_fingerprint,
            "metadata_redacted": self.metadata_redacted,
            "proposal_reference": self.proposal_reference,
            "approval_lock_reference": self.approval_lock_reference,
            "final_validation_reference": self.final_validation_reference,
            "approved_semantic_values_hash": self.approved_semantic_values_hash,
            "purpose": self.purpose,
            "non_executable": self.non_executable,
        }


@dataclass(frozen=True)
class ProtectedCaptureUpstreamArtifacts:
    parameter_draft: object
    parameter_draft_validation: object
    parameter_source_boundary: object
    parameter_source_validation: object
    parameter_policy_spec: object
    parameter_policy_validation: object
    contract_skeleton: object
    contract_skeleton_validation: object
    live_order_intent: object
    live_order_intent_validation: object
    permission_decision: object
    preflight_report: object
    proposal_draft: object
    simulated_contract: object
    simulated_receipt: object | None = None


class OperatorProtectedArtifactCaptureService:
    def __init__(
        self,
        *,
        upstream_builder: Callable[[str, str], ProtectedCaptureUpstreamArtifacts] | None = None,
        adapter_factory: Callable[[str], MT5LiveAdapterDisabled] | None = None,
        pre_submit_service_factory: Callable[[str], MT5LiveAdapterPreSubmitService] | None = None,
    ):
        self.upstream_builder = upstream_builder or build_live_capture_upstream
        self.adapter_factory = adapter_factory or _default_adapter
        self.pre_submit_service_factory = pre_submit_service_factory or _default_pre_submit_service

    def capture(
        self,
        *,
        semantic_input: str | Path,
        output_dir: str | Path,
        approval_confirmation_phrase: str,
        export_confirmation_phrase: str,
        bridge_url: str | None = None,
        mode: str = "REVIEW_ONLY",
        max_age_seconds: int = 300,
        current_time: datetime | None = None,
    ) -> ProtectedArtifactCaptureResult:
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ProtectedArtifactCaptureError("current time must include timezone information")
        if max_age_seconds <= 0:
            raise ProtectedArtifactCaptureError("max artifact age must be positive")
        semantics = load_approved_semantic_input(semantic_input, now)
        expected_approval = EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE
        expected_export = EXPECTED_PROTECTED_REQUEST_EXPORT_PHRASE
        if not hmac.compare_digest(str(approval_confirmation_phrase or "").strip(), expected_approval):
            raise ProtectedArtifactCaptureError("approval confirmation is invalid")
        if not hmac.compare_digest(str(export_confirmation_phrase or "").strip(), expected_export):
            raise ProtectedArtifactCaptureError("export confirmation is invalid")

        resolved_bridge_url = bridge_url or Config.MT5_BRIDGE_URL
        if "host.docker.internal" in resolved_bridge_url:
            resolved_bridge_url = "http://127.0.0.1:8765"

        bundle = _create_bundle_directory(output_dir)
        try:
            with isolated_capture_journals():
                upstream = self.upstream_builder(resolved_bridge_url, mode)
                artifacts = self._build_artifacts(
                    upstream=upstream,
                    semantics=semantics,
                    approval_phrase=expected_approval,
                    export_phrase=expected_export,
                    bridge_url=resolved_bridge_url,
                    current_time=now,
                    max_age_seconds=max_age_seconds,
                )
            paths = _persist_bundle(bundle, artifacts)
            compatibility_time = max(now, datetime.now(timezone.utc))
            _verify_export_compatibility(
                paths,
                bundle,
                expected_export,
                max_age_seconds=max_age_seconds,
                current_time=compatibility_time,
            )
            manifest = _build_manifest(artifacts, paths)
            _write_protected_json(bundle / MANIFEST_FILENAME, manifest)
            verified_paths = verify_protected_artifact_bundle(bundle)
        except Exception:
            _remove_incomplete_bundle(bundle)
            raise

        semantic_hash = str(artifacts["lock_artifact"]["approved_semantic_values_hash"])
        fingerprint = str(artifacts["account_fingerprint_artifact"]["account_context_fingerprint"])
        capture_digest = hashlib.sha256(str(bundle.resolve()).encode("utf-8")).hexdigest()
        return ProtectedArtifactCaptureResult(
            capture_reference_redacted=f"{capture_digest[:12]}...",
            semantic_hash_prefix=semantic_hash[:12],
            account_fingerprint_redacted=f"{fingerprint[:12]}...",
            artifact_count=len(verified_paths),
            bundle_path=str(bundle.resolve()),
        )

    def _build_artifacts(
        self,
        *,
        upstream: ProtectedCaptureUpstreamArtifacts,
        semantics: Mapping[str, Any],
        approval_phrase: str,
        export_phrase: str,
        bridge_url: str,
        current_time: datetime,
        max_age_seconds: int,
    ) -> dict[str, dict[str, Any]]:
        proposal_result = ControlledLiveParameterValueProposalService().run(
            upstream.parameter_draft,
            upstream.parameter_draft_validation,
            upstream.parameter_source_boundary,
            upstream.parameter_source_validation,
            upstream.parameter_policy_spec,
            upstream.parameter_policy_validation,
            upstream.contract_skeleton,
            upstream.contract_skeleton_validation,
            upstream.live_order_intent,
            upstream.live_order_intent_validation,
            upstream.permission_decision,
            upstream.preflight_report,
            upstream.proposal_draft,
            upstream.simulated_contract,
            simulated_receipt=upstream.simulated_receipt,
            current_time=current_time,
        )
        proposal = proposal_result.proposal
        if not proposal_result.validation_report.valid or not proposal.human_value_approval_allowed:
            raise ProtectedArtifactCaptureError("value proposal is not valid for protected approval")

        lock_result = HumanValueApprovalLockService().run(
            proposal,
            proposal_result.validation_report,
            upstream.parameter_draft,
            upstream.parameter_draft_validation,
            upstream.parameter_source_boundary,
            upstream.parameter_source_validation,
            upstream.parameter_policy_spec,
            upstream.parameter_policy_validation,
            upstream.contract_skeleton,
            upstream.contract_skeleton_validation,
            upstream.live_order_intent,
            upstream.live_order_intent_validation,
            upstream.permission_decision,
            upstream.preflight_report,
            upstream.proposal_draft,
            upstream.simulated_contract,
            simulated_receipt=upstream.simulated_receipt,
            confirmation_phrase=approval_phrase,
            current_time=current_time,
            approved_semantic_values=semantics,
        )
        approval_lock = lock_result.approval_lock
        if not lock_result.validation_report.valid or not approval_lock.approved_semantic_integrity_valid():
            raise ProtectedArtifactCaptureError("protected approval lock is invalid")
        approval = HumanValueApprovalConfirmationService().confirm(
            approval_phrase,
            source_refs=list(approval_lock.source_refs),
            current_time=current_time,
        )
        approval.approved_semantic_values_hash = approval_lock.approved_semantic_values_hash
        if approval.confirmation_id != approval_lock.confirmation_id:
            raise ProtectedArtifactCaptureError("approval confirmation and lock do not match")

        downstream = _build_post_lock_chain(upstream, proposal_result, lock_result)
        final_validation = downstream["final_validation"]
        final_report = downstream["final_validation_report"]
        semantic_hash = approval_lock.approved_semantic_values_hash
        if (
            not final_report.valid
            or not final_validation.approved_semantic_values_verified
            or final_validation.artifact_hash != semantic_hash
        ):
            raise ProtectedArtifactCaptureError("final validation did not preserve semantic integrity")

        pre_submit_service = self.pre_submit_service_factory(bridge_url)
        pre_submit_result = pre_submit_service.run(final_validation, final_report)
        pre_submit = pre_submit_result.report
        if not pre_submit.valid or not pre_submit.controlled_demo_integration_workflow_allowed:
            raise ProtectedArtifactCaptureError("disabled pre-submit validation failed")
        _require_blocked_execution_state(pre_submit)

        adapter = self.adapter_factory(bridge_url)
        first = _capture_account_context(adapter, datetime.now(timezone.utc))
        second = _capture_account_context(adapter, datetime.now(timezone.utc))
        first_fingerprint = first.account_context_fingerprint
        if not hmac.compare_digest(first_fingerprint, second.account_context_fingerprint):
            raise ProtectedArtifactCaptureError("account context changed between captures")
        _validate_capture_freshness(first, current_time, max_age_seconds)
        _validate_capture_freshness(second, current_time, max_age_seconds)
        confirmation = ProtectedExportConfirmation.confirm(
            export_phrase,
            first_fingerprint,
            approval_lock,
            proposal,
            final_validation,
            datetime.now(timezone.utc),
            max_age_seconds,
        )

        return {
            "proposal_artifact": proposal.as_dict(),
            "approval_artifact": approval.as_dict(),
            "lock_artifact": approval_lock.as_protected_dict(),
            "final_validation_artifact": final_validation.as_dict(),
            "final_validation_report_artifact": final_report.as_dict(),
            "pre_submit_artifact": pre_submit.as_dict(),
            "account_fingerprint_artifact": first.as_dict(),
            "account_fingerprint_submit_artifact": second.as_dict(),
            "human_confirmation_artifact": confirmation.as_dict(),
        }


def load_approved_semantic_input(path_value: str | Path, current_time: datetime) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_OPERATOR_INPUT_BYTES:
        raise ProtectedArtifactCaptureError("semantic input is missing or unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtectedArtifactCaptureError("semantic input is not readable JSON") from exc
    if not isinstance(payload, dict) or set(payload) != set(APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES):
        raise ProtectedArtifactCaptureError("semantic input fields do not match the approved allow-list")
    if any(str(value).strip().upper() in _SCHEMA_ONLY_VALUE_MARKERS for value in payload.values()):
        raise ProtectedArtifactCaptureError("schema-only semantic values are not allowed")
    try:
        validated = ApprovedSemanticExecutionParameters.from_mapping(
            payload,
            approval_artifact_ref="capture-input-validation",
            lock_artifact_ref="capture-input-validation",
            source_artifact_ref="capture-input-validation",
            approved_at=current_time.isoformat(),
            locked_at=current_time.isoformat(),
        )
    except (TypeError, ValueError) as exc:
        raise ProtectedArtifactCaptureError("semantic input values are invalid") from exc
    protected = validated.to_protected_dict()
    return {name: protected[name] for name in APPROVED_SEMANTIC_EXECUTION_FIELD_NAMES}


def verify_protected_artifact_bundle(bundle_dir: str | Path) -> dict[str, Path]:
    bundle = Path(bundle_dir).expanduser()
    manifest_path = bundle / MANIFEST_FILENAME
    if not bundle.is_dir() or bundle.is_symlink() or not manifest_path.is_file():
        raise ProtectedArtifactCaptureError("protected artifact bundle is incomplete")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtectedArtifactCaptureError("protected artifact manifest is invalid") from exc
    if manifest.get("status") != "COMPLETE" or manifest.get("artifact_count") != len(
        PROTECTED_ARTIFACT_FILENAMES
    ):
        raise ProtectedArtifactCaptureError("protected artifact manifest is incomplete")
    entries = manifest.get("artifacts")
    if not isinstance(entries, dict) or set(entries) != set(PROTECTED_ARTIFACT_FILENAMES):
        raise ProtectedArtifactCaptureError("protected artifact manifest entries are invalid")
    paths: dict[str, Path] = {}
    for key, filename in PROTECTED_ARTIFACT_FILENAMES.items():
        entry = entries.get(key)
        path = bundle / filename
        if not isinstance(entry, dict) or entry.get("filename") != filename or not path.is_file():
            raise ProtectedArtifactCaptureError("protected artifact bundle is incomplete")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not hmac.compare_digest(digest, str(entry.get("sha256", ""))):
            raise ProtectedArtifactCaptureError("protected artifact bundle integrity failed")
        paths[key] = path
    return paths


def build_live_capture_upstream(bridge_url: str, mode: str) -> ProtectedCaptureUpstreamArtifacts:
    symbol = Config.MARKET_DEFAULT_SYMBOL
    provider = MT5BridgeMarketDataProvider(bridge_url=bridge_url)
    feature = LiveFeatureService(bundle_builder=MarketSnapshotBundleBuilder(provider)).build_features(
        symbol, Config.MARKET_DEFAULT_TIMEFRAMES, Config.MARKET_DEFAULT_CANDLE_COUNT
    ).feature_snapshot
    calendar = CalendarContextBuilder(ForexFactoryCalendarProvider()).build(symbol=symbol)
    regime = MarketRegimeDetector().detect(feature, calendar)
    candidates = KnowledgeRouter().route("autonomous_live", symbol, feature, calendar, regime)
    context_pack = RuntimeContextPackBuilder().build(
        candidates, feature, calendar, regime, "autonomous_live", symbol, feature.broker_symbol
    )
    selection = MethodSelectorService().select(context_pack, mode="autonomous_live")
    score_report = SignalScoringEngine().score(
        feature, calendar, regime, context_pack, selection, mode="autonomous_live"
    )
    readiness = TradeDecisionPolicyEngine().decide(
        score_report, feature, calendar, regime, context_pack, selection, mode="autonomous_live"
    )
    review = HumanReviewArtifactBuilder().build(
        readiness, score_report, selection, context_pack, regime, calendar, feature
    )
    card = HumanReviewFormatter().to_card(review)
    dry_run = DryRunConfirmationService().run(review, card=card, mode=mode)
    proposal_policy = ProposalBoundaryPolicy.from_config()
    proposal_intent = HumanProposalConfirmationService(policy=proposal_policy).confirm_with_journal(
        review,
        dry_run.receipt,
        execution_journal_record=dry_run.journal_record,
        user_acknowledgement_text=proposal_policy.confirmation_phrase,
    )
    proposal_draft = ProposalDraftService().build(
        proposal_intent.intent,
        review,
        score_report,
        selection,
        context_pack,
        calendar_context=calendar,
        regime_snapshot=regime,
        feature_snapshot=feature,
    )
    simulated = SimulatedExecutionService().run(
        proposal_draft.draft,
        intent=proposal_intent.intent,
        dry_run_receipt=dry_run.receipt,
        execution_journal_record=dry_run.journal_record,
        proposal_draft_journal_record=proposal_draft.journal_record,
    )
    skeleton = MT5ExecutionSkeletonService().run(
        simulated.contract, simulated.receipt, simulated.journal_record
    )
    design = LiveExecutionDesignSpecService().build_and_record(
        skeleton.capability_report,
        skeleton.blocked_receipt,
        contract=simulated.contract,
        simulated_receipt=simulated.receipt,
        draft=proposal_draft.draft,
    )
    preflight = LiveExecutionPreflightService().run(
        design.report,
        skeleton.capability_report,
        skeleton.blocked_receipt,
        simulated_contract=simulated.contract,
        simulated_receipt=simulated.receipt,
        live_block_journal_record=skeleton.journal_record,
    )
    permission_policy = LivePermissionPolicy.from_config()
    permission = LivePermissionGateService(policy=permission_policy).run(
        preflight.report,
        design.report,
        skeleton.capability_report,
        skeleton.blocked_receipt,
        simulated_contract=simulated.contract,
        proposal_draft=proposal_draft.draft,
        user_acknowledgement_text=permission_policy.confirmation_phrase,
    )
    intent = LiveOrderIntentService().run(
        permission.intent,
        permission.decision,
        preflight.report,
        proposal_draft.draft,
        simulated.contract,
        simulated_receipt=simulated.receipt,
    )
    contract = LiveOrderContractSkeletonService().run(
        intent.intent,
        intent.validation_report,
        permission.decision,
        preflight.report,
        proposal_draft.draft,
        simulated.contract,
        simulated_receipt=simulated.receipt,
    )
    policy = LiveOrderParameterPolicyService().run(
        contract.skeleton,
        contract.validation_report,
        intent.intent,
        intent.validation_report,
        permission.decision,
        preflight.report,
        proposal_draft.draft,
        simulated.contract,
        simulated_receipt=simulated.receipt,
    )
    source = LiveOrderParameterSourceBoundaryService().run(
        policy.policy_spec,
        policy.validation_report,
        contract.skeleton,
        contract.validation_report,
        intent.intent,
        intent.validation_report,
        permission.decision,
        preflight.report,
        proposal_draft.draft,
        simulated.contract,
        simulated_receipt=simulated.receipt,
    )
    parameter_draft = HumanReviewedLiveParameterDraftService().run(
        source.boundary,
        source.validation_report,
        policy.policy_spec,
        policy.validation_report,
        contract.skeleton,
        contract.validation_report,
        intent.intent,
        intent.validation_report,
        permission.decision,
        preflight.report,
        proposal_draft.draft,
        simulated.contract,
        simulated_receipt=simulated.receipt,
    )
    return ProtectedCaptureUpstreamArtifacts(
        parameter_draft=parameter_draft.draft,
        parameter_draft_validation=parameter_draft.validation_report,
        parameter_source_boundary=source.boundary,
        parameter_source_validation=source.validation_report,
        parameter_policy_spec=policy.policy_spec,
        parameter_policy_validation=policy.validation_report,
        contract_skeleton=contract.skeleton,
        contract_skeleton_validation=contract.validation_report,
        live_order_intent=intent.intent,
        live_order_intent_validation=intent.validation_report,
        permission_decision=permission.decision,
        preflight_report=preflight.report,
        proposal_draft=proposal_draft.draft,
        simulated_contract=simulated.contract,
        simulated_receipt=simulated.receipt,
    )


def _build_post_lock_chain(upstream, proposal_result, lock_result) -> dict[str, object]:
    parameterization = LiveOrderContractParameterizationService().run(
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
    )
    final_review = LiveOrderContractFinalReviewService().run(
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
        confirmation_phrase=EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
    )
    mapping = PreMT5OrderRequestMappingService().run(
        final_review.final_review,
        final_review.validation_report,
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
    )
    dry_payload = MT5OrderRequestDryRunPayloadValidationService().run(
        mapping.mapping_boundary,
        mapping.validation_report,
        final_review.final_review,
        final_review.validation_report,
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
    )
    request_draft = MT5RequestDraftService().run(
        dry_payload.dry_run_validation,
        dry_payload.validation_report,
        mapping.mapping_boundary,
        mapping.validation_report,
        final_review.final_review,
        final_review.validation_report,
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
    )
    final_approval = MT5RequestDraftFinalApprovalService().run(
        request_draft.request_draft,
        request_draft.validation_report,
        dry_payload.dry_run_validation,
        dry_payload.validation_report,
        mapping.mapping_boundary,
        mapping.validation_report,
        final_review.final_review,
        final_review.validation_report,
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
        confirmation_phrase=EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE,
    )
    dry_config = MT5RequestDictDryRunBuilderConfig.from_config()
    dry_boundary = MT5RequestDictDryRunBuilder(dry_config).build(
        final_approval.final_approval,
        final_approval.validation_report,
        request_draft.request_draft,
        request_draft.validation_report,
        dry_payload.dry_run_validation,
        dry_payload.validation_report,
        mapping.mapping_boundary,
        mapping.validation_report,
        final_review.final_review,
        final_review.validation_report,
        parameterization.parameterization,
        parameterization.validation_report,
        lock_result.approval_lock,
        lock_result.validation_report,
        proposal_result.proposal,
        proposal_result.validation_report,
        upstream.parameter_draft,
        upstream.parameter_draft_validation,
        upstream.parameter_source_boundary,
        upstream.parameter_source_validation,
        upstream.parameter_policy_spec,
        upstream.parameter_policy_validation,
        upstream.contract_skeleton,
        upstream.contract_skeleton_validation,
        upstream.live_order_intent,
        upstream.live_order_intent_validation,
        upstream.permission_decision,
        upstream.preflight_report,
        upstream.proposal_draft,
        upstream.simulated_contract,
        simulated_receipt=upstream.simulated_receipt,
        require_approved_semantic_values=True,
    )
    dry_report = MT5RequestDictDryRunBuilderGate(dry_config).validate(dry_boundary)
    final_config = MT5RequestDictFinalValidationConfig.from_config()
    final_validation = MT5RequestDictFinalValidationBuilder(final_config).build(
        dry_boundary, dry_report
    )
    final_report = MT5RequestDictFinalValidationGate(final_config).validate(final_validation)
    return {"final_validation": final_validation, "final_validation_report": final_report}


def _default_adapter(bridge_url: str) -> MT5LiveAdapterDisabled:
    config = MT5LiveAdapterPreSubmitConfig.from_config()
    config.bridge_url = bridge_url
    return MT5LiveAdapterDisabled(config=config)


def _default_pre_submit_service(bridge_url: str) -> MT5LiveAdapterPreSubmitService:
    config = MT5LiveAdapterPreSubmitConfig.from_config()
    config.bridge_url = bridge_url
    return MT5LiveAdapterPreSubmitService(config=config, adapter=MT5LiveAdapterDisabled(config=config))


def _capture_account_context(
    adapter: MT5LiveAdapterDisabled, captured_at: datetime
) -> ProtectedAccountContextCapture:
    return ProtectedAccountContextCapture.from_read_only_payload(
        adapter.capture_account_context(), captured_at
    )


def _validate_capture_freshness(payload, current_time, max_age_seconds):
    captured = datetime.fromisoformat(str(payload.captured_at).replace("Z", "+00:00"))
    if captured.tzinfo is None or captured < current_time - timedelta(seconds=max_age_seconds):
        raise ProtectedArtifactCaptureError("account context capture is stale")
    if captured > datetime.now(timezone.utc) + timedelta(seconds=5):
        raise ProtectedArtifactCaptureError("account context capture timestamp is invalid")


def _create_bundle_directory(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    protected_root = Path("data/trading/protected_requests").resolve()
    try:
        path.relative_to(protected_root)
    except ValueError as exc:
        raise ProtectedArtifactCaptureError("output directory must be inside protected_requests") from exc
    if path == protected_root or path.exists() or path.is_symlink():
        raise ProtectedArtifactCaptureError("output directory must be a new unique directory")
    protected_root.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    except OSError as exc:
        raise ProtectedArtifactCaptureError("protected output directory could not be created") from exc
    return path


def _remove_incomplete_bundle(bundle: Path) -> None:
    try:
        for path in bundle.iterdir():
            if path.is_file() and not path.is_symlink():
                path.unlink()
        bundle.rmdir()
    except OSError:
        # A failed cleanup still leaves a manifest-less bundle that verification rejects.
        return


def _persist_bundle(bundle: Path, artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Path]:
    if set(artifacts) != set(PROTECTED_ARTIFACT_FILENAMES):
        raise ProtectedArtifactCaptureError("protected artifact set is incomplete")
    paths: dict[str, Path] = {}
    for key, filename in PROTECTED_ARTIFACT_FILENAMES.items():
        path = bundle / filename
        _write_protected_json(path, artifacts[key])
        paths[key] = path
    return paths


def _build_manifest(artifacts, paths):
    lock = artifacts["lock_artifact"]
    final_validation = artifacts["final_validation_artifact"]
    return {
        "capture_version": "protected-mt5-artifact-capture/v1",
        "status": "COMPLETE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_count": len(paths),
        "semantic_hash": lock["approved_semantic_values_hash"],
        "proposal_reference": artifacts["proposal_artifact"]["proposal_id"],
        "approval_lock_reference": lock["approval_lock_id"],
        "final_validation_reference": final_validation["final_validation_id"],
        "account_context_fingerprint": artifacts["account_fingerprint_artifact"][
            "account_context_fingerprint"
        ],
        "export_compatibility_valid": True,
        "execution_permission_granted": False,
        "artifacts": {
            key: {
                "filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for key, path in paths.items()
        },
    }


def _verify_export_compatibility(paths, bundle, expected_phrase, **kwargs):
    probe = bundle / ".export-compatibility-probe.json"
    try:
        export_protected_request(
            **paths,
            output=probe,
            expected_confirmation_phrase=expected_phrase,
            **kwargs,
        )
    except ProtectedRequestExportError as exc:
        safe_reason = str(exc).strip() or type(exc).__name__
        raise ProtectedArtifactCaptureError(
            f"protected bundle is not exporter-compatible: {safe_reason}"
        ) from exc
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise ProtectedArtifactCaptureError("export compatibility probe could not be removed") from exc


def _write_protected_json(path: Path, payload: Mapping[str, Any]) -> None:
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
        raise ProtectedArtifactCaptureError("protected artifact could not be written") from exc


def _require_blocked_execution_state(report) -> None:
    unsafe = (
        report.live_submission_allowed,
        report.live_execution_allowed,
        report.order_send_allowed,
        report.execution_allowed,
        report.executable,
        report.order_sent,
    )
    if any(unsafe) or report.ticket is not None or report.deal is not None:
        raise ProtectedArtifactCaptureError("pre-submit report enables execution")
    if not report.hard_live_block_required or not report.kill_switch_engaged:
        raise ProtectedArtifactCaptureError("pre-submit hard block is not engaged")


@contextmanager
def isolated_capture_journals():
    path_names = [
        name
        for name in dir(Config)
        if (name.endswith("JOURNAL_PATH") or name.endswith("IDEMPOTENCY_PATH"))
        and isinstance(getattr(Config, name, None), str)
    ]
    originals = {name: getattr(Config, name) for name in path_names}
    with tempfile.TemporaryDirectory(prefix="mt5-protected-capture-") as temporary:
        root = Path(temporary)
        try:
            for name in path_names:
                setattr(Config, name, str(root / f"{name.lower()}.jsonl"))
            yield
        finally:
            for name, value in originals.items():
                setattr(Config, name, value)
