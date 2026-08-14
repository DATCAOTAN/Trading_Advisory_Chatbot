from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Mapping

from src.services.trading.execution.live_value_approval_lock.models import (
    ApprovedSemanticExecutionParameters,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import hash_text
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (
    pre_submit_record_hash,
)


if TYPE_CHECKING:
    from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
        ControlledPendingOrderContract,
        ControlledPendingOrderValidation,
        PendingOrderDryRunRequestDraft,
    )


PENDING_EXECUTION_REQUEST_VERSION = "controlled-mt5-pending-execution/v1"
AUTONOMOUS_EXECUTION_REQUEST_VERSION = "controlled-mt5-autonomous-execution/v1"


@dataclass(frozen=True)
class MT5ControlledExecutionRequest:
    request_version: str
    approved_semantic_parameters: Mapping[str, Any] = field(repr=False)
    canonical_semantic_hash: str
    approval_value_hash: str
    lock_value_hash: str
    approval_reference: str
    lock_reference: str
    source_artifact_reference: str
    approval_timestamp: str
    lock_timestamp: str
    human_confirmation_reference: str
    human_confirmation_phrase: str = field(repr=False)
    pre_submit_validation_reference: str
    pre_submit_validation_valid: bool
    idempotency_key: str = field(repr=False)
    expected_account_context_fingerprint: str
    execution_permission_requested: bool
    authorization_source: str = "HUMAN_CONFIRMATION"
    authorization_reference: str = ""

    @classmethod
    def from_mandate_artifacts(
        cls,
        candidate,
        authorization,
        final_validation,
        pre_submit_report,
        *,
        expected_account_context_fingerprint: str,
        execution_permission_requested: bool = True,
    ) -> "MT5ControlledExecutionRequest":
        protected_intent = dict(getattr(final_validation, "protected_intent", {}) or {})
        fingerprint = str(expected_account_context_fingerprint or "").strip().lower()
        if (
            getattr(authorization, "authorization_source", "") != "STANDING_MANDATE"
            or not callable(getattr(authorization, "integrity_valid", None))
            or not authorization.integrity_valid()
            or getattr(final_validation, "valid", False) is not True
            or getattr(final_validation, "authorization_source", "") != "STANDING_MANDATE"
            or getattr(final_validation, "authorization_id", "") != authorization.authorization_id
            or getattr(pre_submit_report, "valid", False) is not True
            or getattr(pre_submit_report, "pre_submit_ready", False) is not True
            or getattr(pre_submit_report, "authorization_source", "") != "STANDING_MANDATE"
            or getattr(pre_submit_report, "source_authorization_id", "") != authorization.authorization_id
            or not protected_intent
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not isinstance(execution_permission_requested, bool)
            or execution_permission_requested is not True
        ):
            raise ValueError("MANDATE_EXECUTION_ARTIFACTS_INVALID")
        bindings = (
            (protected_intent.get("candidate_reference"), candidate.candidate_reference),
            (protected_intent.get("candidate_provenance_hash"), candidate.provenance_hash),
            (protected_intent.get("structured_order_hash"), candidate.structured_order_hash),
            (protected_intent.get("authorization_id"), authorization.authorization_id),
            (protected_intent.get("symbol"), authorization.symbol),
            (protected_intent.get("broker_symbol"), authorization.broker_symbol),
            (protected_intent.get("action"), authorization.order_family),
        )
        if any(left != right for left, right in bindings):
            raise ValueError("MANDATE_EXECUTION_BINDING_MISMATCH")
        intent_hash = hash_text(
            json.dumps(protected_intent, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        )
        permission_state = protected_intent.get("permission_state")
        permission_state_hash = (
            hash_text(
                json.dumps(
                    permission_state,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if isinstance(permission_state, Mapping)
            else ""
        )
        if not hmac.compare_digest(
            permission_state_hash, str(getattr(final_validation, "permission_state_hash", ""))
        ):
            raise ValueError("MANDATE_PERMISSION_SNAPSHOT_INVALID")
        if not hmac.compare_digest(intent_hash, str(getattr(pre_submit_report, "intent_hash", ""))):
            raise ValueError("MANDATE_PRE_SUBMIT_HASH_MISMATCH")
        return cls(
            request_version=AUTONOMOUS_EXECUTION_REQUEST_VERSION,
            approved_semantic_parameters=protected_intent,
            canonical_semantic_hash=intent_hash,
            approval_value_hash=final_validation.approval_integrity_hash,
            lock_value_hash=authorization.artifact_hash,
            approval_reference=final_validation.final_validation_id,
            lock_reference=authorization.authorization_id,
            source_artifact_reference=candidate.candidate_reference,
            approval_timestamp=final_validation.created_at,
            lock_timestamp=authorization.created_at,
            human_confirmation_reference="",
            human_confirmation_phrase="",
            pre_submit_validation_reference=pre_submit_report.report_id,
            pre_submit_validation_valid=True,
            idempotency_key=authorization.deterministic_idempotency_key,
            expected_account_context_fingerprint=fingerprint,
            execution_permission_requested=True,
            authorization_source="STANDING_MANDATE",
            authorization_reference=authorization.authorization_id,
        )

    @classmethod
    def from_artifacts(
        cls,
        approval_lock,
        final_validation,
        final_validation_report,
        pre_submit_report,
        *,
        expected_account_context_fingerprint: str,
        human_confirmation_phrase: str,
        execution_permission_requested: bool = True,
    ) -> "MT5ControlledExecutionRequest":
        parameters = getattr(approval_lock, "approved_semantic_parameters", None)
        integrity_check = getattr(approval_lock, "approved_semantic_integrity_valid", None)
        if parameters is None or not callable(integrity_check) or not integrity_check():
            raise ValueError("approved semantic parameters are missing or invalid")
        semantic_hash = parameters.canonical_values_hash
        if (
            getattr(final_validation_report, "valid", False) is not True
            or getattr(final_validation, "approved_semantic_values_verified", False) is not True
            or getattr(final_validation, "artifact_hash", "") != semantic_hash
        ):
            raise ValueError("final validation does not verify approved semantic parameters")
        if (
            getattr(pre_submit_report, "valid", False) is not True
            or getattr(pre_submit_report, "controlled_demo_integration_workflow_allowed", False) is not True
        ):
            raise ValueError("pre-submit validation is not valid")
        fingerprint = str(expected_account_context_fingerprint or "").strip()
        phrase = str(human_confirmation_phrase or "").strip()
        idempotency_key = str(parameters.idempotency or "").strip()
        if not isinstance(execution_permission_requested, bool):
            raise ValueError("execution permission request flag must be boolean")
        if not fingerprint or not phrase or not idempotency_key:
            raise ValueError("controlled execution request references are incomplete")
        confirmation_reference = hash_text(f"{phrase}|{idempotency_key}|{fingerprint}")
        return cls(
            request_version="controlled-mt5-execution/v1",
            approved_semantic_parameters=parameters.to_protected_dict(),
            canonical_semantic_hash=semantic_hash,
            approval_value_hash=getattr(approval_lock, "approval_value_hash", ""),
            lock_value_hash=getattr(approval_lock, "lock_value_hash", ""),
            approval_reference=parameters.approval_artifact_ref,
            lock_reference=parameters.lock_artifact_ref,
            source_artifact_reference=parameters.source_artifact_ref,
            approval_timestamp=parameters.approved_at,
            lock_timestamp=parameters.locked_at,
            human_confirmation_reference=confirmation_reference,
            human_confirmation_phrase=phrase,
            pre_submit_validation_reference=getattr(pre_submit_report, "report_id", ""),
            pre_submit_validation_valid=True,
            idempotency_key=idempotency_key,
            expected_account_context_fingerprint=fingerprint,
            execution_permission_requested=execution_permission_requested,
        )

    @classmethod
    def from_human_candidate_artifacts(
        cls,
        candidate,
        confirmation,
        pre_submit_record: Mapping[str, Any],
        *,
        expected_account_context_fingerprint: str,
        human_confirmation_phrase: str,
        execution_permission_requested: bool = True,
        now: datetime | None = None,
    ) -> "MT5ControlledExecutionRequest":
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
        evaluated_at = evaluated_at.astimezone(timezone.utc)
        fingerprint = str(expected_account_context_fingerprint or "").strip().lower()
        phrase = str(human_confirmation_phrase or "").strip()
        protected = dict(pre_submit_record.get("protected_intent", {}) or {})
        record_material = dict(pre_submit_record)
        actual_record_hash = str(record_material.get("record_hash", ""))
        record_material["record_hash"] = ""
        if (
            len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not phrase
            or execution_permission_requested is not True
            or pre_submit_record.get("status") != "PRE_SUBMIT_READY_NON_EXECUTABLE"
            or pre_submit_record.get("valid") is not True
            or pre_submit_record.get("pre_submit_state")
            != "PRE_SUBMIT_READY_NON_EXECUTABLE"
            or pre_submit_record.get("authorization_source") != "HUMAN_CONFIRMATION"
            or not actual_record_hash
            or not hmac.compare_digest(
                actual_record_hash, pre_submit_record_hash(record_material)
            )
            or not protected
        ):
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_ARTIFACTS_INVALID")
        bindings = (
            (pre_submit_record.get("source_candidate_reference"), candidate.candidate_reference),
            (pre_submit_record.get("source_confirmation_intent_id"), confirmation.intent_id),
            (protected.get("candidate_reference"), candidate.candidate_reference),
            (protected.get("candidate_provenance_hash"), candidate.provenance_hash),
            (protected.get("structured_order_hash"), candidate.structured_order_hash),
            (protected.get("confirmation_intent_id"), confirmation.intent_id),
            (protected.get("authorization_binding_hash"), confirmation.confirmation_binding_hash),
            (protected.get("account_fingerprint_hash"), hash_text(fingerprint)),
            (protected.get("symbol"), candidate.symbol_reference),
            (protected.get("broker_symbol"), candidate.broker_symbol_reference),
            (protected.get("side"), candidate.side),
            (protected.get("order_type"), candidate.order_type),
            (protected.get("action"), candidate.action),
            (protected.get("entry_price"), candidate.entry_price),
            (protected.get("stop_loss"), candidate.stop_loss),
            (protected.get("take_profit"), candidate.take_profit),
            (protected.get("volume"), candidate.proposed_volume),
        )
        if any(left != right for left, right in bindings):
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_BINDING_MISMATCH")
        if (
            confirmation.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW"
            or confirmation.human_confirmation_state != "CONFIRMED_PROPOSAL_WORKFLOW"
            or confirmation.operator_action != "CONFIRM"
            or candidate.action != "MARKET"
            or candidate.order_type not in {"BUY", "SELL"}
        ):
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_AUTHORITY_INVALID")
        try:
            expires_at = datetime.fromisoformat(str(protected.get("expires_at", "")))
            if expires_at.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_EXPIRED") from exc
        if expires_at.astimezone(timezone.utc) <= evaluated_at:
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_EXPIRED")
        protected_hash = hash_text(
            json.dumps(protected, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        )
        if not hmac.compare_digest(
            protected_hash, str(pre_submit_record.get("artifact_hash", ""))
        ):
            raise ValueError("HUMAN_CANDIDATE_EXECUTION_ARTIFACTS_INVALID")
        idempotency_key = hash_text(
            "human-confirmed-candidate/v1|"
            + candidate.candidate_reference
            + "|"
            + confirmation.intent_id
            + "|"
            + str(pre_submit_record.get("pre_submit_report_id", ""))
            + "|"
            + protected_hash
        )
        parameters = ApprovedSemanticExecutionParameters.from_mapping(
            {
                "action": "MARKET",
                "symbol": candidate.broker_symbol_reference,
                "volume": candidate.proposed_volume,
                "order_type": candidate.order_type,
                "price": candidate.entry_price or "0",
                "stop_loss": candidate.stop_loss,
                "take_profit": candidate.take_profit,
                "deviation": 0,
                "magic": 0,
                "comment": "human-confirmed",
                "idempotency": idempotency_key,
                "audit": confirmation.intent_id,
            },
            approval_artifact_ref=confirmation.intent_id,
            lock_artifact_ref=str(pre_submit_record.get("pre_submit_report_id", "")),
            source_artifact_ref=candidate.candidate_reference,
            approved_at=confirmation.confirmation_timestamp,
            locked_at=str(pre_submit_record.get("created_at", "")),
        )
        semantic_hash = parameters.canonical_values_hash
        confirmation_reference = hash_text(
            f"{phrase}|{idempotency_key}|{fingerprint}"
        )
        return cls(
            request_version="controlled-mt5-execution/v1",
            approved_semantic_parameters=parameters.to_protected_dict(),
            canonical_semantic_hash=semantic_hash,
            approval_value_hash=semantic_hash,
            lock_value_hash=semantic_hash,
            approval_reference=parameters.approval_artifact_ref,
            lock_reference=parameters.lock_artifact_ref,
            source_artifact_reference=parameters.source_artifact_ref,
            approval_timestamp=parameters.approved_at,
            lock_timestamp=parameters.locked_at,
            human_confirmation_reference=confirmation_reference,
            human_confirmation_phrase=phrase,
            pre_submit_validation_reference=str(
                pre_submit_record.get("pre_submit_report_id", "")
            ),
            pre_submit_validation_valid=True,
            idempotency_key=idempotency_key,
            expected_account_context_fingerprint=fingerprint,
            execution_permission_requested=True,
        )

    @classmethod
    def from_pending_artifacts(
        cls,
        contract: ControlledPendingOrderContract,
        contract_validation: ControlledPendingOrderValidation,
        request_draft: PendingOrderDryRunRequestDraft,
        pre_submit_report,
        *,
        expected_account_context_fingerprint: str,
        human_confirmation_phrase: str,
        execution_permission_requested: bool = True,
        validation_only: bool = False,
        now: datetime | None = None,
    ) -> "MT5ControlledExecutionRequest":
        from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
            PENDING_ORDER_CONTRACT_SCHEMA_VERSION,
            SUPPORTED_PENDING_ORDER_TYPES,
        )

        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
        evaluated_at = evaluated_at.astimezone(timezone.utc)
        if (
            contract.schema_version != PENDING_ORDER_CONTRACT_SCHEMA_VERSION
            or contract.validation_status != "VALID"
            or contract.blocker_codes
            or not contract.integrity_valid()
        ):
            raise ValueError("PENDING_CONTRACT_INTEGRITY_INVALID")
        if (
            contract_validation.valid is not True
            or contract_validation.status != "VALID"
            or contract_validation.blockers
        ):
            raise ValueError("PENDING_CONTRACT_APPROVAL_INVALID")
        if request_draft is None or not request_draft.integrity_valid(contract):
            raise ValueError("PENDING_DRY_RUN_BINDING_INVALID")
        if contract.action != "PENDING" or contract.order_type not in SUPPORTED_PENDING_ORDER_TYPES:
            raise ValueError("PENDING_ORDER_TYPE_INVALID")
        if not validation_only:
            if contract.expiration_policy != "GTC":
                raise ValueError("PENDING_EXPIRATION_POLICY_REQUIRED")
            if (
                not contract.proposed_volume
                or not contract.comment
                or not contract.audit
                or contract.deviation < 0
                or contract.deviation > 1000
                or contract.magic < 0
                or contract.magic > 2_147_483_647
            ):
                raise ValueError("PENDING_EXECUTION_VALUES_INCOMPLETE")
        required_references = (
            contract.candidate_reference,
            contract.candidate_provenance_hash,
            contract.market_snapshot_reference,
            contract.market_snapshot_provenance_hash,
            contract.symbol_metadata_reference,
            contract.symbol_metadata_hash,
            contract.account_context_reference,
            contract.source_review_artifact_id,
            contract.source_confirmation_intent_id,
            contract.confirmation_artifact_hash,
            contract.structured_order_hash,
        )
        if any(not value for value in required_references) or not contract.source_refs:
            raise ValueError("PENDING_APPROVAL_REFERENCES_INCOMPLETE")
        try:
            generated_at = datetime.fromisoformat(contract.generated_at)
            expires_at = datetime.fromisoformat(contract.expires_at)
            if generated_at.tzinfo is None or expires_at.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise ValueError("PENDING_CONTRACT_TIMESTAMP_INVALID") from exc
        generated_at = generated_at.astimezone(timezone.utc)
        expires_at = expires_at.astimezone(timezone.utc)
        if (
            generated_at > evaluated_at
            or (evaluated_at - generated_at).total_seconds() > 300
            or expires_at <= evaluated_at
        ):
            raise ValueError("PENDING_CONTRACT_EXPIRED")
        if not validation_only and (
            getattr(pre_submit_report, "valid", False) is not True
            or getattr(pre_submit_report, "controlled_demo_integration_workflow_allowed", False) is not True
        ):
            raise ValueError("PRE_SUBMIT_VALIDATION_REQUIRED")
        fingerprint = str(expected_account_context_fingerprint or "").strip().lower()
        phrase = str(human_confirmation_phrase or "").strip()
        if (
            len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not phrase
            or (validation_only and execution_permission_requested is not False)
            or (not validation_only and execution_permission_requested is not True)
        ):
            raise ValueError("PENDING_EXECUTION_REQUEST_INCOMPLETE")
        expected_account_reference = "account_context_" + hash_text(
            "pending-dry-run|" + fingerprint
        )[:24]
        if not hmac.compare_digest(contract.account_context_reference, expected_account_reference):
            raise ValueError("ACCOUNT_CONTEXT_MISMATCH")
        confirmation_reference = hash_text(
            f"{phrase}|{contract.idempotency_key}|{fingerprint}"
        )
        return cls(
            request_version=PENDING_EXECUTION_REQUEST_VERSION,
            approved_semantic_parameters=contract.to_protected_dict(),
            canonical_semantic_hash=contract.canonical_integrity_hash,
            approval_value_hash=contract.canonical_integrity_hash,
            lock_value_hash=contract.canonical_integrity_hash,
            approval_reference=contract.source_confirmation_intent_id,
            lock_reference=contract.contract_reference,
            source_artifact_reference=contract.candidate_reference,
            approval_timestamp=contract.generated_at,
            lock_timestamp=contract.generated_at,
            human_confirmation_reference=confirmation_reference,
            human_confirmation_phrase=phrase,
            pre_submit_validation_reference=(
                "" if validation_only else getattr(pre_submit_report, "report_id", "")
            ),
            pre_submit_validation_valid=not validation_only,
            idempotency_key=contract.idempotency_key,
            expected_account_context_fingerprint=fingerprint,
            execution_permission_requested=execution_permission_requested,
        )
    def as_protected_dict(self) -> Dict[str, Any]:
        payload = {
            "request_version": self.request_version,
            "approved_semantic_parameters": dict(self.approved_semantic_parameters),
            "canonical_semantic_hash": self.canonical_semantic_hash,
            "approval_value_hash": self.approval_value_hash,
            "lock_value_hash": self.lock_value_hash,
            "approval_reference": self.approval_reference,
            "lock_reference": self.lock_reference,
            "source_artifact_reference": self.source_artifact_reference,
            "approval_timestamp": self.approval_timestamp,
            "lock_timestamp": self.lock_timestamp,
            "human_confirmation_reference": self.human_confirmation_reference,
            "human_confirmation_phrase": self.human_confirmation_phrase,
            "pre_submit_validation_reference": self.pre_submit_validation_reference,
            "pre_submit_validation_valid": self.pre_submit_validation_valid,
            "idempotency_key": self.idempotency_key,
            "expected_account_context_fingerprint": self.expected_account_context_fingerprint,
            "execution_permission_requested": self.execution_permission_requested,
        }
        if self.authorization_source == "STANDING_MANDATE":
            payload.update(
                authorization_source=self.authorization_source,
                authorization_reference=self.authorization_reference,
            )
        return payload

    def as_redacted_dict(self) -> Dict[str, Any]:
        return {
            "request_version": self.request_version,
            "canonical_semantic_hash": self.canonical_semantic_hash,
            "approval_reference": self.approval_reference,
            "lock_reference": self.lock_reference,
            "source_artifact_reference": self.source_artifact_reference,
            "human_confirmation_reference": self.human_confirmation_reference,
            "pre_submit_validation_reference": self.pre_submit_validation_reference,
            "expected_account_context_fingerprint": self.expected_account_context_fingerprint,
            "semantic_values_redacted": True,
            "metadata_redacted": True,
        }


@dataclass(frozen=True)
class MT5ControlledExecutionReceipt:
    status: str
    idempotency_status: str
    order_sent: bool
    ticket_present: bool
    deal_present: bool
    reason: str = ""
    ticket: Any = None
    deal: Any = None
    metadata_redacted: bool = True

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MT5ControlledExecutionReceipt":
        return cls(
            status=str(payload.get("status", "BLOCKED")),
            idempotency_status=str(payload.get("idempotency_status", "UNKNOWN")),
            order_sent=payload.get("order_sent") is True,
            ticket_present=payload.get("ticket_present") is True,
            deal_present=payload.get("deal_present") is True,
            reason=str(payload.get("reason", "")),
            ticket=None,
            deal=None,
            metadata_redacted=True,
        )
