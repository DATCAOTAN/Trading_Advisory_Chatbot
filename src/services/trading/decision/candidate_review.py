from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_SCHEMA_VERSION,
    AutonomousDecisionCandidate,
    AutonomousDecisionValidationResult,
)


UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AutonomousCandidateReviewView:
    status: str
    schema_version: str
    structured_details_available: bool
    symbol: str
    intent: str
    side: str
    order_type: str
    action: str
    entry_intent: str
    entry_condition: str
    entry_price: str
    trigger_price: str
    limit_price: str
    stop_loss: str
    take_profit: str
    proposed_volume: str
    risk_policy_summary: str
    reasoning_summary: str
    market_validation_status: str
    validation_blockers: tuple[str, ...]
    recommendation: str
    generated_at: str
    expires_at: str
    freshness_status: str
    non_executable: bool
    safety_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "schema_version": self.schema_version,
            "structured_details_available": self.structured_details_available,
            "symbol": self.symbol,
            "intent": self.intent,
            "side": self.side,
            "order_type": self.order_type,
            "action": self.action,
            "entry_intent": self.entry_intent,
            "entry_condition": self.entry_condition,
            "entry_price": self.entry_price,
            "trigger_price": self.trigger_price,
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "proposed_volume": self.proposed_volume,
            "risk_policy_summary": self.risk_policy_summary,
            "reasoning_summary": self.reasoning_summary,
            "market_validation_status": self.market_validation_status,
            "validation_blockers": list(self.validation_blockers),
            "recommendation": self.recommendation,
            "generated_at": self.generated_at,
            "expires_at": self.expires_at,
            "freshness_status": self.freshness_status,
            "non_executable": self.non_executable,
            "safety_status": self.safety_status,
        }


def present_autonomous_candidate_review(
    candidate: AutonomousDecisionCandidate | None,
    validation: AutonomousDecisionValidationResult | None = None,
    *,
    now: datetime | None = None,
) -> AutonomousCandidateReviewView:
    if candidate is None:
        return _unavailable_view()

    public_payload = candidate.to_public_dict()
    review_payload = candidate.to_operator_review_dict()
    blockers = _ordered_codes(
        public_payload.get("blocked_reason_codes", ()),
        validation.issues if validation else ("VALIDATION_UNAVAILABLE",),
    )
    freshness = _freshness_status(str(review_payload.get("expires_at") or ""), now)
    safety_flags = (
        review_payload.get("execution_authority"),
        review_payload.get("execution_permission_requested"),
        review_payload.get("live_submission_allowed"),
        review_payload.get("live_execution_allowed"),
        review_payload.get("order_send_allowed"),
        review_payload.get("execution_allowed"),
        review_payload.get("executable"),
        review_payload.get("order_sent"),
    )
    non_executable = all(value is False for value in safety_flags)
    status = _review_status(
        intent=str(review_payload.get("intent") or UNAVAILABLE),
        blockers=blockers,
        freshness=freshness,
        validation_valid=(validation.valid if validation else False),
        non_executable=non_executable,
    )
    schema = str(review_payload.get("schema_version") or UNAVAILABLE)
    order_type = str(review_payload.get("order_type") or "")
    structured = schema == AUTONOMOUS_DECISION_SCHEMA_VERSION and bool(order_type)
    order_fields = (
        _order_fields(review_payload, order_type)
        if structured
        else _unavailable_order_fields()
    )
    market_status = _market_validation_status(
        structured=structured,
        blockers=blockers,
        freshness=freshness,
        validation_available=validation is not None,
        validation_valid=validation.valid if validation else False,
    )
    reasoning = tuple(review_payload.get("structured_reasoning_summary") or ())

    return AutonomousCandidateReviewView(
        status=status,
        schema_version=schema,
        structured_details_available=structured,
        symbol=str(review_payload.get("symbol") or UNAVAILABLE),
        intent=str(review_payload.get("intent") or UNAVAILABLE),
        side=_operator_value(review_payload.get("side")),
        order_type=order_type or UNAVAILABLE,
        action=str(review_payload.get("action") or UNAVAILABLE),
        entry_intent=str(review_payload.get("entry_intent") or UNAVAILABLE),
        entry_condition=order_fields["entry_condition"],
        entry_price=order_fields["entry_price"],
        trigger_price=order_fields["trigger_price"],
        limit_price=order_fields["limit_price"],
        stop_loss=_operator_value(review_payload.get("stop_loss")),
        take_profit=_operator_value(review_payload.get("take_profit")),
        proposed_volume=_operator_value(review_payload.get("proposed_volume")),
        risk_policy_summary=(
            "POLICY_REFERENCE_AVAILABLE"
            if review_payload.get("risk_policy_present")
            else UNAVAILABLE
        ),
        reasoning_summary=(
            " | ".join(str(item) for item in reasoning)
            if reasoning
            else UNAVAILABLE
        ),
        market_validation_status=market_status,
        validation_blockers=blockers,
        recommendation=str(review_payload.get("recommendation") or UNAVAILABLE),
        generated_at=str(review_payload.get("generated_at") or UNAVAILABLE),
        expires_at=str(review_payload.get("expires_at") or UNAVAILABLE),
        freshness_status=freshness,
        non_executable=non_executable,
        safety_status="NON_EXECUTABLE" if non_executable else "BLOCKED_UNSAFE_FLAGS",
    )


