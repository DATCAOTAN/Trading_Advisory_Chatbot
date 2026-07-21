from __future__ import annotations

import hashlib
import json

from src.services.trading.calendar.models import CalendarContext
from src.services.trading.decision.models import TradeReadinessDecision
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.review.models import HumanReviewArtifact, now_utc_iso
from src.services.trading.review.validator import HumanReviewArtifactValidator
from src.services.trading.scoring.models import SignalScoreReport


class HumanReviewArtifactBuilder:
    def __init__(self, validator: HumanReviewArtifactValidator | None = None):
        self.validator = validator or HumanReviewArtifactValidator()

    def build(
        self,
        readiness_decision: TradeReadinessDecision,
        score_report: SignalScoreReport,
        method_selection: MethodSelectionResult,
        context_pack: RuntimeContextPack,
        market_regime: MarketRegimeSnapshot | None = None,
        calendar_context: CalendarContext | None = None,
        feature_snapshot: FeatureSnapshot | None = None,
    ) -> HumanReviewArtifact:
        created_at = now_utc_iso()
        artifact = HumanReviewArtifact(
            artifact_id=_artifact_id(readiness_decision.decision_id, created_at),
            created_at=created_at,
            mode=readiness_decision.mode,
            symbol=readiness_decision.symbol,
            broker_symbol=readiness_decision.broker_symbol,
            review_status=review_status_for_action(readiness_decision.action),
            readiness_action=readiness_decision.action,
            readiness_score=readiness_decision.readiness_score,
            confidence=readiness_decision.confidence,
            grade=readiness_decision.grade,
            primary_method_id=readiness_decision.primary_method_id,
            supporting_method_ids=list(method_selection.supporting_method_ids),
            selected_playbook_ids=list(readiness_decision.selected_playbook_ids or method_selection.selected_playbook_ids),
            primary_regime=_primary_regime(context_pack, market_regime),
            calendar_risk_state=_calendar_risk(context_pack, calendar_context),
            final_context_score=score_report.final_context_score,
            component_score_summary=_component_summary(score_report),
            reasons=list(readiness_decision.reasons),
            warnings=list(dict.fromkeys(list(readiness_decision.warnings) + list(score_report.warnings))),
            blockers=[item.as_dict() for item in readiness_decision.blockers],
            source_refs=list(dict.fromkeys(list(readiness_decision.source_refs) + list(score_report.source_refs) + list(context_pack.source_refs))),
            source_readiness_decision_id=readiness_decision.decision_id,
            source_score_report_id=score_report.score_report_id,
            source_method_selection_id=method_selection.result_id,
            source_context_pack_id=context_pack.context_pack_id,
        )
        artifact.payload_size_chars = len(json.dumps(artifact.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate(artifact)
        if not validation.passed:
            artifact.review_status = "BLOCKED"
            artifact.blockers.extend({"code": issue, "severity": "ERROR", "message": "Review artifact validation failed.", "source": "validator"} for issue in validation.issues)
            artifact.payload_size_chars = len(json.dumps(artifact.as_dict(), ensure_ascii=False, sort_keys=True))
        return artifact


def review_status_for_action(action: str) -> str:
    mapping = {
        "REVIEW_READY": "READY_FOR_REVIEW",
        "WAIT": "WAITING",
        "NO_TRADE": "NO_TRADE_CONTEXT",
        "BLOCKED": "BLOCKED",
        "MANAGE_EXISTING_POSITION": "MANAGE_EXISTING_POSITION",
    }
    return mapping.get(str(action or ""), "UNKNOWN")


def _component_summary(score_report: SignalScoreReport) -> dict[str, dict]:
    if not score_report.components:
        return {}
    result: dict[str, dict] = {}
    for name, value in score_report.components.as_dict().items():
        if not isinstance(value, dict):
            continue
        result[name] = {
            "score": value.get("score", 0.0),
            "grade": value.get("grade", "UNKNOWN"),
            "warnings_count": len(value.get("warnings", []) or []),
            "blockers_count": len(value.get("blockers", []) or []),
        }
    return result


def _primary_regime(context_pack: RuntimeContextPack, market_regime: MarketRegimeSnapshot | None) -> str:
    if market_regime:
        return market_regime.primary_regime
    return str((context_pack.market_regime_summary or {}).get("primary_regime") or "UNKNOWN")


def _calendar_risk(context_pack: RuntimeContextPack, calendar_context: CalendarContext | None) -> str:
    if calendar_context:
        return calendar_context.calendar_risk_state
    return str((context_pack.calendar_context_summary or {}).get("calendar_risk_state") or "UNKNOWN")


def _artifact_id(decision_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{decision_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"human_review_{digest}"
