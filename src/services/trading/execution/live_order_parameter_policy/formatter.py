from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.services.trading.execution.live_order_parameter_policy.models import (
    LiveOrderParameterPolicyJournalRecord,
    LiveOrderParameterPolicySpec,
    LiveOrderParameterPolicyValidationReport,
)


@dataclass
class LiveOrderParameterPolicyCard:
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


class LiveOrderParameterPolicyFormatter:
    def to_card(
        self,
        spec: LiveOrderParameterPolicySpec,
        validation_report: LiveOrderParameterPolicyValidationReport | None = None,
        journal_record: LiveOrderParameterPolicyJournalRecord | None = None,
    ) -> LiveOrderParameterPolicyCard:
        return LiveOrderParameterPolicyCard(
            title="Live Order Parameter Policy Validator",
            status=spec.status,
            fields={
                "validation_valid": bool(getattr(validation_report, "valid", False)) if validation_report else False,
                "parameter_source_boundary_allowed": bool(spec.parameter_source_boundary_allowed),
                "policy_groups": list(spec.required_parameter_groups),
                "policy_rules_count": len(spec.policy_rules),
                "unresolved_groups_count": len(spec.unresolved_parameter_groups),
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
                "resolved_parameter_values_present": False,
                "actual_order_values_present": False,
                "source_refs_count": len(spec.source_refs),
                "journal_record_id": getattr(journal_record, "journal_record_id", ""),
            },
            blockers=list(spec.blockers) + list(getattr(validation_report, "blockers", []) or []),
            warnings=list(spec.warnings) + list(getattr(validation_report, "warnings", []) or []),
        )

    def to_markdown_summary(
        self,
        spec: LiveOrderParameterPolicySpec,
        validation_report: LiveOrderParameterPolicyValidationReport | None = None,
        journal_record: LiveOrderParameterPolicyJournalRecord | None = None,
    ) -> str:
        valid = bool(getattr(validation_report, "valid", False)) if validation_report else False
        return "\n".join(
            [
                "### Live Order Parameter Policy Validator",
                f"- policy_status: {spec.status}",
                f"- validation_valid: {str(valid).lower()}",
                f"- parameter_source_boundary_allowed: {str(spec.parameter_source_boundary_allowed).lower()}",
                f"- policy_groups_count: {len(spec.required_parameter_groups)}",
                f"- policy_rules_count: {len(spec.policy_rules)}",
                f"- unresolved_groups_count: {len(spec.unresolved_parameter_groups)}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                "- resolved_parameter_values_present: false",
                "- actual_order_values_present: false",
                f"- source_refs_count: {len(spec.source_refs)}",
                f"- journal_record_id: {getattr(journal_record, 'journal_record_id', '')}",
            ]
        )
