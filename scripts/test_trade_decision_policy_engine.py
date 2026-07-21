from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.decision import TradeDecisionPolicy, TradeDecisionPolicyEngine, TradeReadinessDecisionValidator
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport, now_utc_iso


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_trade_decision_policy_loads_defaults():
    policy = TradeDecisionPolicy.from_config()
    assert policy.review_ready_min_score == 0.70
    assert policy.no_trade_below_score == 0.55
    assert policy.block_on_invalid_data is True


def test_invalid_data_quality_returns_blocked():
    decision = _engine().decide(
        _score_report(0.88),
        _feature_snapshot(data_quality="INVALID"),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(data_quality="INVALID"),
        _method_selection(),
    )
    assert decision.action == "BLOCKED"
    assert any(item.code == "DATA_QUALITY_INVALID" for item in decision.blockers)


def test_immediate_high_impact_calendar_risk_returns_blocked_by_default():
    decision = _engine().decide(
        _score_report(0.88),
        _feature_snapshot(),
        _calendar_context("IMMEDIATE_HIGH_IMPACT"),
        _regime_snapshot(calendar_risk="IMMEDIATE_HIGH_IMPACT"),
        _context_pack(calendar_state="IMMEDIATE_HIGH_IMPACT"),
        _method_selection(),
    )
    assert decision.action == "BLOCKED"
    assert any("CALENDAR_RISK_IMMEDIATE_HIGH_IMPACT" == item.code for item in decision.blockers)


def test_immediate_high_impact_can_return_wait_when_policy_allows():
    policy = TradeDecisionPolicy(block_on_immediate_high_impact=False)
    decision = TradeDecisionPolicyEngine(policy=policy).decide(
        _score_report(0.88),
        _feature_snapshot(),
        _calendar_context("EVENT_ACTIVE"),
        _regime_snapshot(calendar_risk="EVENT_ACTIVE"),
        _context_pack(calendar_state="EVENT_ACTIVE"),
        _method_selection(),
    )
    assert decision.action == "WAIT"


