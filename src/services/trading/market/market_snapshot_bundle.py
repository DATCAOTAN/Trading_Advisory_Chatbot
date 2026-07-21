from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from src.config import Config
from src.services.trading.market.models import AccountSnapshot, MarketSnapshot, ProviderHealth, TickSnapshot
from src.services.trading.market.provider_registry import ProviderRegistry
from src.services.trading.market.timeframes import broker_symbol_for, default_symbol, normalize_timeframes


@dataclass
class MarketSnapshotBundle:
    bundle_id: str
    created_at: str
    symbol: str
    broker_symbol: str
    provider_name: str
    timeframes: Dict[str, MarketSnapshot] = field(default_factory=dict)
    tick: TickSnapshot | None = None
    account_id_hash: str = ""
    source: str = "mt5_bridge"
    data_quality_summary: str = "EMPTY"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    provider_health: ProviderHealth | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "provider_name": self.provider_name,
            "timeframes": {key: value.as_dict() for key, value in self.timeframes.items()},
            "tick": self.tick.as_dict() if self.tick else None,
            "account_id_hash": self.account_id_hash,
            "source": self.source,
            "data_quality_summary": self.data_quality_summary,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "provider_health": self.provider_health.as_dict() if self.provider_health else None,
        }


class MarketSnapshotBundleBuilder:
    def __init__(self, provider: Any | None = None):
        self.provider = provider or ProviderRegistry.build_provider()

    def build(
        self,
        symbol: str | None = None,
        timeframes: Iterable[str] | None = None,
        candle_count: int | None = None,
    ) -> MarketSnapshotBundle:
        logical_symbol = str(symbol or default_symbol()).upper()
        broker_symbol = broker_symbol_for(logical_symbol)
        normalized_timeframes = normalize_timeframes(timeframes)
        count = int(candle_count or getattr(Config, "MARKET_DEFAULT_CANDLE_COUNT", 300))
        created_at = datetime.now(timezone.utc).isoformat()
        provider_name = getattr(self.provider, "provider_name", "unknown")
        warnings: list[str] = []
        errors: list[str] = []

        try:
            provider_health = self.provider.health_check()
        except Exception as exc:
            provider_health = ProviderHealth(provider_name=provider_name, status="UNAVAILABLE", message=type(exc).__name__)
            warnings.append(f"provider_health_unavailable:{type(exc).__name__}")

        snapshots: Dict[str, MarketSnapshot] = {}
        for timeframe in normalized_timeframes:
            try:
                snapshots[timeframe] = self.provider.get_ohlcv(logical_symbol, timeframe, count)
                if not snapshots[timeframe].bars:
                    warnings.append(f"{timeframe}:empty_bars")
            except Exception as exc:
                errors.append(f"{timeframe}:fetch_failed:{type(exc).__name__}")
                snapshots[timeframe] = MarketSnapshot(
                    symbol=logical_symbol,
                    timeframe=timeframe,
                    bars=[],
                    source=provider_name,
                    provider_name=provider_name,
                    data_quality="EMPTY",
                )

        try:
            tick = self.provider.get_latest_tick(logical_symbol)
        except Exception as exc:
            tick = None
            warnings.append(f"tick_unavailable:{type(exc).__name__}")

        try:
            account: AccountSnapshot = self.provider.get_account()
            account_id_hash = account.account_id_hash or ""
        except Exception:
            account_id_hash = ""

        data_quality_summary = _summarize_snapshot_quality(snapshots)
        return MarketSnapshotBundle(
            bundle_id=_bundle_id(logical_symbol, created_at, snapshots),
            created_at=created_at,
            symbol=logical_symbol,
            broker_symbol=broker_symbol,
            provider_name=provider_name,
            timeframes=snapshots,
            tick=tick,
            account_id_hash=account_id_hash,
            source=provider_name,
            data_quality_summary=data_quality_summary,
            warnings=warnings,
            errors=errors,
            provider_health=provider_health,
        )


def _summarize_snapshot_quality(snapshots: Dict[str, MarketSnapshot]) -> str:
    if not snapshots:
        return "EMPTY"
    qualities = {str(snapshot.data_quality or "EMPTY").upper() for snapshot in snapshots.values()}
    if qualities == {"COMPLETE"}:
        return "COMPLETE"
    if "INVALID" in qualities:
        return "INVALID"
    if "STALE" in qualities:
        return "STALE"
    if any(snapshot.bars for snapshot in snapshots.values()):
        return "PARTIAL"
    return "EMPTY"


def _bundle_id(symbol: str, created_at: str, snapshots: Dict[str, MarketSnapshot]) -> str:
    parts = [symbol, created_at]
    for timeframe, snapshot in sorted(snapshots.items()):
        latest = snapshot.bars[-1].timestamp if snapshot.bars else ""
        parts.append(f"{timeframe}:{len(snapshot.bars)}:{latest}")
    return "market_bundle_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
