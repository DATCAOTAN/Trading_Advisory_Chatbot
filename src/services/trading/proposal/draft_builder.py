from __future__ import annotations

import hashlib
import json
from typing import Any

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft, ProposalDraftSection, now_utc_iso
from src.services.trading.proposal.draft_policy import ProposalDraftPolicy
from src.services.trading.proposal.draft_validator import ProposalDraftValidator
from src.services.trading.proposal.models import HumanConfirmedProposalIntent
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.review.models import HumanReviewArtifact
from src.services.trading.scoring.models import SignalScoreReport


class NonExecutableProposalDraftBuilder:
    def __init__(self, policy: ProposalDraftPolicy | None = None, validator: ProposalDraftValidator | None = None):
        self.policy = policy or ProposalDraftPolicy.from_config()
        self.validator = validator or ProposalDraftValidator(max_payload_chars=self.policy.max_context_chars)

    def build(
        self,
        intent: HumanConfirmedProposalIntent,
        review_artifact: HumanReviewArtifact,
        score_report: SignalScoreReport,
        method_selection: MethodSelectionResult,
        context_pack: RuntimeContextPack,
        calendar_context: CalendarContext | None = None,
        regime_snapshot: MarketRegimeSnapshot | None = None,
        feature_snapshot: FeatureSnapshot | None = None,
    ) -> NonExecutableTradeProposalDraft:
        status = self._status(intent, review_artifact)
        source_refs = _unique(
            intent.source_refs
            + review_artifact.source_refs
            + score_report.source_refs
            + method_selection.source_refs
            + context_pack.source_refs
        )
        blockers = _unique(intent.blockers + review_artifact.blockers + score_report.blockers + method_selection.blockers + context_pack.blockers)
        warnings = _unique(intent.warnings + review_artifact.warnings + score_report.warnings + method_selection.warnings + context_pack.warnings)
        if not self.policy.enabled:
            status = "INVALID"
            blockers.append("proposal_draft_disabled")

        primary_regime = regime_snapshot.primary_regime if regime_snapshot else review_artifact.primary_regime
        calendar_risk = calendar_context.calendar_risk_state if calendar_context else review_artifact.calendar_risk_state
        method_thesis = _method_thesis(method_selection, context_pack)
        market_summary = _market_summary(regime_snapshot, feature_snapshot, context_pack)
        calendar_summary = _calendar_summary(calendar_context, context_pack)
        risk_summary = _risk_summary(intent, review_artifact, score_report)
        score_summary = _score_summary(score_report)
        human_checks = _human_checks(calendar_risk, review_artifact.review_status, score_report.grade)
        sections = [
            ProposalDraftSection(
                section_id="method_context",
                title="Method Context",
                summary=method_thesis,
                details={
                    "primary_method_id": method_selection.primary_method_id,
                    "supporting_method_ids": list(method_selection.supporting_method_ids),
                    "selected_playbook_ids": list(method_selection.selected_playbook_ids),
                },
                source_refs=source_refs[:5],
            ),
            ProposalDraftSection(
                section_id="market_context",
                title="Market Context",
                summary=market_summary,
                details={
                    "primary_regime": primary_regime,
                    "calendar_risk_state": calendar_risk,
                    "review_status": review_artifact.review_status,
                    "readiness_action": review_artifact.readiness_action,
                },
                warnings=warnings[:5],
                blockers=blockers[:5],
                source_refs=source_refs[:5],
            ),
            ProposalDraftSection(
                section_id="human_checks",
                title="Required Human Checks",
                summary="Manual checks required before any future workflow step.",
                details={"required_human_checks": human_checks},
                warnings=warnings[:5],
                blockers=blockers[:5],
                source_refs=source_refs[:5],
            ),
        ]
        draft = NonExecutableTradeProposalDraft(
            draft_id=_draft_id(intent.intent_id, review_artifact.artifact_id, score_report.score_report_id),
            created_at=now_utc_iso(),
            mode=intent.mode or review_artifact.mode,
            symbol=review_artifact.symbol,
            broker_symbol=review_artifact.broker_symbol,
            status=status,
            non_executable=True,
            executable=False,
            proposal_workflow_allowed=intent.proposal_workflow_allowed,
            source_intent_id=intent.intent_id,
            source_review_artifact_id=review_artifact.artifact_id,
            source_score_report_id=score_report.score_report_id,
            source_method_selection_id=method_selection.result_id,
            source_context_pack_id=context_pack.context_pack_id,
            source_calendar_context_id=calendar_context.context_id if calendar_context else score_report.source_calendar_context_id,
            source_regime_snapshot_id=regime_snapshot.regime_snapshot_id if regime_snapshot else score_report.source_regime_snapshot_id,
            primary_method_id=method_selection.primary_method_id,
            supporting_method_ids=list(method_selection.supporting_method_ids),
            selected_playbook_ids=list(method_selection.selected_playbook_ids),
            primary_regime=primary_regime,
            calendar_risk_state=calendar_risk,
            readiness_action=review_artifact.readiness_action,
            review_status=review_artifact.review_status,
            final_context_score=score_report.final_context_score,
            grade=score_report.grade,
            method_thesis_summary=method_thesis,
            market_context_summary=market_summary,
            calendar_context_summary=calendar_summary,
            risk_context_summary=risk_summary,
            score_summary=score_summary,
            required_human_checks=human_checks,
            blockers=blockers,
            warnings=warnings,
            sections=sections,
            source_refs=source_refs,
        )
        draft.payload_size_chars = len(json.dumps(draft.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_draft(draft)
        if not validation.passed and draft.status == "DRAFT_CREATED":
            draft.status = "INVALID"
            draft.blockers.extend(validation.issues)
            draft.blockers = _unique(draft.blockers)
            draft.payload_size_chars = len(json.dumps(draft.as_dict(), ensure_ascii=False, sort_keys=True))
        return draft

    def _status(self, intent: HumanConfirmedProposalIntent, review_artifact: HumanReviewArtifact) -> str:
        if self.policy.require_confirmed_intent and intent.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            return "BLOCKED"
        if intent.proposal_boundary_status == "EXPIRED":
            return "EXPIRED"
        if intent.proposal_boundary_status == "DUPLICATE":
            return "DUPLICATE"
        if intent.proposal_boundary_status in {"BLOCKED", "INVALID"}:
            return "BLOCKED" if self.policy.allow_blocked_intent else "INVALID"
        if review_artifact.review_status == "WAITING" or review_artifact.readiness_action == "WAIT":
            return "WAITING" if self.policy.allow_waiting_context else "BLOCKED"
        return "DRAFT_CREATED"


def _method_thesis(method_selection: MethodSelectionResult, context_pack: RuntimeContextPack) -> str:
    method_name = method_selection.primary_method_id or "unknown_method"
    playbooks = ", ".join(method_selection.selected_playbook_ids) or "no playbook selected"
    return f"Primary method context is {method_name}; selected playbooks: {playbooks}. This is review context only."


def _market_summary(
    regime_snapshot: MarketRegimeSnapshot | None,
    feature_snapshot: FeatureSnapshot | None,
    context_pack: RuntimeContextPack,
) -> str:
    if regime_snapshot:
        return (
            f"Regime={regime_snapshot.primary_regime}; confidence={regime_snapshot.confidence:.2f}; "
            f"volatility={regime_snapshot.volatility_state}; alignment={regime_snapshot.multi_timeframe_alignment}."
        )
    summary = context_pack.market_regime_summary
    return f"Regime={summary.get('primary_regime', 'UNKNOWN')}; confidence={summary.get('confidence', 'n/a')}."


def _calendar_summary(calendar_context: CalendarContext | None, context_pack: RuntimeContextPack) -> str:
    if calendar_context:
        event = calendar_context.next_high_impact_event.title if calendar_context.next_high_impact_event else "n/a"
        return f"Calendar risk={calendar_context.calendar_risk_state}; next high impact event={event}."
    summary = context_pack.calendar_context_summary
    return f"Calendar risk={summary.get('calendar_risk_state', 'UNKNOWN')}."


def _risk_summary(
    intent: HumanConfirmedProposalIntent,
    review_artifact: HumanReviewArtifact,
    score_report: SignalScoreReport,
) -> str:
    return (
        f"Readiness={review_artifact.readiness_action}; review={review_artifact.review_status}; "
        f"grade={score_report.grade}; proposal workflow allowed={intent.proposal_workflow_allowed}."
    )


def _score_summary(score_report: SignalScoreReport) -> dict[str, Any]:
    components = {}
    if score_report.components:
        raw = score_report.components.as_dict()
        components = {
            key: {"score": value.get("score"), "grade": value.get("grade")}
            for key, value in raw.items()
            if isinstance(value, dict)
        }
    return {
        "final_context_score": round(float(score_report.final_context_score), 4),
        "grade": score_report.grade,
        "components": components,
    }


def _human_checks(calendar_risk_state: str, review_status: str, grade: str) -> list[str]:
    checks = [
        "Verify MT5 terminal manually.",
        "Verify symbol mapping manually.",
        "Verify current calendar state.",
        "Verify spread and data quality.",
        "Verify method thesis still matches current regime.",
        "Verify no blocker is active.",
    ]
    if calendar_risk_state not in {"CLEAR", ""}:
        checks.append("Recheck calendar risk before continuing.")
    if review_status != "READY_FOR_REVIEW":
        checks.append("Resolve review status before continuing.")
    if grade in {"WEAK", "BLOCKED", "UNKNOWN"}:
        checks.append("Review weak or unknown score before continuing.")
    return checks


def _draft_id(intent_id: str, artifact_id: str, score_report_id: str) -> str:
    digest = hashlib.sha256(f"{intent_id}|{artifact_id}|{score_report_id}".encode("utf-8")).hexdigest()[:16]
    return f"proposal_draft_{digest}"


def _unique(items: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for item in items:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result
