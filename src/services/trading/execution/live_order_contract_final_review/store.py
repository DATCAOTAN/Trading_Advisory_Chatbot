from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.services.trading.execution.live_order_contract_final_review.models import (
    LiveOrderContractFinalReviewJournalRecord,
    LiveOrderContractFinalReviewSummary,
)


class LiveOrderContractFinalReviewJournalStore:
    def __init__(self, path: str | Path | None = None, max_read_records: int | None = None):
        raw_path = path or getattr(
            Config,
            "TRADING_CONTRACT_FINAL_REVIEW_JOURNAL_PATH",
            "data/trading/execution_journal/live_order_contract_final_reviews.jsonl",
        )
        self.path = Path(raw_path)
        if not self.path.is_absolute():
            self.path = Config.BASE_DIR / self.path
        self.max_read_records = int(max_read_records or getattr(Config, "TRADING_CONTRACT_FINAL_REVIEW_MAX_READ_RECORDS", 100))
        self.warnings: list[str] = []

    def append(self, record: LiveOrderContractFinalReviewJournalRecord) -> LiveOrderContractFinalReviewJournalRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_latest(self, limit: int | None = None) -> list[LiveOrderContractFinalReviewJournalRecord]:
        self.warnings = []
        if not self.path.exists():
            self.warnings.append("live_order_contract_final_review_journal_missing")
            return []
        records: list[LiveOrderContractFinalReviewJournalRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    records.append(_record_from_dict(json.loads(raw)))
                except Exception:
                    self.warnings.append(f"corrupt_jsonl_line:{line_number}")
        return records[-int(limit or self.max_read_records) :]

    def summarize(self, limit: int | None = None) -> LiveOrderContractFinalReviewSummary:
        records = self.read_latest(limit)
        summary = LiveOrderContractFinalReviewSummary(total_records=len(records), warnings=list(self.warnings))
        if not records:
            return summary
        summary.total_approved = sum(1 for item in records if item.status == "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY")
        summary.total_blocked = sum(1 for item in records if item.status in {"BLOCKED", "INVALID", "EXPIRED", "REJECTED"})
        summary.total_duplicates = sum(1 for item in records if item.status == "DUPLICATE")
        latest = records[-1]
        summary.latest_record_at = latest.created_at
        summary.latest_final_review_id = latest.final_review_id
        summary.latest_validation_report_id = latest.validation_report_id
        summary.latest_status = latest.status
        return summary

    def idempotency_keys(self, limit: int | None = None) -> set[str]:
        return {item.idempotency_key for item in self.read_latest(limit) if item.idempotency_key}

    def find_by_idempotency_key(
        self, idempotency_key: str, limit: int | None = None
    ) -> LiveOrderContractFinalReviewJournalRecord | None:
        for record in reversed(self.read_latest(limit)):
            if record.idempotency_key == idempotency_key:
                return record
        return None


def _record_from_dict(data: dict) -> LiveOrderContractFinalReviewJournalRecord:
    return LiveOrderContractFinalReviewJournalRecord(
        journal_record_id=str(data.get("journal_record_id", "")),
        created_at=str(data.get("created_at", "")),
        event_type=str(data.get("event_type", "UNKNOWN")),
        final_review_id=str(data.get("final_review_id", "")),
        validation_report_id=str(data.get("validation_report_id", "")),
        status=str(data.get("status", "UNKNOWN")),
        scope=str(data.get("scope", "UNKNOWN")),
        pre_mt5_mapping_boundary_workflow_allowed=bool(data.get("pre_mt5_mapping_boundary_workflow_allowed", False)),
        live_execution_allowed=bool(data.get("live_execution_allowed", False)),
        order_send_allowed=bool(data.get("order_send_allowed", False)),
        execution_allowed=bool(data.get("execution_allowed", False)),
        executable=bool(data.get("executable", False)),
        mt5_payload_created=bool(data.get("mt5_payload_created", False)),
        order_sent=bool(data.get("order_sent", False)),
        hard_live_block_required=bool(data.get("hard_live_block_required", True)),
        order_contract_ready=bool(data.get("order_contract_ready", False)),
        order_request_mapping_allowed=bool(data.get("order_request_mapping_allowed", False)),
        broker_mapping_created=bool(data.get("broker_mapping_created", False)),
        raw_values_stored=bool(data.get("raw_values_stored", False)),
        executable_order_created=bool(data.get("executable_order_created", False)),
        confirmation_phrase_valid=bool(data.get("confirmation_phrase_valid", False)),
        slot_validations_count=int(data.get("slot_validations_count", 0) or 0),
        passed_slot_validations_count=int(data.get("passed_slot_validations_count", 0) or 0),
        blocked_slot_validations_count=int(data.get("blocked_slot_validations_count", 0) or 0),
        missing_slot_validations_count=int(data.get("missing_slot_validations_count", 0) or 0),
        artifact_hash=str(data.get("artifact_hash", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        source_parameterization_id=str(data.get("source_parameterization_id", "")),
        source_parameterization_validation_id=str(data.get("source_parameterization_validation_id", "")),
        source_approval_lock_id=str(data.get("source_approval_lock_id", "")),
        source_value_proposal_id=str(data.get("source_value_proposal_id", "")),
        source_parameter_draft_id=str(data.get("source_parameter_draft_id", "")),
        source_parameter_source_boundary_id=str(data.get("source_parameter_source_boundary_id", "")),
        source_parameter_policy_spec_id=str(data.get("source_parameter_policy_spec_id", "")),
        source_contract_skeleton_id=str(data.get("source_contract_skeleton_id", "")),
        source_live_order_intent_id=str(data.get("source_live_order_intent_id", "")),
        source_live_permission_decision_id=str(data.get("source_live_permission_decision_id", "")),
        source_preflight_report_id=str(data.get("source_preflight_report_id", "")),
        source_refs=list(data.get("source_refs", []) or []),
        payload_size_chars=int(data.get("payload_size_chars", 0) or 0),
        metadata_redacted=dict(data.get("metadata_redacted", {}) or {}),
    )
