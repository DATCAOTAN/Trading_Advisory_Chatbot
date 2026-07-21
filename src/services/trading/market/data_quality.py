from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundle
from src.services.trading.market.models import MarketSnapshot, OHLCVBar
from src.services.trading.market.timeframes import stale_seconds_for_timeframe


QUALITY_ORDER = {"INVALID": 4, "EMPTY": 3, "STALE": 2, "PARTIAL": 1, "COMPLETE": 0}


@dataclass
class DataQualityIssue:
    code: str
    message: str
    timeframe: str = ""
    severity: str = "WARN"

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class DataQualityReport:
    status: str = "EMPTY"
    issues: List[DataQualityIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    per_timeframe_quality: Dict[str, str] = field(default_factory=dict)
    latest_timestamp_by_timeframe: Dict[str, str] = field(default_factory=dict)
    provider_name: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "warnings": list(self.warnings),
            "per_timeframe_quality": dict(self.per_timeframe_quality),
            "latest_timestamp_by_timeframe": dict(self.latest_timestamp_by_timeframe),
            "provider_name": self.provider_name,
            "checked_at": self.checked_at,
        }


class DataQualityGate:
    def __init__(self, min_bars_for_indicators: int = 35):
        self.min_bars_for_indicators = min_bars_for_indicators

    def evaluate(self, bundle: MarketSnapshotBundle, required_timeframes: list[str] | None = None) -> DataQualityReport:
        issues: List[DataQualityIssue] = []
        warnings: List[str] = list(bundle.warnings)
        per_quality: Dict[str, str] = {}
        latest_by_tf: Dict[str, str] = {}
        required = set(required_timeframes or bundle.timeframes.keys())

        if bundle.provider_health and bundle.provider_health.status not in {"OK", "DEGRADED"}:
            issues.append(DataQualityIssue("PROVIDER_UNAVAILABLE", bundle.provider_health.message, severity="ERROR"))

        for timeframe in sorted(required):
            snapshot = bundle.timeframes.get(timeframe)
            if snapshot is None:
                per_quality[timeframe] = "EMPTY"
                issues.append(DataQualityIssue("MISSING_TIMEFRAME", "Required timeframe missing", timeframe, "ERROR"))
                continue
            quality, tf_issues, latest = self._evaluate_snapshot(snapshot)
            per_quality[timeframe] = quality
            if latest:
                latest_by_tf[timeframe] = latest
            issues.extend(tf_issues)

        if bundle.tick:
            if bundle.tick.spread is None:
                warnings.append("tick_spread_missing")
            elif bundle.tick.spread < 0:
                issues.append(DataQualityIssue("INVALID_SPREAD", "Tick spread is negative", severity="ERROR"))
        else:
            warnings.append("tick_missing")

        status = _aggregate_status(per_quality, issues, required)
        return DataQualityReport(
            status=status,
            issues=issues,
            warnings=warnings,
            per_timeframe_quality=per_quality,
            latest_timestamp_by_timeframe=latest_by_tf,
            provider_name=bundle.provider_name,
        )

    def _evaluate_snapshot(self, snapshot: MarketSnapshot) -> tuple[str, List[DataQualityIssue], str]:
        issues: List[DataQualityIssue] = []
        bars = list(snapshot.bars or [])
        timeframe = snapshot.timeframe
        if not timeframe:
            issues.append(DataQualityIssue("MISSING_TIMEFRAME_NAME", "Snapshot timeframe is missing", timeframe, "ERROR"))
        if not bars:
            issues.append(DataQualityIssue("EMPTY_BARS", "OHLCV bars are empty", timeframe, "ERROR"))
            return "EMPTY", issues, ""
        if len(bars) < self.min_bars_for_indicators:
            issues.append(DataQualityIssue("INSUFFICIENT_BARS", "Not enough bars for full indicator set", timeframe, "WARN"))

        parsed = [_parse_timestamp(bar.timestamp) for bar in bars]
        if any(value is None for value in parsed):
            issues.append(DataQualityIssue("INVALID_TIMESTAMP", "One or more timestamps are invalid", timeframe, "ERROR"))
        valid_times = [value for value in parsed if value is not None]
        if valid_times and valid_times != sorted(valid_times):
            issues.append(DataQualityIssue("UNSORTED_BARS", "Bars are not sorted by timestamp", timeframe, "WARN"))
        if len(set(valid_times)) != len(valid_times):
            issues.append(DataQualityIssue("DUPLICATE_TIMESTAMP", "Duplicate bar timestamp detected", timeframe, "ERROR"))

        for index, bar in enumerate(bars):
            _check_bar_values(bar, timeframe, index, issues)

        latest_timestamp = bars[-1].timestamp
        latest_dt = _parse_timestamp(latest_timestamp)
        if latest_dt is not None:
            age = (datetime.now(timezone.utc) - latest_dt).total_seconds()
            if age > stale_seconds_for_timeframe(timeframe):
                issues.append(DataQualityIssue("STALE_LATEST_BAR", "Latest candle is stale", timeframe, "WARN"))

        if any(issue.severity == "ERROR" for issue in issues):
            return "INVALID", issues, latest_timestamp
        if any(issue.code == "STALE_LATEST_BAR" for issue in issues):
            return "STALE", issues, latest_timestamp
        if len(bars) < self.min_bars_for_indicators:
            return "PARTIAL", issues, latest_timestamp
        return "COMPLETE", issues, latest_timestamp


def _check_bar_values(bar: OHLCVBar, timeframe: str, index: int, issues: List[DataQualityIssue]) -> None:
    values = [bar.open, bar.high, bar.low, bar.close]
    if any(value is None for value in values):
        issues.append(DataQualityIssue("MISSING_OHLC", f"OHLC value missing at index {index}", timeframe, "ERROR"))
        return
    if any(not _finite_float(value) for value in values):
        issues.append(DataQualityIssue("INVALID_OHLC", f"OHLC value invalid at index {index}", timeframe, "ERROR"))
    if bar.high < bar.low:
        issues.append(DataQualityIssue("HIGH_LOW_INVALID", f"High is below low at index {index}", timeframe, "ERROR"))
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
        issues.append(DataQualityIssue("OHLC_RANGE_INVALID", f"Open/close outside high/low at index {index}", timeframe, "ERROR"))
    if bar.volume is not None and bar.volume < 0:
        issues.append(DataQualityIssue("NEGATIVE_VOLUME", f"Volume negative at index {index}", timeframe, "ERROR"))


def _aggregate_status(per_quality: Dict[str, str], issues: List[DataQualityIssue], required: set[str]) -> str:
    if any(issue.severity == "ERROR" for issue in issues):
        return "INVALID"
    if not per_quality:
        return "EMPTY"
    if any(per_quality.get(timeframe) == "EMPTY" for timeframe in required):
        return "PARTIAL"
    if any(value == "STALE" for value in per_quality.values()):
        return "STALE"
    if all(value == "COMPLETE" for value in per_quality.values()):
        return "COMPLETE"
    return "PARTIAL"


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _finite_float(value: Any) -> bool:
    try:
        numeric = float(value)
        return numeric == numeric and numeric not in {float("inf"), float("-inf")}
    except Exception:
        return False
