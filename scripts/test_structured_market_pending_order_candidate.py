from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from scripts.test_autonomous_decision_orchestrator import (
    NOW,
    SOURCE_REF,
    make_inputs,
    mapping_for_cli,
    service,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    AutonomousEntryIntent,
    AutonomousOrderAction,
    AutonomousOrderIntentProposal,
    AutonomousOrderMarketSnapshot,
    AutonomousOrderSide,
    AutonomousOrderType,
    autonomous_inputs_from_mapping,
    resolve_autonomous_order_action,
)


def market_snapshot(**changes):
    values = {
        "snapshot_reference": "market-tick-fixture",
        "observed_at": NOW.isoformat(),
        "symbol": "TEST_SYMBOL",
        "bid": "100.0",
        "ask": "101.0",
        "provider_name": "mt5_bridge",
        "point": "0.1",
        "tick_size": "0.1",
        "digits": 1,
        "minimum_distance_points": "2",
        "source_refs": (SOURCE_REF,),
    }
    values.update(changes)
    return AutonomousOrderMarketSnapshot(**values)


def proposal(order_type="BUY", **changes):
    defaults = {
        "BUY": {
            "side": "BUY",
            "entry_intent": "IMMEDIATE",
            "stop_loss": "99.0",
            "take_profit": "102.0",
        },
        "SELL": {
            "side": "SELL",
            "entry_intent": "IMMEDIATE",
            "stop_loss": "102.0",
            "take_profit": "99.0",
        },
        "BUY_LIMIT": {
            "side": "BUY",
            "entry_intent": "PULLBACK",
            "entry_price": "100.5",
            "stop_loss": "99.0",
            "take_profit": "102.0",
        },
        "SELL_LIMIT": {
            "side": "SELL",
            "entry_intent": "PULLBACK",
            "entry_price": "101.5",
            "stop_loss": "103.0",
            "take_profit": "99.0",
        },
        "BUY_STOP": {
            "side": "BUY",
            "entry_intent": "BREAKOUT",
            "entry_price": "101.5",
            "stop_loss": "100.0",
            "take_profit": "103.0",
        },
        "SELL_STOP": {
            "side": "SELL",
            "entry_intent": "BREAKOUT",
            "entry_price": "99.5",
            "stop_loss": "101.0",
            "take_profit": "98.0",
        },
        "BUY_STOP_LIMIT": {
            "side": "BUY",
            "entry_intent": "STOP_LIMIT",
            "trigger_price": "101.5",
            "limit_price": "101.2",
            "stop_loss": "100.0",
            "take_profit": "103.0",
        },
        "SELL_STOP_LIMIT": {
            "side": "SELL",
            "entry_intent": "STOP_LIMIT",
            "trigger_price": "99.5",
            "limit_price": "99.8",
            "stop_loss": "101.0",
            "take_profit": "98.0",
        },
    }
    values = {
        "symbol": "TEST_SYMBOL",
        "order_type": order_type,
        "proposed_volume": "0.01",
        "risk_policy_reference": "risk-policy-fixture",
        "structured_reasoning": ("method-aligned", "risk-reviewed"),
        **defaults[order_type],
    }
    values.update(changes)
    return AutonomousOrderIntentProposal(**values)


def structured_inputs(order_type="BUY", **proposal_changes):
    side = "SELL" if order_type.startswith("SELL") else "BUY"
    return replace(
        make_inputs(),
        direction=side,
        order_proposal=proposal(order_type, **proposal_changes),
        order_market_snapshot=market_snapshot(),
    )


def build(tmp_path, inputs):
    return service(tmp_path).run_once(inputs, now=NOW)


def test_supported_structured_order_contract_values_are_exact():
    assert {item.value for item in AutonomousOrderSide} == {"BUY", "SELL"}
    assert {item.value for item in AutonomousEntryIntent} == {
        "IMMEDIATE",
        "PULLBACK",
        "BREAKOUT",
        "STOP_LIMIT",
    }
    assert {item.value for item in AutonomousOrderType} == {
        "BUY",
        "SELL",
        "BUY_LIMIT",
        "SELL_LIMIT",
        "BUY_STOP",
        "SELL_STOP",
        "BUY_STOP_LIMIT",
        "SELL_STOP_LIMIT",
    }
    assert {item.value for item in AutonomousOrderAction} == {"MARKET", "PENDING"}


