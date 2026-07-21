from __future__ import annotations

from src.config import Config
from src.services.trading.calendar.models import CalendarEvent, SymbolCalendarRelevance


def relevance_for_event(symbol: str, event: CalendarEvent) -> SymbolCalendarRelevance:
    logical_symbol = str(symbol or "XAUUSD").upper().replace("/", "").replace("_", "")
    currencies = _configured_list(f"MARKET_SYMBOL_RELEVANT_CURRENCIES_{logical_symbol}", "USD")
    keywords = _configured_list(
        f"MARKET_SYMBOL_RELEVANT_KEYWORDS_{logical_symbol}",
        "gold,inflation,cpi,nfp,fomc,rate,yield,fed",
    )
    score = 0.0
    reasons: list[str] = []
    event_currency = str(event.currency or event.country or "").upper()
    if event_currency in currencies:
        score += 0.6
        reasons.append(f"currency:{event_currency}")
    title = str(event.title or "").lower()
    matched_keywords = [keyword for keyword in keywords if keyword and keyword.lower() in title]
    if matched_keywords:
        score += min(0.3, 0.1 * len(matched_keywords))
        reasons.append("keywords:" + ",".join(matched_keywords[:3]))
    if event.impact == "HIGH":
        score += 0.1
        reasons.append("impact:HIGH")
    elif event.impact == "MEDIUM":
        score += 0.05
    return SymbolCalendarRelevance(
        symbol=logical_symbol,
        relevant_currencies=currencies,
        relevant_event_keywords=keywords,
        relevance_score=_clamp(score),
        reason=";".join(reasons) if reasons else "not_relevant",
    )


def is_relevant(symbol: str, event: CalendarEvent, threshold: float = 0.25) -> bool:
    return relevance_for_event(symbol, event).relevance_score >= threshold


def _configured_list(name: str, default: str) -> list[str]:
    value = str(getattr(Config, name, default) or default)
    return [item.strip().upper() if len(item.strip()) <= 3 else item.strip().lower() for item in value.split(",") if item.strip()]


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
