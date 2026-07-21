from __future__ import annotations

from dataclasses import dataclass

from src.config import Config


@dataclass
class TradeDecisionPolicy:
    review_ready_min_score: float = 0.70
    no_trade_below_score: float = 0.55
    block_on_invalid_data: bool = True
    block_on_immediate_high_impact: bool = True
    block_on_unknown_regime: bool = True
    block_on_scoring_blockers: bool = True
    wait_on_upcoming_high_impact: bool = True
    wait_on_choppy_low_score: bool = True
    manage_if_open_position: bool = True

    @classmethod
    def from_config(cls) -> "TradeDecisionPolicy":
        return cls(
            review_ready_min_score=float(getattr(Config, "TRADE_POLICY_REVIEW_READY_MIN_SCORE", 0.70)),
            no_trade_below_score=float(getattr(Config, "TRADE_POLICY_NO_TRADE_BELOW_SCORE", 0.55)),
            block_on_invalid_data=bool(getattr(Config, "TRADE_POLICY_BLOCK_ON_INVALID_DATA", True)),
            block_on_immediate_high_impact=bool(getattr(Config, "TRADE_POLICY_BLOCK_ON_IMMEDIATE_HIGH_IMPACT", True)),
            block_on_unknown_regime=bool(getattr(Config, "TRADE_POLICY_BLOCK_ON_UNKNOWN_REGIME", True)),
            block_on_scoring_blockers=bool(getattr(Config, "TRADE_POLICY_BLOCK_ON_SCORING_BLOCKERS", True)),
            wait_on_upcoming_high_impact=bool(getattr(Config, "TRADE_POLICY_WAIT_ON_UPCOMING_HIGH_IMPACT", True)),
            wait_on_choppy_low_score=bool(getattr(Config, "TRADE_POLICY_WAIT_ON_CHOPPY_LOW_SCORE", True)),
            manage_if_open_position=bool(getattr(Config, "TRADE_POLICY_MANAGE_IF_OPEN_POSITION", True)),
        )
