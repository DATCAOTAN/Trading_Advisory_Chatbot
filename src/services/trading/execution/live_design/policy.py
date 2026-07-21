from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class LiveExecutionDesignPolicy:
    enabled: bool = True
    require_hard_block: bool = True
    require_capability_report: bool = True
    require_blocked_receipt: bool = True
    min_critical_threats: int = 5
    min_preflight_checks: int = 10
    min_approval_requirements: int = 8
    min_failure_modes: int = 8
    min_audit_requirements: int = 8
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/live_execution_design_reports.jsonl"
    max_read_records: int = 100
    max_payload_chars: int = 120000

    @classmethod
    def from_config(cls) -> "LiveExecutionDesignPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_LIVE_DESIGN_SPEC_ENABLED", True)),
            require_hard_block=bool(getattr(Config, "TRADING_LIVE_DESIGN_REQUIRE_HARD_BLOCK", True)),
            require_capability_report=bool(getattr(Config, "TRADING_LIVE_DESIGN_REQUIRE_CAPABILITY_REPORT", True)),
            require_blocked_receipt=bool(getattr(Config, "TRADING_LIVE_DESIGN_REQUIRE_BLOCKED_RECEIPT", True)),
            min_critical_threats=int(getattr(Config, "TRADING_LIVE_DESIGN_MIN_CRITICAL_THREATS", 5)),
            min_preflight_checks=int(getattr(Config, "TRADING_LIVE_DESIGN_MIN_PREFLIGHT_CHECKS", 10)),
            min_approval_requirements=int(getattr(Config, "TRADING_LIVE_DESIGN_MIN_APPROVAL_REQUIREMENTS", 8)),
            min_failure_modes=int(getattr(Config, "TRADING_LIVE_DESIGN_MIN_FAILURE_MODES", 8)),
            min_audit_requirements=int(getattr(Config, "TRADING_LIVE_DESIGN_MIN_AUDIT_REQUIREMENTS", 8)),
            journal_enabled=bool(getattr(Config, "TRADING_LIVE_DESIGN_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_LIVE_DESIGN_JOURNAL_PATH",
                    "data/trading/execution_journal/live_execution_design_reports.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_LIVE_DESIGN_MAX_READ_RECORDS", 100)),
        )
