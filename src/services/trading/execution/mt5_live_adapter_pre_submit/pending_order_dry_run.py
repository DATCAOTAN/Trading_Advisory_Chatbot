from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_SCHEMA_VERSION,
    AutonomousDecisionCandidate,
    AutonomousDecisionOrchestrator,
    AutonomousOrderMarketSnapshot,
    autonomous_candidate_has_offline_provenance,
    autonomous_market_snapshot_provenance_hash,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.proposal.models import HumanConfirmedProposalIntent
from src.services.trading.review.models import HumanReviewArtifact


PENDING_ORDER_CONTRACT_SCHEMA_VERSION = "controlled-pending-order-contract/v1"
PENDING_ORDER_DRY_RUN_SCHEMA_VERSION = "pending-order-request-draft/v1"
SUPPORTED_PENDING_ORDER_TYPES = (
    "BUY_LIMIT",
    "SELL_LIMIT",
    "BUY_STOP",
    "SELL_STOP",
    "BUY_STOP_LIMIT",
    "SELL_STOP_LIMIT",
)


@dataclass(frozen=True)
class ControlledPendingOrderValidation:
    valid: bool
    status: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ControlledPendingOrderContract:
    schema_version: str
    contract_reference: str
    candidate_reference: str
    candidate_provenance_hash: str
    generated_at: str
    expires_at: str
    symbol: str = field(repr=False)
    side: str = ""
    order_type: str = ""
    action: str = "PENDING"
    entry_intent: str = ""
    entry_price: str = field(default="", repr=False)
    trigger_price: str = field(default="", repr=False)
    limit_price: str = field(default="", repr=False)
    stop_loss: str = field(default="", repr=False)
    take_profit: str = field(default="", repr=False)
    proposed_volume: str = field(default="", repr=False)
    risk_policy_reference: str = ""
    expiration_policy: str = ""
    market_snapshot_reference: str = ""
    market_snapshot_provenance_hash: str = ""
    symbol_metadata_reference: str = ""
    symbol_metadata_hash: str = ""
    account_context_reference: str = ""
    source_review_artifact_id: str = ""
    source_confirmation_intent_id: str = ""
    confirmation_artifact_hash: str = ""
    structured_order_hash: str = ""
    deviation: int = 0
    magic: int = 0
    comment: str = field(default="", repr=False)
    audit: str = field(default="", repr=False)
    validation_status: str = "BLOCKED"
    blocker_codes: tuple[str, ...] = ()
    canonical_integrity_hash: str = ""
    idempotency_key: str = ""
    source_refs: tuple[str, ...] = ()
    execution_authority: bool = False
    human_confirmation_present: bool = False
    execution_permission_requested: bool = False
    live_submission_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    order_sent: bool = False
    metadata_redacted: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_reference": self.contract_reference,
            "candidate_reference": self.candidate_reference,
            "candidate_provenance_hash": self.candidate_provenance_hash,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "symbol_present": bool(self.symbol),
            "side": self.side,
            "order_type": self.order_type,
            "action": self.action,
            "entry_intent": self.entry_intent,
            "entry_price_present": bool(self.entry_price),
            "trigger_price_present": bool(self.trigger_price),
            "limit_price_present": bool(self.limit_price),
            "stop_loss_present": bool(self.stop_loss),
            "take_profit_present": bool(self.take_profit),
            "proposed_volume_present": bool(self.proposed_volume),
            "risk_policy_reference": self.risk_policy_reference,
            "expiration_policy": self.expiration_policy,
            "market_snapshot_reference": self.market_snapshot_reference,
            "market_snapshot_provenance_hash": self.market_snapshot_provenance_hash,
            "symbol_metadata_reference": self.symbol_metadata_reference,
            "symbol_metadata_hash": self.symbol_metadata_hash,
            "account_context_reference": self.account_context_reference,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_confirmation_intent_id": self.source_confirmation_intent_id,
            "confirmation_artifact_hash": self.confirmation_artifact_hash,
            "structured_order_hash": self.structured_order_hash,
            "execution_metadata_present": bool(self.comment and self.audit),
            "validation_status": self.validation_status,
            "blocker_codes": list(self.blocker_codes),
            "canonical_integrity_hash": self.canonical_integrity_hash,
            "idempotency_key_hash": _sha256(self.idempotency_key),
            "source_refs_count": len(self.source_refs),
            "execution_authority": False,
            "human_confirmation_present": False,
            "execution_permission_requested": False,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "metadata_redacted": True,
        }

    def to_operator_review_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_reference": self.contract_reference,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "action": self.action,
            "entry_intent": self.entry_intent,
            "entry_price": self.entry_price,
            "trigger_price": self.trigger_price,
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "proposed_volume": self.proposed_volume,
            "risk_policy_present": bool(self.risk_policy_reference),
            "expiration_policy": self.expiration_policy,
            "validation_status": self.validation_status,
            "blocker_codes": list(self.blocker_codes),
            "fresh": self.validation_status == "VALID",
            "execution_authority": False,
            "execution_permission_requested": False,
            "order_send_allowed": False,
            "executable": False,
            "order_sent": False,
        }

    def to_protected_dict(self) -> dict[str, Any]:
        """Serialize the immutable approved contract for the protected bridge boundary."""
        return {
            "schema_version": self.schema_version,
            "contract_reference": self.contract_reference,
            "candidate_reference": self.candidate_reference,
            "candidate_provenance_hash": self.candidate_provenance_hash,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "action": self.action,
            "entry_intent": self.entry_intent,
            "entry_price": self.entry_price,
            "trigger_price": self.trigger_price,
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "proposed_volume": self.proposed_volume,
            "risk_policy_reference": self.risk_policy_reference,
            "expiration_policy": self.expiration_policy,
            "market_snapshot_reference": self.market_snapshot_reference,
            "market_snapshot_provenance_hash": self.market_snapshot_provenance_hash,
            "symbol_metadata_reference": self.symbol_metadata_reference,
            "symbol_metadata_hash": self.symbol_metadata_hash,
            "account_context_reference": self.account_context_reference,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_confirmation_intent_id": self.source_confirmation_intent_id,
            "confirmation_artifact_hash": self.confirmation_artifact_hash,
            "structured_order_hash": self.structured_order_hash,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": self.comment,
            "audit": self.audit,
            "validation_status": self.validation_status,
            "blocker_codes": list(self.blocker_codes),
            "canonical_integrity_hash": self.canonical_integrity_hash,
            "idempotency_key": self.idempotency_key,
            "source_refs": list(self.source_refs),
            "execution_authority": False,
            "human_confirmation_present": False,
            "execution_permission_requested": False,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "metadata_redacted": True,
        }

    def integrity_valid(self) -> bool:
        calculated = _sha256(_canonical_json(_contract_material(self)))
        return (
            _valid_hash(self.canonical_integrity_hash)
            and hmac.compare_digest(calculated, self.canonical_integrity_hash)
            and self.contract_reference == "controlled_pending_" + calculated[:24]
            and hmac.compare_digest(
                self.idempotency_key,
                _sha256("controlled-pending-dry-run/v1|" + calculated),
            )
        )


