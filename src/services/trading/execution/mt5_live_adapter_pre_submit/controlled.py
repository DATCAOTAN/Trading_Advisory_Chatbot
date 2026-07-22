from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import hash_text


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

    def as_protected_dict(self) -> Dict[str, Any]:
        return {
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
