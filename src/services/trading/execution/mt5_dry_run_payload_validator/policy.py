from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class MT5DryRunPayloadValidationConfig:
    enabled: bool = True
    require_pre_mt5_mapping: bool = True
    require_pre_mt5_mapping_validation: bool = True
    require_workflow_allowed: bool = True
    require_final_review: bool = True
    require_parameterization: bool = True
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
    reject_raw_values: bool = True
    reject_mt5_payload: bool = True
    reject_mt5_request_dict: bool = True
    reject_mt5_constants: bool = True
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/mt5_dry_run_payload_validations.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 180000

    @classmethod
    def from_config(cls) -> "MT5DryRunPayloadValidationConfig":
        return cls(
            enabled=bool(getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_ENABLED", True)),
            require_pre_mt5_mapping=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PRE_MT5_MAPPING", True)
            ),
            require_pre_mt5_mapping_validation=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PRE_MT5_MAPPING_VALIDATION", True)
            ),
            require_workflow_allowed=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_WORKFLOW_ALLOWED", True)
            ),
            require_final_review=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_FINAL_REVIEW", True)
            ),
            require_parameterization=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PARAMETERIZATION", True)
            ),
            require_approval_lock=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_APPROVAL_LOCK", True)
            ),
            require_value_proposal=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_VALUE_PROPOSAL", True)
            ),
            require_parameter_draft=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PARAMETER_DRAFT", True)
            ),
            require_source_boundary=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_SOURCE_BOUNDARY", True)
            ),
            require_policy_spec=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_POLICY_SPEC", True)
            ),
            require_contract_skeleton=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_CONTRACT_SKELETON", True)
            ),
            require_live_order_intent=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_LIVE_ORDER_INTENT", True)
            ),
            require_permission_decision=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PERMISSION_DECISION", True)
            ),
            require_preflight_pass=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PREFLIGHT_PASS", True)
            ),
            require_proposal_draft=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_PROPOSAL_DRAFT", True)
            ),
            require_simulated_contract=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_SIMULATED_CONTRACT", True)
            ),
            require_source_refs=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_SOURCE_REFS", True)
            ),
            require_idempotency=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REQUIRE_IDEMPOTENCY", True)
            ),
            reject_raw_values=bool(getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REJECT_RAW_VALUES", True)),
            reject_mt5_payload=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REJECT_MT5_PAYLOAD", True)
            ),
            reject_mt5_request_dict=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REJECT_MT5_REQUEST_DICT", True)
            ),
            reject_mt5_constants=bool(
                getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_REJECT_MT5_CONSTANTS", True)
            ),
            ttl_seconds=int(getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_TTL_SECONDS", 300)),
            journal_enabled=bool(getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_JOURNAL_PATH",
                    "data/trading/execution_journal/mt5_dry_run_payload_validations.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_MT5_DRY_RUN_PAYLOAD_VALIDATOR_MAX_READ_RECORDS", 100)),
        )
