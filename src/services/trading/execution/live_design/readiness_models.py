from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.approval_models import LiveExecutionApprovalRequirement
from src.services.trading.execution.live_design.audit_models import LiveExecutionAuditRequirement
from src.services.trading.execution.live_design.common import clamp, dedupe
from src.services.trading.execution.live_design.failure_models import LiveExecutionFailureMode
from src.services.trading.execution.live_design.preflight_models import LiveExecutionPreflightCheck
from src.services.trading.execution.live_design.threat_models import LiveExecutionThreat


LIVE_EXECUTION_DESIGN_STATUSES = {
    "DESIGN_ONLY",
    "HARD_BLOCKED",
    "INCOMPLETE",
    "INVALID",
    "APPROVAL_REQUIRED",
    "UNKNOWN",
}


@dataclass
class LiveExecutionReadinessSpecReport:
    report_id: str
    created_at: str
    design_status: str = "DESIGN_ONLY"
    live_execution_allowed: bool = False
    hard_live_block_required: bool = True
    source_capability_report_id: str = ""
    source_blocked_receipt_id: str = ""
    source_contract_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    threats: List[LiveExecutionThreat] = field(default_factory=list)
    preflight_checks: List[LiveExecutionPreflightCheck] = field(default_factory=list)
    approval_requirements: List[LiveExecutionApprovalRequirement] = field(default_factory=list)
    failure_modes: List[LiveExecutionFailureMode] = field(default_factory=list)
    audit_requirements: List[LiveExecutionAuditRequirement] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    readiness_score: float = 0.0
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "design_status": self.design_status if self.design_status in LIVE_EXECUTION_DESIGN_STATUSES else "UNKNOWN",
            "live_execution_allowed": False,
            "hard_live_block_required": True,
            "source_capability_report_id": self.source_capability_report_id,
            "source_blocked_receipt_id": self.source_blocked_receipt_id,
            "source_contract_id": self.source_contract_id,
            "source_refs": dedupe(self.source_refs),
            "threats": [item.as_dict() for item in self.threats],
            "preflight_checks": [item.as_dict() for item in self.preflight_checks],
            "approval_requirements": [item.as_dict() for item in self.approval_requirements],
            "failure_modes": [item.as_dict() for item in self.failure_modes],
            "audit_requirements": [item.as_dict() for item in self.audit_requirements],
            "blockers": dedupe(self.blockers),
            "warnings": dedupe(self.warnings),
            "readiness_score": clamp(self.readiness_score),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveExecutionDesignReportRecord:
    journal_record_id: str
    created_at: str
    report_id: str
    design_status: str
    live_execution_allowed: bool
    hard_live_block_required: bool
    threats_count: int
    preflight_checks_count: int
    approval_requirements_count: int
    failure_modes_count: int
    audit_requirements_count: int
    readiness_score: float
    source_capability_report_id: str
    source_blocked_receipt_id: str
    source_contract_id: str
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "report_id": self.report_id,
            "design_status": self.design_status if self.design_status in LIVE_EXECUTION_DESIGN_STATUSES else "UNKNOWN",
            "live_execution_allowed": False,
            "hard_live_block_required": True,
            "threats_count": int(self.threats_count),
            "preflight_checks_count": int(self.preflight_checks_count),
            "approval_requirements_count": int(self.approval_requirements_count),
            "failure_modes_count": int(self.failure_modes_count),
            "audit_requirements_count": int(self.audit_requirements_count),
            "readiness_score": clamp(self.readiness_score),
            "source_capability_report_id": self.source_capability_report_id,
            "source_blocked_receipt_id": self.source_blocked_receipt_id,
            "source_contract_id": self.source_contract_id,
            "source_refs": dedupe(self.source_refs),
            "blockers": dedupe(self.blockers),
            "warnings": dedupe(self.warnings),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveExecutionDesignReportSummary:
    total_records: int = 0
    latest_record_at: str = ""
    latest_report_id: str = ""
    latest_design_status: str = ""
    total_design_only: int = 0
    total_invalid: int = 0
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "latest_record_at": self.latest_record_at,
            "latest_report_id": self.latest_report_id,
            "latest_design_status": self.latest_design_status,
            "total_design_only": int(self.total_design_only),
            "total_invalid": int(self.total_invalid),
            "warnings": dedupe(self.warnings),
        }
