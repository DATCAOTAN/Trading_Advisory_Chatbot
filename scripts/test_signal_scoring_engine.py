from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.reasoning.models import MethodCandidateAssessment, MethodSelectionResult
from src.services.trading.scoring import ScoringPolicy, SignalScoringEngine, SignalScoreValidator
from src.services.trading.scoring.component_scores import (
    data_quality_component,
    feasibility_component,
    macro_calendar_component,
    method_fit_component,
    regime_alignment_component,
    risk_context_component,
    technical_component,
)
from src.services.trading.scoring.models import grade_for_score, now_utc_iso
from src.services.trading.scoring.normalization import normalize_weights


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_scoring_policy_loads_defaults():
    policy = ScoringPolicy.from_config()
    assert abs(sum(policy.weights.values()) - 1.0) < 0.001
    assert policy.weights["technical_score"] > policy.weights["data_quality_score"]


def test_playbook_scoring_weights_override_defaults():
    policy = ScoringPolicy.from_config()
    context_pack = _context_pack(playbook_weights={"trend": 0.35, "alignment": 0.25, "calendar": 0.20})
    weights = policy.resolve_weights(context_pack, _method_selection())
    assert abs(sum(weights.values()) - 1.0) < 0.001
    assert weights["technical_score"] > policy.weights["technical_score"]


def test_weights_normalize_to_one():
    weights = normalize_weights({"a": 2.0, "b": 1.0})
    assert abs(sum(weights.values()) - 1.0) < 0.001
    assert round(weights["a"], 6) == 0.666667


def test_data_quality_complete_scores_high():
    component = data_quality_component(_context_pack(), _method_selection(), 0.1, ScoringPolicy())
    assert component.score >= 0.9
    assert not component.blockers


def test_data_quality_invalid_produces_blocker():
    component = data_quality_component(_context_pack(data_quality="INVALID"), _method_selection(), 0.1, ScoringPolicy())
    assert component.score == 0.0
    assert "DATA_QUALITY_INVALID" in component.blockers


def test_technical_score_handles_trend_pullback_fixture():
    component = technical_component(_context_pack(), _method_selection(), 0.2)
    assert component.score > 0.65
    assert "pullback_context_present" in component.reasons


def test_technical_score_penalizes_choppy_conflict():
    component = technical_component(_context_pack(range_chop_score=0.9), _method_selection(), 0.2)
    assert component.score < 0.65
    assert "range_chop_elevated" in component.warnings


def test_technical_score_penalizes_wide_spread():
    component = technical_component(_context_pack(spread_state="WIDE"), _method_selection(), 0.2)
    assert component.score < 0.65
    assert "spread_wide" in component.warnings


def test_method_fit_uses_method_selection_compatibility():
    component = method_fit_component(_context_pack(), _method_selection(compatibility=0.82), 0.2, ScoringPolicy())
    assert component.score == 0.82


def test_method_fit_penalizes_conflicts():
    component = method_fit_component(_context_pack(), _method_selection(conflicts=["feature_conflict"]), 0.2, ScoringPolicy())
    assert component.score < 0.82
    assert "feature_conflict" in component.warnings


def test_regime_alignment_high_for_compatible_regime():
    component = regime_alignment_component(_context_pack(regime="PULLBACK_UPTREND"), _method_selection(), 0.2)
    assert component.score > 0.75


def test_regime_alignment_low_for_bad_regime():
    component = regime_alignment_component(_context_pack(regime="CHOPPY"), _method_selection(), 0.2)
    assert component.score < 0.3
    assert component.blockers


def test_macro_calendar_clear_scores_high():
    component = macro_calendar_component(_context_pack(calendar_state="CLEAR"), _method_selection(), 0.15, ScoringPolicy())
    assert component.score >= 0.9
    assert not component.blockers


def test_macro_calendar_immediate_high_impact_blocks():
    component = macro_calendar_component(_context_pack(calendar_state="IMMEDIATE_HIGH_IMPACT"), _method_selection(), 0.15, ScoringPolicy())
    assert component.score <= 0.151
    assert "CALENDAR_RISK_IMMEDIATE_HIGH_IMPACT" in component.blockers


