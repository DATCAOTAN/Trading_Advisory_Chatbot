from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


CALENDAR_IMPACTS = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
CALENDAR_PROVIDER_STATUSES = {"OK", "DEGRADED", "UNAVAILABLE", "MISCONFIGURED"}
CALENDAR_RISK_STATES = {
    "CLEAR",
    "UPCOMING_HIGH_IMPACT",
    "IMMEDIATE_HIGH_IMPACT",
    "POST_EVENT_COOLDOWN",
    "EVENT_ACTIVE",
    "UNKNOWN",
}


@dataclass
class CalendarEvent:
    event_id: str
    title: str
    currency: str = ""
    country: str = ""
    impact: str = "UNKNOWN"
    event_time_utc: str = ""
    event_time_local: str = ""
    source: str = "forex_factory"
    raw_source: str = "forex_factory"
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous: str = ""
    forecast: str = ""
    actual: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "currency": self.currency,
            "country": self.country,
            "impact": self.impact,
            "event_time_utc": self.event_time_utc,
            "event_time_local": self.event_time_local,
            "source": self.source,
            "raw_source": self.raw_source,
            "fetched_at": self.fetched_at,
            "previous": self.previous,
            "forecast": self.forecast,
            "actual": self.actual,
            "metadata": dict(self.metadata),
        }


@dataclass
class CalendarProviderHealth:
    provider_name: str
    status: str = "UNAVAILABLE"
    message: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cache_used: bool = False
    details_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "status": self.status,
            "message": self.message,
            "checked_at": self.checked_at,
            "cache_used": bool(self.cache_used),
            "details_redacted": dict(self.details_redacted),
        }


@dataclass
class SymbolCalendarRelevance:
    symbol: str
    relevant_currencies: List[str] = field(default_factory=list)
    relevant_event_keywords: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "relevant_currencies": list(self.relevant_currencies),
            "relevant_event_keywords": list(self.relevant_event_keywords),
            "relevance_score": _clamp(self.relevance_score),
            "reason": self.reason,
        }


@dataclass
class CalendarContext:
    context_id: str
    symbol: str
    created_at: str
    provider_name: str
    events: List[CalendarEvent] = field(default_factory=list)
    relevant_events: List[CalendarEvent] = field(default_factory=list)
    next_high_impact_event: CalendarEvent | None = None
    minutes_to_next_high_impact_event: float | None = None
    recent_high_impact_event: CalendarEvent | None = None
    minutes_since_recent_high_impact_event: float | None = None
    calendar_risk_state: str = "UNKNOWN"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cache_status: str = "UNKNOWN"
    source: str = "forex_factory"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "symbol": self.symbol,
            "created_at": self.created_at,
            "provider_name": self.provider_name,
            "events": [event.as_dict() for event in self.events],
            "relevant_events": [event.as_dict() for event in self.relevant_events],
            "next_high_impact_event": self.next_high_impact_event.as_dict() if self.next_high_impact_event else None,
            "minutes_to_next_high_impact_event": _json_number(self.minutes_to_next_high_impact_event),
            "recent_high_impact_event": self.recent_high_impact_event.as_dict() if self.recent_high_impact_event else None,
            "minutes_since_recent_high_impact_event": _json_number(self.minutes_since_recent_high_impact_event),
            "calendar_risk_state": self.calendar_risk_state,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "cache_status": self.cache_status,
            "source": self.source,
        }


def _json_number(value: float | None) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return round(number, 4)
    except Exception:
        return None


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
