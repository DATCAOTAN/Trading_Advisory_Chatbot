from __future__ import annotations

import json

from src.services.trading.review.models import HumanReviewArtifact, ReviewCard
from src.services.trading.review.validator import HumanReviewArtifactValidator


class HumanReviewFormatter:
    def __init__(self, validator: HumanReviewArtifactValidator | None = None):
        self.validator = validator or HumanReviewArtifactValidator()

    def to_card(self, artifact: HumanReviewArtifact) -> ReviewCard:
        card = ReviewCard(
            title="Human Review Card",
            status_label=artifact.review_status,
            summary=_summary(artifact),
            method_section={
                "primary_method_id": artifact.primary_method_id,
                "supporting_method_ids": list(artifact.supporting_method_ids),
                "selected_playbook_ids": list(artifact.selected_playbook_ids),
            },
            market_section={
                "primary_regime": artifact.primary_regime,
                "readiness_action": artifact.readiness_action,
            },
            calendar_section={
                "calendar_risk_state": artifact.calendar_risk_state,
            },
            score_section={
                "readiness_score": artifact.readiness_score,
                "confidence": artifact.confidence,
                "grade": artifact.grade,
                "final_context_score": artifact.final_context_score,
                "component_score_summary": dict(artifact.component_score_summary),
            },
            blocker_section={
                "blockers_count": len(artifact.blockers),
                "warnings_count": len(artifact.warnings),
                "reasons": list(artifact.reasons[:10]),
            },
            source_section={
                "source_refs_count": len(artifact.source_refs),
                "source_readiness_decision_id": artifact.source_readiness_decision_id,
                "source_score_report_id": artifact.source_score_report_id,
            },
            disclaimer="Human review artifact only. It contains no execution instructions.",
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(self, artifact: HumanReviewArtifact) -> str:
        validation = self.validator.validate(artifact)
        status = artifact.review_status if validation.passed else "BLOCKED"
        lines = [
            "### Human Review Card",
            f"- Status: {status}",
            f"- Readiness action: {artifact.readiness_action}",
            f"- Method: {artifact.primary_method_id or 'n/a'}",
            f"- Regime: {artifact.primary_regime}",
            f"- Calendar risk: {artifact.calendar_risk_state}",
            f"- Final context score: {artifact.final_context_score:.4f}",
            f"- Readiness score: {artifact.readiness_score:.4f}",
            f"- Confidence: {artifact.confidence:.4f}",
            f"- Blockers: {len(artifact.blockers)}",
            f"- Warnings: {len(artifact.warnings)}",
            f"- Source refs: {len(artifact.source_refs)}",
            "",
            "Human review artifact only. It contains no execution instructions.",
        ]
        return "\n".join(lines)


def _summary(artifact: HumanReviewArtifact) -> str:
    return (
        f"{artifact.review_status} for {artifact.symbol}: "
        f"action={artifact.readiness_action}, score={artifact.readiness_score:.2f}, "
        f"method={artifact.primary_method_id or 'n/a'}."
    )
