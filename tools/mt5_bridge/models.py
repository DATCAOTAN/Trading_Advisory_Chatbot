from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BridgeResponse:
    status: str
    message: str = ""
    source: str = "mt5_terminal"
    fetched_at: str = field(default_factory=utc_now)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OhlcvResponse(BridgeResponse):
    symbol: str = ""
    timeframe: str = ""
    bars: List[Dict[str, Any]] = field(default_factory=list)
    latest_bid: float | None = None
    latest_ask: float | None = None
    spread: float | None = None
    data_quality: str = "EMPTY"

