from __future__ import annotations

import json
from dataclasses import replace

import pytest
import src.services.trading.reasoning.strategy_evidence as strategy_evidence_module

from scripts.evaluate_reasoning_v2_replay import evaluate_replays
from scripts.evaluate_reasoning_v2_replay import ReplayScenario, _bundle
from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs, service
from src.services.trading.decision.conversational_authorization import (
    ConversationalTradingRequest,
    parse_conversational_trading_request,
)
from src.services.trading.reasoning.strategy_evidence import (
    INDICATOR_REGISTRY,
    IndicatorSpec,
    StrategyRule,
    evaluate_strategy_rule,
    build_reasoning_evidence,
    parse_conversational_strategy,
    plan_strategy_data,
    strategy_identity,
    validate_strategy,
    _evaluate_rule,
)
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.models import AccountSnapshot, MarketSnapshot, ProviderHealth, TickSnapshot
from src.ui.operator_candidate_generation import OperatorCandidateGenerationController


def _request(text: str):
    return parse_conversational_strategy(
        text,
        canonical_symbol="BTCUSD",
        requested_mode="human_confirmed_live",
        confirmation_policy="CONFIRM_EVERY_TRADE",
        account_scope="DEMO",
        request_id="strategy_test",
        default_timeframes=("M15", "H1", "H4"),
    )


def test_registry_is_bounded_to_supported_catalog():
    assert set(INDICATOR_REGISTRY) == {"EMA", "SMA", "RSI", "ATR", "MACD", "BOLLINGER_BANDS"}
    assert all(item.parameter_ranges and item.missing_value_policy == "BLOCK" for item in INDICATOR_REGISTRY.values())
    assert dict(INDICATOR_REGISTRY["MACD"].parameter_defaults) == {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Use EMA 20/50 and RSI 14 on H1. Ask me before every trade on demo.", {"EMA", "RSI"}),
        ("Use EMA 200 on H4 for trend and EMA 9/21 on M15 for entry. Confirm every trade on demo.", {"EMA"}),
        ("Use ATR 14 for the stop and Bollinger Bands 20/2 on H1. Ask before trading on demo.", {"ATR", "BOLLINGER_BANDS"}),
        ("Use MACD 12/26/9 and SMA 50 on H1. Confirm each order on demo.", {"MACD", "SMA"}),
    ],
)
def test_varied_wording_normalizes_without_sentence_matching(text, expected):
    strategy = _request(text)
    assert strategy is not None
    assert {item.indicator_id for item in strategy.indicators} == expected
    assert validate_strategy(strategy) == ()


def test_rules_are_typed_and_bounded():
    strategy = _request("Use EMA 20/50 and RSI 14 on H1. Only buy when EMA20 crosses above EMA50 and RSI is above 55. Ask before every trade on demo.")
    assert strategy is not None
    assert [item.operator for item in strategy.entry_rules] == ["CROSSES_ABOVE", "GREATER_THAN"]


def test_rule_mentions_do_not_create_default_timeframe_indicator_duplicates():
    strategy = _request(
        "Use EMA 20 and EMA 50 on H1, RSI 14 on H1 and ATR 14 for risk. "
        "Only buy when EMA20 crosses above EMA50 and RSI is above 55."
    )
    assert strategy is not None
    assert [item.output_alias for item in strategy.indicators] == [
        "atr_14_m15",
        "ema_20_h1",
        "ema_50_h1",
        "rsi_14_h1",
    ]
    assert strategy.entry_rules[0] == StrategyRule(
        "CROSSES_ABOVE", "ema_20_h1", "ema_50_h1"
    )


def test_explicit_same_indicator_on_two_timeframes_is_preserved():
    strategy = _request(
        "Use EMA 20 on M15 and EMA 20 on H1, then confirm every trade on demo."
    )
    assert strategy is not None
    assert [item.output_alias for item in strategy.indicators] == [
        "ema_20_h1",
        "ema_20_m15",
    ]


