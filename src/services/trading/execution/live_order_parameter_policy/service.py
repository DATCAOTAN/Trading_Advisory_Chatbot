from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_parameter_policy.builder import LiveOrderParameterPolicySpecBuilder
from src.services.trading.execution.live_order_parameter_policy.gate import LiveOrderParameterPolicyGate
from src.services.trading.execution.live_order_parameter_policy.models import (
    LiveOrderParameterPolicyJournalRecord,
    LiveOrderParameterPolicySpec,
    LiveOrderParameterPolicySummary,
    LiveOrderParameterPolicyValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_parameter_policy.policy import LiveOrderParameterPolicyConfig
from src.services.trading.execution.live_order_parameter_policy.store import LiveOrderParameterPolicyJournalStore
from src.services.trading.execution.live_order_parameter_policy.validator import LiveOrderParameterPolicyValidator


@dataclass
class LiveOrderParameterPolicyServiceResult:
    policy_spec: LiveOrderParameterPolicySpec
    validation_report: LiveOrderParameterPolicyValidationReport
    journal_record: LiveOrderParameterPolicyJournalRecord | None
    summary: LiveOrderParameterPolicySummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderParameterPolicyService:
    def __init__(
        self,
        config: LiveOrderParameterPolicyConfig | None = None,
        builder: LiveOrderParameterPolicySpecBuilder | None = None,
        gate: LiveOrderParameterPolicyGate | None = None,
        store: LiveOrderParameterPolicyJournalStore | None = None,
        validator: LiveOrderParameterPolicyValidator | None = None,
    ):
        self.config = config or LiveOrderParameterPolicyConfig.from_config()
        self.builder = builder or LiveOrderParameterPolicySpecBuilder(self.config)
        self.gate = gate or LiveOrderParameterPolicyGate(self.config)
        self.store = store or LiveOrderParameterPolicyJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or LiveOrderParameterPolicyValidator(self.config)

    def run(
        self,
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
    ) -> LiveOrderParameterPolicyServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        spec = self.builder.build(
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
        validation_report = self.gate.validate(spec)
        validation_latency = (perf_counter() - validation_started) * 1000

        spec_validation = self.validator.validate_spec(spec)
        report_validation = self.validator.validate_report(validation_report)
        if not spec_validation.passed or not report_validation.passed:
            spec.status = "INVALID"
            spec.parameter_source_boundary_allowed = False
            validation_report.valid = False
            validation_report.parameter_source_boundary_allowed = False
            issues = list(dict.fromkeys(spec_validation.issues + report_validation.issues))
            spec.blockers = list(dict.fromkeys(list(spec.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            spec.payload_size_chars = len(json.dumps(spec.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("live_order_parameter_policy_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(spec, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_order_parameter_policy_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_order_parameter_policy_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_order_parameter_policy_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "parameter_policy_spec_build_latency_ms": build_latency,
            "parameter_policy_validation_latency_ms": validation_latency,
            "parameter_policy_journal_append_latency_ms": append_latency,
            "parameter_policy_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderParameterPolicyServiceResult(
            spec,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        spec: LiveOrderParameterPolicySpec,
        validation_report: LiveOrderParameterPolicyValidationReport,
    ) -> LiveOrderParameterPolicyJournalRecord:
        created_at = now_utc_iso()
        if spec.status == "POLICY_VALIDATED" and validation_report.valid:
            event_type = "LIVE_ORDER_PARAMETER_POLICY_VALIDATED"
        elif spec.status == "DUPLICATE":
            event_type = "LIVE_ORDER_PARAMETER_POLICY_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_PARAMETER_POLICY_BLOCKED"
        record = LiveOrderParameterPolicyJournalRecord(
            journal_record_id=_record_id(spec.policy_spec_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            policy_spec_id=spec.policy_spec_id,
            validation_report_id=validation_report.validation_report_id,
            status=spec.status,
            scope=spec.scope,
            parameter_source_boundary_allowed=validation_report.parameter_source_boundary_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            policy_groups_count=validation_report.policy_groups_count,
            policy_rules_count=validation_report.policy_rules_count,
            unresolved_groups_count=validation_report.unresolved_groups_count,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            artifact_hash=spec.artifact_hash,
            idempotency_key=spec.idempotency_key,
            source_contract_skeleton_id=spec.source_contract_skeleton_id,
            source_contract_skeleton_validation_id=spec.source_contract_skeleton_validation_id,
            source_live_order_intent_id=spec.source_live_order_intent_id,
            source_live_permission_decision_id=spec.source_live_permission_decision_id,
            source_preflight_report_id=spec.source_preflight_report_id,
            source_refs=list(spec.source_refs),
            metadata_redacted={
                "parameter_policy_only": True,
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


def _record_id(policy_spec_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{policy_spec_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_parameter_policy_journal_{digest}"
