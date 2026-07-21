from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_contract_parameterization.builder import (
    LiveOrderContractParameterizationBuilder,
)
from src.services.trading.execution.live_order_contract_parameterization.gate import (
    LiveOrderContractParameterizationGate,
)
from src.services.trading.execution.live_order_contract_parameterization.models import (
    LiveOrderContractParameterizationBoundary,
    LiveOrderContractParameterizationJournalRecord,
    LiveOrderContractParameterizationSummary,
    LiveOrderContractParameterizationValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract_parameterization.policy import (
    LiveOrderContractParameterizationConfig,
)
from src.services.trading.execution.live_order_contract_parameterization.store import (
    LiveOrderContractParameterizationJournalStore,
)
from src.services.trading.execution.live_order_contract_parameterization.validator import (
    LiveOrderContractParameterizationValidator,
)


@dataclass
class LiveOrderContractParameterizationServiceResult:
    parameterization: LiveOrderContractParameterizationBoundary
    validation_report: LiveOrderContractParameterizationValidationReport
    journal_record: LiveOrderContractParameterizationJournalRecord | None
    summary: LiveOrderContractParameterizationSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderContractParameterizationService:
    def __init__(
        self,
        config: LiveOrderContractParameterizationConfig | None = None,
        builder: LiveOrderContractParameterizationBuilder | None = None,
        gate: LiveOrderContractParameterizationGate | None = None,
        store: LiveOrderContractParameterizationJournalStore | None = None,
        validator: LiveOrderContractParameterizationValidator | None = None,
    ):
        self.config = config or LiveOrderContractParameterizationConfig.from_config()
        self.builder = builder or LiveOrderContractParameterizationBuilder(self.config)
        self.gate = gate or LiveOrderContractParameterizationGate(self.config)
        self.store = store or LiveOrderContractParameterizationJournalStore(
            self.config.journal_path, self.config.max_read_records
        )
        self.validator = validator or LiveOrderContractParameterizationValidator(self.config)

    def run(
        self,
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
    ) -> LiveOrderContractParameterizationServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        parameterization = self.builder.build(
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
        validation_report = self.gate.validate(parameterization)
        validation_latency = (perf_counter() - validation_started) * 1000

        parameterization_validation = self.validator.validate_parameterization(parameterization)
        report_validation = self.validator.validate_report(validation_report)
        if not parameterization_validation.passed or not report_validation.passed:
            parameterization.status = "INVALID"
            parameterization.contract_validation_workflow_allowed = False
            validation_report.valid = False
            validation_report.contract_validation_workflow_allowed = False
            issues = list(dict.fromkeys(parameterization_validation.issues + report_validation.issues))
            parameterization.blockers = list(dict.fromkeys(list(parameterization.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            parameterization.payload_size_chars = len(json.dumps(parameterization.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("live_order_contract_parameterization_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(parameterization, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_order_contract_parameterization_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "live_order_contract_parameterization_journal_validation_failed:"
                    + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("live_order_contract_parameterization_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "contract_parameterization_build_latency_ms": build_latency,
            "contract_parameterization_validation_latency_ms": validation_latency,
            "contract_parameterization_journal_append_latency_ms": append_latency,
            "contract_parameterization_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderContractParameterizationServiceResult(
            parameterization,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        parameterization: LiveOrderContractParameterizationBoundary,
        validation_report: LiveOrderContractParameterizationValidationReport,
    ) -> LiveOrderContractParameterizationJournalRecord:
        created_at = now_utc_iso()
        if parameterization.status == "PARAMETERIZATION_BOUNDARY_CREATED" and validation_report.valid:
            event_type = "LIVE_ORDER_CONTRACT_PARAMETERIZATION_CREATED"
        elif parameterization.status == "DUPLICATE":
            event_type = "LIVE_ORDER_CONTRACT_PARAMETERIZATION_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_CONTRACT_PARAMETERIZATION_BLOCKED"
        record = LiveOrderContractParameterizationJournalRecord(
            journal_record_id=_record_id(parameterization.parameterization_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            parameterization_id=parameterization.parameterization_id,
            validation_report_id=validation_report.validation_report_id,
            status=parameterization.status,
            scope=parameterization.scope,
            contract_validation_workflow_allowed=validation_report.contract_validation_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            raw_values_stored=False,
            executable_order_created=False,
            contract_slots_count=validation_report.contract_slots_count,
            parameterized_slots_count=validation_report.parameterized_slots_count,
            missing_slots_count=validation_report.missing_slots_count,
            invalid_slots_count=validation_report.invalid_slots_count,
            artifact_hash=parameterization.artifact_hash,
            idempotency_key=parameterization.idempotency_key,
            source_approval_lock_id=parameterization.source_approval_lock_id,
            source_approval_lock_validation_id=parameterization.source_approval_lock_validation_id,
            source_value_proposal_id=parameterization.source_value_proposal_id,
            source_parameter_draft_id=parameterization.source_parameter_draft_id,
            source_parameter_source_boundary_id=parameterization.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=parameterization.source_parameter_policy_spec_id,
            source_contract_skeleton_id=parameterization.source_contract_skeleton_id,
            source_live_order_intent_id=parameterization.source_live_order_intent_id,
            source_live_permission_decision_id=parameterization.source_live_permission_decision_id,
            source_preflight_report_id=parameterization.source_preflight_report_id,
            source_refs=list(parameterization.source_refs),
            metadata_redacted={
                "contract_parameterization_validation_only": True,
                "raw_values_stored": False,
                "executable_order_created": False,
                "order_request_mapping_allowed": False,
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


def _record_id(parameterization_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{parameterization_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_contract_parameterization_journal_{digest}"
