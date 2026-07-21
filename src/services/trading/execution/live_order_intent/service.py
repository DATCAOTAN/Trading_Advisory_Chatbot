from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_intent.builder import LiveOrderIntentBuilder
from src.services.trading.execution.live_order_intent.gate import LiveOrderIntentGate
from src.services.trading.execution.live_order_intent.models import (
    LiveOrderIntent,
    LiveOrderIntentJournalRecord,
    LiveOrderIntentSummary,
    LiveOrderIntentValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_intent.policy import LiveOrderIntentPolicy
from src.services.trading.execution.live_order_intent.store import LiveOrderIntentJournalStore
from src.services.trading.execution.live_order_intent.validator import LiveOrderIntentValidator


@dataclass
class LiveOrderIntentServiceResult:
    intent: LiveOrderIntent
    validation_report: LiveOrderIntentValidationReport
    journal_record: LiveOrderIntentJournalRecord | None
    summary: LiveOrderIntentSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderIntentService:
    def __init__(
        self,
        policy: LiveOrderIntentPolicy | None = None,
        builder: LiveOrderIntentBuilder | None = None,
        gate: LiveOrderIntentGate | None = None,
        store: LiveOrderIntentJournalStore | None = None,
        validator: LiveOrderIntentValidator | None = None,
    ):
        self.policy = policy or LiveOrderIntentPolicy.from_config()
        self.builder = builder or LiveOrderIntentBuilder(self.policy)
        self.gate = gate or LiveOrderIntentGate(self.policy)
        self.store = store or LiveOrderIntentJournalStore(self.policy.journal_path, self.policy.max_read_records)
        self.validator = validator or LiveOrderIntentValidator(self.policy)

    def run(
        self,
        permission_intent,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time=None,
    ) -> LiveOrderIntentServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.policy.journal_enabled else set()
        intent_started = perf_counter()
        intent = self.builder.build(
            permission_intent,
            permission_decision,
            preflight_report,
            proposal_draft,
            simulated_contract,
            simulated_receipt=simulated_receipt,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        intent_latency = (perf_counter() - intent_started) * 1000
        validation_started = perf_counter()
        validation_report = self.gate.validate(intent)
        validation_latency = (perf_counter() - validation_started) * 1000

        intent_validation = self.validator.validate_intent(intent)
        report_validation = self.validator.validate_report(validation_report)
        if not intent_validation.passed or not report_validation.passed:
            intent.status = "INVALID"
            intent.order_contract_workflow_allowed = False
            validation_report.valid = False
            validation_report.order_contract_workflow_allowed = False
            issues = list(dict.fromkeys(intent_validation.issues + report_validation.issues))
            intent.blockers = list(dict.fromkeys(list(intent.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(
                json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
            warning_parts.append("live_order_intent_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.policy.journal_enabled:
            record = self._build_record(intent, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_order_intent_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_order_intent_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_order_intent_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "live_order_intent_build_latency_ms": intent_latency,
            "live_order_intent_validation_latency_ms": validation_latency,
            "live_order_intent_journal_append_latency_ms": append_latency,
            "live_order_intent_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderIntentServiceResult(intent, validation_report, record, summary, ";".join(warning_parts), timings)

    def _build_record(
        self,
        intent: LiveOrderIntent,
        validation_report: LiveOrderIntentValidationReport,
    ) -> LiveOrderIntentJournalRecord:
        created_at = now_utc_iso()
        if intent.status == "CREATED_FOR_CONTRACT_WORKFLOW" and validation_report.valid:
            event_type = "LIVE_ORDER_INTENT_CREATED"
        elif intent.status == "DUPLICATE":
            event_type = "LIVE_ORDER_INTENT_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_INTENT_BLOCKED"
        record = LiveOrderIntentJournalRecord(
            journal_record_id=_record_id(intent.intent_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            intent_id=intent.intent_id,
            validation_report_id=validation_report.validation_report_id,
            status=intent.status,
            scope=intent.scope,
            order_contract_workflow_allowed=validation_report.order_contract_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            artifact_hash=intent.artifact_hash,
            idempotency_key=intent.idempotency_key,
            source_live_permission_intent_id=intent.source_live_permission_intent_id,
            source_live_permission_decision_id=intent.source_live_permission_decision_id,
            source_preflight_report_id=intent.source_preflight_report_id,
            source_proposal_draft_id=intent.source_proposal_draft_id,
            source_simulated_contract_id=intent.source_simulated_contract_id,
            source_refs=list(intent.source_refs),
            metadata_redacted={
                "order_contract_workflow_preparation_only": True,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(intent_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{intent_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_intent_journal_{digest}"
