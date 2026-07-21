from __future__ import annotations

from typing import Protocol

from src.services.trading.calendar.models import CalendarEvent, CalendarProviderHealth


class CalendarProvider(Protocol):
    provider_name: str

    def health_check(self) -> CalendarProviderHealth:
        ...

    def fetch_events(self, force_refresh: bool = False) -> list[CalendarEvent]:
        ...

    def close(self) -> None:
        ...
