from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from src.config import Config
from src.services.trading.decision.autonomous_proposal_provider import (
    AutonomousOrderProposalProvider,
    AutonomousOrderProposalRequest,
    AutonomousOrderProposalResult,
    market_snapshot_from_feature_result,
    valid_autonomous_order_proposal_bindings,
)
from src.services.trading.calendar import CalendarContextBuilder
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionInputs,
    AutonomousDecisionOrchestrator,
    AutonomousDecisionRunResult,
    AutonomousOrderIntentProposal,
    EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
    MANUAL_OPERATOR_PROPOSAL_SOURCE,
    OPERATOR_PROPOSAL_SOURCES,
    _ORDER_TYPE_SEMANTICS,
    autonomous_account_context_reference,
    autonomous_market_snapshot_provenance_hash,
)
from src.services.trading.decision.policy_engine import TradeDecisionPolicyEngine
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleState,
    MT5PositionLifecycleSupervisor,
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.knowledge import KnowledgeRouter, RuntimeContextPackBuilder
from src.services.trading.market.live_feature_service import LiveFeatureService
from src.services.trading.market.market_snapshot_bundle import MarketSnapshotBundleBuilder
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.market.regime_detector import MarketRegimeDetector
from src.services.trading.reasoning import MethodSelectorService
from src.services.trading.reasoning.strategy_evidence import (
    ConversationalStrategyRequest,
    evaluate_strategy_rule,
    plan_strategy_data,
    validate_strategy,
)
from src.services.trading.scoring import SignalScoringEngine
from src.services.trading.proposal.editable_trade_draft import (
    build_deterministic_strategy_draft,
    EditableTradeDraft,
    EditableTradeDraftStore,
    market_evidence_from_live_result,
    TradeDraftError,
)


AUTONOMOUS_RUNTIME_MODE = "autonomous_live"
BTCUSD_OPERATOR_TIMEFRAMES = ("M1", "H1", "H4")


def operator_timeframe_profile(symbol: str) -> tuple[str, ...]:
    return (
        BTCUSD_OPERATOR_TIMEFRAMES
        if str(symbol).strip().upper() == "BTCUSD"
        else tuple(Config.MARKET_DEFAULT_TIMEFRAMES)
    )


@dataclass(frozen=True)
class ManualOperatorProposalInput:
    order_type: str
    entry_price: str = ""
    trigger_price: str = ""
    limit_price: str = ""
    stop_loss: str = ""
    take_profit: str = ""
    proposed_volume: str = ""
    proposal_source: str = MANUAL_OPERATOR_PROPOSAL_SOURCE
    proposal_source_reference: str = ""


