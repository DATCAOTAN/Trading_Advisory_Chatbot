from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitor,
    AutonomousCandidateMonitorJournal,
    AutonomousCandidateMonitorResult,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionOrchestrator,
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.autonomous_execution_policy import (
    AutonomousExecutionPolicyGate,
    AutonomousPolicyInputs,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    ApprovalPreSubmitLifecycleService,
    terminal_capability_from_lifecycle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
)
from src.services.trading.human_confirmed_management import (
    build_management_proposal,
    management_target_changed,
)
from src.services.trading.position_read_model import PositionReadModelService


@dataclass(frozen=True)
class CoordinatorAccountContext:
    status: str
    account_context_fingerprint: str
    account_id_hash: str
    captured_at: str
    account_is_demo: bool
    redacted: bool = True

    @classmethod
    def from_value(cls, value: Any) -> "CoordinatorAccountContext":
        get = value.get if isinstance(value, Mapping) else lambda name, default=None: getattr(value, name, default)
        return cls(
            status=str(get("status", "")),
            account_context_fingerprint=str(
                get("account_context_fingerprint", "")
            ).strip().lower(),
            account_id_hash=str(get("account_id_hash", "")),
            captured_at=str(get("captured_at", "")),
            account_is_demo=get("account_is_demo", False) is True,
            redacted=get("redacted", False) is True,
        )


@dataclass(frozen=True)
class AutonomousManagementEvaluation:
    decision: str
    semantic_intent: str = ""
    target_reference: str = field(default="", repr=False)
    strategy_reference: str = ""
    evaluation_reference: str = ""
    policy_reference: str = ""
    values: Mapping[str, Decimal | None] = field(default_factory=dict, repr=False)
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"NO_ACTION", "PROPOSE", "BLOCKED"}:
            raise ValueError("AUTONOMOUS_MANAGEMENT_EVALUATION_INVALID")
        if self.decision == "PROPOSE" and not all(
            str(value or "").strip()
            for value in (
                self.semantic_intent,
                self.target_reference,
                self.strategy_reference,
                self.evaluation_reference,
                self.policy_reference,
            )
        ):
            raise ValueError("AUTONOMOUS_MANAGEMENT_EVALUATION_INVALID")


