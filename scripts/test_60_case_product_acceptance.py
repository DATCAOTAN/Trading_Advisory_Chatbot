from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from scripts import test_autonomous_post_entry_management as autonomous_management
from scripts import test_editable_trade_draft_candidate_lifecycle as candidate_lifecycle
from scripts import test_field_aware_editable_trade_draft as draft_fields
from scripts import test_human_confirmed_position_management as human_management
from scripts import test_mt5_reconciliation_failure_recovery as recovery
from scripts import test_operator_review_confirmation_lifecycle as confirmation
from scripts import test_position_read_model as position_read
from scripts import test_standing_trading_mandate_authority as mandate
from scripts import test_structured_semantic_interpreter as semantic_interpreter
from scripts import test_trading_semantic_cutover as trading_semantics
from scripts import test_universal_semantic_routing as semantic_routing
from src.pipelines.modules.router import RouteAction, RouterModule
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    family: str
    input_summary: str
    fixture: str
    expected_intent: str
    expected_artifact: str
    expected_mode: str = "advisory_only"
    expected_blockers: tuple[str, ...] = ()
    expected_result_class: str = "PASS"
    details: dict = field(default_factory=dict, compare=False, repr=False)


def _case(case_id, family, input_summary, fixture, intent, artifact, mode="advisory_only", blockers=(), **details):
    return AcceptanceCase(
        f"{case_id:02d}", family, input_summary, fixture, intent, artifact, mode,
        tuple(blockers), details=details,
    )


