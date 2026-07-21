from __future__ import annotations

from typing import Any

from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.scoring.models import ScoreComponent, grade_for_score
from src.services.trading.scoring.normalization import clamp
from src.services.trading.scoring.policies import ScoringPolicy


def data_quality_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float, policy: ScoringPolicy) -> ScoreComponent:
    quality = str(context_pack.feature_snapshot_summary.get("data_quality_status") or "UNKNOWN")
    score_map = {"COMPLETE": 0.95, "PARTIAL": 0.62, "STALE": 0.35, "EMPTY": 0.05, "INVALID": 0.0}
    score = score_map.get(quality, 0.25)
    warnings = []
    blockers = []
    reasons = [f"data_quality:{quality}"]
    if quality == "PARTIAL":
        warnings.append("data_quality_partial")
    if quality in {"INVALID", "EMPTY"} and policy.block_on_invalid_data:
        blockers.append(f"DATA_QUALITY_{quality}")
    return _component("data_quality_score", score, weight, reasons, warnings, blockers, context_pack.source_refs)


def technical_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float) -> ScoreComponent:
    feature = context_pack.feature_snapshot_summary
    score = 0.5
    reasons = []
    warnings = []
    blockers = []
    trend_strength = _float(feature.get("trend_strength"))
    chop = _float(feature.get("range_chop_score"))
    score += min(0.2, trend_strength * 0.25)
    if feature.get("pullback_detected"):
        score += 0.08
        reasons.append("pullback_context_present")
    if feature.get("multi_timeframe_alignment") in {"ALIGNED_UP", "ALIGNED_DOWN"}:
        score += 0.08
        reasons.append("multi_timeframe_aligned")
    if feature.get("momentum_state") in {"BULLISH", "BEARISH"}:
        score += 0.05
        reasons.append("momentum_directional")
    if feature.get("spread_state") == "WIDE":
        score -= 0.25
        warnings.append("spread_wide")
    if feature.get("spread_state") == "UNKNOWN":
        score -= 0.1
        warnings.append("spread_unknown")
    if chop >= 0.72:
        score -= 0.25
        warnings.append("range_chop_elevated")
    if feature.get("volatility_state") == "EXTREME":
        score -= 0.15
        warnings.append("volatility_extreme")
    return _component("technical_score", score, weight, reasons or ["technical_context_scored"], warnings, blockers, context_pack.source_refs)


def method_fit_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float, policy: ScoringPolicy) -> ScoreComponent:
    assessment = next((item for item in method_selection.candidate_assessments if item.method_id == method_selection.primary_method_id), None)
    score = assessment.compatibility_score if assessment else method_selection.overall_context_fit
    reasons = ["method_assessment_score"]
    warnings = []
    blockers = []
    if not method_selection.primary_method_id:
        score = 0.0
        blockers.append("PRIMARY_METHOD_MISSING")
    if assessment and assessment.conflicts:
        score -= min(0.35, 0.12 * len(assessment.conflicts))
        warnings.extend(assessment.conflicts)
    if policy.block_on_unknown_method and method_selection.primary_method_id not in {item.get("method_id") for item in context_pack.selected_method_cards}:
        blockers.append("UNKNOWN_METHOD")
        score = 0.0
    return _component("method_fit_score", score, weight, reasons, warnings, blockers, method_selection.source_refs)


def regime_alignment_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float) -> ScoreComponent:
    regime = str(context_pack.market_regime_summary.get("primary_regime") or "UNKNOWN")
    method = next((item for item in context_pack.selected_method_cards if item.get("method_id") == method_selection.primary_method_id), {})
    playbooks = [item for item in context_pack.selected_playbooks if item.get("playbook_id") in set(method_selection.selected_playbook_ids)]
    score = 0.5
    reasons = []
    warnings = []
    blockers = []
    if regime in set(method.get("suitable_regimes", [])):
        score += 0.25
        reasons.append(f"method_regime_fit:{regime}")
    if regime in set(method.get("bad_regimes", [])):
        score -= 0.45
        blockers.append(f"method_bad_regime:{regime}")
    if any(regime in set(playbook.get("compatible_regimes", [])) or "ANY" in set(playbook.get("compatible_regimes", [])) for playbook in playbooks):
        score += 0.2
        reasons.append("playbook_regime_compatible")
    elif playbooks:
        score -= 0.25
        blockers.append("playbook_regime_incompatible")
    if regime in {"CHOPPY", "NEWS_RISK"}:
        warnings.append(f"regime_caution:{regime}")
    return _component("regime_alignment_score", score, weight, reasons or ["regime_alignment_scored"], warnings, blockers, context_pack.source_refs)


