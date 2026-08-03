from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from src.config import Config


SUPPORTED_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4", "D1")

_DURATION_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

_ALIASES = {
    "1M": "M1",
    "M1": "M1",
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


def timeframe_duration_seconds(timeframe: str) -> int:
    return _DURATION_SECONDS.get(normalize_timeframe(timeframe), 0)


def default_symbol() -> str:
    return str(getattr(Config, "MARKET_DEFAULT_SYMBOL", "XAUUSD") or "XAUUSD").upper()


def broker_symbol_for(symbol: str) -> str:
    logical = str(symbol or default_symbol()).upper().replace("/", "").replace("_", "")
    value = getattr(Config, f"MARKET_BROKER_SYMBOL_{logical}", "")
    if value:
        return str(value)
    value = getattr(Config, f"MT5_SYMBOL_MAP_{logical}", "")
    return str(value or logical)


@dataclass(frozen=True)
class SymbolResolution:
    raw_symbol: str
    canonical_symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNRESOLVED"


def resolve_symbol(symbol: str) -> SymbolResolution:
    raw = str(symbol or "").strip()
    normalized = _symbol_key(raw)
    for canonical in _configured_symbols():
        broker = broker_symbol_for(canonical)
        if normalized in {_symbol_key(canonical), _symbol_key(broker)}:
            return SymbolResolution(raw, canonical, broker, "RESOLVED")
    return SymbolResolution(raw)


def resolve_symbols_from_text(text: str) -> List[SymbolResolution]:
    source = str(text or "")
    configured = []
    for canonical in _configured_symbols():
        for alias in (canonical, broker_symbol_for(canonical)):
            if alias and re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", source, re.IGNORECASE):
                configured.append(resolve_symbol(alias))
    candidates = re.findall(r"\b[A-Za-z]{3,8}USD[A-Za-z0-9._-]*\b", source, re.IGNORECASE)
    resolved = configured + [resolve_symbol(candidate) for candidate in candidates]
    output: List[SymbolResolution] = []
    seen = set()
    for item in resolved:
        key = (item.status, item.canonical_symbol or _symbol_key(item.raw_symbol))
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _configured_symbols() -> List[str]:
    prefixes = ("MARKET_BROKER_SYMBOL_", "MT5_SYMBOL_MAP_")
    symbols = {
        name.removeprefix(prefix)
        for prefix in prefixes
        for name in dir(Config)
        if name.startswith(prefix) and getattr(Config, name, "")
    }
    return sorted(symbols)


def _symbol_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
