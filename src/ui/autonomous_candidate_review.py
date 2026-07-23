from __future__ import annotations

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
