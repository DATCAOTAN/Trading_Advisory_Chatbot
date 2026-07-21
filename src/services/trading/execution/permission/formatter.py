from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.execution.permission.models import LivePermissionGateDecision, LivePermissionIntent


@dataclass
class LivePermissionGateCard:
    title: str
    status_label: str
    summary: str
    permission_section: Dict[str, Any] = field(default_factory=dict)
    blocker_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Permission gate only. This permits live order intent preparation only and sends no trade."
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "permission_section": dict(self.permission_section),
            "blocker_section": dict(self.blocker_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


class LivePermissionGateFormatter:
    def to_card(self, intent: LivePermissionIntent, decision: LivePermissionGateDecision) -> LivePermissionGateCard:
        card = LivePermissionGateCard(
            title="Human-Confirmed Live Permission Gate",
            status_label=intent.permission_status,
            summary="Order intent preparation permission only; live execution and order submission remain disabled.",
            permission_section={
                "confirmation_state": intent.confirmation_state,
                "gate_allowed": decision.gate_allowed,
                "order_intent_workflow_allowed": decision.order_intent_workflow_allowed,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "hard_live_block_required": True,
            },
            blocker_section={
                "block_reasons": list(decision.block_reasons),
                "blockers": list(decision.blockers),
                "warnings": list(decision.warnings),
            },
            source_section={
                "source_preflight_report_id": intent.source_preflight_report_id,
                "source_design_report_id": intent.source_design_report_id,
                "source_refs_count": len(intent.source_refs),
            },
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(self, intent: LivePermissionIntent, decision: LivePermissionGateDecision) -> str:
        return "\n".join(
            [
                "### Human-Confirmed Live Permission Gate",
                "",
                "Permission gate only. This permits live order intent preparation only and sends no trade.",
                "",
                f"- permission_status: {intent.permission_status}",
                f"- confirmation_state: {intent.confirmation_state}",
                f"- gate_allowed: {str(decision.gate_allowed).lower()}",
                f"- order_intent_workflow_allowed: {str(decision.order_intent_workflow_allowed).lower()}",
                "- live_execution_allowed: false",
                "- order_send_allowed: false",
                "- execution_allowed: false",
                "- hard_live_block_required: true",
                f"- block_reasons_count: {len(decision.block_reasons)}",
                f"- source_refs_count: {len(intent.source_refs)}",
            ]
        )
