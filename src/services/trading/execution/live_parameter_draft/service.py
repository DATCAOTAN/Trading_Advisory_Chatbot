from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_parameter_draft.builder import HumanReviewedLiveParameterDraftBuilder
from src.services.trading.execution.live_parameter_draft.gate import HumanReviewedLiveParameterDraftGate
from src.services.trading.execution.live_parameter_draft.models import (
    HumanReviewedLiveParameterDraft,
    HumanReviewedLiveParameterDraftJournalRecord,
    HumanReviewedLiveParameterDraftSummary,
    HumanReviewedLiveParameterDraftValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_parameter_draft.policy import HumanReviewedLiveParameterDraftConfig
from src.services.trading.execution.live_parameter_draft.store import HumanReviewedLiveParameterDraftJournalStore
from src.services.trading.execution.live_parameter_draft.validator import HumanReviewedLiveParameterDraftValidator


@dataclass
class HumanReviewedLiveParameterDraftServiceResult:
    draft: HumanReviewedLiveParameterDraft
    validation_report: HumanReviewedLiveParameterDraftValidationReport
    journal_record: HumanReviewedLiveParameterDraftJournalRecord | None
    summary: HumanReviewedLiveParameterDraftSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class HumanReviewedLiveParameterDraftService:
    def __init__(
        self,
        config: HumanReviewedLiveParameterDraftConfig | None = None,
        builder: HumanReviewedLiveParameterDraftBuilder | None = None,
        gate: HumanReviewedLiveParameterDraftGate | None = None,
        store: HumanReviewedLiveParameterDraftJournalStore | None = None,
        validator: HumanReviewedLiveParameterDraftValidator | None = None,
    ):
        self.config = config or HumanReviewedLiveParameterDraftConfig.from_config()
        self.builder = builder or HumanReviewedLiveParameterDraftBuilder(self.config)
        self.gate = gate or HumanReviewedLiveParameterDraftGate(self.config)
        self.store = store or HumanReviewedLiveParameterDraftJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or HumanReviewedLiveParameterDraftValidator(self.config)

    def run(
        self,
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
    ) -> HumanReviewedLiveParameterDraftServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        draft = self.builder.build(
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
        validation_report = self.gate.validate(draft)
        validation_latency = (perf_counter() - validation_started) * 1000

        draft_validation = self.validator.validate_draft(draft)
        report_validation = self.validator.validate_report(validation_report)
        if not draft_validation.passed or not report_validation.passed:
            draft.status = "INVALID"
            draft.value_proposal_workflow_allowed = False
            validation_report.valid = False
            validation_report.value_proposal_workflow_allowed = False
            issues = list(dict.fromkeys(draft_validation.issues + report_validation.issues))
            draft.blockers = list(dict.fromkeys(list(draft.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            draft.payload_size_chars = len(json.dumps(draft.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("human_reviewed_live_parameter_draft_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(draft, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"human_reviewed_live_parameter_draft_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "human_reviewed_live_parameter_draft_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("human_reviewed_live_parameter_draft_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "parameter_draft_build_latency_ms": build_latency,
            "parameter_draft_validation_latency_ms": validation_latency,
            "parameter_draft_journal_append_latency_ms": append_latency,
            "parameter_draft_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return HumanReviewedLiveParameterDraftServiceResult(
            draft,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        draft: HumanReviewedLiveParameterDraft,
        validation_report: HumanReviewedLiveParameterDraftValidationReport,
    ) -> HumanReviewedLiveParameterDraftJournalRecord:
        created_at = now_utc_iso()
        if draft.status == "DRAFT_CREATED" and validation_report.valid:
            event_type = "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_CREATED"
        elif draft.status == "DUPLICATE":
            event_type = "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_DUPLICATE_DETECTED"
        else:
            event_type = "HUMAN_REVIEWED_LIVE_PARAMETER_DRAFT_BLOCKED"
        record = HumanReviewedLiveParameterDraftJournalRecord(
            journal_record_id=_record_id(draft.draft_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            draft_id=draft.draft_id,
            validation_report_id=validation_report.validation_report_id,
            status=draft.status,
            scope=draft.scope,
            value_proposal_workflow_allowed=validation_report.value_proposal_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            slots_count=validation_report.slots_count,
            unresolved_slots_count=validation_report.unresolved_slots_count,
            resolved_slots_count=0,
            missing_slots_count=validation_report.missing_slots_count,
            artifact_hash=draft.artifact_hash,
            idempotency_key=draft.idempotency_key,
            source_parameter_source_boundary_id=draft.source_parameter_source_boundary_id,
            source_parameter_source_validation_id=draft.source_parameter_source_validation_id,
            source_parameter_policy_spec_id=draft.source_parameter_policy_spec_id,
            source_contract_skeleton_id=draft.source_contract_skeleton_id,
            source_live_order_intent_id=draft.source_live_order_intent_id,
            source_live_permission_decision_id=draft.source_live_permission_decision_id,
            source_preflight_report_id=draft.source_preflight_report_id,
            source_refs=list(draft.source_refs),
            metadata_redacted={
                "human_reviewed_parameter_draft_only": True,
                "slots_unresolved": True,
                "actual_order_values_present": False,
                "resolved_parameter_values_present": False,
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


def _record_id(draft_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{draft_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"human_reviewed_live_parameter_draft_journal_{digest}"
