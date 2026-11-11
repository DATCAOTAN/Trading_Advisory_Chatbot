from decimal import Decimal

import pytest

from scripts.test_autonomous_decision_orchestrator import NOW, service
from scripts.test_deterministic_autonomous_strategy_authority import _assembler
from scripts.test_editable_trade_draft_candidate_lifecycle import _evidence
from scripts.test_trading_semantic_cutover import request_from, semantic
from src.services.semantic.resolved_semantics import resolve_structured_semantics
from src.services.trading.decision.operator_candidate_generation import EditableTradeDraftCandidateService
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraftService,
    EditableTradeDraftStore,
    TradeParameterPatch,
)


PARAMETERS = {
    "stop_loss": {"value": "99.00", "unit": "PRICE"},
    "take_profit": {"value": "105.00", "unit": "PRICE"},
    "risk": {"value": "0.50", "unit": "PERCENT"},
    "volume": {"value": "0.01", "unit": "LOT"},
}


def _source(parameters=PARAMETERS, **changes):
    return semantic(
        trade_parameters=parameters,
        explicit_fields=[*semantic().explicit_fields, *(f"trade_parameters.{key}" for key in parameters)],
        **changes,
    )


def _draft_service(tmp_path):
    return EditableTradeDraftService(EditableTradeDraftStore(tmp_path / "drafts.jsonl"))


def _build(drafts, request, evidence=None):
    return drafts.build_or_load(request, conversation_id="semantic-cutover", evidence=evidence or _evidence())


@pytest.mark.parametrize("signal, blocker", [(True, ""), (False, "ENTRY_CONDITION_FALSE"), (None, "ENTRY_CONDITION_UNKNOWN")])
def test_canonical_conditional_preview_to_candidate_uses_current_bound_result(tmp_path, signal, blocker):
    _, request = request_from(_source(), "sl 12 tp 13 risk 0.9 lot 10")
    request = type(request).from_public_dict(request.to_public_dict())
    drafts = _draft_service(tmp_path)
    draft = _build(drafts, request)
    assert not draft.blockers
    assert draft.stop.value["price"] == Decimal("99")
    assert draft.target.value["price"] == Decimal("105")
    assert draft.risk.value["fraction"] == Decimal("0.005")
    assert draft.risk.value["requested_input"] == {"value": "0.50", "unit": "PERCENT", "source": "USER_EXPLICIT"}
    assert not draft.executable and not draft.execution_authority

    assembler, provider, method = _assembler()
    assembler.mode = request.requested_mode
    features = assembler.feature_service.value.feature_snapshot
    features.reasoning_evidence_v2.strategy_identity = request.strategy.identity
    features.reasoning_evidence_v2.features.data_quality = {"rule_results": [signal]}
    orchestrator = service(tmp_path / "candidate")
    result = EditableTradeDraftCandidateService(drafts.store, assembler, orchestrator).create(
        draft.draft_id, draft.revision, strategy=request.strategy,
        authoritative_mode="human_confirmed_live", account_environment="DEMO",
        mode_integrity_valid=True, now=NOW,
    )

    assert result.blocker == blocker
    assert provider.calls == 0
    if blocker:
        assert orchestrator.journal.records() == []
        assert not method.calls
    else:
        assert result.status == "CANDIDATE_CREATED"
        candidate = result.run_result.candidate
        assert (candidate.stop_loss, candidate.take_profit, candidate.proposed_volume) == ("99", "105", "0.01")
        assert candidate.intent == "OPEN_POSITION"
        assert not candidate.execution_authority and not candidate.order_sent
        assert len(orchestrator.journal.records()) == 1


@pytest.mark.parametrize("direction, stop, target", [("BUY", "99", "105"), ("SELL", "102", "96")])
def test_canonical_direct_open_keeps_typed_prices_without_needing_entry_rule(tmp_path, direction, stop, target):
    _, request = request_from(_source(
        {**PARAMETERS, "stop_loss": {"value": stop, "unit": "PRICE"},
         "take_profit": {"value": target, "unit": "PRICE"}},
        primary_intent="TRADE_LIFECYCLE", indicators=[], conditions=[], direction=direction,
    ))
    assert request.strategy is None
    request = type(request).from_public_dict(request.to_public_dict())
    drafts = _draft_service(tmp_path)
    draft = _build(drafts, request)
    assert not draft.blockers
    assert draft.entry.value["immediate_entry"] is True
    assembler, provider, _method = _assembler()
    assembler.mode = request.requested_mode
    features = assembler.feature_service.value.feature_snapshot
    features.reasoning_evidence_v2 = None
    result = EditableTradeDraftCandidateService(drafts.store, assembler, service(tmp_path / "candidate")).create(
        draft.draft_id, draft.revision, strategy=None, authoritative_mode="human_confirmed_live",
        account_environment="DEMO", mode_integrity_valid=True, now=NOW,
    )
    assert result.status == "CANDIDATE_CREATED", result.blocker
    candidate = result.run_result.candidate
    assert (candidate.order_type, candidate.stop_loss, candidate.take_profit) == (direction, stop, target)
    assert provider.calls == 0


