from __future__ import annotations

from dataclasses import dataclass

from src.config import Config
from src.services.trading.execution.live_order_contract_final_review.models import (
    EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE,
)


@dataclass
class LiveOrderContractFinalReviewConfig:
    enabled: bool = True
    require_parameterization: bool = True
    require_parameterization_validation: bool = True
    require_contract_validation_workflow_allowed: bool = True
    require_approval_lock: bool = True
    require_value_proposal: bool = True
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
    reject_raw_values: bool = True
    reject_broker_mapping: bool = True
    expected_phrase: str = EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_order_contract_final_reviews.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 180000

    @classmethod
    def from_config(cls) -> "LiveOrderContractFinalReviewConfig":
        return cls(
            enabled=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_ENABLED", True)),
            require_parameterization=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PARAMETERIZATION", True)),
            require_parameterization_validation=bool(
                getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PARAMETERIZATION_VALIDATION", True)
            ),
            require_contract_validation_workflow_allowed=bool(
                getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_CONTRACT_VALIDATION_WORKFLOW_ALLOWED", True)
            ),
            require_approval_lock=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_APPROVAL_LOCK", True)),
            require_value_proposal=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_VALUE_PROPOSAL", True)),
            require_parameter_draft=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PARAMETER_DRAFT", True)),
            require_source_boundary=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_SOURCE_BOUNDARY", True)),
            require_policy_spec=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_POLICY_SPEC", True)),
            require_contract_skeleton=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_CONTRACT_SKELETON", True)),
            require_live_order_intent=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_LIVE_ORDER_INTENT", True)),
            require_permission_decision=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PERMISSION_DECISION", True)),
            require_preflight_pass=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PREFLIGHT_PASS", True)),
            require_proposal_draft=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_PROPOSAL_DRAFT", True)),
            require_simulated_contract=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_SIMULATED_CONTRACT", True)),
            require_source_refs=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_IDEMPOTENCY", True)),
            require_exact_confirmation=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REQUIRE_EXACT_CONFIRMATION", True)),
            reject_raw_values=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REJECT_RAW_VALUES", True)),
            reject_broker_mapping=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_REJECT_BROKER_MAPPING", True)),
            expected_phrase=str(
                getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_EXPECTED_PHRASE", EXPECTED_CONTRACT_FINAL_REVIEW_PHRASE)
            ),
            ttl_seconds=int(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_CONTRACT_FINAL_REVIEW_JOURNAL_PATH",
                    "data/trading/execution_journal/live_order_contract_final_reviews.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_MAX_READ_RECORDS", 100)),
        )
