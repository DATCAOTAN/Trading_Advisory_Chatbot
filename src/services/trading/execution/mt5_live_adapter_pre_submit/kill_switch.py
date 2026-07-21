from __future__ import annotations

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import MT5KillSwitchCheck, now_utc_iso, hash_text
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


class MT5KillSwitchService:
    def __init__(self, config: MT5LiveAdapterPreSubmitConfig | None = None):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()

    def check(self) -> MT5KillSwitchCheck:
        engaged = bool(self.config.kill_switch_engaged)
        state = "ENGAGED" if engaged else "DISENGAGED_FOR_FUTURE_DEMO_ONLY"
        return MT5KillSwitchCheck(
            check_id="mt5_kill_switch_check_" + hash_text(state + now_utc_iso())[:16],
            created_at=now_utc_iso(),
            state=state,
            engaged=engaged,
            source="config",
            blockers=["KILL_SWITCH_ENGAGED"] if engaged else [],
        )
