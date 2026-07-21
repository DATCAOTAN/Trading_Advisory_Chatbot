from __future__ import annotations

from dataclasses import dataclass

from src.services.trading.execution.adapter_models import SimulatedExecutionJournalRecord, SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.mt5_skeleton_adapter import MT5ExecutionAdapterSkeleton
from src.services.trading.execution.mt5_skeleton_journal import LiveExecutionBlockJournalService
from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockedReceipt,
    LiveExecutionCapabilityReport,
)
from src.services.trading.execution.mt5_skeleton_policy import MT5ExecutionSkeletonPolicy
from src.services.trading.execution.mt5_skeleton_store import LiveExecutionBlockJournalStore
from src.services.trading.execution.mt5_skeleton_validator import HardLiveBlockValidator


@dataclass
class MT5ExecutionSkeletonServiceResult:
    capability_report: LiveExecutionCapabilityReport
    blocked_receipt: LiveExecutionBlockedReceipt
    journal_record: LiveExecutionBlockJournalRecord | None
    warning: str = ""


class MT5ExecutionSkeletonService:
    def __init__(
        self,
        policy: MT5ExecutionSkeletonPolicy | None = None,
        adapter: MT5ExecutionAdapterSkeleton | None = None,
        journal_service: LiveExecutionBlockJournalService | None = None,
        validator: HardLiveBlockValidator | None = None,
    ):
        self.policy = policy or MT5ExecutionSkeletonPolicy.from_config()
        self.validator = validator or HardLiveBlockValidator(self.policy.max_payload_chars)
        self.adapter = adapter or MT5ExecutionAdapterSkeleton(policy=self.policy, validator=self.validator)
        self.journal_service = journal_service or LiveExecutionBlockJournalService(
            store=LiveExecutionBlockJournalStore(
                path=self.policy.journal_path,
                max_read_records=self.policy.max_read_records,
            ),
            validator=self.validator,
            enabled=self.policy.journal_enabled,
        )

    def run(
        self,
        contract: SimulatedOrderContract | None,
        simulated_receipt: SimulatedExecutionReceipt | None,
        simulated_journal_record: SimulatedExecutionJournalRecord | None = None,
    ) -> MT5ExecutionSkeletonServiceResult:
        report = self.adapter.capability_report(contract, simulated_receipt)
        receipt = self.adapter.attempt_live_execution_blocked(contract, simulated_receipt, simulated_journal_record)
        report_validation = self.validator.validate_report(report)
        receipt_validation = self.validator.validate_receipt(receipt)
        warning_parts: list[str] = []
        if not report_validation.passed:
            warning_parts.append("capability_report_validation_failed:" + ",".join(report_validation.issues))
        if not receipt_validation.passed:
            warning_parts.append("blocked_receipt_validation_failed:" + ",".join(receipt_validation.issues))
        record = None
        if receipt_validation.passed:
            record = self.journal_service.append_block(contract, receipt, simulated_receipt, simulated_journal_record)
            if self.journal_service.last_warning:
                warning_parts.append(self.journal_service.last_warning)
        return MT5ExecutionSkeletonServiceResult(
            capability_report=report,
            blocked_receipt=receipt,
            journal_record=record,
            warning=";".join(warning_parts),
        )
