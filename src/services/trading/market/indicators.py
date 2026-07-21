from __future__ import annotations

import math
from statistics import pstdev
from typing import List

from src.services.trading.market.feature_models import IndicatorSnapshot
from src.services.trading.market.models import MarketSnapshot, OHLCVBar


class IndicatorEngine:
    def compute(
        self,
        snapshot: MarketSnapshot,
        ema_fast_period: int = 12,
        ema_slow_period: int = 26,
        sma_fast_period: int = 20,
        sma_slow_period: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
    ) -> IndicatorSnapshot:
        bars = list(snapshot.bars or [])
        warnings: List[str] = []
        if not bars:
            return IndicatorSnapshot(snapshot.symbol, snapshot.timeframe, data_quality="EMPTY", warnings=["empty_bars"])

        closes = [_clean_number(bar.close) for bar in bars]
        highs = [_clean_number(bar.high) for bar in bars]
        lows = [_clean_number(bar.low) for bar in bars]
        opens = [_clean_number(bar.open) for bar in bars]
        closes = [value for value in closes if value is not None]
        if not closes:
            return IndicatorSnapshot(snapshot.symbol, snapshot.timeframe, data_quality="INVALID", warnings=["invalid_closes"])

        ema_fast_series = ema_series(closes, ema_fast_period)
        ema_slow_series = ema_series(closes, ema_slow_period)
        macd_line = _series_diff(ema_series(closes, 12), ema_series(closes, 26))
        macd_signal_series = ema_series([value for value in macd_line if value is not None], 9)
        macd = _last(macd_line)
        macd_signal = _last(macd_signal_series)
        macd_hist = (macd - macd_signal) if macd is not None and macd_signal is not None else None

        if len(closes) < sma_slow_period:
            warnings.append("insufficient_bars_for_slow_sma")
        if len(closes) < ema_slow_period:
            warnings.append("insufficient_bars_for_slow_ema")

        latest = bars[-1]
        latest_range = _safe_sub(latest.high, latest.low)
        latest_body = abs(float(latest.close) - float(latest.open))
        return IndicatorSnapshot(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            ema_fast=_last(ema_fast_series),
            ema_slow=_last(ema_slow_series),
            sma_fast=sma(closes, sma_fast_period),
            sma_slow=sma(closes, sma_slow_period),
            rsi=rsi(closes, rsi_period),
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            atr=atr(bars, atr_period),
            rolling_volatility=rolling_volatility(closes, min(20, len(closes))),
            latest_close=closes[-1],
            latest_range=latest_range,
            latest_body=latest_body,
            swing_high=max([value for value in highs[-10:] if value is not None], default=None),
            swing_low=min([value for value in lows[-10:] if value is not None], default=None),
            support_zones=_zones([value for value in lows[-50:] if value is not None], take_low=True),
            resistance_zones=_zones([value for value in highs[-50:] if value is not None], take_low=False),
            data_quality=snapshot.data_quality,
            warnings=warnings,
        )


def sma(values: List[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: List[float], period: int) -> List[float | None]:
    if period <= 0 or not values:
        return []
    alpha = 2 / (period + 1)
    result: List[float | None] = []
    ema_value: float | None = None
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        if ema_value is None:
            ema_value = sum(values[index + 1 - period : index + 1]) / period
        else:
            ema_value = alpha * value + (1 - alpha) * ema_value
        result.append(ema_value)
    return result


def rsi(values: List[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(bars: List[OHLCVBar], period: int = 14) -> float | None:
    if len(bars) <= period:
        return None
    true_ranges: List[float] = []
    for previous, current in zip(bars[-period - 1 : -1], bars[-period:]):
        high = float(current.high)
        low = float(current.low)
        prev_close = float(previous.close)
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(true_ranges) / period if true_ranges else None


def rolling_volatility(values: List[float], period: int = 20) -> float | None:
    if len(values) < max(2, period):
        return None
    returns: List[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        if previous:
            returns.append((current - previous) / previous)
    return pstdev(returns) if len(returns) > 1 else None


def _series_diff(left: List[float | None], right: List[float | None]) -> List[float | None]:
    values: List[float | None] = []
    for a, b in zip(left, right):
        values.append((a - b) if a is not None and b is not None else None)
    return values


def _last(values: List[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None and _is_finite(value):
            return float(value)
    return None


def _safe_sub(left: float, right: float) -> float | None:
    if _is_finite(left) and _is_finite(right):
        return float(left) - float(right)
    return None


def _clean_number(value: float) -> float | None:
    if _is_finite(value):
        return float(value)
    return None


def _is_finite(value: float | None) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def _zones(values: List[float], take_low: bool) -> List[float]:
    if not values:
        return []
    ordered = sorted(values)
    candidates = ordered[:3] if take_low else ordered[-3:]
    return sorted({round(value, 2) for value in candidates})