@pytest.mark.parametrize("order_type", ["BUY", "SELL"])
def test_market_order_types_resolve_to_market(tmp_path, order_type):
    result = build(tmp_path, structured_inputs(order_type))
    assert result.validation.valid
    assert result.candidate.intent == "OPEN_POSITION"
    assert result.candidate.action == "MARKET"
    assert result.candidate.entry_intent == "IMMEDIATE"


@pytest.mark.parametrize(
    "order_type",
    [
        "BUY_LIMIT",
        "SELL_LIMIT",
        "BUY_STOP",
        "SELL_STOP",
        "BUY_STOP_LIMIT",
        "SELL_STOP_LIMIT",
    ],
)
def test_pending_order_types_resolve_to_pending_and_remain_non_executable(tmp_path, order_type):
    result = build(tmp_path, structured_inputs(order_type))
    candidate = result.candidate
    assert result.validation.valid
    assert candidate.intent == "OPEN_POSITION"
    assert candidate.action == "PENDING"
    assert candidate.market_recommendation == "PENDING_PRICE_RELATION_VALID"
    assert candidate.execution_authority is False
    assert candidate.live_submission_allowed is False
    assert candidate.order_send_allowed is False
    assert candidate.execution_allowed is False
    assert candidate.executable is False
    assert candidate.order_sent is False


@pytest.mark.parametrize(
    ("order_type", "entry_price", "reason"),
    [
        ("BUY_LIMIT", "101.0", "BUY_LIMIT_PRICE_NOT_BELOW_ASK"),
        ("SELL_LIMIT", "100.0", "SELL_LIMIT_PRICE_NOT_ABOVE_BID"),
        ("BUY_STOP", "101.0", "BUY_STOP_PRICE_NOT_ABOVE_ASK"),
        ("SELL_STOP", "100.0", "SELL_STOP_PRICE_NOT_BELOW_BID"),
    ],
)
def test_equal_or_wrong_side_pending_prices_block_without_silent_conversion(
    tmp_path, order_type, entry_price, reason
):
    result = build(tmp_path, structured_inputs(order_type, entry_price=entry_price))
    candidate = result.candidate
    assert reason in candidate.blocked_reason_codes
    assert candidate.action == "PENDING"
    assert candidate.market_recommendation == "MARKET_ORDER_REVIEW_RECOMMENDED"
    assert candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE"


def test_minimum_distance_metadata_blocks_near_pending_price(tmp_path):
    result = build(tmp_path, structured_inputs("BUY_STOP", entry_price="101.1"))
    assert "PENDING_PRICE_INSIDE_MINIMUM_DISTANCE" in result.candidate.blocked_reason_codes
    assert result.candidate.action == "PENDING"


@pytest.mark.parametrize(
    ("order_type", "changes", "reason"),
    [
        ("BUY_STOP_LIMIT", {"trigger_price": None}, "REQUIRED_TRIGGER_PRICE_MISSING"),
        ("SELL_STOP_LIMIT", {"limit_price": None}, "REQUIRED_LIMIT_PRICE_MISSING"),
        (
            "BUY_STOP_LIMIT",
            {"trigger_price": "101.5", "limit_price": "101.6"},
            "BUY_STOP_LIMIT_LIMIT_NOT_BELOW_TRIGGER",
        ),
        (
            "SELL_STOP_LIMIT",
            {"trigger_price": "99.5", "limit_price": "99.4"},
            "SELL_STOP_LIMIT_LIMIT_NOT_ABOVE_TRIGGER",
        ),
    ],
)
def test_stop_limit_requires_distinct_valid_trigger_and_limit_prices(
    tmp_path, order_type, changes, reason
):
    result = build(tmp_path, structured_inputs(order_type, **changes))
    assert reason in result.candidate.blocked_reason_codes
    assert result.candidate.action == "PENDING"


def test_llm_advisory_action_cannot_override_deterministic_action(tmp_path):
    result = build(
        tmp_path,
        structured_inputs("BUY_LIMIT", proposed_action="MARKET"),
    )
    assert result.candidate.action == "PENDING"
    assert result.candidate.advisory_action == "MARKET"
    assert (
        "ADVISORY_ACTION_CONTRADICTS_RESOLVED_ACTION"
        in result.candidate.blocked_reason_codes
    )


