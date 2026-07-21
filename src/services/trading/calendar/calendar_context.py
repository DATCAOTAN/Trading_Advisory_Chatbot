from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable

from src.config import Config
from src.services.trading.calendar.forex_factory_provider import ForexFactoryCalendarProvider
from src.services.trading.calendar.models import CalendarContext, CalendarEvent
from src.services.trading.calendar.provider import CalendarProvider
from src.services.trading.calendar.relevance import relevance_for_event


class CalendarContextBuilder:
    def __init__(self, provider: CalendarProvider | None = None):
        self.provider = provider or ForexFactoryCalendarProvider()

    def build(
        self,
        symbol: str = "XAUUSD",
        now: datetime | None = None,
        events: Iterable[CalendarEvent] | None = None,
    ) -> CalendarContext:
        created = now or datetime.now(timezone.utc)
        warnings: list[str] = []
        errors: list[str] = []
        if events is None:
            all_events = self.provider.fetch_events()
            health = self.provider.health_check()
            cache_status = "HIT" if health.cache_used else "MISS"
            if health.status not in {"OK", "DEGRADED"}:
                warnings.append(f"calendar_provider_{health.status.lower()}:{health.message}")
        else:
            all_events = list(events)
            health = self.provider.health_check()
            cache_status = "SUPPLIED"

        relevant_events = [
            event
            for event in all_events
            if relevance_for_event(symbol, event).relevance_score >= 0.25
        ]
        relevant_events.sort(key=lambda event: event.event_time_utc or "")
        high_impact = [event for event in relevant_events if event.impact == "HIGH"]
        next_event, minutes_to_next = _next_high_impact(high_impact, created)
        recent_event, minutes_since_recent = _recent_high_impact(high_impact, created)
        risk_state = _risk_state(minutes_to_next, minutes_since_recent, bool(high_impact), warnings)

        if not all_events and not warnings:
            warnings.append("calendar_events_empty")
        return CalendarContext(
            context_id=_context_id(symbol, created, relevant_events),
            symbol=str(symbol or "XAUUSD").upper(),
            created_at=created.isoformat(),
            provider_name=getattr(self.provider, "provider_name", "unknown"),
            events=list(all_events),
            relevant_events=relevant_events,
            next_high_impact_event=next_event,
            minutes_to_next_high_impact_event=minutes_to_next,
            recent_high_impact_event=recent_event,
            minutes_since_recent_high_impact_event=minutes_since_recent,
            calendar_risk_state=risk_state,
            warnings=warnings,
            errors=errors,
            cache_status=cache_status,
            source=getattr(self.provider, "provider_name", "unknown"),
        )


def _next_high_impact(events: list[CalendarEvent], now: datetime) -> tuple[CalendarEvent | None, float | None]:
    future: list[tuple[datetime, CalendarEvent]] = []
    for event in events:
        parsed = _parse_time(event.event_time_utc)
        if parsed and parsed >= now:
            future.append((parsed, event))
    if not future:
        return None, None
    event_time, event = sorted(future, key=lambda item: item[0])[0]
    return event, round((event_time - now).total_seconds() / 60, 2)


def _recent_high_impact(events: list[CalendarEvent], now: datetime) -> tuple[CalendarEvent | None, float | None]:
    past: list[tuple[datetime, CalendarEvent]] = []
    for event in events:
        parsed = _parse_time(event.event_time_utc)
        if parsed and parsed <= now:
            past.append((parsed, event))
    if not past:
        return None, None
    event_time, event = sorted(past, key=lambda item: item[0], reverse=True)[0]
    return event, round((now - event_time).total_seconds() / 60, 2)


def _risk_state(minutes_to_next: float | None, minutes_since_recent: float | None, has_high_impact: bool, warnings: list[str]) -> str:
    if warnings and not has_high_impact:
        return "UNKNOWN"
    immediate = float(getattr(Config, "ECONOMIC_CALENDAR_IMMEDIATE_EVENT_WINDOW_MINUTES", 15))
    pre = float(getattr(Config, "ECONOMIC_CALENDAR_PRE_EVENT_WINDOW_MINUTES", 60))
    post = float(getattr(Config, "ECONOMIC_CALENDAR_POST_EVENT_WINDOW_MINUTES", 60))
    if minutes_to_next is not None:
        if 0 <= minutes_to_next <= immediate:
            return "IMMEDIATE_HIGH_IMPACT"
        if 0 <= minutes_to_next <= pre:
            return "UPCOMING_HIGH_IMPACT"
    if minutes_since_recent is not None:
        if 0 <= minutes_since_recent <= immediate:
            return "EVENT_ACTIVE"
        if 0 <= minutes_since_recent <= post:
            return "POST_EVENT_COOLDOWN"
    return "CLEAR"


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _context_id(symbol: str, created: datetime, relevant_events: list[CalendarEvent]) -> str:
    event_ids = ",".join(event.event_id for event in relevant_events[:10])
    digest = hashlib.sha256(f"{symbol}|{created.isoformat()}|{event_ids}".encode("utf-8")).hexdigest()[:16]
    return f"calendar_context_{digest}"
