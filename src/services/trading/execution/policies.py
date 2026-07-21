from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class ExecutionGatePolicy:
    mode: str = "REVIEW_ONLY"
    dry_run_enabled: bool = True
    live_enabled: bool = False
    autonomous_enabled: bool = False
    kill_switch: bool = True
    artifact_ttl_seconds: int = 300
    max_dry_runs_per_session: int = 20
    require_review_ready: bool = True
    block_on_warnings: bool = False
    block_on_blockers: bool = True
    require_source_refs: bool = True
    idempotency_enabled: bool = True
    max_payload_chars: int = 12000

    @classmethod
    def from_config(cls) -> "ExecutionGatePolicy":
        return cls(
            mode=str(getattr(Config, "TRADING_EXECUTION_MODE", "REVIEW_ONLY")).strip().upper(),
            dry_run_enabled=bool(getattr(Config, "TRADING_EXECUTION_DRY_RUN_ENABLED", True)),
            live_enabled=bool(getattr(Config, "TRADING_EXECUTION_LIVE_ENABLED", False)),
            autonomous_enabled=bool(getattr(Config, "TRADING_EXECUTION_AUTONOMOUS_ENABLED", False)),
            kill_switch=bool(getattr(Config, "TRADING_EXECUTION_KILL_SWITCH", True)),
            artifact_ttl_seconds=int(getattr(Config, "TRADING_EXECUTION_ARTIFACT_TTL_SECONDS", 300)),
            max_dry_runs_per_session=int(getattr(Config, "TRADING_EXECUTION_MAX_DRY_RUNS_PER_SESSION", 20)),
            require_review_ready=bool(getattr(Config, "TRADING_EXECUTION_REQUIRE_REVIEW_READY", True)),
            block_on_warnings=bool(getattr(Config, "TRADING_EXECUTION_BLOCK_ON_WARNINGS", False)),
            block_on_blockers=bool(getattr(Config, "TRADING_EXECUTION_BLOCK_ON_BLOCKERS", True)),
            require_source_refs=bool(getattr(Config, "TRADING_EXECUTION_REQUIRE_SOURCE_REFS", True)),
            idempotency_enabled=bool(getattr(Config, "TRADING_EXECUTION_IDEMPOTENCY_ENABLED", True)),
        )
