from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_order_contract_parameterization.models import (
    LiveOrderContractParameterizationBoundary,
    LiveOrderContractParameterizationJournalRecord,
    LiveOrderContractParameterizationValidationReport,
)


@dataclass
class LiveOrderContractParameterizationCard:
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


class LiveOrderContractParameterizationFormatter:
    def to_card(
        self,
        parameterization: LiveOrderContractParameterizationBoundary,
        validation_report: LiveOrderContractParameterizationValidationReport | None = None,
        journal_record: LiveOrderContractParameterizationJournalRecord | None = None,
    ) -> LiveOrderContractParameterizationCard:
        return LiveOrderContractParameterizationCard(
            title="Live Order Contract Parameterization Boundary",
            status=parameterization.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "contract_validation_workflow_allowed": bool(parameterization.contract_validation_workflow_allowed),
                "contract_slots_count": len(parameterization.contract_slots),
                "parameterized_slots_count": len(parameterization.parameterized_slot_types),
                "missing_slots_count": len(parameterization.missing_contract_slot_types),
                "invalid_slots_count": len(parameterization.invalid_contract_slot_types),
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "order_contract_ready": False,
                "order_request_mapping_allowed": False,
                "raw_values_stored": False,
                "executable_order_created": False,
                "source_refs_count": len(parameterization.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(parameterization.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(parameterization.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        parameterization: LiveOrderContractParameterizationBoundary,
        validation_report: LiveOrderContractParameterizationValidationReport | None = None,
        journal_record: LiveOrderContractParameterizationJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Live Order Contract Parameterization Boundary",
                f"- parameterization_status: {parameterization.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- contract_validation_workflow_allowed: {str(parameterization.contract_validation_workflow_allowed).lower()}",
                f"- contract_slots_count: {len(parameterization.contract_slots)}",
                f"- parameterized_slots_count: {len(parameterization.parameterized_slot_types)}",
                f"- missing_slots_count: {len(parameterization.missing_contract_slot_types)}",
                f"- invalid_slots_count: {len(parameterization.invalid_contract_slot_types)}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- order_contract_ready: false",
                "- order_request_mapping_allowed: false",
                "- raw_values_stored: false",
                "- executable_order_created: false",
                f"- source_refs_count: {len(parameterization.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
