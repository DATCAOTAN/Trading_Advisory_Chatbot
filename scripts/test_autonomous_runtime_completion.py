from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.trading.decision.autonomous_runtime import AutonomousMonitorProcess
from src.services.trading.decision.autonomous_trading_coordinator import (
    production_mandate_context,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    MandateGrantCommand,
    TradingAuthorityOperatorService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5RuntimeSupervisorStatus,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)
from tools.mt5_bridge import mt5_client


NOW = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)


def test_daily_deal_summary_counts_openings_and_net_loss(monkeypatch):
    monkeypatch.setattr(
        mt5_client,
        "mt5",
        SimpleNamespace(DEAL_ENTRY_IN=1, DEAL_ENTRY_INOUT=2),
    )
    Deal = namedtuple(
        "Deal", "time_msc time entry order position_id ticket profit commission swap fee"
    )
    rows = [
        Deal(NOW.timestamp() * 1000, 0, 1, 10, 0, 100, -12, -1, 0, 0),
        Deal(NOW.timestamp() * 1000, 0, 1, 10, 0, 101, 3, 0, 0, 0),
        Deal(NOW.timestamp() * 1000, 0, 2, 11, 0, 102, -2, 0, 0, 0),
    ]

    assert mt5_client._daily_deal_summary(rows, NOW) == (2, "12")


def test_production_mandate_context_uses_lifecycle_and_symbol_metadata(tmp_path):
    authority, mandate = _authority(tmp_path)
    candidate = _candidate()
    lifecycle = MT5RuntimeSupervisorStatus(
        supervisor_status="HEALTHY",
        last_successful_cycle=NOW.isoformat(),
        bridge_available=True,
        account_context_match=True,
        active_position_count=1,
        trades_today=2,
        loss_today="15",
        terminal_trade_allowed=True,
        account_trade_allowed=True,
        mandate_limit_evidence_available=True,
    )
    inputs = SimpleNamespace(
        lifecycle_status=lifecycle,
        order_market_snapshot=SimpleNamespace(
            bid="62000", ask="62001", tick_size="1", tick_value="1"
        ),
    )

    context = production_mandate_context(
        candidate,
        inputs,
        authority_service=authority,
        mandate_id=mandate.mandate_id,
        account_context_fingerprint="a" * 64,
        kill_switch_engaged=False,
    )

    assert context["evaluated_risk_per_trade"] == "1"
    assert context["concurrent_positions"] == 1
    assert context["trades_today"] == 2
    assert context["loss_today"] == "15"
    assert context["terminal_capability"].trade_allowed is True


def test_missing_mandate_limit_evidence_fails_closed(tmp_path):
    authority, mandate = _authority(tmp_path)
    inputs = SimpleNamespace(
        lifecycle_status=MT5RuntimeSupervisorStatus(
            supervisor_status="HEALTHY", mandate_limit_evidence_available=False
        ),
        order_market_snapshot=SimpleNamespace(),
    )

    with pytest.raises(TradingAuthorityError, match="LIFECYCLE_NOT_HEALTHY"):
        production_mandate_context(
            _candidate(),
            inputs,
            authority_service=authority,
            mandate_id=mandate.mandate_id,
            account_context_fingerprint="a" * 64,
            kill_switch_engaged=False,
        )


def test_operator_service_reloads_mode_and_mandate_and_rejects_real_account(tmp_path):
    account = _AccountAdapter("DEMO")
    lifecycle = SimpleNamespace(
        status=lambda: MT5RuntimeSupervisorStatus(),
        run_once=lambda: MT5RuntimeSupervisorStatus(supervisor_status="HEALTHY"),
        execution_journal=SimpleNamespace(execution_records=lambda: []),
    )
    pre_submit = SimpleNamespace(
        summarize=lambda: SimpleNamespace(
            total_records=0,
            total_valid=0,
            total_blocked=0,
            latest_status="",
            warnings=[],
        )
    )
    authority = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    service = TradingAuthorityOperatorService(
        authority_service=authority,
        account_adapter=account,
        lifecycle_supervisor=lifecycle,
        pre_submit_store=pre_submit,
    )
    service.set_mode("autonomous_live", operator_grant=True)
    command = _mandate_command(datetime.now(timezone.utc))
    service.grant_mandate(command, operator_grant=True)
    status = service.status()
    assert status["mode"] == "autonomous_live"
    assert status["mandates"][0]["mandate_id"] == command.mandate_id
    assert status["permission_state"]["controlled_management_enabled"] is False
    assert status["permission_state"]["management_kill_switch_engaged"] is True
    assert status["permission_state"]["live_submission_allowed"] is False
    assert status["permission_state"]["order_send_allowed"] is False
    assert status["unresolved_execution_count"] == 0
    service.revoke_mandate(command.mandate_id, operator_grant=True)
    assert service.status()["mandates"][0]["revoked"] is True

    blocked = TradingAuthorityOperatorService(
        authority_service=authority,
        account_adapter=_AccountAdapter("REAL"),
        lifecycle_supervisor=lifecycle,
        pre_submit_store=pre_submit,
    )
    with pytest.raises(RuntimeError, match="REAL_ACCOUNT_AUTHORITY_FORBIDDEN"):
        blocked.set_mode("advisory_only", operator_grant=True)


