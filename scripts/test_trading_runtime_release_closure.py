from __future__ import annotations

import gc
import json
import math
import statistics
import threading
import time
from pathlib import Path

import psutil

from scripts.test_autonomous_decision_orchestrator import NOW, make_inputs
from scripts.test_autonomous_execution_policy_gate import ACCOUNT_REFERENCE
from scripts.test_mt5_position_lifecycle_supervisor import (
    ACCOUNT_B,
    FakeLifecycleClient,
    MT5LifecycleJournal,
    MT5PositionLifecycleSupervisor,
    make_snapshot,
    open_position,
    seed_execution,
)
from scripts.test_mt5_reconciliation_failure_recovery import (
    AUTH_TOKEN,
    FakeReconciliationClient,
    config as reconciliation_config,
    reconcile,
    seed_record,
    unique_evidence,
)
from src.services.trading.decision.autonomous_execution_policy import (
    AutonomousExecutionPolicyConfig,
    AutonomousExecutionPolicyGate,
    AutonomousPolicyInputs,
)
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousDecisionConfig,
    AutonomousDecisionOrchestrator,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5LifecycleState,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
)
from tools.mt5_bridge.execution import ControlledExecutionConfig
from tools.mt5_bridge.management import ControlledManagementConfig
from tools.mt5_bridge.reconciliation import ControlledMT5ReconciliationService


def test_complete_non_mutating_decision_policy_chain_is_fail_closed(tmp_path):
    source = make_inputs()
    orchestrator = AutonomousDecisionOrchestrator(
        AutonomousDecisionConfig(journal_path=str(tmp_path / "decisions.jsonl"))
    )
    decision = orchestrator.run_once(source, now=NOW)
    assert decision.validation.valid is True
    assert decision.candidate.execution_authority is False
    assert decision.candidate.executable is False

    policy = AutonomousExecutionPolicyGate(
        AutonomousExecutionPolicyConfig(journal_path=str(tmp_path / "policy.jsonl"))
    ).run_once(_policy_inputs(decision.candidate, source), now=NOW)
    assert policy.validation.valid is True
    assert policy.policy_result.decision == "BLOCK"
    assert policy.policy_result.target_controlled_boundary == "NONE"
    assert "POLICY_GATE_DISABLED" in policy.policy_result.deterministic_reason_codes
    _assert_non_executable(policy.policy_result)


def test_no_action_and_human_review_never_gain_authority(tmp_path):
    enabled = AutonomousExecutionPolicyConfig(
        enabled=True,
        open_eligibility_enabled=True,
        management_eligibility_enabled=True,
        hard_block=False,
        journal_path=str(tmp_path / "policy.jsonl"),
    )
    gate = AutonomousExecutionPolicyGate(enabled)
    no_action_source = make_inputs(risk_action="NO_TRADE", requested_intent="AUTO")
    review_source = make_inputs(requested_intent="REQUIRE_HUMAN_REVIEW")
    candidates = []
    for source in (no_action_source, review_source):
        candidates.append(
            AutonomousDecisionOrchestrator(
                AutonomousDecisionConfig(journal_path=str(tmp_path / "unused.jsonl"))
            ).build_candidate(source, now=NOW)
        )
    no_action = gate.run_once(_policy_inputs(candidates[0], no_action_source), now=NOW)
    review = gate.run_once(_policy_inputs(candidates[1], review_source), now=NOW)
    assert no_action.policy_result.decision == "BLOCK"
    assert no_action.policy_result.target_controlled_boundary == "NONE"
    assert "NO_ACTION_TERMINAL" in no_action.policy_result.deterministic_reason_codes
    assert review.policy_result.decision == "REQUIRE_HUMAN_REVIEW"
    assert review.policy_result.target_controlled_boundary == "NONE"
    _assert_non_executable(no_action.policy_result)
    _assert_non_executable(review.policy_result)


