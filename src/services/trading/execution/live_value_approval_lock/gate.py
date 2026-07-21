from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_value_approval_lock.models import (
    REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES,
    HumanValueApprovalLock,
    HumanValueApprovalLockValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_value_approval_lock.policy import HumanValueApprovalLockConfig


class HumanValueApprovalLockGate:
    def __init__(self, config: HumanValueApprovalLockConfig | None = None):
        self.config = config or HumanValueApprovalLockConfig.from_config()

    def validate(self, approval_lock: HumanValueApprovalLock) -> HumanValueApprovalLockValidationReport:
        slot_types = {slot.slot_type for slot in approval_lock.slot_locks}
        checks = [
            _check("values_locked_for_contract_parameterization", approval_lock.status == "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION"),
            _check("scope_contract_parameterization_only", approval_lock.scope == "CONTRACT_PARAMETERIZATION_ONLY"),
            _check("contract_parameterization_workflow_allowed", approval_lock.contract_parameterization_workflow_allowed is True),
            _check("confirmation_phrase_valid", approval_lock.confirmation_phrase_valid is True),
            _check("live_execution_disabled", approval_lock.live_execution_allowed is False),
            _check("order_submission_disabled", approval_lock.order_send_allowed is False),
            _check("execution_disabled", approval_lock.execution_allowed is False),
            _check("not_executable", approval_lock.executable is False),
            _check("mt5_payload_not_created", approval_lock.mt5_payload_created is False),
            _check("order_not_sent", approval_lock.order_sent is False),
            _check("hard_block_required", approval_lock.hard_live_block_required is True),
            _check("order_contract_not_ready", approval_lock.order_contract_ready is False),
            _check("raw_values_not_stored", approval_lock.raw_values_stored is False),
            _check("executable_order_not_created", approval_lock.executable_order_created is False),
            _check("value_lock_required", approval_lock.value_lock_required is True),
            _check("human_review_required", approval_lock.human_review_required is True),
            _check("exactly_nine_slot_locks", len(approval_lock.slot_locks) == len(REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES)),
            _check("required_slot_lock_types_present", slot_types == set(REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES)),
            _check(
                "slot_locks_safe_and_redacted",
                all(
                    not slot.raw_value_stored
                    and not slot.executable_value
                    and not slot.mt5_payload_value
                    and not slot.order_value
                    and slot.value_payload_redacted
                    for slot in approval_lock.slot_locks
                ),
            ),
            _check("source_refs_present", bool(approval_lock.source_refs)),
            _check("idempotency_present", bool(approval_lock.idempotency_key)),
            _check("artifact_hash_present", bool(approval_lock.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not approval_lock.blockers
        blockers = [] if valid else list(dict.fromkeys(list(approval_lock.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = HumanValueApprovalLockValidationReport(
            validation_report_id=f"human_value_approval_lock_validation_{_hash(approval_lock.approval_lock_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_approval_lock_id=approval_lock.approval_lock_id,
            valid=valid,
            contract_parameterization_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            value_lock_required=True,
            human_review_required=True,
            raw_values_stored=False,
            executable_order_created=False,
            confirmation_phrase_valid=approval_lock.confirmation_phrase_valid and valid,
            slot_locks_count=len(approval_lock.slot_locks),
            locked_slots_count=sum(1 for slot in approval_lock.slot_locks if slot.approved_for_future_parameterization),
            rejected_slots_count=0,
            missing_slots_count=len(approval_lock.missing_slot_lock_types),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(approval_lock.warnings),
            source_refs=list(approval_lock.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
