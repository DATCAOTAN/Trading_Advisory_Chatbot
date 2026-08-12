from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.config import Config
from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitor,
    AutonomousCandidateMonitorJournal,
    AutonomousCandidateMonitorResult,
    monitor_profile_id,
)
from src.services.trading.decision.autonomous_trading_coordinator import (
    AutonomousTradingCoordinator,
    production_trade_draft_sizing_constraints,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
    strategy_monitor_projection,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    MandateGrantCommand,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.reasoning.strategy_evidence import (
    ConversationalStrategyRequest,
    IndicatorSpec,
    StrategyIdentity,
    StrategyRule,
    strategy_identity,
)


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)


def test_bound_strategy_reloads_from_fresh_authority_service(tmp_path):
    authority, mandate = _bound_authority(tmp_path)
    restarted = TradingAuthorityService(TradingAuthorityStore(authority.store.path))

    reloaded_mandate, strategy = restarted.load_supervisor_strategy(
        mandate.mandate_id,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        now=NOW,
    )

    assert reloaded_mandate.strategy_id == strategy.identity.strategy_id
    assert strategy == _strategy()
    constraints = production_trade_draft_sizing_constraints(
        strategy,
        authority_service=restarted,
        mandate_id=mandate.mandate_id,
        account_context_fingerprint="a" * 64,
        account_is_demo=True,
        now=NOW,
    )
    assert str(constraints.maximum_volume) == mandate.maximum_volume
    assert str(constraints.maximum_risk_amount) == mandate.maximum_risk_per_trade


def test_legacy_mandate_without_strategy_fails_closed(tmp_path):
    authority = _authority(tmp_path)
    mandate = authority.grant_mandate(
        **_command().__dict__,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        nonce="legacy-nonce",
        idempotency_key="legacy-idempotency",
        operator_grant=True,
        now=NOW,
    )

    with pytest.raises(TradingAuthorityError, match="SUPERVISOR_STRATEGY_NOT_FOUND"):
        authority.load_supervisor_strategy(
            mandate.mandate_id,
            account_fingerprint="a" * 64,
            account_is_demo=True,
            now=NOW,
        )


@pytest.mark.parametrize(
    "change",
    (
        {"normalized_strategy_hash": "f" * 64},
        {"strategy_id": "strategy_wrong"},
        {"permitted_symbols": ("BTCUSD",)},
        {"permitted_broker_symbols": ("BTCUSDm",)},
        {"strategy_direction": "HOLD"},
        {"strategy_action": "CLOSE_POSITION"},
    ),
)
def test_mismatched_strategy_binding_is_rejected_before_persistence(tmp_path, change):
    authority = _authority(tmp_path)
    command = replace(_bound_command(), **change)

    with pytest.raises(TradingAuthorityError, match="MANDATE_STRATEGY_BINDING_INVALID"):
        authority.grant_mandate(
            **command.__dict__,
            account_fingerprint="a" * 64,
            account_is_demo=True,
            nonce="binding-nonce",
            idempotency_key="binding-idempotency",
            operator_grant=True,
            now=NOW,
        )
    assert authority.store.latest_mandates() == ()


@pytest.mark.parametrize("requested_mode", ("human_confirmed_live", "advisory_only"))
def test_non_autonomous_strategy_is_rejected_before_persistence(
    tmp_path, requested_mode
):
    authority = _authority(tmp_path)
    strategy = replace(_strategy(), requested_mode=requested_mode)
    strategy = replace(strategy, identity=strategy_identity(strategy))
    command = _command_for_strategy(strategy)

    with pytest.raises(TradingAuthorityError, match="MANDATE_STRATEGY_BINDING_INVALID"):
        authority.grant_mandate(
            **command.__dict__,
            account_fingerprint="a" * 64,
            account_is_demo=True,
            nonce="mode-binding-nonce",
            idempotency_key="mode-binding-idempotency",
            operator_grant=True,
            now=NOW,
        )