def _order_fields(payload: dict[str, Any], order_type: str) -> dict[str, str]:
    if order_type in {"BUY", "SELL"}:
        return {
            "entry_condition": "IMMEDIATE_MARKET_ENTRY",
            "entry_price": "NOT_APPLICABLE",
            "trigger_price": "NOT_APPLICABLE",
            "limit_price": "NOT_APPLICABLE",
        }
    if order_type.endswith("_STOP_LIMIT"):
        return {
            "entry_condition": "STOP_TRIGGER_THEN_SEPARATE_LIMIT_ENTRY",
            "entry_price": "NOT_APPLICABLE",
            "trigger_price": _operator_value(payload.get("trigger_price")),
            "limit_price": _operator_value(payload.get("limit_price")),
        }
    if order_type.endswith("_LIMIT"):
        condition = "LIMIT_ENTRY_AT_APPROVED_PRICE"
    elif order_type.endswith("_STOP"):
        condition = "STOP_TRIGGER_AT_APPROVED_PRICE"
    else:
        condition = UNAVAILABLE
    return {
        "entry_condition": condition,
        "entry_price": _operator_value(payload.get("entry_price")),
        "trigger_price": "NOT_APPLICABLE",
        "limit_price": "NOT_APPLICABLE",
    }


def _unavailable_order_fields() -> dict[str, str]:
    return {
        "entry_condition": UNAVAILABLE,
        "entry_price": UNAVAILABLE,
        "trigger_price": UNAVAILABLE,
        "limit_price": UNAVAILABLE,
    }


def _operator_value(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else UNAVAILABLE


def _review_status(
    *,
    intent: str,
    blockers: tuple[str, ...],
    freshness: str,
    validation_valid: bool,
    non_executable: bool,
) -> str:
    if freshness == "EXPIRED":
        return "EXPIRED"
    if freshness == "STALE":
        return "STALE"
    if intent == "REQUIRE_HUMAN_REVIEW":
        return "REQUIRE_HUMAN_REVIEW"
    if blockers or not validation_valid or not non_executable:
        return "BLOCKED"
    return "VALID"


def _market_validation_status(
    *,
    structured: bool,
    blockers: tuple[str, ...],
    freshness: str,
    validation_available: bool,
    validation_valid: bool,
) -> str:
    if freshness in {"EXPIRED", "STALE"}:
        return freshness
    if blockers:
        return "BLOCKED"
    if not structured:
        return "NOT_APPLICABLE"
    if not validation_available:
        return UNAVAILABLE
    return "VALID" if validation_valid else "BLOCKED"


def _freshness_status(expires_at: str, now: datetime | None) -> str:
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "STALE"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return "EXPIRED" if expiry <= current.astimezone(timezone.utc) else "FRESH"


def _ordered_codes(*groups: Any) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for value in group or ():
            code = str(value or "").strip()
            if code and code not in result:
                result.append(code)
    return tuple(result)


def _unavailable_view() -> AutonomousCandidateReviewView:
    return AutonomousCandidateReviewView(
        status=UNAVAILABLE,
        schema_version=UNAVAILABLE,
        structured_details_available=False,
        symbol=UNAVAILABLE,
        intent=UNAVAILABLE,
        side=UNAVAILABLE,
        order_type=UNAVAILABLE,
        action=UNAVAILABLE,
        entry_intent=UNAVAILABLE,
        entry_condition=UNAVAILABLE,
        entry_price=UNAVAILABLE,
        trigger_price=UNAVAILABLE,
        limit_price=UNAVAILABLE,
        stop_loss=UNAVAILABLE,
        take_profit=UNAVAILABLE,
        proposed_volume=UNAVAILABLE,
        risk_policy_summary=UNAVAILABLE,
        reasoning_summary=UNAVAILABLE,
        market_validation_status=UNAVAILABLE,
        validation_blockers=(),
        recommendation=UNAVAILABLE,
        generated_at=UNAVAILABLE,
        expires_at=UNAVAILABLE,
        freshness_status=UNAVAILABLE,
        non_executable=True,
        safety_status="NON_EXECUTABLE",
    )
