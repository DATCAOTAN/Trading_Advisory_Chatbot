from __future__ import annotations

import json
from pathlib import Path

from src.services.trading.decision.models import DecisionBlocker, TradeReadinessDecision, now_utc_iso
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.review import (
    HumanReviewArtifactBuilder,
    HumanReviewArtifactValidator,
    HumanReviewFormatter,
    review_status_for_action,
)
from src.services.trading.review.validator import expected_review_status
from src.services.trading.scoring.models import ScoreComponent, SignalScoreBreakdown, SignalScoreReport


SOURCE_REF = "data/knowledge_repository/book/al_brooks_price_action.pdf#p=12"


def test_review_status_maps_from_review_ready():
    assert review_status_for_action("REVIEW_READY") == "READY_FOR_REVIEW"


def test_review_status_maps_from_wait():
    assert review_status_for_action("WAIT") == "WAITING"


def test_review_status_maps_from_no_trade():
    assert review_status_for_action("NO_TRADE") == "NO_TRADE_CONTEXT"


def test_review_status_maps_from_blocked():
    assert review_status_for_action("BLOCKED") == "BLOCKED"


def test_review_status_maps_from_manage_existing_position():
    assert review_status_for_action("MANAGE_EXISTING_POSITION") == "MANAGE_EXISTING_POSITION"


def test_expected_review_status_unknown_for_unknown_action():
    assert expected_review_status("SOMETHING_ELSE") == "UNKNOWN"


def test_human_review_artifact_preserves_source_ids():
    artifact = _artifact()
    assert artifact.source_readiness_decision_id == "readiness_fixture"
    assert artifact.source_score_report_id == "score_fixture"
    assert artifact.source_method_selection_id == "method_selection_fixture"
    assert artifact.source_context_pack_id == "context_fixture"


def test_human_review_artifact_preserves_source_refs():
    assert SOURCE_REF in _artifact().source_refs


def test_human_review_artifact_includes_readiness_score():
    assert _artifact().readiness_score == 0.82


def test_human_review_artifact_includes_method_regime_calendar_summaries():
    artifact = _artifact()
    assert artifact.primary_method_id == "al_brooks_trend_pullback"
    assert artifact.primary_regime == "PULLBACK_UPTREND"
    assert artifact.calendar_risk_state == "CLEAR"


def test_human_review_artifact_includes_blockers_and_warnings():
    artifact = _artifact(action="BLOCKED", blockers=[DecisionBlocker(code="DATA_QUALITY_INVALID", severity="ERROR")])
    assert artifact.review_status == "BLOCKED"
    assert artifact.blockers


def test_component_score_summary_is_compact():
    artifact = _artifact()
    assert "technical_score" in artifact.component_score_summary
    assert "reasons" not in artifact.component_score_summary["technical_score"]


def test_review_card_markdown_is_generated():
    markdown = HumanReviewFormatter().to_markdown(_artifact())
    assert "Human Review Card" in markdown
    assert "READY_FOR_REVIEW" in markdown


def test_review_card_json_is_generated():
    card = HumanReviewFormatter().to_card(_artifact())
    assert card.as_dict()["status_label"] == "READY_FOR_REVIEW"
    assert card.payload_size_chars > 0


def test_review_card_contains_safe_sections():
    card = HumanReviewFormatter().to_card(_artifact()).as_dict()
    assert card["method_section"]["primary_method_id"] == "al_brooks_trend_pullback"
    assert card["market_section"]["primary_regime"] == "PULLBACK_UPTREND"
    assert card["calendar_section"]["calendar_risk_state"] == "CLEAR"


def test_validator_rejects_buy_sell():
    artifact = _artifact()
    artifact.warnings.append("contains_" + "buy")
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed
    assert any(issue.startswith("forbidden_marker") for issue in result.issues)


def test_validator_rejects_price_and_size_recommendation_markers():
    artifact = _artifact()
    artifact.reasons.extend(["entry_price", "stop_loss", "take_profit", "lot_size", "account_risk"])
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed
    assert any("entry_price" in issue for issue in result.issues)


