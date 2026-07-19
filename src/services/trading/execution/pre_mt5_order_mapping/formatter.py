from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.trading.execution.pre_mt5_order_mapping.models import (
    PreMT5OrderRequestMappingBoundary,
    PreMT5OrderRequestMappingJournalRecord,
    PreMT5OrderRequestMappingValidationReport,
)


@dataclass
class PreMT5OrderRequestMappingCard:
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


class PreMT5OrderRequestMappingFormatter:
    def to_card(
        self,
        boundary: PreMT5OrderRequestMappingBoundary,
        validation_report: PreMT5OrderRequestMappingValidationReport,
        journal_record: PreMT5OrderRequestMappingJournalRecord | None = None,
    ) -> PreMT5OrderRequestMappingCard:
        return PreMT5OrderRequestMappingCard(
            title="Pre-MT5 Order Request Mapping Boundary",
            fields={
                "pre_mt5_mapping_status": boundary.status,
                "validation_valid": validation_report.valid,
                "mt5_dry_run_payload_validation_workflow_allowed": (
                    validation_report.mt5_dry_run_payload_validation_workflow_allowed
                ),
                "mapping_slots_count": validation_report.mapping_slots_count,
                "mapped_slots_count": validation_report.mapped_slots_count,
                "missing_slots_count": validation_report.missing_slots_count,
                "invalid_slots_count": validation_report.invalid_slots_count,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "mt5_request_dict_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "order_request_mapping_allowed": False,
                "broker_mapping_created": False,
                "raw_values_stored": False,
                "executable_order_created": False,
                "source_refs_count": len(boundary.source_refs),
            },
            blockers=list(validation_report.blockers or boundary.blockers or []),
            warnings=list(validation_report.warnings or boundary.warnings or []),
            journal_record_id=journal_record.journal_record_id if journal_record else "",
        )

    def to_markdown_summary(
        self,
        boundary: PreMT5OrderRequestMappingBoundary,
        validation_report: PreMT5OrderRequestMappingValidationReport,
        journal_record: PreMT5OrderRequestMappingJournalRecord | None = None,
    ) -> str:
        card = self.to_card(boundary, validation_report, journal_record)
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
