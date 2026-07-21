from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LivePermissionPolicy:
    enabled: bool = True
    require_preflight_pass: bool = True
    require_design_report: bool = True
    require_capability_report: bool = True
    require_blocked_receipt: bool = True
    require_hard_block: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    ttl_seconds: int = 300
    confirmation_phrase: str = "I understand this only permits live order intent preparation and does not send a trade"
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_permission_intents.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 120000

    @classmethod
    def from_config(cls) -> "LivePermissionPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_PERMISSION_GATE_ENABLED", True)),
            require_preflight_pass=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_PREFLIGHT_PASS", True)),
            require_design_report=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_DESIGN_REPORT", True)),
            require_capability_report=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_CAPABILITY_REPORT", True)),
            require_blocked_receipt=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_BLOCKED_RECEIPT", True)),
            require_hard_block=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_HARD_BLOCK", True)),
            require_source_refs=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_LIVE_PERMISSION_REQUIRE_IDEMPOTENCY", True)),
            ttl_seconds=int(getattr(Config, "TRADING_LIVE_PERMISSION_TTL_SECONDS", 300)),
            confirmation_phrase=str(
                getattr(
                    Config,
                    "TRADING_LIVE_PERMISSION_CONFIRMATION_PHRASE",
                    "I understand this only permits live order intent preparation and does not send a trade",
                )
            ),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_PERMISSION_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_PERMISSION_JOURNAL_PATH",
                    "data/trading/execution_journal/live_permission_intents.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_PERMISSION_MAX_READ_RECORDS", 100)),
        )
