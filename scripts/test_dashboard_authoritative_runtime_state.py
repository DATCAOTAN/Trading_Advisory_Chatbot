from pathlib import Path
from types import SimpleNamespace

from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    TradingAuthorityOperatorService,
)
from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.ui.tab_dashboard import (
    _candidate_runtime_blockers,
    _market_runtime_projection,
    _mode_ui_capabilities,
)


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
