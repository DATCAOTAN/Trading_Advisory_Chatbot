from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_parameter_value_proposal.builder import (
    ControlledLiveParameterValueProposalBuilder,
)
from src.services.trading.execution.live_parameter_value_proposal.gate import ControlledLiveParameterValueProposalGate
from src.services.trading.execution.live_parameter_value_proposal.models import (
    ControlledLiveParameterValueProposal,
    ControlledLiveParameterValueProposalJournalRecord,
    ControlledLiveParameterValueProposalSummary,
    ControlledLiveParameterValueProposalValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_parameter_value_proposal.policy import (
    ControlledLiveParameterValueProposalConfig,
)
from src.services.trading.execution.live_parameter_value_proposal.store import (
    ControlledLiveParameterValueProposalJournalStore,
)
from src.services.trading.execution.live_parameter_value_proposal.validator import (
    ControlledLiveParameterValueProposalValidator,
)


@dataclass
class ControlledLiveParameterValueProposalServiceResult:
    proposal: ControlledLiveParameterValueProposal
    validation_report: ControlledLiveParameterValueProposalValidationReport
    journal_record: ControlledLiveParameterValueProposalJournalRecord | None
    summary: ControlledLiveParameterValueProposalSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class ControlledLiveParameterValueProposalService:
    def __init__(
        self,
        config: ControlledLiveParameterValueProposalConfig | None = None,
        builder: ControlledLiveParameterValueProposalBuilder | None = None,
        gate: ControlledLiveParameterValueProposalGate | None = None,
        store: ControlledLiveParameterValueProposalJournalStore | None = None,
        validator: ControlledLiveParameterValueProposalValidator | None = None,
    ):
        self.config = config or ControlledLiveParameterValueProposalConfig.from_config()
        self.builder = builder or ControlledLiveParameterValueProposalBuilder(self.config)
        self.gate = gate or ControlledLiveParameterValueProposalGate(self.config)
        self.store = store or ControlledLiveParameterValueProposalJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or ControlledLiveParameterValueProposalValidator(self.config)

    def run(
        self,
        parameter_draft,
        parameter_draft_validation,
        parameter_source_boundary,
        parameter_source_validation,
        parameter_policy_spec,
        parameter_policy_validation,
        contract_skeleton,
        contract_skeleton_validation,
        live_order_intent,
        live_order_intent_validation,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time=None,
    ) -> ControlledLiveParameterValueProposalServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        proposal = self.builder.build(
            parameter_draft,
            parameter_draft_validation,
            parameter_source_boundary,
            parameter_source_validation,
            parameter_policy_spec,
            parameter_policy_validation,
            contract_skeleton,
            contract_skeleton_validation,
            live_order_intent,
            live_order_intent_validation,
            permission_decision,
            preflight_report,
            proposal_draft,
            simulated_contract,
            simulated_receipt=simulated_receipt,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        build_latency = (perf_counter() - build_started) * 1000
        validation_started = perf_counter()
        validation_report = self.gate.validate(proposal)
        validation_latency = (perf_counter() - validation_started) * 1000

        proposal_validation = self.validator.validate_proposal(proposal)
        report_validation = self.validator.validate_report(validation_report)
        if not proposal_validation.passed or not report_validation.passed:
            proposal.status = "INVALID"
            proposal.human_value_approval_allowed = False
            validation_report.valid = False
            validation_report.human_value_approval_allowed = False
            issues = list(dict.fromkeys(proposal_validation.issues + report_validation.issues))
            proposal.blockers = list(dict.fromkeys(list(proposal.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            proposal.payload_size_chars = len(json.dumps(proposal.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("controlled_live_parameter_value_proposal_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(proposal, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"controlled_live_parameter_value_proposal_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "controlled_live_parameter_value_proposal_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("controlled_live_parameter_value_proposal_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "controlled_value_proposal_build_latency_ms": build_latency,
            "controlled_value_proposal_validation_latency_ms": validation_latency,
            "controlled_value_proposal_journal_append_latency_ms": append_latency,
            "controlled_value_proposal_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return ControlledLiveParameterValueProposalServiceResult(
            proposal,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        proposal: ControlledLiveParameterValueProposal,
        validation_report: ControlledLiveParameterValueProposalValidationReport,
    ) -> ControlledLiveParameterValueProposalJournalRecord:
        created_at = now_utc_iso()
        if proposal.status == "PROPOSAL_CREATED" and validation_report.valid:
            event_type = "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_CREATED"
        elif proposal.status == "DUPLICATE":
            event_type = "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_DUPLICATE_DETECTED"
        else:
            event_type = "CONTROLLED_LIVE_PARAMETER_VALUE_PROPOSAL_BLOCKED"
        record = ControlledLiveParameterValueProposalJournalRecord(
            journal_record_id=_record_id(proposal.proposal_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            proposal_id=proposal.proposal_id,
            validation_report_id=validation_report.validation_report_id,
            status=proposal.status,
            scope=proposal.scope,
            human_value_approval_allowed=validation_report.human_value_approval_allowed,
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
            value_slots_count=validation_report.value_slots_count,
            review_required_slots_count=validation_report.review_required_slots_count,
            approved_slots_count=0,
            rejected_slots_count=0,
            missing_slots_count=validation_report.missing_slots_count,
            artifact_hash=proposal.artifact_hash,
            idempotency_key=proposal.idempotency_key,
            source_parameter_draft_id=proposal.source_parameter_draft_id,
            source_parameter_draft_validation_id=proposal.source_parameter_draft_validation_id,
            source_parameter_source_boundary_id=proposal.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=proposal.source_parameter_policy_spec_id,
            source_contract_skeleton_id=proposal.source_contract_skeleton_id,
            source_live_order_intent_id=proposal.source_live_order_intent_id,
            source_live_permission_decision_id=proposal.source_live_permission_decision_id,
            source_preflight_report_id=proposal.source_preflight_report_id,
            source_refs=list(proposal.source_refs),
            metadata_redacted={
                "controlled_value_proposal_only": True,
                "human_review_required": True,
                "value_lock_required": True,
                "order_contract_ready": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "order_sent": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(proposal_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{proposal_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"controlled_live_parameter_value_proposal_journal_{digest}"
