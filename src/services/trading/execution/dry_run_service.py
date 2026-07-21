from __future__ import annotations

from dataclasses import dataclass

from src.services.trading.execution.dry_run_adapter import DryRunExecutionAdapter
from src.services.trading.execution.gate import ExecutionGate
from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.journal_service import ExecutionJournalService
from src.services.trading.execution.models import DryRunExecutionReceipt, ExecutionGateDecision
from src.services.trading.review.models import HumanReviewArtifact, ReviewCard


@dataclass
class DryRunConfirmationResult:
    gate_decision: ExecutionGateDecision
    receipt: DryRunExecutionReceipt
    journal_record: ExecutionJournalRecord | None = None
    warning: str = ""


class DryRunConfirmationService:
    def __init__(
        self,
        gate: ExecutionGate | None = None,
        adapter: DryRunExecutionAdapter | None = None,
        journal: ExecutionJournalService | None = None,
    ):
        self.gate = gate or ExecutionGate()
        self.adapter = adapter or DryRunExecutionAdapter()
        self.journal = journal or ExecutionJournalService()

    def run(self, artifact: HumanReviewArtifact, card: ReviewCard | None = None, mode: str | None = None) -> DryRunConfirmationResult:
        gate_decision = self.gate.evaluate(artifact, card=card, mode=mode)
        receipt = self.adapter.run(gate_decision, artifact)
        journal_record = self.journal.append_receipt(artifact, gate_decision, receipt)
        return DryRunConfirmationResult(
            gate_decision=gate_decision,
            receipt=receipt,
            journal_record=journal_record,
            warning=self.journal.last_warning,
        )
