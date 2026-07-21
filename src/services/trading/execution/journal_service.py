from __future__ import annotations

import hashlib
import json

from src.config import Config
from src.services.trading.execution.journal_models import ExecutionJournalRecord, ExecutionJournalSummary, now_utc_iso
from src.services.trading.execution.journal_store import ExecutionJournalStore
from src.services.trading.execution.journal_validator import ExecutionJournalValidator
from src.services.trading.execution.models import DryRunExecutionReceipt, ExecutionGateDecision
from src.services.trading.review.models import HumanReviewArtifact


class ExecutionJournalService:
    def __init__(
        self,
        store: ExecutionJournalStore | None = None,
        validator: ExecutionJournalValidator | None = None,
        enabled: bool | None = None,
    ):
        self.store = store or ExecutionJournalStore()
        self.validator = validator or ExecutionJournalValidator()
        self.enabled = bool(getattr(Config, "TRADING_EXECUTION_JOURNAL_ENABLED", True) if enabled is None else enabled)
        self.last_warning = ""

    def build_record(
        self,
        artifact: HumanReviewArtifact,
        gate_decision: ExecutionGateDecision,
        receipt: DryRunExecutionReceipt,
    ) -> ExecutionJournalRecord:
        event_type = _event_type(gate_decision, receipt)
        created_at = now_utc_iso()
        record = ExecutionJournalRecord(
            journal_record_id=_record_id(receipt.receipt_id, created_at),
            created_at=created_at,
            event_type=event_type,
            mode=receipt.mode,
            symbol=receipt.symbol,
            broker_symbol=receipt.broker_symbol,
            artifact_id=artifact.artifact_id,
            artifact_hash=receipt.artifact_hash,
            idempotency_key=receipt.idempotency_key,
            gate_decision_id=gate_decision.gate_decision_id,
            gate_action=gate_decision.action,
            receipt_id=receipt.receipt_id,
            dry_run_only=True,
            executed=False,
            allowed=receipt.allowed,
            review_status=artifact.review_status,
            readiness_action=artifact.readiness_action,
            blockers=list(receipt.blockers),
            warnings=list(receipt.warnings),
            source_refs=list(dict.fromkeys(receipt.source_refs)),
            metadata_redacted={
                "artifact_hash_prefix": receipt.artifact_hash[:12],
                "idempotency_key_prefix": receipt.idempotency_key[:12],
                "dry_run_only": True,
                "executed": False,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record

    def append_receipt(
        self,
        artifact: HumanReviewArtifact,
        gate_decision: ExecutionGateDecision,
        receipt: DryRunExecutionReceipt,
    ) -> ExecutionJournalRecord | None:
        self.last_warning = ""
        if not self.enabled:
            self.last_warning = "journal_disabled"
            return None
        record = self.build_record(artifact, gate_decision, receipt)
        validation = self.validator.validate(record)
        if not validation.passed:
            self.last_warning = "journal_validation_failed:" + ",".join(validation.issues)
            return None
        try:
            return self.store.append(record)
        except Exception as exc:
            self.last_warning = f"journal_write_failed:{type(exc).__name__}"
            return None

    def summary(self) -> ExecutionJournalSummary:
        return self.store.summarize()


def _event_type(gate_decision: ExecutionGateDecision, receipt: DryRunExecutionReceipt) -> str:
    if gate_decision.action == "DUPLICATE_ARTIFACT":
        return "DRY_RUN_DUPLICATE_DETECTED"
    if receipt.allowed:
        return "DRY_RUN_ALLOWED"
    if not receipt.allowed:
        return "DRY_RUN_BLOCKED"
    return "DRY_RUN_RECEIPT_CREATED"


def _record_id(receipt_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{receipt_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"execution_journal_{digest}"
