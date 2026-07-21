from __future__ import annotations

from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft, ProposalDraftCard


class ProposalDraftFormatter:
    def to_card(self, draft: NonExecutableTradeProposalDraft) -> ProposalDraftCard:
        card = ProposalDraftCard(
            title="Non-Executable Proposal Draft",
            status_label=draft.status,
            non_executable_label="non_executable=true, executable=false",
            summary=(
                "Structured review draft only. It is not a signal, not an order request, "
                "and no live order is sent."
            ),
            method_section={
                "primary_method_id": draft.primary_method_id,
                "supporting_method_ids": list(draft.supporting_method_ids),
                "selected_playbook_ids": list(draft.selected_playbook_ids),
                "method_thesis_summary": draft.method_thesis_summary,
            },
            market_section={
                "primary_regime": draft.primary_regime,
                "market_context_summary": draft.market_context_summary,
                "readiness_action": draft.readiness_action,
                "review_status": draft.review_status,
            },
            calendar_section={
                "calendar_risk_state": draft.calendar_risk_state,
                "calendar_context_summary": draft.calendar_context_summary,
            },
            score_section={
                "final_context_score": draft.final_context_score,
                "grade": draft.grade,
                "score_summary": dict(draft.score_summary),
            },
            risk_section={"risk_context_summary": draft.risk_context_summary},
            human_checks_section={"required_human_checks": list(draft.required_human_checks)},
            blockers_section={
                "blockers": list(draft.blockers),
                "warnings": list(draft.warnings),
            },
            source_section={"source_refs_count": len(draft.source_refs)},
        )
        card.payload_size_chars = len(str(card.as_dict()))
        return card

    def to_markdown(self, draft: NonExecutableTradeProposalDraft) -> str:
        blockers = ", ".join(draft.blockers[:5]) or "n/a"
        warnings = ", ".join(draft.warnings[:5]) or "n/a"
        checks = "; ".join(draft.required_human_checks[:6]) or "n/a"
        return "\n".join(
            [
                "### Non-Executable Proposal Draft",
                f"- Status: `{draft.status}`",
                f"- Non-executable: `{str(draft.non_executable).lower()}`",
                f"- Executable: `{str(draft.executable).lower()}`",
                f"- Method: `{draft.primary_method_id}`",
                f"- Regime: `{draft.primary_regime}`",
                f"- Calendar risk: `{draft.calendar_risk_state}`",
                f"- Final context score: `{draft.final_context_score:.4f}`",
                f"- Readiness action: `{draft.readiness_action}`",
                f"- Review status: `{draft.review_status}`",
                f"- Human checks: {checks}",
                f"- Source refs: `{len(draft.source_refs)}`",
                f"- Blockers: {blockers}",
                f"- Warnings: {warnings}",
                "",
                "This is not a signal and not an executable order request. No live order is sent.",
            ]
        )
