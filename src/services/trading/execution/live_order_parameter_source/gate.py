from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_parameter_source.models import (
    REQUIRED_PARAMETER_SOURCE_GROUP_LABELS,
    REQUIRED_PARAMETER_SOURCE_TYPE_LABELS,
    LiveOrderParameterSourceBoundary,
    LiveOrderParameterSourceValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_parameter_source.policy import LiveOrderParameterSourceBoundaryConfig


class LiveOrderParameterSourceBoundaryGate:
    def __init__(self, config: LiveOrderParameterSourceBoundaryConfig | None = None):
        self.config = config or LiveOrderParameterSourceBoundaryConfig.from_config()

    def validate(self, boundary: LiveOrderParameterSourceBoundary) -> LiveOrderParameterSourceValidationReport:
        groups = {candidate.parameter_group for candidate in boundary.source_candidates}
        types = {candidate.source_type for candidate in boundary.source_candidates}
        checks = [
            _check("source_boundary_validated", boundary.status == "SOURCE_BOUNDARY_VALIDATED"),
            _check("scope_human_reviewed_parameter_draft_only", boundary.scope == "HUMAN_REVIEWED_PARAMETER_DRAFT_ONLY"),
            _check("human_reviewed_parameter_draft_allowed", boundary.human_reviewed_parameter_draft_allowed is True),
            _check("live_execution_disabled", boundary.live_execution_allowed is False),
            _check("order_submission_disabled", boundary.order_send_allowed is False),
            _check("execution_disabled", boundary.execution_allowed is False),
            _check("not_executable", boundary.executable is False),
            _check("mt5_payload_not_created", boundary.mt5_payload_created is False),
            _check("order_not_sent", boundary.order_sent is False),
            _check("hard_block_required", boundary.hard_live_block_required is True),
            _check("resolved_values_absent", boundary.resolved_parameter_values_present is False),
            _check("actual_order_values_absent", boundary.actual_order_values_present is False),
            _check("source_candidates_present", bool(boundary.source_candidates)),
            _check("source_candidates_cover_groups", groups == set(REQUIRED_PARAMETER_SOURCE_GROUP_LABELS)),
            _check("required_source_types_declared", set(REQUIRED_PARAMETER_SOURCE_TYPE_LABELS).issubset(types)),
            _check("candidate_values_unresolved", all(not item.actual_value_allowed_now and not item.value_resolved_now for item in boundary.source_candidates)),
            _check("source_refs_present", bool(boundary.source_refs)),
            _check("idempotency_present", bool(boundary.idempotency_key)),
            _check("artifact_hash_present", bool(boundary.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not boundary.blockers
        blockers = [] if valid else list(dict.fromkeys(list(boundary.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = LiveOrderParameterSourceValidationReport(
            validation_report_id=f"live_order_parameter_source_validation_{_hash(boundary.boundary_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_boundary_id=boundary.boundary_id,
            valid=valid,
            human_reviewed_parameter_draft_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            source_candidates_count=len(boundary.source_candidates),
            required_sources_count=len(boundary.required_source_types),
            missing_sources_count=len(boundary.missing_source_types),
            rejected_sources_count=len(boundary.rejected_source_types),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(boundary.warnings),
            source_refs=list(boundary.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
