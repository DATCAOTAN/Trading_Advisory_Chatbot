from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Mapping

from src.services.trading.decision.autonomous_orchestrator import (
    OFFLINE_FIXTURE_MODE,
    AutonomousDecisionConfig,
    AutonomousDecisionJournalError,
    AutonomousDecisionOrchestrator,
    AutonomousOrderMarketSnapshot,
    autonomous_account_context_reference,
    autonomous_lifecycle_status_reference,
    autonomous_symbol_metadata_hash,
    validate_autonomous_candidate_order_snapshot,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5PreSubmitGateReport,
    MT5PreSubmitJournalRecord,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
    execution_permission_state,
    mandate_permissions_execution_ready,
    mandate_permissions_safely_disabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (
    MT5PreSubmitJournalStore,
    pre_submit_record_hash,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    MandateCandidateAuthorization,
    TradingAuthorityError,
    TradingAuthorityService,
)
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.proposal.confirmation_service import (
    HumanProposalConfirmationService,
    candidate_confirmation_binding_hash,
    candidate_confirmation_source_refs,
)
from src.services.trading.proposal.intent_store import (
    ProposalIntentJournalStore,
    load_candidate_confirmation,
)


PRE_SUBMIT_STATE = "PRE_SUBMIT_READY_NON_EXECUTABLE"
SUPPORTED_CONTROLLED_ORDER_TYPES = (
    "BUY",
    "SELL",
    "BUY_LIMIT",
    "SELL_LIMIT",
    "BUY_STOP",
    "SELL_STOP",
    "BUY_STOP_LIMIT",
    "SELL_STOP_LIMIT",
)


@dataclass(frozen=True)
class TerminalCapabilityEvidence:
    capability_reference: str
    observed_at: str
    symbol: str
    broker_symbol: str
    account_fingerprint_hash: str
    trade_allowed: bool
    supported_order_types: tuple[str, ...]
    capability_hash: str
    metadata_redacted: bool = True

    @classmethod
    def create(
        cls,
        *,
        observed_at: str,
        symbol: str,
        broker_symbol: str,
        account_fingerprint_hash: str,
        trade_allowed: bool,
        supported_order_types: tuple[str, ...],
    ) -> "TerminalCapabilityEvidence":
        material = {
            "observed_at": observed_at,
            "symbol": symbol,
            "broker_symbol": broker_symbol,
            "account_fingerprint_hash": account_fingerprint_hash,
            "trade_allowed": trade_allowed,
            "supported_order_types": sorted(set(supported_order_types)),
            "metadata_redacted": True,
        }
        digest = _hash(material)
        return cls(
            capability_reference="terminal_capability_" + digest[:24],
            observed_at=observed_at,
            symbol=symbol,
            broker_symbol=broker_symbol,
            account_fingerprint_hash=account_fingerprint_hash,
            trade_allowed=trade_allowed,
            supported_order_types=tuple(sorted(set(supported_order_types))),
            capability_hash=digest,
        )

    def integrity_valid(self) -> bool:
        material = {
            "observed_at": self.observed_at,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "account_fingerprint_hash": self.account_fingerprint_hash,
            "trade_allowed": self.trade_allowed,
            "supported_order_types": sorted(set(self.supported_order_types)),
            "metadata_redacted": True,
        }
        expected = _hash(material)
        return hmac.compare_digest(self.capability_hash, expected) and hmac.compare_digest(
            self.capability_reference, "terminal_capability_" + expected[:24]
        )


def terminal_capability_from_lifecycle(
    candidate: Any,
    lifecycle: MT5RuntimeSupervisorStatus,
    account_context_fingerprint: str,
) -> TerminalCapabilityEvidence:
    """Bind current read-only terminal capability to one protected Candidate."""
    return TerminalCapabilityEvidence.create(
        observed_at=str(lifecycle.last_successful_cycle or ""),
        symbol=candidate.symbol_reference,
        broker_symbol=candidate.broker_symbol_reference,
        account_fingerprint_hash=_sha256(account_context_fingerprint),
        trade_allowed=(
            lifecycle.terminal_trade_allowed is True
            and lifecycle.account_trade_allowed is True
        ),
        supported_order_types=SUPPORTED_CONTROLLED_ORDER_TYPES,
    )


@dataclass(frozen=True)
class ApprovalIntegrityResult:
    valid: bool
    approval_integrity_hash: str = ""
    candidate_reference: str = ""
    confirmation_intent_id: str = ""
    blockers: tuple[str, ...] = ()
    authorization_source: str = "HUMAN_CONFIRMATION"
    authorization_id: str = ""


@dataclass(frozen=True)
class FinalValidationResult:
    final_validation_id: str
    created_at: str
    valid: bool
    candidate_reference: str
    confirmation_intent_id: str
    approval_integrity_hash: str
    terminal_capability_reference: str
    lifecycle_reference: str
    reconciliation_reference: str
    permission_state_hash: str
    symbol_metadata_hash: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    protected_intent: Mapping[str, Any] = field(default_factory=dict, repr=False)
    authorization_source: str = "HUMAN_CONFIRMATION"
    authorization_id: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "final_validation_id": self.final_validation_id,
            "created_at": self.created_at,
            "valid": self.valid,
            "candidate_reference": self.candidate_reference,
            "confirmation_intent_id": self.confirmation_intent_id,
            "authorization_source": self.authorization_source,
            "authorization_id": self.authorization_id,
            "approval_integrity_hash": self.approval_integrity_hash,
            "terminal_capability_reference": self.terminal_capability_reference,
            "lifecycle_reference": self.lifecycle_reference,
            "reconciliation_reference": self.reconciliation_reference,
            "permission_state_hash": self.permission_state_hash,
            "symbol_metadata_hash": self.symbol_metadata_hash,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "semantic_values_redacted": True,
            "executable": False,
            "order_send_allowed": False,
            "order_sent": False,
        }


