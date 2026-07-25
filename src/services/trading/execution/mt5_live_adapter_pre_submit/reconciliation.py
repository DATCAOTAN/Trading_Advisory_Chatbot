from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import hash_text


@dataclass(frozen=True)
class MT5ReconciliationRequest:
    request_version: str
    protected_execution_reference: str
    correlation_identity: str = field(repr=False)
    correlation_tag: str
    expected_account_context_fingerprint: str
    symbol_reference: str
    expected_order_type: str
    expected_volume: str = field(repr=False)
    submission_window_start: str
    submission_window_end: str
    canonical_semantic_hash: str
    approval_reference: str
    lock_reference: str
    source_artifact_reference: str

    @classmethod
    def from_controlled_request(
        cls,
        request: MT5ControlledExecutionRequest,
        *,
        submission_window_end: str | None = None,
    ) -> "MT5ReconciliationRequest":
        protected = dict(request.approved_semantic_parameters)
        if not {"symbol", "order_type"}.issubset(protected) or not (
            "volume" in protected or "proposed_volume" in protected
        ):
            raise ValueError("controlled request lacks reconciliation fields")
        terminal_symbol = protected.get("broker_symbol") or protected["symbol"]
        volume = protected.get("volume", protected.get("proposed_volume"))
        key_hash = hash_text(request.idempotency_key)
        identity = hash_text(
            "|".join(
                (
                    "controlled-execution-correlation/v1",
                    key_hash,
                    request.canonical_semantic_hash,
                    request.approval_reference,
                    request.lock_reference,
                    request.source_artifact_reference,
                )
            )
        )
        return cls(
            request_version="mt5-execution-reconciliation/v1",
            protected_execution_reference="mt5_execution_" + identity[:24],
            correlation_identity=identity,
            correlation_tag="mt5r" + identity[:12],
            expected_account_context_fingerprint=request.expected_account_context_fingerprint,
            symbol_reference=str(terminal_symbol),
            expected_order_type=str(protected["order_type"]).upper(),
            expected_volume=str(volume),
            submission_window_start=request.lock_timestamp,
            submission_window_end=submission_window_end or datetime.now(timezone.utc).isoformat(),
            canonical_semantic_hash=request.canonical_semantic_hash,
            approval_reference=request.approval_reference,
            lock_reference=request.lock_reference,
            source_artifact_reference=request.source_artifact_reference,
        )

    def as_protected_dict(self) -> Dict[str, Any]:
        return {
            "request_version": self.request_version,
            "protected_execution_reference": self.protected_execution_reference,
            "correlation_identity": self.correlation_identity,
            "correlation_tag": self.correlation_tag,
            "expected_account_context_fingerprint": self.expected_account_context_fingerprint,
            "symbol_reference": self.symbol_reference,
            "expected_order_type": self.expected_order_type,
            "expected_volume": self.expected_volume,
            "submission_window_start": self.submission_window_start,
            "submission_window_end": self.submission_window_end,
            "canonical_semantic_hash": self.canonical_semantic_hash,
            "approval_reference": self.approval_reference,
            "lock_reference": self.lock_reference,
            "source_artifact_reference": self.source_artifact_reference,
        }

    def as_redacted_dict(self) -> Dict[str, Any]:
        return {
            "request_version": self.request_version,
            "protected_execution_reference": self.protected_execution_reference,
            "correlation_tag": self.correlation_tag,
            "expected_account_context_fingerprint": self.expected_account_context_fingerprint,
            "canonical_semantic_hash": self.canonical_semantic_hash,
            "approval_reference": self.approval_reference,
            "lock_reference": self.lock_reference,
            "source_artifact_reference": self.source_artifact_reference,
            "submission_window_start": self.submission_window_start,
            "submission_window_end": self.submission_window_end,
            "execution_values_redacted": True,
            "metadata_redacted": True,
        }


@dataclass(frozen=True)
class MT5ReconciliationReceipt:
    status: str
    reconciliation_reference: str
    evidence_classification: str
    original_execution_state: str
    resulting_execution_state: str
    retry_decision: str
    order_reference_present: bool
    deal_reference_present: bool
    position_reference_present: bool
    reason: str = ""
    ticket: Any = None
    deal: Any = None
    position: Any = None
    live_submission_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    automatic_retry_allowed: bool = False
    order_sent: bool = False
    metadata_redacted: bool = True

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MT5ReconciliationReceipt":
        return cls(
            status=str(payload.get("status", "BLOCKED")),
            reconciliation_reference=str(payload.get("reconciliation_reference", "")),
            evidence_classification=str(payload.get("evidence_classification", "QUERY_FAILED")),
            original_execution_state=str(payload.get("original_execution_state", "UNKNOWN")),
            resulting_execution_state=str(payload.get("resulting_execution_state", "UNKNOWN")),
            retry_decision=str(payload.get("retry_decision", "RETRY_PROHIBITED")),
            order_reference_present=payload.get("order_reference_present") is True,
            deal_reference_present=payload.get("deal_reference_present") is True,
            position_reference_present=payload.get("position_reference_present") is True,
            reason=str(payload.get("reason", "")),
            ticket=None,
            deal=None,
            position=None,
            live_submission_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            automatic_retry_allowed=False,
            order_sent=False,
            metadata_redacted=True,
        )

    def to_safe_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "reconciliation_reference": self.reconciliation_reference,
                "evidence_classification": self.evidence_classification,
                "original_execution_state": self.original_execution_state,
                "resulting_execution_state": self.resulting_execution_state,
                "retry_decision": self.retry_decision,
                "order_reference_present": self.order_reference_present,
                "deal_reference_present": self.deal_reference_present,
                "position_reference_present": self.position_reference_present,
                "live_submission_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "automatic_retry_allowed": False,
                "order_sent": False,
                "metadata_redacted": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
