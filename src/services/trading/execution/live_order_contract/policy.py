from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveOrderContractSkeletonPolicy:
    enabled: bool = True
    require_live_order_intent: bool = True
    require_valid_intent: bool = True
    require_permission_decision: bool = True
    require_preflight_pass: bool = True
    require_proposal_draft: bool = True
    require_non_executable_proposal_draft: bool = True
    require_simulated_contract: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_order_contract_skeletons.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 140000

    @classmethod
    def from_config(cls) -> "LiveOrderContractSkeletonPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_SKELETON_ENABLED", True)),
            require_live_order_intent=bool(
                getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_LIVE_ORDER_INTENT", True)
            ),
            require_valid_intent=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_VALID_INTENT", True)),
            require_permission_decision=bool(
                getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_PERMISSION_DECISION", True)
            ),
            require_preflight_pass=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_PREFLIGHT_PASS", True)),
            require_proposal_draft=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_PROPOSAL_DRAFT", True)),
            require_non_executable_proposal_draft=bool(
                getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_NON_EXECUTABLE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_REQUIRE_IDEMPOTENCY", True)),
            ttl_seconds=int(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_ORDER_CONTRACT_JOURNAL_PATH",
                    "data/trading/execution_journal/live_order_contract_skeletons.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_ORDER_CONTRACT_MAX_READ_RECORDS", 100)),
        )
