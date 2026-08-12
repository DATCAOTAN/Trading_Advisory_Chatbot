from __future__ import annotations

import json
from decimal import Decimal

import pytest

from src.services.semantic.conversational_context import (
    normalize_trade_instruction,
    resolve_conversational_context,
)
from src.services.trading.decision.conversational_authorization import (
    parse_conversational_trading_request,
)
from src.services.trading.proposal.editable_trade_draft import (
    EditableTradeDraftService,
    EditableTradeDraftStore,
    TradeDraftError,
    TradeDraftMarketEvidence,
    TradeDraftSizingConstraints,
    TradeParameterPatch,
)


def _evidence(symbol="XAUUSD", broker="XAUUSDm"):
    return TradeDraftMarketEvidence(
        reference="market_bundle_safe",
        observed_at="2026-08-03T00:00:00+00:00",
        canonical_symbol=symbol,
        broker_symbol=broker,
        bid=Decimal("100"),
        ask=Decimal("101"),
        atr=Decimal("2"),
        swing_high=Decimal("110"),
        swing_low=Decimal("90"),
        point=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1"),
        minimum_distance_points=Decimal("10"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        contract_size=Decimal("100"),
        account_equity=Decimal("10000"),
        free_margin=Decimal("9000"),
        account_reference="redacted_account_hash",
        account_environment="DEMO",
        freshness="COMPLETE",
    )


def _request(text, previous=None, conversation_id="conversation-safe"):
    context = resolve_conversational_context(text, previous)
    return parse_conversational_trading_request(
        text,
        conversation_id=conversation_id,
        context=context,
    ), context


@pytest.mark.parametrize(
    ("text", "action", "direction", "instruction"),
    [
        ("buy", "OPEN_POSITION", "BUY", True),
        ("hãy mở lệnh mua", "OPEN_POSITION", "BUY", True),
        ("enter long", "OPEN_POSITION", "BUY", True),
        ("sell", "OPEN_POSITION", "SELL", True),
        ("vào lệnh bán", "OPEN_POSITION", "SELL", True),
        ("open a sell", "OPEN_POSITION", "SELL", True),
        ("tìm cơ hội giao dịch", "GENERIC_TRADE", "", True),
        ("đóng lệnh", "CLOSE_POSITION", "", True),
        ("Buy là gì?", "", "", False),
        ("Có nên buy XAUUSD hiện tại không?", "", "", False),
        ("Nếu buy thì rủi ro gì?", "", "", False),
        ("Chỉ phân tích RSI, đừng buy", "", "", False),
        ("do not trade", "", "", False),
    ],
)
def test_trade_language_is_centralized_and_safe(text, action, direction, instruction):
    value = normalize_trade_instruction(text)
    assert (value.action, value.direction, value.instruction) == (
        action,
        direction,
        instruction,
    )


def test_inherited_symbol_and_explicit_timeframe_override(tmp_path):
    _, previous = _request("RSI 14 hiện tại của XAUUSDm trên H1 là bao nhiêu?")
    request, context = _request("hãy buy khi RSI 14 khung M1 > 10", previous)
    assert request is not None
    assert context.canonical_symbol == "XAUUSD"
    assert context.broker_symbol == "XAUUSDm"
    assert request.trade_action == "OPEN_POSITION"
    assert request.trade_direction == "BUY"
    assert request.strategy.timeframes == ("M1",)
    assert request.strategy.entry_rules[0].operator == "GREATER_THAN"
    assert request.strategy.entry_rules[0].constants == (10.0,)

    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    draft = service.build_or_load(
        request,
        conversation_id="conversation-safe",
        evidence=_evidence(),
    )
    assert draft.symbol.source == "CONVERSATION_INHERITED"
    assert draft.direction.value == "BUY"
    assert draft.stop.value["method"] == "ATR_MULTIPLE"
    assert draft.target.value["method"] == "REWARD_RISK_RATIO"
    assert draft.risk.value["fraction"] == Decimal("0.01")
    assert draft.sizing.value["proposed_volume"] is not None
    assert draft.account_scope.value == "DEMO"
    assert not draft.blockers
    assert draft.executable is False
    assert draft.execution_authority is False


def test_mandate_sizing_provenance_survives_protected_reload(tmp_path):
    request, _ = _request(
        "buy XAUUSDm when RSI 14 M1 > 10, demo account, confirm every trade"
    )
    assert request is not None
    store = EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    service = EditableTradeDraftService(
        store=store,
        sizing_constraints=TradeDraftSizingConstraints(
            maximum_risk_amount=Decimal("30"),
            maximum_volume=Decimal("0.05"),
            authority_reference="mandate-safe:v2",
        ),
    )

    draft = service.build_or_load(
        request, conversation_id="mandate-sizing", evidence=_evidence()
    )
    loaded = store.load(draft.draft_id, draft.revision)

    assert loaded == draft
    assert draft.risk.value == {
        "fraction": Decimal("0.01"),
        "amount": Decimal("100.00"),
        "policy_risk_amount": Decimal("100.00"),
        "mandate_maximum_risk": Decimal("30"),
        "authorized_risk_budget": Decimal("30"),
        "policy_version": "editable-trade-risk/v1",
    }
    assert draft.sizing.value["mandate_maximum_volume"] == Decimal("0.05")
    assert draft.sizing.value["broker_minimum_volume"] == Decimal("0.01")
    assert draft.sizing.value["broker_maximum_volume"] == Decimal("100")
    assert draft.sizing.value["broker_volume_step"] == Decimal("0.01")
    assert draft.sizing.value["proposed_volume"] == Decimal("0.05")
    assert draft.sizing.value["actual_risk_amount"] == Decimal("15.00")
    assert draft.sizing.value["sizing_authority_reference"] == "mandate-safe:v2"


def test_partial_completion_preserves_explicit_fields_and_only_supplies_stop(tmp_path):
    text = (
        "hãy buy XAUUSDm khi RSI 14 H1 > 55, TP 110, risk 1%, "
        "volume 0.2, tài khoản demo, xác nhận mỗi lệnh"
    )
    request, _ = _request(text)
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    draft = service.build_or_load(request, conversation_id="only-sl", evidence=_evidence())
    assert draft.stop.source == "STRATEGY_POLICY"
    assert draft.stop.value["method"] == "ATR_MULTIPLE"
    assert draft.target.source == "USER_EXPLICIT"
    assert draft.target.value["price"] == Decimal("110")
    assert draft.risk.source == "USER_EXPLICIT"
    assert draft.risk.value["fraction"] == Decimal("0.01")
    assert draft.sizing.source == "USER_EXPLICIT"
    assert draft.sizing.value["proposed_volume"] == Decimal("0.2")


def test_dependency_recalculation_and_immutable_revisions(tmp_path):
    request, _ = _request(
        "hãy buy XAUUSDm khi RSI 14 H1 > 55, ATR 14 x 1.5, RR 2, risk 1%, tài khoản demo"
    )
    store = EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    service = EditableTradeDraftService(store=store)
    first = service.build_or_load(request, conversation_id="patches", evidence=_evidence())
    original_stop = first.stop.value["price"]
    original_target = first.target.value["price"]
    original_volume = first.sizing.value["proposed_volume"]

    risk_edit = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(first.revision, risk_fraction=Decimal("0.005")),
        evidence=_evidence(),
    )
    assert risk_edit.revision == 2
    assert risk_edit.stop.value["price"] == original_stop
    assert risk_edit.target.value["price"] == original_target
    assert risk_edit.sizing.value["proposed_volume"] != original_volume
    assert risk_edit.risk.source == "USER_EDITED"

    rr_edit = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(risk_edit.revision, reward_risk_ratio=Decimal("3")),
        evidence=_evidence(),
    )
    assert rr_edit.revision == 3
    assert rr_edit.stop.value["price"] == original_stop
    assert rr_edit.target.value["price"] != original_target
    assert rr_edit.sizing.value["proposed_volume"] == risk_edit.sizing.value["proposed_volume"]
    with pytest.raises(TradeDraftError, match="DRAFT_REVISION_CONFLICT"):
        service.apply_patch(
            first.draft_id,
            TradeParameterPatch(first.revision, risk_fraction=Decimal("0.004")),
            evidence=_evidence(),
        )


