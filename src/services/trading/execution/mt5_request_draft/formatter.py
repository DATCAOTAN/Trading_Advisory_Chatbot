from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.mt5_request_draft.models import (
    MT5RequestDraftBoundary,
    MT5RequestDraftJournalRecord,
    MT5RequestDraftValidationReport,
)


@dataclass
class MT5RequestDraftCard:
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


class MT5RequestDraftFormatter:
    def to_card(
        self,
        validation: MT5RequestDraftBoundary,
        report: MT5RequestDraftValidationReport,
        journal_record: MT5RequestDraftJournalRecord | None = None,
    ) -> MT5RequestDraftCard:
        return MT5RequestDraftCard(
            title="MT5 Request Draft Boundary",
            fields={
                "request_draft_status": validation.status,
                "validation_valid": report.valid,
                "mt5_request_draft_final_approval_workflow_allowed": (
                    report.mt5_request_draft_final_approval_workflow_allowed
                ),
                "draft_fields_count": report.draft_fields_count,
                "created_draft_fields_count": report.created_draft_fields_count,
                "missing_draft_fields_count": report.missing_draft_fields_count,
                "invalid_draft_fields_count": report.invalid_draft_fields_count,
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
                "source_refs_count": len(validation.source_refs),
            },
            blockers=list(report.blockers or validation.blockers or []),
            warnings=list(report.warnings or validation.warnings or []),
            journal_record_id=journal_record.journal_record_id if journal_record else "",
        )

    def to_markdown_summary(
        self,
        validation: MT5RequestDraftBoundary,
        report: MT5RequestDraftValidationReport,
        journal_record: MT5RequestDraftJournalRecord | None = None,
    ) -> str:
        card = self.to_card(validation, report, journal_record)
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
