from __future__ import annotations


class ExecutionGateError(Exception):
    """Base exception for non-executing gate failures."""


class DryRunReceiptValidationError(ExecutionGateError):
    """Raised when a dry-run receipt violates safety constraints."""
