from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Iterable

from src.config import Config
from src.services.trading.calendar.calendar_context import CalendarContextBuilder
from src.services.trading.calendar.models import CalendarContext
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.live_feature_service import LiveFeatureResult, LiveFeatureService
from src.services.trading.market.regime_detector import MarketRegimeDetector
from src.services.trading.market.regime_models import MarketRegimeSnapshot


@dataclass
class LiveRegimeResult:
    feature_result: LiveFeatureResult
    calendar_context: CalendarContext
    regime_snapshot: MarketRegimeSnapshot
    calendar_latency_ms: float
    regime_latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_result": self.feature_result.as_dict(),
            "calendar_context": self.calendar_context.as_dict(),
            "regime_snapshot": self.regime_snapshot.as_dict(),
            "calendar_latency_ms": round(self.calendar_latency_ms, 3),
            "regime_latency_ms": round(self.regime_latency_ms, 3),
        }


class LiveRegimeService:
    def __init__(
        self,
        feature_service: LiveFeatureService | None = None,
        calendar_context_builder: CalendarContextBuilder | None = None,
        regime_detector: MarketRegimeDetector | None = None,
    ):
        self.feature_service = feature_service or LiveFeatureService()
        self.calendar_context_builder = calendar_context_builder or CalendarContextBuilder()
        self.regime_detector = regime_detector or MarketRegimeDetector()

    def build_regime(
        self,
        symbol: str | None = None,
        timeframes: Iterable[str] | None = None,
        candle_count: int | None = None,
    ) -> LiveRegimeResult:
        logical_symbol = symbol or getattr(Config, "MARKET_DEFAULT_SYMBOL", "XAUUSD")
        feature_result = self.feature_service.build_features(logical_symbol, timeframes, candle_count)
        start = perf_counter()
        calendar_context = self.calendar_context_builder.build(symbol=logical_symbol)
        calendar_latency_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        regime_snapshot = self.regime_detector.detect(feature_result.feature_snapshot, calendar_context)
        regime_latency_ms = (perf_counter() - start) * 1000
        return LiveRegimeResult(feature_result, calendar_context, regime_snapshot, calendar_latency_ms, regime_latency_ms)

    def detect_from_snapshot(self, feature_snapshot: FeatureSnapshot, calendar_context: CalendarContext | None = None) -> MarketRegimeSnapshot:
        return self.regime_detector.detect(feature_snapshot, calendar_context)
