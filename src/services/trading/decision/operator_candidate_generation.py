from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.config import Config
from src.services.trading.calendar import CalendarContextBuilder
from src.services.trading.decision.autonomous_orchestrator import AutonomousDecisionInputs
from src.services.trading.decision.policy_engine import TradeDecisionPolicyEngine
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleState,
    MT5PositionLifecycleSupervisor,
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder
from src.services.trading.market.live_feature_service import LiveFeatureService
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.regime_detector import MarketRegimeDetector
from src.services.trading.reasoning import MethodSelectorService
from src.services.trading.scoring import SignalScoringEngine


AUTONOMOUS_RUNTIME_MODE = "autonomous_live"


class OperatorCandidateInputError(RuntimeError):
    """Public-safe failure raised before the decision orchestrator is called."""


class AuthoritativeAutonomousInputAssembler:
    """Build one decision input from the repository's existing live pipeline."""

    def __init__(
        self,
        live_service: Any,
        *,
        feature_service: Any | None = None,
        calendar_builder: Any | None = None,
        regime_detector: Any | None = None,
        knowledge_router: Any | None = None,
        context_builder: Any | None = None,
        method_selector: Any | None = None,
        scoring_engine: Any | None = None,
        decision_engine: Any | None = None,
        lifecycle_supervisor: Any | None = None,
        mode: str = AUTONOMOUS_RUNTIME_MODE,
    ) -> None:
        self.live_service = live_service
        self.feature_service = feature_service or LiveFeatureService(
            bundle_builder=MarketSnapshotBundleBuilder(live_service.provider)
        )
        self.calendar_builder = calendar_builder or CalendarContextBuilder(
            live_service.calendar_provider
        )
        self.regime_detector = regime_detector or MarketRegimeDetector()
        self.knowledge_router = knowledge_router or KnowledgeRouter()
        self.context_builder = context_builder or RuntimeContextPackBuilder()
        self.method_selector = method_selector or MethodSelectorService()
        self.scoring_engine = scoring_engine or SignalScoringEngine()
        self.decision_engine = decision_engine or TradeDecisionPolicyEngine()
        self.lifecycle_supervisor = lifecycle_supervisor or MT5PositionLifecycleSupervisor()
        self.mode = mode

    def build(self, *, now: datetime | None = None) -> AutonomousDecisionInputs:
        evaluated_at = _utc(now)
        symbol = Config.MARKET_DEFAULT_SYMBOL
        try:
            feature_result = self.feature_service.build_features(
                symbol,
                Config.MARKET_DEFAULT_TIMEFRAMES,
                Config.MARKET_DEFAULT_CANDLE_COUNT,
            )
        except Exception as exc:
            raise OperatorCandidateInputError("MARKET_SNAPSHOT_UNAVAILABLE") from exc

        _validate_market_sources(
            feature_result,
            symbol=symbol,
            now=evaluated_at,
            max_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
        )

        try:
            calendar = self.calendar_builder.build(symbol=symbol, now=evaluated_at)
            feature = feature_result.feature_snapshot
            regime = self.regime_detector.detect(feature, calendar)
            knowledge = self.knowledge_router.route(
                self.mode, symbol, feature, calendar, regime
            )
            context = self.context_builder.build(
                knowledge,
                feature,
                calendar,
                regime,
                self.mode,
                symbol,
                feature.broker_symbol,
            )
            method = self.method_selector.select(context, mode=self.mode)
            score = self.scoring_engine.score(
                feature, calendar, regime, context, method, mode=self.mode
            )
            risk = self.decision_engine.decide(
                score,
                feature,
                calendar,
                regime,
                context,
                method,
                mode=self.mode,
            )
        except Exception as exc:
            raise OperatorCandidateInputError("STRUCTURED_RUNTIME_INPUT_UNAVAILABLE") from exc

        try:
            lifecycle_status = self.lifecycle_supervisor.run_once()
        except Exception as exc:
            raise OperatorCandidateInputError("LIFECYCLE_UNAVAILABLE") from exc

        inputs = AutonomousDecisionInputs(
            runtime_context=context,
            method_selection=method,
            score_report=score,
            risk_result=risk,
            lifecycle_status=lifecycle_status,
        )
        _validate_structured_inputs(
            inputs,
            now=evaluated_at,
            max_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
        )
        return inputs


