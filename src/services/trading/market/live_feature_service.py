from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Iterable

from src.config import Config
from src.services.trading.market.data_quality import DataQualityGate, DataQualityReport
from src.services.trading.market.feature_engine import FeatureEngine
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundle, MarketSnapshotBundleBuilder
from src.services.trading.market.timeframes import default_symbol, normalize_timeframes


@dataclass
class LiveFeatureResult:
    bundle: MarketSnapshotBundle
    quality_report: DataQualityReport
    feature_snapshot: FeatureSnapshot
    bundle_latency_ms: float
    feature_latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle.as_dict(),
            "quality_report": self.quality_report.as_dict(),
            "feature_snapshot": self.feature_snapshot.as_dict(),
            "bundle_latency_ms": round(self.bundle_latency_ms, 3),
            "feature_latency_ms": round(self.feature_latency_ms, 3),
        }


class LiveFeatureService:
    def __init__(
        self,
        bundle_builder: MarketSnapshotBundleBuilder | None = None,
        data_quality_gate: DataQualityGate | None = None,
        feature_engine: FeatureEngine | None = None,
    ):
        self.bundle_builder = bundle_builder or MarketSnapshotBundleBuilder()
        self.data_quality_gate = data_quality_gate or DataQualityGate()
        self.feature_engine = feature_engine or FeatureEngine()

    def build_features(
        self,
        symbol: str | None = None,
        timeframes: Iterable[str] | None = None,
        candle_count: int | None = None,
    ) -> LiveFeatureResult:
        normalized_timeframes = normalize_timeframes(timeframes)
        start = perf_counter()
        bundle = self.bundle_builder.build(
            symbol=symbol or default_symbol(),
            timeframes=normalized_timeframes,
            candle_count=candle_count or getattr(Config, "MARKET_DEFAULT_CANDLE_COUNT", 300),
        )
        bundle_latency_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        quality_report = self.data_quality_gate.evaluate(bundle, normalized_timeframes)
        feature_snapshot = self.feature_engine.compute(bundle, quality_report, normalized_timeframes[0])
        feature_latency_ms = (perf_counter() - start) * 1000
        return LiveFeatureResult(bundle, quality_report, feature_snapshot, bundle_latency_ms, feature_latency_ms)