class AutonomousTradingCoordinator:
    """Own one bounded completed-bar path; injected services retain authority."""

    def __init__(
        self,
        *,
        feature_service: Any,
        input_assembler: Any,
        account_context_provider: Any,
        authority_service: TradingAuthorityService,
        decision_orchestrator: Any | None = None,
        approval_service: ApprovalPreSubmitLifecycleService | None = None,
        mandate_context_provider: Any | None = None,
        execution_adapter: Any | None = None,
        position_read_service: PositionReadModelService | None = None,
        management_evaluator: Any | None = None,
        management_context_provider: Any | None = None,
        management_adapter: Any | None = None,
        policy_gate: Any | None = None,
        monitor_journal: AutonomousCandidateMonitorJournal | None = None,
        clock: Any | None = None,
    ) -> None:
        self.input_assembler = input_assembler
        self.account_context_provider = account_context_provider
        self.authority_service = authority_service
        self.decision_orchestrator = decision_orchestrator or AutonomousDecisionOrchestrator()
        self.approval_service = approval_service
        self.mandate_context_provider = mandate_context_provider
        self.execution_adapter = execution_adapter
        self.position_read_service = position_read_service
        self.management_evaluator = management_evaluator
        self.management_context_provider = management_context_provider
        self.management_adapter = management_adapter or execution_adapter
        self.policy_gate = policy_gate or AutonomousExecutionPolicyGate()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        # ponytail: one coordinator lock; use per-account locks only if measured throughput needs it.
        self._run_lock = threading.Lock()
        self._account_context: CoordinatorAccountContext | None = None
        self.monitor = AutonomousCandidateMonitor(
            feature_service=feature_service,
            completed_bar_handler=self._handle_completed_bar,
            journal=monitor_journal,
        )

    def run_once(
        self, *, symbol: str, timeframes: tuple[str, ...]
    ) -> AutonomousCandidateMonitorResult:
        if not self._run_lock.acquire(blocking=False):
            return AutonomousCandidateMonitorResult(
                "BLOCKED", symbol, timeframes=timeframes,
                blocker="COORDINATOR_BUSY", coordinator_status="BLOCKED",
            )
        try:
            return self._run_once(symbol=symbol, timeframes=timeframes)
        finally:
            self._run_lock.release()

    def _run_once(
        self, *, symbol: str, timeframes: tuple[str, ...]
    ) -> AutonomousCandidateMonitorResult:
        try:
            account = CoordinatorAccountContext.from_value(
                self.account_context_provider()
            )
        except Exception:
            return AutonomousCandidateMonitorResult(
                "BLOCKED", symbol, timeframes=timeframes,
                blocker="COORDINATOR_ACCOUNT_CONTEXT_UNAVAILABLE",
                coordinator_status="BLOCKED",
            )
        if (
            account.status != "OK"
            or not account.redacted
            or not _valid_hash(account.account_context_fingerprint)
            or not account.account_id_hash
        ):
            return AutonomousCandidateMonitorResult(
                "BLOCKED", symbol, timeframes=timeframes,
                blocker="COORDINATOR_ACCOUNT_CONTEXT_INVALID",
                coordinator_status="BLOCKED",
            )
        self._account_context = account
        account_scope = hashlib.sha256(
            account.account_context_fingerprint.encode("utf-8")
        ).hexdigest()[:24]
        return self.monitor.run_once(
            symbol=symbol, timeframes=timeframes, account_scope=account_scope
        )

    def _handle_completed_bar(
        self,
        *,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
        account_scope: str,
    ) -> AutonomousCandidateMonitorResult:
        try:
            inputs = self.input_assembler.build(symbol=symbol, timeframes=timeframes)
        except OperatorCandidateInputError as exc:
            no_action = bool(exc.blockers) and exc.blockers[0] == "STRUCTURED_PROPOSAL_NOT_AVAILABLE"
            return self._result(
                "NO_ACTION" if no_action else "BLOCKED",
                symbol,
                broker_symbol,
                timeframes,
                closed_bar_time,
                account_scope,
                intent="NO_ACTION" if no_action else "",
                blocker=str(exc),
            )
        if not _runtime_safe(inputs):
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, blocker="COORDINATOR_RUNTIME_STATE_UNSAFE",
            )
        management_result = self._handle_post_entry_management(
            inputs=inputs,
            symbol=symbol,
            broker_symbol=broker_symbol,
            timeframes=timeframes,
            closed_bar_time=closed_bar_time,
            account_scope=account_scope,
        )
        if management_result is not None:
            return management_result
        run_result = self.decision_orchestrator.run_once(inputs)
        if not isinstance(run_result, AutonomousDecisionRunResult):
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, blocker="COORDINATOR_RESULT_INVALID",
            )
        candidate = run_result.candidate
        if not run_result.validation.valid or not run_result.persistence_safe:
            blocker = run_result.journal_warning or (
                run_result.validation.issues[0]
                if run_result.validation.issues
                else "COORDINATOR_RESULT_INVALID"
            )
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, intent=candidate.intent, blocker=blocker,
            )
        try:
            mode = self.authority_service.store.latest_mode()
        except TradingAuthorityError as exc:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", str(exc),
            )
        if mode is None:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", "MODE_AUTHORITY_MISSING",
            )
        account = self._account_context
        assert account is not None
        fingerprint_hash = hashlib.sha256(
            account.account_context_fingerprint.encode("utf-8")
        ).hexdigest()
        if not mode.integrity_valid() or not hmac.compare_digest(
            mode.account_fingerprint_hash, fingerprint_hash
        ):
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", "MODE_ACCOUNT_MISMATCH",
            )
        if mode.operating_mode == "advisory_only":
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "ADVISORY_CANDIDATE", "",
            )
        if mode.operating_mode == "human_confirmed_live":
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "AWAITING_HUMAN_CONFIRMATION", "",
                authorization_source="HUMAN_CONFIRMATION",
            )
        policy_run = self.policy_gate.run_once(
            AutonomousPolicyInputs(
                candidate=candidate,
                risk_result=getattr(inputs, "risk_result", None),
                account_context_reference=candidate.account_context_reference,
                account_context_created_at=account.captured_at,
                account_context_matches=True,
                semantic_proposal_complete=bool(
                    candidate.proposed_semantic_parameter_references
                ),
                lifecycle_observation=getattr(inputs, "lifecycle_observation", None),
                reconciliation_result=getattr(inputs, "reconciliation_result", None),
                management_exposure_effect=getattr(inputs, "exposure_effect", "NONE"),
            ),
            now=self.clock(),
        )
        policy = policy_run.policy_result
        if (
            not policy_run.persistence_safe
            or not policy_run.validation.valid
            or policy.decision != "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
            or policy.target_controlled_boundary != "CONTROLLED_OPEN_POSITION"
        ):
            blocker = (
                policy_run.journal_warning
                or (policy.deterministic_reason_codes[0] if policy.deterministic_reason_codes else "AUTONOMOUS_POLICY_BLOCKED")
            )
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", blocker,
                authorization_source="STANDING_MANDATE",
            )
        if self.mandate_context_provider is None:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", "MANDATE_CONTEXT_MISSING",
                authorization_source="STANDING_MANDATE",
            )
        try:
            context = dict(self.mandate_context_provider(candidate, inputs))
            authorization = self.authority_service.authorize_candidate(
                candidate,
                mandate_id=str(context["mandate_id"]),
                account_fingerprint=account.account_context_fingerprint,
                account_is_demo=account.account_is_demo,
                evaluated_risk_per_trade=str(context["evaluated_risk_per_trade"]),
                concurrent_positions=int(context["concurrent_positions"]),
                trades_today=int(context["trades_today"]),
                loss_today=str(context["loss_today"]),
                current_kill_switch_engaged=context.get("kill_switch_engaged") is True,
                lifecycle_healthy=True,
                reconciliation_healthy=True,
                authorization_nonce=str(context["authorization_nonce"]),
                now=self.clock(),
            )
        except (KeyError, TypeError, ValueError, TradingAuthorityError) as exc:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", str(exc),
                authorization_source="STANDING_MANDATE",
            )
        if self.approval_service is None:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "AUTHORIZED_NON_EXECUTABLE", "",
                authorization_source="STANDING_MANDATE",
            )
        try:
            approval = self.approval_service.run(
                candidate.candidate_reference,
                account_context=account,
                expected_account_fingerprint=account.account_context_fingerprint,
                account_is_demo=account.account_is_demo,
                terminal_capability=context["terminal_capability"],
                current_lifecycle_status=inputs.lifecycle_status,
                current_reconciliation=inputs.reconciliation_result,
                authorization_source="STANDING_MANDATE",
                authorization_reference=authorization.authorization_id,
                mandate_evaluated_risk_per_trade=str(context["evaluated_risk_per_trade"]),
                mandate_concurrent_positions=int(context["concurrent_positions"]),
                mandate_trades_today=int(context["trades_today"]),
                mandate_loss_today=str(context["loss_today"]),
                now=self.clock(),
            )
        except (KeyError, RuntimeError):
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", "PRE_SUBMIT_SERVICE_FAILED",
                authorization_source="STANDING_MANDATE",
            )
        ready = bool(approval.report and approval.report.pre_submit_ready)
        if not ready or self.execution_adapter is None:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope,
                "PRE_SUBMIT_READY_NON_EXECUTABLE" if ready else "BLOCKED",
                "" if ready else (approval.approval.blockers[0] if approval.approval.blockers else "PRE_SUBMIT_BLOCKED"),
                authorization_source="STANDING_MANDATE",
                pre_submit_ready=ready,
            )
        revalidation = self.authority_service.validate_candidate_authorization(
            authorization.authorization_id,
            candidate,
            account_fingerprint=account.account_context_fingerprint,
            account_is_demo=account.account_is_demo,
            current_kill_switch_engaged=context.get("kill_switch_engaged") is True,
            evaluated_risk_per_trade=str(context["evaluated_risk_per_trade"]),
            concurrent_positions=int(context["concurrent_positions"]),
            trades_today=int(context["trades_today"]),
            loss_today=str(context["loss_today"]),
            now=self.clock(),
        )
        if revalidation:
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", revalidation[0],
                authorization_source="STANDING_MANDATE", pre_submit_ready=True,
            )
        try:
            request = MT5ControlledExecutionRequest.from_mandate_artifacts(
                candidate,
                authorization,
                approval.final_validation,
                approval.report,
                expected_account_context_fingerprint=account.account_context_fingerprint,
            )
            receipt = self.execution_adapter.submit_prepared_request(request)
        except (TypeError, ValueError, RuntimeError):
            return self._candidate_result(
                candidate, symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, "BLOCKED", "CONTROLLED_EXECUTION_INTEGRATION_FAILED",
                authorization_source="STANDING_MANDATE", pre_submit_ready=True,
            )
        status = {
            "ACCEPTED": "RESULT_CONFIRMED",
            "REJECTED": "RESULT_REJECTED",
            "UNKNOWN": "RESULT_UNKNOWN",
        }.get(receipt.status, "BLOCKED")
        return self._candidate_result(
            candidate, symbol, broker_symbol, timeframes, closed_bar_time,
            account_scope, status,
            receipt.reason if status in {"BLOCKED", "RESULT_UNKNOWN"} else "",
            authorization_source="STANDING_MANDATE",
            pre_submit_ready=True,
        )

    def _handle_post_entry_management(
        self,
        *,
        inputs: Any,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
        account_scope: str,
    ) -> AutonomousCandidateMonitorResult | None:
        if self.position_read_service is None:
            return None
        positions = self.position_read_service.read(
            query_type="CURRENT", canonical_symbol=symbol, singular=False
        )
        orders = self.position_read_service.read(
            query_type="PENDING", canonical_symbol=symbol, singular=False
        )
        targets = tuple(positions.open_positions) + tuple(orders.pending_orders)
        if not targets:
            return None
        if self.management_evaluator is None:
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, blocker="AUTONOMOUS_MANAGEMENT_EVALUATOR_MISSING",
            )
        try:
            evaluation = self.management_evaluator(inputs, positions, orders)
        except Exception:
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, blocker="AUTONOMOUS_MANAGEMENT_EVALUATION_FAILED",
            )
        if not isinstance(evaluation, AutonomousManagementEvaluation):
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, blocker="AUTONOMOUS_MANAGEMENT_EVALUATION_INVALID",
            )
        if evaluation.decision == "NO_ACTION":
            return self._management_result(
                None,
                evaluation,
                symbol,
                broker_symbol,
                timeframes,
                closed_bar_time,
                account_scope,
                "NO_ACTION",
                "",
            )
        if evaluation.decision == "BLOCKED":
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope,
                intent=evaluation.semantic_intent,
                blocker=evaluation.blockers[0] if evaluation.blockers else "AUTONOMOUS_MANAGEMENT_BLOCKED",
            )
        matches = [
            target
            for target in targets
            if hmac.compare_digest(target.protected_reference, evaluation.target_reference)
        ]
        if len(matches) != 1:
            return self._result(
                "BLOCKED", symbol, broker_symbol, timeframes, closed_bar_time,
                account_scope, intent=evaluation.semantic_intent,
                blocker="AUTONOMOUS_MANAGEMENT_TARGET_NOT_UNIQUE",
            )
        target = matches[0]
        model = orders if target.state == "ORDER_ACTIVE" else positions
        try:
            observation = self.position_read_service.lifecycle_journal.latest_by_execution().get(
                target.provenance.execution_reference
            )
            if not observation:
                raise ValueError("LIFECYCLE_OBSERVATION_UNAVAILABLE")
            proposal = build_management_proposal(
                semantic_intent=evaluation.semantic_intent,
                model=model,
                target=target,
                values=evaluation.values,
                observation=observation,
                current_time=self.clock(),
            )
            if self.management_context_provider is None:
                raise TradingAuthorityError("MANDATE_MANAGEMENT_CONTEXT_MISSING")
            context = dict(self.management_context_provider(evaluation, target, inputs))
            account = self._account_context
            assert account is not None
            authorization = self.authority_service.authorize_management(
                proposal,
                target,
                semantic_management_intent=evaluation.semantic_intent,
                mandate_id=str(context["mandate_id"]),
                strategy_reference=evaluation.strategy_reference,
                source_candidate_authorization_reference=target.provenance.authorization_reference,
                evaluation_reference=evaluation.evaluation_reference,
                policy_reference=evaluation.policy_reference,
                account_fingerprint=account.account_context_fingerprint,
                account_is_demo=account.account_is_demo,
                concurrent_positions=int(context["concurrent_positions"]),
                trades_today=int(context["trades_today"]),
                loss_today=str(context["loss_today"]),
                current_kill_switch_engaged=context.get("kill_switch_engaged") is True,
                lifecycle_healthy=True,
                reconciliation_healthy=True,
                authorization_nonce=str(context["authorization_nonce"]),
                now=self.clock(),
            )
        except (KeyError, TypeError, ValueError, TradingAuthorityError) as exc:
            return self._management_result(
                proposal if "proposal" in locals() else None,
                evaluation,
                symbol,
                broker_symbol,
                timeframes,
                closed_bar_time,
                account_scope,
                "BLOCKED",
                str(exc),
            )
        refreshed = self.position_read_service.read(
            query_type="PENDING" if target.state == "ORDER_ACTIVE" else "CURRENT",
            canonical_symbol=target.canonical_symbol,
            protected_reference=target.protected_reference,
            singular=True,
        )
        current_target = refreshed.selected_position
        if refreshed.status != "AVAILABLE" or current_target is None:
            blockers = refreshed.blockers or ("MANAGEMENT_TARGET_UNAVAILABLE",)
            return self._management_result(
                proposal, evaluation, symbol, broker_symbol, timeframes,
                closed_bar_time, account_scope, "BLOCKED", blockers[0],
            )
        stale = management_target_changed(proposal, current_target)
        latest_observation = self.position_read_service.lifecycle_journal.latest_by_execution().get(
            current_target.provenance.execution_reference
        )
        if (
            stale
            or not latest_observation
            or latest_observation.get("observation_id") != proposal.lifecycle_observation_reference
            or latest_observation.get("observation_hash") != proposal.lifecycle_observation_hash
        ):
            return self._management_result(
                proposal, evaluation, symbol, broker_symbol, timeframes,
                closed_bar_time, account_scope, "BLOCKED",
                stale or "LIFECYCLE_OBSERVATION_STALE",
            )
        account = self._account_context
        assert account is not None
        blockers = self.authority_service.validate_management_authorization(
            authorization.authorization_id,
            proposal,
            current_target,
            account_fingerprint=account.account_context_fingerprint,
            account_is_demo=account.account_is_demo,
            concurrent_positions=int(context["concurrent_positions"]),
            trades_today=int(context["trades_today"]),
            loss_today=str(context["loss_today"]),
            current_kill_switch_engaged=context.get("kill_switch_engaged") is True,
            lifecycle_healthy=True,
            reconciliation_healthy=True,
            now=self.clock(),
        )
        if blockers or self.management_adapter is None:
            return self._management_result(
                proposal, evaluation, symbol, broker_symbol, timeframes,
                closed_bar_time, account_scope,
                "AUTHORIZED_NON_EXECUTABLE" if not blockers else "BLOCKED",
                blockers[0] if blockers else "",
            )
        try:
            request = MT5ControlledManagementRequest.from_mandate_authorization(
                proposal, authorization, current_time=self.clock()
            )
            receipt = self.management_adapter.manage_prepared_request(request)
        except (TypeError, ValueError, RuntimeError):
            return self._management_result(
                proposal, evaluation, symbol, broker_symbol, timeframes,
                closed_bar_time, account_scope, "BLOCKED",
                "CONTROLLED_MANAGEMENT_INTEGRATION_FAILED",
            )
        status = {
            "ACCEPTED": "RESULT_CONFIRMED",
            "REJECTED": "RESULT_REJECTED",
            "UNKNOWN": "RESULT_UNKNOWN",
        }.get(receipt.status, "BLOCKED")
        return self._management_result(
            proposal, evaluation, symbol, broker_symbol, timeframes,
            closed_bar_time, account_scope, status,
            receipt.reason if status in {"BLOCKED", "RESULT_UNKNOWN"} else "",
        )

    @staticmethod
    def _management_result(
        proposal: Any | None,
        evaluation: AutonomousManagementEvaluation,
        symbol: str,
        broker_symbol: str,
        timeframes: tuple[str, ...],
        closed_bar_time: str,
        account_scope: str,
        status: str,
        blocker: str,
    ) -> AutonomousCandidateMonitorResult:
        reference = (
            "management_" + proposal.mutation_hash[:24] if proposal is not None else ""
        )
        return AutonomousCandidateMonitorResult(
            status,
            symbol,
            broker_symbol,
            timeframes,
            closed_bar_time,
            candidate_reference=reference,
            intent=evaluation.semantic_intent,
            blocker=blocker,
            validation_valid=status != "BLOCKED",
            generation_count=0,
            proposal_provider_max_invocations=0,
            account_scope=account_scope,
            coordinator_status=status,
            authorization_source="STANDING_MANDATE",
        )

    @staticmethod
    def _result(
        status, symbol, broker_symbol, timeframes, closed_bar_time, account_scope,
        *, intent="", blocker="",
    ) -> AutonomousCandidateMonitorResult:
        return AutonomousCandidateMonitorResult(
            status, symbol, broker_symbol, timeframes, closed_bar_time,
            intent=intent, blocker=blocker, generation_count=1,
            proposal_provider_max_invocations=1, account_scope=account_scope,
            coordinator_status=status,
        )

    @staticmethod
    def _candidate_result(
        candidate, symbol, broker_symbol, timeframes, closed_bar_time, account_scope,
        status, blocker, *, authorization_source="", pre_submit_ready=False,
    ) -> AutonomousCandidateMonitorResult:
        return AutonomousCandidateMonitorResult(
            status, symbol, broker_symbol, timeframes, closed_bar_time,
            candidate_reference=candidate.candidate_reference,
            intent=candidate.intent,
            blocker=blocker,
            validation_valid=True,
            generation_count=1,
            proposal_provider_max_invocations=1,
            account_scope=account_scope,
            coordinator_status=status,
            authorization_source=authorization_source,
            pre_submit_ready=pre_submit_ready,
        )