def test_vietnamese_rule_references_do_not_duplicate_declared_h1_indicators():
    request = parse_conversational_trading_request(
        "Hãy phân tích BTCUSD bằng EMA 20 và EMA 50 trên H1, RSI 14 trên H1 "
        "và ATR 14 để quản lý rủi ro. Chỉ xem xét BUY khi EMA20 cắt lên "
        "EMA50 và RSI lớn hơn 55. Phải hỏi tôi trước mỗi giao dịch và chỉ "
        "dùng tài khoản MT5 demo.",
        conversation_id="vietnamese-reasoning-v2",
    )
    assert request is not None and request.strategy is not None
    aliases = [item.output_alias for item in request.strategy.indicators]
    assert aliases == ["atr_14_m1", "ema_20_h1", "ema_50_h1", "rsi_14_h1"]
    assert request.strategy.entry_rules == (
        StrategyRule("CROSSES_ABOVE", "ema_20_h1", "ema_50_h1"),
        StrategyRule("GREATER_THAN", "rsi_14_h1", constants=(55.0,)),
    )


def test_invalid_indicator_and_parameters_fail_closed():
    unsupported = _request("Use ADX 14 on H1 and ask before every trade on demo.")
    assert unsupported is not None
    assert validate_strategy(unsupported) == ("UNSUPPORTED_INDICATOR",)
    valid = _request("Use EMA 20 on H1 and ask before every trade on demo.")
    bad = replace(valid, indicators=(IndicatorSpec("EMA", "H1", (("period", 0.0),), "ema_0_h1"),))
    assert "INDICATOR_PARAMETER_OUT_OF_RANGE" in validate_strategy(bad)
    duplicate = replace(valid, indicators=(valid.indicators[0], valid.indicators[0]))
    assert "DUPLICATE_OUTPUT_ALIAS" in validate_strategy(duplicate)


def test_unknown_rule_output_and_arbitrary_code_are_not_executed(tmp_path):
    marker = tmp_path / "never-created"
    strategy = _request(f"Use EMA 20 on H1; __import__('pathlib').Path('{marker}').touch(); ask before every trade on demo.")
    assert strategy is not None and not marker.exists()
    bad = replace(strategy, entry_rules=(StrategyRule("GREATER_THAN", "missing", constants=(1,)),))
    assert "RULE_OUTPUT_UNKNOWN" in validate_strategy(bad)


def test_identity_is_stable_and_public_round_trip_validates_it():
    request = parse_conversational_trading_request(
        "Analyze BTCUSD using EMA 20/50 and RSI 14 on H1. Ask me before every trade and use demo MT5.",
        conversation_id="conversation-v2",
    )
    assert request is not None and request.strategy is not None
    assert strategy_identity(request.strategy) == request.strategy.identity
    assert ConversationalTradingRequest.from_public_dict(request.to_public_dict()) == request
    tampered = request.to_public_dict()
    tampered["strategy"]["identity"]["normalized_strategy_hash"] = "0" * 64
    with pytest.raises(ValueError):
        ConversationalTradingRequest.from_public_dict(tampered)


def test_data_plan_is_per_timeframe_and_accounts_for_warmup_and_rules():
    strategy = _request("Use EMA 200 on H4 and EMA 9/21 on M15. EMA9 crosses above EMA21. Ask before every trade on demo.")
    plan = plan_strategy_data(strategy)
    counts = plan.candle_counts()
    assert counts["H4"] >= 600
    assert counts["M15"] >= 100
    assert counts["H4"] <= 1000


def test_bundle_builder_requests_each_planned_completed_bar_count():
    class Provider:
        provider_name = "planned"

        def __init__(self):
            self.calls = []

        def normalize_symbol(self, symbol):
            return symbol + "m"

        def health_check(self):
            return ProviderHealth(provider_name="planned", status="OK")

        def get_ohlcv(self, symbol, timeframe, count):
            self.calls.append((symbol, timeframe, count))
            return MarketSnapshot(symbol, timeframe, [], provider_name="planned")

        def get_latest_tick(self, symbol):
            return TickSnapshot(symbol)

        def get_account(self):
            return AccountSnapshot(provider_name="planned", redacted=True)

    strategy = _request("Use EMA 20 on H1 and EMA 200 on H4. Ask before every trade on demo.")
    counts = plan_strategy_data(strategy).candle_counts()
    provider = Provider()
    MarketSnapshotBundleBuilder(provider).build("BTCUSD", counts, counts)
    assert provider.calls == [("BTCUSD", timeframe, count) for timeframe, count in counts.items()]


