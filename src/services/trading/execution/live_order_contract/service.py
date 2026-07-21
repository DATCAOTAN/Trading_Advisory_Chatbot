from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_contract.builder import LiveOrderContractSkeletonBuilder
from src.services.trading.execution.live_order_contract.gate import LiveOrderContractSkeletonGate
from src.services.trading.execution.live_order_contract.models import (
    LiveOrderContractSkeleton,
    LiveOrderContractSkeletonJournalRecord,
    LiveOrderContractSkeletonSummary,
    LiveOrderContractSkeletonValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract.policy import LiveOrderContractSkeletonPolicy
from src.services.trading.execution.live_order_contract.store import LiveOrderContractSkeletonJournalStore
from src.services.trading.execution.live_order_contract.validator import LiveOrderContractSkeletonValidator


@dataclass
class LiveOrderContractSkeletonServiceResult:
    skeleton: LiveOrderContractSkeleton
    validation_report: LiveOrderContractSkeletonValidationReport
    journal_record: LiveOrderContractSkeletonJournalRecord | None
    summary: LiveOrderContractSkeletonSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderContractSkeletonService:
    def __init__(
        self,
        policy: LiveOrderContractSkeletonPolicy | None = None,
        builder: LiveOrderContractSkeletonBuilder | None = None,
        gate: LiveOrderContractSkeletonGate | None = None,
        store: LiveOrderContractSkeletonJournalStore | None = None,
        validator: LiveOrderContractSkeletonValidator | None = None,
    ):
        self.policy = policy or LiveOrderContractSkeletonPolicy.from_config()
        self.builder = builder or LiveOrderContractSkeletonBuilder(self.policy)
        self.gate = gate or LiveOrderContractSkeletonGate(self.policy)
        self.store = store or LiveOrderContractSkeletonJournalStore(self.policy.journal_path, self.policy.max_read_records)
        self.validator = validator or LiveOrderContractSkeletonValidator(self.policy)

    def run(
        self,
        live_order_intent,
        live_order_intent_validation,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time=None,
    ) -> LiveOrderContractSkeletonServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.policy.journal_enabled else set()
        skeleton_started = perf_counter()
        skeleton = self.builder.build(
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
        skeleton_latency = (perf_counter() - skeleton_started) * 1000
        validation_started = perf_counter()
        validation_report = self.gate.validate(skeleton)
        validation_latency = (perf_counter() - validation_started) * 1000

        skeleton_validation = self.validator.validate_skeleton(skeleton)
        report_validation = self.validator.validate_report(validation_report)
        if not skeleton_validation.passed or not report_validation.passed:
            skeleton.status = "INVALID"
            skeleton.contract_parameter_validation_allowed = False
            validation_report.valid = False
            validation_report.contract_parameter_validation_allowed = False
            issues = list(dict.fromkeys(skeleton_validation.issues + report_validation.issues))
            skeleton.blockers = list(dict.fromkeys(list(skeleton.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            skeleton.payload_size_chars = len(json.dumps(skeleton.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("live_order_contract_skeleton_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.policy.journal_enabled:
            record = self._build_record(skeleton, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_order_contract_skeleton_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append(
                    "live_order_contract_skeleton_journal_validation_failed:" + ",".join(record_validation.issues)
                )
        else:
            warning_parts.append("live_order_contract_skeleton_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "live_order_contract_skeleton_build_latency_ms": skeleton_latency,
            "live_order_contract_skeleton_validation_latency_ms": validation_latency,
            "live_order_contract_skeleton_journal_append_latency_ms": append_latency,
            "live_order_contract_skeleton_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderContractSkeletonServiceResult(
            skeleton,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        skeleton: LiveOrderContractSkeleton,
        validation_report: LiveOrderContractSkeletonValidationReport,
    ) -> LiveOrderContractSkeletonJournalRecord:
        created_at = now_utc_iso()
        if skeleton.status == "SKELETON_CREATED" and validation_report.valid:
            event_type = "LIVE_ORDER_CONTRACT_SKELETON_CREATED"
        elif skeleton.status == "DUPLICATE":
            event_type = "LIVE_ORDER_CONTRACT_SKELETON_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_CONTRACT_SKELETON_BLOCKED"
        record = LiveOrderContractSkeletonJournalRecord(
            journal_record_id=_record_id(skeleton.contract_skeleton_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            contract_skeleton_id=skeleton.contract_skeleton_id,
            validation_report_id=validation_report.validation_report_id,
            status=skeleton.status,
            scope=skeleton.scope,
            contract_parameter_validation_allowed=validation_report.contract_parameter_validation_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            artifact_hash=skeleton.artifact_hash,
            idempotency_key=skeleton.idempotency_key,
            source_live_order_intent_id=skeleton.source_live_order_intent_id,
            source_live_order_intent_validation_id=skeleton.source_live_order_intent_validation_id,
            source_live_permission_decision_id=skeleton.source_live_permission_decision_id,
            source_preflight_report_id=skeleton.source_preflight_report_id,
            source_proposal_draft_id=skeleton.source_proposal_draft_id,
            source_simulated_contract_id=skeleton.source_simulated_contract_id,
            source_refs=list(skeleton.source_refs),
            metadata_redacted={
                "parameter_validation_preparation_only": True,
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


def _record_id(contract_skeleton_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{contract_skeleton_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_contract_skeleton_journal_{digest}"
