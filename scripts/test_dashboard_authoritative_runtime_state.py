from datetime import datetime
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    TradingAuthorityOperatorService,
)
from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.ui.tab_dashboard import (
    _active_mandate_for_setup,
    _candidate_runtime_blockers,
    _latest_monitor_row,
    _market_runtime_projection,
    _mode_ui_capabilities,
    _sync_mandate_form_state,
)


def _mandate(**overrides):
    value = {
        "mandate_id": "mandate-current",
        "mandate_version": 2,
        "strategy_id": "strategy-current",
        "operating_mode": "autonomous_live",
        "expires_at": "2026-08-02T11:00:00+00:00",
        "integrity_valid": True,
        "revoked": False,
        "permitted_management_actions": ["OBSERVE", "NO_ACTION"],
        "maximum_volume": "0.01",
        "maximum_risk_per_trade": "100",
        "maximum_concurrent_positions": 3,
        "maximum_trades_per_day": 3,
        "maximum_loss_per_day": "500",
        "kill_switch_engaged": False,
    }
    value.update(overrides)
    return value


def _market_result(*, symbol="BTCUSD", broker_symbol="BTCUSDm", issue=None):
    tick = SimpleNamespace(
        timestamp="2026-08-02T10:00:00+00:00",
        digits=2,
        point=0.01,
        tick_size=0.01,
        minimum_distance_points=10,
        volume_min=0.01,
        volume_max=10.0,
        volume_step=0.01,
        tick_value=1.0,
        contract_size=1.0,
    )
    quality_issue = (
        [SimpleNamespace(code=issue, timeframe="M1")] if issue else []
    )
    return SimpleNamespace(
        bundle=SimpleNamespace(
            symbol=symbol,
            broker_symbol=broker_symbol,
            tick=tick,
            provider_health=SimpleNamespace(status="OK"),
        ),
        quality_report=SimpleNamespace(
            status="STALE" if issue else "COMPLETE",
            issues=quality_issue,
            latest_timestamp_by_timeframe={
                "M1": "2026-08-02T09:59:00+00:00",
                "H1": "2026-08-02T09:00:00+00:00",
                "H4": "2026-08-02T08:00:00+00:00",
            },
        ),
    )


def test_btc_selection_resolves_existing_broker_symbol_and_profile():
    state = _market_runtime_projection(
        _market_result(), "BTCUSD", operator_timeframe_profile("BTCUSD")
    )

    assert state["canonical_symbol"] == "BTCUSD"
    assert state["broker_symbol"] == "BTCUSDm"
    assert state["timeframes"] == ("M1", "H1", "H4")
    assert state["quality_status"] == "COMPLETE"
    assert state["symbol_capability"] == "COMPLETE"
    assert state["blockers"] == ()


def test_xau_default_profile_is_unchanged_and_not_session_owned():
    assert operator_timeframe_profile("XAUUSD") != ("M1", "H1", "H4")
    assert "session_state" not in operator_timeframe_profile.__code__.co_names


def test_dashboard_reload_uses_current_integrity_valid_persisted_mandate():
    setup = SimpleNamespace(
        mandate_id="mandate-current",
        strategy_id="strategy-current",
        operating_mode="autonomous_live",
    )
    mandate = _mandate()

    assert _active_mandate_for_setup(
        setup,
        [mandate],
        preferred_mandate_id="mandate-current",
        now=datetime.fromisoformat("2026-08-02T10:00:00+00:00"),
    ) == mandate


def test_dashboard_does_not_restore_expired_revoked_or_wrong_strategy_mandate():
    setup = SimpleNamespace(
        mandate_id="mandate-current",
        strategy_id="strategy-current",
        operating_mode="autonomous_live",
    )
    now = datetime.fromisoformat("2026-08-02T10:00:00+00:00")

    for mandate in (
        _mandate(expires_at="2026-08-02T09:59:00+00:00"),
        _mandate(revoked=True),
        _mandate(strategy_id="strategy-other"),
        _mandate(integrity_valid=False),
    ):
        assert _active_mandate_for_setup(setup, [mandate], now=now) is None


def test_persisted_mandate_values_replace_fresh_session_defaults(monkeypatch):
    session_state = {}
    monkeypatch.setattr(
        "src.ui.tab_dashboard.st", SimpleNamespace(session_state=session_state)
    )

    _sync_mandate_form_state("trade_", _mandate())

    assert session_state["trade_mandate_management_actions"] == [
        "OBSERVE",
        "NO_ACTION",
    ]
    assert session_state["trade_mandate_max_volume"] == "0.01"
    assert session_state["trade_mandate_max_risk"] == "100"
    assert session_state["trade_mandate_max_positions"] == 3
    assert session_state["trade_mandate_max_trades"] == 3
    assert session_state["trade_mandate_max_loss"] == "500"
    assert session_state["trade_mandate_kill_switch"] is False


