from __future__ import annotations


class TradeDecisionPolicyError(Exception):
    """Base exception for trade readiness policy failures."""


class TradeReadinessValidationError(TradeDecisionPolicyError):
    """Raised when a trade readiness decision violates policy constraints."""
