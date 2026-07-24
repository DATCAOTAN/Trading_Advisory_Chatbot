from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, service
from scripts.test_structured_market_pending_order_candidate import (
    market_snapshot,
    structured_inputs,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.pending_order_dry_run import (
    PENDING_ORDER_CONTRACT_SCHEMA_VERSION,
    PENDING_ORDER_DRY_RUN_SCHEMA_VERSION,
    ControlledPendingOrderDryRunMapper,
    SUPPORTED_PENDING_ORDER_TYPES,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.proposal.models import HumanConfirmedProposalIntent
from src.services.trading.review.models import HumanReviewArtifact


FINGERPRINT = "a" * 64
PHRASE = "I confirm this reviewed proposal remains dry-run only"


def candidate_for(tmp_path, order_type="BUY_LIMIT", **changes):
    orchestrator = service(tmp_path)
    candidate = orchestrator.build_candidate(
        structured_inputs(order_type, **changes), now=NOW
    )
    return orchestrator, candidate


def review_for(candidate, **changes):
    values = {
        "artifact_id": "pending_review_fixture",
        "created_at": NOW.isoformat(),
        "mode": "REVIEW_ONLY",
        "symbol": candidate.symbol_reference,
        "broker_symbol": candidate.symbol_reference,
        "review_status": "READY_FOR_REVIEW",
        "readiness_action": "REVIEW_READY",
        "blockers": [],
        "source_refs": [
            candidate.candidate_reference,
            candidate.provenance_hash,
            candidate.structured_order_hash,
        ],
    }
    values.update(changes)
    return HumanReviewArtifact(**values)


def confirmation_for(candidate, review, **changes):
    values = {
        "intent_id": "pending_confirmation_fixture",
        "created_at": NOW.isoformat(),
        "mode": "REVIEW_ONLY",
        "symbol": candidate.symbol_reference,
        "broker_symbol": candidate.symbol_reference,
        "proposal_boundary_status": "CONFIRMED_FOR_PROPOSAL_WORKFLOW",
        "human_confirmation_state": "CONFIRMED_PROPOSAL_WORKFLOW",
        "proposal_workflow_allowed": True,
        "dry_run_only": True,
        "executable": False,
        "confirmation_phrase_required": PHRASE,
        "confirmation_phrase_received": PHRASE,
        "review_status": "READY_FOR_REVIEW",
        "dry_run_allowed": True,
        "artifact_id": review.artifact_id,
        "artifact_hash": "reviewed-artifact-hash",
        "idempotency_key": "proposal-dry-run-idempotency",
        "source_review_artifact_id": review.artifact_id,
        "source_refs": [
            candidate.candidate_reference,
            candidate.provenance_hash,
            candidate.structured_order_hash,
        ],
    }
    values.update(changes)
    return HumanConfirmedProposalIntent(**values)


def account_context(**changes):
    values = {
        "status": "OK",
        "account_context_fingerprint": FINGERPRINT,
        "account_id_hash": "b" * 64,
        "server_redacted": "server-***",
        "currency": "USD",
        "trade_mode": "DEMO",
        "redacted": True,
        "captured_at": NOW.isoformat(),
    }
    values.update(changes)
    return ProtectedAccountContextCapture(**values)


def build_result(tmp_path, order_type="BUY_LIMIT", *, snapshot=None, candidate=None, **changes):
    if candidate is None:
        orchestrator, candidate = candidate_for(tmp_path, order_type, **changes)
    else:
        orchestrator = service(tmp_path)
    selected_snapshot = snapshot or market_snapshot()
    review = review_for(candidate)
    confirmation = confirmation_for(candidate, review)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=selected_snapshot,
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    return result, candidate, review, confirmation


@pytest.mark.parametrize("order_type", SUPPORTED_PENDING_ORDER_TYPES)
def test_all_supported_pending_types_create_typed_valid_contracts(tmp_path, order_type):
    result, candidate, _, _ = build_result(tmp_path, order_type)
    assert result.validation.valid
    assert result.contract.schema_version == PENDING_ORDER_CONTRACT_SCHEMA_VERSION
    assert result.contract.candidate_reference == candidate.candidate_reference
    assert result.contract.order_type == order_type
    assert result.contract.action == "PENDING"
    assert result.contract.validation_status == "VALID"
    assert result.request_draft is not None
    assert result.request_draft.schema_version == PENDING_ORDER_DRY_RUN_SCHEMA_VERSION


@pytest.mark.parametrize("order_type", ["BUY_STOP_LIMIT", "SELL_STOP_LIMIT"])
def test_stop_limit_keeps_trigger_and_limit_separate(tmp_path, order_type):
    result, candidate, _, _ = build_result(tmp_path, order_type)
    draft = result.request_draft
    assert draft is not None
    assert draft.trigger_price == candidate.trigger_price
    assert draft.limit_price == candidate.limit_price
    assert draft.trigger_price != draft.limit_price
    assert draft.entry_price == ""


def test_deterministic_action_is_pending(tmp_path):
    result, _, _, _ = build_result(tmp_path, "SELL_STOP")
    assert result.contract.action == "PENDING"
    assert result.request_draft is not None
    assert result.request_draft.action == "PENDING"


def test_missing_required_entry_price_is_blocked(tmp_path):
    result, _, _, _ = build_result(tmp_path, "BUY_LIMIT", entry_price=None)
    assert not result.validation.valid
    assert "REQUIRED_ENTRY_PRICE_MISSING" in result.validation.blockers
    assert result.request_draft is None


@pytest.mark.parametrize(
    ("field_name", "reason"),
    [
        ("trigger_price", "REQUIRED_TRIGGER_PRICE_MISSING"),
        ("limit_price", "REQUIRED_LIMIT_PRICE_MISSING"),
    ],
)
def test_missing_stop_limit_component_is_blocked(tmp_path, field_name, reason):
    result, _, _, _ = build_result(
        tmp_path, "BUY_STOP_LIMIT", **{field_name: None}
    )
    assert not result.validation.valid
    assert reason in result.validation.blockers
    assert result.request_draft is None


def test_invalid_bid_ask_relationship_is_blocked(tmp_path):
    orchestrator = service(tmp_path)
    bad_snapshot = market_snapshot(bid="102", ask="101")
    candidate = orchestrator.build_candidate(
        replace(structured_inputs("BUY_LIMIT"), order_market_snapshot=bad_snapshot),
        now=NOW,
    )
    review = review_for(candidate)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=bad_snapshot,
        review_artifact=review,
        confirmation_intent=confirmation_for(candidate, review),
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert not result.validation.valid
    assert "MARKET_BID_ASK_INVALID" in result.validation.blockers
    assert result.request_draft is None


@pytest.mark.parametrize(
    ("entry_price", "reason"),
    [
        ("101.0", "BUY_LIMIT_PRICE_NOT_BELOW_ASK"),
        ("100.9", "PENDING_PRICE_INSIDE_MINIMUM_DISTANCE"),
    ],
)
def test_equal_or_too_close_market_price_is_blocked(tmp_path, entry_price, reason):
    result, _, _, _ = build_result(tmp_path, "BUY_LIMIT", entry_price=entry_price)
    assert not result.validation.valid
    assert reason in result.validation.blockers


def test_tick_size_validation_uses_symbol_metadata(tmp_path):
    result, _, _, _ = build_result(tmp_path, "BUY_LIMIT", entry_price="100.55")
    assert not result.validation.valid
    assert "ENTRY_PRICE_NOT_ON_TICK_SIZE" in result.validation.blockers


@pytest.mark.parametrize("field_name", ["point", "tick_size", "digits", "minimum_distance_points"])
def test_missing_symbol_metadata_fails_closed(tmp_path, field_name):
    orchestrator, candidate = candidate_for(tmp_path, "BUY_LIMIT")
    incomplete = replace(market_snapshot(), **{field_name: None})
    review = review_for(candidate)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=incomplete,
        review_artifact=review,
        confirmation_intent=confirmation_for(candidate, review),
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert not result.validation.valid
    assert "SYMBOL_METADATA_MISSING_OR_INVALID" in result.validation.blockers


@pytest.mark.parametrize(
    ("order_type", "changes", "reason"),
    [
        ("BUY_STOP", {"stop_loss": "102"}, "BUY_STOP_LOSS_NOT_BELOW_REFERENCE"),
        ("BUY_STOP", {"take_profit": "101"}, "BUY_TAKE_PROFIT_NOT_ABOVE_REFERENCE"),
        ("SELL_STOP", {"stop_loss": "99"}, "SELL_STOP_LOSS_NOT_ABOVE_REFERENCE"),
        ("SELL_STOP", {"take_profit": "100"}, "SELL_TAKE_PROFIT_NOT_BELOW_REFERENCE"),
    ],
)
def test_invalid_protection_direction_is_blocked(tmp_path, order_type, changes, reason):
    result, _, _, _ = build_result(tmp_path, order_type, **changes)
    assert not result.validation.valid
    assert reason in result.validation.blockers


def test_missing_authoritative_volume_and_risk_reference_is_blocked(tmp_path):
    result, _, _, _ = build_result(
        tmp_path,
        "BUY_LIMIT",
        proposed_volume=None,
        risk_policy_reference="",
    )
    assert not result.validation.valid
    assert "AUTHORITATIVE_VOLUME_OR_RISK_REFERENCE_MISSING" in result.validation.blockers


def test_stale_candidate_is_blocked(tmp_path):
    orchestrator, candidate = candidate_for(tmp_path, "BUY_LIMIT")
    stale = replace(candidate, expires_at=(NOW - timedelta(seconds=1)).isoformat())
    review = review_for(stale)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=stale,
        market_snapshot=market_snapshot(),
        review_artifact=review,
        confirmation_intent=confirmation_for(stale, review),
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert "CANDIDATE_EXPIRED" in result.validation.blockers
    assert result.request_draft is None


def test_stale_market_snapshot_is_blocked(tmp_path):
    stale_snapshot = market_snapshot(observed_at=(NOW - timedelta(hours=1)).isoformat())
    result, _, _, _ = build_result(tmp_path, "BUY_LIMIT", snapshot=stale_snapshot)
    assert not result.validation.valid
    assert "MARKET_SNAPSHOT_STALE" in result.validation.blockers


def test_account_context_mismatch_is_blocked(tmp_path):
    orchestrator, candidate = candidate_for(tmp_path, "BUY_LIMIT")
    review = review_for(candidate)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=market_snapshot(),
        review_artifact=review,
        confirmation_intent=confirmation_for(candidate, review),
        account_context=account_context(),
        expected_account_context_fingerprint="c" * 64,
        now=NOW,
    )
    assert not result.validation.valid
    assert "ACCOUNT_CONTEXT_MISMATCH" in result.validation.blockers


def test_post_review_parameter_mutation_invalidates_integrity(tmp_path):
    orchestrator, candidate = candidate_for(tmp_path, "BUY_LIMIT")
    review = review_for(candidate)
    confirmation = confirmation_for(candidate, review)
    mutated = replace(candidate, entry_price="100.4")
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=mutated,
        market_snapshot=market_snapshot(),
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert not result.validation.valid
    assert "STRUCTURED_ORDER_HASH_INVALID" in result.validation.blockers
    assert result.request_draft is None


def test_review_and_confirmation_must_bind_candidate_integrity(tmp_path):
    orchestrator, candidate = candidate_for(tmp_path, "BUY_LIMIT")
    review = review_for(candidate, source_refs=[candidate.candidate_reference])
    confirmation = confirmation_for(
        candidate, review, source_refs=[candidate.candidate_reference]
    )
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=market_snapshot(),
        review_artifact=review,
        confirmation_intent=confirmation,
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert "HUMAN_REVIEW_CANDIDATE_BINDING_MISMATCH" in result.validation.blockers
    assert "CONFIRMATION_CANDIDATE_BINDING_MISMATCH" in result.validation.blockers


def test_identical_canonical_inputs_produce_identical_hashes(tmp_path):
    first, _, _, _ = build_result(tmp_path / "first", "BUY_LIMIT")
    second, _, _, _ = build_result(tmp_path / "second", "BUY_LIMIT")
    assert first.contract.canonical_integrity_hash == second.contract.canonical_integrity_hash
    assert first.contract.idempotency_key == second.contract.idempotency_key
    assert first.request_draft is not None and second.request_draft is not None
    assert first.request_draft.semantic_request_hash == second.request_draft.semantic_request_hash


def test_changed_price_changes_integrity_hash(tmp_path):
    first, _, _, _ = build_result(tmp_path / "first", "BUY_LIMIT", entry_price="100.5")
    second, _, _, _ = build_result(tmp_path / "second", "BUY_LIMIT", entry_price="100.4")
    assert first.validation.valid and second.validation.valid
    assert first.contract.canonical_integrity_hash != second.contract.canonical_integrity_hash


def test_public_serialization_is_redacted_and_safety_flags_are_false(tmp_path):
    result, _, _, _ = build_result(tmp_path, "BUY_STOP_LIMIT")
    payload = json.dumps(result.to_public_dict(), sort_keys=True)
    for secret_value in ("101.5", "101.2", "100.0", "103.0", "0.01", FINGERPRINT):
        assert secret_value not in payload
    assert '"symbol_present": true' in payload
    assert result.request_draft is not None
    for artifact in (result.contract, result.request_draft):
        assert artifact.execution_authority is False
        assert artifact.execution_permission_requested is False
        assert artifact.live_submission_allowed is False
        assert artifact.live_execution_allowed is False
        assert artifact.order_send_allowed is False
        assert artifact.execution_allowed is False
        assert artifact.executable is False
        assert artifact.order_sent is False


def test_market_candidate_remains_valid_but_is_not_silently_converted(tmp_path):
    orchestrator, candidate = candidate_for(tmp_path, "BUY")
    assert orchestrator.validate_candidate(candidate, now=NOW).valid
    assert candidate.action == "MARKET"
    review = review_for(candidate)
    result = ControlledPendingOrderDryRunMapper(orchestrator).build(
        candidate=candidate,
        market_snapshot=market_snapshot(),
        review_artifact=review,
        confirmation_intent=confirmation_for(candidate, review),
        account_context=account_context(),
        expected_account_context_fingerprint=FINGERPRINT,
        now=NOW,
    )
    assert "PENDING_ACTION_REQUIRED" in result.validation.blockers
    assert "UNSUPPORTED_PENDING_ORDER_TYPE" in result.validation.blockers
    assert result.contract.action == "MARKET"
    assert result.request_draft is None


def test_valid_dry_run_has_no_bridge_or_broker_artifact(tmp_path):
    result, _, _, _ = build_result(tmp_path, "SELL_STOP_LIMIT")
    draft = result.request_draft
    assert draft is not None
    assert draft.real_mt5_payload_created is False
    assert draft.broker_submittable_request_dict_created is False
    assert draft.mt5_constants_used is False
    assert draft.bridge_request_created is False
    assert not (tmp_path / "execution_journal.jsonl").exists()
    source = Path(
        "src/services/trading/execution/mt5_live_adapter_pre_submit/pending_order_dry_run.py"
    ).read_text(encoding="utf-8")
    assert "/execution/controlled-submit" not in source
    assert "/execution/controlled-manage" not in source
    assert "Meta" + "Trader5" not in source
    assert ".order_" + "send(" not in source
