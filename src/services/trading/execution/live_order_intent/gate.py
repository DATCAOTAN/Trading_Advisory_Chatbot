from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_intent.models import (
    LiveOrderIntent,
    LiveOrderIntentValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_intent.policy import LiveOrderIntentPolicy


class LiveOrderIntentGate:
    def __init__(self, policy: LiveOrderIntentPolicy | None = None):
        self.policy = policy or LiveOrderIntentPolicy.from_config()

    def validate(self, intent: LiveOrderIntent) -> LiveOrderIntentValidationReport:
        checks = [
            _check("intent_created_for_contract_workflow", intent.status == "CREATED_FOR_CONTRACT_WORKFLOW"),
            _check("scope_contract_preparation_only", intent.scope == "ORDER_CONTRACT_PREPARATION_ONLY"),
            _check("workflow_allowed", intent.order_contract_workflow_allowed is True),
            _check("live_execution_disabled", intent.live_execution_allowed is False),
            _check("order_submission_disabled", intent.order_send_allowed is False),
            _check("execution_disabled", intent.execution_allowed is False),
            _check("hard_block_required", intent.hard_live_block_required is True),
            _check("source_refs_present", bool(intent.source_refs)),
            _check("idempotency_present", bool(intent.idempotency_key)),
            _check("artifact_hash_present", bool(intent.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not intent.blockers
        blockers = [] if valid else list(dict.fromkeys(list(intent.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = LiveOrderIntentValidationReport(
            validation_report_id=f"live_order_intent_validation_{_hash(intent.intent_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_live_order_intent_id=intent.intent_id,
            valid=valid,
            order_contract_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            validation_checks=checks,
            blockers=blockers,
            warnings=list(intent.warnings),
            source_refs=list(intent.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
