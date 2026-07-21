from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_dry_run_payload_validator.builder import (
    MT5OrderRequestDryRunPayloadValidationBuilder,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.gate import (
    MT5OrderRequestDryRunPayloadValidationGate,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.models import (
    MT5DryRunPayloadValidationSummary,
    MT5OrderRequestDryRunPayloadValidation,
    MT5OrderRequestDryRunPayloadValidationJournalRecord,
    MT5OrderRequestDryRunPayloadValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.policy import (
    MT5DryRunPayloadValidationConfig,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.store import (
    MT5DryRunPayloadValidationJournalStore,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.validator import (
    MT5OrderRequestDryRunPayloadValidator,
)


@dataclass
class MT5OrderRequestDryRunPayloadValidationServiceResult:
    dry_run_validation: MT5OrderRequestDryRunPayloadValidation
    validation_report: MT5OrderRequestDryRunPayloadValidationReport
    journal_record: MT5OrderRequestDryRunPayloadValidationJournalRecord | None
    summary: MT5DryRunPayloadValidationSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class MT5OrderRequestDryRunPayloadValidationService:
    def __init__(
        self,
        config: MT5DryRunPayloadValidationConfig | None = None,
        builder: MT5OrderRequestDryRunPayloadValidationBuilder | None = None,
        gate: MT5OrderRequestDryRunPayloadValidationGate | None = None,
        store: MT5DryRunPayloadValidationJournalStore | None = None,
        validator: MT5OrderRequestDryRunPayloadValidator | None = None,
    ):
        self.config = config or MT5DryRunPayloadValidationConfig.from_config()
        self.builder = builder or MT5OrderRequestDryRunPayloadValidationBuilder(self.config)
        self.gate = gate or MT5OrderRequestDryRunPayloadValidationGate(self.config)
        self.store = store or MT5DryRunPayloadValidationJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or MT5OrderRequestDryRunPayloadValidator(self.config)

    def run(
        self,
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
    ) -> MT5OrderRequestDryRunPayloadValidationServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()

        build_started = perf_counter()
        dry_run_validation = self.builder.build(
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
        validation_report = self.gate.validate(dry_run_validation)
        report_latency = (perf_counter() - report_started) * 1000

        object_validation = self.validator.validate_dry_run_validation(dry_run_validation, pre_mt5_mapping_validation)
        report_validation = self.validator.validate_report(validation_report)
        if not object_validation.passed or not report_validation.passed:
            dry_run_validation.status = "INVALID"
            dry_run_validation.mt5_request_draft_workflow_allowed = False
            validation_report.valid = False
            validation_report.mt5_request_draft_workflow_allowed = False
            issues = list(dict.fromkeys(object_validation.issues + report_validation.issues))
            dry_run_validation.blockers = list(dict.fromkeys(list(dry_run_validation.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            dry_run_validation.payload_size_chars = len(json.dumps(dry_run_validation.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("mt5_dry_run_payload_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(dry_run_validation, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"mt5_dry_run_payload_validation_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "mt5_dry_run_payload_validation_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("mt5_dry_run_payload_validation_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "mt5_dry_run_payload_validation_build_latency_ms": build_latency,
            "mt5_dry_run_payload_validation_report_latency_ms": report_latency,
            "mt5_dry_run_payload_validation_journal_append_latency_ms": append_latency,
            "mt5_dry_run_payload_validation_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return MT5OrderRequestDryRunPayloadValidationServiceResult(
            dry_run_validation,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        validation: MT5OrderRequestDryRunPayloadValidation,
        report: MT5OrderRequestDryRunPayloadValidationReport,
    ) -> MT5OrderRequestDryRunPayloadValidationJournalRecord:
        created_at = now_utc_iso()
        if validation.status == "DRY_RUN_PAYLOAD_VALIDATED" and report.valid:
            event_type = "MT5_DRY_RUN_PAYLOAD_VALIDATED"
        elif validation.status == "DUPLICATE":
            event_type = "MT5_DRY_RUN_PAYLOAD_VALIDATION_DUPLICATE_DETECTED"
        else:
            event_type = "MT5_DRY_RUN_PAYLOAD_VALIDATION_BLOCKED"
        record = MT5OrderRequestDryRunPayloadValidationJournalRecord(
            journal_record_id=_record_id(validation.dry_run_validation_id, report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            dry_run_validation_id=validation.dry_run_validation_id,
            validation_report_id=report.validation_report_id,
            status=validation.status,
            scope=validation.scope,
            mt5_request_draft_workflow_allowed=report.mt5_request_draft_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            mt5_constants_used=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            field_validations_count=report.field_validations_count,
            validated_fields_count=report.validated_fields_count,
            missing_fields_count=report.missing_fields_count,
            invalid_fields_count=report.invalid_fields_count,
            artifact_hash=validation.artifact_hash,
            idempotency_key=validation.idempotency_key,
            source_pre_mt5_mapping_id=validation.source_pre_mt5_mapping_id,
            source_pre_mt5_mapping_validation_id=validation.source_pre_mt5_mapping_validation_id,
            source_final_review_id=validation.source_final_review_id,
            source_parameterization_id=validation.source_parameterization_id,
            source_approval_lock_id=validation.source_approval_lock_id,
            source_value_proposal_id=validation.source_value_proposal_id,
            source_parameter_draft_id=validation.source_parameter_draft_id,
            source_parameter_source_boundary_id=validation.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=validation.source_parameter_policy_spec_id,
            source_contract_skeleton_id=validation.source_contract_skeleton_id,
            source_live_order_intent_id=validation.source_live_order_intent_id,
            source_live_permission_decision_id=validation.source_live_permission_decision_id,
            source_preflight_report_id=validation.source_preflight_report_id,
            source_refs=list(validation.source_refs),
            metadata_redacted={
                "mt5_dry_run_payload_shape_only": True,
                "raw_values_stored": False,
                "executable_order_created": False,
                "broker_mapping_created": False,
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


def _record_id(dry_run_validation_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{dry_run_validation_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mt5_dry_run_payload_validation_journal_{digest}"
