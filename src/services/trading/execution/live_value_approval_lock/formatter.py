from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_value_approval_lock.models import (
    HumanValueApprovalLock,
    HumanValueApprovalLockJournalRecord,
    HumanValueApprovalLockValidationReport,
)


@dataclass
class HumanValueApprovalLockCard:
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


class HumanValueApprovalLockFormatter:
    def to_card(
        self,
        approval_lock: HumanValueApprovalLock,
        validation_report: HumanValueApprovalLockValidationReport | None = None,
        journal_record: HumanValueApprovalLockJournalRecord | None = None,
    ) -> HumanValueApprovalLockCard:
        return HumanValueApprovalLockCard(
            title="Human Value Approval and Lock Boundary",
            status=approval_lock.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "contract_parameterization_workflow_allowed": bool(
                    approval_lock.contract_parameterization_workflow_allowed
                ),
                "confirmation_phrase_valid": bool(approval_lock.confirmation_phrase_valid),
                "slot_locks_count": len(approval_lock.slot_locks),
                "locked_slots_count": len(approval_lock.locked_slot_types),
                "rejected_slots_count": 0,
                "missing_slots_count": len(approval_lock.missing_slot_lock_types),
                "value_lock_required": True,
                "human_review_required": True,
                "raw_values_stored": False,
                "executable_order_created": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "source_refs_count": len(approval_lock.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(approval_lock.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(approval_lock.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        approval_lock: HumanValueApprovalLock,
        validation_report: HumanValueApprovalLockValidationReport | None = None,
        journal_record: HumanValueApprovalLockJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Human Value Approval and Lock Boundary",
                f"- approval_lock_status: {approval_lock.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- contract_parameterization_workflow_allowed: {str(approval_lock.contract_parameterization_workflow_allowed).lower()}",
                f"- confirmation_phrase_valid: {str(approval_lock.confirmation_phrase_valid).lower()}",
                f"- slot_locks_count: {len(approval_lock.slot_locks)}",
                f"- locked_slots_count: {len(approval_lock.locked_slot_types)}",
                "- rejected_slots_count: 0",
                f"- missing_slots_count: {len(approval_lock.missing_slot_lock_types)}",
                "- value_lock_required: true",
                "- human_review_required: true",
                "- raw_values_stored: false",
                "- executable_order_created: false",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- order_contract_ready: false",
                f"- source_refs_count: {len(approval_lock.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
