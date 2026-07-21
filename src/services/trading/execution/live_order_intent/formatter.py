from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.execution.live_order_intent.models import (
    LiveOrderIntent,
    LiveOrderIntentValidationReport,
)


@dataclass
class LiveOrderIntentCard:
    title: str
    status_label: str
    summary: str
    intent_section: Dict[str, Any] = field(default_factory=dict)
    validation_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = (
        "Live order intent only. This prepares the next contract workflow and contains no side, price, size, "
        "or executable order."
    )
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "intent_section": dict(self.intent_section),
            "validation_section": dict(self.validation_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


class LiveOrderIntentFormatter:
    def to_card(self, intent: LiveOrderIntent, validation_report: LiveOrderIntentValidationReport) -> LiveOrderIntentCard:
        card = LiveOrderIntentCard(
            title="Live Order Intent Builder",
            status_label=intent.status,
            summary="Contract workflow preparation only; live execution, order submission, and execution remain disabled.",
            intent_section={
                "scope": intent.scope,
                "order_contract_workflow_allowed": validation_report.order_contract_workflow_allowed,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "hard_live_block_required": True,
            },
            validation_section={
                "valid": validation_report.valid,
                "blockers": list(validation_report.blockers),
                "warnings": list(validation_report.warnings),
                "validation_checks": len(validation_report.validation_checks),
            },
            source_section={
                "source_live_permission_intent_id": intent.source_live_permission_intent_id,
                "source_live_permission_decision_id": intent.source_live_permission_decision_id,
                "source_preflight_report_id": intent.source_preflight_report_id,
                "source_proposal_draft_id": intent.source_proposal_draft_id,
                "source_simulated_contract_id": intent.source_simulated_contract_id,
                "source_refs_count": len(intent.source_refs),
            },
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(self, intent: LiveOrderIntent, validation_report: LiveOrderIntentValidationReport) -> str:
        return "\n".join(
            [
                "### Live Order Intent Builder",
                "",
                "Contract workflow preparation only. This sends no trade and contains no side, price, or size.",
                "",
                f"- status: {intent.status}",
                f"- scope: {intent.scope}",
                f"- validation_valid: {str(validation_report.valid).lower()}",
                f"- order_contract_workflow_allowed: {str(validation_report.order_contract_workflow_allowed).lower()}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- hard_live_block_required: true",
                f"- blockers_count: {len(validation_report.blockers)}",
                f"- source_refs_count: {len(intent.source_refs)}",
            ]
        )
