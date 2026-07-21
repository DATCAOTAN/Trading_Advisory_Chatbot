from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_parameter_draft.models import (
    REQUIRED_HUMAN_REVIEWED_SLOT_TYPES,
    HumanReviewedLiveParameterDraft,
    HumanReviewedLiveParameterDraftValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_parameter_draft.policy import HumanReviewedLiveParameterDraftConfig


class HumanReviewedLiveParameterDraftGate:
    def __init__(self, config: HumanReviewedLiveParameterDraftConfig | None = None):
        self.config = config or HumanReviewedLiveParameterDraftConfig.from_config()

    def validate(self, draft: HumanReviewedLiveParameterDraft) -> HumanReviewedLiveParameterDraftValidationReport:
        slot_types = {slot.slot_type for slot in draft.slots}
        checks = [
            _check("draft_created", draft.status == "DRAFT_CREATED"),
            _check("scope_value_proposal_workflow_only", draft.scope == "VALUE_PROPOSAL_WORKFLOW_ONLY"),
            _check("value_proposal_workflow_allowed", draft.value_proposal_workflow_allowed is True),
            _check("live_execution_disabled", draft.live_execution_allowed is False),
            _check("order_submission_disabled", draft.order_send_allowed is False),
            _check("execution_disabled", draft.execution_allowed is False),
            _check("not_executable", draft.executable is False),
            _check("mt5_payload_not_created", draft.mt5_payload_created is False),
            _check("order_not_sent", draft.order_sent is False),
            _check("hard_block_required", draft.hard_live_block_required is True),
            _check("resolved_values_absent", draft.resolved_parameter_values_present is False),
            _check("actual_order_values_absent", draft.actual_order_values_present is False),
            _check("exactly_nine_slots", len(draft.slots) == len(REQUIRED_HUMAN_REVIEWED_SLOT_TYPES)),
            _check("required_slot_types_present", slot_types == set(REQUIRED_HUMAN_REVIEWED_SLOT_TYPES)),
            _check(
                "slot_values_unresolved",
                all(
                    not slot.value_allowed_now and not slot.value_resolved_now and not slot.actual_value_present
                    for slot in draft.slots
                ),
            ),
            _check("source_refs_present", bool(draft.source_refs)),
            _check("idempotency_present", bool(draft.idempotency_key)),
            _check("artifact_hash_present", bool(draft.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not draft.blockers
        blockers = [] if valid else list(dict.fromkeys(list(draft.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = HumanReviewedLiveParameterDraftValidationReport(
            validation_report_id=f"human_reviewed_live_parameter_draft_validation_{_hash(draft.draft_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_draft_id=draft.draft_id,
            valid=valid,
            value_proposal_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            slots_count=len(draft.slots),
            unresolved_slots_count=len(draft.unresolved_slot_types),
            resolved_slots_count=0,
            missing_slots_count=len(draft.missing_slot_types),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(draft.warnings),
            source_refs=list(draft.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