def test_strategy_scope_does_not_replace_authoritative_demo_account_binding(tmp_path):
    authority = _authority(tmp_path)
    strategy = replace(_strategy(), account_scope="")
    strategy = replace(strategy, identity=strategy_identity(strategy))
    mandate = authority.grant_mandate(
        **_command_for_strategy(strategy).__dict__,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        nonce="scope-binding-nonce",
        idempotency_key="scope-binding-idempotency",
        operator_grant=True,
        now=NOW,
    )

    assert mandate.account_is_demo is True
    reloaded, _strategy_record = authority.load_supervisor_strategy(
        mandate.mandate_id,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        now=NOW,
    )
    assert reloaded.account_is_demo is True


def test_mandate_authorization_rejects_candidate_from_another_trading_scope(tmp_path):
    authority = _authority(tmp_path)
    strategy = replace(_strategy(), trading_scope="trading_scope_" + "a" * 24)
    strategy = replace(strategy, identity=strategy_identity(strategy))
    mandate = authority.grant_mandate(
        **replace(_command_for_strategy(strategy), kill_switch_engaged=False).__dict__,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        nonce="scope-nonce",
        idempotency_key="scope-idempotency",
        operator_grant=True,
        now=NOW,
    )
    candidate = SimpleNamespace(
        operating_mode="autonomous_live",
        strategy_id=strategy.identity.strategy_id,
        strategy_version=strategy.identity.strategy_version,
        normalized_strategy_hash=strategy.identity.normalized_strategy_hash,
        trading_scope="trading_scope_" + "b" * 24,
        candidate_reference="candidate-ref",
        provenance_hash="a" * 64,
        structured_order_hash="b" * 64,
        proposal_source_reference="proposal-ref",
        account_context_reference="account-ref",
        risk_result_reference="risk-ref",
        lifecycle_observation_reference="lifecycle-ref",
        expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        symbol_reference="XAUUSD",
        broker_symbol_reference="XAUUSDm",
        action="MARKET",
        deterministic_eligibility_result="ELIGIBLE_CANDIDATE",
        blocked_reason_codes=(),
        proposed_volume="0.01",
    )

    blockers = authority._candidate_blockers(
        candidate,
        authority.store.latest_mode(),
        mandate,
        "a" * 64,
        True,
        "0.5",
        0,
        0,
        "0",
        False,
        True,
        True,
        NOW,
    )

    assert blockers == ("CANDIDATE_STRATEGY_BINDING_MISMATCH",)


def test_unsupported_strategy_rule_is_rejected_before_persistence(tmp_path):
    authority = _authority(tmp_path)
    strategy = replace(
        _strategy(),
        entry_rules=(StrategyRule("EQUALS", "rsi_14_m1", constants=(10.0,)),),
    )
    strategy = replace(strategy, identity=strategy_identity(strategy))

    with pytest.raises(TradingAuthorityError, match="MANDATE_STRATEGY_BINDING_INVALID"):
        authority.grant_mandate(
            **_command_for_strategy(strategy).__dict__,
            account_fingerprint="a" * 64,
            account_is_demo=True,
            nonce="rule-binding-nonce",
            idempotency_key="rule-binding-idempotency",
            operator_grant=True,
            now=NOW,
        )


def test_supervisor_reload_rejects_account_revocation_and_expiry(tmp_path):
    authority, mandate = _bound_authority(tmp_path)
    with pytest.raises(TradingAuthorityError, match="SUPERVISOR_ACCOUNT_MISMATCH"):
        production_trade_draft_sizing_constraints(
            _strategy(),
            authority_service=authority,
            mandate_id=mandate.mandate_id,
            account_context_fingerprint="b" * 64,
            account_is_demo=True,
            now=NOW,
        )

    authority.revoke_mandate(
        mandate.mandate_id,
        operator_grant=True,
        revocation_nonce="revoke-bound-strategy",
        now=NOW,
    )
    with pytest.raises(TradingAuthorityError, match="SUPERVISOR_MANDATE_INACTIVE"):
        production_trade_draft_sizing_constraints(
            _strategy(),
            authority_service=authority,
            mandate_id=mandate.mandate_id,
            account_context_fingerprint="a" * 64,
            account_is_demo=True,
            now=NOW,
        )

    other, other_mandate = _bound_authority(tmp_path / "expired")
    with pytest.raises(TradingAuthorityError, match="SUPERVISOR_MANDATE_INACTIVE"):
        production_trade_draft_sizing_constraints(
            _strategy(),
            authority_service=other,
            mandate_id=other_mandate.mandate_id,
            account_context_fingerprint="a" * 64,
            account_is_demo=True,
            now=NOW + timedelta(hours=2),
        )