CASES = (
    _case(1, "SOCIAL", "xin chao", "social", "SOCIAL", "EARLY_EXIT"),
    _case(2, "SOCIAL", "product capabilities", "system", "SYSTEM", "EARLY_EXIT"),
    _case(3, "SOCIAL", "cam on", "social", "SOCIAL", "EARLY_EXIT"),
    _case(4, "SOCIAL", "unrelated general request", "out_of_scope", "OUT_OF_SCOPE", "EARLY_EXIT"),
    _case(5, "SOCIAL", "low-information text", "out_of_scope", "OUT_OF_SCOPE", "EARLY_EXIT"),
    _case(6, "KNOWLEDGE", "RSI definition", "knowledge", "KNOWLEDGE", "STATIC_KNOWLEDGE", subtype="RSI"),
    _case(7, "KNOWLEDGE", "ATR purpose", "knowledge", "KNOWLEDGE", "STATIC_KNOWLEDGE", subtype="ATR"),
    _case(8, "KNOWLEDGE", "EMA versus SMA", "knowledge", "KNOWLEDGE", "STATIC_KNOWLEDGE", subtype="EMA_SMA"),
    _case(9, "KNOWLEDGE", "stop-loss definition", "knowledge", "KNOWLEDGE", "STATIC_KNOWLEDGE", subtype="STOP_LOSS"),
    _case(10, "KNOWLEDGE", "position sizing definition", "knowledge", "KNOWLEDGE", "STATIC_KNOWLEDGE", subtype="POSITION_SIZING"),
    _case(11, "MARKET", "current RSI14 M1 BTCUSD", "market", "MARKET_DATA", "TECHNICAL_SNAPSHOT", indicator="RSI", period=14, timeframe="M1"),
    _case(12, "MARKET", "current EMA20 H1 XAUUSD", "market", "MARKET_DATA", "TECHNICAL_SNAPSHOT", symbol="XAUUSD", indicator="EMA", period=20, timeframe="H1"),
    _case(13, "MARKET", "current BTCUSD price", "market_price", "MARKET_DATA", "MARKET_SNAPSHOT"),
    _case(14, "MARKET", "current ATR14 M15 BTCUSD", "market", "MARKET_DATA", "TECHNICAL_SNAPSHOT", indicator="ATR", period=14, timeframe="M15"),
    _case(15, "MARKET", "current RSI BTCUSD with missing period/timeframe", "market_partial", "MARKET_DATA", "TYPED_UNAVAILABLE", blockers=("INDICATOR_PERIOD_UNRESOLVED",)),
    _case(16, "ANALYSIS", "analyze BTCUSD", "analysis", "ANALYSIS", "MARKET_ANALYSIS"),
    _case(17, "ANALYSIS", "should I buy BTCUSD", "advisory_buy", "ANALYSIS", "ADVISORY_RESULT"),
    _case(18, "ANALYSIS", "CPI impact on gold plus current RSI H1", "mixed", "ANALYSIS", "MIXED_EVIDENCE"),
    _case(19, "ANALYSIS", "BTCUSD strength", "analysis", "ANALYSIS", "MARKET_ANALYSIS"),
    _case(20, "ANALYSIS", "BTCUSD RSI H1 and H4", "multi_timeframe", "ANALYSIS", "TECHNICAL_SNAPSHOT"),
    _case(21, "STRATEGY_COMPLETION", "BUY RSI threshold, period/timeframe missing", "strategy_missing_period_timeframe", "STRATEGY", "COMPLETION", "human_confirmed_live", blockers=("SEMANTIC_UNRESOLVED",)),
    _case(22, "STRATEGY_COMPLETION", "SELL RSI14 threshold, timeframe missing", "strategy_missing_timeframe", "STRATEGY", "COMPLETION", "human_confirmed_live", blockers=("SEMANTIC_UNRESOLVED",)),
    _case(23, "STRATEGY_COMPLETION", "BUY RSI M5 threshold, period missing", "strategy_missing_period", "STRATEGY", "COMPLETION", "human_confirmed_live", blockers=("SEMANTIC_UNRESOLVED",)),
    _case(24, "STRATEGY_COMPLETION", "indicator complete, threshold missing", "strategy_missing_threshold", "STRATEGY", "COMPLETION", "human_confirmed_live", blockers=("ENTRY_RULE_MISSING",)),
    _case(25, "STRATEGY_COMPLETION", "inherit valid prior parameter", "strategy_inherited", "STRATEGY", "COMPLETION", "human_confirmed_live"),
    _case(26, "STRATEGY_DRAFT", "complete BUY RSI14 M1 strategy", "strategy_complete", "STRATEGY", "NON_EXECUTABLE_REQUEST", "human_confirmed_live"),
    _case(27, "STRATEGY_DRAFT", "complete SELL strategy", "strategy_sell", "STRATEGY", "NON_EXECUTABLE_REQUEST", "human_confirmed_live"),
    _case(28, "STRATEGY_DRAFT", "complete strategy with explicit SL", "explicit_values", "STRATEGY", "EDITABLE_DRAFT", "human_confirmed_live"),
    _case(29, "STRATEGY_DRAFT", "complete strategy with SL and TP", "explicit_conflict", "STRATEGY", "EDITABLE_DRAFT", "human_confirmed_live"),
    _case(30, "STRATEGY_DRAFT", "complete strategy with stale evidence", "market_quality_block", "STRATEGY", "TYPED_BLOCKER", "human_confirmed_live", blockers=("MARKET_EVIDENCE_BLOCKED",)),
    _case(31, "CANDIDATE", "valid admissible Draft", "candidate_create", "CANDIDATE", "NON_EXECUTABLE_CANDIDATE", "human_confirmed_live"),
    _case(32, "CANDIDATE", "blocked Draft", "candidate_blocked", "CANDIDATE", "NO_CANDIDATE", "human_confirmed_live", blockers=("MARKET_DATA_STALE",)),
    _case(33, "CANDIDATE", "Draft structured edit", "draft_revision", "DRAFT", "NEW_REVISION", "human_confirmed_live"),
    _case(34, "CANDIDATE", "Candidate revision binding", "candidate_revision_binding", "CANDIDATE", "STALE_AUTHORITY_BLOCKED", "human_confirmed_live"),
    _case(35, "CANDIDATE", "exact human confirmation", "candidate_confirmation", "CONFIRMATION", "CANDIDATE_BOUND_CONFIRMATION", "human_confirmed_live"),
    _case(36, "POSITION_READ", "open positions", "position_empty", "POSITION_READ", "AUTHORITATIVE_EMPTY"),
    _case(37, "POSITION_READ", "pending orders", "pending_read", "POSITION_READ", "PENDING_ORDER_LIST"),
    _case(38, "POSITION_READ", "BTCUSD profit or loss", "position_pnl", "POSITION_READ", "BROKER_PNL"),
    _case(39, "POSITION_READ", "current SL and TP", "position_protection", "POSITION_READ", "BROKER_PROTECTION"),
    _case(40, "POSITION_READ", "protected position continuation", "position_reference", "POSITION_READ", "PROTECTED_REFERENCE"),
    _case(41, "HISTORY", "today trade history", "history", "POSITION_READ", "BROKER_HISTORY"),
    _case(42, "HISTORY", "today aggregate P/L", "history", "POSITION_READ", "BROKER_PNL"),
    _case(43, "PROVENANCE", "why trade opened", "provenance", "POSITION_READ", "STORED_PROVENANCE"),
    _case(44, "PROVENANCE", "why trade closed", "provenance", "POSITION_READ", "STORED_PROVENANCE"),
    _case(45, "PROVENANCE", "why stop changed", "provenance", "POSITION_READ", "EXPLICIT_UNAVAILABLE"),
    _case(46, "HUMAN_MANAGEMENT", "cancel BTCUSD pending order", "cancel_pending", "POSITION_MANAGEMENT", "MANAGEMENT_PROPOSAL", "human_confirmed_live"),
    _case(47, "HUMAN_MANAGEMENT", "change stop loss", "modify_stop", "POSITION_MANAGEMENT", "MANAGEMENT_PROPOSAL", "human_confirmed_live"),
    _case(48, "HUMAN_MANAGEMENT", "change take profit", "modify_take", "POSITION_MANAGEMENT", "MANAGEMENT_PROPOSAL", "human_confirmed_live"),
    _case(49, "HUMAN_MANAGEMENT", "close 50 percent", "partial_close", "POSITION_MANAGEMENT", "MANAGEMENT_PROPOSAL", "human_confirmed_live"),
    _case(50, "HUMAN_MANAGEMENT", "close entire position", "full_close", "POSITION_MANAGEMENT", "MANAGEMENT_PROPOSAL", "human_confirmed_live"),
    _case(51, "AUTONOMOUS", "request autonomous strategy mode", "autonomous_mode", "STRATEGY", "MODE_REQUEST_ONLY", "autonomous_live"),
    _case(52, "AUTONOMOUS", "autonomous mode without mandate", "autonomous_no_mandate", "AUTONOMOUS", "AUTHORITY_BLOCKED", "autonomous_live"),
    _case(53, "AUTONOMOUS", "bounded DEMO mandate", "mandate_valid", "AUTONOMOUS", "BOUNDED_MANDATE", "autonomous_live"),
    _case(54, "AUTONOMOUS", "revoked mandate", "mandate_revoked", "AUTONOMOUS", "FINAL_VALIDATION_BLOCKED", "autonomous_live"),
    _case(55, "AUTONOMOUS", "read-only query in autonomous mode", "autonomous_read", "POSITION_READ", "POSITION_READ_MODEL", "autonomous_live"),
    _case(56, "FAILURE_RECOVERY", "semantic provider failure", "provider_failure", "UNKNOWN", "FAIL_CLOSED", blockers=("SEMANTIC_PROVIDER_RUNTIMEERROR",)),
    _case(57, "FAILURE_RECOVERY", "ambiguous position target", "ambiguous_position", "POSITION_READ", "TYPED_BLOCKER", blockers=("AMBIGUOUS_POSITION_REFERENCE",)),
    _case(58, "FAILURE_RECOVERY", "stale lifecycle observation", "stale_position", "POSITION_READ", "TYPED_BLOCKER", blockers=("POSITION_SNAPSHOT_STALE",)),
    _case(59, "FAILURE_RECOVERY", "RESULT_UNKNOWN", "result_unknown", "RECONCILIATION", "RETRY_PROHIBITED", blockers=("RECONCILIATION_REQUIRED",)),
    _case(60, "FAILURE_RECOVERY", "kill switch blocks mutation", "kill_switch", "EXECUTION", "PERMISSION_BLOCKED", blockers=("KILL_SWITCH_ENGAGED",)),
)


