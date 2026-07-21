from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class MT5ExecutionSkeletonPolicy:
    skeleton_enabled: bool = True
    live_execution_enabled: bool = False
    hard_live_block_enabled: bool = True
    order_submission_enabled: bool = False
    execution_bridge_enabled: bool = False
    execution_adapter_implemented: bool = False
    require_simulated_contract: bool = True
    require_simulated_receipt: bool = True
    require_source_refs: bool = True
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_execution_blocks.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 12000

    @classmethod
    def from_config(cls) -> "MT5ExecutionSkeletonPolicy":
        return cls(
            skeleton_enabled=bool(getattr(Config, "TRADING_MT5_EXECUTION_SKELETON_ENABLED", True)),
            live_execution_enabled=bool(getattr(Config, "TRADING_MT5_LIVE_EXECUTION_ENABLED", False)),
            hard_live_block_enabled=bool(getattr(Config, "TRADING_MT5_HARD_LIVE_BLOCK_ENABLED", True)),
            order_submission_enabled=bool(getattr(Config, "TRADING_MT5_ORDER_SEND_ENABLED", False)),
            execution_bridge_enabled=bool(getattr(Config, "TRADING_MT5_EXECUTION_BRIDGE_ENABLED", False)),
            execution_adapter_implemented=bool(getattr(Config, "TRADING_MT5_EXECUTION_ADAPTER_IMPLEMENTED", False)),
            require_simulated_contract=bool(getattr(Config, "TRADING_MT5_SKELETON_REQUIRE_SIMULATED_CONTRACT", True)),
            require_simulated_receipt=bool(getattr(Config, "TRADING_MT5_SKELETON_REQUIRE_SIMULATED_RECEIPT", True)),
            require_source_refs=bool(getattr(Config, "TRADING_MT5_SKELETON_REQUIRE_SOURCE_REFS", True)),
            journal_enabled=bool(getattr(Config, "TRADING_MT5_SKELETON_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_MT5_SKELETON_JOURNAL_PATH",
                    "data/trading/execution_journal/live_execution_blocks.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_MT5_SKELETON_MAX_READ_RECORDS", 100)),
        )

    @property
    def live_path_blocked(self) -> bool:
        return (
            not self.live_execution_enabled
            or self.hard_live_block_enabled
            or not self.execution_adapter_implemented
            or not self.order_submission_enabled
            or not self.execution_bridge_enabled
        )