def test_signal_score_report_blockers_return_blocked():
    decision = _engine().decide(
        _score_report(0.88, blockers=["score_blocker"]),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    assert decision.action == "BLOCKED"
    assert any(item.code == "SCORING_BLOCKERS_PRESENT" for item in decision.blockers)


def test_high_score_with_no_blockers_returns_review_ready():
    decision = _engine().decide(
        _score_report(0.82),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    assert decision.action == "REVIEW_READY"
    assert "score_above_review_ready_threshold" in decision.reasons


def test_low_score_returns_no_trade():
    decision = _engine().decide(
        _score_report(0.42),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    assert decision.action == "NO_TRADE"


def test_upcoming_high_impact_risk_returns_wait():
    decision = _engine().decide(
        _score_report(0.82),
        _feature_snapshot(),
        _calendar_context("UPCOMING_HIGH_IMPACT"),
        _regime_snapshot(calendar_risk="UPCOMING_HIGH_IMPACT"),
        _context_pack(calendar_state="UPCOMING_HIGH_IMPACT"),
        _method_selection(),
    )
    assert decision.action == "WAIT"
    assert "upcoming_high_impact_calendar_risk" in decision.warnings


def test_choppy_regime_with_weak_score_returns_wait_or_no_trade():
    decision = _engine().decide(
        _score_report(0.61),
        _feature_snapshot(range_chop_score=0.84),
        _calendar_context(),
        _regime_snapshot(regime="CHOPPY", range_chop_score=0.84),
        _context_pack(regime="CHOPPY", range_chop_score=0.84),
        _method_selection(),
    )
    assert decision.action in {"WAIT", "NO_TRADE"}
    assert any("choppy" in item for item in decision.reasons + decision.warnings)


def test_source_ids_are_preserved():
    decision = _valid_decision()
    assert decision.source_score_report_id == "score_fixture"
    assert decision.source_feature_snapshot_id == "feature_fixture"
    assert decision.source_calendar_context_id == "calendar_fixture"
    assert decision.source_regime_snapshot_id == "regime_fixture"
    assert decision.source_context_pack_id == "context_fixture"
    assert decision.source_method_selection_id == "method_selection_fixture"


def test_source_refs_are_preserved():
    decision = _valid_decision()
    assert SOURCE_REF in decision.source_refs


def test_readiness_score_is_clamped():
    decision = _engine().decide(
        _score_report(1.8),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    assert decision.readiness_score == 1.0


def test_confidence_is_clamped():
    decision = _engine().decide(
        _score_report(0.82),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(confidence=2.0),
        _context_pack(),
        _method_selection(confidence=2.0),
    )
    assert 0.0 <= decision.confidence <= 1.0


def test_decision_payload_contains_no_buy_or_sell():
    payload = json.dumps(_valid_decision().as_dict()).lower()
    assert "buy" not in payload
    assert "sell" not in payload


def test_decision_payload_contains_no_price_or_size_recommendations():
    payload = json.dumps(_valid_decision().as_dict()).lower()
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_decision_payload_contains_no_order_submission_marker():
    payload = json.dumps(_valid_decision().as_dict()).lower()
    assert "order" + "_send" not in payload
    assert "executable_order" not in payload


def test_decision_payload_contains_no_raw_candles_or_full_text():
    payload = json.dumps(_valid_decision().as_dict()).lower()
    assert "raw_candles" not in payload
    assert "full_raw_book" not in payload
    assert "full_raw_report" not in payload


def test_validator_rejects_forbidden_marker():
    decision = _valid_decision()
    decision.warnings.append("contains_" + "buy")
    result = TradeReadinessDecisionValidator().validate(decision)
    assert not result.passed
    assert any(issue.startswith("forbidden_marker") for issue in result.issues)


def test_policy_engine_does_not_import_forbidden_runtime_dependencies():
    root = Path("src/services/trading/decision")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text
    assert "LLMReasoningAdapter" not in text


def test_policy_engine_has_no_order_submission_marker():
    root = Path("src/services/trading/decision")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "order" + "_send(" not in text


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def test_manage_existing_position_mode_returns_manage_action():
    decision = _engine().decide(
        _score_report(0.82, mode="manage_existing_position"),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(mode="manage_existing_position"),
        _method_selection(mode="manage_existing_position"),
        mode="manage_existing_position",
    )
    assert decision.action == "MANAGE_EXISTING_POSITION"


def _engine() -> TradeDecisionPolicyEngine:
    return TradeDecisionPolicyEngine(policy=TradeDecisionPolicy())


def _valid_decision():
    return _engine().decide(
        _score_report(0.82),
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )


def _score_report(score: float, blockers: list[str] | None = None, mode: str = "autonomous_live") -> SignalScoreReport:
    return SignalScoreReport(
        score_report_id="score_fixture",
        created_at=now_utc_iso(),
        mode=mode,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_method_id="al_brooks_trend_pullback",
        supporting_method_ids=["risk_management_core"],
        selected_playbook_ids=["trend_pullback_v1"],
        final_context_score=score,
        grade="GOOD" if score >= 0.70 else "WEAK",
        blockers=blockers or [],
        warnings=[],
        scoring_summary="Context readiness score only.",
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
        source_regime_snapshot_id="regime_fixture",
        source_context_pack_id="context_fixture",
        source_method_selection_id="method_selection_fixture",
        source_refs=[SOURCE_REF],
    )


def _feature_snapshot(
    data_quality: str = "COMPLETE",
    range_chop_score: float = 0.22,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_snapshot_id="feature_fixture",
        created_at=now_utc_iso(),
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        provider_name="mt5_bridge",
        timeframes=["M15", "H1", "H4"],
        primary_timeframe="M15",
        indicator_snapshots={},
        trend_direction="UP",
        trend_strength=0.72,
        volatility_state="NORMAL",
        momentum_state="BULLISH",
        pullback_detected=True,
        range_chop_score=range_chop_score,
        multi_timeframe_alignment="ALIGNED_UP",
        spread_state="OK",
        data_quality_status=data_quality,
        source_snapshot_ids=["bundle_fixture"],
    )


def _calendar_context(state: str = "CLEAR") -> CalendarContext:
    return CalendarContext(
        context_id="calendar_fixture",
        symbol="XAUUSD",
        created_at=now_utc_iso(),
        provider_name="forex_factory",
        calendar_risk_state=state,
        cache_status="HIT",
        source="forex_factory",
    )


def _regime_snapshot(
    regime: str = "PULLBACK_UPTREND",
    range_chop_score: float = 0.22,
    calendar_risk: str = "CLEAR",
    confidence: float = 0.78,
) -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        regime_snapshot_id="regime_fixture",
        created_at=now_utc_iso(),
        symbol="XAUUSD",
        primary_regime=regime,
        confidence=confidence,
        trend_direction="UP",
        volatility_state="NORMAL",
        momentum_state="BULLISH",
        range_chop_score=range_chop_score,
        pullback_detected=True,
        multi_timeframe_alignment="ALIGNED_UP",
        calendar_risk_state=calendar_risk,
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
    )


def _context_pack(
    mode: str = "autonomous_live",
    data_quality: str = "COMPLETE",
    calendar_state: str = "CLEAR",
    regime: str = "PULLBACK_UPTREND",
    range_chop_score: float = 0.22,
) -> RuntimeContextPack:
    return RuntimeContextPack(
        context_pack_id="context_fixture",
        created_at=now_utc_iso(),
        mode=mode,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={
            "feature_snapshot_id": "feature_fixture",
            "data_quality_status": data_quality,
            "range_chop_score": range_chop_score,
            "spread_state": "OK",
        },
        calendar_context_summary={"context_id": "calendar_fixture", "calendar_risk_state": calendar_state},
        market_regime_summary={"regime_snapshot_id": "regime_fixture", "primary_regime": regime, "range_chop_score": range_chop_score},
        selected_method_cards=[{"method_id": "al_brooks_trend_pullback", "source_refs": [SOURCE_REF]}],
        selected_playbooks=[{"playbook_id": "trend_pullback_v1", "source_refs": [SOURCE_REF]}],
        source_refs=[SOURCE_REF],
    )


def _method_selection(mode: str = "autonomous_live", confidence: float = 0.77) -> MethodSelectionResult:
    return MethodSelectionResult(
        result_id="method_selection_fixture",
        created_at=now_utc_iso(),
        mode=mode,
        symbol="XAUUSD",
        primary_method_id="al_brooks_trend_pullback",
        selected_playbook_ids=["trend_pullback_v1"],
        overall_context_fit=0.82,
        confidence=confidence,
        source_context_pack_id="context_fixture",
        source_refs=[SOURCE_REF],
    )
