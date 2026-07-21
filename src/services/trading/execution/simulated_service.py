from __future__ import annotations

from src.services.trading.execution.adapter_policy import ExecutionAdapterPolicy
from src.services.trading.execution.adapter_registry import ExecutionAdapterRegistry
from src.services.trading.execution.journal_models import ExecutionJournalRecord
from src.services.trading.execution.models import DryRunExecutionReceipt
from src.services.trading.execution.simulated_contract import SimulatedOrderContractBuilder
from src.services.trading.execution.simulated_journal import SimulatedExecutionJournalService
from src.services.trading.execution.simulated_receipt import SimulatedExecutionServiceResult
from src.services.trading.proposal.draft_models import NonExecutableTradeProposalDraft, ProposalDraftJournalRecord
from src.services.trading.proposal.models import HumanConfirmedProposalIntent


class SimulatedExecutionService:
    def __init__(
        self,
        policy: ExecutionAdapterPolicy | None = None,
        registry: ExecutionAdapterRegistry | None = None,
        contract_builder: SimulatedOrderContractBuilder | None = None,
        journal: SimulatedExecutionJournalService | None = None,
    ):
        self.policy = policy or ExecutionAdapterPolicy.from_config()
        self.registry = registry or ExecutionAdapterRegistry(policy=self.policy)
        self.contract_builder = contract_builder or SimulatedOrderContractBuilder(policy=self.policy)
        self.journal = journal or SimulatedExecutionJournalService(enabled=self.policy.simulated_journal_enabled)

    def run(
        self,
        draft: NonExecutableTradeProposalDraft,
        intent: HumanConfirmedProposalIntent | None = None,
        dry_run_receipt: DryRunExecutionReceipt | None = None,
        execution_journal_record: ExecutionJournalRecord | None = None,
        proposal_draft_journal_record: ProposalDraftJournalRecord | None = None,
    ) -> SimulatedExecutionServiceResult:
        contract = self.contract_builder.build(
            draft,
            intent=intent,
            dry_run_receipt=dry_run_receipt,
            execution_journal_record=execution_journal_record,
            proposal_draft_journal_record=proposal_draft_journal_record,
        )
        adapter = self.registry.get_adapter()
        health = adapter.health_check()
        receipt = adapter.submit_simulated(contract)
        journal_record = self.journal.append_receipt(contract, receipt)
        return SimulatedExecutionServiceResult(
            contract=contract,
            adapter_health=health,
            receipt=receipt,
            journal_record=journal_record,
            warning=self.journal.last_warning,
        )