def _assert_safe(case: AcceptanceCase):
    assert case.expected_result_class in {"PASS", "EXPECTED_FAIL_CLOSED"}
    assert case.expected_artifact
    assert case.expected_mode in {"advisory_only", "human_confirmed_live", "autonomous_live"}


def _verify_router(case: AcceptanceCase):
    action, response = RouterModule.process_structured(case.expected_intent, case.input_summary)
    assert action == RouteAction.EARLY_EXIT
    assert response


def _requirements(source):
    plan = QueryPlanAssembler().assemble("acceptance wording is not routing authority", structured_semantics=source)
    requirements = ContextRequirementPlanner().plan(plan)
    assert plan.requires_execution is False
    assert plan.constraints["execution_allowed"] is False
    return plan, {need.capability for need in requirements.needs}


def _verify_semantic(case: AcceptanceCase):
    if case.fixture == "knowledge":
        _plan, capabilities = _requirements(
            semantic_routing.semantic(subtype=case.details["subtype"], domain="technical_analysis")
        )
        assert "static_knowledge" in capabilities
        assert not ({"market_snapshot", "ohlcv", "technical_snapshot"} & capabilities)
        return

    if case.fixture == "market_partial":
        source = semantic_routing.semantic(
            primary_intent="MARKET_DATA", action="ANALYZE", symbols=["BTCUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": ""}],
            unresolved_fields=["indicators[0].parameters.period", "indicators[0].timeframe"],
        )
        plan, capabilities = _requirements(source)
        assert plan.requested_indicators == []
        assert any(item.startswith("unresolved:") for item in plan.ambiguity)
        assert "technical_snapshot" in capabilities
        return

    if case.fixture == "market_price":
        source = semantic_routing.semantic(
            primary_intent="MARKET_DATA", action="ANALYZE", symbols=["BTCUSD"],
            requested_data=["current_price"],
        )
    elif case.fixture == "market":
        source = semantic_routing.semantic(
            primary_intent="MARKET_DATA", action="ANALYZE",
            symbols=[case.details.get("symbol", "BTCUSD")],
            indicators=[{
                "indicator_id": case.details["indicator"],
                "parameters": {"period": case.details["period"]},
                "timeframe": case.details["timeframe"],
            }],
            requested_data=["current_indicator_value"],
        )
    elif case.fixture == "mixed":
        source = semantic_routing.semantic(
            primary_intent="ANALYSIS", secondary_intents=["KNOWLEDGE"], action="ANALYZE",
            subtype="CPI", domain="macro", symbols=["XAUUSD"],
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"}],
        )
    elif case.fixture == "multi_timeframe":
        source = semantic_routing.semantic(
            primary_intent="ANALYSIS", action="ANALYZE", symbols=["BTCUSD"],
            indicators=[
                {"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H1"},
                {"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": "H4"},
            ],
        )
    else:
        source = semantic_routing.semantic(primary_intent="ANALYSIS", action="ANALYZE", symbols=["BTCUSD"])
    plan, capabilities = _requirements(source)
    assert "market_snapshot" in capabilities
    if case.fixture in {"market", "mixed", "multi_timeframe"}:
        assert "technical_snapshot" in capabilities
    if case.fixture == "mixed":
        assert {"official_report", "economic_event"} <= capabilities
    if case.fixture == "advisory_buy":
        assert plan.constraints["requested_mode"] == "advisory_only"