class OperatorCandidateInputError(RuntimeError):
    """Public-safe failure raised before the decision orchestrator is called."""

    def __init__(self, *blockers: str, evidence_summary: str = "") -> None:
        self.blockers = tuple(dict.fromkeys(str(item) for item in blockers if item))
        self.evidence_summary = str(evidence_summary or "")[:2000]
        super().__init__(
            ",".join(self.blockers) or "STRUCTURED_RUNTIME_INPUT_UNAVAILABLE"
        )


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
        proposal_provider: Any | None = None,
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
        self.proposal_provider = proposal_provider or AutonomousOrderProposalProvider()
        self.mode = mode

    def build(
        self,
        *,
        symbol: str | None = None,
        timeframes: Iterable[str] | None = None,
        now: datetime | None = None,
        operator_proposal: ManualOperatorProposalInput | None = None,
        strategy: ConversationalStrategyRequest | None = None,
        strategy_direction: str = "",
        strategy_action: str = "",
    ) -> AutonomousDecisionInputs:
        market_evaluated_at = _utc(now)
        symbol = str(symbol or Config.MARKET_DEFAULT_SYMBOL).strip().upper()
        if strategy is not None:
            strategy_issues = validate_strategy(strategy)
            if (
                strategy_issues
                or strategy.canonical_symbol != symbol
                or strategy.requested_mode != self.mode
            ):
                raise OperatorCandidateInputError(
                    *(
                        strategy_issues
                        or (
                            "STRATEGY_MODE_MISMATCH"
                            if strategy.requested_mode != self.mode
                            else "STRATEGY_SYMBOL_MISMATCH"
                        ,)
                    )
                )
            data_plan = plan_strategy_data(strategy)
            selected_timeframes = strategy.timeframes
            candle_count: Any = data_plan.candle_counts()
        else:
            data_plan = None
            selected_timeframes = tuple(timeframes or Config.MARKET_DEFAULT_TIMEFRAMES)
            candle_count = Config.MARKET_DEFAULT_CANDLE_COUNT
        try:
            if strategy is None:
                feature_result = self.feature_service.build_features(
                    symbol, selected_timeframes, candle_count
                )
            else:
                feature_result = self.feature_service.build_features(
                    symbol,
                    selected_timeframes,
                    candle_count,
                    strategy=strategy,
                    data_plan=data_plan,
                )
        except Exception as exc:
            raise OperatorCandidateInputError("MARKET_SNAPSHOT_UNAVAILABLE") from exc

        if strategy is not None:
            evidence = getattr(
                feature_result.feature_snapshot, "reasoning_evidence_v2", None
            )
            if evidence is None or evidence.strategy_identity != strategy.identity:
                raise OperatorCandidateInputError("STRATEGY_EVIDENCE_BINDING_INVALID")

        _validate_market_sources(
            feature_result,
            symbol=symbol,
            now=market_evaluated_at,
            max_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
        )

        try:
            calendar = self.calendar_builder.build(symbol=symbol, now=market_evaluated_at)
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
            method = self.method_selector.select(
                context,
                mode=self.mode,
                use_llm=(
                    False
                    if operator_proposal is not None
                    or _is_deterministic_autonomous_strategy(
                        strategy, strategy_direction, strategy_action, self.mode
                    )
                    else None
                ),
            )
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
            timeframe_profile=tuple(
                getattr(feature_result.feature_snapshot, "timeframes", ())
                or selected_timeframes
                or Config.MARKET_DEFAULT_TIMEFRAMES
            ),
            account_context_reference=autonomous_account_context_reference(
                feature_result.bundle.account_id_hash
            ),
            strategy_id=(strategy.identity.strategy_id if strategy else ""),
            strategy_version=(strategy.identity.strategy_version if strategy else ""),
            normalized_strategy_hash=(
                strategy.identity.normalized_strategy_hash if strategy else ""
            ),
            reasoning_evidence_summary=_reasoning_evidence_summary(feature_result),
        )
        handoff_evaluated_at = (
            _utc(now) if now is not None else datetime.now(timezone.utc)
        )
        _validate_structured_inputs(
            inputs,
            now=handoff_evaluated_at,
            max_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
        )
        if operator_proposal is not None:
            return _manual_inputs(
                operator_proposal,
                feature_result,
                inputs,
            )

        if _is_deterministic_autonomous_strategy(
            strategy, strategy_direction, strategy_action, self.mode
        ):
            assert strategy is not None
            return self._deterministic_strategy_inputs(
                strategy=strategy,
                strategy_direction=strategy_direction,
                strategy_action=strategy_action,
                feature_result=feature_result,
                inputs=inputs,
            )

        proposal_result = self.proposal_provider.produce(
            AutonomousOrderProposalRequest(
                feature_result=feature_result,
                runtime_context=context,
                method_selection=method,
                score_report=score,
                risk_decision=risk,
                evaluated_at=handoff_evaluated_at,
                maximum_age_seconds=Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS,
            )
        )
        evidence_summary = _with_proposal_observability(
            inputs.reasoning_evidence_summary, proposal_result
        )
        if proposal_result.proposal_status == "VALID_NO_PROPOSAL":
            raise OperatorCandidateInputError(
                "VALID_NO_PROPOSAL",
                *proposal_result.reason_codes,
                evidence_summary=evidence_summary,
            )
        try:
            _validate_proposal_result(proposal_result, feature_result, inputs)
        except OperatorCandidateInputError as exc:
            raise OperatorCandidateInputError(
                *exc.blockers, evidence_summary=evidence_summary
            ) from exc
        return AutonomousDecisionInputs(
            runtime_context=context,
            method_selection=method,
            score_report=score,
            risk_result=risk,
            lifecycle_status=lifecycle_status,
            direction=proposal_result.direction,
            semantic_parameter_references=proposal_result.semantic_parameter_references,
            order_proposal=proposal_result.order_proposal,
            order_market_snapshot=proposal_result.order_market_snapshot,
            timeframe_profile=inputs.timeframe_profile,
            account_context_reference=inputs.account_context_reference,
            proposal_source_reference=proposal_result.proposal_reference,
            strategy_id=inputs.strategy_id,
            strategy_version=inputs.strategy_version,
            normalized_strategy_hash=inputs.normalized_strategy_hash,
            reasoning_evidence_summary=evidence_summary,
        )

    def _deterministic_strategy_inputs(
        self,
        *,
        strategy: ConversationalStrategyRequest,
        strategy_direction: str,
        strategy_action: str,
        feature_result: Any,
        inputs: AutonomousDecisionInputs,
    ) -> AutonomousDecisionInputs:
        try:
            account = self.live_service.provider.get_account()
        except Exception as exc:
            raise OperatorCandidateInputError("ACCOUNT_CONTEXT_UNAVAILABLE") from exc
        if (
            not getattr(account, "redacted", False)
            or not getattr(account, "account_id_hash", "")
            or account.account_id_hash != feature_result.bundle.account_id_hash
        ):
            raise OperatorCandidateInputError("ACCOUNT_CONTEXT_MISMATCH")
        if str(getattr(account, "account_environment", "UNKNOWN")).upper() != "DEMO":
            raise OperatorCandidateInputError("DEMO_ACCOUNT_SCOPE_REQUIRED")
        evidence = market_evidence_from_live_result(
            feature_result,
            account,
            primary_timeframe=strategy.timeframes[0],
            account_environment=getattr(account, "account_environment", "UNKNOWN"),
        )
        try:
            draft = build_deterministic_strategy_draft(
                strategy,
                direction=strategy_direction,
                action=strategy_action,
                broker_symbol=feature_result.feature_snapshot.broker_symbol,
                evidence=evidence,
            )
        except TradeDraftError as exc:
            raise OperatorCandidateInputError(str(exc)) from exc
        if draft.blockers:
            raise OperatorCandidateInputError(*draft.blockers)
        entry = dict(draft.entry.value or {})
        stop = dict(draft.stop.value or {})
        target = dict(draft.target.value or {})
        sizing = dict(draft.sizing.value or {})
        values = (
            entry.get("reference_price"),
            stop.get("price"),
            target.get("price"),
            sizing.get("proposed_volume"),
        )
        if any(value is None for value in values):
            raise OperatorCandidateInputError("DETERMINISTIC_PROPOSAL_INCOMPLETE")
        return _manual_inputs(
            ManualOperatorProposalInput(
                order_type=str(strategy_direction).upper(),
                stop_loss=_canonical_manual_decimal(values[1]),
                take_profit=_canonical_manual_decimal(values[2]),
                proposed_volume=_canonical_manual_decimal(values[3]),
                proposal_source=EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
                proposal_source_reference=(
                    f"{draft.draft_id}:{draft.revision}:{draft.market_evidence_reference}"
                ),
            ),
            feature_result,
            inputs,
        )


