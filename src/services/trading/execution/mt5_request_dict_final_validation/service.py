from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter

from src.services.trading.execution.mt5_request_dict_final_validation.builder import MT5RequestDictFinalValidationBuilder
from src.services.trading.execution.mt5_request_dict_final_validation.gate import MT5RequestDictFinalValidationGate
from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationJournalRecord,
    MT5RequestDictFinalValidationReport,
    MT5RequestDictFinalValidationSummary,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import MT5RequestDictFinalValidationConfig
from src.services.trading.execution.mt5_request_dict_final_validation.store import MT5RequestDictFinalValidationJournalStore
from src.services.trading.execution.mt5_request_dict_final_validation.validator import MT5RequestDictFinalValidationValidator


@dataclass
class MT5RequestDictFinalValidationServiceResult:
    final_validation: MT5RequestDictFinalValidationBoundary
    validation_report: MT5RequestDictFinalValidationReport
    journal_record: MT5RequestDictFinalValidationJournalRecord | None
    summary: MT5RequestDictFinalValidationSummary
    warning: str = ""
    timings_ms: dict[str, float] | None = None


class MT5RequestDictFinalValidationService:
    def __init__(
        self,
        config: MT5RequestDictFinalValidationConfig | None = None,
        builder: MT5RequestDictFinalValidationBuilder | None = None,
        gate: MT5RequestDictFinalValidationGate | None = None,
        store: MT5RequestDictFinalValidationJournalStore | None = None,
        validator: MT5RequestDictFinalValidationValidator | None = None,
    ):
        self.config = config or MT5RequestDictFinalValidationConfig.from_config()
        self.builder = builder or MT5RequestDictFinalValidationBuilder(self.config)
        self.gate = gate or MT5RequestDictFinalValidationGate(self.config)
        self.store = store or MT5RequestDictFinalValidationJournalStore(self.config.journal_path, self.config.max_read_records)
        self.validator = validator or MT5RequestDictFinalValidationValidator(self.config)

    def run(self, dry_run_builder_boundary, dry_run_builder_validation_report, current_time=None) -> MT5RequestDictFinalValidationServiceResult:
        started = perf_counter()
        warnings: list[str] = []
        existing_keys = self.store.idempotency_keys() if self.config.journal_enabled else set()
        build_started = perf_counter()
        final_validation = self.builder.build(
            dry_run_builder_boundary,
            dry_run_builder_validation_report,
            current_time=current_time,
            existing_idempotency_keys=existing_keys,
        )
        build_latency = (perf_counter() - build_started) * 1000
        report_started = perf_counter()
        validation_report = self.gate.validate(final_validation)
        report_latency = (perf_counter() - report_started) * 1000

        object_validation = self.validator.validate_boundary(final_validation, dry_run_builder_validation_report)
        report_validation = self.validator.validate_report(validation_report)
        if not object_validation.passed or not report_validation.passed:
            final_validation.status = "INVALID" if final_validation.status not in {"EXPIRED", "DUPLICATE"} else final_validation.status
            final_validation.bridge_write_skeleton_check_allowed = False
            validation_report.valid = False
            validation_report.bridge_write_skeleton_check_allowed = False
            issues = list(dict.fromkeys(object_validation.issues + report_validation.issues))
            final_validation.blockers = list(dict.fromkeys(list(final_validation.blockers) + issues))
            validation_report.blockers = list(dict.fromkeys(list(validation_report.blockers) + issues))
            warnings.append("mt5_request_dict_final_validation_failed:" + ",".join(issues))

        record = None
        append_latency = 0.0
        if self.config.journal_enabled:
            record = self._build_record(final_validation, validation_report)
            record_validation = self.validator.validate_record(record)
            if record_validation.passed:
                append_started = perf_counter()
                self.store.append(record)
                append_latency = (perf_counter() - append_started) * 1000
            else:
                warnings.append("mt5_request_dict_final_validation_journal_validation_failed:" + ",".join(record_validation.issues))
                record = None
        else:
            warnings.append("mt5_request_dict_final_validation_journal_disabled")
        read_started = perf_counter()
        summary = self.store.summarize()
        read_latency = (perf_counter() - read_started) * 1000
        timings = {
            "mt5_request_dict_final_validation_build_latency_ms": build_latency,
            "mt5_request_dict_final_validation_report_latency_ms": report_latency,
            "mt5_request_dict_final_validation_journal_append_latency_ms": append_latency,
            "mt5_request_dict_final_validation_journal_read_latency_ms": read_latency,
            "service_total_latency_ms": (perf_counter() - started) * 1000,
        }
        return MT5RequestDictFinalValidationServiceResult(final_validation, validation_report, record, summary, ";".join(warnings), timings)

    def _build_record(
        self,
        final_validation: MT5RequestDictFinalValidationBoundary,
        report: MT5RequestDictFinalValidationReport,
    ) -> MT5RequestDictFinalValidationJournalRecord:
        created_at = now_utc_iso()
        if final_validation.status == "FINAL_VALIDATION_PASSED" and report.valid:
            event_type = "MT5_REQUEST_DICT_FINAL_VALIDATION_PASSED"
        elif final_validation.status == "DUPLICATE":
            event_type = "MT5_REQUEST_DICT_FINAL_VALIDATION_DUPLICATE"
        else:
            event_type = "MT5_REQUEST_DICT_FINAL_VALIDATION_BLOCKED"
        return MT5RequestDictFinalValidationJournalRecord(
            journal_record_id="mt5_request_dict_final_validation_journal_" + hashlib.sha256(
                f"{final_validation.final_validation_id}:{report.validation_report_id}:{created_at}".encode("utf-8")
            ).hexdigest()[:16],
            created_at=created_at,
            event_type=event_type,
            final_validation_id=final_validation.final_validation_id,
            validation_report_id=report.validation_report_id,
            status=final_validation.status,
            scope=final_validation.scope,
            bridge_write_skeleton_check_allowed=report.bridge_write_skeleton_check_allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            real_mt5_payload_created=False,
            broker_submittable_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            validated_fields_count=report.validated_fields_count,
            missing_fields_count=report.missing_fields_count,
            invalid_fields_count=report.invalid_fields_count,
            artifact_hash=final_validation.artifact_hash,
            idempotency_key=final_validation.idempotency_key,
            source_dry_run_request_dict_id=final_validation.source_dry_run_request_dict_id,
            source_refs=list(final_validation.source_refs),
            payload_size_chars=len(json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False)),
            metadata_redacted=True,
        )