def _runtime_safe(inputs: Any) -> bool:
    lifecycle = getattr(inputs, "lifecycle_status", None)
    if (
        lifecycle is None
        or lifecycle.supervisor_status != "HEALTHY"
        or not lifecycle.bridge_available
        or not lifecycle.account_context_match
        or lifecycle.discrepancy_count
        or any(
            lifecycle.lifecycle_state_counts.get(state, 0)
            for state in ("RESULT_UNKNOWN", "RECONCILIATION_REQUIRED", "SUBMISSION_STARTED")
        )
    ):
        return False
    reconciliation = getattr(inputs, "reconciliation_result", None)
    return reconciliation is None or (
        reconciliation.resulting_execution_state != "RESULT_UNKNOWN"
        and reconciliation.evidence_classification
        not in {"AMBIGUOUS_MATCH", "QUERY_FAILED", "RESULT_UNKNOWN"}
        and reconciliation.retry_decision == "RETRY_PROHIBITED"
    )


def coordinator_account_context(
    *, account_context_fingerprint: str, account_id_hash: str, account_is_demo: bool
) -> CoordinatorAccountContext:
    return CoordinatorAccountContext(
        status="OK",
        account_context_fingerprint=account_context_fingerprint,
        account_id_hash=account_id_hash,
        captured_at=datetime.now(timezone.utc).isoformat(),
        account_is_demo=account_is_demo,
        redacted=True,
    )


