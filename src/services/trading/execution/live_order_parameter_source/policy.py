from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveOrderParameterSourceBoundaryConfig:
    enabled: bool = True
    require_policy_spec: bool = True
    require_policy_validation: bool = True
    require_source_boundary_allowed: bool = True
    require_contract_skeleton: bool = True
    require_live_order_intent: bool = True
    require_permission_decision: bool = True
    require_preflight_pass: bool = True
    require_proposal_draft: bool = True
    require_simulated_contract: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    reject_resolved_values: bool = True
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_order_parameter_sources.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 180000

    @classmethod
    def from_config(cls) -> "LiveOrderParameterSourceBoundaryConfig":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_ENABLED", True)),
            require_policy_spec=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_POLICY_SPEC", True)),
            require_policy_validation=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_POLICY_VALIDATION", True)
            ),
            require_source_boundary_allowed=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_SOURCE_BOUNDARY_ALLOWED", True)
            ),
            require_contract_skeleton=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_CONTRACT_SKELETON", True)
            ),
            require_live_order_intent=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_LIVE_ORDER_INTENT", True)
            ),
            require_permission_decision=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_PERMISSION_DECISION", True)
            ),
            require_preflight_pass=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_PREFLIGHT_PASS", True)
            ),
            require_proposal_draft=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REQUIRE_IDEMPOTENCY", True)),
            reject_resolved_values=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_REJECT_RESOLVED_VALUES", True)
            ),
            ttl_seconds=int(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_ORDER_PARAMETER_SOURCE_JOURNAL_PATH",
                    "data/trading/execution_journal/live_order_parameter_sources.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_SOURCE_MAX_READ_RECORDS", 100)),
        )