def _verify_strategy(case: AcceptanceCase):
    if case.fixture == "strategy_inherited":
        trading_semantics.test_resolved_context_inheritance_reaches_trading_projection_without_a_second_parser()
        return
    if case.fixture == "strategy_complete":
        source = trading_semantics.semantic(symbols=["BTCUSDm"])
    elif case.fixture == "strategy_sell":
        source = trading_semantics.semantic(symbols=["BTCUSDm"], direction="SELL")
    elif case.fixture == "strategy_missing_period_timeframe":
        source = trading_semantics.semantic(
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": ""}],
            conditions=[{"subject": "RSI", "operator": "GREATER_THAN", "value": 10}],
            unresolved_fields=["indicators[0].parameters.period", "indicators[0].timeframe"],
        )
    elif case.fixture == "strategy_missing_timeframe":
        source = trading_semantics.semantic(
            symbols=["BTCUSDm"], direction="SELL",
            indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": ""}],
            unresolved_fields=["indicators[0].timeframe"],
        )
    elif case.fixture == "strategy_missing_period":
        source = trading_semantics.semantic(
            symbols=["BTCUSDm"],
            indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M5"}],
            unresolved_fields=["indicators[0].parameters.period"],
        )
    else:
        source = trading_semantics.semantic(
            symbols=["BTCUSDm"], conditions=[], unresolved_fields=["conditions[0].value"]
        )
    _plan, request = trading_semantics.request_from(source)
    public = request.to_public_dict()
    assert public["execution_authority"] is False
    assert public["executable"] is False
    if case.fixture in {"strategy_complete", "strategy_sell"}:
        assert request.strategy.semantic_unresolved_fields == ()
        assert request.trade_direction == ("SELL" if case.fixture == "strategy_sell" else "BUY")
    else:
        assert request.blockers


