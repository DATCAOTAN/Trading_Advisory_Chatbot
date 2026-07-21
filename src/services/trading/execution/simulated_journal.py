from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.adapter_models import (
    SimulatedExecutionJournalRecord,
    SimulatedExecutionReceipt,
    SimulatedExecutionSummary,
    SimulatedOrderContract,
    now_utc_iso,
)
from src.services.trading.execution.adapter_validator import ExecutionAdapterContractValidator
from src.services.trading.execution.simulated_store import SimulatedExecutionJournalStore


class SimulatedExecutionJournalService:
    def __init__(
        self,
        store: SimulatedExecutionJournalStore | None = None,
        validator: ExecutionAdapterContractValidator | None = None,
        enabled: bool = True,
    ):
        self.store = store or SimulatedExecutionJournalStore()
        self.validator = validator or ExecutionAdapterContractValidator()
        self.enabled = bool(enabled)
        self.last_warning = ""

    def build_record(
        self,
        contract: SimulatedOrderContract,
        receipt: SimulatedExecutionReceipt,
    ) -> SimulatedExecutionJournalRecord:
        created_at = now_utc_iso()
        record = SimulatedExecutionJournalRecord(
            journal_record_id=_record_id(receipt.receipt_id, created_at),
            created_at=created_at,
            event_type="SIMULATED_RECEIPT_CREATED" if receipt.accepted_by_adapter else "SIMULATED_RECEIPT_REJECTED",
            adapter_type="SIMULATED",
            contract_id=contract.contract_id,
            receipt_id=receipt.receipt_id,
            contract_status=contract.contract_status,
            simulated_only=True,
            executable=False,
            executed=False,
            accepted_by_adapter=receipt.accepted_by_adapter,
            source_draft_id=contract.source_draft_id,
            artifact_hash=contract.artifact_hash,
            idempotency_key=contract.idempotency_key,
            blockers=list(receipt.blockers),
            warnings=list(receipt.warnings),
            source_refs=list(dict.fromkeys(receipt.source_refs)),
            metadata_redacted={
                "artifact_hash_prefix": contract.artifact_hash[:12],
                "idempotency_key_prefix": contract.idempotency_key[:12],
                "simulated_only": True,
                "executable": False,
                "executed": False,
            },
        )
        record.payload_size_chars = len(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True))
        return record

    def append_receipt(
        self,
        contract: SimulatedOrderContract,
        receipt: SimulatedExecutionReceipt,
    ) -> SimulatedExecutionJournalRecord | None:
        self.last_warning = ""
        if not self.enabled:
            self.last_warning = "simulated_execution_journal_disabled"
            return None
        record = self.build_record(contract, receipt)
        validation = self.validator.validate_record(record)
        if not validation.passed:
            self.last_warning = "simulated_execution_journal_validation_failed:" + ",".join(validation.issues)
            return None
        try:
            return self.store.append(record)
        except Exception as exc:
            self.last_warning = f"simulated_execution_journal_write_failed:{type(exc).__name__}"
            return None

    def summary(self) -> SimulatedExecutionSummary:
        return self.store.summarize()


def _record_id(receipt_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{receipt_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"simulated_execution_journal_{digest}"
