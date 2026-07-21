from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class ExecutionAdapterPolicy:
    adapter_type: str = "SIMULATED"
    simulated_adapter_enabled: bool = True
    live_adapter_enabled: bool = False
    mt5_live_adapter_enabled: bool = False
    contract_ttl_seconds: int = 300
    require_draft: bool = True
    require_non_executable_draft: bool = True
    require_source_refs: bool = True
    idempotency_enabled: bool = True
    simulated_journal_enabled: bool = True
    simulated_journal_path: str = "data/trading/execution_journal/simulated_execution_receipts.jsonl"
    max_payload_chars: int = 12000

    @classmethod
    def from_config(cls) -> "ExecutionAdapterPolicy":
        return cls(
            adapter_type=str(getattr(Config, "TRADING_EXECUTION_ADAPTER_TYPE", "SIMULATED")).strip().upper(),
            simulated_adapter_enabled=bool(getattr(Config, "TRADING_EXECUTION_SIMULATED_ADAPTER_ENABLED", True)),
            live_adapter_enabled=bool(getattr(Config, "TRADING_EXECUTION_LIVE_ADAPTER_ENABLED", False)),
            mt5_live_adapter_enabled=bool(getattr(Config, "TRADING_EXECUTION_MT5_LIVE_ADAPTER_ENABLED", False)),
            contract_ttl_seconds=int(getattr(Config, "TRADING_EXECUTION_ADAPTER_CONTRACT_TTL_SECONDS", 300)),
            require_draft=bool(getattr(Config, "TRADING_EXECUTION_ADAPTER_REQUIRE_DRAFT", True)),
            require_non_executable_draft=bool(
                getattr(Config, "TRADING_EXECUTION_ADAPTER_REQUIRE_NON_EXECUTABLE_DRAFT", True)
            ),
            require_source_refs=bool(getattr(Config, "TRADING_EXECUTION_ADAPTER_REQUIRE_SOURCE_REFS", True)),
            idempotency_enabled=bool(getattr(Config, "TRADING_EXECUTION_ADAPTER_IDEMPOTENCY_ENABLED", True)),
            simulated_journal_enabled=bool(getattr(Config, "TRADING_EXECUTION_SIMULATED_JOURNAL_ENABLED", True)),
            simulated_journal_path=str(
                getattr(
                    Config,
                    "TRADING_EXECUTION_SIMULATED_JOURNAL_PATH",
                    "data/trading/execution_journal/simulated_execution_receipts.jsonl",
                )
            ),
        )
