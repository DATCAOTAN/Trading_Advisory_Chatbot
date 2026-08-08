from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs, service
from scripts.test_structured_market_pending_order_candidate import structured_inputs
from src.services.trading.decision.autonomous_orchestrator import (
    AUTONOMOUS_DECISION_LEGACY_SCHEMA_VERSION,
)
from src.services.trading.decision.candidate_review import (
    UNAVAILABLE,
    present_autonomous_candidate_review,
)
import src.ui.autonomous_candidate_review as review_ui


def candidate(tmp_path, order_type="BUY", **changes):
    orchestrator = service(tmp_path)
    value = orchestrator.build_candidate(
        structured_inputs(order_type, **changes),
        now=NOW,
    )
    validation = orchestrator.validate_candidate(value, now=NOW)
    return value, validation


def test_market_candidate_displays_operator_proposal_values(tmp_path):
    value, validation = candidate(tmp_path, "BUY")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.status == "VALID"
    assert view.side == "BUY"
    assert view.order_type == "BUY"
    assert view.action == "MARKET"
    assert view.entry_condition == "IMMEDIATE_MARKET_ENTRY"
    assert view.entry_price == "NOT_APPLICABLE"
    assert view.trigger_price == "NOT_APPLICABLE"
    assert view.limit_price == "NOT_APPLICABLE"
    assert view.stop_loss == "99"
    assert view.take_profit == "102"
    assert view.proposed_volume == "0.01"
    assert view.reasoning_summary == "method-aligned | risk-reviewed"


def test_limit_candidate_displays_operator_entry_price(tmp_path):
    value, validation = candidate(tmp_path, "BUY_LIMIT")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.action == "PENDING"
    assert view.entry_condition == "LIMIT_ENTRY_AT_APPROVED_PRICE"
    assert view.entry_price == "100.5"
    assert view.trigger_price == "NOT_APPLICABLE"


def test_stop_candidate_displays_operator_entry_price(tmp_path):
    value, validation = candidate(tmp_path, "SELL_STOP")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.entry_condition == "STOP_TRIGGER_AT_APPROVED_PRICE"
    assert view.entry_price == "99.5"


def test_stop_limit_displays_separate_trigger_and_limit_prices(tmp_path):
    value, validation = candidate(tmp_path, "BUY_STOP_LIMIT")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.entry_price == "NOT_APPLICABLE"
    assert view.trigger_price == "101.5"
    assert view.limit_price == "101.2"
    assert view.entry_condition == "STOP_TRIGGER_THEN_SEPARATE_LIMIT_ENTRY"


def test_blocked_candidate_displays_deterministic_blockers(tmp_path):
    value, validation = candidate(tmp_path, "BUY_LIMIT", entry_price="101.0")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.status == "BLOCKED"
    assert view.market_validation_status == "BLOCKED"
    assert view.validation_blockers == value.blocked_reason_codes


def test_market_recommendation_does_not_change_pending_order_type(tmp_path):
    value, validation = candidate(tmp_path, "BUY_LIMIT", entry_price="101.0")
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.order_type == "BUY_LIMIT"
    assert view.action == "PENDING"
    assert view.recommendation == "MARKET_ORDER_REVIEW_RECOMMENDED"


def test_missing_optional_values_display_as_unavailable(tmp_path):
    value, validation = candidate(
        tmp_path,
        "BUY",
        stop_loss=None,
        take_profit=None,
        proposed_volume=None,
    )
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.stop_loss == UNAVAILABLE
    assert view.take_profit == UNAVAILABLE
    assert view.proposed_volume == UNAVAILABLE


def test_expired_candidate_displays_expired_status(tmp_path):
    value, validation = candidate(tmp_path, "BUY_LIMIT")
    expired = replace(value, expires_at=NOW.isoformat())
    view = present_autonomous_candidate_review(expired, validation, now=NOW)
    assert view.status == "EXPIRED"
    assert view.freshness_status == "EXPIRED"
    assert view.market_validation_status == "EXPIRED"


def test_v1_candidate_remains_compatible_without_structured_details(tmp_path):
    orchestrator = service(tmp_path)
    value = orchestrator.build_candidate(make_inputs(), now=NOW)
    legacy = replace(
        value,
        schema_version=AUTONOMOUS_DECISION_LEGACY_SCHEMA_VERSION,
        side="",
        entry_intent="",
        order_type="",
        action="",
        advisory_action="",
        entry_price="",
        trigger_price="",
        limit_price="",
        stop_loss="",
        take_profit="",
        proposed_volume="",
        risk_policy_reference="",
        structured_reasoning=(),
        market_snapshot_reference="",
        market_snapshot_provenance_hash="",
        market_recommendation="",
        structured_order_hash="",
    )
    validation = orchestrator.validate_candidate(legacy, now=NOW)
    view = present_autonomous_candidate_review(legacy, validation, now=NOW)
    assert view.status == "VALID"
    assert view.structured_details_available is False
    assert view.order_type == UNAVAILABLE
    assert view.entry_price == UNAVAILABLE


