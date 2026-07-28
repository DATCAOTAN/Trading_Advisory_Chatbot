from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


MT5_LIVE_ADAPTER_DISABLED_STATUSES = {
    "NOT_REQUESTED",
    "DISABLED_READY",
    "BRIDGE_SKELETON_REACHABLE",
    "BLOCKED_BY_DISABLED_ADAPTER",
    "BLOCKED_BY_KILL_SWITCH",
    "BLOCKED_BY_IDEMPOTENCY",
    "BLOCKED_BY_CONFIG",
    "INVALID",
    "UNKNOWN",
}
MT5_PRE_SUBMIT_GATE_STATUSES = {
    "NOT_REQUESTED",
    "PASSED_DISABLED_PRE_SUBMIT_CHECK",
    "READY_FOR_CONTROLLED_DEMO_INTEGRATION",
    "PRE_SUBMIT_READY_NON_EXECUTABLE",
    "BLOCKED",
    "INVALID",
    "DUPLICATE",
    "UNKNOWN",
}
MT5_KILL_SWITCH_STATES = {"ENGAGED", "DISENGAGED_FOR_FUTURE_DEMO_ONLY", "UNKNOWN"}
MT5_IDEMPOTENCY_STATUSES = {"CHECK_REGISTERED", "DUPLICATE_BLOCKED", "MISSING_KEY", "INVALID", "UNKNOWN"}
MT5_PRE_SUBMIT_BLOCK_REASONS = {
    "MISSING_FINAL_VALIDATION",
    "FINAL_VALIDATION_NOT_VALID",
    "BRIDGE_WRITE_SKELETON_NOT_ALLOWED",
    "BRIDGE_WRITE_SKELETON_UNREACHABLE",
    "BRIDGE_WRITE_SKELETON_NOT_BLOCKED",
    "LIVE_ADAPTER_DISABLED",
    "KILL_SWITCH_ENGAGED",
    "IDEMPOTENCY_DUPLICATE",
    "IDEMPOTENCY_MISSING",
    "ORDER_SEND_NOT_ALLOWED",
    "LIVE_EXECUTION_DISABLED",
    "EXECUTION_DISABLED",
    "REAL_MT5_PAYLOAD_NOT_ALLOWED",
    "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED",
    "MT5_CONSTANT_NOT_ALLOWED",
    "BROKER_SUBMISSION_NOT_ALLOWED",
    "EXECUTABLE_ORDER_NOT_ALLOWED",
    "TICKET_DEAL_NOT_ALLOWED",
    "FORBIDDEN_EXECUTION_CALL",
    "INVALID_INPUT",
    "UNKNOWN",
}


@dataclass
class MT5KillSwitchCheck:
    check_id: str
    created_at: str
    state: str
    engaged: bool
    source: str
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "created_at": self.created_at,
            "state": self.state if self.state in MT5_KILL_SWITCH_STATES else "UNKNOWN",
            "engaged": bool(self.engaged),
            "source": self.source,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class MT5IdempotencyCheck:
    check_id: str
    created_at: str
    idempotency_key: str
    status: str
    duplicate: bool
    registered_for_check_only: bool
    live_execution_reservation_created: bool
    order_send_reservation_created: bool
    expires_at: str
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "created_at": self.created_at,
            "idempotency_key_hash": hash_text(self.idempotency_key),
            "status": self.status if self.status in MT5_IDEMPOTENCY_STATUSES else "UNKNOWN",
            "duplicate": bool(self.duplicate),
            "registered_for_check_only": bool(self.registered_for_check_only),
            "live_execution_reservation_created": False,
            "order_send_reservation_created": False,
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class MT5LiveAdapterDisabledReceipt:
    receipt_id: str
    created_at: str
    adapter_status: str
    bridge_check_reachable: bool
    bridge_check_status: str
    bridge_endpoint: str
    adapter_enabled: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    order_sent: bool = False
    ticket: Any = None
    deal: Any = None
    hard_live_block_required: bool = True
    metadata_redacted: bool = True
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "adapter_status": self.adapter_status if self.adapter_status in MT5_LIVE_ADAPTER_DISABLED_STATUSES else "UNKNOWN",
            "bridge_check_reachable": bool(self.bridge_check_reachable),
            "bridge_check_status": self.bridge_check_status,
            "bridge_endpoint": self.bridge_endpoint,
            "adapter_enabled": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "ticket": None,
            "deal": None,
            "hard_live_block_required": True,
            "metadata_redacted": True,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "latency_ms": float(self.latency_ms or 0.0),
        }