def test_validator_rejects_order_submission_marker():
    artifact = _artifact()
    artifact.warnings.append("order" + "_send")
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed


def test_validator_rejects_executable_order_marker():
    artifact = _artifact()
    artifact.warnings.append("executable_order")
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed


def test_validator_rejects_raw_candles():
    artifact = _artifact()
    artifact.reasons.append("raw_candles")
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed


def test_validator_rejects_raw_full_book_or_report_text():
    artifact = _artifact()
    artifact.reasons.append("full_raw_book")
    artifact.warnings.append("full_raw_report")
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed


def test_validator_rejects_account_id_and_credentials_markers():
    artifact = _artifact()
    artifact.warnings.extend(["account_id", "api_key", "password"])
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed


def test_payload_size_bounded():
    artifact = _artifact()
    artifact.payload_size_chars = 999999
    result = HumanReviewArtifactValidator(max_payload_chars=12000).validate(artifact)
    assert not result.passed
    assert "payload_size_exceeds_limit" in result.issues


def test_review_status_must_match_readiness_action():
    artifact = _artifact()
    artifact.review_status = "WAITING"
    result = HumanReviewArtifactValidator().validate(artifact)
    assert not result.passed
    assert "review_status_action_mismatch" in result.issues


def test_builder_marks_invalid_artifact_blocked_when_validation_fails():
    readiness = _readiness_decision()
    readiness.warnings.append("contains_" + "buy")
    artifact = HumanReviewArtifactBuilder().build(readiness, _score_report(), _method_selection(), _context_pack())
    assert artifact.review_status == "BLOCKED"
    assert artifact.blockers


def test_wait_action_builds_waiting_artifact():
    artifact = _artifact(action="WAIT", score=0.62)
    assert artifact.review_status == "WAITING"


def test_no_trade_action_builds_no_trade_context_artifact():
    artifact = _artifact(action="NO_TRADE", score=0.42)
    assert artifact.review_status == "NO_TRADE_CONTEXT"


def test_manage_existing_position_action_builds_management_artifact():
    artifact = _artifact(action="MANAGE_EXISTING_POSITION")
    assert artifact.review_status == "MANAGE_EXISTING_POSITION"


def test_markdown_contains_no_forbidden_trade_markers():
    payload = HumanReviewFormatter().to_markdown(_artifact()).lower()
    assert "buy" not in payload
    assert "sell" not in payload
    assert "entry_price" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "lot_size" not in payload
    assert "account_risk" not in payload


def test_review_card_contains_no_forbidden_trade_markers():
    payload = json.dumps(HumanReviewFormatter().to_card(_artifact()).as_dict()).lower()
    assert "buy" not in payload
    assert "sell" not in payload
    assert "order" + "_send" not in payload
    assert "executable_order" not in payload


def test_review_builder_does_not_import_forbidden_runtime_dependencies():
    root = Path("src/services/trading/review")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "Meta" + "Trader5" not in text
    assert "live_data_service" not in text
    assert "LLMReasoningAdapter" not in text


def test_review_builder_has_no_order_submission_marker():
    root = Path("src/services/trading/review")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "order" + "_send(" not in text


def test_unit_test_does_not_reference_live_oanda_or_calendar_or_mt5_calls():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "api-fxtrade." + "oanda" not in text
    assert "ff_calendar" + "_thisweek" not in text
    assert "Meta" + "Trader5" not in text


def test_artifact_json_contains_no_raw_candles_or_full_text():
    payload = json.dumps(_artifact().as_dict()).lower()
    assert "raw_candles" not in payload
    assert "full_raw_book" not in payload
    assert "full_raw_report" not in payload


def test_card_source_section_has_counts_and_ids_only():
    section = HumanReviewFormatter().to_card(_artifact()).source_section
    assert section["source_refs_count"] == 1
    assert section["source_readiness_decision_id"] == "readiness_fixture"


