from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_request_dict_dry_run_builder.builder import (
    MT5RequestDictDryRunBuilder,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.gate import (
    MT5RequestDictDryRunBuilderGate,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.models import (
    MT5RequestDictDryRunBuilderBoundary,
    MT5RequestDictDryRunBuilderJournalRecord,
    MT5RequestDictDryRunBuilderSummary,
    MT5RequestDictDryRunBuilderValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.policy import (
    MT5RequestDictDryRunBuilderConfig,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.store import (
    MT5RequestDictDryRunBuilderJournalStore,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.validator import (
    MT5RequestDictDryRunBuilderValidator,
)


@dataclass
class MT5RequestDictDryRunBuilderServiceResult:
    boundary: MT5RequestDictDryRunBuilderBoundary
    validation_report: MT5RequestDictDryRunBuilderValidationReport
    journal_record: MT5RequestDictDryRunBuilderJournalRecord | None
    summary: MT5RequestDictDryRunBuilderSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class MT5RequestDictDryRunBuilderService:
    def __init__(
        self,
        config: MT5RequestDictDryRunBuilderConfig | None = None,
        builder: MT5RequestDictDryRunBuilder | None = None,
        gate: MT5RequestDictDryRunBuilderGate | None = None,
        store: MT5RequestDictDryRunBuilderJournalStore | None = None,
        validator: MT5RequestDictDryRunBuilderValidator | None = None,
    ):
        self.config = config or MT5RequestDictDryRunBuilderConfig.from_config()
        self.builder = builder or MT5RequestDictDryRunBuilder(self.config)
        self.gate = gate or MT5RequestDictDryRunBuilderGate(self.config)
        self.store = store or MT5RequestDictDryRunBuilderJournalStore(
            self.config.journal_path,
            self.config.max_read_records,
        )
        self.validator = validator or MT5RequestDictDryRunBuilderValidator(self.config)

    def run(
        self,
        draft_final_approval,
        draft_final_approval_validation_report,
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
        current_time=None,
    ) -> MT5RequestDictDryRunBuilderServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()

        build_started = perf_counter()
        boundary = self.builder.build(
            draft_final_approval,
            draft_final_approval_validation_report,
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
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        build_latency = (perf_counter() - build_started) * 1000

        report_started = perf_counter()
        validation_report = self.gate.validate(boundary)
        report_latency = (perf_counter() - report_started) * 1000

        object_validation = self.validator.validate_boundary(boundary, draft_final_approval_validation_report)
        report_validation = self.validator.validate_report(validation_report)
        if not object_validation.passed or not report_validation.passed:
            boundary.status = "INVALID" if boundary.status not in {"EXPIRED", "DUPLICATE"} else boundary.status
            boundary.mt5_request_dict_final_validation_workflow_allowed = False
            validation_report.valid = False
            validation_report.mt5_request_dict_final_validation_workflow_allowed = False
            issues = list(dict.fromkeys(object_validation.issues + report_validation.issues))
            boundary.blockers = list(dict.fromkeys(list(boundary.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            boundary.payload_size_chars = len(json.dumps(boundary.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("mt5_request_dict_dry_run_builder_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(boundary, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"mt5_request_dict_dry_run_builder_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "mt5_request_dict_dry_run_builder_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("mt5_request_dict_dry_run_builder_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "mt5_request_dict_dry_run_builder_build_latency_ms": build_latency,
            "mt5_request_dict_dry_run_builder_report_latency_ms": report_latency,
            "mt5_request_dict_dry_run_builder_journal_append_latency_ms": append_latency,
            "mt5_request_dict_dry_run_builder_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return MT5RequestDictDryRunBuilderServiceResult(
            boundary=boundary,
            validation_report=validation_report,
            journal_record=record,
            summary=summary,
            warning=";".join(warning_parts),
            timings_ms=timings,
        )

    def _build_record(
        self,
        boundary: MT5RequestDictDryRunBuilderBoundary,
        report: MT5RequestDictDryRunBuilderValidationReport,
    ) -> MT5RequestDictDryRunBuilderJournalRecord:
        created_at = now_utc_iso()
        if boundary.status == "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED" and report.valid:
            event_type = "MT5_REQUEST_DICT_DRY_RUN_BOUNDARY_CREATED"
        elif boundary.status == "DUPLICATE":
            event_type = "MT5_REQUEST_DICT_DRY_RUN_BOUNDARY_DUPLICATE_DETECTED"
        else:
            event_type = "MT5_REQUEST_DICT_DRY_RUN_BOUNDARY_BLOCKED"
        record = MT5RequestDictDryRunBuilderJournalRecord(
            journal_record_id=_record_id(boundary.dry_run_request_dict_id, report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            dry_run_request_dict_id=boundary.dry_run_request_dict_id,
            validation_report_id=report.validation_report_id,
            status=boundary.status,
            scope=boundary.scope,
            mt5_request_dict_final_validation_workflow_allowed=report.mt5_request_dict_final_validation_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            real_mt5_payload_created=False,
            broker_submittable_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            dry_run_fields_count=report.dry_run_fields_count,
            created_dry_run_fields_count=report.created_dry_run_fields_count,
            missing_dry_run_fields_count=report.missing_dry_run_fields_count,
            invalid_dry_run_fields_count=report.invalid_dry_run_fields_count,
            artifact_hash=boundary.artifact_hash,
            idempotency_key=boundary.idempotency_key,
            source_draft_final_approval_id=boundary.source_draft_final_approval_id,
            source_draft_final_approval_validation_report_id=boundary.source_draft_final_approval_validation_report_id,
            source_request_draft_id=boundary.source_request_draft_id,
            source_request_draft_validation_report_id=boundary.source_request_draft_validation_report_id,
            source_dry_run_validation_id=boundary.source_dry_run_validation_id,
            source_dry_run_validation_report_id=boundary.source_dry_run_validation_report_id,
            source_pre_mt5_mapping_id=boundary.source_pre_mt5_mapping_id,
            source_pre_mt5_mapping_validation_id=boundary.source_pre_mt5_mapping_validation_id,
            source_final_review_id=boundary.source_final_review_id,
            source_parameterization_id=boundary.source_parameterization_id,
            source_approval_lock_id=boundary.source_approval_lock_id,
            source_value_proposal_id=boundary.source_value_proposal_id,
            source_parameter_draft_id=boundary.source_parameter_draft_id,
            source_parameter_source_boundary_id=boundary.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=boundary.source_parameter_policy_spec_id,
            source_contract_skeleton_id=boundary.source_contract_skeleton_id,
            source_live_order_intent_id=boundary.source_live_order_intent_id,
            source_live_permission_decision_id=boundary.source_live_permission_decision_id,
            source_preflight_report_id=boundary.source_preflight_report_id,
            source_refs=list(boundary.source_refs),
            metadata_redacted={
                "request_dict_dry_run_builder_boundary_only": True,
                "dry_run_key_labels_schema_only": True,
                "concrete_value_created": False,
                "raw_values_stored": False,
                "executable_order_created": False,
                "broker_mapping_created": False,
                "broker_submission_created": False,
                "broker_submittable_request_dict_created": False,
                "order_request_mapping_allowed": False,
                "order_contract_ready": False,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "executable": False,
                "real_mt5_payload_created": False,
                "mt5_constants_used": False,
                "order_sent": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(boundary_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{boundary_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mt5_request_dict_dry_run_builder_journal_{digest}"