def _reasoning_evidence_summary(feature_result: Any) -> str:
    evidence = getattr(feature_result.feature_snapshot, "reasoning_evidence_v2", None)
    if evidence is None:
        return ""
    payload = {
        "regime": evidence.regime,
        "regime_confidence": evidence.regime_confidence,
        "scores": dict(evidence.setup.scores),
        "hard_blockers": list(evidence.setup.hard_blockers),
        "indicator_values": {
            key: dict(value)
            for key, value in evidence.features.indicator_values.items()
        },
        "reasons": [item.as_dict() for item in evidence.reasons[:12]],
        "history": [item.as_dict() for item in evidence.history],
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _is_deterministic_autonomous_strategy(
    strategy: ConversationalStrategyRequest | None,
    direction: str,
    action: str,
    mode: str,
) -> bool:
    return bool(
        strategy is not None
        and mode == AUTONOMOUS_RUNTIME_MODE
        and strategy.requested_mode == AUTONOMOUS_RUNTIME_MODE
        and not strategy.semantic_unresolved_fields
        and strategy.entry_rules
        and str(direction).upper() in {"BUY", "SELL"}
        and str(action).upper() == "OPEN_POSITION"
    )


def strategy_monitor_projection(
    strategy: ConversationalStrategyRequest, evidence_summary: str
) -> dict[str, Any]:
    try:
        evidence = json.loads(evidence_summary or "{}")
    except json.JSONDecodeError:
        return {}
    if not strategy.entry_rules or not isinstance(evidence, dict):
        return {}
    rule = strategy.entry_rules[0]
    values = evidence.get("indicator_values")
    if not isinstance(values, dict):
        return {}
    indicator = next(
        (item for item in strategy.indicators if item.output_alias == rule.left),
        None,
    )
    observed = values.get(rule.left)
    if indicator is None or not isinstance(observed, dict):
        return {}
    evaluation = evaluate_strategy_rule(rule, values)
    parameters = indicator.parameter_map()
    threshold: Any = list(rule.constants)
    if len(rule.constants) == 1:
        threshold = rule.constants[0]
    elif rule.right:
        threshold = rule.right
    projection = {
        "strategy_reference": strategy.identity.strategy_id,
        "strategy_version": strategy.identity.strategy_version,
        "strategy_hash_prefix": strategy.identity.normalized_strategy_hash[:12],
        "semantic_timeframe": indicator.timeframe,
        "indicator_name": indicator.indicator_id,
        "indicator_period": parameters.get("period"),
        "previous_indicator_value": observed.get("previous"),
        "current_indicator_value": observed.get("current"),
        "operator": rule.operator,
        "threshold": threshold,
        "trigger_mode": evaluation["trigger_mode"],
        "previous_condition": evaluation["previous_condition"],
        "current_condition": evaluation["current_condition"],
        "rearm_state": evaluation["signal_state"],
        "opening_eligibility": evaluation["opening_eligibility"],
        "hard_blockers": list(evidence.get("hard_blockers") or ()),
    }
    observability = evidence.get("proposal_observability")
    if isinstance(observability, dict):
        projection["proposal_observability"] = dict(observability)
    return projection


def _with_proposal_observability(
    evidence_summary: str,
    proposal_result: AutonomousOrderProposalResult,
) -> str:
    try:
        payload = json.loads(evidence_summary or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["proposal_observability"] = proposal_result.observability()
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _manual_inputs(
    operator_proposal: ManualOperatorProposalInput,
    feature_result: Any,
    inputs: AutonomousDecisionInputs,
) -> AutonomousDecisionInputs:
    order_type = str(operator_proposal.order_type or "").strip().upper()
    semantics = _ORDER_TYPE_SEMANTICS.get(order_type)
    if semantics is None:
        raise OperatorCandidateInputError("UNSUPPORTED_ORDER_TYPE")
    proposal_source = str(operator_proposal.proposal_source or "").strip().upper()
    if proposal_source not in OPERATOR_PROPOSAL_SOURCES:
        raise OperatorCandidateInputError("PROPOSAL_SOURCE_INVALID")
    side, entry_intent, action = semantics
    snapshot = market_snapshot_from_feature_result(feature_result)
    proposal = AutonomousOrderIntentProposal(
        symbol=inputs.runtime_context.symbol,
        side=side,
        entry_intent=entry_intent,
        order_type=order_type,
        proposed_action=action,
        entry_price=operator_proposal.entry_price,
        trigger_price=operator_proposal.trigger_price,
        limit_price=operator_proposal.limit_price,
        stop_loss=operator_proposal.stop_loss,
        take_profit=operator_proposal.take_profit,
        proposed_volume=operator_proposal.proposed_volume,
        risk_policy_reference=inputs.risk_result.decision_id if inputs.risk_result else "",
        structured_reasoning=(),
    )
    material = {
        "source": proposal_source,
        "proposal": {
            "order_type": order_type,
            **{
                name: _canonical_manual_decimal(getattr(operator_proposal, name))
                for name in (
                    "entry_price",
                    "trigger_price",
                    "limit_price",
                    "stop_loss",
                    "take_profit",
                    "proposed_volume",
                )
            },
        },
        "symbol": inputs.runtime_context.symbol,
        "broker_symbol": inputs.runtime_context.broker_symbol,
        "account_context_reference": inputs.account_context_reference,
        "market_snapshot_hash": autonomous_market_snapshot_provenance_hash(snapshot),
        "context_reference": inputs.runtime_context.context_pack_id,
        "risk_reference": inputs.risk_result.decision_id if inputs.risk_result else "",
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    source_reference = str(operator_proposal.proposal_source_reference or "").strip()
    if not source_reference:
        source_reference = "manual_operator_proposal_" + digest[:24]
    return AutonomousDecisionInputs(
        runtime_context=inputs.runtime_context,
        method_selection=inputs.method_selection,
        score_report=inputs.score_report,
        risk_result=inputs.risk_result,
        lifecycle_status=inputs.lifecycle_status,
        lifecycle_observation=inputs.lifecycle_observation,
        reconciliation_result=inputs.reconciliation_result,
        requested_intent=inputs.requested_intent,
        direction=side,
        semantic_parameter_references=(
            source_reference,
            inputs.risk_result.decision_id if inputs.risk_result else "",
            inputs.method_selection.result_id,
            inputs.runtime_context.context_pack_id,
        ),
        order_proposal=proposal,
        order_market_snapshot=snapshot,
        timeframe_profile=inputs.timeframe_profile,
        account_context_reference=inputs.account_context_reference,
        proposal_source=proposal_source,
        proposal_source_reference=source_reference,
        strategy_id=inputs.strategy_id,
        strategy_version=inputs.strategy_version,
        normalized_strategy_hash=inputs.normalized_strategy_hash,
        reasoning_evidence_summary=inputs.reasoning_evidence_summary,
    )


@dataclass(frozen=True)
class EditableTradeDraftCandidateResult:
    status: str
    blocker: str = ""
    run_result: AutonomousDecisionRunResult | None = None


class EditableTradeDraftCandidateService:
    """Project one exact authoritative Draft revision into the existing candidate path."""

    def __init__(
        self,
        draft_store: EditableTradeDraftStore,
        input_assembler: AuthoritativeAutonomousInputAssembler,
        decision_orchestrator: AutonomousDecisionOrchestrator,
    ) -> None:
        self.draft_store = draft_store
        self.input_assembler = input_assembler
        self.decision_orchestrator = decision_orchestrator

    def create(
        self,
        draft_id: str,
        expected_revision: int,
        *,
        strategy: ConversationalStrategyRequest | None,
        authoritative_mode: str,
        account_environment: str,
        mode_integrity_valid: bool,
        now: datetime | None = None,
    ) -> EditableTradeDraftCandidateResult:
        try:
            draft = self.draft_store.load(str(draft_id or ""))
        except TradeDraftError as exc:
            return EditableTradeDraftCandidateResult("DRAFT_NOT_ELIGIBLE", str(exc))
        if draft is None:
            return EditableTradeDraftCandidateResult("DRAFT_NOT_FOUND")
        if draft.revision != expected_revision:
            return EditableTradeDraftCandidateResult("DRAFT_REVISION_STALE")

        blockers = _draft_candidate_blockers(
            draft,
            strategy=strategy,
            authoritative_mode=authoritative_mode,
            account_environment=account_environment,
            mode_integrity_valid=mode_integrity_valid,
            now=now,
        )
        if blockers:
            return EditableTradeDraftCandidateResult("DRAFT_NOT_ELIGIBLE", blockers[0])

        symbol = dict(draft.symbol.value or {})
        entry = dict(draft.entry.value or {})
        stop = dict(draft.stop.value or {})
        target = dict(draft.target.value or {})
        sizing = dict(draft.sizing.value or {})
        proposal = ManualOperatorProposalInput(
            order_type=str(draft.direction.value or ""),
            stop_loss=_canonical_manual_decimal(stop.get("price")),
            take_profit=_canonical_manual_decimal(target.get("price")),
            proposed_volume=_canonical_manual_decimal(sizing.get("proposed_volume")),
            proposal_source=EDITABLE_TRADE_DRAFT_PROPOSAL_SOURCE,
            proposal_source_reference=draft_candidate_source_reference(draft),
        )
        try:
            inputs = self.input_assembler.build(
                symbol=str(symbol.get("canonical_symbol") or ""),
                timeframes=tuple(symbol.get("timeframes") or ()),
                now=now,
                operator_proposal=proposal,
                strategy=strategy,
            )
        except OperatorCandidateInputError as exc:
            return EditableTradeDraftCandidateResult(
                "DRAFT_NOT_ELIGIBLE", exc.blockers[0] if exc.blockers else "DOMAIN_VALIDATION_BLOCKED"
            )

        run_result = self.decision_orchestrator.run_once(
            inputs, now=now, require_actionable=True
        )
        if not run_result.validation.valid or not run_result.persistence_safe:
            return EditableTradeDraftCandidateResult(
                "DRAFT_NOT_ELIGIBLE",
                run_result.journal_warning
                or (run_result.validation.issues[0] if run_result.validation.issues else "DOMAIN_VALIDATION_BLOCKED"),
                run_result,
            )
        if (
            run_result.candidate.intent != "OPEN_POSITION"
            or run_result.candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE"
        ):
            return EditableTradeDraftCandidateResult(
                "DRAFT_NOT_ELIGIBLE",
                run_result.candidate.blocked_reason_codes[0]
                if run_result.candidate.blocked_reason_codes
                else "DRAFT_CANDIDATE_NOT_ACTIONABLE",
                run_result,
            )
        return EditableTradeDraftCandidateResult(
            "CANDIDATE_CREATED" if run_result.journal_appended else "CANDIDATE_ALREADY_EXISTS",
            run_result=run_result,
        )


def draft_candidate_source_reference(draft: EditableTradeDraft) -> str:
    """Return a safe opaque binding for one immutable Draft revision."""
    material = {
        "draft_id": draft.draft_id,
        "revision": draft.revision,
        "protected_draft": draft.to_protected_dict(),
    }
    digest = hashlib.sha256(
        json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "editable_trade_draft_" + digest[:24]


def _draft_candidate_blockers(
    draft: EditableTradeDraft,
    *,
    strategy: ConversationalStrategyRequest | None,
    authoritative_mode: str,
    account_environment: str,
    mode_integrity_valid: bool,
    now: datetime | None,
) -> tuple[str, ...]:
    blockers = list(draft.blockers)
    required_fields = (
        "symbol", "direction", "action", "entry", "stop", "target", "risk",
        "sizing", "mode", "confirmation_policy", "account_scope",
    )
    if draft.executable or draft.execution_authority:
        blockers.append("DRAFT_EXECUTION_AUTHORITY_INVALID")
    if any(getattr(draft, name).status != "VALID" for name in required_fields):
        blockers.append("DRAFT_FIELD_VALIDATION_BLOCKED")
    if draft.action.value != "OPEN_POSITION" or draft.direction.value not in {"BUY", "SELL"}:
        blockers.append("DRAFT_ACTION_NOT_OPEN_POSITION")
    if draft.account_scope.value != "DEMO" or str(account_environment).upper() != "DEMO":
        blockers.append("DEMO_ACCOUNT_SCOPE_REQUIRED")
    if not draft.account_context_bound:
        blockers.append("DRAFT_ACCOUNT_CONTEXT_UNBOUND")
    if not draft.market_evidence_reference or not _draft_evidence_is_fresh(draft, now):
        blockers.append("MARKET_DATA_STALE")
    if not mode_integrity_valid:
        blockers.append("MODE_INTEGRITY_INVALID")
    if draft.mode.value != authoritative_mode:
        blockers.append("DRAFT_MODE_AUTHORITY_MISMATCH")
    identity = getattr(strategy, "identity", None)
    if (
        identity is None
        or getattr(strategy, "canonical_symbol", None) != (draft.symbol.value or {}).get("canonical_symbol")
        or getattr(strategy, "requested_mode", None) != draft.mode.value
        or (
            getattr(identity, "strategy_id", ""),
            getattr(identity, "strategy_version", ""),
            getattr(identity, "normalized_strategy_hash", ""),
        ) != (draft.strategy_id, draft.strategy_version, draft.strategy_hash)
    ):
        blockers.append("DRAFT_STRATEGY_BINDING_INVALID")
    return tuple(dict.fromkeys(str(item) for item in blockers if item))


def _draft_evidence_is_fresh(
    draft: EditableTradeDraft, now: datetime | None
) -> bool:
    try:
        observed = datetime.fromisoformat(draft.market_evidence_timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    if observed.tzinfo is None:
        return False
    current = _utc(now)
    return (current - observed.astimezone(timezone.utc)).total_seconds() <= (
        Config.TRADING_AUTONOMOUS_DECISION_INPUT_MAX_AGE_SECONDS
    )


def _canonical_manual_decimal(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite():
        return text
    normalized = format(number, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


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
        or broker_symbol != broker_symbol_for(symbol)
    ):
        raise OperatorCandidateInputError("SYMBOL_METADATA_MISSING")
    if symbol.upper() == "BTCUSD" and any(
        getattr(bundle.tick, name, None) in (None, "")
        for name in (
            "digits", "point", "tick_size", "minimum_distance_points",
            "volume_min", "volume_max", "volume_step", "tick_value", "contract_size",
        )
    ):
        raise OperatorCandidateInputError("BROKER_SYMBOL_METADATA_MISSING")
    if not getattr(feature, "source_snapshot_ids", None):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_MISSING")
    if not _fresh(getattr(feature, "created_at", ""), now, max_age_seconds):
        raise OperatorCandidateInputError("MARKET_SNAPSHOT_STALE")
    entry_blockers = tuple(
        str(blocker)
        for blocker in getattr(feature, "blockers", ())
        if str(blocker).startswith("ENTRY_CONDITION_")
    )
    if entry_blockers:
        raise OperatorCandidateInputError(
            *entry_blockers,
            evidence_summary=_reasoning_evidence_summary(feature_result),
        )


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


def _validate_proposal_result(
    result: AutonomousOrderProposalResult,
    feature_result: Any,
    inputs: AutonomousDecisionInputs,
) -> None:
    if not isinstance(result, AutonomousOrderProposalResult):
        raise OperatorCandidateInputError("STRUCTURED_PROPOSAL_RESULT_INVALID")
    if result.blockers:
        raise OperatorCandidateInputError(*result.blockers)
    expected_bindings = (
        feature_result.feature_snapshot.feature_snapshot_id,
        feature_result.bundle.bundle_id,
        inputs.runtime_context.context_pack_id,
        inputs.method_selection.result_id,
        inputs.score_report.score_report_id,
        inputs.risk_result.decision_id if inputs.risk_result else "",
    )
    if not (
        valid_autonomous_order_proposal_bindings(result.source_bindings)
        and valid_autonomous_order_proposal_bindings(expected_bindings)
    ):
        raise OperatorCandidateInputError("PROPOSAL_PROVENANCE_MISSING")
    if not result.valid:
        raise OperatorCandidateInputError("STRUCTURED_PROPOSAL_RESULT_INCOMPLETE")
    if result.source_bindings != expected_bindings:
        raise OperatorCandidateInputError("STRUCTURED_PROPOSAL_REFERENCE_MISMATCH")


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
