from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_parameter_source.builder import LiveOrderParameterSourceBoundaryBuilder
from src.services.trading.execution.live_order_parameter_source.gate import LiveOrderParameterSourceBoundaryGate
from src.services.trading.execution.live_order_parameter_source.models import (
    LiveOrderParameterSourceBoundary,
    LiveOrderParameterSourceJournalRecord,
    LiveOrderParameterSourceSummary,
    LiveOrderParameterSourceValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_parameter_source.policy import LiveOrderParameterSourceBoundaryConfig
from src.services.trading.execution.live_order_parameter_source.store import LiveOrderParameterSourceJournalStore
from src.services.trading.execution.live_order_parameter_source.validator import LiveOrderParameterSourceBoundaryValidator


@dataclass
class LiveOrderParameterSourceBoundaryServiceResult:
    boundary: LiveOrderParameterSourceBoundary
    validation_report: LiveOrderParameterSourceValidationReport
    journal_record: LiveOrderParameterSourceJournalRecord | None
    summary: LiveOrderParameterSourceSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderParameterSourceBoundaryService:
    def __init__(
        self,
        config: LiveOrderParameterSourceBoundaryConfig | None = None,
        builder: LiveOrderParameterSourceBoundaryBuilder | None = None,
        gate: LiveOrderParameterSourceBoundaryGate | None = None,
        store: LiveOrderParameterSourceJournalStore | None = None,
        validator: LiveOrderParameterSourceBoundaryValidator | None = None,
    ):
        self.config = config or LiveOrderParameterSourceBoundaryConfig.from_config()
        self.builder = builder or LiveOrderParameterSourceBoundaryBuilder(self.config)
        self.gate = gate or LiveOrderParameterSourceBoundaryGate(self.config)
        self.store = store or LiveOrderParameterSourceJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or LiveOrderParameterSourceBoundaryValidator(self.config)

    def run(
        self,
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
    ) -> LiveOrderParameterSourceBoundaryServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        boundary = self.builder.build(
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

        boundary_validation = self.validator.validate_boundary(boundary)
        report_validation = self.validator.validate_report(validation_report)
        if not boundary_validation.passed or not report_validation.passed:
            boundary.status = "INVALID"
            boundary.human_reviewed_parameter_draft_allowed = False
            validation_report.valid = False
            validation_report.human_reviewed_parameter_draft_allowed = False
            issues = list(dict.fromkeys(boundary_validation.issues + report_validation.issues))
            boundary.blockers = list(dict.fromkeys(list(boundary.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            boundary.payload_size_chars = len(json.dumps(boundary.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("live_order_parameter_source_boundary_validation_failed:" + ",".join(issues))

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
                    warning_parts.append(f"live_order_parameter_source_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_order_parameter_source_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_order_parameter_source_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "parameter_source_boundary_build_latency_ms": build_latency,
            "parameter_source_boundary_validation_latency_ms": validation_latency,
            "parameter_source_boundary_journal_append_latency_ms": append_latency,
            "parameter_source_boundary_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderParameterSourceBoundaryServiceResult(
            boundary,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        boundary: LiveOrderParameterSourceBoundary,
        validation_report: LiveOrderParameterSourceValidationReport,
    ) -> LiveOrderParameterSourceJournalRecord:
        created_at = now_utc_iso()
        if boundary.status == "SOURCE_BOUNDARY_VALIDATED" and validation_report.valid:
            event_type = "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_VALIDATED"
        elif boundary.status == "DUPLICATE":
            event_type = "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_BLOCKED"
        record = LiveOrderParameterSourceJournalRecord(
            journal_record_id=_record_id(boundary.boundary_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            boundary_id=boundary.boundary_id,
            validation_report_id=validation_report.validation_report_id,
            status=boundary.status,
            scope=boundary.scope,
            human_reviewed_parameter_draft_allowed=validation_report.human_reviewed_parameter_draft_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            source_candidates_count=validation_report.source_candidates_count,
            required_sources_count=validation_report.required_sources_count,
            missing_sources_count=validation_report.missing_sources_count,
            rejected_sources_count=validation_report.rejected_sources_count,
            artifact_hash=boundary.artifact_hash,
            idempotency_key=boundary.idempotency_key,
            source_parameter_policy_spec_id=boundary.source_parameter_policy_spec_id,
            source_parameter_policy_validation_id=boundary.source_parameter_policy_validation_id,
            source_contract_skeleton_id=boundary.source_contract_skeleton_id,
            source_live_order_intent_id=boundary.source_live_order_intent_id,
            source_live_permission_decision_id=boundary.source_live_permission_decision_id,
            source_preflight_report_id=boundary.source_preflight_report_id,
            source_refs=list(boundary.source_refs),
            metadata_redacted={
                "parameter_source_boundary_only": True,
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


def _record_id(boundary_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{boundary_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_parameter_source_journal_{digest}"
