from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class ProposalBoundaryPolicy:
    enabled: bool = True
    require_dry_run_receipt: bool = True
    require_journal_record: bool = True
    require_ready_for_review: bool = True
    require_dry_run_allowed: bool = True
    allow_waiting_artifact: bool = False
    allow_blocked_artifact: bool = False
    intent_ttl_seconds: int = 300
    confirmation_phrase: str = "I understand this is dry-run only and does not execute a trade"
    idempotency_enabled: bool = True
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/proposal_intents.jsonl"
    max_payload_chars: int = 12000

    @classmethod
    def from_config(cls) -> "ProposalBoundaryPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_PROPOSAL_BOUNDARY_ENABLED", True)),
            require_dry_run_receipt=bool(getattr(Config, "TRADING_PROPOSAL_REQUIRE_DRY_RUN_RECEIPT", True)),
            require_journal_record=bool(getattr(Config, "TRADING_PROPOSAL_REQUIRE_JOURNAL_RECORD", True)),
            require_ready_for_review=bool(getattr(Config, "TRADING_PROPOSAL_REQUIRE_READY_FOR_REVIEW", True)),
            require_dry_run_allowed=bool(getattr(Config, "TRADING_PROPOSAL_REQUIRE_DRY_RUN_ALLOWED", True)),
            allow_waiting_artifact=bool(getattr(Config, "TRADING_PROPOSAL_ALLOW_WAITING_ARTIFACT", False)),
            allow_blocked_artifact=bool(getattr(Config, "TRADING_PROPOSAL_ALLOW_BLOCKED_ARTIFACT", False)),
            intent_ttl_seconds=int(getattr(Config, "TRADING_PROPOSAL_INTENT_TTL_SECONDS", 300)),
            confirmation_phrase=str(
                getattr(
                    Config,
                    "TRADING_PROPOSAL_CONFIRMATION_PHRASE",
                    "I understand this is dry-run only and does not execute a trade",
                )
            ),
            idempotency_enabled=bool(getattr(Config, "TRADING_PROPOSAL_IDEMPOTENCY_ENABLED", True)),
            journal_enabled=bool(getattr(Config, "TRADING_PROPOSAL_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_PROPOSAL_JOURNAL_PATH",
                    "data/trading/execution_journal/proposal_intents.jsonl",
                )
            ),
        )