def test_restart_duplicate_bridge_loss_and_account_change_fail_closed(tmp_path):
    lifecycle_root = tmp_path / "lifecycle"
    cfg = seed_execution(lifecycle_root)
    snapshot = make_snapshot(positions=[open_position()])
    first = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient(snapshot))
    assert first.run_once().observations_appended == 1
    restarted = MT5PositionLifecycleSupervisor(cfg, bridge_client=FakeLifecycleClient(snapshot))
    assert restarted.run_once().observations_appended == 0
    assert len(MT5LifecycleJournal(cfg.lifecycle_journal_path).observations()) == 1

    unavailable = MT5PositionLifecycleSupervisor(
        cfg, bridge_client=FakeLifecycleClient(snapshot, error=True)
    ).run_once()
    assert unavailable.supervisor_status == "BLOCKED"
    assert unavailable.health_reason == "BRIDGE_UNAVAILABLE"

    changed = MT5PositionLifecycleSupervisor(
        cfg,
        bridge_client=FakeLifecycleClient(
            make_snapshot(fingerprint=ACCOUNT_B, positions=[open_position()])
        ),
    ).run_once()
    assert changed.supervisor_status == "DEGRADED"
    assert changed.account_context_match is False
    assert changed.lifecycle_state_counts == {MT5LifecycleState.INCONSISTENT.value: 2}
    assert changed.historical_unresolved_records == 1


def test_timeout_auth_unknown_and_corrupt_persistence_remain_closed(tmp_path):
    timeout_root = tmp_path / "timeout"
    timeout_root.mkdir()
    timeout_payload, _, _, _, _ = reconcile(
        timeout_root, FakeReconciliationClient(raise_query=True)
    )
    assert timeout_payload["resulting_execution_state"] == "RESULT_UNKNOWN"
    assert timeout_payload["retry_decision"] == "RETRY_PROHIBITED"
    assert timeout_payload["automatic_retry_allowed"] is False

    auth_root = tmp_path / "auth"
    auth_root.mkdir()
    request, journal = seed_record(auth_root)
    client = FakeReconciliationClient(unique_evidence())
    service = ControlledMT5ReconciliationService(
        client,
        config=reconciliation_config(auth_root),
        journal=journal,
    )
    payload, status = service.handle(request.as_protected_dict(), "wrong-token")
    assert status == 401
    assert payload["status"] == "BLOCKED"
    assert client.query_calls == 0

    corrupt_root = tmp_path / "corrupt"
    corrupt_root.mkdir()
    corrupt_cfg = seed_execution(corrupt_root)
    Path(corrupt_cfg.lifecycle_journal_path).write_text('{"truncated":', encoding="utf-8")
    corrupt_client = FakeLifecycleClient()
    corrupt = MT5PositionLifecycleSupervisor(
        corrupt_cfg, bridge_client=corrupt_client
    ).run_once()
    assert corrupt.supervisor_status == "PERSISTENCE_UNSAFE"
    assert corrupt.health_reason == "LIFECYCLE_JOURNAL_CORRUPT"
    assert corrupt_client.calls == 0


