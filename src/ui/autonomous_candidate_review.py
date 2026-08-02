from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import streamlit as st

from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionCandidate,
    AutonomousDecisionRunResult,
    AutonomousDecisionValidationResult,
)
from src.services.trading.decision.candidate_review import (
    AutonomousCandidateReviewView,
    present_autonomous_candidate_review,
)


AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY = "autonomous_decision_run_result"
AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY = (
    "autonomous_candidate_review_outcome"
)
AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY = (
    "autonomous_candidate_pre_submit_outcome"
)


@dataclass(frozen=True)
class OperatorCandidateReviewOutcome:
    candidate_reference: str
    status: str
    confirmation_state: str
    journal_record_id: str
    blocker: str = ""


@dataclass(frozen=True)
class OperatorCandidatePreSubmitOutcome:
    candidate_reference: str
    status: str
    final_validation_valid: bool
    pre_submit_ready: bool
    journal_record_id: str
    blocker: str = ""


class OperatorCandidateReviewController:
    def __init__(
        self,
        confirmation_service,
        candidate_journal,
        account_context_provider,
        pre_submit_service=None,
        pre_submit_evidence_provider=None,
    ):
        self.confirmation_service = confirmation_service
        self.candidate_journal = candidate_journal
        self.account_context_provider = account_context_provider
        self.pre_submit_service = pre_submit_service
        self.pre_submit_evidence_provider = pre_submit_evidence_provider

    def act(
        self,
        session_state: Any,
        candidate_reference: str,
        operator_action: str,
        phrase: str = "",
        *,
        now: datetime | None = None,
    ) -> OperatorCandidateReviewOutcome:
        account_context, expected_fingerprint = self.account_context_provider()
        result = self.confirmation_service.review_candidate(
            self.candidate_journal,
            candidate_reference,
            account_context,
            expected_fingerprint,
            operator_action=operator_action,
            user_acknowledgement_text=phrase,
            expected_candidate_reference=candidate_reference,
            now=now,
        )
        outcome = OperatorCandidateReviewOutcome(
            candidate_reference=candidate_reference,
            status=result.intent.proposal_boundary_status,
            confirmation_state=result.intent.human_confirmation_state,
            journal_record_id=(
                result.journal_record.journal_record_id
                if result.journal_record
                else ""
            ),
            blocker=(result.intent.blockers[0] if result.intent.blockers else ""),
        )
        session_state[AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY] = outcome
        return outcome

    def advance_to_pre_submit(
        self,
        session_state: Any,
        candidate_reference: str,
        *,
        now: datetime | None = None,
    ) -> OperatorCandidatePreSubmitOutcome:
        if self.pre_submit_service is None or self.pre_submit_evidence_provider is None:
            outcome = OperatorCandidatePreSubmitOutcome(
                candidate_reference,
                "BLOCKED",
                False,
                False,
                "",
                "PRE_SUBMIT_SERVICE_UNAVAILABLE",
            )
        else:
            evidence = dict(self.pre_submit_evidence_provider(candidate_reference))
            result = self.pre_submit_service.run(
                candidate_reference, now=now, **evidence
            )
            blockers = (
                result.final_validation.blockers
                if result.final_validation is not None
                else result.approval.blockers
            )
            outcome = OperatorCandidatePreSubmitOutcome(
                candidate_reference=candidate_reference,
                status=(result.report.status if result.report else "BLOCKED"),
                final_validation_valid=bool(
                    result.final_validation and result.final_validation.valid
                ),
                pre_submit_ready=bool(result.report and result.report.pre_submit_ready),
                journal_record_id=(
                    result.journal_record.journal_record_id
                    if result.journal_record
                    else ""
                ),
                blocker=(blockers[0] if blockers else ""),
            )
        session_state[AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY] = outcome
        return outcome


def store_autonomous_decision_run_result(
    session_state: Any,
    run_result: AutonomousDecisionRunResult,
) -> None:
    if not isinstance(run_result, AutonomousDecisionRunResult):
        raise TypeError("run_result must be AutonomousDecisionRunResult")
    session_state[AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY] = run_result


def get_autonomous_decision_run_result(
    session_state: Any,
) -> AutonomousDecisionRunResult | None:
    run_result = session_state.get(AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY)
    return run_result if isinstance(run_result, AutonomousDecisionRunResult) else None


def clear_autonomous_decision_run_result(session_state: Any) -> None:
    session_state.pop(AUTONOMOUS_DECISION_RUN_RESULT_SESSION_KEY, None)