def test_stop_edit_recalculates_rr_target_and_volume_but_fixed_target_is_preserved(tmp_path):
    request, _ = _request(
        "hãy buy XAUUSDm khi RSI 14 H1 > 55, TP 110, risk 1%, tài khoản demo"
    )
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    first = service.build_or_load(request, conversation_id="fixed-target", evidence=_evidence())
    updated = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(first.revision, stop_loss=Decimal("96")),
        evidence=_evidence(),
    )
    assert updated.stop.source == "USER_EDITED"
    assert updated.target.value["price"] == Decimal("110")
    assert updated.sizing.value["proposed_volume"] != first.sizing.value["proposed_volume"]

    rr_updated = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(updated.revision, reward_risk_ratio=Decimal("3")),
        evidence=_evidence(),
    )
    assert rr_updated.target.value["method"] == "REWARD_RISK_RATIO"
    assert rr_updated.target.value["price"] != Decimal("110")
    assert rr_updated.stop.value == updated.stop.value
    assert rr_updated.sizing.value == updated.sizing.value
    assert "TARGET_POLICY_CONFLICT" not in rr_updated.blockers


def test_explicit_volume_edit_recalculates_risk_only(tmp_path):
    request, _ = _request(
        "hãy buy XAUUSDm khi RSI 14 H1 > 55, ATR 14 x 1.5, RR 2, risk 1%, tài khoản demo"
    )
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    first = service.build_or_load(request, conversation_id="volume-edit", evidence=_evidence())
    updated = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(first.revision, requested_volume=Decimal("0.5")),
        evidence=_evidence(),
    )
    assert updated.stop.value == first.stop.value
    assert updated.target.value == first.target.value
    assert updated.sizing.value["proposed_volume"] == Decimal("0.5")
    assert updated.sizing.value["actual_risk_amount"] != first.sizing.value["actual_risk_amount"]


