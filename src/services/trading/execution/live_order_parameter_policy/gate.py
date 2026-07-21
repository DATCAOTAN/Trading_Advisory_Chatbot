from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_parameter_policy.models import (
    REQUIRED_PARAMETER_POLICY_GROUP_LABELS,
    LiveOrderParameterPolicySpec,
    LiveOrderParameterPolicyValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_parameter_policy.policy import LiveOrderParameterPolicyConfig


class LiveOrderParameterPolicyGate:
    def __init__(self, config: LiveOrderParameterPolicyConfig | None = None):
        self.config = config or LiveOrderParameterPolicyConfig.from_config()

    def validate(self, spec: LiveOrderParameterPolicySpec) -> LiveOrderParameterPolicyValidationReport:
        checks = [
            _check("policy_validated", spec.status == "POLICY_VALIDATED"),
            _check("scope_source_boundary_only", spec.scope == "PARAMETER_SOURCE_BOUNDARY_ONLY"),
            _check("source_boundary_allowed", spec.parameter_source_boundary_allowed is True),
            _check("live_execution_disabled", spec.live_execution_allowed is False),
            _check("order_submission_disabled", spec.order_send_allowed is False),
            _check("execution_disabled", spec.execution_allowed is False),
            _check("not_executable", spec.executable is False),
            _check("mt5_payload_not_created", spec.mt5_payload_created is False),
            _check("order_not_sent", spec.order_sent is False),
            _check("hard_block_required", spec.hard_live_block_required is True),
            _check("policy_groups_present", set(spec.required_parameter_groups) == set(REQUIRED_PARAMETER_POLICY_GROUP_LABELS)),
            _check("unresolved_groups_present", set(spec.unresolved_parameter_groups) == set(REQUIRED_PARAMETER_POLICY_GROUP_LABELS)),
            _check("policy_rules_cover_groups", {rule.group for rule in spec.policy_rules} == set(REQUIRED_PARAMETER_POLICY_GROUP_LABELS)),
            _check("policy_rules_policy_only", all(rule.status == "SATISFIED_AS_POLICY_ONLY" for rule in spec.policy_rules)),
            _check("future_source_boundary_required", all(rule.future_source_boundary_required for rule in spec.policy_rules)),
            _check("resolved_parameter_values_absent", spec.resolved_parameter_values_present is False),
            _check("actual_order_values_absent", spec.actual_order_values_present is False),
            _check("source_refs_present", bool(spec.source_refs)),
            _check("idempotency_present", bool(spec.idempotency_key)),
            _check("artifact_hash_present", bool(spec.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not spec.blockers
        blockers = [] if valid else list(dict.fromkeys(list(spec.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = LiveOrderParameterPolicyValidationReport(
            validation_report_id=f"live_order_parameter_policy_validation_{_hash(spec.policy_spec_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_policy_spec_id=spec.policy_spec_id,
            valid=valid,
            parameter_source_boundary_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            policy_groups_count=len(spec.required_parameter_groups),
            policy_rules_count=len(spec.policy_rules),
            unresolved_groups_count=len(spec.unresolved_parameter_groups),
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            validation_checks=checks,
            blockers=blockers,
            warnings=list(spec.warnings),
            source_refs=list(spec.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
