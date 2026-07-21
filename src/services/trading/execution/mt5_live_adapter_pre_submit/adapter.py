from __future__ import annotations

from time import perf_counter

from src.services.trading.execution.mt5_bridge_write_skeleton import MT5BridgeWriteSkeletonService
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5LiveAdapterDisabledReceipt,
    hash_text,
    now_utc_iso,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


class MT5LiveAdapterDisabled:
    def __init__(self, config: MT5LiveAdapterPreSubmitConfig | None = None, bridge_service: MT5BridgeWriteSkeletonService | None = None):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()
        self.bridge_service = bridge_service or MT5BridgeWriteSkeletonService()

    def health_check(self) -> dict:
        return {
            "adapter_status": "DISABLED_READY",
            "adapter_enabled": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
        }

    def check_bridge_write_skeleton(self):
        return self.bridge_service.run()

    def pre_submit_check(self) -> MT5LiveAdapterDisabledReceipt:
        bridge_result = self.check_bridge_write_skeleton()
        return self.submit_disabled(bridge_result.check)

    def submit_disabled(self, bridge_check=None) -> MT5LiveAdapterDisabledReceipt:
        started = perf_counter()
        created_at = now_utc_iso()
        reachable = bool(getattr(bridge_check, "reachable", False))
        status = str(getattr(bridge_check, "status", "UNKNOWN"))
        endpoint = str(getattr(bridge_check, "endpoint", "/execution/write-skeleton/check"))
        blockers = ["LIVE_ADAPTER_DISABLED"]
        if not reachable:
            blockers.append("BRIDGE_WRITE_SKELETON_UNREACHABLE")
        if status != "BLOCKED":
            blockers.append("BRIDGE_WRITE_SKELETON_NOT_BLOCKED")
        return MT5LiveAdapterDisabledReceipt(
            receipt_id="mt5_live_adapter_disabled_receipt_" + hash_text(created_at + status)[:16],
            created_at=created_at,
            adapter_status="BLOCKED_BY_DISABLED_ADAPTER",
            bridge_check_reachable=reachable,
            bridge_check_status=status,
            bridge_endpoint=endpoint,
            adapter_enabled=False,
            blockers=blockers,
            latency_ms=(perf_counter() - started) * 1000,
        )

    def close(self) -> None:
        return None
