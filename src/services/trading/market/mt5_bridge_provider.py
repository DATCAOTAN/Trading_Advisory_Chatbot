from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

from src.config import Config
from src.services.trading.market.models import (
    AccountSnapshot,
    MarketSnapshot,
    OHLCVBar,
    PositionSnapshot,
    ProviderHealth,
    TickSnapshot,
)


class MT5BridgeMarketDataProvider:
    provider_name = "mt5_bridge"

    def __init__(self, bridge_url: str | None = None, timeout_seconds: float | None = None, symbol_map: Mapping[str, str] | None = None):
        self.bridge_url = (bridge_url or getattr(Config, "MT5_BRIDGE_URL", "") or _default_bridge_url()).rstrip("/")
        self.timeout_seconds = float(timeout_seconds if timeout_seconds is not None else getattr(Config, "MT5_BRIDGE_TIMEOUT_SECONDS", 3))
        self.symbol_map = {str(k).upper(): str(v) for k, v in (symbol_map or _config_symbol_map()).items()}

    def health_check(self) -> ProviderHealth:
        try:
            data = self._get_json("/health")
            status = str(data.get("status") or "UNAVAILABLE").upper()
            if status not in {"OK", "DEGRADED", "UNAVAILABLE", "MISCONFIGURED"}:
                status = "DEGRADED"
            return ProviderHealth(
                provider_name=self.provider_name,
                status=status,
                message=str(data.get("message") or ""),
                details_redacted={k: v for k, v in data.items() if k not in {"account_login", "login", "password", "server"}},
            )
        except Exception as exc:
            return ProviderHealth(
                provider_name=self.provider_name,
                status="UNAVAILABLE",
                message=f"MT5 bridge unavailable: {type(exc).__name__}",
                details_redacted={"bridge_url": _redact_url(self.bridge_url)},
            )

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        try:
            data = self._get_json(
                "/ohlcv",
                {"symbol": normalized, "timeframe": timeframe, "count": max(1, int(count or 1))},
            )
            bars = [_bar_from_mapping(item, normalized, timeframe) for item in data.get("bars", []) or [] if isinstance(item, Mapping)]
            tick = data.get("tick") if isinstance(data.get("tick"), Mapping) else {}
            quality = str(data.get("data_quality") or ("COMPLETE" if bars else "EMPTY")).upper()
            if quality not in {"COMPLETE", "PARTIAL", "EMPTY", "STALE", "INVALID"}:
                quality = "PARTIAL" if bars else "EMPTY"
            return MarketSnapshot(
                symbol=symbol.upper(),
                timeframe=timeframe,
                bars=bars,
                latest_bid=_safe_float(data.get("latest_bid", tick.get("bid"))),
                latest_ask=_safe_float(data.get("latest_ask", tick.get("ask"))),
                spread=_safe_float(data.get("spread", tick.get("spread"))),
                source=str(data.get("source") or "mt5_terminal"),
                fetched_at=str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat()),
                provider_name=self.provider_name,
                data_quality=quality,
            )
        except Exception:
            return MarketSnapshot(
                symbol=symbol.upper(),
                timeframe=timeframe,
                bars=[],
                source="mt5_bridge",
                provider_name=self.provider_name,
                data_quality="EMPTY",
            )

    def get_latest_tick(self, symbol: str) -> TickSnapshot:
        normalized = self.normalize_symbol(symbol)
        try:
            data = self._get_json("/tick", {"symbol": normalized})
            return TickSnapshot(
                symbol=symbol.upper(),
                bid=_safe_float(data.get("bid")),
                ask=_safe_float(data.get("ask")),
                spread=_safe_float(data.get("spread")),
                timestamp=str(data.get("timestamp") or ""),
                provider_name=self.provider_name,
            )
        except Exception:
            return TickSnapshot(symbol=symbol.upper(), provider_name=self.provider_name)

    def get_positions(self, symbol: str | None = None) -> List[PositionSnapshot]:
        params = {"symbol": self.normalize_symbol(symbol)} if symbol else None
        try:
            data = self._get_json("/positions", params)
            rows = data.get("positions") if isinstance(data, Mapping) else []
            return [_position_from_mapping(item) for item in rows or [] if isinstance(item, Mapping)]
        except Exception:
            return []

    def get_account(self) -> AccountSnapshot:
        try:
            data = self._get_json("/account")
            return AccountSnapshot(
                account_id_hash=str(data.get("account_id_hash") or ""),
                server_redacted=str(data.get("server_redacted") or ""),
                currency=str(data.get("currency") or ""),
                balance=_safe_float(data.get("balance")),
                equity=_safe_float(data.get("equity")),
                margin=_safe_float(data.get("margin")),
                free_margin=_safe_float(data.get("free_margin")),
                leverage=_safe_int(data.get("leverage")),
                provider_name=self.provider_name,
                redacted=True,
            )
        except Exception:
            return AccountSnapshot(provider_name=self.provider_name, redacted=True)

    def normalize_symbol(self, symbol: str) -> str:
        key = str(symbol or "XAUUSD").upper().replace("_", "").replace("/", "")
        return self.symbol_map.get(key, key)

    def close(self) -> None:
        return None

    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        query = f"?{urllib.parse.urlencode(dict(params or {}))}" if params else ""
        req = urllib.request.Request(f"{self.bridge_url}{path}{query}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload or "{}")


def _bar_from_mapping(item: Mapping[str, Any], symbol: str, timeframe: str) -> OHLCVBar:
    return OHLCVBar(
        timestamp=str(item.get("timestamp") or item.get("time") or ""),
        open=float(item.get("open") or 0.0),
        high=float(item.get("high") or 0.0),
        low=float(item.get("low") or 0.0),
        close=float(item.get("close") or 0.0),
        volume=float(item.get("volume") or item.get("tick_volume") or 0.0),
        timeframe=str(item.get("timeframe") or timeframe),
        symbol=str(item.get("symbol") or symbol),
        source=str(item.get("source") or "mt5_terminal"),
    )


def _position_from_mapping(item: Mapping[str, Any]) -> PositionSnapshot:
    return PositionSnapshot(
        position_id_hash=str(item.get("position_id_hash") or ""),
        symbol=str(item.get("symbol") or ""),
        side=str(item.get("side") or ""),
        volume=_safe_float(item.get("volume")),
        open_time=str(item.get("open_time") or ""),
        open_price=_safe_float(item.get("open_price")),
        current_price=_safe_float(item.get("current_price")),
        pnl=_safe_float(item.get("pnl")),
        source=str(item.get("source") or "mt5_terminal"),
        redacted=True,
    )


def _config_symbol_map() -> Dict[str, str]:
    mapping = {"XAUUSD": getattr(Config, "MT5_SYMBOL_MAP_XAUUSD", "XAUUSD")}
    for key, value in os.environ.items():
        if key.startswith("MT5_SYMBOL_MAP_") and value:
            mapping[key.replace("MT5_SYMBOL_MAP_", "").upper()] = value
    return mapping


def _default_bridge_url() -> str:
    return "http://host.docker.internal:8765"


def _redact_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