def test_symbol_mismatch_is_visible_and_never_falls_back():
    state = _market_runtime_projection(
        _market_result(symbol="XAUUSD", broker_symbol="XAUUSDm"),
        "BTCUSD",
        ("M1", "H1", "H4"),
    )

    assert state["canonical_symbol"] == "XAUUSD"
    assert "SYMBOL_PROFILE_MISMATCH" in state["blockers"]


def test_market_freshness_blocker_and_completed_bars_are_projected():
    state = _market_runtime_projection(
        _market_result(issue="STALE_LATEST_BAR"),
        "BTCUSD",
        ("M1", "H1", "H4"),
    )

    assert state["quality_status"] == "STALE"
    assert state["bar_timestamps"]["M1"] == "2026-08-02T09:59:00+00:00"
    assert "STALE_LATEST_BAR:M1" in state["blockers"]


def test_authority_projection_contains_permissions_and_redaction(monkeypatch):
    monkeypatch.setattr(
        "src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime.Config.TRADING_MT5_LIVE_ADAPTER_ENABLED",
        False,
    )
    lifecycle = SimpleNamespace(
        status=lambda: SimpleNamespace(
            to_safe_dict=lambda: {
                "supervisor_status": "HEALTHY",
                "bridge_available": True,
                "account_context_match": True,
                "discrepancy_count": 0,
            }
        ),
        execution_journal=SimpleNamespace(
            execution_records=lambda: [
                {"state": "RESULT_CONFIRMED"},
                {"state": "RESULT_UNKNOWN"},
            ]
        ),
    )
    service = TradingAuthorityOperatorService(
        authority_service=SimpleNamespace(
            store=SimpleNamespace(latest_mode=lambda: None, latest_mandates=lambda: [])
        ),
        account_adapter=SimpleNamespace(
            capture_account_context=lambda: {
                "account_environment": "DEMO",
                "account_context_fingerprint": "protected-value",
                "trade_allowed": True,
            }
        ),
        lifecycle_supervisor=lifecycle,
        pre_submit_store=SimpleNamespace(
            summarize=lambda: SimpleNamespace(
                total_records=0,
                total_valid=0,
                total_blocked=0,
                latest_status="",
                warnings=[],
            )
        ),
    )

    status = service.status()

    assert status["account_environment"] == "DEMO"
    assert status["unresolved_execution_count"] == 1
    assert status["permission_state"]["live_adapter_enabled"] is False
    assert status["metadata_redacted"] is True
    assert "account_context_fingerprint" not in status


def test_authority_pre_submit_evidence_uses_current_demo_account_and_lifecycle():
    lifecycle_status = SimpleNamespace(
        last_successful_cycle="2026-08-02T10:00:00+00:00",
        terminal_trade_allowed=True,
        account_trade_allowed=True,
    )
    account = {
        "account_environment": "DEMO",
        "account_context_fingerprint": "a" * 64,
        "account_id_hash": "b" * 64,
    }
    service = TradingAuthorityOperatorService(
        authority_service=SimpleNamespace(),
        account_adapter=SimpleNamespace(capture_account_context=lambda: account),
        lifecycle_supervisor=SimpleNamespace(run_once=lambda: lifecycle_status),
        pre_submit_store=SimpleNamespace(),
    )
    candidate = SimpleNamespace(
        symbol_reference="BTCUSD", broker_symbol_reference="BTCUSDm"
    )

    evidence = service.pre_submit_evidence(candidate)

    assert evidence["account_is_demo"] is True
    assert evidence["expected_account_fingerprint"] == "a" * 64
    assert evidence["terminal_capability"].integrity_valid()
    assert evidence["terminal_capability"].symbol == "BTCUSD"
    assert evidence["terminal_capability"].broker_symbol == "BTCUSDm"
    assert "status" not in account


def test_dashboard_renders_authority_and_selected_symbol_without_mutation_calls():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")

    for label in (
        'metric("Account"',
        'metric("Mode"',
        'metric("Lifecycle"',
        'metric("Discrepancies"',
        'metric("Unresolved"',
        'metric("Broker"',
        'metric("Profile"',
    ):
        assert label in source
    assert "get_live_price(selected_symbol)" in source
    assert "status(refresh_runtime=True)" in source
    assert ".order_send(" not in source
    assert "controlled-submit" not in source


