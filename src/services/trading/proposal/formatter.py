from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.proposal.models import HumanConfirmedProposalIntent


@dataclass
class ProposalBoundaryCard:
    title: str
    status_label: str
    summary: str
    confirmation_section: Dict[str, Any] = field(default_factory=dict)
    dry_run_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    blocker_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Proposal workflow confirmation only. No live order is sent."
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "confirmation_section": dict(self.confirmation_section),
            "dry_run_section": dict(self.dry_run_section),
            "source_section": dict(self.source_section),
            "blocker_section": dict(self.blocker_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


class ProposalBoundaryFormatter:
    def to_card(self, intent: HumanConfirmedProposalIntent) -> ProposalBoundaryCard:
        card = ProposalBoundaryCard(
            title="Proposal Boundary Confirmation",
            status_label=intent.proposal_boundary_status,
            summary=(
                "Non-executable proposal workflow boundary. "
                f"dry_run_only={intent.dry_run_only}, executable={intent.executable}."
            ),
            confirmation_section={
                "human_confirmation_state": intent.human_confirmation_state,
                "proposal_workflow_allowed": intent.proposal_workflow_allowed,
                "confirmation_phrase_required": intent.confirmation_phrase_required,
            },
            dry_run_section={
                "review_status": intent.review_status,
                "readiness_action": intent.readiness_action,
                "gate_action": intent.gate_action,
                "dry_run_allowed": intent.dry_run_allowed,
                "dry_run_executed": intent.dry_run_executed,
                "dry_run_receipt_id": intent.dry_run_receipt_id,
                "artifact_hash_prefix": intent.artifact_hash[:12],
                "idempotency_key_prefix": intent.idempotency_key[:12],
            },
            source_section={"source_refs_count": len(intent.source_refs)},
            blocker_section={
                "blockers": list(intent.blockers),
                "warnings": list(intent.warnings),
                "reasons": list(intent.reasons),
            },
        )
        card.payload_size_chars = len(str(card.as_dict()))
        return card

    def to_markdown(self, intent: HumanConfirmedProposalIntent) -> str:
        blockers = ", ".join(intent.blockers[:5]) or "n/a"
        warnings = ", ".join(intent.warnings[:5]) or "n/a"
        return "\n".join(
            [
                "### Proposal Boundary Confirmation",
                f"- Status: `{intent.proposal_boundary_status}`",
                f"- Human confirmation: `{intent.human_confirmation_state}`",
                f"- Proposal workflow allowed: `{str(intent.proposal_workflow_allowed).lower()}`",
                f"- Dry-run only: `{str(intent.dry_run_only).lower()}`",
                f"- Executable: `{str(intent.executable).lower()}`",
                f"- Review status: `{intent.review_status}`",
                f"- Readiness action: `{intent.readiness_action}`",
                f"- Gate action: `{intent.gate_action}`",
                f"- Receipt: `{intent.dry_run_receipt_id}`",
                f"- Artifact hash prefix: `{intent.artifact_hash[:12]}`",
                f"- Source refs: `{len(intent.source_refs)}`",
                f"- Blockers: {blockers}",
                f"- Warnings: {warnings}",
                "",
                "Proposal workflow confirmation only. No live order is sent.",
            ]
        )