def production_mandate_context(
    candidate: Any,
    inputs: Any,
    *,
    authority_service: TradingAuthorityService,
    mandate_id: str,
    account_context_fingerprint: str,
    kill_switch_engaged: bool,
) -> dict[str, Any]:
    """Build current mandate-limit evidence from the protected candidate and lifecycle."""
    mandate = authority_service.store.latest_mandate(mandate_id)
    if mandate is None:
        raise TradingAuthorityError("MANDATE_NOT_FOUND")
    lifecycle = getattr(inputs, "lifecycle_status", None)
    if (
        lifecycle is None
        or lifecycle.supervisor_status != "HEALTHY"
        or lifecycle.mandate_limit_evidence_available is not True
    ):
        raise TradingAuthorityError("LIFECYCLE_NOT_HEALTHY")
    capability = terminal_capability_from_lifecycle(
        candidate, lifecycle, account_context_fingerprint
    )
    return {
        "mandate_id": mandate.mandate_id,
        "evaluated_risk_per_trade": _candidate_risk_amount(candidate, inputs),
        "concurrent_positions": int(lifecycle.active_position_count),
        "trades_today": int(lifecycle.trades_today),
        "loss_today": str(lifecycle.loss_today),
        "kill_switch_engaged": bool(kill_switch_engaged),
        "authorization_nonce": hashlib.sha256(
            f"{candidate.decision_idempotency_key}|{mandate.artifact_hash}".encode("utf-8")
        ).hexdigest(),
        "terminal_capability": capability,
    }


