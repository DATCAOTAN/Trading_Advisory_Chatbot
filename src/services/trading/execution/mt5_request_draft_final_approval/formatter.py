from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    MT5RequestDraftFinalApprovalBoundary,
    MT5RequestDraftFinalApprovalJournalRecord,
    MT5RequestDraftFinalApprovalValidationReport,
)


@dataclass
class MT5RequestDraftFinalApprovalCard:
    title: str
    fields: dict[str, Any]
    blockers: list[str]
    warnings: list[str]
    journal_record_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "fields": dict(self.fields),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "journal_record_id": self.journal_record_id,
        }


class MT5RequestDraftFinalApprovalFormatter:
    def to_card(
        self,
        approval: MT5RequestDraftFinalApprovalBoundary,
        report: MT5RequestDraftFinalApprovalValidationReport,
        journal_record: MT5RequestDraftFinalApprovalJournalRecord | None = None,
    ) -> MT5RequestDraftFinalApprovalCard:
        return MT5RequestDraftFinalApprovalCard(
            title="MT5 Request Draft Final Approval Boundary",
            fields={
                "final_approval_status": approval.status,
                "validation_valid": report.valid,
                "confirmation_phrase_valid": report.confirmation_phrase_valid,
                "mt5_request_dict_dry_run_builder_workflow_allowed": (
                    report.mt5_request_dict_dry_run_builder_workflow_allowed
                ),
                "approved_fields_count": report.approved_fields_count,
                "approved_fields_valid_count": report.approved_fields_valid_count,
                "missing_approved_fields_count": report.missing_approved_fields_count,
                "invalid_approved_fields_count": report.invalid_approved_fields_count,
                "mt5_payload_created": False,
                "mt5_request_dict_created": False,
                "mt5_constants_used": False,
                "broker_submission_created": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "order_request_mapping_allowed": False,
                "broker_mapping_created": False,
                "raw_values_stored": False,
                "executable_order_created": False,
                "source_refs_count": len(approval.source_refs),
            },
            blockers=list(report.blockers or approval.blockers or []),
            warnings=list(report.warnings or approval.warnings or []),
            journal_record_id=journal_record.journal_record_id if journal_record else "",
        )

    def to_markdown_summary(
        self,
        approval: MT5RequestDraftFinalApprovalBoundary,
        report: MT5RequestDraftFinalApprovalValidationReport,
        journal_record: MT5RequestDraftFinalApprovalJournalRecord | None = None,
    ) -> str:
        card = self.to_card(approval, report, journal_record)
        lines = [f"**{card.title}**"]
        for key, value in card.fields.items():
            if isinstance(value, bool):
                value = str(value).lower()
            lines.append(f"- `{key}`: {value}")
        if card.journal_record_id:
            lines.append(f"- `journal_record_id`: {card.journal_record_id}")
        if card.blockers:
            lines.append(f"- `blockers`: {', '.join(card.blockers)}")
        if card.warnings:
            lines.append(f"- `warnings`: {', '.join(card.warnings)}")
        return "\n".join(lines)
