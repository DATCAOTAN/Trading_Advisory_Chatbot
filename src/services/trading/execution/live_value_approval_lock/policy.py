from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE = (
    "I understand this locks human value approval for future contract parameterization only and does not send a trade"
)


@dataclass
class HumanValueApprovalLockConfig:
    enabled: bool = True
    require_value_proposal: bool = True
    require_value_proposal_validation: bool = True
    require_human_value_approval_allowed: bool = True
    require_parameter_draft: bool = True
    require_source_boundary: bool = True
    require_policy_spec: bool = True
    require_contract_skeleton: bool = True
    require_live_order_intent: bool = True
    require_permission_decision: bool = True
    require_preflight_pass: bool = True
    require_proposal_draft: bool = True
    require_simulated_contract: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    require_exact_confirmation: bool = True
    require_value_lock: bool = True
    expected_phrase: str = EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/human_value_approval_locks.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 180000

    @classmethod
    def from_config(cls) -> "HumanValueApprovalLockConfig":
        return cls(
            enabled=bool(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_ENABLED", True)),
            require_value_proposal=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_VALUE_PROPOSAL", True)
            ),
            require_value_proposal_validation=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_VALUE_PROPOSAL_VALIDATION", True)
            ),
            require_human_value_approval_allowed=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_HUMAN_VALUE_APPROVAL_ALLOWED", True)
            ),
            require_parameter_draft=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_PARAMETER_DRAFT", True)
            ),
            require_source_boundary=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_SOURCE_BOUNDARY", True)
            ),
            require_policy_spec=bool(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_POLICY_SPEC", True)),
            require_contract_skeleton=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_CONTRACT_SKELETON", True)
            ),
            require_live_order_intent=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_LIVE_ORDER_INTENT", True)
            ),
            require_permission_decision=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_PERMISSION_DECISION", True)
            ),
            require_preflight_pass=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_PREFLIGHT_PASS", True)
            ),
            require_proposal_draft=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_IDEMPOTENCY", True)
            ),
            require_exact_confirmation=bool(
                getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_EXACT_CONFIRMATION", True)
            ),
            require_value_lock=bool(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_REQUIRE_VALUE_LOCK", True)),
            expected_phrase=str(
                getattr(
                    Config,
                    "TRADING_HUMAN_VALUE_APPROVAL_LOCK_EXPECTED_PHRASE",
                    EXPECTED_HUMAN_VALUE_APPROVAL_LOCK_PHRASE,
                )
            ),
            ttl_seconds=int(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_HUMAN_VALUE_APPROVAL_LOCK_JOURNAL_PATH",
                    "data/trading/execution_journal/human_value_approval_locks.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_HUMAN_VALUE_APPROVAL_LOCK_MAX_READ_RECORDS", 100)),
        )
