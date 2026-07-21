from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.adapter_models import SimulatedExecutionJournalRecord, SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockSummary,
    LiveExecutionBlockedReceipt,
    now_utc_iso,
)
from src.services.trading.execution.mt5_skeleton_store import LiveExecutionBlockJournalStore
from src.services.trading.execution.mt5_skeleton_validator import HardLiveBlockValidator


class LiveExecutionBlockJournalService:
    def __init__(
        self,
        store: LiveExecutionBlockJournalStore | None = None,
        validator: HardLiveBlockValidator | None = None,
        enabled: bool = True,
    ):
        self.store = store or LiveExecutionBlockJournalStore()
        self.validator = validator or HardLiveBlockValidator()
        self.enabled = bool(enabled)
        self.last_warning = ""

    def build_record(
        self,
        contract: SimulatedOrderContract | None,
        receipt: LiveExecutionBlockedReceipt,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        simulated_journal_record: SimulatedExecutionJournalRecord | None = None,
    ) -> LiveExecutionBlockJournalRecord:
        created_at = now_utc_iso()
        source_contract_id = getattr(contract, "contract_id", "") or receipt.source_contract_id
        source_simulated_receipt_id = getattr(simulated_receipt, "receipt_id", "") or receipt.source_simulated_receipt_id
        record = LiveExecutionBlockJournalRecord(
            journal_record_id=_record_id(receipt.receipt_id, created_at),
            created_at=created_at,
            event_type="LIVE_EXECUTION_BLOCKED",
            adapter_type="RESERVED_MT5_LIVE",
            skeleton_status=receipt.skeleton_status,
            receipt_id=receipt.receipt_id,
            blocked=True,
            executed=False,
            order_sent=False,
            live_execution_supported=False,
            hard_live_block_enabled=True,
            block_reason=receipt.block_reason,
            source_contract_id=source_contract_id,
            source_simulated_receipt_id=source_simulated_receipt_id,
            artifact_hash=receipt.artifact_hash,
            idempotency_key=receipt.idempotency_key,
            blockers=list(receipt.blockers),
            warnings=list(receipt.warnings),
            source_refs=list(dict.fromkeys(receipt.source_refs)),
            metadata_redacted={
                "artifact_hash_prefix": receipt.artifact_hash[:12],
                "idempotency_key_prefix": receipt.idempotency_key[:12],
                "source_simulated_journal_record_id": getattr(simulated_journal_record, "journal_record_id", ""),
                "blocked": True,
                "executed": False,
                "order_sent": False,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record

    def append_block(
        self,
        contract: SimulatedOrderContract | None,
        receipt: LiveExecutionBlockedReceipt,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        simulated_journal_record: SimulatedExecutionJournalRecord | None = None,
    ) -> LiveExecutionBlockJournalRecord | None:
        self.last_warning = ""
        if not self.enabled:
            self.last_warning = "live_execution_block_journal_disabled"
            return None
        record = self.build_record(contract, receipt, simulated_receipt, simulated_journal_record)
        validation = self.validator.validate_record(record)
        if not validation.passed:
            self.last_warning = "live_execution_block_journal_validation_failed:" + ",".join(validation.issues)
            return None
        try:
            return self.store.append(record)
        except Exception as exc:
            self.last_warning = f"live_execution_block_journal_write_failed:{type(exc).__name__}"
            return None

    def summary(self) -> LiveExecutionBlockSummary:
        return self.store.summarize()


def _record_id(receipt_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{receipt_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_execution_block_journal_{digest}"