def test_direction_edit_refreshes_market_entry_and_only_direction_dependencies(tmp_path):
    request, _ = _request(
        "h\u00e3y buy XAUUSDm khi RSI 14 H1 > 55, ATR 14 x 1.5, RR 2, risk 1%, t\u00e0i kho\u1ea3n demo"
    )
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    first = service.build_or_load(request, conversation_id="direction-edit", evidence=_evidence())
    updated = service.apply_patch(
        first.draft_id,
        TradeParameterPatch(first.revision, direction="SELL"),
        evidence=_evidence(),
    )
    assert first.entry.value["reference_price"] == Decimal("101")
    assert updated.entry.value["reference_price"] == Decimal("100")
    assert updated.stop.value["price"] > Decimal("100")
    assert updated.target.value["price"] < Decimal("100")
    assert updated.risk.value == first.risk.value


def test_market_quality_blockers_are_authoritative(tmp_path):
    request, _ = _request(
        "h\u00e3y buy XAUUSDm khi RSI 14 H1 > 55, risk 1%, t\u00e0i kho\u1ea3n demo"
    )
    evidence = TradeDraftMarketEvidence(
        **{**_evidence().__dict__, "freshness": "PARTIAL", "blockers": ("INSUFFICIENT_COMPLETED_BARS",)}
    )
    draft = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    ).build_or_load(request, conversation_id="quality-block", evidence=evidence)
    assert "INSUFFICIENT_COMPLETED_BARS" in draft.blockers
    assert "MARKET_EVIDENCE_UNAVAILABLE" in draft.blockers
    assert draft.market_evidence_reference == ""


def test_conflicting_explicit_target_and_rr_are_preserved_and_blocked(tmp_path):
    request, _ = _request(
        "hãy buy XAUUSDm khi RSI 14 H1 > 55, SL 95, TP 110, RR 3, risk 1%, tài khoản demo"
    )
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    draft = service.build_or_load(request, conversation_id="conflict", evidence=_evidence())
    assert draft.stop.value["price"] == Decimal("95")
    assert draft.target.value["price"] == Decimal("110")
    assert "TARGET_POLICY_CONFLICT" in draft.blockers


def test_missing_symbol_is_preserved_without_xauusd_fallback(tmp_path):
    request, _ = _request("hãy buy khi RSI 14 M1 > 10")
    assert request is not None
    assert request.canonical_symbol == ""
    service = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    )
    draft = service.build_or_load(request, conversation_id="missing-symbol", evidence=None)
    assert draft.direction.value == "BUY"
    assert "SYMBOL_REQUIRED" in draft.blockers
    assert (draft.symbol.value or {}).get("canonical_symbol", "") == ""
    assert draft.symbol.value["timeframes"] == ("M1",)


