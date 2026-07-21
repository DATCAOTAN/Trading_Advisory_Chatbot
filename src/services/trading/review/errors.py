from __future__ import annotations


class HumanReviewArtifactError(Exception):
    """Base exception for human review artifact failures."""


class HumanReviewArtifactValidationError(HumanReviewArtifactError):
    """Raised when a human review artifact violates safety constraints."""
