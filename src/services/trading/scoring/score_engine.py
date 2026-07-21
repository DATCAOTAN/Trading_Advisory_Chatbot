from __future__ import annotations

import hashlib
import json

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.scoring.component_scores import (
    data_quality_component,
    feasibility_component,
    macro_calendar_component,
    method_fit_component,
    regime_alignment_component,
    risk_context_component,
    technical_component,
)
from src.services.trading.scoring.models import SignalScoreBreakdown, SignalScoreReport, grade_for_score, now_utc_iso
from src.services.trading.scoring.normalization import clamp
from src.services.trading.scoring.policies import ScoringPolicy
from src.services.trading.scoring.validator import SignalScoreValidator


class SignalScoringEngine:
    def __init__(self, policy: ScoringPolicy | None = None, validator: SignalScoreValidator | None = None):
        self.policy = policy or ScoringPolicy.from_config()
        self.validator = validator or SignalScoreValidator()

    def score(
        self,
        feature_snapshot: FeatureSnapshot,
        calendar_context: CalendarContext,
        market_regime: MarketRegimeSnapshot,
        context_pack: RuntimeContextPack,
        method_selection: MethodSelectionResult,
        mode: str | None = None,
    ) -> SignalScoreReport:
        selected_mode = mode or method_selection.mode or context_pack.mode
        weights = self.policy.resolve_weights(context_pack, method_selection)
        components = SignalScoreBreakdown(
            technical_score=technical_component(context_pack, method_selection, weights["technical_score"]),
            method_fit_score=method_fit_component(context_pack, method_selection, weights["method_fit_score"], self.policy),
            regime_alignment_score=regime_alignment_component(context_pack, method_selection, weights["regime_alignment_score"]),
            macro_calendar_score=macro_calendar_component(context_pack, method_selection, weights["macro_calendar_score"], self.policy),
            risk_context_score=risk_context_component(context_pack, method_selection, weights["risk_context_score"]),
            data_quality_score=data_quality_component(context_pack, method_selection, weights["data_quality_score"], self.policy),
            execution_feasibility_score=feasibility_component(context_pack, method_selection, weights["execution_feasibility_score"]),
        )
        component_list = [
            components.technical_score,
            components.method_fit_score,
            components.regime_alignment_score,
            components.macro_calendar_score,
            components.risk_context_score,
            components.data_quality_score,
            components.execution_feasibility_score,
        ]
        final_score = clamp(sum(item.weighted_score for item in component_list))
        blockers = list(method_selection.blockers) + list(context_pack.blockers)
        warnings = list(method_selection.warnings) + list(context_pack.warnings)
        for component in component_list:
            blockers.extend(component.blockers)
            warnings.extend(component.warnings)
        if components.data_quality_score.score < self.policy.min_data_quality:
            warnings.append("data_quality_below_minimum")
        if blockers:
            final_score = min(final_score, 0.49)
        components.final_context_score = final_score
        created_at = now_utc_iso()
        report = SignalScoreReport(
            score_report_id=_report_id(context_pack.context_pack_id, method_selection.result_id, created_at),
            created_at=created_at,
            mode=selected_mode,
            symbol=feature_snapshot.symbol,
            broker_symbol=feature_snapshot.broker_symbol,
            primary_method_id=method_selection.primary_method_id,
            supporting_method_ids=list(method_selection.supporting_method_ids),
            selected_playbook_ids=list(method_selection.selected_playbook_ids),
            components=components,
            final_context_score=final_score,
            grade=grade_for_score(final_score, bool(blockers)),
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            scoring_summary=_summary(final_score, method_selection.primary_method_id, market_regime.primary_regime, calendar_context.calendar_risk_state),
            source_feature_snapshot_id=feature_snapshot.feature_snapshot_id,
            source_calendar_context_id=calendar_context.context_id,
            source_regime_snapshot_id=market_regime.regime_snapshot_id,
            source_context_pack_id=context_pack.context_pack_id,
            source_method_selection_id=method_selection.result_id,
            source_refs=list(dict.fromkeys(list(context_pack.source_refs) + list(method_selection.source_refs))),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate(report)
        if not validation.passed:
            report.blockers.extend(validation.issues)
            report.grade = "BLOCKED"
            report.final_context_score = min(report.final_context_score, 0.49)
        return report


def _summary(score: float, method_id: str, regime: str, calendar_risk: str) -> str:
    return f"Context score {score:.2f} for method={method_id or 'none'}, regime={regime}, calendar_risk={calendar_risk}."


def _report_id(context_pack_id: str, method_selection_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{context_pack_id}|{method_selection_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"signal_score_{digest}"
