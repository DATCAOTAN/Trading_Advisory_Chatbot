from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_parameter_draft.models import (
    HumanReviewedLiveParameterDraft,
    HumanReviewedLiveParameterDraftJournalRecord,
    HumanReviewedLiveParameterDraftValidationReport,
)


@dataclass
class HumanReviewedLiveParameterDraftCard:
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


class HumanReviewedLiveParameterDraftFormatter:
    def to_card(
        self,
        draft: HumanReviewedLiveParameterDraft,
        validation_report: HumanReviewedLiveParameterDraftValidationReport | None = None,
        journal_record: HumanReviewedLiveParameterDraftJournalRecord | None = None,
    ) -> HumanReviewedLiveParameterDraftCard:
        requirements = sorted({req for slot in draft.slots for req in slot.review_requirements})
        return HumanReviewedLiveParameterDraftCard(
            title="Human-Reviewed Live Parameter Draft",
            status=draft.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "value_proposal_workflow_allowed": bool(draft.value_proposal_workflow_allowed),
                "slots_count": len(draft.slots),
                "unresolved_slots_count": len(draft.unresolved_slot_types),
                "resolved_slots_count": 0,
                "missing_slots_count": len(draft.missing_slot_types),
                "slot_type_labels": list(draft.required_slot_types),
                "review_requirement_labels": requirements,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "resolved_parameter_values_present": False,
                "actual_order_values_present": False,
                "source_refs_count": len(draft.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(draft.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(draft.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        draft: HumanReviewedLiveParameterDraft,
        validation_report: HumanReviewedLiveParameterDraftValidationReport | None = None,
        journal_record: HumanReviewedLiveParameterDraftJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Human-Reviewed Live Parameter Draft",
                f"- parameter_draft_status: {draft.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- value_proposal_workflow_allowed: {str(draft.value_proposal_workflow_allowed).lower()}",
                f"- slots_count: {len(draft.slots)}",
                f"- unresolved_slots_count: {len(draft.unresolved_slot_types)}",
                "- resolved_slots_count: 0",
                f"- missing_slots_count: {len(draft.missing_slot_types)}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- resolved_parameter_values_present: false",
                "- actual_order_values_present: false",
                f"- source_refs_count: {len(draft.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
