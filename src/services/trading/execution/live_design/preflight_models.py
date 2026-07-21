from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.common import dedupe


@dataclass
class LiveExecutionPreflightCheck:
    check_id: str
    title: str
    category: str
    required: bool
    current_status: str
    expected_status: str
    blocking: bool
    evidence_required: str
    failure_message: str
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "category": self.category,
            "required": bool(self.required),
            "current_status": self.current_status,
            "expected_status": self.expected_status,
            "blocking": bool(self.blocking),
            "evidence_required": self.evidence_required,
            "failure_message": self.failure_message,
            "source_refs": dedupe(self.source_refs),
        }
