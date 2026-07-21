from __future__ import annotations

from typing import Iterable, List

from src.config import Config


SUPPORTED_TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1")

_ALIASES = {
    "5M": "M5",
    "M5": "M5",
    "15M": "M15",
    "M15": "M15",
    "1H": "H1",
    "H1": "H1",
    "4H": "H4",
    "H4": "H4",
    "1D": "D1",
    "D": "D1",
    "D1": "D1",
}


def normalize_timeframe(timeframe: str | None) -> str:
    raw = str(timeframe or "M15").strip().upper().replace(" ", "")
    return _ALIASES.get(raw, raw)


def normalize_timeframes(timeframes: Iterable[str] | None = None) -> List[str]:
    raw_items = list(timeframes or getattr(Config, "MARKET_DEFAULT_TIMEFRAMES", ["M15", "H1", "H4"]))
    normalized: List[str] = []
    for item in raw_items:
        value = normalize_timeframe(item)
        if value in SUPPORTED_TIMEFRAMES and value not in normalized:
            normalized.append(value)
    return normalized or ["M15", "H1", "H4"]


def stale_seconds_for_timeframe(timeframe: str) -> int:
    normalized = normalize_timeframe(timeframe)
    return int(getattr(Config, f"MARKET_STALE_BAR_SECONDS_{normalized}", 7200))


def default_symbol() -> str:
    return str(getattr(Config, "MARKET_DEFAULT_SYMBOL", "XAUUSD") or "XAUUSD").upper()


def broker_symbol_for(symbol: str) -> str:
    logical = str(symbol or default_symbol()).upper().replace("/", "").replace("_", "")
    value = getattr(Config, f"MARKET_BROKER_SYMBOL_{logical}", "")
    if value:
        return str(value)
    value = getattr(Config, f"MT5_SYMBOL_MAP_{logical}", "")
    return str(value or logical)
