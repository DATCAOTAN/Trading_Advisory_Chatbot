from __future__ import annotations


class SignalScoringError(Exception):
    """Base exception for signal scoring failures."""


class SignalScoreValidationError(SignalScoringError):
    """Raised when a score report violates scoring safety constraints."""
