from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_contract.models import (
    REQUIRED_PARAMETER_GROUP_LABELS,
    LiveOrderContractSkeleton,
    LiveOrderContractSkeletonValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract.policy import LiveOrderContractSkeletonPolicy


class LiveOrderContractSkeletonGate:
    def __init__(self, policy: LiveOrderContractSkeletonPolicy | None = None):
        self.policy = policy or LiveOrderContractSkeletonPolicy.from_config()

    def validate(self, skeleton: LiveOrderContractSkeleton) -> LiveOrderContractSkeletonValidationReport:
        checks = [
            _check("skeleton_created", skeleton.status == "SKELETON_CREATED"),
            _check("scope_parameter_validation_only", skeleton.scope == "CONTRACT_PARAMETER_VALIDATION_ONLY"),
            _check("parameter_validation_allowed", skeleton.contract_parameter_validation_allowed is True),
            _check("live_execution_disabled", skeleton.live_execution_allowed is False),
            _check("order_submission_disabled", skeleton.order_send_allowed is False),
            _check("execution_disabled", skeleton.execution_allowed is False),
            _check("hard_block_required", skeleton.hard_live_block_required is True),
            _check("not_executable", skeleton.executable is False),
            _check("mt5_payload_not_created", skeleton.mt5_payload_created is False),
            _check("order_not_sent", skeleton.order_sent is False),
            _check("required_parameter_groups_labels_only", set(skeleton.required_parameter_groups) == set(REQUIRED_PARAMETER_GROUP_LABELS)),
            _check("missing_parameter_groups_labels_only", set(skeleton.missing_parameter_groups) == set(REQUIRED_PARAMETER_GROUP_LABELS)),
            _check("resolved_parameter_groups_empty", not skeleton.resolved_parameter_groups),
            _check("source_refs_present", bool(skeleton.source_refs)),
            _check("idempotency_present", bool(skeleton.idempotency_key)),
            _check("artifact_hash_present", bool(skeleton.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not skeleton.blockers
        blockers = [] if valid else list(dict.fromkeys(list(skeleton.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = LiveOrderContractSkeletonValidationReport(
            validation_report_id=f"live_order_contract_skeleton_validation_{_hash(skeleton.contract_skeleton_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_contract_skeleton_id=skeleton.contract_skeleton_id,
            valid=valid,
            contract_parameter_validation_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            validation_checks=checks,
            blockers=blockers,
            warnings=list(skeleton.warnings),
            source_refs=list(skeleton.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
