from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.permission.models import LivePermissionIntent, now_utc_iso
from src.services.trading.execution.permission.policy import LivePermissionPolicy


@dataclass
class LivePermissionConfirmationResult:
    confirmation_state: str
    confirmation_phrase_required: str
    confirmation_phrase_received: str
    user_acknowledgement_text: str
    block_reason: str = ""


class LivePermissionConfirmationService:
    def __init__(self, policy: LivePermissionPolicy | None = None):
        self.policy = policy or LivePermissionPolicy.from_config()

    def required_phrase(self) -> str:
        return self.policy.confirmation_phrase

    def evaluate(self, user_acknowledgement_text: str | None) -> LivePermissionConfirmationResult:
        received = _normalize(user_acknowledgement_text or "")
        required = _normalize(self.policy.confirmation_phrase)
        if not received:
            return LivePermissionConfirmationResult(
                confirmation_state="NOT_CONFIRMED",
                confirmation_phrase_required=self.policy.confirmation_phrase,
                confirmation_phrase_received="MISSING",
                user_acknowledgement_text="",
                block_reason="MISSING_CONFIRMATION_PHRASE",
            )
        if received != required:
            return LivePermissionConfirmationResult(
                confirmation_state="REJECTED",
                confirmation_phrase_required=self.policy.confirmation_phrase,
                confirmation_phrase_received="MISMATCH_REDACTED",
                user_acknowledgement_text="redacted_confirmation_mismatch",
                block_reason="WRONG_CONFIRMATION_PHRASE",
            )
        return LivePermissionConfirmationResult(
            confirmation_state="CONFIRMED_PERMISSION_GATE_ONLY",
            confirmation_phrase_required=self.policy.confirmation_phrase,
            confirmation_phrase_received=self.policy.confirmation_phrase,
            user_acknowledgement_text=self.policy.confirmation_phrase,
        )


class LivePermissionIntentBuilder:
    def __init__(
        self,
        policy: LivePermissionPolicy | None = None,
        confirmation_service: LivePermissionConfirmationService | None = None,
    ):
        self.policy = policy or LivePermissionPolicy.from_config()
        self.confirmation_service = confirmation_service or LivePermissionConfirmationService(self.policy)

    def build(
        self,
        preflight_report,
        design_report,
        capability_report,
        blocked_receipt,
        simulated_contract=None,
        proposal_draft=None,
        user_acknowledgement_text: str | None = None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LivePermissionIntent:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at_dt = _parse_datetime(getattr(preflight_report, "created_at", "")) + timedelta(seconds=self.policy.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(preflight_report, "source_refs", []) or [])
            + list(getattr(design_report, "source_refs", []) or [])
            + list(getattr(blocked_receipt, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
            + list(getattr(proposal_draft, "source_refs", []) or [])
        )
        artifact_hash = (
            getattr(blocked_receipt, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
        )
        idempotency_key = (
            getattr(blocked_receipt, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
        )
        confirmation = self.confirmation_service.evaluate(user_acknowledgement_text)
        blockers: list[str] = []
        reasons: list[str] = []
        if preflight_report is None:
            blockers.append("MISSING_PREFLIGHT_REPORT")
        elif self.policy.require_preflight_pass and getattr(preflight_report, "preflight_status", "") != "PASS":
            blockers.append("PREFLIGHT_NOT_PASS")
        if design_report is None and self.policy.require_design_report:
            blockers.append("MISSING_DESIGN_REPORT")
        if capability_report is None and self.policy.require_capability_report:
            blockers.append("INVALID_INPUT")
        if blocked_receipt is None and self.policy.require_blocked_receipt:
            blockers.append("MISSING_HARD_BLOCK_RECEIPT")
        if self.policy.require_hard_block:
            if getattr(preflight_report, "hard_live_block_required", False) is not True:
                blockers.append("LIVE_EXECUTION_STILL_DISABLED")
            if getattr(design_report, "hard_live_block_required", False) is not True:
                blockers.append("LIVE_EXECUTION_STILL_DISABLED")
            if getattr(capability_report, "hard_live_block_enabled", False) is not True:
                blockers.append("LIVE_EXECUTION_STILL_DISABLED")
            if getattr(blocked_receipt, "blocked", False) is not True:
                blockers.append("MISSING_HARD_BLOCK_RECEIPT")
            if getattr(blocked_receipt, "executed", True) is not False or getattr(blocked_receipt, "order_sent", True) is not False:
                blockers.append("INVALID_INPUT")
        if self.policy.require_source_refs and not source_refs:
            blockers.append("MISSING_SOURCE_REFS")
        if self.policy.require_idempotency and (not artifact_hash or not idempotency_key):
            blockers.append("MISSING_IDEMPOTENCY")
        if confirmation.block_reason:
            blockers.append(confirmation.block_reason)
        if now > expires_at_dt:
            blockers.append("EXPIRED_PERMISSION_REQUEST")
        existing = set(existing_idempotency_keys or [])
        if idempotency_key and idempotency_key in existing:
            blockers.append("DUPLICATE_PERMISSION_REQUEST")
        blockers = _dedupe(blockers)
        reasons.extend(blockers)
        allowed = not blockers
        status = "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW" if allowed else "BLOCKED"
        if "EXPIRED_PERMISSION_REQUEST" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_PERMISSION_REQUEST" in blockers:
            status = "DUPLICATE"
        if any(item in blockers for item in {"MISSING_PREFLIGHT_REPORT", "MISSING_DESIGN_REPORT", "MISSING_HARD_BLOCK_RECEIPT", "INVALID_INPUT"}):
            status = "BLOCKED" if status not in {"EXPIRED", "DUPLICATE"} else status
        scope = "ORDER_INTENT_WORKFLOW_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        intent = LivePermissionIntent(
            intent_id=f"live_permission_intent_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(simulated_contract, "mode", getattr(proposal_draft, "mode", "REVIEW_ONLY")),
            symbol=getattr(simulated_contract, "symbol", getattr(proposal_draft, "symbol", "")),
            broker_symbol=getattr(simulated_contract, "broker_symbol", getattr(proposal_draft, "broker_symbol", "")),
            permission_status=status,
            permission_scope=scope,
            confirmation_state=confirmation.confirmation_state if allowed else confirmation.confirmation_state,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            order_intent_workflow_allowed=allowed,
            hard_live_block_required=True,
            user_acknowledgement_text=confirmation.user_acknowledgement_text,
            confirmation_phrase_required=confirmation.confirmation_phrase_required,
            confirmation_phrase_received=confirmation.confirmation_phrase_received,
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_design_report_id=getattr(design_report, "report_id", ""),
            source_capability_report_id=getattr(capability_report, "report_id", ""),
            source_blocked_receipt_id=getattr(blocked_receipt, "receipt_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            reasons=reasons,
            source_refs=source_refs,
        )
        intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
        return intent


def _normalize(value: str) -> str:
    return " ".join(str(value).strip().split())


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.now(timezone.utc)


def _stable_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _dedupe(items):
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