@dataclass(frozen=True)
class PendingOrderDryRunRequestDraft:
    schema_version: str
    draft_reference: str
    contract_reference: str
    contract_integrity_hash: str
    generated_at: str
    expires_at: str
    action: str
    order_type: str
    symbol: str = field(repr=False)
    side: str = ""
    entry_price: str = field(default="", repr=False)
    trigger_price: str = field(default="", repr=False)
    limit_price: str = field(default="", repr=False)
    stop_loss: str = field(default="", repr=False)
    take_profit: str = field(default="", repr=False)
    volume: str = field(default="", repr=False)
    risk_policy_reference: str = ""
    expiration_policy: str = ""
    deviation: int = 0
    magic: int = 0
    comment: str = field(default="", repr=False)
    audit: str = field(default="", repr=False)
    account_context_reference: str = ""
    semantic_request_hash: str = ""
    idempotency_key: str = ""
    real_mt5_payload_created: bool = False
    broker_submittable_request_dict_created: bool = False
    mt5_constants_used: bool = False
    bridge_request_created: bool = False
    execution_authority: bool = False
    execution_permission_requested: bool = False
    live_submission_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    order_sent: bool = False
    metadata_redacted: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "draft_reference": self.draft_reference,
            "contract_reference": self.contract_reference,
            "contract_integrity_hash": self.contract_integrity_hash,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "action": self.action,
            "order_type": self.order_type,
            "symbol_present": bool(self.symbol),
            "side": self.side,
            "entry_price_present": bool(self.entry_price),
            "trigger_price_present": bool(self.trigger_price),
            "limit_price_present": bool(self.limit_price),
            "stop_loss_present": bool(self.stop_loss),
            "take_profit_present": bool(self.take_profit),
            "volume_present": bool(self.volume),
            "risk_policy_reference": self.risk_policy_reference,
            "expiration_policy": self.expiration_policy,
            "execution_metadata_present": bool(self.comment and self.audit),
            "account_context_reference": self.account_context_reference,
            "semantic_request_hash": self.semantic_request_hash,
            "idempotency_key_hash": _sha256(self.idempotency_key),
            "real_mt5_payload_created": False,
            "broker_submittable_request_dict_created": False,
            "mt5_constants_used": False,
            "bridge_request_created": False,
            "execution_authority": False,
            "execution_permission_requested": False,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "metadata_redacted": True,
        }

    def to_semantic_dry_run_dict(self) -> dict[str, Any]:
        """Return semantic values for local operator review, never for bridge submission."""
        return {
            "action": self.action,
            "order_type": self.order_type,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "trigger_price": self.trigger_price,
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "volume": self.volume,
            "risk_policy_reference": self.risk_policy_reference,
            "expiration_policy": self.expiration_policy,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": self.comment,
            "audit": self.audit,
            "contract_reference": self.contract_reference,
            "contract_integrity_hash": self.contract_integrity_hash,
            "account_context_reference": self.account_context_reference,
            "non_executable": True,
        }

    def integrity_valid(self, contract: ControlledPendingOrderContract) -> bool:
        return self == _build_draft(contract) and contract.integrity_valid()


