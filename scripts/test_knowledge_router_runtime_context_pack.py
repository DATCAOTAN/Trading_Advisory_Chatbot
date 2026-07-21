import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.live_data_service import MarketDataService  # noqa: E402
from src.services.trading.calendar.models import CalendarContext, CalendarEvent  # noqa: E402
from src.services.trading.knowledge import (  # noqa: E402
    KnowledgeRouter,
    KnowledgeSelectionValidator,
    MacroCard,
    MacroCardStore,
    MethodCard,
    MethodCardStore,
    RegimeMethodMapStore,
    RuntimeContextPackBuilder,
    StrategyPlaybook,
    StrategyPlaybookStore,
)
from src.services.trading.knowledge.models import RuntimeContextPack  # noqa: E402
from src.services.trading.market.feature_models import FeatureSnapshot  # noqa: E402
from src.services.trading.market.models import AccountSnapshot, MarketSnapshot, OHLCVBar, ProviderHealth, TickSnapshot  # noqa: E402
from src.services.trading.market.regime_models import MarketRegimeSnapshot  # noqa: E402


def feature_snapshot():
    return FeatureSnapshot(
        feature_snapshot_id="feature_fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        provider_name="mt5_bridge",
        timeframes=["M15", "H1", "H4"],
        primary_timeframe="M15",
        indicator_snapshots={},
        trend_direction="UP",
        trend_strength=0.55,
        volatility_state="NORMAL",
        momentum_state="BULLISH",
        pullback_detected=True,
        breakout_candidate=False,
        range_chop_score=0.25,
        multi_timeframe_alignment="ALIGNED_UP",
        spread_state="OK",
        data_quality_status="COMPLETE",
        source_snapshot_ids=["market_bundle_fixture"],
    )


def calendar_context(risk_state="CLEAR"):
    event_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    event = CalendarEvent(
        event_id="calendar_event_fixture",
        title="USD CPI inflation report",
        currency="USD",
        country="USD",
        impact="HIGH",
        event_time_utc=event_time.isoformat(),
        event_time_local=event_time.isoformat(),
    )
    return CalendarContext(
        context_id="calendar_context_fixture",
        symbol="XAUUSD",
        created_at=datetime.now(timezone.utc).isoformat(),
        provider_name="forex_factory",
        events=[event],
        relevant_events=[event],
        next_high_impact_event=event,
        minutes_to_next_high_impact_event=30,
        calendar_risk_state=risk_state,
        cache_status="SUPPLIED",
    )


def regime_snapshot(primary="PULLBACK_UPTREND", calendar_state="CLEAR"):
    return MarketRegimeSnapshot(
        regime_snapshot_id="regime_fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        primary_regime=primary,
        secondary_regimes=[],
        confidence=0.82,
        trend_direction="UP",
        volatility_state="NORMAL",
        momentum_state="BULLISH",
        range_chop_score=0.25,
        pullback_detected=True,
        breakout_candidate=False,
        multi_timeframe_alignment="ALIGNED_UP",
        calendar_risk_state=calendar_state,
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_context_fixture",
    )


def build_pack(mode="autonomous_live", primary="PULLBACK_UPTREND", calendar_state="CLEAR", selected_method=None):
    feature = feature_snapshot()
    calendar = calendar_context(calendar_state)
    regime = regime_snapshot(primary, calendar_state)
    candidates = KnowledgeRouter().route(mode, "XAUUSD", feature, calendar, regime, user_selected_method_id=selected_method)
    pack = RuntimeContextPackBuilder().build(candidates, feature, calendar, regime, mode, "XAUUSD", "XAUUSDm")
    return candidates, pack


