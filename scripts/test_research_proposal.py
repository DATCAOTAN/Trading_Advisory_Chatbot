from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest
from pydantic import ValidationError

from scripts.test_goal_only_research_brief import goal_payload
from scripts.test_trading_semantic_cutover import request_from, semantic
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.structured_semantics import StructuredSemanticResult
from src.services.trading.reasoning.strategy_evidence import conversation_trading_scope, strategy_identity
from src.services.trading.research.proposal import (
    EvidenceReference, ResearchContent, ResearchProposal, ResearchScope,
)


NOW = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)
SCOPE = ResearchScope(trading_scope=conversation_trading_scope("semantic-cutover"), account_ref="account_" + "1" * 24)
ACCEPT = "ACCEPTED_FOR_NEXT_RESEARCH_STAGE"


def plan():
    result = QueryPlanAssembler().assemble(
        "raw language is not a research contract",
        structured_semantics=StructuredSemanticResult.from_payload(goal_payload(
            research_goal={"objective": "Seek weekly profitability", "horizon": "weekly", "max_risk_per_trade_pct": 1},
            unresolved_fields=["research_goal.max_drawdown_pct"],
        )),
    )
    result.constraints["trading_scope"] = SCOPE.trading_scope
    return result


def create(content=None, *, verify=None, source=None, origin="AI_RESEARCHED"):
    return ResearchProposal.from_plan(
        source or plan(), scope=SCOPE, origin=origin, content=content or ResearchContent(),
        created_at=NOW, verify_evidence=verify,
    )


def change(proposal, content, *, parent=None, scope=SCOPE, verify=None):
    return proposal.revise(scope=scope, parent_revision_id=parent or proposal.head.revision_id,
                           author="USER_AUTHORED", content=content, created_at=NOW + timedelta(minutes=2),
                           verify_evidence=verify)


def evidence(status="VALIDATED", **changes):
    return EvidenceReference(**({
        "source_ref": "collection:research", "evidence_ref": "passage:17",
        "kind": "KNOWLEDGE", "stance": "SUPPORTS", "status": status,
        "data_quality": "DIRECT", "evaluation_version": "evidence/v1".replace("/", ":"),
    } | changes))


def test_m1_to_empty_proposal_is_scoped_non_executable_and_idempotent():
    source = plan()
    proposal = create(source=source)
    assert proposal == create(source=source)
    assert proposal.brief.goal.max_risk_per_trade_pct == 1
    assert proposal.brief.goal.horizon == "weekly"
    assert proposal.brief.requested_mode == "autonomous_live"
    assert proposal.brief.account_scope == "DEMO"
    assert proposal.brief.symbols == ("XAUUSD",)
    assert "research_goal.max_drawdown_pct" in proposal.brief.missing_information
    assert dict(proposal.brief.field_sources)["research_goal.max_risk_per_trade_pct"] == "USER_EXPLICIT"
    assert proposal.execution_allowed is False and proposal.head.content.strategy is None
    assert proposal.head.author == "AI_SUGGESTED"
    assert proposal.head.evidence_status() == "ABSENT"
    assert proposal.review_status(proposal.head.revision_id) == "DRAFT"
    assert ResearchProposal.replay(proposal.to_json(), scope=SCOPE).to_json() == proposal.to_json()
    assert "raw language" not in proposal.to_json()


def test_hypothesis_revision_preserves_history_and_rejects_a_stale_fork():
    first = create(ResearchContent(hypothesis="Test a session breakout"))
    second = change(first, ResearchContent(hypothesis="Test a range breakout", timeframes=("M15",)))
    assert first.head.content.hypothesis == "Test a session breakout"
    assert second.revisions == (first.head, second.head)
    assert second.head.parent_revision_id == first.head.revision_id
    assert second.head.author == "USER_AUTHORED"
    assert second.head.content_fingerprint != first.head.content_fingerprint
    assert change(second, second.head.content, parent=first.head.revision_id) is second
    assert change(second, second.head.content) is second
    with pytest.raises(ValueError, match="RESEARCH_REVISION_CONFLICT"):
        change(second, ResearchContent(hypothesis="Another stale branch"), parent=first.head.revision_id)


def test_optional_strategy_reuses_the_existing_identity_and_never_carries_a_live_mode():
    _, request = request_from(semantic())
    with pytest.raises(ValueError, match="RESEARCH_STRATEGY_SCOPE_CONFLICT"):
        create(ResearchContent(strategy=request.strategy))
    strategy = replace(request.strategy, requested_mode="advisory_only", confirmation_policy="NO_EXECUTION")
    strategy = replace(strategy, identity=strategy_identity(strategy))
    proposal = create(ResearchContent(strategy=strategy), origin="USER_DEFINED")
    replay = ResearchProposal.replay(proposal.to_json(), scope=SCOPE)
    assert replay.head.content.strategy.identity == strategy.identity
    assert replay.head.author == "USER_AUTHORED"
    no_rules = replace(strategy, entry_rules=())
    with pytest.raises(ValueError, match="RESEARCH_STRATEGY_NOT_ESTABLISHED"):
        ResearchContent(strategy=replace(no_rules, identity=strategy_identity(no_rules)))
    with pytest.raises(ValueError, match="RESEARCH_STRATEGY_INVALID"):
        ResearchContent(strategy=replace(strategy, identity=request.strategy.identity))


@pytest.mark.parametrize("status", ["PENDING", "UNSUITABLE"])
def test_unverified_evidence_does_not_allow_acceptance(status):
    proposal = create(ResearchContent(hypothesis="Test breakout", evidence=(evidence(status),)))
    assert proposal.head.evidence_status() == status
    assert proposal.review_status(proposal.head.revision_id) == "EVIDENCE_PENDING"
    with pytest.raises(ValueError, match="RESEARCH_REVIEW_INVALID"):
        proposal.review(scope=SCOPE, revision_id=proposal.head.revision_id, decision=ACCEPT, reviewed_at=NOW)


