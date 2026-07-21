from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveOrderParameterPolicyConfig:
    enabled: bool = True
    require_contract_skeleton: bool = True
    require_valid_contract_skeleton: bool = True
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
    journal_path: str = "data/trading/execution_journal/live_order_parameter_policies.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 160000

    @classmethod
    def from_config(cls) -> "LiveOrderParameterPolicyConfig":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_ENABLED", True)),
            require_contract_skeleton=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_CONTRACT_SKELETON", True)
            ),
            require_valid_contract_skeleton=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_VALID_CONTRACT_SKELETON", True)
            ),
            require_live_order_intent=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_LIVE_ORDER_INTENT", True)
            ),
            require_permission_decision=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_PERMISSION_DECISION", True)
            ),
            require_preflight_pass=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_PREFLIGHT_PASS", True)
            ),
            require_proposal_draft=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_SOURCE_REFS", True)
            ),
            require_idempotency=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REQUIRE_IDEMPOTENCY", True)
            ),
            reject_resolved_values=bool(
                getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_REJECT_RESOLVED_VALUES", True)
            ),
            ttl_seconds=int(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_ORDER_PARAMETER_POLICY_JOURNAL_PATH",
                    "data/trading/execution_journal/live_order_parameter_policies.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_ORDER_PARAMETER_POLICY_MAX_READ_RECORDS", 100)),
        )