def test_all_bounded_rule_operators_are_deterministic():
    values = {
        "left": {"previous": 1.0, "current": 3.0},
        "right": {"previous": 2.0, "current": 2.5},
    }
    rules = (
        StrategyRule("GREATER_THAN", "left", constants=(2.0,)),
        StrategyRule("LESS_THAN", "right", constants=(3.0,)),
        StrategyRule("CROSSES_ABOVE", "left", "right"),
        StrategyRule("CROSSES_BELOW", "right", "left"),
        StrategyRule("BETWEEN", "right", constants=(2.0, 3.0)),
        StrategyRule("RISING", "left"),
        StrategyRule("FALLING", "right"),
    )
    assert [_evaluate_rule(rule, values) for rule in rules] == [True, True, True, True, True, True, False]


@pytest.mark.parametrize(
    ("previous", "current", "blocker"),
    ((5.0, 11.0, None), (11.0, 12.0, None), (5.0, 5.0, "ENTRY_CONDITION_FALSE"),
     (11.0, 5.0, "ENTRY_CONDITION_FALSE"), (11.0, None, "ENTRY_CONDITION_UNKNOWN")),
)
def test_autonomous_level_condition_uses_current_completed_bar(
    monkeypatch, previous, current, blocker
):
    strategy = replace(
        _request("Use RSI 14 on H1 and buy when RSI is above 10."),
        requested_mode="autonomous_live",
    )
    strategy = replace(strategy, identity=strategy_identity(strategy))
    plan = plan_strategy_data(strategy)
    bundle, quality = _bundle(
        ReplayScenario("autonomous_rearm", bars=180), plan.candle_counts()
    )
    monkeypatch.setattr(
        strategy_evidence_module,
        "_compute_indicator",
        lambda _spec, _bars: {"previous": previous, "current": current},
    )

    evidence = build_reasoning_evidence(strategy, bundle, quality, plan)

    assert tuple(item for item in evidence.setup.hard_blockers if item.startswith("ENTRY_CONDITION_")) == (
        (blocker,) if blocker else ()
    )


@pytest.mark.parametrize("current, blocker", [(12.0, None), (5.0, "ENTRY_CONDITION_FALSE"), (None, "ENTRY_CONDITION_UNKNOWN")])
def test_human_level_gates_on_current_condition_without_rearm(monkeypatch, current, blocker):
    strategy = _request("Use RSI 14 on H1 and buy when RSI is above 10.")
    plan = plan_strategy_data(strategy)
    bundle, quality = _bundle(
        ReplayScenario("human_level_condition", bars=180), plan.candle_counts()
    )
    monkeypatch.setattr(
        strategy_evidence_module,
        "_compute_indicator",
        lambda _spec, _bars: {"previous": 11.0, "current": current},
    )

    evidence = build_reasoning_evidence(strategy, bundle, quality, plan)

    assert tuple(item for item in evidence.setup.hard_blockers if item.startswith("ENTRY_CONDITION_")) == (
        (blocker,) if blocker else ()
    )


def test_explicit_crossing_retains_edge_rearm_semantics():
    rule = StrategyRule("CROSSES_ABOVE", "left", "right")

    def state(left_previous, left_current):
        return evaluate_strategy_rule(
            rule,
            {
                "left": {"previous": left_previous, "current": left_current},
                "right": {"previous": 10.0, "current": 10.0},
            },
        )

    assert state(5.0, 7.0)["signal_state"] == "ARMED"
    assert state(5.0, 11.0)["signal_state"] == "TRIGGERED"
    assert state(11.0, 12.0)["signal_state"] == "WAITING_FOR_REARM"
    assert state(11.0, 5.0)["signal_state"] == "REARMED"
    assert state(5.0, 11.0)["trigger_mode"] == "EDGE"


def test_plain_comparison_is_level_not_edge():
    result = evaluate_strategy_rule(
        StrategyRule("GREATER_THAN", "left", constants=(10.0,)),
        {"left": {"previous": 11.0, "current": 12.0}},
    )

    assert result == {
        "trigger_mode": "LEVEL",
        "previous_condition": True,
        "current_condition": True,
        "triggered": True,
        "signal_state": "CONDITION_TRUE",
        "opening_eligibility": "ENTRY_ELIGIBLE",
    }


