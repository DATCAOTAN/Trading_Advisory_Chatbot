from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_design.common import dedupe


@dataclass
class LiveExecutionAuditRequirement:
    audit_id: str
    title: str
    required: bool
    event_type: str
    fields_required: List[str] = field(default_factory=list)
    retention_policy: str = "append_only_jsonl_with_runtime_gitignore"
    redaction_required: bool = True
    blocking: bool = True
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "title": self.title,
            "required": bool(self.required),
            "event_type": self.event_type,
            "fields_required": dedupe(self.fields_required),
            "retention_policy": self.retention_policy,
            "redaction_required": bool(self.redaction_required),
            "blocking": bool(self.blocking),
            "source_refs": dedupe(self.source_refs),
        }