class KnowledgeRouterRuntimeContextPackTests(unittest.TestCase):
    def test_card_schemas_validate_required_fields(self):
        method = MethodCard("m1", "Method", "book", ["data/knowledge_repository/book"])
        macro = MacroCard("ma1", "Macro", "report", ["data/knowledge_repository/report"])
        playbook = StrategyPlaybook("p1", "m1", "Playbook", ["ANY"])
        self.assertEqual(method.method_id, "m1")
        self.assertEqual(macro.macro_id, "ma1")
        self.assertEqual(playbook.playbook_id, "p1")

    def test_stores_load_json_cards_and_preserve_source_refs(self):
        self.assertTrue(MethodCardStore().load_all())
        self.assertTrue(MacroCardStore().load_all())
        self.assertTrue(StrategyPlaybookStore().load_all())
        first = MethodCardStore().load_all()[0]
        self.assertTrue(first.source_refs)

    def test_invalid_card_produces_warning_not_crash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(json.dumps({"method_id": "bad"}), encoding="utf-8")
            store = MethodCardStore(temp_dir)
            self.assertEqual(store.load_all(), [])
            self.assertTrue(store.warnings)

    def test_regime_method_map_loads(self):
        maps = RegimeMethodMapStore().load_all()
        self.assertTrue(any(item.regime == "PULLBACK_UPTREND" for item in maps))

    def test_advisory_mode_candidate_set_has_no_execution_fields(self):
        candidates, pack = build_pack("advisory_only")
        self.assertTrue(candidates.method_cards)
        payload = json.dumps(pack.as_dict()).lower()
        self.assertNotIn("order_send", payload)
        self.assertNotIn("trade_decision", payload)

    def test_human_confirmed_preserves_user_selected_method_and_rejects_others(self):
        candidates, pack = build_pack("human_confirmed_live", selected_method="vpa_effort_vs_result")
        self.assertEqual(candidates.method_cards[0].method_id, "vpa_effort_vs_result")
        self.assertTrue(any(item.reason == "human_confirmed_primary_method_locked" for item in candidates.rejected_items))
        result = KnowledgeSelectionValidator().validate(pack, expected_user_selected_method_id="vpa_effort_vs_result")
        self.assertTrue(result.passed, result.issues)

    def test_autonomous_mode_selects_by_regime_and_avoids_bad_regime(self):
        candidates, _pack = build_pack("autonomous_live", primary="NEWS_RISK", calendar_state="IMMEDIATE_HIGH_IMPACT")
        selected = [item.method_id for item in candidates.method_cards]
        self.assertIn("risk_management_core", selected)
        self.assertNotIn("al_brooks_trend_pullback", selected)

    def test_manage_position_prioritizes_risk_knowledge(self):
        candidates, _pack = build_pack("manage_existing_position")
        self.assertTrue(candidates.method_cards)
        self.assertTrue(all("risk" in item.domains or "risk" in item.method_id for item in candidates.method_cards))

    def test_news_risk_includes_macro_calendar_risk_card(self):
        _candidates, pack = build_pack("autonomous_live", primary="NEWS_RISK", calendar_state="IMMEDIATE_HIGH_IMPACT")
        macro_ids = [item["macro_id"] for item in pack.selected_macro_cards]
        self.assertIn("usd_high_impact_calendar_risk", macro_ids)

    def test_runtime_context_pack_includes_structured_summaries(self):
        _candidates, pack = build_pack()
        self.assertEqual(pack.feature_snapshot_summary["feature_snapshot_id"], "feature_fixture")
        self.assertEqual(pack.calendar_context_summary["context_id"], "calendar_context_fixture")
        self.assertEqual(pack.market_regime_summary["regime_snapshot_id"], "regime_fixture")

    def test_runtime_context_pack_excludes_raw_candles_and_full_raw_text(self):
        _candidates, pack = build_pack()
        payload = json.dumps(pack.as_dict()).lower()
        self.assertNotIn("raw_candles", payload)
        self.assertNotIn("full_pdf_text", payload)
        self.assertNotIn("raw_book_text", payload)
        self.assertNotIn("raw_report_text", payload)

    def test_candidate_counts_payload_size_and_source_refs(self):
        _candidates, pack = build_pack()
        self.assertLessEqual(len(pack.selected_method_cards), 3)
        self.assertLessEqual(len(pack.selected_macro_cards), 3)
        self.assertLessEqual(len(pack.selected_playbooks), 3)
        self.assertLessEqual(pack.payload_size_chars, 12000)
        self.assertTrue(pack.source_refs)

    def test_validator_catches_missing_source_refs(self):
        _candidates, pack = build_pack()
        pack.source_refs = []
        result = KnowledgeSelectionValidator().validate(pack)
        self.assertFalse(result.passed)
        self.assertIn("source_refs_missing", result.issues)

    def test_validator_catches_mode_method_mismatch(self):
        _candidates, pack = build_pack("human_confirmed_live", selected_method="al_brooks_trend_pullback")
        result = KnowledgeSelectionValidator().validate(pack, expected_user_selected_method_id="vpa_effort_vs_result")
        self.assertFalse(result.passed)
        self.assertIn("user_selected_method_not_preserved", result.issues)

    def test_validator_catches_oversized_context_pack(self):
        _candidates, pack = build_pack()
        pack.payload_size_chars = 999999
        result = KnowledgeSelectionValidator().validate(pack)
        self.assertFalse(result.passed)
        self.assertIn("context_pack_too_large", result.issues)

    def test_context_pack_contains_no_actionable_markers(self):
        _candidates, pack = build_pack()
        payload = json.dumps(pack.as_dict()).lower()
        for forbidden in ["buy", "sell", "trade_decision", "entry", "stop-loss", "take-profit", "lot", "account-risk"]:
            self.assertNotIn(forbidden, payload)

    def test_knowledge_modules_do_not_call_llm_or_import_metatrader5_or_facade_text(self):
        root = PROJECT_ROOT / "src" / "services" / "trading" / "knowledge"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.py"))
        self.assertNotIn("MetaTrader5", text)
        self.assertNotIn("ChatOpenAI", text)
        self.assertNotIn("openai", text.lower())
        self.assertNotIn("live_data_service", text)
        self.assertNotIn("get_live_price", text)
        self.assertNotIn("get_economic_calendar", text)

    def test_live_data_service_compatibility_methods_still_work(self):
        provider = FixtureMarketProvider()
        service = MarketDataService(provider)
        service.calendar_provider = FixtureCalendarProvider()
        self.assertIn("**XAUUSD**", service.get_live_price("XAUUSD"))
        candles = service.get_historical_candles("XAUUSD", "M15", limit=20, indicators=[{"name": "sma", "period": 14}])
        self.assertIsInstance(candles, list)
        self.assertIsInstance(candles[0], dict)
        self.assertTrue(any("sma_14" in item for item in candles))
        self.assertEqual(service.get_positions(), [])
        self.assertTrue(service.get_account().redacted)
        self.assertIn("**Economic events this week:**", service.get_economic_calendar("All"))
        self.assertIn("Automated macro report ingestion", service.get_latest_macro_report())

    def test_no_oanda_rest_qdrant_reset_or_rag_behavior_in_knowledge_modules(self):
        root = PROJECT_ROOT / "src" / "services" / "trading" / "knowledge"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*.py"))
        self.assertNotIn("api-fxtrade" + ".oanda.com", text)
        self.assertNotIn("delete" + "_collection", text)
        self.assertNotIn("recreate" + "_collection", text)
        self.assertNotIn("ContextAcquisitionExecutor", text)