def test_dashboard_isolates_mode_specific_authority_controls():
    advisory = _mode_ui_capabilities("advisory_only")
    human = _mode_ui_capabilities("human_confirmed_live")
    autonomous = _mode_ui_capabilities("autonomous_live")

    assert advisory == {
        "human_confirmation": False,
        "mandate_controls": False,
    }
    assert human["human_confirmation"] is True
    assert human["mandate_controls"] is False
    assert autonomous["human_confirmation"] is False
    assert autonomous["mandate_controls"] is True


def test_mode_form_submit_is_not_deadlocked_by_form_local_selection():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")

    assert "form_submit_button(mode_action)" in source
    assert "form_submit_button(mode_action, disabled=" not in source


def test_candidate_generation_blockers_follow_authoritative_runtime_status():
    status = {
        "account_environment": "DEMO",
        "mode_integrity_valid": True,
        "unresolved_execution_count": 0,
        "pre_submit": {"warnings": []},
        "lifecycle": {
            "supervisor_status": "CYCLE_SKIPPED",
            "health_reason": "OVERLAPPING_CYCLE_PREVENTED",
            "bridge_available": False,
            "account_context_match": False,
            "discrepancy_count": 0,
        },
    }

    assert _candidate_runtime_blockers(status) == (
        "OVERLAPPING_CYCLE_PREVENTED",
        "BRIDGE_UNAVAILABLE",
        "ACCOUNT_CONTEXT_MISMATCH",
    )


def test_generate_control_is_disabled_until_runtime_blockers_clear():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")

    assert "or bool(runtime_blockers)" in source
    assert "Generate Candidate is unavailable until Refresh Runtime Health" in source


def test_dashboard_reads_latest_authoritative_strategy_evaluation(monkeypatch):
    rows = [
        {
            "symbol": "XAUUSD",
            "timeframes": ["M1"],
            "phase": "COMPLETED",
            "strategy_evaluation": {"rearm_state": "WAITING_FOR_REARM"},
        }
    ]
    monkeypatch.setattr(
        "src.ui.tab_dashboard.AutonomousCandidateMonitorJournal",
        lambda _path: SimpleNamespace(records=lambda: rows),
    )

    row = _latest_monitor_row("XAUUSD", ("M1",), "strategy-current")

    assert row is None

    rows[0]["strategy_evaluation"]["strategy_reference"] = "strategy-current"
    row = _latest_monitor_row("XAUUSD", ("M1",), "strategy-current")
    assert row["strategy_evaluation"]["rearm_state"] == "WAITING_FOR_REARM"


def test_dashboard_only_presents_monitor_strategy_evaluation():
    source = Path("src/ui/tab_dashboard.py").read_text(encoding="utf-8")

    assert 'st.markdown("**Autonomous Runtime**")' in source
    assert "previous_indicator_value" in source
    assert "current_indicator_value" in source
    assert "rearm_state" in source
    assert "strategy_monitor_projection" not in source
    assert "_evaluate_rule" not in source


class _SupervisorRerun(BaseException):
    pass


def _supervisor_controls(monkeypatch, *, running=False, failure=False):
    from src.ui import tab_dashboard

    ui = MagicMock()
    ui.session_state = {}
    ui.columns.side_effect = lambda count: [ui] * count
    ui.form_submit_button.return_value = False
    ui.checkbox.return_value = False
    ui.selectbox.side_effect = lambda label, *_args, **_kwargs: (
        "mandate-current" if label == "Supervisor mandate"
        else 60 if label == "Mandate duration" else None
    )
    ui.rerun.side_effect = _SupervisorRerun
    clicked = set()
    disabled = {}

    def button(label, **kwargs):
        disabled[label] = kwargs.get("disabled", False)
        if label in clicked and not disabled[label]:
            clicked.remove(label)
            return True
        return False

    ui.button.side_effect = button
    state = {"running": running, "mandate_id": "mandate-current"}
    process = SimpleNamespace(status=MagicMock(side_effect=lambda scope: dict(state)))

    def transition(next_running):
        if failure:
            raise OSError("process transition failed")
        state["running"] = next_running
        return dict(state)

    process.start = MagicMock(side_effect=lambda **kwargs: transition(True))
    process.stop = MagicMock(side_effect=lambda scope: transition(False))
    service = MagicMock()
    service.status.return_value = {
        "account_environment": "DEMO", "mode": "autonomous_live",
        "metadata_redacted": True, "mode_integrity_valid": True,
        "unresolved_execution_count": 0,
        "execution_state_counts": {}, "reconciliation_state_counts": {},
        "mandates": [_mandate()], "permission_state": defaultdict(bool),
        "pre_submit": {"warnings": [], "latest_status": ""},
        "lifecycle": {
            "supervisor_status": "HEALTHY", "account_context_match": True,
            "bridge_available": True, "discrepancy_count": 0,
            "terminal_trade_allowed": True, "account_trade_allowed": True,
            "active_position_count": 0, "trades_today": 0,
        },
    }
    # Existing persisted selection still renders if setup cannot be rebuilt.
    service.build_mandate_setup.side_effect = ValueError("MANDATE_SETUP_UNAVAILABLE")
    monkeypatch.setattr(tab_dashboard, "st", ui)
    monkeypatch.setattr(tab_dashboard, "_trading_authority_service", lambda: service)
    monkeypatch.setattr(tab_dashboard, "_autonomous_monitor_process", lambda: process)
    monkeypatch.setattr(
        "subprocess.Popen", lambda *_args, **_kwargs: pytest.fail("real process forbidden")
    )

    def render():
        return tab_dashboard._render_trading_runtime_controls(
            "XAUUSD", ("M1",), None, requested_mode="autonomous_live",
            key_prefix="scope-a_", strategy=SimpleNamespace(
                trading_scope="scope-a", identity=SimpleNamespace(strategy_id="strategy-current")
            ),
        )

    return ui, process, clicked, disabled, render


