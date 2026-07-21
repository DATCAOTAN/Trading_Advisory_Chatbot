from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_value_approval_lock.builder import HumanValueApprovalLockBuilder
from src.services.trading.execution.live_value_approval_lock.gate import HumanValueApprovalLockGate
from src.services.trading.execution.live_value_approval_lock.models import (
    HumanValueApprovalLock,
    HumanValueApprovalLockJournalRecord,
    HumanValueApprovalLockSummary,
    HumanValueApprovalLockValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_value_approval_lock.policy import HumanValueApprovalLockConfig
from src.services.trading.execution.live_value_approval_lock.store import HumanValueApprovalLockJournalStore
from src.services.trading.execution.live_value_approval_lock.validator import HumanValueApprovalLockValidator


@dataclass
class HumanValueApprovalLockServiceResult:
    approval_lock: HumanValueApprovalLock
    validation_report: HumanValueApprovalLockValidationReport
    journal_record: HumanValueApprovalLockJournalRecord | None
    summary: HumanValueApprovalLockSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class HumanValueApprovalLockService:
    def __init__(
        self,
        config: HumanValueApprovalLockConfig | None = None,
        builder: HumanValueApprovalLockBuilder | None = None,
        gate: HumanValueApprovalLockGate | None = None,
        store: HumanValueApprovalLockJournalStore | None = None,
        validator: HumanValueApprovalLockValidator | None = None,
    ):
        self.config = config or HumanValueApprovalLockConfig.from_config()
        self.builder = builder or HumanValueApprovalLockBuilder(self.config)
        self.gate = gate or HumanValueApprovalLockGate(self.config)
        self.store = store or HumanValueApprovalLockJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or HumanValueApprovalLockValidator(self.config)

    def run(
        self,
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
        approved_semantic_values=None,
    ) -> HumanValueApprovalLockServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        existing_confirmation_ids = self.store.confirmation_ids() if self.config.journal_enabled else set()
        build_started = perf_counter()
        approval_lock = self.builder.build(
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
            existing_confirmation_ids=existing_confirmation_ids,
            approved_semantic_values=approved_semantic_values,
        )
        build_latency = (perf_counter() - build_started) * 1000
        validation_started = perf_counter()
        validation_report = self.gate.validate(approval_lock)
        validation_latency = (perf_counter() - validation_started) * 1000

        lock_validation = self.validator.validate_lock(approval_lock)
        report_validation = self.validator.validate_report(validation_report)
        if not lock_validation.passed or not report_validation.passed:
            approval_lock.status = "INVALID"
            approval_lock.contract_parameterization_workflow_allowed = False
            validation_report.valid = False
            validation_report.contract_parameterization_workflow_allowed = False
            issues = list(dict.fromkeys(lock_validation.issues + report_validation.issues))
            approval_lock.blockers = list(dict.fromkeys(list(approval_lock.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            approval_lock.payload_size_chars = len(json.dumps(approval_lock.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("human_value_approval_lock_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(approval_lock, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"human_value_approval_lock_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("human_value_approval_lock_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("human_value_approval_lock_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "human_value_approval_lock_build_latency_ms": build_latency,
            "human_value_approval_lock_validation_latency_ms": validation_latency,
            "human_value_approval_lock_journal_append_latency_ms": append_latency,
            "human_value_approval_lock_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return HumanValueApprovalLockServiceResult(
            approval_lock,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        approval_lock: HumanValueApprovalLock,
        validation_report: HumanValueApprovalLockValidationReport,
    ) -> HumanValueApprovalLockJournalRecord:
        created_at = now_utc_iso()
        if approval_lock.status == "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION" and validation_report.valid:
            event_type = "HUMAN_VALUE_APPROVAL_LOCK_CREATED"
        elif approval_lock.status == "DUPLICATE":
            event_type = "HUMAN_VALUE_APPROVAL_LOCK_DUPLICATE_DETECTED"
        elif approval_lock.status == "REJECTED":
            event_type = "HUMAN_VALUE_APPROVAL_LOCK_REJECTED"
        else:
            event_type = "HUMAN_VALUE_APPROVAL_LOCK_BLOCKED"
        record = HumanValueApprovalLockJournalRecord(
            journal_record_id=_record_id(approval_lock.approval_lock_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            approval_lock_id=approval_lock.approval_lock_id,
            validation_report_id=validation_report.validation_report_id,
            status=approval_lock.status,
            scope=approval_lock.scope,
            contract_parameterization_workflow_allowed=validation_report.contract_parameterization_workflow_allowed,
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
            raw_values_stored=False,
            executable_order_created=False,
            confirmation_phrase_valid=validation_report.confirmation_phrase_valid,
            slot_locks_count=validation_report.slot_locks_count,
            locked_slots_count=validation_report.locked_slots_count,
            rejected_slots_count=0,
            missing_slots_count=validation_report.missing_slots_count,
            artifact_hash=approval_lock.artifact_hash,
            idempotency_key=approval_lock.idempotency_key,
            source_value_proposal_id=approval_lock.source_value_proposal_id,
            source_value_proposal_validation_id=approval_lock.source_value_proposal_validation_id,
            source_parameter_draft_id=approval_lock.source_parameter_draft_id,
            source_parameter_source_boundary_id=approval_lock.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=approval_lock.source_parameter_policy_spec_id,
            source_contract_skeleton_id=approval_lock.source_contract_skeleton_id,
            source_live_order_intent_id=approval_lock.source_live_order_intent_id,
            source_live_permission_decision_id=approval_lock.source_live_permission_decision_id,
            source_preflight_report_id=approval_lock.source_preflight_report_id,
            source_refs=list(approval_lock.source_refs),
            metadata_redacted={
                "approval_lock_parameterization_only": True,
                "confirmation_id": approval_lock.confirmation_id,
                "confirmation_phrase_valid": validation_report.confirmation_phrase_valid,
                "raw_values_stored": False,
                "executable_order_created": False,
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


def _record_id(approval_lock_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{approval_lock_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"human_value_approval_lock_journal_{digest}"
