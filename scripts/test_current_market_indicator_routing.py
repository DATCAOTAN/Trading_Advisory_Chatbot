from datetime import datetime, timedelta, timezone

import pytest

from src.config import Config
from src.services.decision_context import (
    DecisionContextBuilder,
    ExistingMarketDataAdapter,
    ExistingTechnicalSnapshotAdapter,
)
from src.services.evidence import EvidenceSelector
from src.services.semantic.context_acquisition import ContextAcquisitionExecutor
from src.services.semantic.context_execution import ContextExecutionPlanner
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.trading.market.timeframes import resolve_symbol


QUERY = "EMA 20 và RSI 14 hiện tại của BTCUSDm trên H1 là bao nhiêu?"


class FakeLiveService:
    def __init__(self, *, bars=80, stale=False):
        self.bars = bars
        self.stale = stale
        self.calls = []

    def get_live_price(self, symbol="XAUUSD"):
        return f"**{symbol}**: 63000 (bid=62999, ask=63001, spread=2, updated=now) - Source: fake"

    def get_historical_candles(self, symbol="XAUUSD", timeframe="1h", limit=100, **_):
        self.calls.append((symbol, timeframe, limit))
        latest = datetime.now(timezone.utc) - (timedelta(days=3) if self.stale else timedelta(hours=2))
        start = latest - timedelta(hours=max(self.bars - 1, 0))
        return [
            {
                "timestamp": (start + timedelta(hours=index)).isoformat(),
                "open": 62000 + index,
                "high": 62010 + index,
                "low": 61990 + index,
                "close": 62005 + index,
                "volume": 10,
            }
            for index in range(self.bars)
        ]


def _run(query=QUERY, *, live=None):
    live = live or FakeLiveService()
    plan = QueryPlanAssembler().assemble(query)
    requirements = ContextRequirementPlanner().plan(plan)
    execution = ContextExecutionPlanner().plan(requirements)
    executor = ContextAcquisitionExecutor(
        market_adapter=ExistingMarketDataAdapter(live),
        technical_adapter=ExistingTechnicalSnapshotAdapter(),
        live_service=live,
    )
    batch = executor.execute(plan, requirements, execution)
    return plan, requirements, execution, batch, live


def test_configured_broker_alias_resolves_to_canonical_symbol(monkeypatch):
    assert resolve_symbol("BTCUSDm").canonical_symbol == "BTCUSD"
    monkeypatch.setattr(Config, "MARKET_BROKER_SYMBOL_EURUSD", "EURUSD.demo", raising=False)
    resolved = resolve_symbol("eurusd.demo")
    assert (resolved.canonical_symbol, resolved.broker_symbol, resolved.status) == (
        "EURUSD",
        "EURUSD.demo",
        "RESOLVED",
    )
    assert resolve_symbol("UNKNOWNUSDx").status == "UNRESOLVED"


def test_current_indicator_query_has_market_precedence_and_typed_parameters():
    plan = QueryPlanAssembler().assemble(QUERY)
    requirements = ContextRequirementPlanner().plan(plan)
    by_capability = {need.capability: need for need in requirements.needs}

    assert plan.primary_intent == "market_state_analysis"
    assert plan.entities.symbols == ["BTCUSD"]
    assert plan.entities.broker_symbols == ["BTCUSDm"]
    assert plan.entities.timeframes == ["1h"]
    assert [item.output_alias for item in plan.requested_indicators] == ["ema_20_h1", "rsi_14_h1"]
    assert by_capability["ohlcv"].parameters["timeframe"] == "H1"
    assert by_capability["ohlcv"].parameters["limit"] == 60
    assert len(by_capability["ohlcv"].parameters["indicators"]) == 2
    assert by_capability["technical_snapshot"].required is True


def test_concept_query_stays_book_only_and_mixed_keeps_market_evidence():
    concept = QueryPlanAssembler().assemble("EMA la gi?")
    mixed = QueryPlanAssembler().assemble("EMA la gi va EMA 20 hien tai cua BTCUSDm tren H1 la bao nhieu?")

    assert concept.primary_intent == "book_concept_explanation"
    assert not concept.current_market_request
    assert mixed.current_market_request
    assert mixed.conceptual_request
    assert mixed.primary_intent in {"market_state_analysis", "multi_intent"}
    assert "technical_indicator_values" in mixed.requested_analysis


def test_unknown_broker_alias_is_explicit_and_never_defaults_to_xauusd():
    plan = QueryPlanAssembler().assemble("EMA 20 hien tai cua UNKNOWNUSDx tren H1 la bao nhieu?")
    requirements = ContextRequirementPlanner().plan(plan)

    assert plan.entities.symbols == []
    assert plan.entities.unresolved_symbols == ["UNKNOWNUSDx"]
    assert any(item.startswith("unresolved_symbol:") for item in plan.ambiguity)
    assert all(need.target != "XAUUSD" for need in requirements.needs)


def test_fresh_completed_bars_build_deterministic_indicator_evidence_and_market_context():
    plan, requirements, execution, batch, live = _run()
    by_capability = {result.capability: result for result in batch.results}
    technical = by_capability["technical_snapshot"]

    assert by_capability["ohlcv"].freshness_status == "fresh"
    assert technical.status == "success"
    assert technical.data["canonical_symbol"] == "BTCUSD"
    assert technical.data["broker_symbol"] == "BTCUSDm"
    assert technical.data["timeframe"] == "H1"
    assert technical.data["freshness"] == "FRESH"
    assert set(technical.data["indicators"]) == {"ema_20_h1", "rsi_14_h1"}
    assert technical.data["as_of_completed_bar"]
    assert live.calls == [("BTCUSD", "H1", 60)]

    context = DecisionContextBuilder().build(
        original_query=QUERY,
        query_plan=plan,
        context_requirements=requirements,
        context_execution_plan=execution,
        acquisition_batch_result=batch,
    )
    assert context.market_data_required is True
    assert context.static_knowledge_required is False
    assert context.symbols == ["BTCUSD"]
    assert context.timeframe == "1h"

    bundle = EvidenceSelector().select(
        plan,
        batch.task_context_views[0],
        batch.results,
        "market_analysis",
    )
    technical_item = next(
        item for item in bundle.technical_evidence if item.evidence_type == "technical_snapshot"
    )
    assert "technical_snapshot" in bundle.required_evidence_roles
    assert technical_item.freshness_status == "fresh"
    assert "ema_20_h1" in technical_item.raw["indicators"]
    assert "rsi_14_h1" in technical_item.raw["indicators"]
    assert technical_item.raw["as_of_completed_bar"]


@pytest.mark.parametrize(
    ("live", "expected"),
    [
        (FakeLiveService(stale=True), "stale_ohlcv"),
        (FakeLiveService(bars=20), "technical_evidence_invalid"),
    ],
)
def test_stale_or_insufficient_history_blocks_without_fabricated_values(live, expected):
    _, _, _, batch, _ = _run(live=live)
    errors = {result.error_code for result in batch.results if result.error_code}
    assert expected in errors
    assert not any(result.capability == "technical_snapshot" and result.status == "success" for result in batch.results)