def test_operator_mode_grant_is_idempotent_for_stable_request_id(tmp_path):
    authority = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    service = TradingAuthorityOperatorService(
        authority_service=authority,
        account_adapter=_AccountAdapter("DEMO"),
        lifecycle_supervisor=SimpleNamespace(),
        pre_submit_store=SimpleNamespace(),
    )

    first = service.set_mode(
        "human_confirmed_live",
        operator_grant=True,
        idempotency_key="conversation_trade_stable_request",
    )
    second = service.set_mode(
        "human_confirmed_live",
        operator_grant=True,
        idempotency_key="conversation_trade_stable_request",
    )

    assert second == first
    assert len(authority.store.read_strict()) == 1

    with pytest.raises(TradingAuthorityError, match="AUTHORITY_IDEMPOTENCY_CONFLICT"):
        service.set_mode(
            "autonomous_live",
            operator_grant=True,
            idempotency_key="conversation_trade_stable_request",
        )


def test_monitor_process_starts_once_and_stops(monkeypatch, tmp_path):
    script = tmp_path / "scripts" / "run_autonomous_candidate_monitor.py"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    processes = []

    class Process:
        def __init__(self, command, **kwargs):
            self.command = command
            self.returncode = None
            processes.append(self)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout):
            return self.returncode

    monkeypatch.setattr("subprocess.Popen", Process)
    controller = AutonomousMonitorProcess(tmp_path)
    first = controller.start(
        symbol="BTCUSD", timeframes=("M1", "H1", "H4"), mandate_id="mandate-1"
    )
    second = controller.start(
        symbol="BTCUSD", timeframes=("M1", "H1", "H4"), mandate_id="mandate-1"
    )

    assert first["running"] and second["running"]
    assert len(processes) == 1
    assert "--mandate-id" in processes[0].command
    assert controller.stop()["running"] is False


def test_monitor_process_requires_mandate_before_start(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *_args, **_kwargs: pytest.fail("supervisor process must not start"),
    )

    with pytest.raises(ValueError, match="SUPERVISOR_MANDATE_REQUIRED"):
        AutonomousMonitorProcess(tmp_path).start(
            symbol="XAUUSD", timeframes=("M1",), mandate_id=""
        )


def test_dashboard_controls_delegate_without_broker_mutation():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")
    assert "Trading Authority and Runtime Supervisor" in source
    assert "Confirm Standing Mandate" in source
    assert "Revoke Mandate" in source
    assert "Start Supervisor" in source
    assert "Stop Supervisor" in source
    assert 'disabled=process_status["running"] or monitor_mandate is None' in source
    assert ".order_send(" not in source
    assert "controlled-submit" not in source


class _AccountAdapter:
    def __init__(self, environment):
        self.environment = environment

    def capture_account_context(self):
        return {
            "account_environment": self.environment,
            "account_context_fingerprint": "a" * 64,
            "trade_allowed": True,
        }

    def close(self):
        return None


def _authority(tmp_path):
    service = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    service.set_mode(
        "autonomous_live",
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="mode-nonce",
        now=NOW,
    )
    mandate = service.grant_mandate(
        **_mandate_command().__dict__,
        account_fingerprint="a" * 64,
        account_is_demo=True,
        nonce="mandate-nonce",
        idempotency_key="mandate-key",
        operator_grant=True,
        now=NOW,
    )
    return service, mandate


def _mandate_command(now=NOW):
    return MandateGrantCommand(
        mandate_id="mandate-runtime-1",
        mandate_version=1,
        permitted_symbols=("BTCUSD",),
        permitted_broker_symbols=("BTCUSDm",),
        permitted_order_families=("MARKET", "PENDING"),
        permitted_management_actions=("OBSERVE", "NO_ACTION"),
        maximum_volume="1",
        maximum_risk_per_trade="100",
        maximum_concurrent_positions=2,
        maximum_trades_per_day=3,
        maximum_loss_per_day="500",
        active_from=(now - timedelta(minutes=1)).isoformat(),
        active_until=(now + timedelta(hours=1)).isoformat(),
        expires_at=(now + timedelta(hours=2)).isoformat(),
        kill_switch_engaged=False,
    )


def _candidate():
    return SimpleNamespace(
        candidate_reference="candidate-runtime-1",
        decision_idempotency_key="b" * 64,
        symbol_reference="BTCUSD",
        broker_symbol_reference="BTCUSDm",
        order_type="BUY",
        side="BUY",
        entry_price="",
        trigger_price="",
        limit_price="",
        stop_loss="61991",
        proposed_volume="0.1",
    )