@pytest.mark.parametrize(
    ("previous", "current", "state", "eligibility"),
    (
        (5.0, 7.0, "CONDITION_FALSE", "CONDITION_FALSE"),
        (5.0, 11.0, "CONDITION_TRUE", "ENTRY_ELIGIBLE"),
        (11.0, 12.0, "CONDITION_TRUE", "ENTRY_ELIGIBLE"),
    ),
)
def test_level_rule_projection_uses_current_condition(
    previous, current, state, eligibility
):
    summary = json.dumps(
        {
            "indicator_values": {
                "rsi_14_m1": {"previous": previous, "current": current}
            },
            "hard_blockers": [],
        }
    )

    projection = strategy_monitor_projection(_strategy(), summary)

    assert projection["previous_indicator_value"] == previous
    assert projection["current_indicator_value"] == current
    assert projection["trigger_mode"] == "LEVEL"
    assert projection["rearm_state"] == state
    assert projection["opening_eligibility"] == eligibility


def test_coordinator_passes_exact_strategy_and_projects_level_condition(tmp_path):
    strategy = _strategy()
    calls = []
    summary = json.dumps(
        {
            "indicator_values": {
                "rsi_14_m1": {"previous": 30.3172, "current": 27.8983}
            },
            "hard_blockers": [],
            "proposal_observability": {
                "provider_invoked": True,
                "provider_name": "groq",
                "model_name": "safe-model",
                "attempt_count": 1,
                "retry_count": 0,
                "transport_status": "OK",
                "parse_status": "OK",
                "schema_status": "VALID",
                "proposal_status": "VALID_NO_PROPOSAL",
                "reason_code": "NO_SETUP",
            },
        }
    )

    class Assembler:
        def build(self, **kwargs):
            calls.append(kwargs)
            raise OperatorCandidateInputError(
                "VALID_NO_PROPOSAL",
                evidence_summary=summary,
            )

    coordinator = AutonomousTradingCoordinator(
        feature_service=SimpleNamespace(),
        input_assembler=Assembler(),
        strategy=strategy,
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
        account_context_provider=lambda: {},
        authority_service=TradingAuthorityService(
            TradingAuthorityStore(tmp_path / "authority.jsonl")
        ),
    )

    result = coordinator._handle_completed_bar(
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        timeframes=("M1",),
        closed_bar_time="2026-08-10T08:00:00+00:00",
        account_scope="scope",
    )

    assert calls == [{
        "symbol": "XAUUSD",
        "timeframes": ("M1",),
        "strategy": strategy,
        "strategy_direction": "BUY",
        "strategy_action": "OPEN_POSITION",
    }]
    assert result.status == "NO_ACTION"
    assert result.strategy_evaluation["trigger_mode"] == "LEVEL"
    assert result.strategy_evaluation["rearm_state"] == "CONDITION_TRUE"
    assert result.strategy_evaluation["opening_eligibility"] == "ENTRY_ELIGIBLE"
    assert result.strategy_evaluation["direction"] == "BUY"
    assert result.proposal_provider_max_invocations == 1
    assert result.strategy_evaluation["proposal_observability"]["proposal_status"] == (
        "VALID_NO_PROPOSAL"
    )


def test_monitor_journal_persists_safe_strategy_projection(tmp_path):
    journal = AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl")
    strategy_reference = _strategy().identity.strategy_id
    assert journal.claim(
        profile_id=monitor_profile_id("XAUUSD", ("M1",), "scope", strategy_reference),
        account_scope="scope",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        timeframes=("M1",),
        closed_bar_time="2026-08-10T08:00:00+00:00",
        strategy_reference=strategy_reference,
    )
    journal.complete(
        AutonomousCandidateMonitorResult(
            "NO_ACTION",
            "XAUUSD",
            "XAUUSDm",
            ("M1",),
            "2026-08-10T08:00:00+00:00",
            account_scope="scope",
            coordinator_status="NO_ACTION",
            strategy_evaluation={
                "strategy_reference": _strategy().identity.strategy_id,
                "rearm_state": "WAITING_FOR_REARM",
            },
        )
    )

    row = journal.records()[-1]
    assert row["strategy_evaluation"]["rearm_state"] == "WAITING_FOR_REARM"
    assert row["metadata_redacted"] is True