def test_artifact_payload_size_is_set():
    assert _artifact().payload_size_chars > 0


def _artifact(
    action: str = "REVIEW_READY",
    score: float = 0.82,
    blockers: list[DecisionBlocker] | None = None,
):
    return HumanReviewArtifactBuilder().build(
        _readiness_decision(action=action, score=score, blockers=blockers),
        _score_report(score=score),
        _method_selection(),
        _context_pack(),
    )


def _readiness_decision(
    action: str = "REVIEW_READY",
    score: float = 0.82,
    blockers: list[DecisionBlocker] | None = None,
) -> TradeReadinessDecision:
    return TradeReadinessDecision(
        decision_id="readiness_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        action=action,
        readiness_score=score,
        confidence=0.78,
        grade="GOOD",
        primary_method_id="al_brooks_trend_pullback",
        selected_playbook_ids=["trend_pullback_v1"],
        blockers=blockers or [],
        warnings=["review_warning"],
        reasons=["score_above_review_ready_threshold"],
        source_score_report_id="score_fixture",
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
        source_regime_snapshot_id="regime_fixture",
        source_context_pack_id="context_fixture",
        source_method_selection_id="method_selection_fixture",
        source_refs=[SOURCE_REF],
    )


def _score_report(score: float = 0.82) -> SignalScoreReport:
    return SignalScoreReport(
        score_report_id="score_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_method_id="al_brooks_trend_pullback",
        supporting_method_ids=["risk_management_core"],
        selected_playbook_ids=["trend_pullback_v1"],
        components=_score_breakdown(score),
        final_context_score=score,
        grade="GOOD",
        warnings=["score_warning"],
        source_feature_snapshot_id="feature_fixture",
        source_calendar_context_id="calendar_fixture",
        source_regime_snapshot_id="regime_fixture",
        source_context_pack_id="context_fixture",
        source_method_selection_id="method_selection_fixture",
        source_refs=[SOURCE_REF],
    )


def _score_breakdown(score: float) -> SignalScoreBreakdown:
    component = ScoreComponent(name="technical_score", score=score, grade="GOOD", weight=1.0, weighted_score=score)
    empty = ScoreComponent(name="method_fit_score", score=score, grade="GOOD", weight=0.0, weighted_score=0.0)
    return SignalScoreBreakdown(
        technical_score=component,
        method_fit_score=empty,
        regime_alignment_score=ScoreComponent(name="regime_alignment_score"),
        macro_calendar_score=ScoreComponent(name="macro_calendar_score"),
        risk_context_score=ScoreComponent(name="risk_context_score"),
        data_quality_score=ScoreComponent(name="data_quality_score"),
        execution_feasibility_score=ScoreComponent(name="execution_feasibility_score"),
        final_context_score=score,
    )


def _method_selection() -> MethodSelectionResult:
    return MethodSelectionResult(
        result_id="method_selection_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        primary_method_id="al_brooks_trend_pullback",
        supporting_method_ids=["risk_management_core"],
        selected_playbook_ids=["trend_pullback_v1"],
        source_context_pack_id="context_fixture",
        source_refs=[SOURCE_REF],
    )


def _context_pack() -> RuntimeContextPack:
    return RuntimeContextPack(
        context_pack_id="context_fixture",
        created_at=now_utc_iso(),
        mode="autonomous_live",
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        feature_snapshot_summary={"feature_snapshot_id": "feature_fixture"},
        calendar_context_summary={"context_id": "calendar_fixture", "calendar_risk_state": "CLEAR"},
        market_regime_summary={"regime_snapshot_id": "regime_fixture", "primary_regime": "PULLBACK_UPTREND"},
        selected_method_cards=[{"method_id": "al_brooks_trend_pullback", "source_refs": [SOURCE_REF]}],
        selected_playbooks=[{"playbook_id": "trend_pullback_v1", "source_refs": [SOURCE_REF]}],
        source_refs=[SOURCE_REF],
    )
