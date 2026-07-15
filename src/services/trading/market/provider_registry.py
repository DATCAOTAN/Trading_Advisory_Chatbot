from __future__ import annotations

from typing import Any, Dict

from src.config import Config
from src.services.trading.market.models import AccountSnapshot, MarketSnapshot, ProviderHealth, TickSnapshot
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider


class UnavailableMarketDataProvider:
    def __init__(self, provider_name: str, status: str = "UNAVAILABLE", message: str = ""):
        self.provider_name = provider_name
        self.status = status
        self.message = message or f"provider {provider_name} is unavailable"

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(self.provider_name, self.status, self.message)

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol.upper(), timeframe=timeframe, bars=[], source=self.provider_name, provider_name=self.provider_name, data_quality="EMPTY")

    def get_latest_tick(self, symbol: str) -> TickSnapshot:
        return TickSnapshot(symbol=symbol.upper(), provider_name=self.provider_name)

    def get_positions(self, symbol: str | None = None):
        return []

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(provider_name=self.provider_name, redacted=True)

    def normalize_symbol(self, symbol: str) -> str:
        return str(symbol or "XAUUSD").upper().replace("_", "").replace("/", "")

    def close(self) -> None:
        return None


class OandaLegacyMarketDataProvider(UnavailableMarketDataProvider):
    def __init__(self):
        if not getattr(Config, "OANDA_LEGACY_ENABLED", False):
            super().__init__("oanda_legacy", "MISCONFIGURED", "OANDA legacy provider disabled")
        elif not getattr(Config, "OANDA_API_KEY", "") or not getattr(Config, "OANDA_ACCOUNT_ID", ""):
            super().__init__("oanda_legacy", "MISCONFIGURED", "OANDA legacy credentials missing")
        else:
            super().__init__("oanda_legacy", "DEGRADED", "OANDA legacy provider is deprecated and not default")


class ProviderRegistry:
    @staticmethod
    def selected_provider_name() -> str:
        return str(getattr(Config, "MARKET_DATA_PROVIDER", "mt5_bridge") or "mt5_bridge").strip().lower()

    @classmethod
    def build_provider(cls, provider_name: str | None = None):
        selected = (provider_name or cls.selected_provider_name()).strip().lower()
        if selected == "mt5_bridge":
            return MT5BridgeMarketDataProvider()
        if selected == "oanda_legacy":
            return OandaLegacyMarketDataProvider()
        return UnavailableMarketDataProvider(selected or "unknown", "MISCONFIGURED", f"unknown market data provider: {selected}")

    @classmethod
    def health(cls) -> ProviderHealth:
        return cls.build_provider().health_check()


def provider_status_summary() -> Dict[str, Any]:
    provider = ProviderRegistry.build_provider()
    health = provider.health_check()
    return {
        "active_provider": provider.provider_name,
        "status": health.status,
        "message": health.message,
        "checked_at": health.checked_at,
        "details_redacted": health.details_redacted,
    }

