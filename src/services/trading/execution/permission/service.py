from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.permission.confirmation import LivePermissionIntentBuilder
from src.services.trading.execution.permission.gate import LivePermissionGate
from src.services.trading.execution.permission.models import (
    LivePermissionGateDecision,
    LivePermissionIntent,
    LivePermissionJournalRecord,
    LivePermissionSummary,
    now_utc_iso,
)
from src.services.trading.execution.permission.policy import LivePermissionPolicy
from src.services.trading.execution.permission.store import LivePermissionJournalStore
from src.services.trading.execution.permission.validator import LivePermissionGateValidator


@dataclass
class LivePermissionGateServiceResult:
    intent: LivePermissionIntent
    decision: LivePermissionGateDecision
    journal_record: LivePermissionJournalRecord | None
    summary: LivePermissionSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LivePermissionGateService:
    def __init__(
        self,
        policy: LivePermissionPolicy | None = None,
        builder: LivePermissionIntentBuilder | None = None,
        gate: LivePermissionGate | None = None,
        store: LivePermissionJournalStore | None = None,
        validator: LivePermissionGateValidator | None = None,
    ):
        self.policy = policy or LivePermissionPolicy.from_config()
        self.builder = builder or LivePermissionIntentBuilder(self.policy)
        self.gate = gate or LivePermissionGate(self.policy)
        self.store = store or LivePermissionJournalStore(self.policy.journal_path, self.policy.max_read_records)
        self.validator = validator or LivePermissionGateValidator(self.policy)

    def run(
        self,
        preflight_report,
        design_report,
        capability_report,
        blocked_receipt,
        simulated_contract=None,
        proposal_draft=None,
        user_acknowledgement_text: str | None = None,
        current_time=None,
    ) -> LivePermissionGateServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.policy.journal_enabled else set()
        intent_started = perf_counter()
        intent = self.builder.build(
            preflight_report,
            design_report,
            capability_report,
            blocked_receipt,
            simulated_contract=simulated_contract,
            proposal_draft=proposal_draft,
            user_acknowledgement_text=user_acknowledgement_text,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        intent_latency = (perf_counter() - intent_started) * 1000
        gate_started = perf_counter()
        decision = self.gate.decide(intent)
        gate_latency = (perf_counter() - gate_started) * 1000

        intent_validation = self.validator.validate_intent(intent)
        decision_validation = self.validator.validate_decision(decision)
        if not intent_validation.passed or not decision_validation.passed:
            intent.permission_status = "INVALID"
            intent.order_intent_workflow_allowed = False
            decision.permission_status = "INVALID"
            decision.gate_allowed = False
            decision.order_intent_workflow_allowed = False
            issues = list(dict.fromkeys(intent_validation.issues + decision_validation.issues))
            intent.blockers = list(dict.fromkeys(list(intent.blockers) + issues))
            decision.blockers = list(dict.fromkeys(list(decision.blockers) + issues))
            decision.block_reasons = list(dict.fromkeys(list(decision.block_reasons) + ["INVALID_INPUT"]))
            intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
            decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("live_permission_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.policy.journal_enabled:
            record = self._build_record(intent, decision)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_permission_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_permission_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_permission_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "permission_intent_build_latency_ms": intent_latency,
            "permission_gate_latency_ms": gate_latency,
            "permission_journal_append_latency_ms": append_latency,
            "permission_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LivePermissionGateServiceResult(intent, decision, record, summary, ";".join(warning_parts), timings)

    def _build_record(self, intent: LivePermissionIntent, decision: LivePermissionGateDecision) -> LivePermissionJournalRecord:
        created_at = now_utc_iso()
        if decision.gate_allowed:
            event_type = "LIVE_PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW"
        elif intent.permission_status == "DUPLICATE":
            event_type = "LIVE_PERMISSION_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_PERMISSION_BLOCKED"
        record = LivePermissionJournalRecord(
            journal_record_id=_record_id(intent.intent_id, decision.decision_id, created_at),
            created_at=created_at,
            event_type=event_type,
            intent_id=intent.intent_id,
            decision_id=decision.decision_id,
            permission_status=intent.permission_status,
            permission_scope=decision.permission_scope,
            confirmation_state=intent.confirmation_state,
            order_intent_workflow_allowed=decision.order_intent_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            artifact_hash=intent.artifact_hash,
            idempotency_key=intent.idempotency_key,
            source_preflight_report_id=intent.source_preflight_report_id,
            source_design_report_id=intent.source_design_report_id,
            source_refs=list(intent.source_refs),
            metadata_redacted={
                "permission_gate_only": True,
                "live_execution_allowed": False,
                "order_send_allowed": False,
                "execution_allowed": False,
                "hard_live_block_required": True,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record


def _record_id(intent_id: str, decision_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{intent_id}|{decision_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_permission_journal_{digest}"
