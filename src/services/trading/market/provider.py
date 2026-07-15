from __future__ import annotations

from typing import Protocol

from src.services.trading.market.models import (
    AccountSnapshot,
    MarketSnapshot,
    PositionSnapshot,
    ProviderHealth,
    TickSnapshot,
)


class MarketDataProvider(Protocol):
    provider_name: str

    def health_check(self) -> ProviderHealth:
        ...

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> MarketSnapshot:
        ...

    def get_latest_tick(self, symbol: str) -> TickSnapshot:
        ...

    def get_positions(self, symbol: str | None = None) -> list[PositionSnapshot]:
        ...

    def get_account(self) -> AccountSnapshot:
        ...

    def normalize_symbol(self, symbol: str) -> str:
        ...

    def close(self) -> None:
        ...

