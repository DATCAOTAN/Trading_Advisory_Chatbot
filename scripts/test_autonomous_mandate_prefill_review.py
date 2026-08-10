from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    MandateGrantCommand,
    TradingAuthorityOperatorService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
DASHBOARD = Path("src/ui/tab_dashboard.py")
CHATBOT = Path("src/ui/tab_chatbot.py")


class AccountAdapter:
    def __init__(self, fingerprint="a" * 64):
        self.fingerprint = fingerprint

    def capture_account_context(self):
        return {
            "account_environment": "DEMO",
            "account_context_fingerprint": self.fingerprint,
            "trade_allowed": True,
        }

    def close(self):
        return None


class MarketProvider:
    def __init__(self, *, volume_min=0.01, volume_max=200, volume_step=0.01):
        self.tick = SimpleNamespace(
            volume_min=volume_min,
            volume_max=volume_max,
            volume_step=volume_step,
        )

    def get_latest_tick(self, symbol):
        assert symbol == "XAUUSD"
        return self.tick

    def close(self):
        return None


def test_completed_strategy_projects_authoritative_mandate_setup(tmp_path):
    service = _service(tmp_path)

    setup = service.build_mandate_setup(
        _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
    )

    assert setup.operating_mode == "autonomous_live"
    assert setup.account_environment == "DEMO"
    assert setup.canonical_symbol == "XAUUSD"
    assert setup.broker_symbol == "XAUUSDm"
    assert setup.permitted_order_families == ("MARKET",)
    assert setup.suggested_management_actions == ("OBSERVE", "NO_ACTION")
    assert (setup.volume_min, setup.volume_max, setup.volume_step) == (
        "0.01",
        "200",
        "0.01",
    )
    assert setup.active_from == NOW.isoformat()
    assert setup.active_until == setup.expires_at
    assert setup.active_until == "2026-08-10T09:00:00+00:00"
    assert "maximum_risk_per_trade" in setup.unresolved_fields
    assert "maximum_loss_per_day" in setup.unresolved_fields
    assert service.authority.store.latest_mandates() == ()


def test_user_edits_build_typed_command_and_revalidate_broker_volume(tmp_path):
    service = _service(tmp_path)
    setup = service.build_mandate_setup(
        _strategy(), order_family="MARKET", duration_minutes=30, now=NOW
    )

    command = service.command_from_mandate_setup(
        setup,
        maximum_volume="0.02",
        maximum_risk_per_trade="10",
        maximum_concurrent_positions=1,
        maximum_trades_per_day=1,
        maximum_loss_per_day="20",
        permitted_management_actions=("OBSERVE",),
        kill_switch_engaged=True,
    )

    assert isinstance(command, MandateGrantCommand)
    assert command.permitted_symbols == ("XAUUSD",)
    assert command.permitted_broker_symbols == ("XAUUSDm",)
    assert command.maximum_volume == "0.02"
    assert command.kill_switch_engaged is True
    with pytest.raises(
        ValueError, match="MANDATE_MAXIMUM_VOLUME_OUTSIDE_BROKER_CONSTRAINTS"
    ):
        service.command_from_mandate_setup(
            setup,
            maximum_volume="0.015",
            maximum_risk_per_trade="10",
            maximum_concurrent_positions=1,
            maximum_trades_per_day=1,
            maximum_loss_per_day="20",
            permitted_management_actions=("OBSERVE",),
            kill_switch_engaged=True,
        )


def test_missing_policy_limits_remain_required_and_do_not_grant(tmp_path):
    service = _service(tmp_path)
    setup = service.build_mandate_setup(
        _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
    )

    with pytest.raises(ValueError, match="MANDATE_MAXIMUM_RISK_INVALID"):
        service.command_from_mandate_setup(
            setup,
            maximum_volume="0.01",
            maximum_risk_per_trade="",
            maximum_concurrent_positions=1,
            maximum_trades_per_day=1,
            maximum_loss_per_day="",
            permitted_management_actions=setup.suggested_management_actions,
            kill_switch_engaged=True,
        )
    assert service.authority.store.latest_mandates() == ()


