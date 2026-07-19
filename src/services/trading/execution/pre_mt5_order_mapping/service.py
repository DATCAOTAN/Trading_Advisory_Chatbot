from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.pre_mt5_order_mapping.builder import (
    PreMT5OrderRequestMappingBuilder,
)
from src.services.trading.execution.pre_mt5_order_mapping.gate import (
    PreMT5OrderRequestMappingGate,
)
from src.services.trading.execution.pre_mt5_order_mapping.models import (
    PreMT5OrderRequestMappingBoundary,
    PreMT5OrderRequestMappingJournalRecord,
    PreMT5OrderRequestMappingSummary,
    PreMT5OrderRequestMappingValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.pre_mt5_order_mapping.policy import (
    PreMT5OrderRequestMappingConfig,
)
from src.services.trading.execution.pre_mt5_order_mapping.store import (
    PreMT5OrderRequestMappingJournalStore,
)
from src.services.trading.execution.pre_mt5_order_mapping.validator import (
    PreMT5OrderRequestMappingValidator,
)


@dataclass
class PreMT5OrderRequestMappingServiceResult:
    mapping_boundary: PreMT5OrderRequestMappingBoundary
    validation_report: PreMT5OrderRequestMappingValidationReport
    journal_record: PreMT5OrderRequestMappingJournalRecord | None
    summary: PreMT5OrderRequestMappingSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class PreMT5OrderRequestMappingService:
    def __init__(
        self,
        config: PreMT5OrderRequestMappingConfig | None = None,
        builder: PreMT5OrderRequestMappingBuilder | None = None,
        gate: PreMT5OrderRequestMappingGate | None = None,
        store: PreMT5OrderRequestMappingJournalStore | None = None,
        validator: PreMT5OrderRequestMappingValidator | None = None,
    ):
        self.config = config or PreMT5OrderRequestMappingConfig.from_config()
        self.builder = builder or PreMT5OrderRequestMappingBuilder(self.config)
        self.gate = gate or PreMT5OrderRequestMappingGate(self.config)
        self.store = store or PreMT5OrderRequestMappingJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or PreMT5OrderRequestMappingValidator(self.config)

    def run(
        self,
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
    ) -> PreMT5OrderRequestMappingServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()

        build_started = perf_counter()
        boundary = self.builder.build(
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

        validation_started = perf_counter()
        validation_report = self.gate.validate(boundary)
        validation_latency = (perf_counter() - validation_started) * 1000

        boundary_validation = self.validator.validate_mapping_boundary(boundary, final_review_validation)
        report_validation = self.validator.validate_report(validation_report)
        if not boundary_validation.passed or not report_validation.passed:
            boundary.status = "INVALID"
            boundary.mt5_dry_run_payload_validation_workflow_allowed = False
            validation_report.valid = False
            validation_report.mt5_dry_run_payload_validation_workflow_allowed = False
            issues = list(dict.fromkeys(boundary_validation.issues + report_validation.issues))
            boundary.blockers = list(dict.fromkeys(list(boundary.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            boundary.payload_size_chars = len(json.dumps(boundary.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("pre_mt5_mapping_validation_failed:" + ",".join(issues))

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
                    warning_parts.append(f"pre_mt5_mapping_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("pre_mt5_mapping_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("pre_mt5_mapping_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "pre_mt5_mapping_build_latency_ms": build_latency,
            "pre_mt5_mapping_validation_latency_ms": validation_latency,
            "pre_mt5_mapping_journal_append_latency_ms": append_latency,
            "pre_mt5_mapping_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return PreMT5OrderRequestMappingServiceResult(
            boundary,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        boundary: PreMT5OrderRequestMappingBoundary,
        validation_report: PreMT5OrderRequestMappingValidationReport,
    ) -> PreMT5OrderRequestMappingJournalRecord:
        created_at = now_utc_iso()
        if boundary.status == "MAPPING_BOUNDARY_CREATED" and validation_report.valid:
            event_type = "PRE_MT5_MAPPING_BOUNDARY_CREATED"
        elif boundary.status == "DUPLICATE":
            event_type = "PRE_MT5_MAPPING_DUPLICATE_DETECTED"
        else:
            event_type = "PRE_MT5_MAPPING_BLOCKED"
        record = PreMT5OrderRequestMappingJournalRecord(
            journal_record_id=_record_id(boundary.mapping_boundary_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            mapping_boundary_id=boundary.mapping_boundary_id,
            validation_report_id=validation_report.validation_report_id,
            status=boundary.status,
            scope=boundary.scope,
            mt5_dry_run_payload_validation_workflow_allowed=validation_report.mt5_dry_run_payload_validation_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            mapping_slots_count=validation_report.mapping_slots_count,
            mapped_slots_count=validation_report.mapped_slots_count,
            missing_slots_count=validation_report.missing_slots_count,
            invalid_slots_count=validation_report.invalid_slots_count,
            artifact_hash=boundary.artifact_hash,
            idempotency_key=boundary.idempotency_key,
            source_final_review_id=boundary.source_final_review_id,
            source_final_review_validation_id=boundary.source_final_review_validation_id,
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
                "pre_mt5_mapping_boundary_only": True,
                "schema_only_mapping_slots": True,
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
                "order_sent": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(mapping_boundary_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{mapping_boundary_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"pre_mt5_mapping_journal_{digest}"
