from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


EXECUTION_ADAPTER_TYPES = {"SIMULATED", "RESERVED_MT5_LIVE", "DISABLED", "UNKNOWN"}
EXECUTION_ADAPTER_STATUSES = {"OK", "DISABLED", "UNAVAILABLE", "MISCONFIGURED", "BLOCKED", "UNKNOWN"}
SIMULATED_ORDER_CONTRACT_STATUSES = {"CREATED", "BLOCKED", "INVALID", "EXPIRED", "DUPLICATE", "UNKNOWN"}
SIMULATED_JOURNAL_EVENT_TYPES = {
    "SIMULATED_CONTRACT_CREATED",
    "SIMULATED_CONTRACT_BLOCKED",
    "SIMULATED_RECEIPT_CREATED",
    "SIMULATED_RECEIPT_REJECTED",
    "SIMULATED_DUPLICATE_DETECTED",
    "JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class ExecutionAdapterHealth:
    adapter_type: str
    status: str
    message: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    live_execution_supported: bool = False
    simulated_only: bool = True
    details_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "adapter_type": self.adapter_type if self.adapter_type in EXECUTION_ADAPTER_TYPES else "UNKNOWN",
            "status": self.status if self.status in EXECUTION_ADAPTER_STATUSES else "UNKNOWN",
            "message": self.message,
            "checked_at": self.checked_at,
            "live_execution_supported": False,
            "simulated_only": True,
            "details_redacted": dict(self.details_redacted),
        }


@dataclass
class SimulatedOrderContract:
    contract_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    adapter_type: str = "SIMULATED"
    contract_status: str = "UNKNOWN"
    simulated_only: bool = True
    executable: bool = False
    source_draft_id: str = ""
    source_draft_status: str = ""
    source_intent_id: str = ""
    source_review_artifact_id: str = ""
    source_dry_run_receipt_id: str = ""
    source_execution_journal_record_id: str = ""
    source_proposal_draft_journal_record_id: str = ""
    artifact_hash: str = ""
    idempotency_key: str = ""
    non_executable_proposal: bool = True
    readiness_action: str = ""
    review_status: str = ""
    proposal_boundary_status: str = ""
    draft_status: str = ""
    adapter_contract_version: str = "simulated_contract_v1"
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "adapter_type": "SIMULATED",
            "contract_status": self.contract_status
            if self.contract_status in SIMULATED_ORDER_CONTRACT_STATUSES
            else "UNKNOWN",
            "simulated_only": True,
            "executable": False,
            "source_draft_id": self.source_draft_id,
            "source_draft_status": self.source_draft_status,
            "source_intent_id": self.source_intent_id,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_dry_run_receipt_id": self.source_dry_run_receipt_id,
            "source_execution_journal_record_id": self.source_execution_journal_record_id,
            "source_proposal_draft_journal_record_id": self.source_proposal_draft_journal_record_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "non_executable_proposal": True,
            "readiness_action": self.readiness_action,
            "review_status": self.review_status,
            "proposal_boundary_status": self.proposal_boundary_status,
            "draft_status": self.draft_status,
            "adapter_contract_version": self.adapter_contract_version,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "reasons": list(dict.fromkeys(self.reasons)),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class SimulatedExecutionReceipt:
    receipt_id: str
    created_at: str
    adapter_type: str
    contract_id: str
    contract_status: str
    simulated_only: bool = True
    executable: bool = False
    executed: bool = False
    accepted_by_adapter: bool = False
    provider_name: str = "simulated_execution_adapter"
    source_draft_id: str = ""
    source_contract_id: str = ""
    idempotency_key: str = ""
    artifact_hash: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    message: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "adapter_type": "SIMULATED",
            "contract_id": self.contract_id,
            "contract_status": self.contract_status,
            "simulated_only": True,
            "executable": False,
            "executed": False,
            "accepted_by_adapter": bool(self.accepted_by_adapter),
            "provider_name": self.provider_name,
            "source_draft_id": self.source_draft_id,
            "source_contract_id": self.source_contract_id,
            "idempotency_key": self.idempotency_key,
            "artifact_hash": self.artifact_hash,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "message": self.message,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class SimulatedExecutionJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    adapter_type: str
    contract_id: str
    receipt_id: str
    contract_status: str
    simulated_only: bool
    executable: bool
    executed: bool
    accepted_by_adapter: bool
    source_draft_id: str
    artifact_hash: str
    idempotency_key: str
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in SIMULATED_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "adapter_type": "SIMULATED",
            "contract_id": self.contract_id,
            "receipt_id": self.receipt_id,
            "contract_status": self.contract_status,
            "simulated_only": True,
            "executable": False,
            "executed": False,
            "accepted_by_adapter": bool(self.accepted_by_adapter),
            "source_draft_id": self.source_draft_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class SimulatedExecutionSummary:
    total_records: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    latest_record_at: str = ""
    latest_contract_id: str = ""
    latest_receipt_id: str = ""
    latest_contract_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_accepted": int(self.total_accepted),
            "total_rejected": int(self.total_rejected),
            "latest_record_at": self.latest_record_at,
            "latest_contract_id": self.latest_contract_id,
            "latest_receipt_id": self.latest_receipt_id,
            "latest_contract_status": self.latest_contract_status,
            "warnings": list(dict.fromkeys(self.warnings)),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
