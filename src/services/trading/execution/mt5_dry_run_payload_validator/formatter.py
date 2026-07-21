from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.mt5_dry_run_payload_validator.models import (
    MT5OrderRequestDryRunPayloadValidation,
    MT5OrderRequestDryRunPayloadValidationJournalRecord,
    MT5OrderRequestDryRunPayloadValidationReport,
)


@dataclass
class MT5OrderRequestDryRunPayloadValidationCard:
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


class MT5OrderRequestDryRunPayloadValidationFormatter:
    def to_card(
        self,
        validation: MT5OrderRequestDryRunPayloadValidation,
        report: MT5OrderRequestDryRunPayloadValidationReport,
        journal_record: MT5OrderRequestDryRunPayloadValidationJournalRecord | None = None,
    ) -> MT5OrderRequestDryRunPayloadValidationCard:
        return MT5OrderRequestDryRunPayloadValidationCard(
            title="MT5 Order Request Dry-Run Payload Validator",
            fields={
                "dry_run_payload_validation_status": validation.status,
                "validation_valid": report.valid,
                "mt5_request_draft_workflow_allowed": report.mt5_request_draft_workflow_allowed,
                "field_validations_count": report.field_validations_count,
                "validated_fields_count": report.validated_fields_count,
                "missing_fields_count": report.missing_fields_count,
                "invalid_fields_count": report.invalid_fields_count,
                "mt5_payload_created": False,
                "mt5_request_dict_created": False,
                "mt5_constants_used": False,
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
        validation: MT5OrderRequestDryRunPayloadValidation,
        report: MT5OrderRequestDryRunPayloadValidationReport,
        journal_record: MT5OrderRequestDryRunPayloadValidationJournalRecord | None = None,
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
