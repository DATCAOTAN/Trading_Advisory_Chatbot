from __future__ import annotations

from dataclasses import dataclass

from src.services.trading.execution.models import now_utc_iso


@dataclass
class KillSwitchState:
    enabled: bool = True
    reason: str = "live_execution_disabled_by_default"
    updated_at: str = ""
    source: str = "config"

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = now_utc_iso()

    def as_dict(self) -> dict:
        return {
            "enabled": bool(self.enabled),
            "reason": self.reason,
            "updated_at": self.updated_at,
            "source": self.source,
        }
