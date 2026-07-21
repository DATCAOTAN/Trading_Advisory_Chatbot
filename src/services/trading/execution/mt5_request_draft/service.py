from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_request_draft.builder import MT5RequestDraftBuilder
from src.services.trading.execution.mt5_request_draft.gate import MT5RequestDraftGate
from src.services.trading.execution.mt5_request_draft.models import (
    MT5RequestDraftBoundary,
    MT5RequestDraftJournalRecord,
    MT5RequestDraftSummary,
    MT5RequestDraftValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_draft.policy import MT5RequestDraftConfig
from src.services.trading.execution.mt5_request_draft.store import MT5RequestDraftJournalStore
from src.services.trading.execution.mt5_request_draft.validator import MT5RequestDraftValidator


@dataclass
class MT5RequestDraftServiceResult:
    request_draft: MT5RequestDraftBoundary
    validation_report: MT5RequestDraftValidationReport
    journal_record: MT5RequestDraftJournalRecord | None
    summary: MT5RequestDraftSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class MT5RequestDraftService:
    def __init__(
        self,
        config: MT5RequestDraftConfig | None = None,
        builder: MT5RequestDraftBuilder | None = None,
        gate: MT5RequestDraftGate | None = None,
        store: MT5RequestDraftJournalStore | None = None,
        validator: MT5RequestDraftValidator | None = None,
    ):
        self.config = config or MT5RequestDraftConfig.from_config()
        self.builder = builder or MT5RequestDraftBuilder(self.config)
        self.gate = gate or MT5RequestDraftGate(self.config)
        self.store = store or MT5RequestDraftJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or MT5RequestDraftValidator(self.config)

    def run(
        self,
        dry_run_validation,
        dry_run_validation_report,
        pre_mt5_mapping,
        pre_mt5_mapping_validation,
        final_review,
        final_review_validation,
        parameterization,
        parameterization_validation,
        approval_lock,
        approval_lock_validation,
        value_proposal,
        value_proposal_validation,
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
    ) -> MT5RequestDraftServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()

        build_started = perf_counter()
        request_draft = self.builder.build(
            dry_run_validation,
            dry_run_validation_report,
            pre_mt5_mapping,
            pre_mt5_mapping_validation,
            final_review,
            final_review_validation,
            parameterization,
            parameterization_validation,
            approval_lock,
            approval_lock_validation,
            value_proposal,
            value_proposal_validation,
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

        report_started = perf_counter()
        validation_report = self.gate.validate(request_draft)
        report_latency = (perf_counter() - report_started) * 1000

        object_validation = self.validator.validate_request_draft(request_draft, dry_run_validation_report)
        report_validation = self.validator.validate_report(validation_report)
        if not object_validation.passed or not report_validation.passed:
            request_draft.status = "INVALID"
            request_draft.mt5_request_draft_final_approval_workflow_allowed = False
            validation_report.valid = False
            validation_report.mt5_request_draft_final_approval_workflow_allowed = False
            issues = list(dict.fromkeys(object_validation.issues + report_validation.issues))
            request_draft.blockers = list(dict.fromkeys(list(request_draft.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            request_draft.payload_size_chars = len(json.dumps(request_draft.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("mt5_request_draft_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(request_draft, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"mt5_request_draft_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("mt5_request_draft_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("mt5_request_draft_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "mt5_request_draft_build_latency_ms": build_latency,
            "mt5_request_draft_report_latency_ms": report_latency,
            "mt5_request_draft_journal_append_latency_ms": append_latency,
            "mt5_request_draft_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return MT5RequestDraftServiceResult(
            request_draft=request_draft,
            validation_report=validation_report,
            journal_record=record,
            summary=summary,
            warning=";".join(warning_parts),
            timings_ms=timings,
        )

    def _build_record(
        self,
        request_draft: MT5RequestDraftBoundary,
        report: MT5RequestDraftValidationReport,
    ) -> MT5RequestDraftJournalRecord:
        created_at = now_utc_iso()
        if request_draft.status == "REQUEST_DRAFT_CREATED" and report.valid:
            event_type = "MT5_REQUEST_DRAFT_CREATED"
        elif request_draft.status == "DUPLICATE":
            event_type = "MT5_REQUEST_DRAFT_DUPLICATE_DETECTED"
        else:
            event_type = "MT5_REQUEST_DRAFT_BLOCKED"
        record = MT5RequestDraftJournalRecord(
            journal_record_id=_record_id(request_draft.request_draft_id, report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            request_draft_id=request_draft.request_draft_id,
            validation_report_id=report.validation_report_id,
            status=request_draft.status,
            scope=request_draft.scope,
            mt5_request_draft_final_approval_workflow_allowed=report.mt5_request_draft_final_approval_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            draft_fields_count=report.draft_fields_count,
            created_draft_fields_count=report.created_draft_fields_count,
            missing_draft_fields_count=report.missing_draft_fields_count,
            invalid_draft_fields_count=report.invalid_draft_fields_count,
            artifact_hash=request_draft.artifact_hash,
            idempotency_key=request_draft.idempotency_key,
            source_dry_run_validation_id=request_draft.source_dry_run_validation_id,
            source_dry_run_validation_report_id=request_draft.source_dry_run_validation_report_id,
            source_pre_mt5_mapping_id=request_draft.source_pre_mt5_mapping_id,
            source_pre_mt5_mapping_validation_id=request_draft.source_pre_mt5_mapping_validation_id,
            source_final_review_id=request_draft.source_final_review_id,
            source_parameterization_id=request_draft.source_parameterization_id,
            source_approval_lock_id=request_draft.source_approval_lock_id,
            source_value_proposal_id=request_draft.source_value_proposal_id,
            source_parameter_draft_id=request_draft.source_parameter_draft_id,
            source_parameter_source_boundary_id=request_draft.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=request_draft.source_parameter_policy_spec_id,
            source_contract_skeleton_id=request_draft.source_contract_skeleton_id,
            source_live_order_intent_id=request_draft.source_live_order_intent_id,
            source_live_permission_decision_id=request_draft.source_live_permission_decision_id,
            source_preflight_report_id=request_draft.source_preflight_report_id,
            source_refs=list(request_draft.source_refs),
            metadata_redacted={
                "request_draft_boundary_only": True,
                "draft_values_reference_only": True,
                "raw_values_stored": False,
                "executable_order_created": False,
                "broker_mapping_created": False,
                "broker_submission_created": False,
                "order_request_mapping_allowed": False,
                "order_contract_ready": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "mt5_payload_created": False,
                "mt5_request_dict_created": False,
                "mt5_constants_used": False,
                "order_sent": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(request_draft_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{request_draft_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mt5_request_draft_journal_{digest}"
