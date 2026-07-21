from __future__ import annotations

from dataclasses import dataclass

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.proposal.draft_builder import NonExecutableProposalDraftBuilder
from src.services.trading.proposal.draft_formatter import ProposalDraftFormatter
from src.services.trading.proposal.draft_journal import ProposalDraftJournalService
from src.services.trading.proposal.draft_models import (
    NonExecutableTradeProposalDraft,
    ProposalDraftCard,
    ProposalDraftJournalRecord,
)
from src.services.trading.proposal.draft_policy import ProposalDraftPolicy
from src.services.trading.proposal.models import HumanConfirmedProposalIntent
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.review.models import HumanReviewArtifact
from src.services.trading.scoring.models import SignalScoreReport


@dataclass
class ProposalDraftResult:
    draft: NonExecutableTradeProposalDraft
    card: ProposalDraftCard
    journal_record: ProposalDraftJournalRecord | None = None
    warning: str = ""


class ProposalDraftService:
    def __init__(
        self,
        policy: ProposalDraftPolicy | None = None,
        builder: NonExecutableProposalDraftBuilder | None = None,
        formatter: ProposalDraftFormatter | None = None,
        journal: ProposalDraftJournalService | None = None,
    ):
        self.policy = policy or ProposalDraftPolicy.from_config()
        self.builder = builder or NonExecutableProposalDraftBuilder(policy=self.policy)
        self.formatter = formatter or ProposalDraftFormatter()
        self.journal = journal or ProposalDraftJournalService(enabled=self.policy.journal_enabled)

    def build(
        self,
        intent: HumanConfirmedProposalIntent,
        review_artifact: HumanReviewArtifact,
        score_report: SignalScoreReport,
        method_selection: MethodSelectionResult,
        context_pack: RuntimeContextPack,
        calendar_context: CalendarContext | None = None,
        regime_snapshot: MarketRegimeSnapshot | None = None,
        feature_snapshot: FeatureSnapshot | None = None,
    ) -> ProposalDraftResult:
        draft = self.builder.build(
            intent,
            review_artifact,
            score_report,
            method_selection,
            context_pack,
            calendar_context=calendar_context,
            regime_snapshot=regime_snapshot,
            feature_snapshot=feature_snapshot,
        )
        card = self.formatter.to_card(draft)
        record = self.journal.append_draft(draft, intent)
        return ProposalDraftResult(draft=draft, card=card, journal_record=record, warning=self.journal.last_warning)
