from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveOrderIntentPolicy:
    enabled: bool = True
    require_permission_gate: bool = True
    require_permission_granted: bool = True
    require_preflight_pass: bool = True
    require_proposal_draft: bool = True
    require_non_executable_proposal_draft: bool = True
    require_simulated_contract: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_order_intents.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 120000

    @classmethod
    def from_config(cls) -> "LiveOrderIntentPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_ENABLED", True)),
            require_permission_gate=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_PERMISSION_GATE", True)),
            require_permission_granted=bool(
                getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_PERMISSION_GRANTED", True)
            ),
            require_preflight_pass=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_PREFLIGHT_PASS", True)),
            require_proposal_draft=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_PROPOSAL_DRAFT", True)),
            require_non_executable_proposal_draft=bool(
                getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_NON_EXECUTABLE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_REQUIRE_IDEMPOTENCY", True)),
            ttl_seconds=int(getattr(Config, "TRADING_LIVE_ORDER_INTENT_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_INTENT_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_ORDER_INTENT_JOURNAL_PATH",
                    "data/trading/execution_journal/live_order_intents.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_ORDER_INTENT_MAX_READ_RECORDS", 100)),
        )
