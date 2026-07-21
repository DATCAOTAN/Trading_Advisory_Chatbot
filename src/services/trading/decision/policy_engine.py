from __future__ import annotations

import hashlib
import json

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.decision.models import DecisionBlocker, TradeReadinessDecision, now_utc_iso
from src.services.trading.decision.policies import TradeDecisionPolicy
from src.services.trading.decision.validator import TradeReadinessDecisionValidator
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport
from src.services.trading.scoring.normalization import clamp


class TradeDecisionPolicyEngine:
    def __init__(
        self,
        policy: TradeDecisionPolicy | None = None,
        validator: TradeReadinessDecisionValidator | None = None,
    ):
        self.policy = policy or TradeDecisionPolicy.from_config()
        self.validator = validator or TradeReadinessDecisionValidator()

    def decide(
        self,
        score_report: SignalScoreReport,
        feature_snapshot: FeatureSnapshot,
        calendar_context: CalendarContext,
        market_regime: MarketRegimeSnapshot,
        context_pack: RuntimeContextPack,
        method_selection: MethodSelectionResult,
        mode: str | None = None,
    ) -> TradeReadinessDecision:
        selected_mode = mode or score_report.mode or method_selection.mode or context_pack.mode
        readiness_score = clamp(score_report.final_context_score)
        blockers = _collect_blockers(score_report, feature_snapshot, calendar_context, market_regime, context_pack, method_selection)
        warnings = list(score_report.warnings) + list(feature_snapshot.warnings) + list(calendar_context.warnings) + list(market_regime.warnings)
        reasons: list[str] = []
        action = "UNKNOWN"

        data_quality = str(feature_snapshot.data_quality_status or "UNKNOWN")
        calendar_risk = str(calendar_context.calendar_risk_state or "UNKNOWN")
        regime = str(market_regime.primary_regime or "UNKNOWN")

        if self.policy.manage_if_open_position and _has_existing_position(context_pack, selected_mode):
            action = "MANAGE_EXISTING_POSITION"
            reasons.append("existing_position_management_context")
        elif data_quality in {"INVALID", "EMPTY"} and self.policy.block_on_invalid_data:
            action = "BLOCKED"
            blockers.append(_blocker(f"DATA_QUALITY_{data_quality}", "CRITICAL", "Market data quality is not usable.", "feature_snapshot"))
            reasons.append("hard_block_invalid_data")
        elif calendar_risk in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"}:
            if self.policy.block_on_immediate_high_impact:
                action = "BLOCKED"
                blockers.append(_blocker(f"CALENDAR_RISK_{calendar_risk}", "ERROR", "Immediate calendar risk blocks readiness.", "calendar_context"))
            else:
                action = "WAIT"
                warnings.append(f"calendar_risk_wait:{calendar_risk}")
            reasons.append("calendar_high_impact_boundary")
        elif regime == "UNKNOWN" and self.policy.block_on_unknown_regime:
            action = "BLOCKED"
            blockers.append(_blocker("UNKNOWN_REGIME", "ERROR", "Market regime is unknown.", "market_regime"))
            reasons.append("hard_block_unknown_regime")
        elif score_report.blockers and self.policy.block_on_scoring_blockers:
            action = "BLOCKED"
            blockers.append(_blocker("SCORING_BLOCKERS_PRESENT", "ERROR", "Signal score report contains blockers.", "score_report"))
            reasons.append("hard_block_scoring_blockers")
        elif calendar_risk == "UPCOMING_HIGH_IMPACT" and self.policy.wait_on_upcoming_high_impact:
            action = "WAIT"
            warnings.append("upcoming_high_impact_calendar_risk")
            reasons.append("wait_for_calendar_window")
        elif regime in {"CHOPPY", "RANGING"} and readiness_score < self.policy.review_ready_min_score and self.policy.wait_on_choppy_low_score:
            action = "WAIT" if readiness_score >= self.policy.no_trade_below_score else "NO_TRADE"
            warnings.append(f"weak_score_in_{regime.lower()}_regime")
            reasons.append("choppy_or_ranging_context_not_review_ready")
        elif readiness_score >= self.policy.review_ready_min_score and not blockers:
            action = "REVIEW_READY"
            reasons.append("score_above_review_ready_threshold")
        elif readiness_score < self.policy.no_trade_below_score:
            action = "NO_TRADE"
            reasons.append("score_below_no_trade_threshold")
        else:
            action = "WAIT"
            reasons.append("context_not_ready_but_not_blocked")

        created_at = now_utc_iso()
        decision = TradeReadinessDecision(
            decision_id=_decision_id(score_report.score_report_id, created_at),
            created_at=created_at,
            mode=selected_mode,
            symbol=feature_snapshot.symbol,
            broker_symbol=feature_snapshot.broker_symbol,
            action=action,
            readiness_score=readiness_score,
            confidence=_confidence(score_report, market_regime, method_selection),
            grade="BLOCKED" if action == "BLOCKED" else score_report.grade,
            primary_method_id=score_report.primary_method_id,
            selected_playbook_ids=list(score_report.selected_playbook_ids),
            blockers=list(_dedupe_blockers(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            reasons=list(dict.fromkeys(reasons)),
            source_score_report_id=score_report.score_report_id,
            source_feature_snapshot_id=feature_snapshot.feature_snapshot_id,
            source_calendar_context_id=calendar_context.context_id,
            source_regime_snapshot_id=market_regime.regime_snapshot_id,
            source_context_pack_id=context_pack.context_pack_id,
            source_method_selection_id=method_selection.result_id,
            source_refs=list(dict.fromkeys(list(score_report.source_refs) + list(context_pack.source_refs) + list(method_selection.source_refs))),
        )
        decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate(decision)
        if not validation.passed:
            decision.action = "BLOCKED"
            decision.grade = "BLOCKED"
            for issue in validation.issues:
                decision.blockers.append(_blocker(issue, "ERROR", "Decision validation failed.", "validator"))
            decision.blockers = list(_dedupe_blockers(decision.blockers))
            decision.payload_size_chars = len(json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True))
        return decision


def _collect_blockers(
    score_report: SignalScoreReport,
    feature_snapshot: FeatureSnapshot,
    calendar_context: CalendarContext,
    market_regime: MarketRegimeSnapshot,
    context_pack: RuntimeContextPack,
    method_selection: MethodSelectionResult,
) -> list[DecisionBlocker]:
    blockers: list[DecisionBlocker] = []
    for source, values in (
        ("score_report", score_report.blockers),
        ("feature_snapshot", feature_snapshot.blockers),
        ("calendar_context", calendar_context.errors),
        ("market_regime", market_regime.blockers),
        ("context_pack", context_pack.blockers),
        ("method_selection", method_selection.blockers),
    ):
        for value in values:
            blockers.append(_blocker(str(value), "ERROR", str(value), source))
    return blockers


def _has_existing_position(context_pack: RuntimeContextPack, mode: str) -> bool:
    if mode == "manage_existing_position":
        return True
    summary = context_pack.market_regime_summary or {}
    feature = context_pack.feature_snapshot_summary or {}
    return bool(summary.get("existing_position_detected") or feature.get("existing_position_detected"))


def _confidence(score_report: SignalScoreReport, market_regime: MarketRegimeSnapshot, method_selection: MethodSelectionResult) -> float:
    values = [score_report.final_context_score, market_regime.confidence, method_selection.confidence]
    return clamp(sum(clamp(value) for value in values) / max(1, len(values)))


def _blocker(code: str, severity: str, message: str, source: str) -> DecisionBlocker:
    return DecisionBlocker(code=code, severity=severity, message=message, source=source)


def _dedupe_blockers(blockers: list[DecisionBlocker]):
    seen = set()
    for blocker in blockers:
        key = (blocker.code, blocker.source)
        if key in seen:
            continue
        seen.add(key)
        yield blocker


def _decision_id(score_report_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{score_report_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"trade_readiness_{digest}"