def test_overlapping_lifecycle_cycle_is_skipped_without_leaking_thread(tmp_path):
    cfg = seed_execution(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    supervisor = MT5PositionLifecycleSupervisor(
        cfg,
        bridge_client=FakeLifecycleClient(
            make_snapshot(positions=[open_position()]), entered=entered, release=release
        ),
    )
    worker = threading.Thread(target=supervisor.run_once)
    worker.start()
    assert entered.wait(timeout=1)
    overlap = supervisor.run_once()
    assert overlap.supervisor_status == "CYCLE_SKIPPED_OVERLAP"
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_default_configs_and_static_release_invariants():
    app = MT5LiveAdapterPreSubmitConfig()
    bridge = ControlledExecutionConfig()
    management = ControlledManagementConfig()
    policy = AutonomousExecutionPolicyConfig()
    assert app.allow_live_submission is False
    assert app.allow_order_send is False
    assert app.kill_switch_engaged is True
    assert app.controlled_execution_enabled is False
    assert app.controlled_management_enabled is False
    assert app.management_hard_block is True
    assert app.management_kill_switch_engaged is True
    assert app.management_cancel_allowed is False
    assert app.management_protection_modification_allowed is False
    assert app.management_position_close_allowed is False
    assert bridge.enabled is False and bridge.hard_block is True
    assert bridge.order_send_enabled is False and bridge.live_execution_enabled is False
    assert management.enabled is False and management.hard_block is True
    assert management.kill_switch_engaged is True
    assert management.cancel_allowed is False
    assert management.protection_modification_allowed is False
    assert management.position_close_allowed is False
    assert policy.enabled is False and policy.hard_block is True
    assert policy.open_eligibility_enabled is False
    assert policy.management_eligibility_enabled is False

    production_files = [
        path for root in (Path("src"), Path("tools")) for path in root.rglob("*.py")
    ]
    production = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in production_files
    )
    assert production.count(".order_send(") == 1
    assert "import MetaTrader5" not in "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in Path("src").rglob("*.py")
    )
    autonomous = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "src/services/trading/decision/autonomous_orchestrator.py",
            "src/services/trading/decision/autonomous_execution_policy.py",
            "src/services/trading/execution/mt5_live_adapter_pre_submit/lifecycle_supervisor.py",
            "src/services/trading/execution/mt5_live_adapter_pre_submit/reconciliation.py",
        )
    )
    for marker in (
        ".order_send(",
        "/execution/controlled-submit",
        "/execution/controlled-manage",
        "human_confirmation_present=True",
        "automatic_retry_allowed=True",
    ):
        assert marker not in autonomous