def test_validated_evidence_requires_an_owner_and_cannot_follow_a_changed_hypothesis():
    original = ResearchContent(hypothesis="Test breakout", evidence=(evidence(),))
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        create(original)

    def verify(scope, item, subject):
        return scope == SCOPE and item == original.evidence[0] and subject == original.hypothesis_fingerprint()

    proposal = create(original, verify=verify)
    assert proposal.review_status(proposal.head.revision_id) == "READY_FOR_REVIEW"
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        ResearchProposal.replay(proposal.to_json(), scope=SCOPE)
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_UNVERIFIED"):
        change(proposal, ResearchContent(hypothesis="Changed", evidence=original.evidence), verify=verify)
    assert ResearchProposal.replay(proposal.to_json(), scope=SCOPE, verify_evidence=verify) == proposal


def test_review_is_revision_specific_and_all_execution_writes_are_unreachable(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("research called a trading write boundary")

    for method in (
        "src.services.trading.proposal.editable_trade_draft.EditableTradeDraftService.build_or_load",
        "src.services.trading.decision.operator_candidate_generation.EditableTradeDraftCandidateService.create",
        "src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority.TradingAuthorityService.grant_mandate",
        "src.services.trading.decision.autonomous_runtime.AutonomousMonitorProcess.start",
        "src.services.trading.execution.mt5_live_adapter_pre_submit.adapter.MT5LiveAdapterDisabled.submit_controlled",
        "tools.mt5_bridge.execution.ControlledMT5ExecutionService._submit_once",
    ):
        monkeypatch.setattr(method, forbidden)

    supporting = evidence()
    contrary = evidence(evidence_ref="passage:18", stance="CONTRADICTS")
    content = ResearchContent(hypothesis="Test breakout", evidence=(supporting, contrary))
    def verify(scope, item, subject):
        return scope == SCOPE and item in content.evidence and subject == content.hypothesis_fingerprint()

    first = create(content, verify=verify)
    old_id = first.head.revision_id
    review = first.review(scope=SCOPE, revision_id=old_id, decision=ACCEPT, reviewed_at=NOW, verify_evidence=verify)
    assert review.review_status(old_id) == ACCEPT
    assert review.review(scope=SCOPE, revision_id=old_id, decision=ACCEPT, reviewed_at=NOW) is review
    with pytest.raises(ValueError, match="RESEARCH_REVIEW_CONFLICT"):
        review.review(scope=SCOPE, revision_id=old_id, decision="REJECTED", reviewed_at=NOW)
    newer = change(review, ResearchContent(hypothesis="Test breakout by session"), verify=verify)
    assert newer.reviews == review.reviews
    assert newer.review_status(old_id) == "SUPERSEDED"
    assert newer.review_status(newer.head.revision_id) == "EVIDENCE_PENDING"
    assert all(not item.execution_allowed for item in (first, review, newer))
    assert all(not item.execution_allowed for item in newer.revisions)
    assert ResearchProposal.replay(newer.to_json(), scope=SCOPE, verify_evidence=verify) == newer
    with pytest.raises(ValueError, match="RESEARCH_REVIEW_STALE"):
        newer.review(scope=SCOPE, revision_id=old_id, decision=ACCEPT, reviewed_at=NOW)


@pytest.mark.parametrize("other", [
    ResearchScope(trading_scope=conversation_trading_scope("another"), account_ref=SCOPE.account_ref),
    ResearchScope(trading_scope=SCOPE.trading_scope, account_ref="account_" + "2" * 24),
])
def test_cross_scope_revise_review_and_replay_are_rejected(other):
    proposal = create()
    with pytest.raises(ValueError, match="RESEARCH_SCOPE_MISMATCH"):
        ResearchProposal.replay(proposal.to_json(), scope=other)
    with pytest.raises(ValueError, match="RESEARCH_SCOPE_MISMATCH"):
        change(proposal, ResearchContent(hypothesis="Other scope"), scope=other)
    with pytest.raises(ValueError, match="RESEARCH_SCOPE_MISMATCH"):
        proposal.review(scope=other, revision_id=proposal.head.revision_id, decision="REJECTED", reviewed_at=NOW)


def test_replay_rejects_tampered_links_and_authority():
    first = create()
    second = change(first, ResearchContent(hypothesis="A new hypothesis"))
    with pytest.raises(ValidationError, match="RESEARCH_SCOPE_REQUIRED"):
        ResearchProposal.model_validate_json(second.to_json())
    payload = json.loads(second.to_json())
    payload["revisions"][1]["parent_revision_id"] = "revision_other"
    with pytest.raises(ValidationError, match="RESEARCH_REVISION_CHAIN_INVALID"):
        ResearchProposal.replay(json.dumps(payload), scope=SCOPE)
    payload = json.loads(second.to_json())
    payload["execution_allowed"] = True
    with pytest.raises(ValidationError):
        ResearchProposal.replay(json.dumps(payload), scope=SCOPE)
    payload = json.loads(second.to_json())
    payload["revisions"][1]["execution_allowed"] = True
    with pytest.raises(ValidationError):
        ResearchProposal.replay(json.dumps(payload), scope=SCOPE)


def test_unfinished_tester_and_private_document_payload_cannot_be_evidence():
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_NOT_VALIDATABLE"):
        evidence(kind="MT5_TESTER")
    with pytest.raises(ValidationError):
        evidence(private_document="private content")
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_CONFLICT"):
        ResearchContent(evidence=(evidence(), evidence(stance="CONTRADICTS")))