def test_monitor_requests_enough_completed_bars_for_quality_gate(tmp_path):
    calls = []
    closed_bar_time = "2026-08-10T08:00:00+00:00"

    class FeatureService:
        def build_features(self, symbol, timeframes, candle_count):
            calls.append((symbol, timeframes, candle_count))
            return SimpleNamespace(
                quality_report=SimpleNamespace(status="COMPLETE"),
                bundle=SimpleNamespace(
                    broker_symbol="XAUUSDm",
                    timeframes={
                        "M1": SimpleNamespace(
                            bars=(SimpleNamespace(timestamp=closed_bar_time),)
                        )
                    },
                ),
            )

    monitor = AutonomousCandidateMonitor(
        feature_service=FeatureService(),
        completed_bar_handler=lambda **kwargs: AutonomousCandidateMonitorResult(
            "NO_ACTION",
            kwargs["symbol"],
            kwargs["broker_symbol"],
            kwargs["timeframes"],
            kwargs["closed_bar_time"],
            account_scope=kwargs["account_scope"],
        ),
        journal=AutonomousCandidateMonitorJournal(tmp_path / "monitor.jsonl"),
    )

    result = monitor.run_once(
        symbol="XAUUSD",
        timeframes=("M1",),
        account_scope="scope",
        strategy_reference=_strategy().identity.strategy_id,
    )

    assert result.status == "NO_ACTION"
    assert calls == [("XAUUSD", ("M1",), Config.MARKET_DEFAULT_CANDLE_COUNT)]


def _authority(tmp_path):
    authority = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    authority.set_mode(
        "autonomous_live",
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="mode-nonce",
        now=NOW,
    )
    return authority


def _bound_authority(tmp_path):
    authority = _authority(tmp_path)
    mandate = authority.grant_mandate(
        **_bound_command().__dict__,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        nonce="bound-nonce",
        idempotency_key="bound-idempotency",
        operator_grant=True,
        now=NOW,
    )
    return authority, mandate


def _command():
    return MandateGrantCommand(
        mandate_id="mandate-bound-strategy",
        mandate_version=1,
        permitted_symbols=("XAUUSD",),
        permitted_broker_symbols=("XAUUSDm",),
        permitted_order_families=("MARKET",),
        permitted_management_actions=("OBSERVE", "NO_ACTION"),
        maximum_volume="0.01",
        maximum_risk_per_trade="1",
        maximum_concurrent_positions=1,
        maximum_trades_per_day=1,
        maximum_loss_per_day="1",
        active_from=(NOW - timedelta(minutes=1)).isoformat(),
        active_until=(NOW + timedelta(hours=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        kill_switch_engaged=True,
    )


def _bound_command():
    return _command_for_strategy(_strategy())


def _command_for_strategy(strategy):
    return replace(
        _command(),
        strategy_id=strategy.identity.strategy_id,
        strategy_version=strategy.identity.strategy_version,
        normalized_strategy_hash=strategy.identity.normalized_strategy_hash,
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
        protected_strategy=strategy.as_dict(),
    )


def _strategy():
    provisional = ConversationalStrategyRequest(
        canonical_symbol="XAUUSD",
        requested_mode="autonomous_live",
        confirmation_policy="STANDING_MANDATE",
        account_scope="DEMO",
        indicators=(
            IndicatorSpec("RSI", "M1", (("period", 14.0),), "rsi_14_m1"),
        ),
        entry_rules=(
            StrategyRule("GREATER_THAN", "rsi_14_m1", constants=(10.0,)),
        ),
        exit_rules=(),
        strategy_description="BUY XAUUSD when RSI14 M1 is above 10",
        risk_policy_reference="CONFIGURED_RISK_POLICY",
        request_id="conversation_trade_supervisor",
        identity=StrategyIdentity("", "reasoning-strategy/v2", ""),
    )
    return ConversationalStrategyRequest(
        **{**provisional.__dict__, "identity": strategy_identity(provisional)}
    )