def _candidate_risk_amount(candidate: Any, inputs: Any) -> str:
    snapshot = getattr(inputs, "order_market_snapshot", None)
    if snapshot is None:
        raise TradingAuthorityError("MANDATE_RISK_EVIDENCE_MISSING")
    try:
        order_type = str(candidate.order_type).upper()
        entry = (
            Decimal(str(candidate.limit_price))
            if order_type.endswith("STOP_LIMIT")
            else Decimal(str(candidate.entry_price or candidate.trigger_price))
            if candidate.entry_price or candidate.trigger_price
            else Decimal(str(snapshot.ask if candidate.side == "BUY" else snapshot.bid))
        )
        stop = Decimal(str(candidate.stop_loss))
        volume = Decimal(str(candidate.proposed_volume))
        tick_size = Decimal(str(snapshot.tick_size))
        tick_value = Decimal(str(snapshot.tick_value))
        if min(volume, tick_size, tick_value) <= 0 or entry == stop:
            raise InvalidOperation
        amount = abs(entry - stop) / tick_size * tick_value * volume
    except (InvalidOperation, TypeError, ValueError):
        raise TradingAuthorityError("MANDATE_RISK_EVIDENCE_INVALID") from None
    text = format(amount, "f").rstrip("0").rstrip(".")
    return text or "0"


def _valid_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