@dataclass(frozen=True)
class ControlledPendingOrderDryRunResult:
    contract: ControlledPendingOrderContract
    validation: ControlledPendingOrderValidation
    request_draft: PendingOrderDryRunRequestDraft | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_public_dict(),
            "validation": self.validation.to_public_dict(),
            "request_draft": (
                self.request_draft.to_public_dict() if self.request_draft else None
            ),
        }


class ControlledPendingOrderDryRunMapper:
    """Map a reviewed structured candidate to a non-executable semantic draft."""

    def __init__(self, candidate_validator: AutonomousDecisionOrchestrator):
        self.candidate_validator = candidate_validator

    def build(
        self,
        *,
        candidate: AutonomousDecisionCandidate,
        market_snapshot: AutonomousOrderMarketSnapshot,
        review_artifact: HumanReviewArtifact,
        confirmation_intent: HumanConfirmedProposalIntent,
        account_context: ProtectedAccountContextCapture,
        expected_account_context_fingerprint: str,
        expiration_policy: str = "",
        deviation: int = 0,
        magic: int = 0,
        comment: str = "",
        audit: str = "",
        now: datetime | None = None,
    ) -> ControlledPendingOrderDryRunResult:
        evaluated_at = _utc(now)
        blockers: list[str] = []
        warnings: list[str] = []

        candidate_validation = self.candidate_validator.validate_candidate(
            candidate, now=evaluated_at
        )
        blockers.extend(candidate_validation.issues)
        if autonomous_candidate_has_offline_provenance(candidate):
            blockers.append("OFFLINE_PROVENANCE_NOT_EXECUTABLE")
        if candidate.schema_version != AUTONOMOUS_DECISION_SCHEMA_VERSION:
            blockers.append("PENDING_CANDIDATE_SCHEMA_V2_REQUIRED")
        if candidate.intent != "OPEN_POSITION":
            blockers.append("PENDING_CANDIDATE_OPEN_POSITION_REQUIRED")
        if candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE":
            blockers.append("PENDING_CANDIDATE_NOT_ELIGIBLE")
        blockers.extend(candidate.blocked_reason_codes)
        if candidate.action != "PENDING":
            blockers.append("PENDING_ACTION_REQUIRED")
        if candidate.order_type not in SUPPORTED_PENDING_ORDER_TYPES:
            blockers.append("UNSUPPORTED_PENDING_ORDER_TYPE")
        if not _valid_hash(candidate.provenance_hash):
            blockers.append("CANDIDATE_PROVENANCE_HASH_INVALID")
        elif candidate.candidate_reference != "autonomous_decision_" + candidate.provenance_hash[:24]:
            blockers.append("CANDIDATE_REFERENCE_MISMATCH")
        if not _valid_hash(candidate.decision_idempotency_key) or not hmac.compare_digest(
            candidate.decision_idempotency_key,
            _sha256("autonomous-decision/v2|" + candidate.provenance_hash),
        ):
            blockers.append("CANDIDATE_IDEMPOTENCY_MISMATCH")
        if not candidate.market_snapshot_reference or not candidate.market_snapshot_provenance_hash:
            blockers.append("MARKET_SNAPSHOT_PROVENANCE_MISSING")
        if not candidate.proposed_semantic_parameter_references:
            blockers.append("SEMANTIC_PARAMETER_REFERENCES_MISSING")

        snapshot_hash = autonomous_market_snapshot_provenance_hash(market_snapshot)
        if market_snapshot.snapshot_reference != candidate.market_snapshot_reference:
            blockers.append("MARKET_SNAPSHOT_REFERENCE_MISMATCH")
        if not hmac.compare_digest(snapshot_hash, candidate.market_snapshot_provenance_hash):
            blockers.append("MARKET_SNAPSHOT_HASH_MISMATCH")
        if market_snapshot.symbol != candidate.symbol_reference:
            blockers.append("MARKET_SNAPSHOT_SYMBOL_MISMATCH")
        if not market_snapshot.source_refs:
            blockers.append("MARKET_SNAPSHOT_SOURCE_REFS_MISSING")
        if not _fresh(
            market_snapshot.observed_at,
            evaluated_at,
            self.candidate_validator.config.input_max_age_seconds,
        ):
            blockers.append("MARKET_SNAPSHOT_STALE")

        metadata_material = _symbol_metadata_material(market_snapshot)
        if metadata_material is None:
            blockers.append("SYMBOL_METADATA_MISSING_OR_INVALID")
            metadata_hash = ""
            metadata_reference = ""
        else:
            metadata_hash = _sha256(_canonical_json(metadata_material))
            metadata_reference = "symbol_metadata_" + metadata_hash[:24]

        binding_refs = {
            candidate.candidate_reference,
            candidate.provenance_hash,
            candidate.structured_order_hash,
        }
        review_refs = {str(item) for item in review_artifact.source_refs}
        if review_artifact.review_status != "READY_FOR_REVIEW":
            blockers.append("HUMAN_REVIEW_NOT_READY")
        if review_artifact.blockers:
            blockers.append("HUMAN_REVIEW_HAS_BLOCKERS")
        if review_artifact.symbol != candidate.symbol_reference:
            blockers.append("HUMAN_REVIEW_SYMBOL_MISMATCH")
        if not binding_refs.issubset(review_refs):
            blockers.append("HUMAN_REVIEW_CANDIDATE_BINDING_MISMATCH")
        if not _fresh(
            review_artifact.created_at,
            evaluated_at,
            self.candidate_validator.config.input_max_age_seconds,
        ):
            blockers.append("HUMAN_REVIEW_STALE")

        confirmation_refs = {str(item) for item in confirmation_intent.source_refs}
        if confirmation_intent.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            blockers.append("PROPOSAL_CONFIRMATION_NOT_GRANTED")
        if confirmation_intent.human_confirmation_state != "CONFIRMED_PROPOSAL_WORKFLOW":
            blockers.append("HUMAN_CONFIRMATION_NOT_GRANTED")
        if not confirmation_intent.proposal_workflow_allowed:
            blockers.append("PROPOSAL_WORKFLOW_NOT_ALLOWED")
        if not confirmation_intent.dry_run_only or confirmation_intent.executable:
            blockers.append("CONFIRMATION_MUST_REMAIN_DRY_RUN_ONLY")
        if confirmation_intent.source_review_artifact_id != review_artifact.artifact_id:
            blockers.append("CONFIRMATION_REVIEW_REFERENCE_MISMATCH")
        if not confirmation_intent.artifact_hash:
            blockers.append("CONFIRMATION_ARTIFACT_HASH_MISSING")
        if not binding_refs.issubset(confirmation_refs):
            blockers.append("CONFIRMATION_CANDIDATE_BINDING_MISMATCH")
        required_phrase = str(confirmation_intent.confirmation_phrase_required or "")
        received_phrase = str(confirmation_intent.confirmation_phrase_received or "")
        if not required_phrase or not hmac.compare_digest(required_phrase, received_phrase):
            blockers.append("CONFIRMATION_PHRASE_INVALID")
        if not _fresh(
            confirmation_intent.created_at,
            evaluated_at,
            self.candidate_validator.config.input_max_age_seconds,
        ):
            blockers.append("CONFIRMATION_STALE")

        fingerprint = str(account_context.account_context_fingerprint or "").lower()
        expected_fingerprint = str(expected_account_context_fingerprint or "").lower()
        if account_context.status != "OK" or account_context.redacted is not True:
            blockers.append("ACCOUNT_CONTEXT_INVALID")
        if not _valid_hash(fingerprint) or not _valid_hash(expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_FINGERPRINT_INVALID")
        elif not hmac.compare_digest(fingerprint, expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_MISMATCH")
        if not _fresh(
            account_context.captured_at,
            evaluated_at,
            self.candidate_validator.config.input_max_age_seconds,
        ):
            blockers.append("ACCOUNT_CONTEXT_STALE")
        account_context_reference = (
            "account_context_" + _sha256("pending-dry-run|" + fingerprint)[:24]
            if _valid_hash(fingerprint)
            else ""
        )

        if not candidate.proposed_volume and not candidate.risk_policy_reference:
            blockers.append("AUTHORITATIVE_VOLUME_OR_RISK_REFERENCE_MISSING")
        if candidate.proposed_volume and _positive_decimal(candidate.proposed_volume) is None:
            blockers.append("PROPOSED_VOLUME_INVALID")
        if not candidate.stop_loss or not candidate.take_profit:
            blockers.append("PROTECTION_VALUES_MISSING")
        selected_expiration_policy = str(expiration_policy or "").strip().upper()
        if selected_expiration_policy and selected_expiration_policy != "GTC":
            blockers.append("UNSUPPORTED_EXPIRATION_POLICY")
        if not selected_expiration_policy:
            warnings.append("EXPIRATION_POLICY_REQUIRED_FOR_SUBMISSION")
        if isinstance(deviation, bool) or not isinstance(deviation, int) or deviation < 0:
            blockers.append("DEVIATION_INVALID")
        if isinstance(magic, bool) or not isinstance(magic, int) or magic < 0:
            blockers.append("MAGIC_INVALID")
        if len(str(comment)) > 31:
            blockers.append("COMMENT_INVALID")

        blockers = _ordered_unique(blockers)
        warnings = _ordered_unique(warnings)
        status = "VALID" if not blockers else "BLOCKED"
        source_refs = tuple(
            sorted(
                {
                    *candidate.proposed_semantic_parameter_references,
                    *candidate.knowledge_evidence_references,
                    *market_snapshot.source_refs,
                    *review_refs,
                    *confirmation_refs,
                }
            )
        )
        material = {
            "schema_version": PENDING_ORDER_CONTRACT_SCHEMA_VERSION,
            "candidate_reference": candidate.candidate_reference,
            "candidate_provenance_hash": candidate.provenance_hash,
            "symbol": candidate.symbol_reference,
            "side": candidate.side,
            "order_type": candidate.order_type,
            "action": candidate.action,
            "entry_intent": candidate.entry_intent,
            "entry_price": candidate.entry_price,
            "trigger_price": candidate.trigger_price,
            "limit_price": candidate.limit_price,
            "stop_loss": candidate.stop_loss,
            "take_profit": candidate.take_profit,
            "proposed_volume": candidate.proposed_volume,
            "risk_policy_reference": candidate.risk_policy_reference,
            "expiration_policy": selected_expiration_policy,
            "market_snapshot_reference": candidate.market_snapshot_reference,
            "market_snapshot_provenance_hash": candidate.market_snapshot_provenance_hash,
            "symbol_metadata_hash": metadata_hash,
            "account_context_reference": account_context_reference,
            "source_review_artifact_id": review_artifact.artifact_id,
            "source_confirmation_intent_id": confirmation_intent.intent_id,
            "confirmation_artifact_hash": confirmation_intent.artifact_hash,
            "structured_order_hash": candidate.structured_order_hash,
            "deviation": deviation,
            "magic": magic,
            "comment": str(comment),
            "audit": str(audit),
            "expires_at": candidate.expires_at,
            "blocker_codes": blockers,
            "source_refs": source_refs,
        }
        integrity_hash = _sha256(_canonical_json(material))
        contract_reference = "controlled_pending_" + integrity_hash[:24]
        contract_idempotency = _sha256("controlled-pending-dry-run/v1|" + integrity_hash)
        contract = ControlledPendingOrderContract(
            schema_version=PENDING_ORDER_CONTRACT_SCHEMA_VERSION,
            contract_reference=contract_reference,
            candidate_reference=candidate.candidate_reference,
            candidate_provenance_hash=candidate.provenance_hash,
            generated_at=evaluated_at.isoformat(),
            expires_at=candidate.expires_at,
            symbol=candidate.symbol_reference,
            side=candidate.side,
            order_type=candidate.order_type,
            action=candidate.action,
            entry_intent=candidate.entry_intent,
            entry_price=candidate.entry_price,
            trigger_price=candidate.trigger_price,
            limit_price=candidate.limit_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            proposed_volume=candidate.proposed_volume,
            risk_policy_reference=candidate.risk_policy_reference,
            expiration_policy=selected_expiration_policy,
            market_snapshot_reference=candidate.market_snapshot_reference,
            market_snapshot_provenance_hash=candidate.market_snapshot_provenance_hash,
            symbol_metadata_reference=metadata_reference,
            symbol_metadata_hash=metadata_hash,
            account_context_reference=account_context_reference,
            source_review_artifact_id=review_artifact.artifact_id,
            source_confirmation_intent_id=confirmation_intent.intent_id,
            confirmation_artifact_hash=confirmation_intent.artifact_hash,
            structured_order_hash=candidate.structured_order_hash,
            deviation=deviation,
            magic=magic,
            comment=str(comment),
            audit=str(audit),
            validation_status=status,
            blocker_codes=tuple(blockers),
            canonical_integrity_hash=integrity_hash,
            idempotency_key=contract_idempotency,
            source_refs=source_refs,
        )
        validation = ControlledPendingOrderValidation(
            valid=not blockers,
            status=status,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )
        draft = _build_draft(contract) if validation.valid else None
        return ControlledPendingOrderDryRunResult(contract, validation, draft)


def _build_draft(contract: ControlledPendingOrderContract) -> PendingOrderDryRunRequestDraft:
    semantic_material = {
        "action": contract.action,
        "order_type": contract.order_type,
        "symbol": contract.symbol,
        "side": contract.side,
        "entry_price": contract.entry_price,
        "trigger_price": contract.trigger_price,
        "limit_price": contract.limit_price,
        "stop_loss": contract.stop_loss,
        "take_profit": contract.take_profit,
        "volume": contract.proposed_volume,
        "risk_policy_reference": contract.risk_policy_reference,
        "expiration_policy": contract.expiration_policy,
        "deviation": contract.deviation,
        "magic": contract.magic,
        "comment": contract.comment,
        "audit": contract.audit,
        "contract_reference": contract.contract_reference,
        "contract_integrity_hash": contract.canonical_integrity_hash,
        "account_context_reference": contract.account_context_reference,
    }
    semantic_hash = _sha256(_canonical_json(semantic_material))
    draft_reference = "pending_dry_run_" + semantic_hash[:24]
    return PendingOrderDryRunRequestDraft(
        schema_version=PENDING_ORDER_DRY_RUN_SCHEMA_VERSION,
        draft_reference=draft_reference,
        contract_reference=contract.contract_reference,
        contract_integrity_hash=contract.canonical_integrity_hash,
        generated_at=contract.generated_at,
        expires_at=contract.expires_at,
        action=contract.action,
        order_type=contract.order_type,
        symbol=contract.symbol,
        side=contract.side,
        entry_price=contract.entry_price,
        trigger_price=contract.trigger_price,
        limit_price=contract.limit_price,
        stop_loss=contract.stop_loss,
        take_profit=contract.take_profit,
        volume=contract.proposed_volume,
        risk_policy_reference=contract.risk_policy_reference,
        expiration_policy=contract.expiration_policy,
        deviation=contract.deviation,
        magic=contract.magic,
        comment=contract.comment,
        audit=contract.audit,
        account_context_reference=contract.account_context_reference,
        semantic_request_hash=semantic_hash,
        idempotency_key=_sha256("pending-order-request-draft/v1|" + semantic_hash),
    )


def _contract_material(contract: ControlledPendingOrderContract) -> dict[str, Any]:
    return {
        "schema_version": contract.schema_version,
        "candidate_reference": contract.candidate_reference,
        "candidate_provenance_hash": contract.candidate_provenance_hash,
        "symbol": contract.symbol,
        "side": contract.side,
        "order_type": contract.order_type,
        "action": contract.action,
        "entry_intent": contract.entry_intent,
        "entry_price": contract.entry_price,
        "trigger_price": contract.trigger_price,
        "limit_price": contract.limit_price,
        "stop_loss": contract.stop_loss,
        "take_profit": contract.take_profit,
        "proposed_volume": contract.proposed_volume,
        "risk_policy_reference": contract.risk_policy_reference,
        "expiration_policy": contract.expiration_policy,
        "market_snapshot_reference": contract.market_snapshot_reference,
        "market_snapshot_provenance_hash": contract.market_snapshot_provenance_hash,
        "symbol_metadata_hash": contract.symbol_metadata_hash,
        "account_context_reference": contract.account_context_reference,
        "source_review_artifact_id": contract.source_review_artifact_id,
        "source_confirmation_intent_id": contract.source_confirmation_intent_id,
        "confirmation_artifact_hash": contract.confirmation_artifact_hash,
        "structured_order_hash": contract.structured_order_hash,
        "deviation": contract.deviation,
        "magic": contract.magic,
        "comment": contract.comment,
        "audit": contract.audit,
        "expires_at": contract.expires_at,
        "blocker_codes": list(contract.blocker_codes),
        "source_refs": tuple(contract.source_refs),
    }

def _symbol_metadata_material(
    snapshot: AutonomousOrderMarketSnapshot,
) -> dict[str, Any] | None:
    point = _positive_decimal(snapshot.point)
    tick_size = _positive_decimal(snapshot.tick_size)
    minimum_distance = _positive_decimal(snapshot.minimum_distance_points, allow_zero=True)
    if point is None or tick_size is None or minimum_distance is None:
        return None
    if not isinstance(snapshot.digits, int) or isinstance(snapshot.digits, bool) or snapshot.digits < 0:
        return None
    if not snapshot.provider_name or not snapshot.source_refs:
        return None
    return {
        "symbol": snapshot.symbol,
        "provider_name": snapshot.provider_name,
        "point": _decimal_text(point),
        "tick_size": _decimal_text(tick_size),
        "digits": snapshot.digits,
        "minimum_distance_points": _decimal_text(minimum_distance),
        "source_refs": sorted(set(snapshot.source_refs)),
    }


def _positive_decimal(value: Any, *, allow_zero: bool = False) -> Decimal | None:
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0 or (parsed == 0 and not allow_zero):
        return None
    return parsed


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fresh(value: str, now: datetime, maximum_age_seconds: int) -> bool:
    parsed = _parse_datetime(value)
    if parsed is None or parsed > now + timedelta(seconds=5):
        return False
    return now - parsed <= timedelta(seconds=maximum_age_seconds)


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(timezone.utc)
    if selected.tzinfo is None:
        selected = selected.replace(tzinfo=timezone.utc)
    return selected.astimezone(timezone.utc)


def _valid_hash(value: str) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