def test_mandate_id_is_stable_and_version_uses_authority_store(tmp_path):
    service = _service(tmp_path)
    first = service.build_mandate_setup(
        _strategy(), order_family="MARKET", duration_minutes=60
    )
    command = service.command_from_mandate_setup(
        first,
        maximum_volume="0.01",
        maximum_risk_per_trade="10",
        maximum_concurrent_positions=1,
        maximum_trades_per_day=1,
        maximum_loss_per_day="20",
        permitted_management_actions=("OBSERVE",),
        kill_switch_engaged=True,
    )
    with pytest.raises(TradingAuthorityError, match="MANDATE_GRANT_INVALID"):
        service.grant_mandate(command, operator_grant=False)
    service.grant_mandate(command, operator_grant=True)

    second = service.build_mandate_setup(
        _strategy(), order_family="MARKET", duration_minutes=60
    )
    assert second.mandate_id == first.mandate_id
    assert second.mandate_version == 2


def test_setup_fails_closed_without_authoritative_volume_metadata(tmp_path):
    service = _service(tmp_path, market_provider=MarketProvider(volume_step=None))
    with pytest.raises(ValueError, match="BROKER_VOLUME_STEP_INVALID"):
        service.build_mandate_setup(
            _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
        )


def test_setup_fails_closed_when_current_account_does_not_match_mode(tmp_path):
    service = _service(tmp_path, account_adapter=AccountAdapter("b" * 64))
    with pytest.raises(ValueError, match="MANDATE_ACCOUNT_MISMATCH"):
        service.build_mandate_setup(
            _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
        )


def test_streamlit_review_uses_structured_controls_and_clear_money_units():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    chatbot = CHATBOT.read_text(encoding="utf-8")

    assert "Autonomous Strategy & Mandate Setup" in dashboard
    assert "Max risk / trade (account currency)" in dashboard
    assert "Max loss / day (account currency)" in dashboard
    assert "REQUIRES_USER_CONFIRMATION" in dashboard
    assert "Mandate duration" in dashboard
    assert "Active from (UTC ISO-8601)" not in dashboard
    assert "Confirm Standing Mandate" in dashboard
    assert "default=setup.suggested_management_actions" in dashboard
    assert 'order_family="MARKET" if request.trade_action == "OPEN_POSITION" else ""' in chatbot


def test_human_confirmed_mode_remains_per_trade_and_has_no_mandate_controls():
    from src.ui.tab_dashboard import _mode_ui_capabilities

    human = _mode_ui_capabilities("human_confirmed_live")
    autonomous = _mode_ui_capabilities("autonomous_live")
    assert human["human_confirmation"] is True
    assert human["mandate_controls"] is False
    assert autonomous["human_confirmation"] is False
    assert autonomous["mandate_controls"] is True


def _service(tmp_path, *, market_provider=None, account_adapter=None):
    authority = TradingAuthorityService(TradingAuthorityStore(tmp_path / "authority.jsonl"))
    authority.set_mode(
        "autonomous_live",
        account_fingerprint="a" * 64,
        account_is_demo=True,
        operator_grant=True,
        nonce="mandate-prefill-mode",
        now=NOW,
    )
    return TradingAuthorityOperatorService(
        authority_service=authority,
        account_adapter=account_adapter or AccountAdapter(),
        lifecycle_supervisor=SimpleNamespace(),
        pre_submit_store=SimpleNamespace(),
        market_provider=market_provider or MarketProvider(),
    )


def _strategy():
    return SimpleNamespace(
        canonical_symbol="XAUUSD",
        requested_mode="autonomous_live",
        semantic_unresolved_fields=(),
        strategy_description="BUY XAUUSD when RSI14 M1 is above 10",
        identity=SimpleNamespace(
            strategy_id="strategy_prefill_xauusd",
            strategy_version="reasoning-strategy/v2",
        ),
    )
