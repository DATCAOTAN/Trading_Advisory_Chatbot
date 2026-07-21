from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_order_parameter_source.models import (
    LiveOrderParameterSourceBoundary,
    LiveOrderParameterSourceJournalRecord,
    LiveOrderParameterSourceValidationReport,
)


@dataclass
class LiveOrderParameterSourceBoundaryCard:
    title: str
    status: str
    fields: Dict[str, Any] = field(default_factory=dict)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status": self.status,
            "fields": dict(self.fields),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


class LiveOrderParameterSourceBoundaryFormatter:
    def to_card(
        self,
        boundary: LiveOrderParameterSourceBoundary,
        validation_report: LiveOrderParameterSourceValidationReport | None = None,
        journal_record: LiveOrderParameterSourceJournalRecord | None = None,
    ) -> LiveOrderParameterSourceBoundaryCard:
        return LiveOrderParameterSourceBoundaryCard(
            title="Live Order Parameter Source Boundary",
            status=boundary.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "human_reviewed_parameter_draft_allowed": bool(boundary.human_reviewed_parameter_draft_allowed),
                "source_candidates_count": len(boundary.source_candidates),
                "required_source_types": list(boundary.required_source_types),
                "missing_source_types": list(boundary.missing_source_types),
                "rejected_source_types": list(boundary.rejected_source_types),
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "resolved_parameter_values_present": False,
                "actual_order_values_present": False,
                "source_refs_count": len(boundary.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(boundary.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(boundary.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        boundary: LiveOrderParameterSourceBoundary,
        validation_report: LiveOrderParameterSourceValidationReport | None = None,
        journal_record: LiveOrderParameterSourceJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Live Order Parameter Source Boundary",
                f"- source_boundary_status: {boundary.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- human_reviewed_parameter_draft_allowed: {str(boundary.human_reviewed_parameter_draft_allowed).lower()}",
                f"- source_candidates_count: {len(boundary.source_candidates)}",
                f"- required_sources_count: {len(boundary.required_source_types)}",
                f"- missing_sources_count: {len(boundary.missing_source_types)}",
                f"- rejected_sources_count: {len(boundary.rejected_source_types)}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- resolved_parameter_values_present: false",
                "- actual_order_values_present: false",
                f"- source_refs_count: {len(boundary.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
