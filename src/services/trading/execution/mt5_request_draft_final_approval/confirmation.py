from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    MT5RequestDraftFinalApprovalConfirmation,
)
from src.services.trading.execution.mt5_request_draft_final_approval.policy import (
    EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE,
    MT5RequestDraftFinalApprovalConfig,
)


class MT5RequestDraftFinalApprovalConfirmationService:
    def __init__(self, config: MT5RequestDraftFinalApprovalConfig | None = None):
        self.config = config or MT5RequestDraftFinalApprovalConfig.from_config()

    def confirm(
        self,
        phrase: str | None,
        action: str = "APPROVE_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY",
        source_refs: list[str] | None = None,
        current_time: datetime | None = None,
    ) -> MT5RequestDraftFinalApprovalConfirmation:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at_dt = now + timedelta(seconds=self.config.ttl_seconds)
        normalized_phrase = (phrase or "").strip()
        expected = self.config.expected_phrase or EXPECTED_MT5_REQUEST_DRAFT_FINAL_APPROVAL_PHRASE
        blockers: list[str] = []
        phrase_valid = normalized_phrase == expected
        review_state = "HUMAN_APPROVED_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY"

        if action == "REJECT":
            blockers.append("FINAL_APPROVAL_REJECTED")
            phrase_valid = False
            review_state = "REJECTED"
        elif action == "EXPIRE":
            blockers.append("CONFIRMATION_EXPIRED")
            phrase_valid = False
            review_state = "EXPIRED"
        elif action != "APPROVE_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY":
            blockers.append("INVALID_INPUT")
            phrase_valid = False
            review_state = "UNKNOWN"

        if self.config.require_exact_confirmation and not phrase_valid and "FINAL_APPROVAL_REJECTED" not in blockers:
            blockers.append("WRONG_CONFIRMATION_PHRASE")
            if review_state == "HUMAN_APPROVED_FOR_FUTURE_DRY_RUN_REQUEST_DICT_BUILDER_ONLY":
                review_state = "NOT_REVIEWED"

        return MT5RequestDraftFinalApprovalConfirmation(
            confirmation_id=f"mt5_request_draft_final_approval_confirmation_{_digest(created_at + normalized_phrase)[:16]}",
            created_at=created_at,
            phrase=normalized_phrase,
            expected_phrase=expected,
            phrase_valid=phrase_valid and not blockers,
            action=action,
            review_state=review_state,
            expires_at=expires_at_dt.isoformat(),
            blockers=list(dict.fromkeys(blockers)),
            warnings=[],
            source_refs=list(source_refs or []),
        )


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
