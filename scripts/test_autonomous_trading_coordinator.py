from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

from scripts.test_approval_final_validation_pre_submit import (
    _capability,
    _persisted_lifecycle,
    _prepared,
)
from scripts.test_autonomous_candidate_monitor import FeatureService
from scripts.test_operator_review_confirmation_lifecycle import NOW
from src.services.trading.decision.autonomous_candidate_monitor import (
    AutonomousCandidateMonitorJournal,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionRunResult,
)
from src.services.trading.decision.operator_candidate_generation import (
    OperatorCandidateInputError,
)
from src.services.trading.decision.autonomous_trading_coordinator import (
    AutonomousTradingCoordinator,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    ApprovalPreSubmitLifecycleService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    MT5ControlledExecutionReceipt,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from scripts.test_standing_trading_mandate_authority import _CandidateJournalView


def test_advisory_and_human_modes_stop_before_mandate_authorization(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "advisory_only")
    coordinator, orchestrator = _coordinator(tmp_path, candidate, authority)

    advisory = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))
    authority.set_mode(
        "human_confirmed_live",
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="human-mode-1",
        now=NOW,
    )
    coordinator.monitor.feature_service.bar_time = "2026-07-21T12:01:00+00:00"
    human = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert advisory.status == "ADVISORY_CANDIDATE"
    assert human.status == "AWAITING_HUMAN_CONFIRMATION"
    assert human.authorization_source == "HUMAN_CONFIRMATION"
    assert orchestrator.calls == 2
    assert all(
        row["event_type"] != "CANDIDATE_AUTHORIZED"
        for row in authority.store.read_strict()
    )


def test_autonomous_mode_requires_mandate_context(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "autonomous_live")
    coordinator, _ = _coordinator(tmp_path, candidate, authority)

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "BLOCKED"
    assert result.blocker == "MANDATE_CONTEXT_MISSING"
    assert result.authorization_source == "STANDING_MANDATE"