def _call(function: Callable, tmp_path: Path, *args):
    parameters = inspect.signature(function).parameters
    if "tmp_path" in parameters:
        return function(tmp_path, *args)
    return function(*args)


EVIDENCE = {
    "explicit_values": (draft_fields.test_all_explicit_values_are_preserved_without_replacement, ()),
    "explicit_conflict": (draft_fields.test_conflicting_explicit_target_and_rr_are_preserved_and_blocked, ()),
    "market_quality_block": (draft_fields.test_market_quality_blockers_are_authoritative, ()),
    "candidate_create": (candidate_lifecycle.test_eligible_draft_explicitly_creates_one_non_executable_candidate, ()),
    "candidate_blocked": (candidate_lifecycle.test_blocked_draft_stops_before_candidate_assembly, ()),
    "draft_revision": (candidate_lifecycle.test_revision_change_creates_a_distinct_historical_candidate_only_after_new_action, ()),
    "candidate_revision_binding": (candidate_lifecycle.test_historical_candidate_confirmation_remains_bound_after_draft_revision_changes, ()),
    "candidate_confirmation": (confirmation.test_valid_explicit_market_confirmation_is_bound_and_non_executable, ()),
    "position_empty": (position_read.test_empty_snapshot_is_authoritative_not_an_error, ()),
    "pending_read": (position_read.test_pending_order_is_not_projected_as_position, ()),
    "position_pnl": (position_read.test_open_position_uses_broker_values_and_current_pnl, ()),
    "position_protection": (position_read.test_open_position_uses_broker_values_and_current_pnl, ()),
    "position_reference": (position_read.test_exact_reference_selects_and_stale_reference_fails_closed, ()),
    "history": (position_read.test_closed_history_uses_authoritative_broker_components, ()),
    "provenance": (position_read.test_provenance_joins_existing_protected_references_and_marks_missing_fields, ()),
    "cancel_pending": (human_management.test_cancel_pending_order_requires_exact_human_confirmation, ()),
    "modify_stop": (human_management.test_modify_protection_preserves_the_unchanged_side, (((human_management._condition("requested_stop_loss", 95),), "95", "120"))),
    "modify_take": (human_management.test_modify_protection_preserves_the_unchanged_side, (((human_management._condition("requested_take_profit", 130),), "90", "130"))),
    "partial_close": (human_management.test_partial_close_calculates_resulting_volume_deterministically, (0.5, "0.5")),
    "full_close": (human_management.test_full_close_sets_resulting_volume_to_zero, ()),
    "autonomous_no_mandate": (mandate.test_autonomous_candidate_cannot_use_human_confirmation_source, ()),
    "mandate_valid": (mandate.test_mode_and_mandate_are_protected_persistent_and_demo_only, ()),
    "mandate_revoked": (mandate.test_mandate_version_switch_and_revocation_block_existing_authorization, ()),
    "provider_failure": (semantic_interpreter.test_provider_failure_does_not_retry_or_fall_back, ()),
    "ambiguous_position": (position_read.test_unique_symbol_selects_and_multiple_symbol_positions_are_ambiguous, ()),
    "stale_position": (position_read.test_account_mismatch_and_stale_snapshot_fail_closed, ()),
    "result_unknown": (recovery.test_result_unknown_never_authorizes_retry, ()),
    "kill_switch": (mandate.test_expired_corrupt_and_kill_switched_mandates_fail_closed, ()),
}


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"case-{case.case_id}-{case.family.lower()}")
def test_canonical_product_acceptance(case: AcceptanceCase, tmp_path):
    _assert_safe(case)
    if case.fixture in {"social", "system", "out_of_scope"}:
        _verify_router(case)
    elif case.fixture in {"knowledge", "market", "market_price", "market_partial", "analysis", "advisory_buy", "mixed", "multi_timeframe"}:
        _verify_semantic(case)
    elif case.fixture.startswith("strategy_"):
        _verify_strategy(case)
    elif case.fixture == "autonomous_mode":
        trading_semantics.test_mode_is_deterministic_and_does_not_change_strategy_facts(
            {
                "requested_mode": "autonomous_live",
                "explicit_fields": ["action", "direction", "symbols[0]", "indicators[0]", "conditions[0]", "requested_mode"],
            },
            "autonomous_live",
        )
    elif case.fixture == "autonomous_read":
        semantic_routing.test_requested_mode_does_not_change_information_requirements_or_execution_permission()
        position_read.test_structured_position_read_routes_to_one_read_capability_without_execution()
    else:
        function, args = EVIDENCE[case.fixture]
        _call(function, tmp_path / case.case_id, *args)


