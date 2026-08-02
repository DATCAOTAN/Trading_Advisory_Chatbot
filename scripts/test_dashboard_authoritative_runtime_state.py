from pathlib import Path
from types import SimpleNamespace

from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    TradingAuthorityOperatorService,
)
from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.ui.tab_dashboard import _market_runtime_projection


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
