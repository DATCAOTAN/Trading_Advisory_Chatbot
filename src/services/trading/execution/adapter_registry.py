from __future__ import annotations

from src.services.trading.execution.adapter_models import ExecutionAdapterHealth
from src.services.trading.execution.adapter_policy import ExecutionAdapterPolicy
from src.services.trading.execution.mt5_skeleton_adapter import MT5ExecutionAdapterSkeleton
from src.services.trading.execution.mt5_skeleton_policy import MT5ExecutionSkeletonPolicy
from src.services.trading.execution.simulated_adapter import SimulatedExecutionAdapter


class DisabledExecutionAdapter:
    def __init__(self, adapter_type: str, message: str = "execution_adapter_disabled"):
        self._adapter_type = adapter_type or "UNKNOWN"
        self._message = message

    def adapter_type(self) -> str:
        return self._adapter_type

    def health_check(self) -> ExecutionAdapterHealth:
        return ExecutionAdapterHealth(
            adapter_type=self._adapter_type if self._adapter_type in {"SIMULATED", "RESERVED_MT5_LIVE", "DISABLED"} else "UNKNOWN",
            status="DISABLED",
            message=self._message,
            live_execution_supported=False,
            simulated_only=True,
        )

    def validate_contract(self, contract):
        from src.services.trading.execution.adapter_validator import ExecutionAdapterValidationResult

        return ExecutionAdapterValidationResult(False, ["adapter_disabled"])

    def submit_simulated(self, contract):
        from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, now_utc_iso

        return SimulatedExecutionReceipt(
            receipt_id="simulated_receipt_disabled",
            created_at=now_utc_iso(),
            adapter_type="SIMULATED",
            contract_id=getattr(contract, "contract_id", ""),
            contract_status=getattr(contract, "contract_status", "UNKNOWN"),
            accepted_by_adapter=False,
            source_draft_id=getattr(contract, "source_draft_id", ""),
            source_contract_id=getattr(contract, "contract_id", ""),
            idempotency_key=getattr(contract, "idempotency_key", ""),
            artifact_hash=getattr(contract, "artifact_hash", ""),
            blockers=["adapter_disabled"],
            source_refs=list(getattr(contract, "source_refs", []) or []),
            message=self._message,
        )

    def close(self) -> None:
        return None


class ExecutionAdapterRegistry:
    def __init__(self, policy: ExecutionAdapterPolicy | None = None):
        self.policy = policy or ExecutionAdapterPolicy.from_config()

    def get_adapter(self):
        adapter_type = (self.policy.adapter_type or "SIMULATED").strip().upper()
        if adapter_type == "SIMULATED":
            return SimulatedExecutionAdapter(policy=self.policy)
        if adapter_type in {"RESERVED_MT5_LIVE", "MT5_LIVE"}:
            skeleton_policy = MT5ExecutionSkeletonPolicy.from_config()
            if skeleton_policy.skeleton_enabled:
                return MT5ExecutionAdapterSkeleton(policy=skeleton_policy)
            return DisabledExecutionAdapter("RESERVED_MT5_LIVE", "mt5_execution_skeleton_disabled")
        if adapter_type == "DISABLED":
            return DisabledExecutionAdapter("DISABLED", "execution_adapter_disabled")
        return DisabledExecutionAdapter("UNKNOWN", "unknown_execution_adapter")

    def health_check(self) -> ExecutionAdapterHealth:
        return self.get_adapter().health_check()
