from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveExecutionPreflightPolicy:
    enabled: bool = True
    require_design_report: bool = True
    require_capability_report: bool = True
    require_blocked_receipt: bool = True
    require_hard_block: bool = True
    require_order_submission_absent: bool = True
    require_controlled_order_send_boundary: bool = True
    require_no_bridge_order_endpoints: bool = True
    require_no_docker_mt5_import: bool = True
    require_journal_writable: bool = True
    require_source_refs: bool = True
    require_idempotency: bool = True
    require_redaction: bool = True
    require_ui_safe_wording: bool = True
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_execution_preflight_reports.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 140000

    @classmethod
    def from_config(cls) -> "LiveExecutionPreflightPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_ENABLED", True)),
            require_design_report=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_DESIGN_REPORT", True)),
            require_capability_report=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_CAPABILITY_REPORT", True)),
            require_blocked_receipt=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_BLOCKED_RECEIPT", True)),
            require_hard_block=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_HARD_BLOCK", True)),
            require_order_submission_absent=bool(
                getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_ORDER_SEND_ABSENT", True)
            ),
            require_no_bridge_order_endpoints=bool(
                getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_NO_BRIDGE_ORDER_ENDPOINTS", True)
            ),
            require_no_docker_mt5_import=bool(
                getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_NO_DOCKER_MT5_IMPORT", True)
            ),
            require_journal_writable=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_JOURNAL_WRITABLE", True)),
            require_source_refs=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_SOURCE_REFS", True)),
            require_idempotency=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_IDEMPOTENCY", True)),
            require_redaction=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_REDACTION", True)),
            require_ui_safe_wording=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_REQUIRE_UI_SAFE_WORDING", True)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_PREFLIGHT_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_PREFLIGHT_JOURNAL_PATH",
                    "data/trading/execution_journal/live_execution_preflight_reports.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_PREFLIGHT_MAX_READ_RECORDS", 100)),
        )
