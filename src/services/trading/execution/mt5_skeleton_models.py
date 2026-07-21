from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


MT5_SKELETON_STATUSES = {"HARD_BLOCKED", "DISABLED", "RESERVED_ONLY", "MISCONFIGURED", "UNKNOWN"}
LIVE_EXECUTION_BLOCK_REASONS = {
    "HARD_LIVE_BLOCK_ENABLED",
    "LIVE_EXECUTION_DISABLED",
    "MT5_LIVE_ADAPTER_NOT_IMPLEMENTED",
    "ORDER_SEND_FORBIDDEN",
    "EXECUTABLE_ORDER_FORBIDDEN",
    "TRADE_SIDE_FORBIDDEN",
    "ORDER_PARAMETERS_FORBIDDEN",
    "INVALID_SOURCE_CONTRACT",
    "INVALID_SIMULATED_RECEIPT",
    "UNKNOWN",
}
LIVE_EXECUTION_BLOCK_JOURNAL_EVENT_TYPES = {
    "LIVE_EXECUTION_CAPABILITY_CHECKED",
    "LIVE_EXECUTION_BLOCKED",
    "LIVE_EXECUTION_BLOCK_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class LiveExecutionCapabilityReport:
    report_id: str
    created_at: str
    adapter_type: str = "RESERVED_MT5_LIVE"
    skeleton_status: str = "HARD_BLOCKED"
    live_execution_supported: bool = False
    live_execution_enabled: bool = False
    mt5_order_send_available: bool = False
    mt5_terminal_required: bool = True
    docker_side_mt5_import_allowed: bool = False
    hard_live_block_enabled: bool = True
    message: str = "MT5 live execution is reserved and hard-blocked."
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_contract_id: str = ""
    source_simulated_receipt_id: str = ""
    source_draft_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "adapter_type": "RESERVED_MT5_LIVE",
            "skeleton_status": self.skeleton_status
            if self.skeleton_status in MT5_SKELETON_STATUSES
            else "UNKNOWN",
            "live_execution_supported": False,
            "live_execution_enabled": False,
            "mt5_order_send_available": False,
            "mt5_terminal_required": bool(self.mt5_terminal_required),
            "docker_side_mt5_import_allowed": False,
            "hard_live_block_enabled": True,
            "message": self.message,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_contract_id": self.source_contract_id,
            "source_simulated_receipt_id": self.source_simulated_receipt_id,
            "source_draft_id": self.source_draft_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveExecutionBlockedReceipt:
    receipt_id: str
    created_at: str
    adapter_type: str = "RESERVED_MT5_LIVE"
    skeleton_status: str = "HARD_BLOCKED"
    blocked: bool = True
    executed: bool = False
    order_sent: bool = False
    live_execution_supported: bool = False
    hard_live_block_enabled: bool = True
    block_reason: str = "HARD_LIVE_BLOCK_ENABLED"
    message: str = "Live execution was hard-blocked before any order path."
    source_contract_id: str = ""
    source_simulated_receipt_id: str = ""
    source_simulated_journal_record_id: str = ""
    artifact_hash: str = ""
    idempotency_key: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "adapter_type": "RESERVED_MT5_LIVE",
            "skeleton_status": self.skeleton_status
            if self.skeleton_status in MT5_SKELETON_STATUSES
            else "UNKNOWN",
            "blocked": True,
            "executed": False,
            "order_sent": False,
            "live_execution_supported": False,
            "hard_live_block_enabled": True,
            "block_reason": self.block_reason
            if self.block_reason in LIVE_EXECUTION_BLOCK_REASONS
            else "UNKNOWN",
            "message": self.message,
            "source_contract_id": self.source_contract_id,
            "source_simulated_receipt_id": self.source_simulated_receipt_id,
            "source_simulated_journal_record_id": self.source_simulated_journal_record_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveExecutionBlockJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    adapter_type: str
    skeleton_status: str
    receipt_id: str
    blocked: bool
    executed: bool
    order_sent: bool
    live_execution_supported: bool
    hard_live_block_enabled: bool
    block_reason: str
    source_contract_id: str
    source_simulated_receipt_id: str
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
            "event_type": self.event_type
            if self.event_type in LIVE_EXECUTION_BLOCK_JOURNAL_EVENT_TYPES
            else "UNKNOWN",
            "adapter_type": "RESERVED_MT5_LIVE",
            "skeleton_status": self.skeleton_status
            if self.skeleton_status in MT5_SKELETON_STATUSES
            else "UNKNOWN",
            "receipt_id": self.receipt_id,
            "blocked": True,
            "executed": False,
            "order_sent": False,
            "live_execution_supported": False,
            "hard_live_block_enabled": True,
            "block_reason": self.block_reason
            if self.block_reason in LIVE_EXECUTION_BLOCK_REASONS
            else "UNKNOWN",
            "source_contract_id": self.source_contract_id,
            "source_simulated_receipt_id": self.source_simulated_receipt_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveExecutionBlockSummary:
    total_records: int = 0
    total_blocked: int = 0
    latest_record_at: str = ""
    latest_receipt_id: str = ""
    latest_block_reason: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_blocked": int(self.total_blocked),
            "latest_record_at": self.latest_record_at,
            "latest_receipt_id": self.latest_receipt_id,
            "latest_block_reason": self.latest_block_reason,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(items: List[Any]) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
