from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from scripts.test_operator_review_confirmation_lifecycle import NOW
from scripts.test_autonomous_supervisor_strategy_binding import _strategy
from src.services.trading.decision.autonomous_trading_coordinator import (
    AutonomousTradingCoordinator,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.reasoning.strategy_evidence import (
    StrategyRule,
    evaluate_strategy_rule,
)


@pytest.mark.parametrize(
    ("previous", "current", "eligible"),
    ((11.0, 12.0, True), (5.0, 11.0, True), (5.0, 5.0, False), (11.0, 5.0, False)),
)
def test_level_uses_current_condition_only(previous, current, eligible):
    result = evaluate_strategy_rule(
        StrategyRule("GREATER_THAN", "value", constants=(10.0,)),
        {"value": {"previous": previous, "current": current}},
    )

    assert result["trigger_mode"] == "LEVEL"
    assert result["triggered"] is eligible
    assert result["opening_eligibility"] == (
        "ENTRY_ELIGIBLE" if eligible else "CONDITION_FALSE"
    )


@pytest.mark.parametrize(
    ("previous", "current", "state", "triggered"),
    (
        (5.0, 7.0, "ARMED", False),
        (5.0, 11.0, "TRIGGERED", True),
        (11.0, 12.0, "WAITING_FOR_REARM", False),
        (11.0, 5.0, "REARMED", False),
    ),
)
def test_explicit_crossing_retains_edge_state(previous, current, state, triggered):
    result = evaluate_strategy_rule(
        StrategyRule("CROSSES_ABOVE", "left", "right"),
        {
            "left": {"previous": previous, "current": current},
            "right": {"previous": 10.0, "current": 10.0},
        },
    )

    assert result["trigger_mode"] == "EDGE"
    assert result["signal_state"] == state
    assert result["triggered"] is triggered


@pytest.mark.parametrize(
    "lifecycle",
    (
        SimpleNamespace(active_position_count=1, lifecycle_state_counts={}),
        SimpleNamespace(
            active_position_count=0,
            lifecycle_state_counts={"ORDER_ACTIVE": 1},
        ),
    ),
)
def test_active_order_or_position_blocks_another_opening(tmp_path, lifecycle):
    coordinator = _coordinator(tmp_path)

    assert coordinator._opening_lifecycle_blocker(
        SimpleNamespace(lifecycle_status=lifecycle)
    ) == "ENTRY_ALREADY_ACTIVE"


def test_active_candidate_blocks_until_expired_then_terminal_state_allows_reentry(
    tmp_path,
):
    candidate = SimpleNamespace(
        strategy_id=_strategy().identity.strategy_id,
        intent="OPEN_POSITION",
        deterministic_eligibility_result="ELIGIBLE_CANDIDATE",
        expires_at=(NOW + timedelta(minutes=5)).isoformat(),
    )

    class Journal:
        def records(self):
            return [{"candidate_reference": "candidate-1"}]

        def load_candidate(self, _reference):
            return candidate

    coordinator = _coordinator(tmp_path, journal=Journal())
    terminal = SimpleNamespace(
        active_position_count=0,
        lifecycle_state_counts={"POSITION_CLOSED": 1},
    )

    assert coordinator._opening_lifecycle_blocker(
        SimpleNamespace(lifecycle_status=terminal)
    ) == "ENTRY_ALREADY_ACTIVE"
    candidate.expires_at = (NOW - timedelta(seconds=1)).isoformat()
    assert coordinator._opening_lifecycle_blocker(
        SimpleNamespace(lifecycle_status=terminal)
    ) == ""


def test_human_confirmed_mode_does_not_use_autonomous_opening_guard(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.strategy = replace(
        coordinator.strategy, requested_mode="human_confirmed_live"
    )

    assert coordinator._opening_lifecycle_blocker(
        SimpleNamespace(
            lifecycle_status=SimpleNamespace(
                active_position_count=1,
                lifecycle_state_counts={"POSITION_OPEN": 1},
            )
        )
    ) == ""


def _coordinator(tmp_path, journal=None):
    orchestrator = SimpleNamespace(journal=journal) if journal is not None else SimpleNamespace()
    return AutonomousTradingCoordinator(
        feature_service=SimpleNamespace(),
        input_assembler=SimpleNamespace(),
        strategy=_strategy(),
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
        account_context_provider=lambda: {},
        authority_service=TradingAuthorityService(
            TradingAuthorityStore(tmp_path / "authority.jsonl")
        ),
        decision_orchestrator=orchestrator,
        clock=lambda: NOW,
    )
