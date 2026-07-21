from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_parameter_value_proposal.models import (
    ControlledLiveParameterValueProposal,
    ControlledLiveParameterValueProposalJournalRecord,
    ControlledLiveParameterValueProposalValidationReport,
)


@dataclass
class ControlledLiveParameterValueProposalCard:
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


class ControlledLiveParameterValueProposalFormatter:
    def to_card(
        self,
        proposal: ControlledLiveParameterValueProposal,
        validation_report: ControlledLiveParameterValueProposalValidationReport | None = None,
        journal_record: ControlledLiveParameterValueProposalJournalRecord | None = None,
    ) -> ControlledLiveParameterValueProposalCard:
        return ControlledLiveParameterValueProposalCard(
            title="Controlled Live Parameter Value Proposal",
            status=proposal.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "human_value_approval_allowed": bool(proposal.human_value_approval_allowed),
                "value_slots_count": len(proposal.value_slots),
                "review_required_slots_count": sum(1 for slot in proposal.value_slots if slot.human_review_required),
                "approved_slots_count": 0,
                "rejected_slots_count": 0,
                "missing_slots_count": len(proposal.missing_value_slot_types),
                "value_lock_required": True,
                "human_review_required": True,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "source_refs_count": len(proposal.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(proposal.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(proposal.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        proposal: ControlledLiveParameterValueProposal,
        validation_report: ControlledLiveParameterValueProposalValidationReport | None = None,
        journal_record: ControlledLiveParameterValueProposalJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Controlled Live Parameter Value Proposal",
                f"- value_proposal_status: {proposal.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- human_value_approval_allowed: {str(proposal.human_value_approval_allowed).lower()}",
                f"- value_slots_count: {len(proposal.value_slots)}",
                f"- review_required_slots_count: {sum(1 for slot in proposal.value_slots if slot.human_review_required)}",
                "- approved_slots_count: 0",
                "- rejected_slots_count: 0",
                f"- missing_slots_count: {len(proposal.missing_value_slot_types)}",
                "- value_lock_required: true",
                "- human_review_required: true",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- order_contract_ready: false",
                f"- source_refs_count: {len(proposal.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