def test_side_and_entry_intent_contradictions_are_blocked(tmp_path):
    result = build(
        tmp_path,
        structured_inputs("BUY_LIMIT", side="SELL", entry_intent="BREAKOUT"),
    )
    assert "ORDER_SIDE_MISMATCH" in result.candidate.blocked_reason_codes
    assert "ENTRY_INTENT_MISMATCH" in result.candidate.blocked_reason_codes


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (market_snapshot(symbol="OTHER"), "MARKET_SNAPSHOT_SYMBOL_MISMATCH"),
        (
            market_snapshot(observed_at=(NOW - timedelta(hours=1)).isoformat()),
            "MARKET_SNAPSHOT_STALE",
        ),
    ],
)
def test_market_snapshot_mismatch_or_staleness_blocks(tmp_path, snapshot, reason):
    inputs = replace(structured_inputs("BUY_LIMIT"), order_market_snapshot=snapshot)
    result = build(tmp_path, inputs)
    assert reason in result.candidate.blocked_reason_codes


def test_invalid_numeric_value_is_preserved_internally_and_blocked(tmp_path):
    result = build(
        tmp_path,
        structured_inputs("BUY_LIMIT", entry_price="not-a-number"),
    )
    assert result.candidate.entry_price == "not-a-number"
    assert "INVALID_ENTRY_PRICE" in result.candidate.blocked_reason_codes


def test_public_serialization_redacts_prices_volume_side_and_reasoning(tmp_path):
    candidate = build(tmp_path, structured_inputs("BUY_STOP_LIMIT")).candidate
    payload = json.dumps(candidate.to_public_dict(), sort_keys=True)
    assert "101.5" not in payload
    assert "101.2" not in payload
    assert "0.01" not in payload
    assert "method-aligned" not in payload
    assert '"side":' not in payload
    assert '"direction":' not in payload
    assert '"order_type": "BUY_STOP_LIMIT"' in payload
    assert '"action": "PENDING"' in payload


def test_structured_order_hash_detects_candidate_value_tampering(tmp_path):
    orchestrator = service(tmp_path)
    candidate = orchestrator.build_candidate(structured_inputs("BUY_LIMIT"), now=NOW)
    tampered = replace(candidate, entry_price="99.9")
    validation = orchestrator.validate_candidate(tampered, now=NOW)
    assert not validation.valid
    assert "STRUCTURED_ORDER_HASH_INVALID" in validation.issues


def test_legacy_open_candidate_without_order_proposal_remains_valid(tmp_path):
    result = build(tmp_path, make_inputs())
    assert result.validation.valid
    assert result.candidate.intent == "OPEN_POSITION"
    assert result.candidate.order_type == ""
    assert result.candidate.structured_order_hash == ""


def test_mapping_accepts_json_numbers_and_strings_without_trusting_action():
    payload = mapping_for_cli(make_inputs())
    payload["order_proposal"] = {
        "symbol": "TEST_SYMBOL",
        "side": "BUY",
        "entry_intent": "PULLBACK",
        "order_type": "BUY_LIMIT",
        "action": "MARKET",
        "entry_price": 100.5,
        "stop_loss": "99.0",
        "take_profit": 102,
        "proposed_volume": "0.01",
        "risk_policy_reference": "risk-policy-fixture",
        "structured_reasoning": ["method-aligned"],
    }
    payload["order_market_snapshot"] = {
        "snapshot_reference": "market-tick-fixture",
        "observed_at": NOW.isoformat(),
        "symbol": "TEST_SYMBOL",
        "bid": 100,
        "ask": "101.0",
        "point": "0.1",
        "tick_size": 0.1,
        "digits": 1,
        "minimum_distance_points": 2,
        "source_refs": [SOURCE_REF],
    }
    inputs = autonomous_inputs_from_mapping(payload)
    candidate = AutonomousDecisionOrchestrator().build_candidate(inputs, now=NOW)
    assert resolve_autonomous_order_action(candidate.order_type) == "PENDING"
    assert candidate.action == "PENDING"
    assert "ADVISORY_ACTION_CONTRADICTS_RESOLVED_ACTION" in candidate.blocked_reason_codes


def test_changed_structured_price_changes_provenance(tmp_path):
    orchestrator = service(tmp_path)
    first = orchestrator.build_candidate(structured_inputs("BUY_LIMIT"), now=NOW)
    second = orchestrator.build_candidate(
        structured_inputs("BUY_LIMIT", entry_price="100.4"), now=NOW
    )
    assert first.provenance_hash != second.provenance_hash
    assert first.structured_order_hash != second.structured_order_hash


def test_decision_files_contain_no_execution_or_bridge_mutation_call():
    paths = [
        Path("src/services/trading/decision/autonomous_orchestrator.py"),
        Path("src/services/trading/decision/autonomous_execution_policy.py"),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert ".order" + "_send(" not in source
    assert "controlled" + "-submit" not in source.lower()
    assert "controlled" + "-manage" not in source.lower()
    assert "Meta" + "Trader5" not in source