def macro_calendar_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float, policy: ScoringPolicy) -> ScoreComponent:
    risk_state = str(context_pack.calendar_context_summary.get("calendar_risk_state") or "UNKNOWN")
    score_map = {
        "CLEAR": 0.9,
        "UPCOMING_HIGH_IMPACT": 0.55,
        "IMMEDIATE_HIGH_IMPACT": 0.1,
        "EVENT_ACTIVE": 0.1,
        "POST_EVENT_COOLDOWN": 0.45,
        "UNKNOWN": 0.45,
    }
    score = score_map.get(risk_state, 0.45)
    warnings = []
    blockers = []
    reasons = [f"calendar_risk_state:{risk_state}"]
    if risk_state in {"UPCOMING_HIGH_IMPACT", "POST_EVENT_COOLDOWN", "UNKNOWN"}:
        warnings.append(f"calendar_risk_warning:{risk_state}")
    if risk_state in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"} and policy.block_on_immediate_high_impact:
        blockers.append(f"CALENDAR_RISK_{risk_state}")
    if context_pack.selected_macro_cards:
        score += 0.05
        reasons.append("macro_context_available")
    return _component("macro_calendar_score", score, weight, reasons, warnings, blockers, context_pack.source_refs)


def risk_context_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float) -> ScoreComponent:
    score = 0.55
    reasons = []
    warnings = list(method_selection.warnings)
    blockers = list(method_selection.blockers)
    method_cards = context_pack.selected_method_cards
    playbooks = context_pack.selected_playbooks
    if any("risk" in item.get("domains", []) or "risk" in item.get("method_id", "") for item in method_cards):
        score += 0.2
        reasons.append("risk_method_present")
    if any(item.get("no_trade_conditions") for item in playbooks):
        score += 0.1
        reasons.append("caution_conditions_present")
    if context_pack.market_regime_summary.get("volatility_state") == "EXTREME":
        score -= 0.2
        warnings.append("volatility_extreme")
    if context_pack.market_regime_summary.get("primary_regime") in {"CHOPPY", "NEWS_RISK"}:
        score -= 0.1
        warnings.append("regime_requires_caution")
    if blockers:
        score -= min(0.25, 0.08 * len(blockers))
    return _component("risk_context_score", score, weight, reasons or ["risk_context_scored"], warnings, blockers, context_pack.source_refs)


def feasibility_component(context_pack: RuntimeContextPack, method_selection: MethodSelectionResult, weight: float) -> ScoreComponent:
    feature = context_pack.feature_snapshot_summary
    quality = feature.get("data_quality_status")
    spread = feature.get("spread_state")
    score = 0.75
    reasons = []
    warnings = []
    blockers = []
    if quality == "COMPLETE":
        score += 0.15
        reasons.append("market_data_complete")
    elif quality in {"INVALID", "EMPTY"}:
        score = 0.0
        blockers.append(f"MARKET_DATA_{quality}")
        return _component("execution_feasibility_score", score, weight, reasons or ["context_feasibility_blocked"], warnings, blockers, context_pack.source_refs)
    else:
        score -= 0.2
        warnings.append(f"market_data_{quality}")
    if spread == "OK":
        score += 0.05
        reasons.append("spread_ok")
    elif spread == "WIDE":
        score -= 0.2
        warnings.append("spread_wide")
    else:
        score -= 0.1
        warnings.append("spread_unknown")
    if context_pack.blockers or method_selection.blockers:
        score -= min(0.3, 0.08 * (len(context_pack.blockers) + len(method_selection.blockers)))
    return _component("execution_feasibility_score", score, weight, reasons or ["context_feasibility_scored"], warnings, blockers, context_pack.source_refs)


def _component(name: str, score: float, weight: float, reasons: list[str], warnings: list[str], blockers: list[str], source_refs: list[str]) -> ScoreComponent:
    final_score = clamp(score)
    return ScoreComponent(
        name=name,
        score=final_score,
        grade=grade_for_score(final_score, bool(blockers)),
        weight=clamp(weight),
        weighted_score=clamp(final_score * weight),
        reasons=list(dict.fromkeys(reasons)),
        warnings=list(dict.fromkeys(warnings)),
        blockers=list(dict.fromkeys(blockers)),
        source_refs=list(dict.fromkeys(source_refs)),
    )


def _float(value: Any) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return number
    except Exception:
        return 0.0