def test_post_event_cooldown_produces_warning():
    component = macro_calendar_component(_context_pack(calendar_state="POST_EVENT_COOLDOWN"), _method_selection(), 0.15, ScoringPolicy())
    assert "calendar_risk_warning:POST_EVENT_COOLDOWN" in component.warnings


def test_risk_context_includes_volatility_chop_warnings():
    component = risk_context_component(_context_pack(regime="CHOPPY", volatility_state="EXTREME"), _method_selection(), 0.1)
    assert "volatility_extreme" in component.warnings
    assert "regime_requires_caution" in component.warnings


def test_execution_feasibility_score_low_for_invalid_data():
    component = feasibility_component(_context_pack(data_quality="INVALID"), _method_selection(), 0.05)
    assert component.score == 0.0
    assert "MARKET_DATA_INVALID" in component.blockers


def test_final_score_is_weighted_sum_and_clamped():
    report = SignalScoringEngine(policy=ScoringPolicy()).score(
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    weighted = sum(
        item["weighted_score"]
        for name, item in report.components.as_dict().items()
        if name.endswith("_score") and isinstance(item, dict)
    )
    assert abs(report.final_context_score - min(1.0, weighted)) < 0.001
    assert 0.0 <= report.final_context_score <= 1.0


def test_grade_mapping_works():
    assert grade_for_score(0.9) == "EXCELLENT"
    assert grade_for_score(0.75) == "GOOD"
    assert grade_for_score(0.55) == "ACCEPTABLE"
    assert grade_for_score(0.2) == "WEAK"
    assert grade_for_score(0.8, blocked=True) == "BLOCKED"


def test_signal_score_report_preserves_source_ids_and_refs():
    report = SignalScoringEngine(policy=ScoringPolicy()).score(
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    assert report.source_feature_snapshot_id == "feature_fixture"
    assert report.source_calendar_context_id == "calendar_fixture"
    assert report.source_regime_snapshot_id == "regime_fixture"
    assert report.source_context_pack_id == "context_fixture"
    assert report.source_method_selection_id == "method_selection_fixture"
    assert SOURCE_REF in report.source_refs


def test_signal_score_report_contains_no_forbidden_trade_outputs():
    report = SignalScoringEngine(policy=ScoringPolicy()).score(
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    payload = json.dumps(report.as_dict()).lower()
    assert "buy" not in payload
    assert "sell" not in payload
    assert "trade_decision" not in payload
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_signal_score_report_contains_no_raw_candles_or_full_text():
    report = SignalScoringEngine(policy=ScoringPolicy()).score(
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    payload = json.dumps(report.as_dict()).lower()
    assert "raw_candles" not in payload
    assert "full_raw_book" not in payload
    assert "full_raw_report" not in payload


def test_validator_rejects_forbidden_marker():
    report = SignalScoringEngine(policy=ScoringPolicy()).score(
        _feature_snapshot(),
        _calendar_context(),
        _regime_snapshot(),
        _context_pack(),
        _method_selection(),
    )
    report.warnings.append("contains_" + "buy")
    result = SignalScoreValidator().validate(report)
    assert not result.passed
    assert any(issue.startswith("forbidden_marker") for issue in result.issues)


def test_signal_scoring_engine_does_not_import_forbidden_runtime_dependencies():
    root = Path("src/services/trading/scoring")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text
    assert "LLMReasoningAdapter" not in text


def test_signal_scoring_engine_has_no_order_submission_marker():
    root = Path("src/services/trading/scoring")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "order" + "_send(" not in text


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def _feature_snapshot(
    data_quality: str = "COMPLETE",
    spread_state: str = "OK",
    range_chop_score: float = 0.22,
    volatility_state: str = "NORMAL",
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
        volatility_state=volatility_state,
        momentum_state="BULLISH",
        pullback_detected=True,
        breakout_candidate=False,
        range_chop_score=range_chop_score,
        multi_timeframe_alignment="ALIGNED_UP",
        spread_state=spread_state,
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


def _regime_snapshot(regime: str = "PULLBACK_UPTREND", volatility_state: str = "NORMAL") -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        regime_snapshot_id="regime_fixture",
        created_at=now_utc_iso(),
        symbol="XAUUSD",
        primary_regime=regime,
        secondary_regimes=[],
        confidence=0.78,
        trend_direction="UP",
        volatility_state=volatility_state,
        momentum_state="BULLISH",
        range_chop_score=0.22,
        pullback_detected=True,
        multi_timeframe_alignment="ALIGNED_UP",
        calendar_risk_state="CLEAR",
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
    )


def _context_pack(
    data_quality: str = "COMPLETE",
    spread_state: str = "OK",
    calendar_state: str = "CLEAR",
    regime: str = "PULLBACK_UPTREND",
    range_chop_score: float = 0.22,
    volatility_state: str = "NORMAL",
    playbook_weights: dict[str, float] | None = None,
) -> RuntimeContextPack:
    return RuntimeContextPack(
        context_pack_id="context_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={
            "feature_snapshot_id": "feature_fixture",
            "data_quality_status": data_quality,
            "trend_direction": "UP",
            "trend_strength": 0.72,
            "volatility_state": volatility_state,
            "momentum_state": "BULLISH",
            "pullback_detected": True,
            "range_chop_score": range_chop_score,
            "multi_timeframe_alignment": "ALIGNED_UP",
            "spread_state": spread_state,
        },
        calendar_context_summary={
            "context_id": "calendar_fixture",
            "calendar_risk_state": calendar_state,
        },
        market_regime_summary={
            "regime_snapshot_id": "regime_fixture",
            "primary_regime": regime,
            "volatility_state": volatility_state,
            "range_chop_score": range_chop_score,
        },
        selected_method_cards=[
            {
                "method_id": "al_brooks_trend_pullback",
                "method_name": "Trend Pullback",
                "domains": ["price_action"],
                "suitable_regimes": ["PULLBACK_UPTREND", "TRENDING_UP"],
                "bad_regimes": ["CHOPPY"],
                "source_refs": [SOURCE_REF],
            },
            {
                "method_id": "risk_management_core",
                "method_name": "Risk Framework",
                "domains": ["risk"],
                "suitable_regimes": ["ANY"],
                "bad_regimes": [],
                "source_refs": [SOURCE_REF],
            },
        ],
        selected_macro_cards=[
            {
                "macro_id": "usd_high_impact_calendar_risk",
                "title": "USD High Impact Calendar Risk",
                "source_refs": [SOURCE_REF],
            }
        ],
        selected_playbooks=[
            {
                "playbook_id": "trend_pullback_v1",
                "method_id": "al_brooks_trend_pullback",
                "compatible_regimes": ["PULLBACK_UPTREND", "TRENDING_UP"],
                "no_trade_conditions": ["immediate_high_impact_calendar_risk"],
                "scoring_weights": playbook_weights or {},
                "source_refs": [SOURCE_REF],
            }
        ],
        source_refs=[SOURCE_REF],
    )


def _method_selection(compatibility: float = 0.82, conflicts: list[str] | None = None) -> MethodSelectionResult:
    return MethodSelectionResult(
        result_id="method_selection_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        primary_method_id="al_brooks_trend_pullback",
        supporting_method_ids=["risk_management_core"],
        rejected_method_ids=[],
        selected_playbook_ids=["trend_pullback_v1"],
        relevant_macro_ids=["usd_high_impact_calendar_risk"],
        overall_context_fit=compatibility,
        confidence=0.77,
        candidate_assessments=[
            MethodCandidateAssessment(
                method_id="al_brooks_trend_pullback",
                method_name="Trend Pullback",
                role="PRIMARY_CANDIDATE",
                compatibility_score=compatibility,
                conflicts=conflicts or [],
                source_refs=[SOURCE_REF],
            )
        ],
        source_context_pack_id="context_fixture",
        source_refs=[SOURCE_REF],
    )
