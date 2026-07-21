import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.live_data_service import MarketDataService  # noqa: E402
from src.services.trading.calendar import CalendarContextBuilder, CalendarFormatter, ForexFactoryCalendarProvider  # noqa: E402
from src.services.trading.calendar.forex_factory_provider import normalize_impact  # noqa: E402
from src.services.trading.calendar.models import CalendarEvent, CalendarProviderHealth  # noqa: E402
from src.services.trading.calendar.relevance import relevance_for_event  # noqa: E402
from src.services.trading.market.feature_models import FeatureSnapshot  # noqa: E402
from src.services.trading.market.regime_detector import MarketRegimeDetector  # noqa: E402


class FixtureCalendarProvider(ForexFactoryCalendarProvider):
    def __init__(self, payload=None, error=False):
        super().__init__(url="https://fixture.local/calendar", cache_ttl_seconds=3600)
        self.payload = payload or []
        self.error = error
        self.calls = 0

    def _fetch_raw(self):
        self.calls += 1
        if self.error:
            raise TimeoutError("fixture unavailable")
        return self.payload


def raw_event(title, minutes=60, impact="High", country="USD", currency="USD"):
    when = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return {
        "title": title,
        "country": country,
        "currency": currency,
        "impact": impact,
        "date": when.isoformat(),
        "forecast": "n/a",
        "previous": "n/a",
        "actual": "",
    }


def calendar_event(title="CPI m/m", minutes=60, impact="HIGH", currency="USD"):
    when = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return CalendarEvent(
        event_id=f"event_{title}_{minutes}".replace(" ", "_"),
        title=title,
        currency=currency,
        country=currency,
        impact=impact,
        event_time_utc=when.isoformat(),
        event_time_local=when.astimezone(timezone.utc).isoformat(),
    )


def feature_snapshot(
    trend="UP",
    strength=0.5,
    quality="COMPLETE",
    chop=0.2,
    pullback=False,
    breakout=False,
    volatility="NORMAL",
):
    return FeatureSnapshot(
        feature_snapshot_id="feature_fixture",
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        provider_name="mt5_bridge",
        timeframes=["M15", "H1"],
        primary_timeframe="M15",
        indicator_snapshots={},
        trend_direction=trend,
        trend_strength=strength,
        volatility_state=volatility,
        momentum_state="BULLISH" if trend == "UP" else "BEARISH" if trend == "DOWN" else "NEUTRAL",
        pullback_detected=pullback,
        breakout_candidate=breakout,
        range_chop_score=chop,
        multi_timeframe_alignment="ALIGNED_UP" if trend == "UP" else "ALIGNED_DOWN" if trend == "DOWN" else "MIXED",
        spread_state="OK",
        data_quality_status=quality,
    )


