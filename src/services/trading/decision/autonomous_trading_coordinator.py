from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
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
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    ApprovalPreSubmitLifecycleService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
)


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
            no_action = exc.blockers == ("STRUCTURED_PROPOSAL_NOT_AVAILABLE",)
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


def _valid_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
