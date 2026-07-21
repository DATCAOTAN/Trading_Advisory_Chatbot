from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import Config
from src.services.trading.calendar.models import CalendarEvent


class CalendarFormatter:
    @staticmethod
    def format_for_chatbot(events: list[CalendarEvent], impact: str = "All") -> str:
        filtered = filter_by_impact(events, impact)
        if not filtered:
            return "Economic calendar: no matching events found."
        lines = []
        timezone_name = getattr(Config, "ECONOMIC_CALENDAR_LOCAL_TIMEZONE", "Asia/Ho_Chi_Minh")
        for event in filtered:
            date_str = _format_local_time(event, timezone_name)
            country = event.country or event.currency or "N/A"
            impact_label = event.impact.title() if event.impact else "Low"
            lines.append(f"{date_str} | {country} | [{impact_label}] {event.title}")
        return "**Economic events this week:**\n\n" + "\n".join(lines)


def filter_by_impact(events: list[CalendarEvent], impact: str = "All") -> list[CalendarEvent]:
    normalized = str(impact or "All").strip().upper()
    if normalized in {"", "ALL"}:
        return list(events)
    return [event for event in events if str(event.impact or "").upper() == normalized]


def _format_local_time(event: CalendarEvent, timezone_name: str) -> str:
    raw = event.event_time_local or event.event_time_utc
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(raw)