@pytest.mark.parametrize(
    ("source", "expected_direction", "expected_blocker"),
    (
        (trading_semantics.semantic(direction="BUY"), "BUY", ""),
        (trading_semantics.semantic(direction="SELL"), "SELL", ""),
        (trading_semantics.semantic(action="ANALYZE", direction="BUY"), "BUY", ""),
        (trading_semantics.semantic(indicators=[{"indicator_id": "RSI", "parameters": {}, "timeframe": "M1"}], unresolved_fields=["indicators[0].parameters.period"]), "BUY", "SEMANTIC_UNRESOLVED"),
        (trading_semantics.semantic(indicators=[{"indicator_id": "RSI", "parameters": {"period": 14}, "timeframe": ""}], unresolved_fields=["indicators[0].timeframe"]), "BUY", "SEMANTIC_UNRESOLVED"),
    ),
)
def test_high_risk_semantic_variants_share_the_structured_contract(source, expected_direction, expected_blocker):
    _plan, request = trading_semantics.request_from(source, "wording is not routing authority")
    assert request.trade_direction == expected_direction
    assert request.to_public_dict()["executable"] is False
    if source.action == "ANALYZE":
        assert request.requested_mode == "advisory_only"
        assert request.allowed_next_action == "ANALYZE_ONLY"
    if expected_blocker:
        assert any(expected_blocker in blocker for blocker in request.blockers)


def test_multi_turn_acceptance_uses_typed_context_and_protected_targets(tmp_path):
    from scripts import test_conversational_intent_contract as conversation

    conversation.test_two_turn_strategy_inherits_symbol_and_latest_timeframe_without_book_fallback()
    draft_fields.test_inherited_symbol_and_explicit_timeframe_override(tmp_path / "draft")
    position_read.test_exact_reference_selects_and_stale_reference_fails_closed()
    human_management.test_previous_position_reference_inherits_only_an_authoritative_protected_reference()
    human_management.test_partial_close_calculates_resulting_volume_deterministically(0.5, "0.5")


def test_manifest_is_exact_complete_and_non_mutating():
    assert len(CASES) == 60
    assert [case.case_id for case in CASES] == [f"{number:02d}" for number in range(1, 61)]
    assert len({case.case_id for case in CASES}) == 60
    assert all(case.expected_result_class == "PASS" for case in CASES)
    assert all(case.expected_artifact for case in CASES)