class MarketRegimeCalendarContextTests(unittest.TestCase):
    def test_forex_factory_json_parses_event_datetime_and_local_time(self):
        provider = FixtureCalendarProvider([raw_event("CPI m/m", minutes=90, impact="High")])
        events = provider.fetch_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].impact, "HIGH")
        self.assertEqual(events[0].currency, "USD")
        parsed_utc = datetime.fromisoformat(events[0].event_time_utc)
        parsed_local = datetime.fromisoformat(events[0].event_time_local)
        self.assertIsNotNone(parsed_utc.tzinfo)
        self.assertIsNotNone(parsed_local.tzinfo)

    def test_impact_normalization(self):
        self.assertEqual(normalize_impact("High"), "HIGH")
        self.assertEqual(normalize_impact("Medium"), "MEDIUM")
        self.assertEqual(normalize_impact("Low"), "LOW")
        self.assertEqual(normalize_impact("Other"), "UNKNOWN")

    def test_calendar_cache_ttl_behavior(self):
        provider = FixtureCalendarProvider([raw_event("NFP", minutes=120)])
        first = provider.fetch_events()
        second = provider.fetch_events()
        self.assertEqual(len(first), len(second))
        self.assertEqual(provider.calls, 1)
        self.assertTrue(provider.health_check().cache_used)

    def test_calendar_provider_unavailable_returns_safe_status(self):
        provider = FixtureCalendarProvider(error=True)
        self.assertEqual(provider.fetch_events(), [])
        self.assertEqual(provider.health_check().status, "UNAVAILABLE")

    def test_legacy_get_economic_calendar_returns_formatted_text_and_filters(self):
        provider = FixtureCalendarProvider(
            [
                raw_event("CPI m/m", minutes=60, impact="High"),
                raw_event("Minor Event", minutes=120, impact="Low", country="EUR", currency="EUR"),
            ]
        )
        service = MarketDataService(provider=NoopMarketProvider())
        service.calendar_provider = provider
        text = service.get_economic_calendar("High")
        self.assertIn("**Economic events this week:**", text)
        self.assertIn("[High] CPI m/m", text)
        self.assertNotIn("Minor Event", text)

    def test_calendar_formatter_no_matching_events(self):
        self.assertEqual(CalendarFormatter.format_for_chatbot([], "High"), "Economic calendar: no matching events found.")

    def test_structured_calendar_context_and_xauusd_relevance(self):
        event = calendar_event("US CPI inflation report", minutes=45)
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[event])
        relevance = relevance_for_event("XAUUSD", event)
        self.assertGreaterEqual(relevance.relevance_score, 0.7)
        self.assertEqual(context.next_high_impact_event.event_id, event.event_id)
        self.assertIsNotNone(context.minutes_to_next_high_impact_event)
        self.assertIn(context.calendar_risk_state, {"UPCOMING_HIGH_IMPACT", "IMMEDIATE_HIGH_IMPACT"})

    def test_non_relevant_event_lower_relevance(self):
        event = calendar_event("French Services PMI", minutes=60, impact="LOW", currency="EUR")
        relevance = relevance_for_event("XAUUSD", event)
        self.assertLess(relevance.relevance_score, 0.25)

    def test_calendar_risk_state_clear(self):
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[calendar_event("CPI", minutes=240)])
        self.assertEqual(context.calendar_risk_state, "CLEAR")

    def test_calendar_risk_state_upcoming(self):
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[calendar_event("CPI", minutes=45)])
        self.assertEqual(context.calendar_risk_state, "UPCOMING_HIGH_IMPACT")

    def test_calendar_risk_state_immediate(self):
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[calendar_event("CPI", minutes=5)])
        self.assertEqual(context.calendar_risk_state, "IMMEDIATE_HIGH_IMPACT")

    def test_calendar_risk_state_post_event_cooldown(self):
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[calendar_event("CPI", minutes=-30)])
        self.assertEqual(context.calendar_risk_state, "POST_EVENT_COOLDOWN")

    def test_calendar_failure_does_not_crash_context(self):
        context = CalendarContextBuilder(FixtureCalendarProvider(error=True)).build("XAUUSD")
        self.assertEqual(context.calendar_risk_state, "UNKNOWN")
        self.assertTrue(context.warnings)

    def test_regime_detector_unknown_on_invalid_data_quality(self):
        regime = MarketRegimeDetector().detect(feature_snapshot(quality="INVALID"))
        self.assertEqual(regime.primary_regime, "UNKNOWN")
        self.assertIn("DATA_QUALITY_INVALID", regime.blockers)

    def test_regime_detector_news_risk_from_immediate_calendar(self):
        context = CalendarContextBuilder(FixtureCalendarProvider()).build("XAUUSD", events=[calendar_event("CPI", minutes=5)])
        regime = MarketRegimeDetector().detect(feature_snapshot(), context)
        self.assertEqual(regime.primary_regime, "NEWS_RISK")
        self.assertIn("IMMEDIATE_HIGH_IMPACT_EVENT", regime.blockers)

    def test_regime_detector_trending_up_down_and_choppy(self):
        detector = MarketRegimeDetector()
        self.assertEqual(detector.detect(feature_snapshot("UP", strength=0.5, chop=0.2)).primary_regime, "TRENDING_UP")
        self.assertEqual(detector.detect(feature_snapshot("DOWN", strength=0.5, chop=0.2)).primary_regime, "TRENDING_DOWN")
        self.assertIn(detector.detect(feature_snapshot("SIDEWAYS", strength=0.05, chop=0.9)).primary_regime, {"RANGING", "CHOPPY"})

    def test_regime_detector_pullbacks(self):
        detector = MarketRegimeDetector()
        self.assertEqual(detector.detect(feature_snapshot("UP", pullback=True)).primary_regime, "PULLBACK_UPTREND")
        self.assertEqual(detector.detect(feature_snapshot("DOWN", pullback=True)).primary_regime, "PULLBACK_DOWNTREND")

    def test_regime_detector_secondary_regimes(self):
        regime = MarketRegimeDetector().detect(feature_snapshot("UP", breakout=True, volatility="EXTREME"))
        self.assertIn("HIGH_VOLATILITY", regime.secondary_regimes)
        self.assertIn("BREAKOUT_CANDIDATE", regime.secondary_regimes)

    def test_market_regime_snapshot_contains_no_actionable_fields(self):
        payload = json.dumps(MarketRegimeDetector().detect(feature_snapshot()).as_dict()).lower()
        for forbidden in ["buy", "sell", "trade_decision", "entry", "stop-loss", "take-profit", "lot", "account-risk"]:
            self.assertNotIn(forbidden, payload)

    def test_regime_and_calendar_modules_do_not_import_metatrader5_or_llm(self):
        files = [
            PROJECT_ROOT / "src" / "services" / "trading" / "market" / "regime_detector.py",
            PROJECT_ROOT / "src" / "services" / "trading" / "market" / "regime_models.py",
            PROJECT_ROOT / "src" / "services" / "trading" / "calendar" / "calendar_context.py",
            PROJECT_ROOT / "src" / "services" / "trading" / "calendar" / "forex_factory_provider.py",
        ]
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)
        self.assertNotIn("MetaTrader5", text)
        self.assertNotIn("ChatOpenAI", text)
        self.assertNotIn("openai", text.lower())

    def test_no_order_send_oanda_rest_qdrant_reset_or_rag_imports(self):
        files = list((PROJECT_ROOT / "src" / "services" / "trading").rglob("*.py"))
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)
        text = text.replace("mt5_order_send_available", "mt5_order_submission_available")
        text = text.replace("order_send_allowed", "order_submission_allowed")
        self.assertNotIn("order" + "_send", text)
        self.assertNotIn("api-fxtrade" + ".oanda.com", text)
        self.assertNotIn("delete" + "_collection", text)
        self.assertNotIn("recreate" + "_collection", text)
        self.assertNotIn("ContextAcquisitionExecutor", text)


class NoopMarketProvider:
    provider_name = "noop"

    def health_check(self):
        return CalendarProviderHealth("noop", status="UNAVAILABLE")

    def close(self):
        return None


if __name__ == "__main__":
    unittest.main()
