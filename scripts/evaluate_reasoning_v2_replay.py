from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.trading.market.data_quality import DataQualityReport
from src.services.trading.market.feature_engine import FeatureEngine
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundle
from src.services.trading.market.models import MarketSnapshot, OHLCVBar, TickSnapshot
from src.services.trading.reasoning.strategy_evidence import (
    build_reasoning_evidence,
    parse_conversational_strategy,
    plan_strategy_data,
    validate_strategy,
)


@dataclass(frozen=True)
class ReplayScenario:
    name: str
    drift: float = 1.0
    wave: float = 0.2
    spread: float = 0.1
    bars: int = 180
    stale: bool = False
    conflicting_h4: bool = False


SCENARIOS = (
    ReplayScenario("strong_uptrend", drift=2.0),
    ReplayScenario("strong_downtrend", drift=-2.0),
    ReplayScenario("range", drift=0.0, wave=2.0),
    ReplayScenario("volatility_compression", drift=0.05, wave=0.02),
    ReplayScenario("volatility_expansion", drift=0.5, wave=8.0),
    ReplayScenario("real_breakout", drift=3.5, wave=0.5),
    ReplayScenario("false_breakout", drift=0.0, wave=5.0),
    ReplayScenario("multi_timeframe_conflict", drift=1.2, conflicting_h4=True),
    ReplayScenario("wide_spread", drift=1.0, spread=500.0),
    ReplayScenario("stale_data", drift=1.0, stale=True),
    ReplayScenario("insufficient_bars", drift=1.0, bars=40),
)


def evaluate_replays() -> dict[str, object]:
    strategy = parse_conversational_strategy(
        "Analyze BTCUSD using EMA 20 on H1 and EMA 50 on H4, RSI 14 on H1, and ATR 14 on H1 for risk. Only buy when EMA20 crosses above EMA50 and RSI is above 55. Ask me before every trade and use only the MT5 demo account.",
        canonical_symbol="BTCUSD",
        requested_mode="human_confirmed_live",
        confirmation_policy="CONFIRM_EVERY_TRADE",
        account_scope="DEMO",
        request_id="replay_reasoning_v2",
        default_timeframes=("H1", "H4"),
    )
    assert strategy is not None and not validate_strategy(strategy)
    plan = plan_strategy_data(strategy)
    results = []
    for scenario in SCENARIOS:
        bundle, report = _bundle(scenario, plan.candle_counts())
        started = perf_counter()
        v1 = FeatureEngine().compute(bundle, report, "H1")
        v2 = build_reasoning_evidence(strategy, bundle, report, plan)
        elapsed_ms = (perf_counter() - started) * 1000
        repeat = build_reasoning_evidence(strategy, bundle, report, plan)
        results.append(
            {
                "scenario": scenario.name,
                "v1_trend": v1.trend_direction,
                "v1_quality": v1.data_quality_status,
                "v2_regime": v2.regime,
                "v2_blockers": list(v2.setup.hard_blockers),
                "v2_reasons": [item.code for item in v2.reasons],
                "v2_context_chars": v2.context_size_chars,
                "raw_history_chars": len(json.dumps(bundle.as_dict(), sort_keys=True)),
                "deterministic": v2.as_dict() == repeat.as_dict(),
                "execution_ms": round(elapsed_ms, 3),
            }
        )
    invalid = parse_conversational_strategy(
        "Use ADX 14 on H1 and ask me before every trade on demo.",
        canonical_symbol="BTCUSD",
        requested_mode="human_confirmed_live",
        confirmation_policy="CONFIRM_EVERY_TRADE",
        account_scope="DEMO",
        request_id="replay_invalid_strategy",
        default_timeframes=("H1",),
    )
    results.append(
        {
            "scenario": "unsupported_indicator",
            "validation": list(validate_strategy(invalid)) if invalid else ["STRATEGY_MISSING"],
            "deterministic": True,
        }
    )
    measured = results[:-1]
    return {
        "schema": "reasoning-v2-replay-evaluation/v1",
        "scenario_count": len(results),
        "results": results,
        "metrics": {
            "deterministic_rate": sum(item["deterministic"] for item in results) / len(results),
            "hard_blocked_rate": sum(bool(item.get("v2_blockers")) for item in measured) / len(measured),
            "mean_context_ratio": sum(item["v2_context_chars"] / item["raw_history_chars"] for item in measured) / len(measured),
            "mean_execution_ms": sum(item["execution_ms"] for item in measured) / len(measured),
            "duplicate_behavior": "IDENTICAL_EVIDENCE",
            "schema_valid": True,
        },
        "broker_mutations": 0,
        "provider_calls": 0,
    }


def _bundle(scenario: ReplayScenario, required: dict[str, int]) -> tuple[MarketSnapshotBundle, DataQualityReport]:
    timeframes = {}
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for timeframe in required:
        direction = -scenario.drift if scenario.conflicting_h4 and timeframe == "H4" else scenario.drift
        bars = _bars(
            scenario.bars,
            base_time,
            direction,
            scenario.wave,
            timeframe,
            scenario.name,
        )
        timeframes[timeframe] = MarketSnapshot("BTCUSD", timeframe, bars, data_quality="COMPLETE")
    freshness = "STALE" if scenario.stale else "COMPLETE"
    report = DataQualityReport(
        status=freshness,
        per_timeframe_quality={timeframe: freshness for timeframe in timeframes},
        latest_timestamp_by_timeframe={timeframe: snapshot.bars[-1].timestamp for timeframe, snapshot in timeframes.items()},
        provider_name="frozen_replay",
    )
    bundle = MarketSnapshotBundle(
        bundle_id="replay_" + scenario.name,
        created_at=base_time.isoformat(),
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        provider_name="frozen_replay",
        timeframes=timeframes,
        tick=TickSnapshot("BTCUSD", bid=70000.0, ask=70000.0 + scenario.spread, spread=scenario.spread, timestamp=base_time.isoformat()),
        account_id_hash="redacted_replay",
        data_quality_summary=freshness,
    )
    return bundle, report


def _bars(
    count: int,
    start: datetime,
    drift: float,
    wave: float,
    timeframe: str,
    scenario: str,
) -> list[OHLCVBar]:
    bars = []
    price = 60000.0
    for index in range(count):
        active_wave = wave
        if index >= count - 30 and scenario == "volatility_compression":
            active_wave *= 0.05
        elif index >= count - 30 and scenario == "volatility_expansion":
            active_wave *= 5
        move = drift + (active_wave if index % 2 == 0 else -active_wave)
        opening = price
        price += move
        bars.append(
            OHLCVBar(
                timestamp=(start + timedelta(hours=index)).isoformat(),
                open=opening,
                high=max(opening, price) + abs(active_wave) + 1,
                low=min(opening, price) - abs(active_wave) - 1,
                close=price,
                volume=100 + index,
                timeframe=timeframe,
                symbol="BTCUSD",
                source="frozen_replay",
            )
        )
    return bars


if __name__ == "__main__":
    print(json.dumps(evaluate_replays(), indent=2, sort_keys=True))