@dataclass
class MT5PreSubmitGateReport:
    report_id: str
    created_at: str
    status: str
    valid: bool
    controlled_demo_integration_workflow_allowed: bool
    live_submission_allowed: bool
    source_final_validation_id: str
    source_final_validation_report_id: str
    source_bridge_skeleton_check_id: str
    source_kill_switch_check_id: str
    source_idempotency_check_id: str
    adapter_receipt_id: str
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    order_sent: bool = False
    ticket: Any = None
    deal: Any = None
    hard_live_block_required: bool = True
    kill_switch_engaged: bool = True
    idempotency_status: str = "UNKNOWN"
    bridge_write_skeleton_reachable: bool = False
    bridge_write_skeleton_status: str = "UNKNOWN"
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    approval_integrity_valid: bool = False
    final_validation_valid: bool = False
    pre_submit_ready: bool = False
    submission_disabled: bool = True
    source_candidate_reference: str = ""
    source_confirmation_intent_id: str = ""
    terminal_capability_reference: str = ""
    lifecycle_reference: str = ""
    reconciliation_reference: str = ""
    intent_hash: str = ""
    idempotency_key_hash: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "status": self.status if self.status in MT5_PRE_SUBMIT_GATE_STATUSES else "UNKNOWN",
            "valid": bool(self.valid),
            "controlled_demo_integration_workflow_allowed": bool(self.controlled_demo_integration_workflow_allowed),
            "live_submission_allowed": False,
            "source_final_validation_id": self.source_final_validation_id,
            "source_final_validation_report_id": self.source_final_validation_report_id,
            "source_bridge_skeleton_check_id": self.source_bridge_skeleton_check_id,
            "source_kill_switch_check_id": self.source_kill_switch_check_id,
            "source_idempotency_check_id": self.source_idempotency_check_id,
            "adapter_receipt_id": self.adapter_receipt_id,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "ticket": None,
            "deal": None,
            "hard_live_block_required": True,
            "kill_switch_engaged": bool(self.kill_switch_engaged),
            "idempotency_status": self.idempotency_status,
            "bridge_write_skeleton_reachable": bool(self.bridge_write_skeleton_reachable),
            "bridge_write_skeleton_status": self.bridge_write_skeleton_status,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars or 0),
            "approval_integrity_valid": bool(self.approval_integrity_valid),
            "final_validation_valid": bool(self.final_validation_valid),
            "pre_submit_ready": bool(self.pre_submit_ready),
            "submission_disabled": True,
            "source_candidate_reference": self.source_candidate_reference,
            "source_confirmation_intent_id": self.source_confirmation_intent_id,
            "terminal_capability_reference": self.terminal_capability_reference,
            "lifecycle_reference": self.lifecycle_reference,
            "reconciliation_reference": self.reconciliation_reference,
            "intent_hash": self.intent_hash,
            "idempotency_key_hash": self.idempotency_key_hash,
        }


@dataclass
class MT5PreSubmitJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    pre_submit_report_id: str
    adapter_receipt_id: str
    status: str
    valid: bool
    controlled_demo_integration_workflow_allowed: bool
    live_submission_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    order_sent: bool
    ticket: Any
    deal: Any
    hard_live_block_required: bool
    kill_switch_engaged: bool
    idempotency_status: str
    bridge_write_skeleton_reachable: bool
    bridge_write_skeleton_status: str
    source_final_validation_id: str
    artifact_hash: str
    idempotency_key_hash: str
    payload_size_chars: int
    metadata_redacted: bool = True
    source_candidate_reference: str = ""
    source_confirmation_intent_id: str = ""
    approval_integrity_hash: str = ""
    pre_submit_state: str = ""
    protected_intent: Dict[str, Any] = field(default_factory=dict, repr=False)
    record_hash: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type,
            "pre_submit_report_id": self.pre_submit_report_id,
            "adapter_receipt_id": self.adapter_receipt_id,
            "status": self.status,
            "valid": bool(self.valid),
            "controlled_demo_integration_workflow_allowed": bool(self.controlled_demo_integration_workflow_allowed),
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
            "ticket": None,
            "deal": None,
            "hard_live_block_required": True,
            "kill_switch_engaged": bool(self.kill_switch_engaged),
            "idempotency_status": self.idempotency_status,
            "bridge_write_skeleton_reachable": bool(self.bridge_write_skeleton_reachable),
            "bridge_write_skeleton_status": self.bridge_write_skeleton_status,
            "source_final_validation_id": self.source_final_validation_id,
            "artifact_hash": self.artifact_hash,
            "idempotency_key_hash": self.idempotency_key_hash,
            "payload_size_chars": int(self.payload_size_chars or 0),
            "metadata_redacted": True,
            "source_candidate_reference": self.source_candidate_reference,
            "source_confirmation_intent_id": self.source_confirmation_intent_id,
            "approval_integrity_hash": self.approval_integrity_hash,
            "pre_submit_state": self.pre_submit_state,
            "protected_intent": dict(self.protected_intent),
            "record_hash": self.record_hash,
        }


@dataclass
class MT5PreSubmitSummary:
    total_records: int
    total_valid: int
    total_blocked: int
    latest_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None and str(value) != ""))
