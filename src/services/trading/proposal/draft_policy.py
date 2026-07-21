from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class ProposalDraftPolicy:
    enabled: bool = True
    require_confirmed_intent: bool = False
    allow_blocked_intent: bool = True
    allow_waiting_context: bool = True
    non_executable_only: bool = True
    max_context_chars: int = 12000
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/proposal_drafts.jsonl"
    max_read_records: int = 100

    @classmethod
    def from_config(cls) -> "ProposalDraftPolicy":
        return cls(
            enabled=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_ENABLED", True)),
            require_confirmed_intent=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_REQUIRE_CONFIRMED_INTENT", False)),
            allow_blocked_intent=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_ALLOW_BLOCKED_INTENT", True)),
            allow_waiting_context=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_ALLOW_WAITING_CONTEXT", True)),
            non_executable_only=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_NON_EXECUTABLE_ONLY", True)),
            max_context_chars=int(getattr(Config, "TRADING_PROPOSAL_DRAFT_MAX_CONTEXT_CHARS", 12000)),
            journal_enabled=bool(getattr(Config, "TRADING_PROPOSAL_DRAFT_JOURNAL_ENABLED", True)),
            journal_path=str(
                getattr(
                    Config,
                    "TRADING_PROPOSAL_DRAFT_JOURNAL_PATH",
                    "data/trading/execution_journal/proposal_drafts.jsonl",
                )
            ),
            max_read_records=int(getattr(Config, "TRADING_PROPOSAL_DRAFT_MAX_READ_RECORDS", 100)),
        )