def test_no_action_remains_non_action(tmp_path):
    orchestrator = service(tmp_path)
    value = orchestrator.build_candidate(
        make_inputs(risk_action="NO_TRADE", requested_intent="AUTO"),
        now=NOW,
    )
    validation = orchestrator.validate_candidate(value, now=NOW)
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.intent == "NO_ACTION"
    assert view.status == "VALID"
    assert view.structured_details_available is False


def test_require_human_review_remains_review_only(tmp_path):
    orchestrator = service(tmp_path)
    value = orchestrator.build_candidate(
        make_inputs(),
        now=NOW,
        forced_blockers=("STALE_MARKET_CONTEXT",),
    )
    validation = orchestrator.validate_candidate(value, now=NOW)
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.intent == "REQUIRE_HUMAN_REVIEW"
    assert view.status == "REQUIRE_HUMAN_REVIEW"
    assert view.non_executable is True


def test_operator_projection_hides_sensitive_and_protected_values(tmp_path):
    value, validation = candidate(tmp_path, "BUY_STOP_LIMIT")
    payload = json.dumps(
        present_autonomous_candidate_review(value, validation, now=NOW).as_dict(),
        sort_keys=True,
    )
    assert "101.5" in payload
    assert "101.2" in payload
    assert "0.01" in payload
    assert "method-aligned" in payload
    for forbidden in (
        "risk-policy-fixture",
        value.provenance_hash,
        value.structured_order_hash,
        value.market_snapshot_provenance_hash,
        "account_login",
        "ticket_id",
        "deal_id",
        "position_id",
        "credential",
        "execution_token",
    ):
        assert forbidden not in payload
    assert value.candidate_reference in payload
    assert value.market_snapshot_reference in payload


def test_operator_projection_redacts_sensitive_reasoning_text(tmp_path):
    value, validation = candidate(tmp_path, "BUY")
    value = replace(
        value,
        structured_reasoning=("method-aligned", "api_key=must-not-render"),
    )
    validation = service(tmp_path).validate_candidate(value, now=NOW)
    view = present_autonomous_candidate_review(value, validation, now=NOW)
    assert view.reasoning_summary == "method-aligned | [REDACTED]"
    assert "must-not-render" not in json.dumps(view.as_dict())


def test_public_serialization_remains_unchanged_and_redacted(tmp_path):
    value, _validation = candidate(tmp_path, "BUY_STOP_LIMIT")
    public_before = value.to_public_dict()
    review = value.to_operator_review_dict()
    public_after = value.to_public_dict()
    assert public_after == public_before
    public_json = json.dumps(public_after, sort_keys=True)
    assert "101.5" not in public_json
    assert "101.2" not in public_json
    assert "0.01" not in public_json
    assert "method-aligned" not in public_json
    assert review["trigger_price"] == "101.5"
    assert review["limit_price"] == "101.2"
    assert review["proposed_volume"] == "0.01"
    assert review["structured_reasoning_summary"] == [
        "method-aligned",
        "risk-reviewed",
    ]
    for forbidden_key in (
        "provenance_hash",
        "structured_order_hash",
        "market_snapshot_provenance_hash",
        "decision_idempotency_key",
        "account_login",
        "ticket_id",
        "deal_id",
        "position_id",
        "credentials",
        "execution_token",
    ):
        assert forbidden_key not in review
    assert review["candidate_reference"] == value.candidate_reference


