from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.common import dedupe


@dataclass
class LiveExecutionFailureMode:
    failure_mode_id: str
    category: str
    severity: str
    title: str
    description: str
    detection_method: str
    required_response: str
    rollback_or_recovery: str
    audit_requirement: str
    blocking: bool
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "failure_mode_id": self.failure_mode_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "detection_method": self.detection_method,
            "required_response": self.required_response,
            "rollback_or_recovery": self.rollback_or_recovery,
            "audit_requirement": self.audit_requirement,
            "blocking": bool(self.blocking),
            "source_refs": dedupe(self.source_refs),
        }
