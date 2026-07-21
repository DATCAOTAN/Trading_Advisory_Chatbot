from __future__ import annotations

from dataclasses import dataclass

from src.services.trading.execution.adapter_models import (
    ExecutionAdapterHealth,
    SimulatedExecutionJournalRecord,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
)


@dataclass
class SimulatedExecutionServiceResult:
    contract: SimulatedOrderContract
    adapter_health: ExecutionAdapterHealth
    receipt: SimulatedExecutionReceipt
    journal_record: SimulatedExecutionJournalRecord | None = None
    warning: str = ""
