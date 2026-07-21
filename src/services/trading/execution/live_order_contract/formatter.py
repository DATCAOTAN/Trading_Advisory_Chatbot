from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.execution.live_order_contract.models import (
    LiveOrderContractSkeleton,
    LiveOrderContractSkeletonValidationReport,
)


@dataclass
class LiveOrderContractSkeletonCard:
    title: str
    status_label: str
    summary: str
    skeleton_section: Dict[str, Any] = field(default_factory=dict)
    parameter_group_section: Dict[str, Any] = field(default_factory=dict)
    validation_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = (
        "Live order contract skeleton only. This prepares future parameter validation and contains no actual "
        "side, price, size, protection, executable order, or MT5 payload."
    )
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "skeleton_section": dict(self.skeleton_section),
            "parameter_group_section": dict(self.parameter_group_section),
            "validation_section": dict(self.validation_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


class LiveOrderContractSkeletonFormatter:
    def to_card(
        self,
        skeleton: LiveOrderContractSkeleton,
        validation_report: LiveOrderContractSkeletonValidationReport,
    ) -> LiveOrderContractSkeletonCard:
        card = LiveOrderContractSkeletonCard(
            title="Live Order Contract Skeleton",
            status_label=skeleton.status,
            summary="Parameter validation preparation only; live execution, order submission, and MT5 payload creation remain disabled.",
            skeleton_section={
                "scope": skeleton.scope,
                "contract_parameter_validation_allowed": validation_report.contract_parameter_validation_allowed,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "hard_live_block_required": True,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
            },
            parameter_group_section={
                "required_parameter_groups": list(skeleton.required_parameter_groups),
                "missing_parameter_groups": list(skeleton.missing_parameter_groups),
                "resolved_parameter_groups": [],
            },
            validation_section={
                "valid": validation_report.valid,
                "blockers": list(validation_report.blockers),
                "warnings": list(validation_report.warnings),
                "validation_checks": len(validation_report.validation_checks),
            },
            source_section={
                "source_live_order_intent_id": skeleton.source_live_order_intent_id,
                "source_live_order_intent_validation_id": skeleton.source_live_order_intent_validation_id,
                "source_preflight_report_id": skeleton.source_preflight_report_id,
                "source_proposal_draft_id": skeleton.source_proposal_draft_id,
                "source_simulated_contract_id": skeleton.source_simulated_contract_id,
                "source_refs_count": len(skeleton.source_refs),
            },
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(
        self,
        skeleton: LiveOrderContractSkeleton,
        validation_report: LiveOrderContractSkeletonValidationReport,
    ) -> str:
        return "\n".join(
            [
                "### Live Order Contract Skeleton",
                "",
                "Parameter validation preparation only. This sends no trade and contains no actual side, price, or size.",
                "",
                f"- status: {skeleton.status}",
                f"- scope: {skeleton.scope}",
                f"- validation_valid: {str(validation_report.valid).lower()}",
                f"- contract_parameter_validation_allowed: {str(validation_report.contract_parameter_validation_allowed).lower()}",
                f"- required_parameter_groups_count: {len(skeleton.required_parameter_groups)}",
                f"- missing_parameter_groups_count: {len(skeleton.missing_parameter_groups)}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- executable: false",
                "- mt5_payload_created: false",
                "- order_sent: false",
                "- hard_live_block_required: true",
                f"- blockers_count: {len(validation_report.blockers)}",
                f"- source_refs_count: {len(skeleton.source_refs)}",
            ]
        )
