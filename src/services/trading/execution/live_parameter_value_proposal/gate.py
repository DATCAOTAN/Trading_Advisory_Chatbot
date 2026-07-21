from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_parameter_value_proposal.models import (
    REQUIRED_CONTROLLED_VALUE_SLOT_TYPES,
    ControlledLiveParameterValueProposal,
    ControlledLiveParameterValueProposalValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_parameter_value_proposal.policy import (
    ControlledLiveParameterValueProposalConfig,
)


class ControlledLiveParameterValueProposalGate:
    def __init__(self, config: ControlledLiveParameterValueProposalConfig | None = None):
        self.config = config or ControlledLiveParameterValueProposalConfig.from_config()

    def validate(self, proposal: ControlledLiveParameterValueProposal) -> ControlledLiveParameterValueProposalValidationReport:
        slot_types = {slot.slot_type for slot in proposal.value_slots}
        checks = [
            _check("proposal_created", proposal.status == "PROPOSAL_CREATED"),
            _check("scope_human_value_approval_only", proposal.scope == "HUMAN_VALUE_APPROVAL_ONLY"),
            _check("human_value_approval_allowed", proposal.human_value_approval_allowed is True),
            _check("live_execution_disabled", proposal.live_execution_allowed is False),
            _check("order_submission_disabled", proposal.order_send_allowed is False),
            _check("execution_disabled", proposal.execution_allowed is False),
            _check("not_executable", proposal.executable is False),
            _check("mt5_payload_not_created", proposal.mt5_payload_created is False),
            _check("order_not_sent", proposal.order_sent is False),
            _check("hard_block_required", proposal.hard_live_block_required is True),
            _check("order_contract_not_ready", proposal.order_contract_ready is False),
            _check("value_lock_required", proposal.value_lock_required is True),
            _check("human_review_required", proposal.human_review_required is True),
            _check("exactly_nine_value_slots", len(proposal.value_slots) == len(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES)),
            _check("required_value_slot_types_present", slot_types == set(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES)),
            _check(
                "value_slots_non_executable_review_required",
                all(
                    not slot.executable_value and slot.human_review_required and slot.value_lock_required
                    for slot in proposal.value_slots
                ),
            ),
            _check("source_refs_present", bool(proposal.source_refs)),
            _check("idempotency_present", bool(proposal.idempotency_key)),
            _check("artifact_hash_present", bool(proposal.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not proposal.blockers
        blockers = [] if valid else list(dict.fromkeys(list(proposal.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = ControlledLiveParameterValueProposalValidationReport(
            validation_report_id=f"controlled_live_parameter_value_proposal_validation_{_hash(proposal.proposal_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_proposal_id=proposal.proposal_id,
            valid=valid,
            human_value_approval_allowed=valid,
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
            value_slots_count=len(proposal.value_slots),
            review_required_slots_count=sum(1 for slot in proposal.value_slots if slot.human_review_required),
            approved_slots_count=0,
            rejected_slots_count=0,
            missing_slots_count=len(proposal.missing_value_slot_types),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(proposal.warnings),
            source_refs=list(proposal.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
