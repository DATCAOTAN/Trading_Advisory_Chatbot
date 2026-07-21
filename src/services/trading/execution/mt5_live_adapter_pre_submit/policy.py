from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MT5LiveAdapterPreSubmitConfig:
    enabled: bool = True
    live_adapter_enabled: bool = False
    live_adapter_hard_block: bool = True
    pre_submit_gate_enabled: bool = True
    allow_live_submission: bool = False
    allow_order_send: bool = False
    require_final_validation: bool = True
    require_bridge_skeleton_check: bool = True
    require_idempotency: bool = True
    require_kill_switch: bool = True
    kill_switch_engaged: bool = True
    idempotency_ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/mt5_pre_submit_checks.jsonl"
    idempotency_path: str = "data/trading/execution_journal/mt5_pre_submit_idempotency.jsonl"
    max_read_records: int = 100

    @classmethod
    def from_config(cls, config=None) -> "MT5LiveAdapterPreSubmitConfig":
        if config is None:
            try:
                from src.config import Config

                config = Config
            except Exception:
                config = None
        if config is None:
            return cls()
        return cls(
            enabled=getattr(config, "TRADING_MT5_LIVE_ADAPTER_PRE_SUBMIT_ENABLED", True),
            live_adapter_enabled=getattr(config, "TRADING_MT5_LIVE_ADAPTER_ENABLED", False),
            live_adapter_hard_block=getattr(config, "TRADING_MT5_LIVE_ADAPTER_HARD_BLOCK", True),
            pre_submit_gate_enabled=getattr(config, "TRADING_MT5_PRE_SUBMIT_GATE_ENABLED", True),
            allow_live_submission=getattr(config, "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION", False),
            allow_order_send=getattr(config, "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND", False),
            require_final_validation=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_FINAL_VALIDATION", True),
            require_bridge_skeleton_check=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_BRIDGE_SKELETON_CHECK", True),
            require_idempotency=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_IDEMPOTENCY", True),
            require_kill_switch=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_KILL_SWITCH", True),
            kill_switch_engaged=getattr(config, "TRADING_MT5_KILL_SWITCH_ENGAGED", True),
            idempotency_ttl_seconds=getattr(config, "TRADING_MT5_IDEMPOTENCY_CHECK_TTL_SECONDS", 300),
            journal_enabled=getattr(config, "TRADING_MT5_PRE_SUBMIT_JOURNAL_ENABLED", True),
            journal_path=getattr(config, "TRADING_MT5_PRE_SUBMIT_JOURNAL_PATH", "data/trading/execution_journal/mt5_pre_submit_checks.jsonl"),
            max_read_records=getattr(config, "TRADING_MT5_PRE_SUBMIT_MAX_READ_RECORDS", 100),
        )
