"""Compatibility facade for live market data.

New trading code should depend on ``MarketDataProvider`` from
``src.services.trading.market``. This facade keeps existing callers working
while routing live price and OHLCV requests through the configured provider.

Default provider for this sprint: MT5 bridge over HTTP.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

import requests

from src.config import Config
from src.services.trading.market import (
    MarketSnapshot,
    ProviderRegistry,
    TickSnapshot,
    provider_status_summary,
)


class MarketDataService:
    def __init__(self, provider: Any | None = None):
        self.provider = provider or ProviderRegistry.build_provider()
        self._calendar_cache: Dict[str, Any] = {}
        self.forex_factory_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def provider_health(self):
        return self.provider.health_check()

    def provider_status(self) -> Dict[str, Any]:
        return provider_status_summary()

    def get_latest_tick(self, symbol: str = "XAUUSD") -> TickSnapshot:
        return self.provider.get_latest_tick(symbol)

    def get_market_snapshot(self, symbol: str = "XAUUSD", timeframe: str = "M15", count: int | None = None) -> MarketSnapshot:
        return self.provider.get_ohlcv(symbol, _normalize_timeframe(timeframe), count or Config.MT5_DEFAULT_CANDLE_COUNT)

    def get_live_price(self, symbol: str = "XAUUSD") -> str:
        tick = self.get_latest_tick(symbol)
        health = self.provider.health_check()
        if tick.bid is None and tick.ask is None:
            return (
                f"Live market data unavailable for {symbol.upper()} "
                f"(provider={self.provider.provider_name}, status={health.status})."
            )
        mid = _mid_price(tick)
        shown = f"{mid:,.2f}" if mid is not None else "n/a"
        timestamp = tick.timestamp or datetime.now(timezone.utc).isoformat()
        return (
            f"**{symbol.upper()}**: {shown} "
            f"(bid={_fmt(tick.bid)}, ask={_fmt(tick.ask)}, spread={_fmt(tick.spread)}, "
            f"updated={timestamp}) - Source: MT5 Bridge"
        )

    def get_historical_candles(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "1h",
        limit: int = 100,
        target_date: str | None = None,
        indicators: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        snapshot = self.provider.get_ohlcv(symbol, _normalize_timeframe(timeframe), int(limit or Config.MT5_DEFAULT_CANDLE_COUNT))
        candles = [_legacy_bar(bar.as_dict()) for bar in snapshot.bars]
        if target_date:
            candles = self._apply_target_date_filter(candles, target_date, indicators)
        if indicators and candles:
            candles = self._calculate_indicators(candles, indicators)
        return candles[-limit:] if candles else []

    def get_positions(self, symbol: str | None = None):
        return self.provider.get_positions(symbol)

    def get_account(self):
        return self.provider.get_account()

    def get_economic_calendar(self, impact: str = "All") -> str:
        try:
            now = datetime.now()
            events = None
            if self._calendar_cache and (now - self._calendar_cache.get("time", datetime.min)).total_seconds() < 3600:
                events = self._calendar_cache.get("data")

            if not events:
                headers = {"User-Agent": "Trading-Advisory-Chatbot/1.0"}
                response = requests.get(self.forex_factory_url, headers=headers, timeout=5)
                if response.status_code != 200:
                    return f"Economic calendar unavailable (status={response.status_code})."
                events = response.json()
                self._calendar_cache["data"] = events
                self._calendar_cache["time"] = now

            target_events = [item for item in events if item.get("impact") == impact] if impact and impact != "All" else events
            if not target_events:
                return "Economic calendar: no matching events found."

            lines = []
            vn_tz = timezone(timedelta(hours=7))
            for event in target_events:
                date_str = str(event.get("date", ""))
                try:
                    date_str = datetime.fromisoformat(date_str).astimezone(vn_tz).strftime("%d/%m/%Y %H:%M")
                except Exception:
                    pass
                lines.append(
                    f"{date_str} | {event.get('country', event.get('currency', 'N/A'))} | "
                    f"[{event.get('impact', 'Low')}] {event.get('title', '')}"
                )
            return "**Economic events this week:**\n\n" + "\n".join(lines)
        except Exception as exc:
            return f"Economic calendar unavailable: {type(exc).__name__}"

    def get_latest_macro_report(self) -> str:
        return (
            "Automated macro report ingestion is not part of the MT5 bridge. "
            "Use indexed dynamic PDF/report evidence for macro report summaries."
        )

    def close(self) -> None:
        self.provider.close()

    def _apply_target_date_filter(self, candles: List[Dict[str, Any]], target_date: str, indicators: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        if not candles:
            return []
        try:
            fmt = "%Y-%m-%d %H:%M:%S" if len(target_date) > 10 else "%Y-%m-%d"
            target_vn = datetime.strptime(target_date, fmt)
            target_utc = target_vn - timedelta(hours=7)
            candidates = []
            for candle in candles:
                raw = str(candle.get("timestamp") or "")
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
                if parsed <= target_utc:
                    candidates.append((parsed, candle))
            if not candidates:
                return [{"error": f"No MT5 candle available before {target_date} VN time."}]
            candidates.sort(key=lambda item: item[0])
            return [candidates[-1][1]]
        except Exception:
            return candles

    def _calculate_indicators(self, candles: List[Dict[str, Any]], indicators: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        closes = [_safe_float(item.get("close")) for item in candles]
        for index, candle in enumerate(candles):
            for indicator in indicators:
                name = str(indicator.get("name", "")).lower()
                period = int(indicator.get("period", 14) or 14)
                values = [value for value in closes[max(0, index - period + 1) : index + 1] if value is not None]
                key = f"{name}_{period}"
                if name == "sma" and len(values) == period:
                    candle[key] = sum(values) / period
                elif name == "ema" and values:
                    candle[key] = _ema(values, period)
                elif name == "rsi" and len(values) == period:
                    candle[key] = _rsi(values)
        return candles


LiveDataService = MarketDataService

_live_data_service_instance: MarketDataService | None = None


def get_live_service() -> MarketDataService:
    global _live_data_service_instance
    if _live_data_service_instance is None:
        _live_data_service_instance = MarketDataService()
    return _live_data_service_instance


def _normalize_timeframe(timeframe: str) -> str:
    mapping = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D1"}
    raw = str(timeframe or "M15")
    return mapping.get(raw.lower(), raw.upper())


def _legacy_bar(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": str(item.get("timestamp") or ""),
        "open": float(item.get("open") or 0.0),
        "high": float(item.get("high") or 0.0),
        "low": float(item.get("low") or 0.0),
        "close": float(item.get("close") or 0.0),
        "volume": float(item.get("volume") or 0.0),
    }


def _mid_price(tick: TickSnapshot) -> float | None:
    if tick.bid is not None and tick.ask is not None:
        return (tick.bid + tick.ask) / 2
    return tick.bid if tick.bid is not None else tick.ask


def _fmt(value: Any) -> str:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "n/a"
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _ema(values: List[float], period: int) -> float:
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _rsi(values: List[float]) -> float:
    gains = []
    losses = []
    for previous, current in zip(values, values[1:]):
        change = current - previous
        if change >= 0:
            gains.append(change)
        else:
            losses.append(abs(change))
    avg_gain = sum(gains) / max(len(gains), 1)
    avg_loss = sum(losses) / max(len(losses), 1)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


if __name__ == "__main__":
    service = get_live_service()
    print(json.dumps(service.provider_status(), indent=2))
    print(service.get_live_price("XAUUSD"))
    print(json.dumps(service.get_historical_candles("XAUUSD", "M15", 2), indent=2))