def test_runtime_owner_preserves_typed_result_without_refresh_side_effects(
    tmp_path, monkeypatch
):
    orchestrator = service(tmp_path)
    run_result = orchestrator.run_once(structured_inputs("SELL_LIMIT"), now=NOW)
    session_state = {}
    review_ui.store_autonomous_decision_run_result(session_state, run_result)
    fake = FakeStreamlit()
    monkeypatch.setattr(review_ui, "st", fake)

    stored_first = review_ui.get_autonomous_decision_run_result(session_state)
    first = review_ui.render_autonomous_candidate_review_card(
        stored_first.candidate, stored_first.validation
    )
    stored_second = review_ui.get_autonomous_decision_run_result(session_state)
    second = review_ui.render_autonomous_candidate_review_card(
        stored_second.candidate, stored_second.validation
    )

    assert stored_first is run_result
    assert stored_second is run_result
    assert first.as_dict() == second.as_dict()
    assert len((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert fake.buttons == 0


def test_runtime_owner_replaces_and_clears_only_explicitly(tmp_path):
    first = service(tmp_path).run_once(structured_inputs("BUY_LIMIT"), now=NOW)
    second_candidate, second_validation = candidate(tmp_path, "SELL_STOP")
    second = replace(
        first,
        candidate=second_candidate,
        validation=second_validation,
        journal_appended=False,
    )
    session_state = {}
    review_ui.store_autonomous_decision_run_result(session_state, first)
    assert review_ui.get_autonomous_decision_run_result(session_state) is first
    review_ui.store_autonomous_decision_run_result(session_state, second)
    assert review_ui.get_autonomous_decision_run_result(session_state) is second
    review_ui.clear_autonomous_decision_run_result(session_state)
    assert review_ui.get_autonomous_decision_run_result(session_state) is None


def test_renderer_emits_distinct_stop_limit_fields(tmp_path, monkeypatch):
    value, validation = candidate(tmp_path, "SELL_STOP_LIMIT")
    fake = FakeStreamlit()
    monkeypatch.setattr(review_ui, "st", fake)
    review_ui.render_autonomous_candidate_review_card(value, validation)
    assert ("Trigger price", "99.5") in fake.metrics
    assert ("Limit price", "99.8") in fake.metrics


def test_candidate_without_validation_fails_closed(tmp_path):
    value, _validation = candidate(tmp_path, "BUY")
    view = present_autonomous_candidate_review(value, now=NOW)
    assert view.status == "BLOCKED"
    assert view.market_validation_status == "BLOCKED"
    assert "VALIDATION_UNAVAILABLE" in view.validation_blockers


def test_unavailable_candidate_renders_clear_empty_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(review_ui, "st", fake)
    view = review_ui.render_autonomous_candidate_review_card(None)
    assert view.status == UNAVAILABLE
    assert any("No autonomous decision candidate" in message for message in fake.infos)


def test_review_projection_has_no_mutation_or_generation_path():
    source = Path("src/services/trading/decision/candidate_review.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
    for forbidden in (
        "autonomousdecisionorchestrator",
        "append_idempotent",
        "controlled" + "-submit",
        "controlled" + "-manage",
        ".order" + "_send(",
        "metatrader5",
        "llmreasoningadapter",
    ):
        assert forbidden not in lowered
    assert "candidate.to_public_dict()" in source


def test_review_ui_only_exposes_explicit_non_executable_actions():
    source = Path("src/ui/autonomous_candidate_review.py").read_text(encoding="utf-8")
    assert "Confirm Candidate (Non-Executable)" in source
    assert "Reject Candidate" in source
    assert "Validate Pre-Submit (Non-Executable)" in source
    for forbidden in ("controlled-submit", "controlled-manage", ".order" + "_send("):
        assert forbidden not in source


def test_confirmed_candidate_requires_a_separate_pre_submit_click(monkeypatch):
    controller = SimpleNamespace(
        confirmation_service=SimpleNamespace(
            policy=SimpleNamespace(confirmation_phrase="CONFIRM")
        ),
        current_outcome=lambda _reference: review_ui.OperatorCandidateReviewOutcome(
            "candidate-1", "CONFIRMED_FOR_PROPOSAL_WORKFLOW", "CONFIRMED", "review-1"
        ),
        current_pre_submit_outcome=lambda _reference: None,
        advance_calls=[],
    )
    controller.advance_to_pre_submit = lambda session, reference: controller.advance_calls.append(
        (session, reference)
    )

    fake = ConfirmationControlStreamlit()
    monkeypatch.setattr(review_ui, "st", fake)

    review_ui.render_autonomous_candidate_confirmation_controls(
        "candidate-1", controller, key_prefix="test_"
    )
    assert controller.advance_calls == []

    fake.clicked.add("Validate Pre-Submit (Non-Executable)")
    review_ui.render_autonomous_candidate_confirmation_controls(
        "candidate-1", controller, key_prefix="test_"
    )
    assert len(controller.advance_calls) == 1


class FakeColumn:
    def __init__(self, owner):
        self.owner = owner

    def metric(self, label, value, **_kwargs):
        self.owner.metrics.append((label, value))


class ConfirmationControlColumn(FakeColumn):
    def button(self, label, **_kwargs):
        return label in self.owner.clicked


class FakeStreamlit:
    def __init__(self):
        self.metrics = []
        self.infos = []
        self.buttons = 0

    def markdown(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def info(self, message, **_kwargs):
        self.infos.append(message)

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def success(self, *_args, **_kwargs):
        return None

    def metric(self, label, value, **_kwargs):
        self.metrics.append((label, value))

    def columns(self, count):
        return [FakeColumn(self) for _ in range(count)]


class ConfirmationControlStreamlit(FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.clicked = set()
        self.session_state = {}

    def text_input(self, *_args, **_kwargs):
        return ""

    def button(self, label, **_kwargs):
        return label in self.clicked

    def columns(self, count):
        return [ConfirmationControlColumn(self) for _ in range(count)]