@pytest.mark.parametrize(
    ("text", "context_blocker"),
    [
        ("h\u00e3y buy ETHUSD khi RSI 14 H1 > 55", "SYMBOL_UNRESOLVED"),
        ("h\u00e3y buy XAUUSDm khi RSI 14 H2 > 55", "TIMEFRAME_UNSUPPORTED"),
    ],
)
def test_unknown_context_values_fail_closed(text, context_blocker):
    request, context = _request(text)
    assert context_blocker in context.blockers
    assert request is not None
    assert context_blocker in request.blockers


def test_generic_trade_preserves_rule_without_inventing_direction(tmp_path):
    request, _ = _request("t\u00ecm c\u01a1 h\u1ed9i giao d\u1ecbch XAUUSDm khi RSI 14 H1 > 55")
    draft = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    ).build_or_load(request, conversation_id="generic", evidence=_evidence())
    assert draft.action.value == "GENERIC_TRADE"
    assert draft.direction.value is None
    assert "STRATEGY_DIRECTION_MISSING" in draft.blockers
    assert draft.entry.value["rules"]


def test_all_explicit_values_are_preserved_without_replacement(tmp_path):
    request, _ = _request(
        "h\u00e3y buy XAUUSDm khi RSI 14 H1 > 55, SL 95, TP 110, risk 1%, volume 0.2, t\u00e0i kho\u1ea3n demo"
    )
    draft = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    ).build_or_load(request, conversation_id="all-explicit", evidence=_evidence())
    assert draft.stop.value["price"] == Decimal("95")
    assert draft.target.value["price"] == Decimal("110")
    assert draft.risk.value["fraction"] == Decimal("0.01")
    assert draft.sizing.value["proposed_volume"] == Decimal("0.2")
    assert {draft.stop.source, draft.target.source, draft.risk.source, draft.sizing.source} == {"USER_EXPLICIT"}


def test_invalid_explicit_risk_is_preserved_and_blocked(tmp_path):
    request, _ = _request(
        "h\u00e3y buy XAUUSDm khi RSI 14 H1 > 55, SL 95, TP 110, risk 3%, t\u00e0i kho\u1ea3n demo"
    )
    draft = EditableTradeDraftService(
        store=EditableTradeDraftStore(tmp_path / "drafts.jsonl")
    ).build_or_load(request, conversation_id="invalid-risk", evidence=_evidence())
    assert draft.risk.value["fraction"] == Decimal("0.03")
    assert draft.risk.source == "USER_EXPLICIT"
    assert "RISK_LIMIT_EXCEEDED" in draft.blockers


def test_store_reload_integrity_duplicate_and_public_redaction(tmp_path):
    request, _ = _request(
        "hãy sell XAUUSDm khi RSI 14 H1 < 45, ATR 14 x 2, RR 2, risk 1%, tài khoản demo"
    )
    path = tmp_path / "drafts.jsonl"
    service = EditableTradeDraftService(store=EditableTradeDraftStore(path))
    draft = service.build_or_load(request, conversation_id="reload", evidence=_evidence())
    duplicate = service.build_or_load(request, conversation_id="reload", evidence=_evidence())
    assert duplicate == draft
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    reloaded = EditableTradeDraftStore(path).load(draft.draft_id)
    assert reloaded == draft
    public = draft.to_public_dict()
    assert "stop_loss" not in json.dumps(public)
    assert "account_reference" not in json.dumps(public)
    assert public["executable"] is False

    row = json.loads(path.read_text(encoding="utf-8"))
    row["draft"]["revision"] = 99
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(TradeDraftError, match="DRAFT_JOURNAL_INTEGRITY_INVALID"):
        EditableTradeDraftStore(path).load(draft.draft_id)


def test_questions_and_negations_do_not_create_trade_request():
    for text in ("Buy là gì?", "Nếu buy thì rủi ro gì?", "Chỉ phân tích RSI, đừng buy"):
        request, _ = _request(text)
        assert request is None or request.trade_action == ""
