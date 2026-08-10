from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


DATA_QUALITY_VALUES = {"COMPLETE", "PARTIAL", "EMPTY", "STALE", "INVALID"}
PROVIDER_HEALTH_VALUES = {"OK", "DEGRADED", "UNAVAILABLE", "MISCONFIGURED"}


@dataclass
class MarketSymbol:
    symbol: str
    broker_symbol: str = ""
    asset_class: str = ""
    enabled: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class OHLCVBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    timeframe: str = ""
    symbol: str = ""
    source: str = "mt5_terminal"

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    bars: List[OHLCVBar] = field(default_factory=list)
    latest_bid: float | None = None
    latest_ask: float | None = None
    spread: float | None = None
    source: str = "mt5_terminal"
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_name: str = "mt5_bridge"
    data_quality: str = "EMPTY"

    def as_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        data["bars"] = [bar.as_dict() for bar in self.bars]
        return data


@dataclass
class TickSnapshot:
    symbol: str
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    timestamp: str = ""
    provider_name: str = "mt5_bridge"
    digits: int | None = None
    point: float | None = None
    tick_size: float | None = None
    minimum_distance_points: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_step: float | None = None
    tick_value: float | None = None
    contract_size: float | None = None

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class PositionSnapshot:
    position_id_hash: str
    symbol: str = ""
    side: str = ""
    volume: float | None = None
    open_time: str = ""
    open_price: float | None = None
    current_price: float | None = None
    pnl: float | None = None
    source: str = "mt5_terminal"
    redacted: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class AccountSnapshot:
    account_id_hash: str = ""
    server_redacted: str = ""
    currency: str = ""
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    free_margin: float | None = None
    leverage: int | None = None
    account_environment: str = "UNKNOWN"
    provider_name: str = "mt5_bridge"
    redacted: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ProviderHealth:
    provider_name: str
    status: str = "UNAVAILABLE"
    message: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)