def test_replay_evaluation_covers_required_states_and_is_compact():
    report = evaluate_replays()
    rows = {item["scenario"]: item for item in report["results"]}
    assert report["scenario_count"] == 12
    assert all(item["deterministic"] for item in report["results"])
    assert "DATA_STALE" in rows["stale_data"]["v2_blockers"]
    assert "INSUFFICIENT_COMPLETED_BARS" in rows["insufficient_bars"]["v2_blockers"]
    assert "SPREAD_TOO_WIDE" in rows["wide_spread"]["v2_blockers"]
    assert rows["unsupported_indicator"]["validation"] == ["UNSUPPORTED_INDICATOR"]
    assert rows["strong_uptrend"]["v2_regime"] == "TREND_UP"
    assert rows["strong_downtrend"]["v2_regime"] == "TREND_DOWN"
    assert rows["range"]["v2_regime"] == "RANGE"
    assert rows["volatility_compression"]["v2_regime"] == "VOLATILITY_COMPRESSION"
    assert rows["volatility_expansion"]["v2_regime"] == "VOLATILITY_EXPANSION"
    assert rows["multi_timeframe_conflict"]["v2_regime"] == "TRANSITION"
    for row in report["results"][:-1]:
        assert row["v2_context_chars"] < row["raw_history_chars"]
    assert report["provider_calls"] == report["broker_mutations"] == 0
    assert report["metrics"]["schema_valid"] is True
    assert report["metrics"]["deterministic_rate"] == 1.0

    strategy = _request("Use EMA 20 and ATR 14 on H1. Ask before every trade on demo.")
    plan = plan_strategy_data(strategy)
    bundle, quality = _bundle(ReplayScenario("feature_groups", bars=180), plan.candle_counts())
    evidence = build_reasoning_evidence(strategy, bundle, quality, plan)
    assert set(evidence.setup.scores) == {
        "regime", "trend", "structure", "momentum", "volatility",
        "timeframe_alignment", "execution_quality", "risk_compatibility",
    }
    assert set(evidence.features.as_dict()) == {
        "trend", "volatility", "structure", "momentum", "timeframe_alignment",
        "execution", "data_quality", "indicator_values",
    }


def test_strategy_serialization_contains_no_executable_authority():
    request = parse_conversational_trading_request(
        "Analyze only BTCUSD with EMA 20/50 and RSI 14 on H1; do not trade.",
        conversation_id="analysis-only",
    )
    payload = request.to_public_dict()
    assert payload["requested_mode"] == "advisory_only"
    assert payload["execution_authority"] is payload["executable"] is False
    assert "order_send" not in json.dumps(payload).lower()


def test_strategy_identity_is_bound_into_candidate_provenance(tmp_path):
    inputs = replace(
        make_inputs(risk_action="WAIT"),
        strategy_id="strategy_" + "a" * 24,
        strategy_version="reasoning-strategy/v2",
        normalized_strategy_hash="b" * 64,
        reasoning_evidence_summary='{"regime":"RANGE"}',
        trading_scope="trading_scope_" + "d" * 24,
    )
    orchestrator = service(tmp_path)
    result = orchestrator.run_once(inputs, now=NOW)
    candidate = result.candidate
    validation = orchestrator.validate_candidate(candidate, now=NOW)
    assert validation.valid
    assert candidate.strategy_id == inputs.strategy_id
    assert candidate.normalized_strategy_hash == inputs.normalized_strategy_hash
    assert candidate.trading_scope == inputs.trading_scope
    assert orchestrator.journal.load_candidate(candidate.candidate_reference).trading_scope == inputs.trading_scope
    assert candidate.to_operator_review_dict()["reasoning_evidence_summary"]
    changed = service(tmp_path).build_candidate(
        replace(inputs, normalized_strategy_hash="c" * 64), now=NOW
    )
    assert changed.provenance_hash != candidate.provenance_hash


def test_controller_passes_one_typed_strategy_without_scalar_duplication():
    strategy = _request("Use EMA 20/50 and RSI 14 on H1. Ask before every trade on demo.")

    class Assembler:
        def __init__(self):
            self.kwargs = None

        def build(self, **kwargs):
            self.kwargs = kwargs
            raise RuntimeError("stop-after-handoff")

    assembler = Assembler()
    outcome = OperatorCandidateGenerationController(assembler).generate(
        {}, "reasoning-v2-generation", symbol="BTCUSD", strategy=strategy
    )
    assert outcome.status == "BLOCKED"
    assert assembler.kwargs == {"symbol": "BTCUSD", "strategy": strategy}
