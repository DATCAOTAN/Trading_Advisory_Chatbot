from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MT5RequestDictFinalValidationConfig:
    enabled: bool = True
    require_dry_run_builder_boundary: bool = True
    require_dry_run_builder_validation_report: bool = True
    require_workflow_allowed: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    reject_raw_values: bool = True
    reject_real_mt5_payload: bool = True
    reject_broker_submittable_request_dict: bool = True
    reject_mt5_constants: bool = True
    reject_broker_submission: bool = True
    reject_executable_order: bool = True
    reject_order_send: bool = True
    ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/mt5_request_dict_final_validations.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 120000

    @classmethod
    def from_config(cls, config=None) -> "MT5RequestDictFinalValidationConfig":
        if config is None:
            try:
                from src.config import Config

                config = Config
            except Exception:
                config = None
        if config is None:
            return cls()
        return cls(
            enabled=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_ENABLED", True),
            require_dry_run_builder_boundary=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REQUIRE_DRY_RUN_BUILDER_BOUNDARY", True),
            require_dry_run_builder_validation_report=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REQUIRE_DRY_RUN_BUILDER_VALIDATION_REPORT", True),
            require_workflow_allowed=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REQUIRE_WORKFLOW_ALLOWED", True),
            require_source_refs=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REQUIRE_SOURCE_REFS", True),
            require_idempotency=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REQUIRE_IDEMPOTENCY", True),
            reject_raw_values=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_RAW_VALUES", True),
            reject_real_mt5_payload=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_REAL_MT5_PAYLOAD", True),
            reject_broker_submittable_request_dict=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_BROKER_SUBMITTABLE_REQUEST_DICT", True),
            reject_mt5_constants=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_MT5_CONSTANTS", True),
            reject_broker_submission=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_BROKER_SUBMISSION", True),
            reject_executable_order=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_EXECUTABLE_ORDER", True),
            reject_order_send=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_REJECT_ORDER_SEND", True),
            ttl_seconds=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_TTL_SECONDS", 300),
            journal_enabled=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_JOURNAL_ENABLED", True),
            journal_path=getattr(
                config,
                "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_JOURNAL_PATH",
                "data/trading/execution_journal/mt5_request_dict_final_validations.jsonl",
            ),
            max_read_records=getattr(config, "TRADING_MT5_REQUEST_DICT_FINAL_VALIDATION_MAX_READ_RECORDS", 100),
        )