def _validate_market_sources(
    feature_result: Any,
    *,
    symbol: str,
    now: datetime,
    max_age_seconds: int,
) -> None:
    bundle = getattr(feature_result, "bundle", None)
    quality = getattr(feature_result, "quality_report", None)
    feature = getattr(feature_result, "feature_snapshot", None)
    if bundle is None or quality is None or feature is None:
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_MISSING")
    health = getattr(bundle, "provider_health", None)
    if health is None or str(getattr(health, "status", "")) not in {"OK", "DEGRADED"}:
        raise OperatorCandidateInputError("MARKET_PROVIDER_UNAVAILABLE")
    quality_status = str(getattr(quality, "status", "")).upper()
    if quality_status == "STALE":
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_STALE")
    if quality_status in {"", "EMPTY"}:
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_MISSING")
    if quality_status == "INVALID" or getattr(bundle, "errors", None):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_INVALID")
    if getattr(bundle, "tick", None) is None:
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_MISSING")
    if not _fresh(getattr(bundle.tick, "timestamp", ""), now, max_age_seconds):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_STALE")
    if not getattr(bundle, "account_id_hash", ""):
        raise OperatorCandidateInputError("ACCOUNT_CONTEXT_UNAVAILABLE")
    broker_symbol = str(getattr(feature, "broker_symbol", ""))
    if (
        not broker_symbol
        or str(getattr(feature, "symbol", "")).upper() != symbol.upper()
        or str(getattr(bundle, "broker_symbol", "")) != broker_symbol
    ):
        raise OperatorCandidateInputError("SYMBOL_METADATA_MISSING")
    if not getattr(feature, "source_snapshot_ids", None):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_MISSING")
    if not _fresh(getattr(feature, "created_at", ""), now, max_age_seconds):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_STALE")


def _validate_structured_inputs(
    inputs: AutonomousDecisionInputs,
    *,
    now: datetime,
    max_age_seconds: int,
) -> None:
    context = inputs.runtime_context
    method = inputs.method_selection
    score = inputs.score_report
    risk = inputs.risk_result
    if not context.context_pack_id or not method.result_id or not score.score_report_id or risk is None:
        raise OperatorCandidateInputError("STRUCTURED_RUNTIME_INPUT_MISSING")
    if not context.source_refs or not method.source_refs or not score.source_refs:
        raise OperatorCandidateInputError("STRUCTURED_REASONING_EVIDENCE_MISSING")
    if not all(
        _fresh(value, now, max_age_seconds)
        for value in (context.created_at, method.created_at, score.created_at, risk.created_at)
    ):
        raise OperatorCandidateInputError("STRUCTURED_RUNTIME_INPUT_STALE")
    if (
        method.source_context_pack_id != context.context_pack_id
        or score.source_context_pack_id != context.context_pack_id
        or score.source_method_selection_id != method.result_id
        or risk.source_context_pack_id != context.context_pack_id
        or risk.source_method_selection_id != method.result_id
        or risk.source_score_report_id != score.score_report_id
    ):
        raise OperatorCandidateInputError("STRUCTURED_RUNTIME_REFERENCE_MISMATCH")
    _validate_lifecycle(inputs.lifecycle_status, now, max_age_seconds)
    reconciliation = inputs.reconciliation_result
    if reconciliation and (
        reconciliation.resulting_execution_state == "RESULT_UNKNOWN"
        or reconciliation.status not in {"CONFIRMED", "REJECTED", "NO_MATCH"}
        or reconciliation.evidence_classification
        in {"AMBIGUOUS_MATCH", "QUERY_FAILED", "RESULT_UNKNOWN"}
    ):
        raise OperatorCandidateInputError("RECONCILIATION_UNRESOLVED")


def _validate_lifecycle(
    status: MT5RuntimeSupervisorStatus, now: datetime, max_age_seconds: int
) -> None:
    if status.supervisor_status not in {"HEALTHY", "DEGRADED"} or not status.bridge_available:
        raise OperatorCandidateInputError("LIFECYCLE_UNAVAILABLE")
    if not status.account_context_match:
        raise OperatorCandidateInputError("ACCOUNT_CONTEXT_MISMATCH")
    if not _fresh(status.last_successful_cycle, now, max_age_seconds):
        raise OperatorCandidateInputError("LIFECYCLE_STALE")
    unsafe_states = {
        MT5LifecycleState.UNKNOWN.value,
        MT5LifecycleState.SUBMISSION_PENDING.value,
        MT5LifecycleState.RECONCILIATION_REQUIRED.value,
        MT5LifecycleState.INCONSISTENT.value,
    }
    if status.discrepancy_count or any(
        status.lifecycle_state_counts.get(state, 0) > 0 for state in unsafe_states
    ):
        raise OperatorCandidateInputError("LIFECYCLE_CONFLICT")


def _fresh(value: Any, now: datetime, max_age_seconds: int) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (now - parsed.astimezone(timezone.utc)).total_seconds()
        return -5 <= age <= max_age_seconds
    except (TypeError, ValueError):
        return False


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