@pytest.mark.parametrize("action", ("start", "stop"))
@pytest.mark.parametrize("failure", (False, True))
def test_supervisor_transition_reruns_once_and_preserves_scope(monkeypatch, action, failure):
    ui, process, clicked, disabled, render = _supervisor_controls(
        monkeypatch, running=action == "stop", failure=failure
    )
    clicked.add(f"{action.title()} Supervisor")
    if failure:
        render()
        ui.rerun.assert_not_called()
        assert any(
            call.args == (f"Supervisor {action} failed: OSError",)
            for call in ui.warning.call_args_list
        )
        ui.success.assert_not_called()
    else:
        with pytest.raises(_SupervisorRerun):
            render()
        ui.rerun.assert_called_once_with()

    render()  # A rerun/refresh is not a second operator click.
    if action == "start":
        process.start.assert_called_once_with(
            symbol="XAUUSD", timeframes=("M1",),
            mandate_id="mandate-current", trading_scope="scope-a",
        )
        process.stop.assert_not_called()
    else:
        process.stop.assert_called_once_with("scope-a")
        process.start.assert_not_called()
    expected_running = (action == "stop") if failure else (action == "start")
    assert disabled["Start Supervisor"] is expected_running
    assert disabled["Stop Supervisor"] is not expected_running
    assert all(call.args == ("scope-a",) for call in process.status.call_args_list)


@pytest.mark.parametrize("running", (False, True))
def test_supervisor_refresh_only_reads_process_status(monkeypatch, running):
    ui, process, _clicked, disabled, render = _supervisor_controls(
        monkeypatch, running=running
    )
    render()
    render()
    assert disabled["Start Supervisor"] is running
    assert disabled["Stop Supervisor"] is not running
    process.start.assert_not_called()
    process.stop.assert_not_called()
    ui.rerun.assert_not_called()


@pytest.mark.parametrize("state", ("STOPPED", "RUNNING", "EXITED", "FAILED", "UNKNOWN"))
def test_supervisor_process_state_is_rendered_independently(monkeypatch, state):
    ui, process, _clicked, _disabled, render = _supervisor_controls(monkeypatch, running=False)
    process.status.side_effect = lambda scope: {
        "running": state == "RUNNING", "mandate_id": "mandate-current",
        "process_state": state, "exit_code": 1 if state == "FAILED" else None,
    }
    render()
    captions = "\n".join(str(call.args[0]) for call in ui.caption.call_args_list)
    assert f"SUPERVISOR_{state}" in captions
    assert "monitor_evidence=UNAVAILABLE" in captions
    process.start.assert_not_called()
    process.stop.assert_not_called()


def test_mandate_setup_warning_does_not_expose_raw_network_exception(monkeypatch):
    from urllib.error import URLError
    from src.ui import tab_dashboard

    ui, _process, _clicked, _disabled, render = _supervisor_controls(monkeypatch, running=False)
    tab_dashboard._trading_authority_service().build_mandate_setup.side_effect = URLError("http://user:secret-token@private-host")
    render()
    warnings = "\n".join(str(call.args[0]) for call in ui.warning.call_args_list)
    assert "Standing Mandate setup unavailable: URLError" in warnings
    assert "secret-token" not in warnings and "private-host" not in warnings
