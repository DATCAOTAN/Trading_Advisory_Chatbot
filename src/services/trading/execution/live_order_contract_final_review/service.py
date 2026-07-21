from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.live_order_contract_final_review.builder import (
    LiveOrderContractFinalReviewBuilder,
)
from src.services.trading.execution.live_order_contract_final_review.confirmation import (
    LiveOrderContractFinalReviewConfirmationService,
)
from src.services.trading.execution.live_order_contract_final_review.gate import (
    LiveOrderContractFinalReviewGate,
)
from src.services.trading.execution.live_order_contract_final_review.models import (
    LiveOrderContractFinalReview,
    LiveOrderContractFinalReviewJournalRecord,
    LiveOrderContractFinalReviewSummary,
    LiveOrderContractFinalReviewValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract_final_review.policy import (
    LiveOrderContractFinalReviewConfig,
)
from src.services.trading.execution.live_order_contract_final_review.store import (
    LiveOrderContractFinalReviewJournalStore,
)
from src.services.trading.execution.live_order_contract_final_review.validator import (
    LiveOrderContractFinalReviewValidator,
)


@dataclass
class LiveOrderContractFinalReviewServiceResult:
    final_review: LiveOrderContractFinalReview
    validation_report: LiveOrderContractFinalReviewValidationReport
    journal_record: LiveOrderContractFinalReviewJournalRecord | None
    summary: LiveOrderContractFinalReviewSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class LiveOrderContractFinalReviewService:
    def __init__(
        self,
        config: LiveOrderContractFinalReviewConfig | None = None,
        confirmation_service: LiveOrderContractFinalReviewConfirmationService | None = None,
        builder: LiveOrderContractFinalReviewBuilder | None = None,
        gate: LiveOrderContractFinalReviewGate | None = None,
        store: LiveOrderContractFinalReviewJournalStore | None = None,
        validator: LiveOrderContractFinalReviewValidator | None = None,
    ):
        self.config = config or LiveOrderContractFinalReviewConfig.from_config()
        self.confirmation_service = confirmation_service or LiveOrderContractFinalReviewConfirmationService(self.config)
        self.builder = builder or LiveOrderContractFinalReviewBuilder(self.config, confirmation_service=self.confirmation_service)
        self.gate = gate or LiveOrderContractFinalReviewGate(self.config)
        self.store = store or LiveOrderContractFinalReviewJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or LiveOrderContractFinalReviewValidator(self.config)

    def run(
        self,
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
        confirmation_phrase: str | None = None,
        current_time=None,
    ) -> LiveOrderContractFinalReviewServiceResult:
        started = perf_counter()
        warning_parts: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        source_refs = list(getattr(parameterization, "source_refs", []) or [])
        confirmation = self.confirmation_service.confirm(confirmation_phrase, current_time, source_refs)

        build_started = perf_counter()
        final_review = self.builder.build(
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
            confirmation=confirmation,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        build_latency = (perf_counter() - build_started) * 1000

        validation_started = perf_counter()
        validation_report = self.gate.validate(final_review)
        validation_latency = (perf_counter() - validation_started) * 1000

        final_review_validation = self.validator.validate_final_review(final_review)
        report_validation = self.validator.validate_report(validation_report)
        if not final_review_validation.passed or not report_validation.passed:
            final_review.status = "INVALID"
            final_review.pre_mt5_mapping_boundary_workflow_allowed = False
            validation_report.valid = False
            validation_report.pre_mt5_mapping_boundary_workflow_allowed = False
            issues = list(dict.fromkeys(final_review_validation.issues + report_validation.issues))
            final_review.blockers = list(dict.fromkeys(list(final_review.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            final_review.payload_size_chars = len(json.dumps(final_review.as_dict(), ensure_ascii=False, sort_keys=True))
            validation_report.payload_size_chars = len(json.dumps(validation_report.as_dict(), ensure_ascii=False, sort_keys=True))
            warning_parts.append("live_order_contract_final_review_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(final_review, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                try:
                    append_started = perf_counter()
                    self.store.append(record)
                    append_latency = (perf_counter() - append_started) * 1000
                except Exception as exc:
                    record = None
                    warning_parts.append(f"live_order_contract_final_review_journal_write_failed:{type(exc).__name__}")
            else:
                record = None
                warning_parts.append("live_order_contract_final_review_journal_validation_failed:" + ",".join(record_validation.issues))
        else:
            warning_parts.append("live_order_contract_final_review_journal_disabled")

        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "contract_final_review_build_latency_ms": build_latency,
            "contract_final_review_validation_latency_ms": validation_latency,
            "contract_final_review_journal_append_latency_ms": append_latency,
            "contract_final_review_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return LiveOrderContractFinalReviewServiceResult(
            final_review,
            validation_report,
            record,
            summary,
            ";".join(warning_parts),
            timings,
        )

    def _build_record(
        self,
        final_review: LiveOrderContractFinalReview,
        validation_report: LiveOrderContractFinalReviewValidationReport,
    ) -> LiveOrderContractFinalReviewJournalRecord:
        created_at = now_utc_iso()
        if final_review.status == "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY" and validation_report.valid:
            event_type = "LIVE_ORDER_CONTRACT_FINAL_REVIEW_APPROVED"
        elif final_review.status == "DUPLICATE":
            event_type = "LIVE_ORDER_CONTRACT_FINAL_REVIEW_DUPLICATE_DETECTED"
        else:
            event_type = "LIVE_ORDER_CONTRACT_FINAL_REVIEW_BLOCKED"
        record = LiveOrderContractFinalReviewJournalRecord(
            journal_record_id=_record_id(final_review.final_review_id, validation_report.validation_report_id, created_at),
            created_at=created_at,
            event_type=event_type,
            final_review_id=final_review.final_review_id,
            validation_report_id=validation_report.validation_report_id,
            status=final_review.status,
            scope=final_review.scope,
            pre_mt5_mapping_boundary_workflow_allowed=validation_report.pre_mt5_mapping_boundary_workflow_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            confirmation_phrase_valid=validation_report.confirmation_phrase_valid,
            slot_validations_count=validation_report.slot_validations_count,
            passed_slot_validations_count=validation_report.passed_slot_validations_count,
            blocked_slot_validations_count=validation_report.blocked_slot_validations_count,
            missing_slot_validations_count=validation_report.missing_slot_validations_count,
            artifact_hash=final_review.artifact_hash,
            idempotency_key=final_review.idempotency_key,
            source_parameterization_id=final_review.source_parameterization_id,
            source_parameterization_validation_id=final_review.source_parameterization_validation_id,
            source_approval_lock_id=final_review.source_approval_lock_id,
            source_value_proposal_id=final_review.source_value_proposal_id,
            source_parameter_draft_id=final_review.source_parameter_draft_id,
            source_parameter_source_boundary_id=final_review.source_parameter_source_boundary_id,
            source_parameter_policy_spec_id=final_review.source_parameter_policy_spec_id,
            source_contract_skeleton_id=final_review.source_contract_skeleton_id,
            source_live_order_intent_id=final_review.source_live_order_intent_id,
            source_live_permission_decision_id=final_review.source_live_permission_decision_id,
            source_preflight_report_id=final_review.source_preflight_report_id,
            source_refs=list(final_review.source_refs),
            metadata_redacted={
                "contract_final_review_only": True,
                "confirmation_phrase_redacted": True,
                "broker_mapping_created": False,
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


def _record_id(final_review_id: str, validation_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{final_review_id}|{validation_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_order_contract_final_review_journal_{digest}"