@dataclass(frozen=True)
class ApprovalPreSubmitLifecycleResult:
    approval: ApprovalIntegrityResult
    final_validation: FinalValidationResult | None
    report: MT5PreSubmitGateReport | None
    journal_record: MT5PreSubmitJournalRecord | None
    journal_appended: bool


class ApprovalPreSubmitLifecycleService:
    """Reload and validate one confirmed candidate without submitting it."""

    def __init__(
        self,
        *,
        candidate_journal: Any,
        confirmation_store: ProposalIntentJournalStore,
        pre_submit_store: MT5PreSubmitJournalStore,
        config: MT5LiveAdapterPreSubmitConfig | None = None,
        decision_config: AutonomousDecisionConfig | None = None,
        confirmation_service: HumanProposalConfirmationService | None = None,
        authority_service: TradingAuthorityService | None = None,
    ):
        self.candidate_journal = candidate_journal
        self.confirmation_store = confirmation_store
        self.pre_submit_store = pre_submit_store
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()
        self.decision_config = decision_config or AutonomousDecisionConfig.from_config()
        self.confirmation_service = confirmation_service or HumanProposalConfirmationService()
        self.authority_service = authority_service

    def run(
        self,
        candidate_reference: str,
        *,
        account_context: Any,
        expected_account_fingerprint: str,
        terminal_capability: TerminalCapabilityEvidence | None,
        current_lifecycle_status: MT5RuntimeSupervisorStatus | None = None,
        current_reconciliation: MT5ReconciliationReceipt | None = None,
        authorization_source: str = "HUMAN_CONFIRMATION",
        authorization_reference: str = "",
        account_is_demo: bool = False,
        mandate_evaluated_risk_per_trade: str | None = None,
        mandate_concurrent_positions: int | None = None,
        mandate_trades_today: int | None = None,
        mandate_loss_today: str | None = None,
        now: datetime | None = None,
    ) -> ApprovalPreSubmitLifecycleResult:
        evaluated_at = _utc(now)
        candidate = confirmation = snapshot = runtime_evidence = None
        load_blockers: list[str] = []
        try:
            candidate = self.candidate_journal.load_candidate(candidate_reference)
            snapshot = self.candidate_journal.load_market_snapshot(candidate_reference)
            runtime_evidence = self.candidate_journal.load_runtime_evidence(
                candidate_reference
            )
            if authorization_source == "HUMAN_CONFIRMATION":
                confirmation = load_candidate_confirmation(
                    self.confirmation_store, candidate_reference
                )
            elif authorization_source == "STANDING_MANDATE":
                if self.authority_service is None:
                    load_blockers.append("MANDATE_AUTHORITY_SERVICE_MISSING")
                elif not authorization_reference:
                    load_blockers.append("MANDATE_AUTHORIZATION_REFERENCE_MISSING")
                else:
                    confirmation = self.authority_service.store.load_authorization(
                        authorization_reference
                    )
            else:
                load_blockers.append("AUTHORIZATION_SOURCE_INVALID")
        except AutonomousDecisionJournalError as exc:
            load_blockers.append(str(exc))
        except (RuntimeError, TradingAuthorityError) as exc:
            load_blockers.append(str(exc))

        approval = self._approval_integrity(
            candidate,
            confirmation,
            account_context,
            expected_account_fingerprint,
            evaluated_at,
            load_blockers,
            authorization_source,
            account_is_demo,
            mandate_evaluated_risk_per_trade,
            mandate_concurrent_positions,
            mandate_trades_today,
            mandate_loss_today,
        )
        if not approval.valid:
            return ApprovalPreSubmitLifecycleResult(approval, None, None, None, False)

        persisted_lifecycle, persisted_reconciliation = _runtime_evidence(runtime_evidence)
        lifecycle = current_lifecycle_status or persisted_lifecycle
        reconciliation = (
            current_reconciliation
            if current_reconciliation is not None
            else persisted_reconciliation
        )
        final = self._final_validation(
            candidate,
            confirmation,
            snapshot,
            expected_account_fingerprint,
            terminal_capability,
            persisted_lifecycle,
            persisted_reconciliation,
            lifecycle,
            reconciliation,
            approval,
            evaluated_at,
        )
        report = self._report(final, candidate, confirmation)
        if not final.valid:
            return ApprovalPreSubmitLifecycleResult(approval, final, report, None, False)

        record = self._record(final, report, candidate, confirmation)
        try:
            _, appended = self.pre_submit_store.append_idempotent(record)
        except RuntimeError as exc:
            blocked = _blocked_final(final, str(exc))
            return ApprovalPreSubmitLifecycleResult(
                approval, blocked, self._report(blocked, candidate, confirmation), None, False
            )
        return ApprovalPreSubmitLifecycleResult(
            approval, final, report, record, appended
        )

    def _approval_integrity(
        self,
        candidate,
        confirmation,
        account_context,
        expected_fingerprint: str,
        now: datetime,
        initial_blockers: list[str],
        authorization_source: str,
        account_is_demo: bool,
        mandate_evaluated_risk_per_trade: str | None,
        mandate_concurrent_positions: int | None,
        mandate_trades_today: int | None,
        mandate_loss_today: str | None,
    ) -> ApprovalIntegrityResult:
        if authorization_source == "STANDING_MANDATE":
            return self._mandate_approval_integrity(
                candidate,
                confirmation,
                account_context,
                expected_fingerprint,
                account_is_demo,
                mandate_evaluated_risk_per_trade,
                mandate_concurrent_positions,
                mandate_trades_today,
                mandate_loss_today,
                now,
                initial_blockers,
            )
        blockers = list(initial_blockers)
        if candidate is None:
            blockers.append("CANDIDATE_NOT_FOUND")
        if confirmation is None:
            blockers.append("CONFIRMATION_NOT_FOUND")
        if blockers:
            return ApprovalIntegrityResult(False, blockers=_unique(blockers))

        validation = AutonomousDecisionOrchestrator(
            self.decision_config, journal=self.candidate_journal
        ).validate_candidate(candidate, now=now)
        blockers.extend(validation.issues)
        if candidate.intent != "OPEN_POSITION" or candidate.action not in {
            "MARKET",
            "PENDING",
        }:
            blockers.append("CANDIDATE_NOT_ACTIONABLE")
        if candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE":
            blockers.append("CANDIDATE_NOT_ELIGIBLE")
        if candidate.operating_mode not in {
            "human_confirmed_live",
            OFFLINE_FIXTURE_MODE,
        }:
            blockers.append("HUMAN_AUTHORIZATION_MODE_MISMATCH")
        if confirmation.proposal_boundary_status != "CONFIRMED_FOR_PROPOSAL_WORKFLOW":
            blockers.append("PROPOSAL_CONFIRMATION_NOT_GRANTED")
        if confirmation.human_confirmation_state != "CONFIRMED_PROPOSAL_WORKFLOW":
            blockers.append("HUMAN_CONFIRMATION_NOT_GRANTED")
        if confirmation.operator_action != "CONFIRM":
            blockers.append("CONFIRMATION_ACTION_NOT_AFFIRMATIVE")
        if not confirmation.proposal_workflow_allowed:
            blockers.append("PROPOSAL_WORKFLOW_NOT_ALLOWED")
        if not confirmation.dry_run_only or confirmation.executable:
            blockers.append("CONFIRMATION_PERMISSION_INVALID")

        fingerprint = str(
            getattr(account_context, "account_context_fingerprint", "") or ""
        ).strip().lower()
        expected_fingerprint = str(expected_fingerprint or "").strip().lower()
        fingerprint_hash = _sha256(fingerprint)
        if (
            getattr(account_context, "status", "") != "OK"
            or getattr(account_context, "redacted", False) is not True
        ):
            blockers.append("ACCOUNT_CONTEXT_INVALID")
        if not _valid_hash(fingerprint) or not _valid_hash(expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_FINGERPRINT_INVALID")
        elif not hmac.compare_digest(fingerprint, expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_MISMATCH")
        account_reference = autonomous_account_context_reference(
            str(getattr(account_context, "account_id_hash", ""))
        )
        comparisons = (
            (confirmation.candidate_reference, candidate.candidate_reference),
            (confirmation.candidate_provenance_hash, candidate.provenance_hash),
            (confirmation.candidate_structured_order_hash, candidate.structured_order_hash),
            (confirmation.account_context_reference, candidate.account_context_reference),
            (confirmation.account_context_reference, account_reference),
            (confirmation.account_fingerprint_hash, fingerprint_hash),
            (confirmation.symbol, candidate.symbol_reference),
            (confirmation.broker_symbol, candidate.broker_symbol_reference),
            (confirmation.order_type, candidate.order_type),
        )
        if any(not hmac.compare_digest(str(left), str(right)) for left, right in comparisons):
            blockers.append("CONFIRMATION_CANDIDATE_BINDING_MISMATCH")
        if tuple(confirmation.timeframe_profile) != candidate.timeframe_profile:
            blockers.append("CONFIRMATION_TIMEFRAME_MISMATCH")
        required_refs = candidate_confirmation_source_refs(candidate)
        if tuple(confirmation.source_refs) != required_refs:
            blockers.append("CONFIRMATION_SOURCE_BINDING_MISMATCH")
        expected_binding = candidate_confirmation_binding_hash(
            candidate,
            account_fingerprint_hash=fingerprint_hash,
            operator_action=confirmation.operator_action,
            confirmation_nonce=confirmation.confirmation_nonce,
            confirmation_phrase=self.confirmation_service.policy.confirmation_phrase,
            confirmed_at=confirmation.confirmation_timestamp,
            expires_at=confirmation.confirmation_expires_at,
        )
        if not (
            hmac.compare_digest(confirmation.confirmation_binding_hash, expected_binding)
            and hmac.compare_digest(confirmation.artifact_hash, expected_binding)
        ):
            blockers.append("APPROVAL_INTEGRITY_HASH_MISMATCH")
        if _expired(candidate.expires_at, now):
            blockers.append("CANDIDATE_EXPIRED")
        if _expired(confirmation.confirmation_expires_at, now):
            blockers.append("CONFIRMATION_EXPIRED")
        if not _fresh(
            getattr(account_context, "captured_at", ""),
            now,
            self.decision_config.input_max_age_seconds,
        ):
            blockers.append("ACCOUNT_CONTEXT_STALE")
        blockers = list(_unique(blockers))
        integrity_hash = _hash(
            {
                "candidate_reference": candidate.candidate_reference,
                "candidate_hash": candidate.provenance_hash,
                "structured_order_hash": candidate.structured_order_hash,
                "confirmation_intent_id": confirmation.intent_id,
                "confirmation_record_hash": confirmation.record_hash,
                "confirmation_binding_hash": confirmation.confirmation_binding_hash,
                "account_fingerprint_hash": fingerprint_hash,
                "source_refs": list(required_refs),
            }
        )
        return ApprovalIntegrityResult(
            not blockers,
            integrity_hash if not blockers else "",
            candidate.candidate_reference,
            confirmation.intent_id,
            tuple(blockers),
            "HUMAN_CONFIRMATION",
            confirmation.intent_id,
        )

    def _mandate_approval_integrity(
        self,
        candidate,
        authorization: MandateCandidateAuthorization | None,
        account_context,
        expected_fingerprint: str,
        account_is_demo: bool,
        evaluated_risk_per_trade: str | None,
        concurrent_positions: int | None,
        trades_today: int | None,
        loss_today: str | None,
        now: datetime,
        initial_blockers: list[str],
    ) -> ApprovalIntegrityResult:
        blockers = list(initial_blockers)
        if candidate is None:
            blockers.append("CANDIDATE_NOT_FOUND")
        if authorization is None:
            blockers.append("MANDATE_AUTHORIZATION_NOT_FOUND")
        if blockers:
            return ApprovalIntegrityResult(
                False,
                blockers=_unique(blockers),
                authorization_source="STANDING_MANDATE",
            )
        validation = AutonomousDecisionOrchestrator(
            self.decision_config, journal=self.candidate_journal
        ).validate_candidate(candidate, now=now)
        blockers.extend(validation.issues)
        if candidate.intent != "OPEN_POSITION" or candidate.action not in {
            "MARKET",
            "PENDING",
        }:
            blockers.append("CANDIDATE_NOT_ACTIONABLE")
        if candidate.deterministic_eligibility_result != "ELIGIBLE_CANDIDATE":
            blockers.append("CANDIDATE_NOT_ELIGIBLE")
        fingerprint = str(
            getattr(account_context, "account_context_fingerprint", "") or ""
        ).strip().lower()
        expected_fingerprint = str(expected_fingerprint or "").strip().lower()
        if (
            getattr(account_context, "status", "") != "OK"
            or getattr(account_context, "redacted", False) is not True
            or not account_is_demo
        ):
            blockers.append("ACCOUNT_CONTEXT_INVALID")
        if not _valid_hash(fingerprint) or not _valid_hash(expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_FINGERPRINT_INVALID")
        elif not hmac.compare_digest(fingerprint, expected_fingerprint):
            blockers.append("ACCOUNT_CONTEXT_MISMATCH")
        if self.authority_service is None:
            blockers.append("MANDATE_AUTHORITY_SERVICE_MISSING")
        else:
            blockers.extend(
                self.authority_service.validate_candidate_authorization(
                    authorization.authorization_id,
                    candidate,
                    account_fingerprint=expected_fingerprint,
                    account_is_demo=account_is_demo,
                    current_kill_switch_engaged=bool(self.config.kill_switch_engaged),
                    evaluated_risk_per_trade=evaluated_risk_per_trade,
                    concurrent_positions=concurrent_positions,
                    trades_today=trades_today,
                    loss_today=loss_today,
                    now=now,
                )
            )
        if _expired(candidate.expires_at, now):
            blockers.append("CANDIDATE_EXPIRED")
        if not _fresh(
            getattr(account_context, "captured_at", ""),
            now,
            self.decision_config.input_max_age_seconds,
        ):
            blockers.append("ACCOUNT_CONTEXT_STALE")
        blockers = list(_unique(blockers))
        integrity_hash = _hash(
            {
                "authorization_source": "STANDING_MANDATE",
                "authorization_id": authorization.authorization_id,
                "authorization_hash": authorization.artifact_hash,
                "candidate_reference": candidate.candidate_reference,
                "candidate_hash": candidate.provenance_hash,
                "structured_order_hash": candidate.structured_order_hash,
                "account_fingerprint_hash": authorization.account_fingerprint_hash,
                "source_refs": list(authorization.source_refs),
            }
        )
        return ApprovalIntegrityResult(
            not blockers,
            integrity_hash if not blockers else "",
            candidate.candidate_reference,
            "",
            tuple(blockers),
            "STANDING_MANDATE",
            authorization.authorization_id,
        )

    def _final_validation(
        self,
        candidate,
        confirmation,
        snapshot: AutonomousOrderMarketSnapshot | None,
        expected_fingerprint: str,
        capability: TerminalCapabilityEvidence | None,
        persisted_lifecycle: MT5RuntimeSupervisorStatus | None,
        persisted_reconciliation: MT5ReconciliationReceipt | None,
        current_lifecycle: MT5RuntimeSupervisorStatus | None,
        current_reconciliation: MT5ReconciliationReceipt | None,
        approval: ApprovalIntegrityResult,
        now: datetime,
    ) -> FinalValidationResult:
        blockers: list[str] = []
        symbol_metadata_hash = ""
        if snapshot is None:
            blockers.append("MARKET_SNAPSHOT_NOT_PERSISTED")
        else:
            order_validation = validate_autonomous_candidate_order_snapshot(
                candidate,
                snapshot,
                now=now,
                maximum_age_seconds=self.decision_config.input_max_age_seconds,
            )
            blockers.extend(order_validation.issues)
            symbol_metadata_hash = autonomous_symbol_metadata_hash(snapshot)

        expected_account_hash = _sha256(str(expected_fingerprint).strip().lower())
        if capability is None:
            blockers.append("TERMINAL_CAPABILITY_MISSING")
        else:
            if not capability.integrity_valid():
                blockers.append("TERMINAL_CAPABILITY_INTEGRITY_FAILED")
            if capability.symbol != candidate.symbol_reference or capability.broker_symbol != candidate.broker_symbol_reference:
                blockers.append("TERMINAL_CAPABILITY_SYMBOL_MISMATCH")
            if capability.broker_symbol != broker_symbol_for(candidate.symbol_reference):
                blockers.append("BROKER_SYMBOL_REFERENCE_MISMATCH")
            if not hmac.compare_digest(
                capability.account_fingerprint_hash, expected_account_hash
            ):
                blockers.append("TERMINAL_CAPABILITY_ACCOUNT_MISMATCH")
            if not capability.trade_allowed:
                blockers.append("SYMBOL_NOT_TRADE_ENABLED")
            if candidate.order_type not in set(capability.supported_order_types):
                blockers.append("ORDER_TYPE_CAPABILITY_MISMATCH")
            if not _fresh(
                capability.observed_at,
                now,
                self.decision_config.input_max_age_seconds,
            ):
                blockers.append("TERMINAL_CAPABILITY_STALE")

        blockers.extend(
            _lifecycle_blockers(
                candidate,
                persisted_lifecycle,
                persisted_reconciliation,
                current_lifecycle,
                current_reconciliation,
                now,
                self.decision_config.input_max_age_seconds,
            )
        )
        permission_state = execution_permission_state(self.config)
        permission_valid = (
            (
                mandate_permissions_safely_disabled(permission_state)
                or mandate_permissions_execution_ready(
                    permission_state,
                    action=candidate.action,
                    order_type=candidate.order_type,
                )
            )
            if approval.authorization_source == "STANDING_MANDATE"
            else (
                _permissions_safely_disabled(permission_state)
                or _human_permissions_execution_ready(permission_state)
            )
        )
        if not permission_valid:
            blockers.append("CURRENT_PERMISSION_STATE_MISMATCH")
        permission_hash = _hash(permission_state)
        authorization_id = _authorization_id(confirmation)
        authorization_binding_hash = _authorization_binding_hash(confirmation)
        authorization_expires_at = _authorization_expires_at(confirmation)
        authorization_source_refs = _authorization_source_refs(candidate, confirmation)
        protected_intent = {
            "state": PRE_SUBMIT_STATE,
            "candidate_reference": candidate.candidate_reference,
            "candidate_provenance_hash": candidate.provenance_hash,
            "structured_order_hash": candidate.structured_order_hash,
            "proposal_source": candidate.proposal_source,
            "proposal_source_reference": candidate.proposal_source_reference,
            "authorization_source": approval.authorization_source,
            "authorization_id": authorization_id,
            "confirmation_intent_id": (
                confirmation.intent_id
                if approval.authorization_source == "HUMAN_CONFIRMATION"
                else ""
            ),
            "authorization_binding_hash": authorization_binding_hash,
            "approval_integrity_hash": approval.approval_integrity_hash,
            "account_fingerprint_hash": expected_account_hash,
            "symbol": candidate.symbol_reference,
            "broker_symbol": candidate.broker_symbol_reference,
            "side": candidate.side,
            "order_type": candidate.order_type,
            "action": candidate.action,
            "entry_price": candidate.entry_price,
            "trigger_price": candidate.trigger_price,
            "limit_price": candidate.limit_price,
            "stop_loss": candidate.stop_loss,
            "take_profit": candidate.take_profit,
            "volume": candidate.proposed_volume,
            "terminal_capability_reference": (
                capability.capability_reference if capability else ""
            ),
            "lifecycle_reference": candidate.lifecycle_observation_reference,
            "reconciliation_reference": candidate.reconciliation_reference,
            "validated_at": now.isoformat(),
            "expires_at": min(
                candidate.expires_at, authorization_expires_at
            ),
            "permission_state": permission_state,
            "source_refs": list(authorization_source_refs),
            "non_submitted": True,
            "live_submission_allowed": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "order_sent": False,
        }
        blockers = list(_unique(blockers))
        material = {
            "approval_integrity_hash": approval.approval_integrity_hash,
            "protected_intent": protected_intent,
            "terminal_capability_hash": capability.capability_hash if capability else "",
            "symbol_metadata_hash": symbol_metadata_hash,
            "blockers": blockers,
        }
        digest = _hash(material)
        return FinalValidationResult(
            "approval_final_validation_" + digest[:24],
            now.isoformat(),
            not blockers,
            candidate.candidate_reference,
            (
                confirmation.intent_id
                if approval.authorization_source == "HUMAN_CONFIRMATION"
                else ""
            ),
            approval.approval_integrity_hash,
            capability.capability_reference if capability else "",
            candidate.lifecycle_observation_reference,
            candidate.reconciliation_reference,
            permission_hash,
            symbol_metadata_hash,
            tuple(blockers),
            (
                ("SUBMISSION_DISABLED",)
                if approval.authorization_source == "STANDING_MANDATE"
                else ("SUBMISSION_DISABLED", "KILL_SWITCH_ENGAGED")
            ),
            protected_intent if not blockers else {},
            approval.authorization_source,
            authorization_id,
        )

    def _report(self, final, candidate, confirmation) -> MT5PreSubmitGateReport:
        intent_hash = _hash(final.protected_intent) if final.valid else ""
        key = _sha256(
            "approval-pre-submit/v1|"
            + final.approval_integrity_hash
            + "|"
            + intent_hash
        )
        report = MT5PreSubmitGateReport(
            report_id="approval_pre_submit_report_" + key[:24],
            created_at=final.created_at,
            status=PRE_SUBMIT_STATE if final.valid else "BLOCKED",
            valid=final.valid,
            controlled_demo_integration_workflow_allowed=final.valid,
            live_submission_allowed=False,
            source_final_validation_id=final.final_validation_id,
            source_final_validation_report_id=final.final_validation_id,
            source_bridge_skeleton_check_id="",
            source_kill_switch_check_id="",
            source_idempotency_check_id="",
            adapter_receipt_id="",
            kill_switch_engaged=bool(self.config.kill_switch_engaged),
            idempotency_status="CHECK_REGISTERED" if final.valid else "INVALID",
            blockers=list(final.blockers),
            warnings=list(final.warnings),
            source_refs=list(_authorization_source_refs(candidate, confirmation)),
            approval_integrity_valid=bool(final.approval_integrity_hash),
            final_validation_valid=final.valid,
            pre_submit_ready=final.valid,
            submission_disabled=True,
            source_candidate_reference=candidate.candidate_reference,
            source_confirmation_intent_id=(
                confirmation.intent_id
                if final.authorization_source == "HUMAN_CONFIRMATION"
                else ""
            ),
            terminal_capability_reference=final.terminal_capability_reference,
            lifecycle_reference=final.lifecycle_reference,
            reconciliation_reference=final.reconciliation_reference,
            intent_hash=intent_hash,
            idempotency_key_hash=_sha256(key),
            authorization_source=final.authorization_source,
            source_authorization_id=final.authorization_id,
        )
        report.payload_size_chars = len(_canonical(report.as_dict()))
        return report

    def _record(self, final, report, candidate, confirmation):
        record = MT5PreSubmitJournalRecord(
            journal_record_id="mt5_pre_submit_journal_" + report.report_id[-24:],
            created_at=final.created_at,
            event_type="MT5_PRE_SUBMIT_READY_NON_EXECUTABLE",
            pre_submit_report_id=report.report_id,
            adapter_receipt_id="",
            status=PRE_SUBMIT_STATE,
            valid=True,
            controlled_demo_integration_workflow_allowed=True,
            live_submission_allowed=False,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            order_sent=False,
            ticket=None,
            deal=None,
            hard_live_block_required=True,
            kill_switch_engaged=bool(self.config.kill_switch_engaged),
            idempotency_status="CHECK_REGISTERED",
            bridge_write_skeleton_reachable=False,
            bridge_write_skeleton_status="NOT_CALLED",
            source_final_validation_id=final.final_validation_id,
            artifact_hash=report.intent_hash,
            idempotency_key_hash=report.idempotency_key_hash,
            payload_size_chars=len(_canonical(final.protected_intent)),
            metadata_redacted=True,
            source_candidate_reference=candidate.candidate_reference,
            source_confirmation_intent_id=(
                confirmation.intent_id
                if final.authorization_source == "HUMAN_CONFIRMATION"
                else ""
            ),
            approval_integrity_hash=final.approval_integrity_hash,
            pre_submit_state=PRE_SUBMIT_STATE,
            protected_intent=dict(final.protected_intent),
            authorization_source=final.authorization_source,
            source_authorization_id=final.authorization_id,
        )
        material = record.as_dict()
        material["record_hash"] = ""
        record.record_hash = pre_submit_record_hash(material)
        return record


def _runtime_evidence(payload):
    if not isinstance(payload, Mapping):
        return None, None
    lifecycle_payload = payload.get("lifecycle_status")
    reconciliation_payload = payload.get("reconciliation_result")
    lifecycle = _construct(MT5RuntimeSupervisorStatus, lifecycle_payload)
    reconciliation = _construct(MT5ReconciliationReceipt, reconciliation_payload)
    return lifecycle, reconciliation


def _lifecycle_blockers(
    candidate,
    persisted_lifecycle,
    persisted_reconciliation,
    current_lifecycle,
    current_reconciliation,
    now,
    maximum_age_seconds,
) -> list[str]:
    blockers: list[str] = []
    if persisted_lifecycle is None or current_lifecycle is None:
        return ["LIFECYCLE_EVIDENCE_MISSING"]
    if candidate.lifecycle_observation_reference != autonomous_lifecycle_status_reference(
        persisted_lifecycle
    ):
        blockers.append("LIFECYCLE_REFERENCE_MISMATCH")
    unsafe_states = {
        "RESULT_UNKNOWN",
        "RECONCILIATION_REQUIRED",
        "AMBIGUOUS",
        "SUBMISSION_STARTED",
    }
    for status in (persisted_lifecycle, current_lifecycle):
        if (
            status.supervisor_status != "HEALTHY"
            or not status.bridge_available
            or not status.account_context_match
            or status.discrepancy_count
        ):
            blockers.append("LIFECYCLE_CONFLICT")
        if any(status.lifecycle_state_counts.get(state, 0) for state in unsafe_states):
            blockers.append("UNRESOLVED_EXECUTION_STATE")
        if not _fresh(status.last_successful_cycle or "", now, maximum_age_seconds):
            blockers.append("LIFECYCLE_STALE")
    if candidate.reconciliation_reference != (
        persisted_reconciliation.reconciliation_reference
        if persisted_reconciliation is not None
        else ""
    ):
        blockers.append("RECONCILIATION_REFERENCE_MISMATCH")
    for receipt in (persisted_reconciliation, current_reconciliation):
        if receipt is None:
            continue
        if (
            receipt.resulting_execution_state == "RESULT_UNKNOWN"
            or receipt.evidence_classification
            in {"AMBIGUOUS_MATCH", "QUERY_FAILED", "RESULT_UNKNOWN"}
            or receipt.retry_decision != "RETRY_PROHIBITED"
        ):
            blockers.append("RECONCILIATION_CONFLICT")
    return list(_unique(blockers))


def _permissions_safely_disabled(state: Mapping[str, bool]) -> bool:
    return (
        state.get("live_adapter_hard_block") is True
        and state.get("pending_submission_hard_block") is True
        and state.get("kill_switch_engaged") is True
        and all(
            state.get(name) is False
            for name in (
                "live_adapter_enabled",
                "allow_live_submission",
                "allow_order_send",
                "controlled_execution_enabled",
                "pending_submission_enabled",
                "global_live_execution_enabled",
                "global_order_send_enabled",
                "autonomous_policy_gate_enabled",
            )
        )
    )


def _human_permissions_execution_ready(state: Mapping[str, bool]) -> bool:
    return (
        state.get("live_adapter_enabled") is True
        and state.get("live_adapter_hard_block") is False
        and state.get("allow_live_submission") is True
        and state.get("allow_order_send") is True
        and state.get("controlled_execution_enabled") is True
        and state.get("kill_switch_engaged") is False
        and state.get("global_live_execution_enabled") is True
        and state.get("global_order_send_enabled") is True
    )


def _blocked_final(final: FinalValidationResult, blocker: str) -> FinalValidationResult:
    return FinalValidationResult(
        final.final_validation_id,
        final.created_at,
        False,
        final.candidate_reference,
        final.confirmation_intent_id,
        final.approval_integrity_hash,
        final.terminal_capability_reference,
        final.lifecycle_reference,
        final.reconciliation_reference,
        final.permission_state_hash,
        final.symbol_metadata_hash,
        _unique((*final.blockers, blocker)),
        final.warnings,
        {},
        final.authorization_source,
        final.authorization_id,
    )


def _authorization_id(authorization: Any) -> str:
    return str(
        getattr(authorization, "authorization_id", "")
        or getattr(authorization, "intent_id", "")
    )


def _authorization_binding_hash(authorization: Any) -> str:
    return str(
        getattr(authorization, "artifact_hash", "")
        or getattr(authorization, "confirmation_binding_hash", "")
    )


def _authorization_expires_at(authorization: Any) -> str:
    return str(
        getattr(authorization, "expires_at", "")
        or getattr(authorization, "confirmation_expires_at", "")
    )


def _authorization_source_refs(candidate: Any, authorization: Any) -> tuple[str, ...]:
    if isinstance(authorization, MandateCandidateAuthorization):
        return tuple(authorization.source_refs)
    return candidate_confirmation_source_refs(candidate)


def _construct(cls, payload):
    if not isinstance(payload, Mapping):
        return None
    allowed = {item.name for item in fields(cls)}
    try:
        return cls(**{key: value for key, value in payload.items() if key in allowed})
    except (TypeError, ValueError):
        return None


def _fresh(value: str, now: datetime, maximum_age_seconds: int) -> bool:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
        return -5 <= age <= maximum_age_seconds
    except (TypeError, ValueError):
        return False


def _expired(value: str, now: datetime) -> bool:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc) < now
    except (TypeError, ValueError):
        return True


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return _sha256(_canonical(value))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_hash(value: str) -> bool:
    return len(str(value or "")) == 64 and all(
        character in "0123456789abcdef" for character in str(value).lower()
    )


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))