def render_autonomous_candidate_review_card(
    candidate: AutonomousDecisionCandidate | None,
    validation: AutonomousDecisionValidationResult | None = None,
) -> AutonomousCandidateReviewView:
    view = present_autonomous_candidate_review(candidate, validation)
    st.markdown("#### Market/Pending Order Review Card")
    st.caption(
        "Read-only operator view. This card does not confirm, approve, execute, "
        "submit, or modify an order."
    )
    if view.status == "UNAVAILABLE":
        st.info("No autonomous decision candidate is available in this session.")
        return view

    _render_status(view)
    columns = st.columns(4)
    columns[0].metric("Symbol", view.symbol)
    columns[1].metric("Intent", view.intent)
    columns[2].metric("Review status", view.status)
    columns[3].metric("Safety", view.safety_status)

    st.caption(
        f"Candidate={view.candidate_reference} | source={view.proposal_source} | "
        f"broker={view.broker_symbol} | "
        f"timeframes={','.join(view.timeframe_profile) or 'UNAVAILABLE'}"
    )
    st.caption(
        f"Integrity={view.integrity_status} | account_context={view.account_context_status} | "
        f"market_snapshot={view.market_snapshot_reference}"
    )

    st.caption(
        f"Schema={view.schema_version} | freshness={view.freshness_status} | "
        f"expires={view.expires_at}"
    )
    if not view.structured_details_available:
        st.info(
            "Structured order details are unavailable for this candidate schema or intent."
        )
    else:
        _render_structured_fields(view)

    if view.recommendation != "UNAVAILABLE":
        st.warning(f"Recommendation: {view.recommendation}")
    if view.validation_blockers:
        st.error("Validation blockers")
        for blocker in view.validation_blockers:
            st.markdown(f"- {blocker}")
    else:
        st.caption("Validation blockers: none")
    st.caption(
        "execution_authority=false | execution_permission_requested=false | "
        "executable=false | order_send_allowed=false | order_sent=false"
    )
    return view


def render_autonomous_candidate_confirmation_controls(
    candidate_reference: str,
    controller: OperatorCandidateReviewController,
    *,
    key_prefix: str = "",
) -> None:
    st.caption(
        "Explicit candidate review only. Confirmation remains non-executable and "
        "does not export or submit an order."
    )
    st.caption(
        f"Required phrase: `{controller.confirmation_service.policy.confirmation_phrase}`"
    )
    phrase = st.text_input(
        "Non-executable confirmation phrase",
        type="password",
        key=f"{key_prefix}autonomous_candidate_confirmation_phrase",
    )
    actions = st.columns(2)
    if actions[0].button(
        "Confirm Candidate (Non-Executable)",
        key=f"{key_prefix}confirm_autonomous_candidate",
        use_container_width=True,
    ):
        controller.act(st.session_state, candidate_reference, "CONFIRM", phrase)
    if actions[1].button(
        "Reject Candidate",
        key=f"{key_prefix}reject_autonomous_candidate",
        use_container_width=True,
    ):
        controller.act(st.session_state, candidate_reference, "REJECT")
    outcome = st.session_state.get(AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY)
    if isinstance(outcome, OperatorCandidateReviewOutcome):
        message = (
            f"Review={outcome.status} | confirmation={outcome.confirmation_state} | "
            f"candidate={outcome.candidate_reference}"
        )
        if outcome.status in {"CONFIRMED_FOR_PROPOSAL_WORKFLOW", "REJECTED"}:
            st.success(message)
        elif outcome.status == "DUPLICATE":
            st.info(message)
        else:
            st.error(message + (f" | blocker={outcome.blocker}" if outcome.blocker else ""))


def _render_status(view: AutonomousCandidateReviewView) -> None:
    message = (
        f"Candidate={view.status} | market_validation={view.market_validation_status}"
    )
    if view.status == "VALID":
        st.success(message)
    elif view.status in {"REQUIRE_HUMAN_REVIEW", "STALE", "EXPIRED"}:
        st.warning(message)
    else:
        st.error(message)


def _render_structured_fields(view: AutonomousCandidateReviewView) -> None:
    columns = st.columns(4)
    columns[0].metric("Side", view.side)
    columns[1].metric("Order type", view.order_type)
    columns[2].metric("Resolved action", view.action)
    columns[3].metric("Entry intent", view.entry_intent)
    st.caption(f"Entry condition: {view.entry_condition}")

    if view.order_type.endswith("_STOP_LIMIT"):
        prices = st.columns(2)
        prices[0].metric("Trigger price", view.trigger_price)
        prices[1].metric("Limit price", view.limit_price)
    elif view.order_type.endswith("_LIMIT") or view.order_type.endswith("_STOP"):
        st.metric("Entry price", view.entry_price)

    risk = st.columns(4)
    risk[0].metric("Stop loss", view.stop_loss)
    risk[1].metric("Take profit", view.take_profit)
    risk[2].metric("Proposed volume", view.proposed_volume)
    risk[3].metric("Risk policy", view.risk_policy_summary)
    st.caption(f"Reasoning summary: {view.reasoning_summary}")
    st.caption(f"Method selection: {view.method_selection_summary}")
