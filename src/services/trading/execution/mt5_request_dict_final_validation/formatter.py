from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationJournalRecord,
    MT5RequestDictFinalValidationReport,
)


@dataclass
class MT5RequestDictFinalValidationCard:
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


class MT5RequestDictFinalValidationFormatter:
    def to_card(
        self,
        boundary: MT5RequestDictFinalValidationBoundary,
        report: MT5RequestDictFinalValidationReport,
        journal_record: MT5RequestDictFinalValidationJournalRecord | None = None,
    ) -> MT5RequestDictFinalValidationCard:
        return MT5RequestDictFinalValidationCard(
            title="MT5 Request Dict Final Validation",
            fields={
                "final_validation_status": boundary.status,
                "validation_valid": report.valid,
                "bridge_write_skeleton_check_allowed": report.bridge_write_skeleton_check_allowed,
                "validated_fields_count": report.validated_fields_count,
                "missing_fields_count": report.missing_fields_count,
                "invalid_fields_count": report.invalid_fields_count,
                "real_mt5_payload_created": False,
                "broker_submittable_request_dict_created": False,
                "mt5_constants_used": False,
                "broker_submission_created": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "order_sent": False,
                "hard_live_block_required": True,
            },
            blockers=list(report.blockers or boundary.blockers or []),
            warnings=list(report.warnings or boundary.warnings or []),
            journal_record_id=journal_record.journal_record_id if journal_record else "",
        )

    def to_markdown_summary(
        self,
        boundary: MT5RequestDictFinalValidationBoundary,
        report: MT5RequestDictFinalValidationReport,
        journal_record: MT5RequestDictFinalValidationJournalRecord | None = None,
    ) -> str:
        card = self.to_card(boundary, report, journal_record)
        lines = [f"**{card.title}**"]
        for key, value in card.fields.items():
            lines.append(f"- `{key}`: {str(value).lower() if isinstance(value, bool) else value}")
        if card.journal_record_id:
            lines.append(f"- `journal_record_id`: {card.journal_record_id}")
        if card.blockers:
            lines.append(f"- `blockers`: {', '.join(card.blockers)}")
        return "\n".join(lines)