class FixtureMarketProvider:
    provider_name = "mt5_bridge"

    def health_check(self):
        return ProviderHealth("mt5_bridge", status="OK", message="fixture")

    def get_latest_tick(self, symbol):
        return TickSnapshot(symbol=symbol, bid=2400.0, ask=2400.2, spread=0.2, timestamp=datetime.now(timezone.utc).isoformat())

    def get_ohlcv(self, symbol, timeframe, count):
        now = datetime.now(timezone.utc)
        bars = []
        for index in range(count):
            close = 2400.0 + index
            bars.append(
                OHLCVBar(
                    timestamp=(now - timedelta(minutes=15 * (count - index))).isoformat(),
                    open=close - 0.5,
                    high=close + 0.5,
                    low=close - 1.0,
                    close=close,
                    volume=100 + index,
                    timeframe=timeframe,
                    symbol=symbol,
                )
            )
        return MarketSnapshot(symbol=symbol, timeframe=timeframe, bars=bars, provider_name="mt5_bridge", data_quality="COMPLETE")

    def get_positions(self, symbol=None):
        return []

    def get_account(self):
        return AccountSnapshot(account_id_hash="hash_fixture", server_redacted="Fi***re", redacted=True)

    def close(self):
        return None


class FixtureCalendarProvider:
    provider_name = "forex_factory"

    def fetch_events(self, force_refresh=False):
        event_time = datetime.now(timezone.utc) + timedelta(minutes=60)
        return [
            CalendarEvent(
                event_id="calendar_event_fixture",
                title="USD CPI inflation report",
                currency="USD",
                country="USD",
                impact="HIGH",
                event_time_utc=event_time.isoformat(),
                event_time_local=event_time.isoformat(),
            )
        ]

    def health_check(self):
        return None


if __name__ == "__main__":
    unittest.main()
