from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.common import dedupe


@dataclass
class LiveExecutionApprovalRequirement:
    requirement_id: str
    title: str
    required: bool
    satisfied: bool
    blocking: bool
    approver_type: str
    evidence_required: str
    expiry_seconds: int
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "title": self.title,
            "required": bool(self.required),
            "satisfied": bool(self.satisfied),
            "blocking": bool(self.blocking),
            "approver_type": self.approver_type,
            "evidence_required": self.evidence_required,
            "expiry_seconds": int(self.expiry_seconds),
            "source_refs": dedupe(self.source_refs),
        }
