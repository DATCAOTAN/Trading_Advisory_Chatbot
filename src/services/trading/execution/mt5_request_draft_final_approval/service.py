from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_request_draft_final_approval.builder import (
    MT5RequestDraftFinalApprovalBuilder,
)
from src.services.trading.execution.mt5_request_draft_final_approval.gate import (
    MT5RequestDraftFinalApprovalGate,
)
from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    MT5RequestDraftFinalApprovalBoundary,
    MT5RequestDraftFinalApprovalJournalRecord,
    MT5RequestDraftFinalApprovalSummary,
    MT5RequestDraftFinalApprovalValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_draft_final_approval.policy import (
    MT5RequestDraftFinalApprovalConfig,
)
from src.services.trading.execution.mt5_request_draft_final_approval.store import (
    MT5RequestDraftFinalApprovalJournalStore,
)
from src.services.trading.execution.mt5_request_draft_final_approval.validator import (
    MT5RequestDraftFinalApprovalValidator,
)


@dataclass
class MT5RequestDraftFinalApprovalServiceResult:
    final_approval: MT5RequestDraftFinalApprovalBoundary
    validation_report: MT5RequestDraftFinalApprovalValidationReport
    journal_record: MT5RequestDraftFinalApprovalJournalRecord | None
    summary: MT5RequestDraftFinalApprovalSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class MT5RequestDraftFinalApprovalService:
    def __init__(
        self,
        config: MT5RequestDraftFinalApprovalConfig | None = None,
        builder: MT5RequestDraftFinalApprovalBuilder | None = None,
        gate: MT5RequestDraftFinalApprovalGate | None = None,
        store: MT5RequestDraftFinalApprovalJournalStore | None = None,
        validator: MT5RequestDraftFinalApprovalValidator | None = None,
    ):
        self.config = config or MT5RequestDraftFinalApprovalConfig.from_config()
        self.builder = builder or MT5RequestDraftFinalApprovalBuilder(self.config)
        self.gate = gate or MT5RequestDraftFinalApprovalGate(self.config)
        self.store = store or MT5RequestDraftFinalApprovalJournalStore(
            self.config.journal_path,
            self.config.max_read_records,
        )
        self.validator = validator or MT5RequestDraftFinalApprovalValidator(self.config)

    def run(
        self,
        request_draft,
        request_draft_validation_report,
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
        confirmation_phrase: str | None = None,
        current_time=None,
    ) -> MT5RequestDraftFinalApprovalServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()

        build_started = perf_counter()
        approval = self.builder.build(
            request_draft,
            request_draft_validation_report,
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
            confirmation_phrase=confirmation_phrase,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        build_latency = (perf_counter() - build_started) * 1000

        report_started = perf_counter()
        validation_report = self.gate.validate(approval)
        report_latency = (perf_counter() - report_started) * 1000

        object_validation = self.validator.validate_final_approval(approval, request_draft_validation_report)
        report_validation = self.validator.validate_report(validation_report)
        if not object_validation.passed or not report_validation.passed:
            approval.status = "INVALID" if approval.status not in {"REJECTED", "EXPIRED", "DUPLICATE"} else approval.status
            approval.mt5_request_dict_dry_run_builder_workflow_allowed = False
            validation_report.valid = False
            validation_report.mt5_request_dict_dry_run_builder_workflow_allowed = False
            issues = list(dict.fromkeys(object_validation.issues + report_validation.issues))
            approval.blockers = list(dict.fromkeys(list(approval.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            approval.payload_size_chars = len(json.dumps(approval.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("mt5_request_draft_final_approval_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(approval, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"mt5_request_draft_final_approval_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "mt5_request_draft_final_approval_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("mt5_request_draft_final_approval_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "mt5_request_draft_final_approval_build_latency_ms": build_latency,
            "mt5_request_draft_final_approval_report_latency_ms": report_latency,
            "mt5_request_draft_final_approval_journal_append_latency_ms": append_latency,
            "mt5_request_draft_final_approval_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return MT5RequestDraftFinalApprovalServiceResult(
            final_approval=approval,
            validation_report=validation_report,
            journal_record=record,
            summary=summary,
            warning=";".join(warning_parts),
            timings_ms=timings,
        )

    def _build_record(
        self,
        approval: MT5RequestDraftFinalApprovalBoundary,
        report: MT5RequestDraftFinalApprovalValidationReport,
    ) -> MT5RequestDraftFinalApprovalJournalRecord:
        created_at = now_utc_iso()
        if approval.status == "FINAL_APPROVAL_GRANTED_FOR_DRY_RUN_REQUEST_DICT_BUILDER" and report.valid:
            event_type = "MT5_REQUEST_DRAFT_FINAL_APPROVAL_GRANTED"
        elif approval.status == "DUPLICATE":
            event_type = "MT5_REQUEST_DRAFT_FINAL_APPROVAL_DUPLICATE_DETECTED"
        elif approval.status == "REJECTED":
            event_type = "MT5_REQUEST_DRAFT_FINAL_APPROVAL_REJECTED"
        else:
            event_type = "MT5_REQUEST_DRAFT_FINAL_APPROVAL_BLOCKED"
        record = MT5RequestDraftFinalApprovalJournalRecord(
            journal_record_id=_record_id(approval.final_approval_id, report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            final_approval_id=approval.final_approval_id,
            validation_report_id=report.validation_report_id,
            status=approval.status,
            scope=approval.scope,
            mt5_request_dict_dry_run_builder_workflow_allowed=report.mt5_request_dict_dry_run_builder_workflow_allowed,
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
            confirmation_phrase_valid=report.confirmation_phrase_valid,
            approved_fields_count=report.approved_fields_count,
            approved_fields_valid_count=report.approved_fields_valid_count,
            missing_approved_fields_count=report.missing_approved_fields_count,
            invalid_approved_fields_count=report.invalid_approved_fields_count,
            artifact_hash=approval.artifact_hash,
            idempotency_key=approval.idempotency_key,
            source_request_draft_id=approval.source_request_draft_id,
            source_request_draft_validation_report_id=approval.source_request_draft_validation_report_id,
            source_dry_run_validation_id=approval.source_dry_run_validation_id,
            source_dry_run_validation_report_id=approval.source_dry_run_validation_report_id,
            source_pre_mt5_mapping_id=approval.source_pre_mt5_mapping_id,
            source_pre_mt5_mapping_validation_id=approval.source_pre_mt5_mapping_validation_id,
            source_final_review_id=approval.source_final_review_id,
            source_parameterization_id=approval.source_parameterization_id,
            source_approval_lock_id=approval.source_approval_lock_id,
            source_value_proposal_id=approval.source_value_proposal_id,
            source_parameter_draft_id=approval.source_parameter_draft_id,
            source_parameter_source_boundary_id=approval.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=approval.source_parameter_policy_spec_id,
            source_contract_skeleton_id=approval.source_contract_skeleton_id,
            source_live_order_intent_id=approval.source_live_order_intent_id,
            source_live_permission_decision_id=approval.source_live_permission_decision_id,
            source_preflight_report_id=approval.source_preflight_report_id,
            source_refs=list(approval.source_refs),
            metadata_redacted={
                "request_draft_final_approval_boundary_only": True,
                "confirmation_phrase_stored_in_journal": False,
                "approved_fields_reference_only": True,
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


def _record_id(final_approval_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{final_approval_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mt5_request_draft_final_approval_journal_{digest}"
