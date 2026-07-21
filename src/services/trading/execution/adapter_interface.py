from __future__ import annotations

from typing import Protocol

from src.services.trading.execution.adapter_models import (
    ExecutionAdapterHealth,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
)
from src.services.trading.execution.adapter_validator import ExecutionAdapterValidationResult


class ExecutionAdapter(Protocol):
    def adapter_type(self) -> str:
        ...

    def health_check(self) -> ExecutionAdapterHealth:
        ...

    def validate_contract(self, contract: SimulatedOrderContract) -> ExecutionAdapterValidationResult:
        ...

    def submit_simulated(self, contract: SimulatedOrderContract) -> SimulatedExecutionReceipt:
        ...

    def close(self) -> None:
        ...