@pytest.mark.parametrize(("item", "fraction", "blocker"), [
    ({"value": 0, "unit": "PERCENT"}, Decimal(0), "TRADE_PARAMETER_RISK_INVALID"),
    ({"value": "0.5"}, None, "TRADE_PARAMETER_RISK_UNRESOLVED"),
    ({"value": "0.5", "unit": "USD"}, None, "TRADE_PARAMETER_RISK_UNIT_UNSUPPORTED"),
    ({"value": "abc", "unit": "FRACTION"}, None, "TRADE_PARAMETER_RISK_INVALID"),
    ({"value": -1, "unit": "PERCENT"}, Decimal("-0.01"), "TRADE_PARAMETER_RISK_INVALID"),
    ({"value": 100, "unit": "PERCENT"}, Decimal(1), "RISK_LIMIT_EXCEEDED"),
    (None, None, "TRADE_PARAMETER_RISK_UNRESOLVED"),
])
def test_zero_missing_or_invalid_risk_never_gets_default(tmp_path, item, fraction, blocker):
    _, request = request_from(_source({**PARAMETERS, "risk": item}))
    drafts = _draft_service(tmp_path)
    draft = _build(drafts, request)
    assert draft.risk.value["fraction"] == fraction
    assert blocker in draft.blockers
    assert draft.target.value["price"] == Decimal("105")
    revised = drafts.apply_patch(draft.draft_id, TradeParameterPatch(expected_revision=draft.revision, requested_volume=Decimal("0.02")), evidence=_evidence())
    assert revised.risk.value == draft.risk.value
    assert blocker in revised.blockers


def test_explicit_context_inherits_parameters_but_new_request_never_inherits_old_draft(tmp_path):
    previous = resolve_structured_semantics(_source())
    drafts = _draft_service(tmp_path)
    _, initial = request_from(_source(), "first")
    _build(drafts, initial)

    _, new = request_from(semantic(), "second", previous=previous)
    clean = _build(drafts, new)
    assert "requested_input" not in clean.stop.value
    assert "requested_input" not in clean.risk.value

    _, followup = request_from(_source({"risk": {"value": "0.003", "unit": "FRACTION"}}, context_references=["previous_trade_parameters"]), "third", previous=previous)
    inherited = _build(drafts, followup)
    assert inherited.stop.value["price"] == Decimal("99")
    assert inherited.stop.source == "CONVERSATION_INHERITED"
    assert inherited.risk.source == "USER_EXPLICIT"
    assert inherited.risk.value["fraction"] == Decimal("0.003")


def test_unresolved_unit_preserves_requested_value_and_valid_siblings(tmp_path):
    _, request = request_from(_source(unresolved_fields=["trade_parameters.risk.unit"]))
    draft = _build(_draft_service(tmp_path), request)
    assert draft.stop.value["price"] == Decimal("99")
    assert draft.risk.value["fraction"] is None
    assert draft.risk.value["requested_input"]["value"] == "0.50"
    assert "TRADE_PARAMETER_RISK_UNRESOLVED" in draft.blockers


def test_fresh_candidate_quote_cannot_exceed_explicit_draft_risk_budget(tmp_path):
    _, request = request_from(_source({**PARAMETERS, "risk": {"value": "0.02", "unit": "PERCENT"}}))
    drafts = _draft_service(tmp_path)
    draft = _build(drafts, request)
    assert not draft.blockers
    assembler, provider, _method = _assembler(tick_change={"ask": "101.01"})
    assembler.mode = request.requested_mode
    features = assembler.feature_service.value.feature_snapshot
    features.reasoning_evidence_v2.strategy_identity = request.strategy.identity
    features.reasoning_evidence_v2.features.data_quality = {"rule_results": [True]}
    orchestrator = service(tmp_path / "candidate")
    result = EditableTradeDraftCandidateService(drafts.store, assembler, orchestrator).create(
        draft.draft_id, draft.revision, strategy=request.strategy,
        authoritative_mode="human_confirmed_live", account_environment="DEMO",
        mode_integrity_valid=True, now=NOW,
    )
    assert result.blocker == "RISK_LIMIT_EXCEEDED"
    assert orchestrator.journal.records() == []
    assert provider.calls == 0