def test_autonomous_mode_authorizes_exact_candidate_without_execution(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "autonomous_live")
    mandate = _mandate(authority)
    coordinator, _ = _coordinator(
        tmp_path,
        candidate,
        authority,
        mandate_context_provider=lambda _candidate, _inputs: {
            "mandate_id": mandate.mandate_id,
            "evaluated_risk_per_trade": "0.5",
            "concurrent_positions": 0,
            "trades_today": 0,
            "loss_today": "0",
            "kill_switch_engaged": False,
            "authorization_nonce": "coordinator-authorization-1",
        },
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "AUTHORIZED_NON_EXECUTABLE"
    assert result.authorization_source == "STANDING_MANDATE"
    assert result.pre_submit_ready is False
    assert result.execution_authority is False
    assert result.submission_called is result.order_send_called is False
    rows = authority.store.read_strict()
    assert sum(row["event_type"] == "CANDIDATE_AUTHORIZED" for row in rows) == 1


def test_unknown_or_conflicting_lifecycle_blocks_before_orchestrator(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "advisory_only")
    unsafe = SimpleNamespace(
        supervisor_status="HEALTHY",
        bridge_available=True,
        account_context_match=True,
        discrepancy_count=0,
        lifecycle_state_counts={"RESULT_UNKNOWN": 1},
    )
    coordinator, orchestrator = _coordinator(
        tmp_path, candidate, authority, lifecycle=unsafe
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.blocker == "COORDINATOR_RUNTIME_STATE_UNSAFE"
    assert orchestrator.calls == 0


def test_rearm_reason_is_terminal_no_action_before_orchestrator(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "autonomous_live")
    coordinator, orchestrator = _coordinator(tmp_path, candidate, authority)

    class RearmAssembler:
        def build(self, **_kwargs):
            raise OperatorCandidateInputError(
                "ENTRY_CONDITION_WAITING_FOR_REARM",
            )

    coordinator.input_assembler = RearmAssembler()
    result = coordinator.run_once(
        symbol="XAUUSD", timeframes=("M15", "H1", "H4")
    )

    assert result.status == result.intent == "NO_ACTION"
    assert result.blocker == "ENTRY_CONDITION_WAITING_FOR_REARM"
    assert orchestrator.calls == 0


def test_missing_or_mismatched_account_authority_fails_closed(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "advisory_only")
    coordinator, _ = _coordinator(
        tmp_path,
        candidate,
        authority,
        account_context={
            "status": "OK",
            "account_context_fingerprint": "b" * 64,
            "account_id_hash": "account-b",
            "captured_at": NOW.isoformat(),
            "account_is_demo": True,
            "redacted": True,
        },
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.blocker == "MODE_ACCOUNT_MISMATCH"


def test_one_coordinator_operation_is_active_at_a_time(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    coordinator, orchestrator = _coordinator(
        tmp_path, candidate, _authority(tmp_path / "authority", "advisory_only")
    )
    coordinator._run_lock.acquire()
    try:
        result = coordinator.run_once(
            symbol="XAUUSD", timeframes=("M15", "H1", "H4")
        )
    finally:
        coordinator._run_lock.release()

    assert result.blocker == "COORDINATOR_BUSY"
    assert orchestrator.calls == 0


def test_pre_submit_ready_mandate_uses_existing_execution_adapter_once(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    state["candidate_journal"] = _CandidateJournalView(
        state["candidate_journal"], candidate
    )
    authority = _authority(tmp_path / "authority", "autonomous_live")
    mandate = _mandate(authority)
    approval = ApprovalPreSubmitLifecycleService(
        candidate_journal=state["candidate_journal"],
        confirmation_store=state["review_store"],
        pre_submit_store=state["pre_submit_store"],
        config=MT5LiveAdapterPreSubmitConfig(kill_switch_engaged=False),
        authority_service=authority,
    )
    adapter = _ExecutionAdapter()
    coordinator, _ = _coordinator(
        tmp_path,
        candidate,
        authority,
        mandate_context_provider=lambda _candidate, _inputs: {
            "mandate_id": mandate.mandate_id,
            "evaluated_risk_per_trade": "0.5",
            "concurrent_positions": 0,
            "trades_today": 0,
            "loss_today": "0",
            "kill_switch_engaged": False,
            "authorization_nonce": "coordinator-execution-1",
            "terminal_capability": _capability({"candidate": candidate}),
        },
        approval_service=approval,
        execution_adapter=adapter,
        lifecycle=_persisted_lifecycle(state),
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.status == "RESULT_CONFIRMED"
    assert adapter.calls == 1
    assert adapter.request.authorization_source == "STANDING_MANDATE"
    assert adapter.typed_confirmation == ""


def test_autonomous_policy_block_stops_before_mandate_authorization(tmp_path):
    state = _prepared(tmp_path / "candidate", "fresh_market", confirm=False)
    candidate = replace(state["candidate"], operating_mode="autonomous_live")
    authority = _authority(tmp_path / "authority", "autonomous_live")
    context_calls = []
    blocked_gate = SimpleNamespace(
        run_once=lambda inputs, now=None: SimpleNamespace(
            persistence_safe=True,
            validation=SimpleNamespace(valid=True),
            policy_result=SimpleNamespace(
                decision="BLOCK",
                target_controlled_boundary="NONE",
                deterministic_reason_codes=("AUTONOMOUS_POLICY_DISABLED",),
            ),
            journal_warning="",
        )
    )
    coordinator, _ = _coordinator(
        tmp_path,
        candidate,
        authority,
        policy_gate=blocked_gate,
        mandate_context_provider=lambda *_: context_calls.append(True),
    )

    result = coordinator.run_once(symbol="XAUUSD", timeframes=("M15", "H1", "H4"))

    assert result.blocker == "AUTONOMOUS_POLICY_DISABLED"
    assert context_calls == []


class _ExecutionAdapter:
    def __init__(self):
        self.calls = 0
        self.request = None
        self.typed_confirmation = None

    def submit_prepared_request(self, request, *, typed_confirmation=""):
        self.calls += 1
        self.request = request
        self.typed_confirmation = typed_confirmation
        return MT5ControlledExecutionReceipt(
            "ACCEPTED", "RESULT_CONFIRMED", True, True, True
        )


class _Assembler:
    def __init__(self, lifecycle):
        self.lifecycle = lifecycle
        self.calls = 0

    def build(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            lifecycle_status=self.lifecycle,
            reconciliation_result=None,
        )


class _Orchestrator:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    def run_once(self, _inputs):
        self.calls += 1
        return AutonomousDecisionRunResult(
            candidate=self.candidate,
            validation=SimpleNamespace(valid=True, issues=()),
            journal_appended=True,
            persistence_safe=True,
        )


def _coordinator(
    tmp_path,
    candidate,
    authority,
    *,
    mandate_context_provider=None,
    lifecycle=None,
    account_context=None,
    approval_service=None,
    execution_adapter=None,
    policy_gate=None,
):
    lifecycle = lifecycle or SimpleNamespace(
        supervisor_status="HEALTHY",
        bridge_available=True,
        account_context_match=True,
        discrepancy_count=0,
        lifecycle_state_counts={},
    )
    orchestrator = _Orchestrator(candidate)
    account_context = account_context or {
        "status": "OK",
        "account_context_fingerprint": "a" * 64,
        "account_id_hash": "account-a",
        "captured_at": NOW.isoformat(),
        "account_is_demo": True,
        "redacted": True,
    }
    return (
        AutonomousTradingCoordinator(
            feature_service=FeatureService("2026-07-21T12:00:00+00:00"),
            input_assembler=_Assembler(lifecycle),
            account_context_provider=lambda: account_context,
            authority_service=authority,
            decision_orchestrator=orchestrator,
            mandate_context_provider=mandate_context_provider,
            approval_service=approval_service,
            execution_adapter=execution_adapter,
            policy_gate=policy_gate or _EligiblePolicyGate(),
            monitor_journal=AutonomousCandidateMonitorJournal(
                tmp_path / "monitor.jsonl"
            ),
            clock=lambda: NOW,
        ),
        orchestrator,
    )


def _authority(tmp_path, mode):
    authority = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    authority.set_mode(
        mode,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="mode-1",
        now=NOW,
    )
    return authority


def _mandate(authority):
    return authority.grant_mandate(
        mandate_id="coordinator-mandate-1",
        mandate_version=1,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        permitted_symbols=("XAUUSD",),
        permitted_broker_symbols=("XAUUSDm",),
        permitted_order_families=("MARKET", "PENDING"),
        permitted_management_actions=("OBSERVE",),
        maximum_volume="1",
        maximum_risk_per_trade="1",
        maximum_concurrent_positions=1,
        maximum_trades_per_day=2,
        maximum_loss_per_day="2",
        active_from=(NOW - timedelta(minutes=1)).isoformat(),
        active_until=(NOW + timedelta(hours=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        nonce="mandate-1",
        idempotency_key="mandate-key-1",
        kill_switch_engaged=False,
        operator_grant=True,
        now=NOW,
    )


class _EligiblePolicyGate:
    def run_once(self, inputs, now=None):
        return SimpleNamespace(
            persistence_safe=True,
            validation=SimpleNamespace(valid=True),
            policy_result=SimpleNamespace(
                decision="ELIGIBLE_FOR_CONTROLLED_BOUNDARY",
                target_controlled_boundary="CONTROLLED_OPEN_POSITION",
                deterministic_reason_codes=(),
            ),
            journal_warning="",
        )
