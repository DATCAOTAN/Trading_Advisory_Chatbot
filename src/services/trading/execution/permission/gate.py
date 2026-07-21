from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.permission.models import LivePermissionGateDecision, LivePermissionIntent, now_utc_iso
from src.services.trading.execution.permission.policy import LivePermissionPolicy


class LivePermissionGate:
    def __init__(self, policy: LivePermissionPolicy | None = None):
        self.policy = policy or LivePermissionPolicy.from_config()

    def decide(self, intent: LivePermissionIntent) -> LivePermissionGateDecision:
        allowed = (
            intent.permission_status == "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW"
            and intent.confirmation_state == "CONFIRMED_PERMISSION_GATE_ONLY"
            and bool(intent.order_intent_workflow_allowed)
            and not intent.blockers
        )
        decision = LivePermissionGateDecision(
            decision_id=f"live_permission_decision_{_hash(intent.intent_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            intent_id=intent.intent_id,
            permission_status=intent.permission_status if allowed else intent.permission_status,
            permission_scope="ORDER_INTENT_WORKFLOW_ONLY" if allowed else "EXECUTION_NOT_ALLOWED",
            gate_allowed=allowed,
            order_intent_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            block_reasons=list(intent.blockers),
            blockers=list(intent.blockers),
            warnings=list(intent.warnings),
            source_preflight_report_id=intent.source_preflight_report_id,
            source_design_report_id=intent.source_design_report_id,
            source_refs=list(intent.source_refs),
        )
        decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
        return decision


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
