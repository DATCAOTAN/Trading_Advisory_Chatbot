from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.live_order_contract_final_review.models import (
    LiveOrderContractFinalReview,
    LiveOrderContractFinalReviewJournalRecord,
    LiveOrderContractFinalReviewValidationReport,
)


@dataclass
class LiveOrderContractFinalReviewCard:
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


class LiveOrderContractFinalReviewFormatter:
    def to_card(
        self,
        final_review: LiveOrderContractFinalReview,
        validation_report: LiveOrderContractFinalReviewValidationReport,
        journal_record: LiveOrderContractFinalReviewJournalRecord | None = None,
    ) -> LiveOrderContractFinalReviewCard:
        return LiveOrderContractFinalReviewCard(
            title="Contract Parameter Validation and Final Human Review",
            fields={
                "final_review_status": final_review.status,
                "validation_valid": validation_report.valid,
                "pre_mt5_mapping_boundary_workflow_allowed": validation_report.pre_mt5_mapping_boundary_workflow_allowed,
                "confirmation_phrase_valid": validation_report.confirmation_phrase_valid,
                "slot_validations_count": validation_report.slot_validations_count,
                "passed_slot_validations_count": validation_report.passed_slot_validations_count,
                "blocked_slot_validations_count": validation_report.blocked_slot_validations_count,
                "missing_slot_validations_count": validation_report.missing_slot_validations_count,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "order_request_mapping_allowed": False,
                "broker_mapping_created": False,
                "raw_values_stored": False,
                "executable_order_created": False,
                "source_refs_count": len(final_review.source_refs),
            },
            blockers=list(validation_report.blockers or final_review.blockers or []),
            warnings=list(validation_report.warnings or final_review.warnings or []),
            journal_record_id=journal_record.journal_record_id if journal_record else "",
        )

    def to_markdown_summary(
        self,
        final_review: LiveOrderContractFinalReview,
        validation_report: LiveOrderContractFinalReviewValidationReport,
        journal_record: LiveOrderContractFinalReviewJournalRecord | None = None,
    ) -> str:
        card = self.to_card(final_review, validation_report, journal_record)
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
