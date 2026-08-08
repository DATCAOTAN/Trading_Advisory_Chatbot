from __future__ import annotations

import json
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
from src.services.trading.proposal.intent_store import load_candidate_confirmation


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

    def current_outcome(
        self, candidate_reference: str
    ) -> OperatorCandidateReviewOutcome | None:
        """Reload the persisted decision for one exact Candidate, if it exists."""
        try:
            record = load_candidate_confirmation(
                self.confirmation_service.journal.store, candidate_reference
            )
        except RuntimeError as exc:
            return OperatorCandidateReviewOutcome(
                candidate_reference,
                "BLOCKED",
                "NOT_REQUESTED",
                "",
                str(exc),
            )
        if record is None:
            return None
        return OperatorCandidateReviewOutcome(
            candidate_reference,
            record.proposal_boundary_status,
            record.human_confirmation_state,
            record.journal_record_id,
        )

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
            try:
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
            except RuntimeError as exc:
                outcome = OperatorCandidatePreSubmitOutcome(
                    candidate_reference, "BLOCKED", False, False, "", str(exc)
                )
        session_state[AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY] = outcome
        return outcome

    def current_pre_submit_outcome(
        self, candidate_reference: str
    ) -> OperatorCandidatePreSubmitOutcome | None:
        if self.pre_submit_service is None:
            return None
        try:
            record = self.pre_submit_service.pre_submit_store.load_candidate_pre_submit(
                candidate_reference
            )
        except RuntimeError as exc:
            return OperatorCandidatePreSubmitOutcome(
                candidate_reference, "BLOCKED", False, False, "", str(exc)
            )
        if record is None:
            return None
        return OperatorCandidatePreSubmitOutcome(
            candidate_reference=candidate_reference,
            status=str(record.get("status", "BLOCKED")),
            final_validation_valid=record.get("valid") is True,
            pre_submit_ready=record.get("pre_submit_state")
            == "PRE_SUBMIT_READY_NON_EXECUTABLE",
            journal_record_id=str(record.get("journal_record_id", "")),
        )


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
    if view.strategy_id != "UNAVAILABLE":
        st.caption(
            f"Strategy={view.strategy_id} | version={view.strategy_version} | "
            f"hash={view.strategy_hash_prefix}"
        )
    render_reasoning_evidence_summary(view.reasoning_evidence_summary)
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
    outcome = controller.current_outcome(candidate_reference)
    if outcome is None:
        session_outcome = st.session_state.get(
            AUTONOMOUS_CANDIDATE_REVIEW_OUTCOME_SESSION_KEY
        )
        outcome = (
            session_outcome
            if isinstance(session_outcome, OperatorCandidateReviewOutcome)
            and session_outcome.candidate_reference == candidate_reference
            else None
        )
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

        if outcome.status == "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            if st.button(
                "Validate Pre-Submit (Non-Executable)",
                key=f"{key_prefix}validate_autonomous_candidate_pre_submit",
                use_container_width=True,
            ):
                controller.advance_to_pre_submit(st.session_state, candidate_reference)

    pre_submit_outcome = controller.current_pre_submit_outcome(candidate_reference)
    if pre_submit_outcome is None:
        session_pre_submit = st.session_state.get(
            AUTONOMOUS_CANDIDATE_PRE_SUBMIT_OUTCOME_SESSION_KEY
        )
        pre_submit_outcome = (
            session_pre_submit
            if isinstance(session_pre_submit, OperatorCandidatePreSubmitOutcome)
            and session_pre_submit.candidate_reference == candidate_reference
            else None
        )
    if isinstance(pre_submit_outcome, OperatorCandidatePreSubmitOutcome):
        message = (
            f"Pre-submit={pre_submit_outcome.status} | "
            f"final_validation={pre_submit_outcome.final_validation_valid} | "
            f"candidate={pre_submit_outcome.candidate_reference}"
        )
        if pre_submit_outcome.pre_submit_ready:
            st.success(message + " | submission_disabled=true")
        else:
            st.error(
                message
                + (
                    f" | blocker={pre_submit_outcome.blocker}"
                    if pre_submit_outcome.blocker
                    else ""
                )
            )


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


def render_reasoning_evidence_summary(value: str) -> None:
    if not value:
        return
    try:
        evidence = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        st.warning("Reasoning evidence is unavailable or invalid.")
        return
    st.markdown("##### Reasoning Evidence v2")
    st.caption(
        f"Regime={evidence.get('regime', 'UNAVAILABLE')} | "
        f"confidence={float(evidence.get('regime_confidence') or 0):.2f}"
    )
    scores = evidence.get("scores") or {}
    if scores:
        st.caption(
            "Score breakdown: "
            + " | ".join(f"{name}={float(score):.2f}" for name, score in scores.items())
        )
    for item in evidence.get("history") or ():
        st.caption(
            f"{item.get('timeframe')}: completed={item.get('completed_bars')}/"
            f"{item.get('requested_bars')} | freshness={item.get('freshness')} | "
            f"gaps={item.get('gaps')}"
        )
    for item in evidence.get("reasons") or ():
        st.markdown(
            f"- **{item.get('code')}**: {item.get('summary')} "
            f"(actual={item.get('actual')}, required={item.get('required')})"
        )
