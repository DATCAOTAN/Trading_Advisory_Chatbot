from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_value_approval_lock.models import HumanValueApprovalConfirmation
from src.services.trading.execution.live_value_approval_lock.policy import HumanValueApprovalLockConfig


class HumanValueApprovalConfirmationService:
    def __init__(self, config: HumanValueApprovalLockConfig | None = None):
        self.config = config or HumanValueApprovalLockConfig.from_config()

    def confirm(
        self,
        phrase: str | None,
        source_refs: list[str] | None = None,
        current_time: datetime | None = None,
        existing_confirmation_ids: Iterable[str] | None = None,
    ) -> HumanValueApprovalConfirmation:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        normalized = str(phrase or "").strip()
        expected = self.config.expected_phrase
        expires_at_dt = now + timedelta(seconds=self.config.ttl_seconds)
        phrase_valid = bool(normalized) and normalized == expected
        confirmation_id = "human_value_approval_confirmation_" + _stable_hash(
            "|".join(["human_value_approval_lock_v1", normalized, created_at])
        )[:16]
        blockers: list[str] = []
        if self.config.require_exact_confirmation and not phrase_valid:
            blockers.append("WRONG_CONFIRMATION_PHRASE")
        if now > expires_at_dt:
            blockers.append("CONFIRMATION_EXPIRED")
        if confirmation_id in set(existing_confirmation_ids or []):
            blockers.append("DUPLICATE_APPROVAL_LOCK")
        action = "APPROVE_FOR_FUTURE_PARAMETERIZATION_ONLY" if phrase_valid and not blockers else "REJECT"
        review_state = "HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY" if action.startswith("APPROVE") else "REJECTED"
        return HumanValueApprovalConfirmation(
            confirmation_id=confirmation_id,
            created_at=created_at,
            phrase=normalized,
            expected_phrase=expected,
            phrase_valid=phrase_valid and not blockers,
            action=action,
            review_state=review_state,
            expires_at=expires_at_dt.isoformat(),
            blockers=blockers,
            warnings=[],
            source_refs=list(source_refs or []),
        )


def _stable_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