def test_bounded_non_mutating_soak_and_resource_growth(tmp_path):
    process = psutil.Process()
    gc.collect()
    rss_start = process.memory_info().rss
    threads_start = process.num_threads()
    decision_latencies: list[float] = []
    policy_latencies: list[float] = []
    lifecycle_latencies: list[float] = []
    reconciliation_latencies: list[float] = []

    decision_path = tmp_path / "decisions.jsonl"
    decision_service = AutonomousDecisionOrchestrator(
        AutonomousDecisionConfig(journal_path=str(decision_path))
    )
    decision_sources = (
        make_inputs(risk_action="NO_TRADE", requested_intent="AUTO"),
        make_inputs(requested_intent="REQUIRE_HUMAN_REVIEW"),
        make_inputs(risk_action="BLOCKED"),
    )
    candidates = []
    for index in range(300):
        started = time.perf_counter()
        result = decision_service.run_once(decision_sources[index % 3], now=NOW)
        decision_latencies.append((time.perf_counter() - started) * 1000)
        assert result.validation.valid is True
        assert result.candidate.execution_authority is False
        assert result.candidate.executable is False
        if index < 3:
            candidates.append(result.candidate)
    rss_warm = process.memory_info().rss

    policy_path = tmp_path / "policy.jsonl"
    policy_service = AutonomousExecutionPolicyGate(
        AutonomousExecutionPolicyConfig(journal_path=str(policy_path))
    )
    policy_inputs = tuple(
        _policy_inputs(candidate, source)
        for candidate, source in zip(candidates, decision_sources)
    )
    for index in range(300):
        started = time.perf_counter()
        result = policy_service.run_once(policy_inputs[index % 3], now=NOW)
        policy_latencies.append((time.perf_counter() - started) * 1000)
        assert result.validation.valid is True
        assert result.policy_result.decision == "BLOCK"
        _assert_non_executable(result.policy_result)

    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_cfg = seed_execution(lifecycle_root)
    lifecycle_client = FakeLifecycleClient(
        make_snapshot(positions=[open_position()], reference="stable-open")
    )
    lifecycle = MT5PositionLifecycleSupervisor(
        lifecycle_cfg, bridge_client=lifecycle_client
    )
    for index in range(200):
        if index == 100:
            lifecycle_client.snapshot = make_snapshot(
                positions=[open_position(volume="0.50")], reference="partial"
            )
        elif index == 150:
            lifecycle_client.error = True
        elif index == 151:
            lifecycle_client.error = False
        elif index == 175:
            lifecycle_client.snapshot = make_snapshot(
                fingerprint=ACCOUNT_B,
                positions=[open_position(volume="0.50")],
                reference="account-mismatch",
            )
        elif index == 176:
            lifecycle_client.snapshot = make_snapshot(
                positions=[open_position(volume="0.50")], reference="restored"
            )
        started = time.perf_counter()
        status = lifecycle.run_once()
        lifecycle_latencies.append((time.perf_counter() - started) * 1000)
        assert status.order_send_allowed is False
        assert status.execution_allowed is False
        assert status.executable is False
        assert status.automatic_retry_allowed is False
        assert status.kill_switch_engaged is True

    reconciliation_root = tmp_path / "reconciliation"
    reconciliation_root.mkdir()
    recon_client = FakeReconciliationClient(unique_evidence())
    payload, _, request, _, recon_service = reconcile(reconciliation_root, recon_client)
    assert payload["status"] == "CONFIRMED"
    for _ in range(50):
        started = time.perf_counter()
        repeated, status = recon_service.handle(request.as_protected_dict(), AUTH_TOKEN)
        reconciliation_latencies.append((time.perf_counter() - started) * 1000)
        assert status == 200
        assert repeated == payload
    assert recon_client.query_calls == 1

    gc.collect()
    rss_end = process.memory_info().rss
    threads_end = process.num_threads()
    decision_records = _jsonl_count(decision_path)
    policy_records = _jsonl_count(policy_path)
    lifecycle_records = _jsonl_count(Path(lifecycle_cfg.lifecycle_journal_path))
    journal_bytes = sum(
        path.stat().st_size for path in tmp_path.rglob("*.jsonl") if path.is_file()
    )
    metrics = {
        "decision": _latency_summary(decision_latencies),
        "policy": _latency_summary(policy_latencies),
        "lifecycle": _latency_summary(lifecycle_latencies),
        "reconciliation_read": _latency_summary(reconciliation_latencies),
        "rss_start_bytes": rss_start,
        "rss_warm_bytes": rss_warm,
        "rss_end_bytes": rss_end,
        "rss_growth_after_warm_bytes": rss_end - rss_warm,
        "threads_start": threads_start,
        "threads_end": threads_end,
        "decision_journal_records": decision_records,
        "policy_journal_records": policy_records,
        "lifecycle_journal_records": lifecycle_records,
        "journal_bytes": journal_bytes,
    }
    print("release_soak_metrics=" + json.dumps(metrics, sort_keys=True))
    assert decision_records == 3
    assert policy_records == 3
    assert lifecycle_records <= 6
    assert journal_bytes < 1_000_000
    assert rss_end - rss_warm < 64 * 1024 * 1024
    assert threads_end <= threads_start + 1


def _policy_inputs(candidate, source) -> AutonomousPolicyInputs:
    return AutonomousPolicyInputs(
        candidate=candidate,
        risk_result=source.risk_result,
        account_context_reference=ACCOUNT_REFERENCE,
        account_context_created_at=NOW.isoformat(),
        account_context_matches=True,
        semantic_proposal_complete=True,
        lifecycle_observation=source.lifecycle_observation,
        reconciliation_result=source.reconciliation_result,
        management_exposure_effect=source.exposure_effect,
        requested_close_volume="0.5" if candidate.intent == "CLOSE_POSITION" else "1.0",
        observed_volume="1.0",
    )


def _assert_non_executable(value) -> None:
    for field in (
        "execution_authority",
        "human_confirmation_present",
        "execution_permission_requested",
        "live_submission_allowed",
        "live_execution_allowed",
        "order_send_allowed",
        "execution_allowed",
        "executable",
        "order_sent",
    ):
        assert getattr(value, field) is False


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(ordered[-1], 3),
    }
