from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import requests

from src.config import Config
from src.services.trading.calendar.models import CalendarEvent, CalendarProviderHealth


class ForexFactoryCalendarProvider:
    provider_name = "forex_factory"

    def __init__(
        self,
        url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: int | None = None,
        local_timezone: str | None = None,
    ):
        self.url = url or getattr(
            Config,
            "FOREX_FACTORY_CALENDAR_URL",
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        )
        self.timeout_seconds = float(timeout_seconds or getattr(Config, "ECONOMIC_CALENDAR_TIMEOUT_SECONDS", 5))
        self.cache_ttl_seconds = int(cache_ttl_seconds or getattr(Config, "ECONOMIC_CALENDAR_CACHE_TTL_SECONDS", 3600))
        self.local_timezone = str(local_timezone or getattr(Config, "ECONOMIC_CALENDAR_LOCAL_TIMEZONE", "Asia/Ho_Chi_Minh"))
        self._cache_events: list[CalendarEvent] = []
        self._cache_time: datetime | None = None
        self._last_health = CalendarProviderHealth(self.provider_name, status="UNAVAILABLE", message="not_checked")

    def health_check(self) -> CalendarProviderHealth:
        return self._last_health

    def fetch_events(self, force_refresh: bool = False) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        if not force_refresh and self._cache_events and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < self.cache_ttl_seconds:
                self._last_health = CalendarProviderHealth(
                    self.provider_name,
                    status="OK",
                    message="cache_hit",
                    cache_used=True,
                    details_redacted={"event_count": len(self._cache_events)},
                )
                return list(self._cache_events)

        try:
            raw_events = self._fetch_raw()
            events = self._parse_events(raw_events, now)
            self._cache_events = events
            self._cache_time = now
            self._last_health = CalendarProviderHealth(
                self.provider_name,
                status="OK",
                message="calendar_loaded",
                cache_used=False,
                details_redacted={"event_count": len(events)},
            )
            return list(events)
        except Exception as exc:
            if self._cache_events:
                self._last_health = CalendarProviderHealth(
                    self.provider_name,
                    status="DEGRADED",
                    message=f"using_cached_events_after_{type(exc).__name__}",
                    cache_used=True,
                    details_redacted={"event_count": len(self._cache_events)},
                )
                return list(self._cache_events)
            self._last_health = CalendarProviderHealth(
                self.provider_name,
                status="UNAVAILABLE",
                message=type(exc).__name__,
                cache_used=False,
                details_redacted={"event_count": 0},
            )
            return []

    def close(self) -> None:
        return None

    def _fetch_raw(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Trading-Advisory-Chatbot/1.0"}
        response = requests.get(self.url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def _parse_events(self, payload: list[dict[str, Any]], fetched_at: datetime) -> list[CalendarEvent]:
        events: List[CalendarEvent] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            event_time_utc = _parse_event_time(item.get("date"))
            event_time_local = _to_local_iso(event_time_utc, self.local_timezone)
            currency = str(item.get("currency") or item.get("country") or "").upper()
            country = str(item.get("country") or currency)
            title = str(item.get("title") or "").strip()
            impact = normalize_impact(item.get("impact"))
            events.append(
                CalendarEvent(
                    event_id=_event_id(title, currency, event_time_utc),
                    title=title,
                    currency=currency,
                    country=country,
                    impact=impact,
                    event_time_utc=event_time_utc,
                    event_time_local=event_time_local,
                    source=self.provider_name,
                    raw_source="forex_factory_json",
                    fetched_at=fetched_at.isoformat(),
                    previous=_safe_text(item.get("previous")),
                    forecast=_safe_text(item.get("forecast")),
                    actual=_safe_text(item.get("actual")),
                    metadata={"impact_raw": _safe_text(item.get("impact"))},
                )
            )
        events.sort(key=lambda event: event.event_time_utc or "")
        return events


def normalize_impact(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "high":
        return "HIGH"
    if raw in {"medium", "med"}:
        return "MEDIUM"
    if raw == "low":
        return "LOW"
    return "UNKNOWN"


def _parse_event_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _to_local_iso(event_time_utc: str, timezone_name: str) -> str:
    try:
        parsed = datetime.fromisoformat(event_time_utc.replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo(timezone_name)).isoformat()
    except Exception:
        return event_time_utc


def _event_id(title: str, currency: str, event_time_utc: str) -> str:
    digest = hashlib.sha256(f"{title}|{currency}|{event_time_utc}|forex_factory".encode("utf-8")).hexdigest()[:16]
    return f"calendar_event_{digest}"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
