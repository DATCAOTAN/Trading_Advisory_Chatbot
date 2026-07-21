from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from src.services.trading.execution.live_order_contract_final_review.models import (
    LiveOrderContractFinalReviewConfirmation,
)
from src.services.trading.execution.live_order_contract_final_review.policy import (
    LiveOrderContractFinalReviewConfig,
)


class LiveOrderContractFinalReviewConfirmationService:
    def __init__(self, config: LiveOrderContractFinalReviewConfig | None = None):
        self.config = config or LiveOrderContractFinalReviewConfig.from_config()

    def confirm(
        self,
        phrase: str | None,
        current_time: datetime | None = None,
        source_refs: list[str] | None = None,
    ) -> LiveOrderContractFinalReviewConfirmation:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at_dt = now + timedelta(seconds=self.config.ttl_seconds)
        normalized = "" if phrase is None else str(phrase).strip()
        blockers: list[str] = []
        phrase_valid = normalized == self.config.expected_phrase
        if self.config.require_exact_confirmation and not phrase_valid:
            blockers.append("WRONG_CONFIRMATION_PHRASE")
        if self.config.ttl_seconds < 0:
            blockers.append("CONFIRMATION_EXPIRED")
            phrase_valid = False
        action = "APPROVE_FOR_FUTURE_PRE_MT5_MAPPING_ONLY" if phrase_valid and not blockers else "REJECT"
        review_state = "HUMAN_REVIEW_APPROVED_FOR_FUTURE_MAPPING_ONLY" if phrase_valid and not blockers else "REJECTED"
        digest = hashlib.sha256(f"contract_final_review|{normalized}|{created_at}".encode("utf-8")).hexdigest()[:16]
        return LiveOrderContractFinalReviewConfirmation(
            confirmation_id=f"live_order_contract_final_review_confirmation_{digest}",
            created_at=created_at,
            phrase=normalized,
            expected_phrase=self.config.expected_phrase,
            phrase_valid=phrase_valid and not blockers,
            action=action,
            review_state=review_state,
            expires_at=expires_at_dt.isoformat(),
            blockers=blockers,
            warnings=[],
            source_refs=list(source_refs or []),
        )
