from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Config
from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import (
    MandateGrantCommand,
    TradingAuthorityOperatorService,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityError,
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.reasoning.strategy_evidence import (
    ConversationalStrategyRequest,
    IndicatorSpec,
    StrategyIdentity,
    StrategyRule,
    strategy_identity,
)


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
DASHBOARD = Path("src/ui/tab_dashboard.py")
CHATBOT = Path("src/ui/tab_chatbot.py")


class AccountAdapter:
    def __init__(self, fingerprint="a" * 64, environment="DEMO"):
        self.fingerprint = fingerprint
        self.environment = environment

    def capture_account_context(self):
        return {
            "account_environment": self.environment,
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

    setup = _build_setup(
        service,
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
    assert setup.suggested_maximum_volume == "0.01"
    assert setup.suggested_maximum_risk_per_trade == "1"
    assert setup.suggested_maximum_concurrent_positions == 1
    assert setup.suggested_maximum_trades_per_day == 1
    assert setup.suggested_maximum_loss_per_day == "1"
    assert setup.strategy_direction == "BUY"
    assert setup.strategy_action == "OPEN_POSITION"
    assert setup.protected_strategy == _strategy().as_dict()
    assert setup.unresolved_fields == ()
    assert dict(setup.field_sources)["maximum_volume"] == "BROKER_METADATA"
    assert dict(setup.field_sources)["maximum_risk_per_trade"] == "CONFIGURED_POLICY"
    assert service.authority.store.latest_mandates() == ()


def test_volume_suggestion_uses_current_broker_minimum(tmp_path):
    service = _service(
        tmp_path,
        market_provider=MarketProvider(volume_min="0.05", volume_max="10", volume_step="0.05"),
    )
    setup = _build_setup(service, _strategy(), order_family="MARKET", now=NOW)

    assert setup.suggested_maximum_volume == "0.05"


def test_configured_demo_policy_values_are_projected(monkeypatch, tmp_path):
    monkeypatch.setattr(
        Config, "TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_RISK_PER_TRADE", "2.5"
    )
    monkeypatch.setattr(
        Config, "TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_CONCURRENT_POSITIONS", 2
    )
    monkeypatch.setattr(
        Config, "TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_TRADES_PER_DAY", 3
    )
    monkeypatch.setattr(
        Config, "TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_LOSS_PER_DAY", "7.5"
    )

    setup = _build_setup(
        _service(tmp_path), _strategy(), order_family="MARKET", now=NOW
    )

    assert setup.suggested_maximum_risk_per_trade == "2.5"
    assert setup.suggested_maximum_concurrent_positions == 2
    assert setup.suggested_maximum_trades_per_day == 3
    assert setup.suggested_maximum_loss_per_day == "7.5"


@pytest.mark.parametrize(
    ("setting", "invalid"),
    (
        ("TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_RISK_PER_TRADE", ""),
        ("TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_CONCURRENT_POSITIONS", 0),
        ("TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_TRADES_PER_DAY", 0),
        ("TRADING_AUTONOMOUS_DEMO_MANDATE_MAX_LOSS_PER_DAY", ""),
    ),
)
def test_demo_policy_configuration_is_required_and_never_uses_llm_values(
    monkeypatch, tmp_path, setting, invalid
):
    monkeypatch.setattr(Config, setting, invalid)
    strategy = _strategy()

    with pytest.raises(
        ValueError, match="DEMO_MANDATE_POLICY_CONFIGURATION_REQUIRED"
    ):
        _build_setup(
            _service(tmp_path), strategy, order_family="MARKET", now=NOW
        )


@pytest.mark.parametrize("environment", ("REAL", "UNKNOWN"))
def test_non_demo_environment_never_inherits_demo_policy(tmp_path, environment):
    service = _service(
        tmp_path, account_adapter=AccountAdapter(environment=environment)
    )

    with pytest.raises(RuntimeError, match="REAL_ACCOUNT_AUTHORITY_FORBIDDEN"):
        _build_setup(service, _strategy(), order_family="MARKET", now=NOW)


def test_user_edits_build_typed_command_and_revalidate_broker_volume(tmp_path):
    service = _service(tmp_path)
    setup = _build_setup(
        service, _strategy(), order_family="MARKET", duration_minutes=30, now=NOW
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
    assert command.maximum_risk_per_trade == "10"
    assert command.maximum_concurrent_positions == 1
    assert command.maximum_trades_per_day == 1
    assert command.maximum_loss_per_day == "20"
    assert command.kill_switch_engaged is True
    assert command.strategy_id == setup.strategy_id
    assert command.protected_strategy == setup.protected_strategy
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
    setup = _build_setup(
        service, _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
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
    first = _build_setup(
        service, _strategy(), order_family="MARKET", duration_minutes=60
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
    stored, reloaded = service.authority.load_supervisor_strategy(
        command.mandate_id,
        account_fingerprint="a" * 64,
        account_is_demo=True,
    )
    assert stored.strategy_direction == "BUY"
    assert reloaded == _strategy()

    second = _build_setup(
        service, _strategy(), order_family="MARKET", duration_minutes=60
    )
    assert second.mandate_id == first.mandate_id
    assert second.mandate_version == 2


def test_setup_fails_closed_without_authoritative_volume_metadata(tmp_path):
    service = _service(tmp_path, market_provider=MarketProvider(volume_step=None))
    with pytest.raises(ValueError, match="BROKER_VOLUME_STEP_INVALID"):
        _build_setup(
            service, _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
        )


def test_setup_fails_closed_when_current_account_does_not_match_mode(tmp_path):
    service = _service(tmp_path, account_adapter=AccountAdapter("b" * 64))
    with pytest.raises(ValueError, match="MANDATE_ACCOUNT_MISMATCH"):
        _build_setup(
            service, _strategy(), order_family="MARKET", duration_minutes=60, now=NOW
        )


def test_streamlit_review_uses_structured_controls_and_clear_money_units():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    chatbot = CHATBOT.read_text(encoding="utf-8")

    assert "Autonomous Strategy & Mandate Setup" in dashboard
    assert "Max risk / trade (account currency)" in dashboard
    assert "Max loss / day (account currency)" in dashboard
    assert '"mandate_max_risk": setup.suggested_maximum_risk_per_trade' in dashboard
    assert "disabled=command is None or not grant_mandate" in dashboard
    assert "Mandate duration" in dashboard
    assert "Active from (UTC ISO-8601)" not in dashboard
    assert "Confirm Standing Mandate" in dashboard
    assert '"mandate_management_actions": list(setup.suggested_management_actions)' in dashboard
    assert "st.session_state.setdefault" in dashboard
    assert 'order_family="MARKET" if request.trade_action == "OPEN_POSITION" else ""' in chatbot


def test_human_confirmed_mode_remains_per_trade_and_has_no_mandate_controls():
    from src.ui.tab_dashboard import _mode_ui_capabilities

    human = _mode_ui_capabilities("human_confirmed_live")
    autonomous = _mode_ui_capabilities("autonomous_live")
    assert human["human_confirmation"] is True
    assert human["mandate_controls"] is False
    assert autonomous["human_confirmation"] is False
    assert autonomous["mandate_controls"] is True


@pytest.mark.parametrize("stage", ("account", "market"))
@pytest.mark.parametrize("kind,category", (("unreachable", "NETWORK_UNREACHABLE"), ("timeout", "TIMEOUT"), ("refused", "CONNECTION_REFUSED"), ("dns", "DNS_FAILURE"), ("http", "HTTP_ERROR")))
def test_setup_connection_failure_is_categorized_redacted_and_recovers(tmp_path, monkeypatch, stage, kind, category):
    import errno
    import socket
    from urllib.error import HTTPError, URLError
    from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider
    from src.services.trading.execution.mt5_live_adapter_pre_submit.authority_runtime import MandateSetupUnavailable

    errors = {
        "unreachable": URLError(OSError(errno.ENETUNREACH, "private-token")),
        "timeout": URLError(TimeoutError("private-token")),
        "refused": URLError(ConnectionRefusedError(errno.ECONNREFUSED, "private-token")),
        "dns": URLError(socket.gaierror(-2, "private-token")),
        "http": HTTPError("http://user:private-token@host", 401, "private-token", {}, None),
    }
    provider = MT5BridgeMarketDataProvider()
    adapter = AccountAdapter()
    service = _service(tmp_path, market_provider=provider, account_adapter=adapter)
    baseline = service.authority.store.path.read_bytes()

    def fail(*args, **kwargs):
        raise errors[kind]

    monkeypatch.setattr(provider, "_get_json", lambda *a, **k: {"volume_min": 0.01, "volume_max": 200, "volume_step": 0.01})
    if stage == "account":
        monkeypatch.setattr(adapter, "capture_account_context", fail)
    else:
        monkeypatch.setattr(provider, "_get_json", fail)
    with pytest.raises(MandateSetupUnavailable) as error:
        _build_setup(service, _strategy(), order_family="MARKET", now=NOW)
    assert str(error.value) == ("ACCOUNT_CONTEXT" if stage == "account" else "BROKER_MARKET_EVIDENCE") + ": " + category
    assert "private-token" not in str(error.value)
    assert service.authority.store.path.read_bytes() == baseline
    monkeypatch.setattr(adapter, "capture_account_context", AccountAdapter().capture_account_context)
    monkeypatch.setattr(provider, "_get_json", lambda *a, **k: {"volume_min": 0.01, "volume_max": 200, "volume_step": 0.01})
    assert _build_setup(service, _strategy(), order_family="MARKET", now=NOW).volume_min == "0.01"
    assert service.authority.store.path.read_bytes() == baseline


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


def _build_setup(service, strategy, **kwargs):
    return service.build_mandate_setup(
        strategy,
        strategy_direction="BUY",
        strategy_action="OPEN_POSITION",
        **kwargs,
    )


def _strategy():
    provisional = ConversationalStrategyRequest(
        canonical_symbol="XAUUSD",
        requested_mode="autonomous_live",
        confirmation_policy="STANDING_MANDATE",
        account_scope="DEMO",
        indicators=(IndicatorSpec("RSI", "M1", (("period", 14.0),), "rsi_14_m1"),),
        entry_rules=(StrategyRule("GREATER_THAN", "rsi_14_m1", constants=(10.0,)),),
        exit_rules=(),
        semantic_unresolved_fields=(),
        strategy_description="BUY XAUUSD when RSI14 M1 is above 10",
        risk_policy_reference="CONFIGURED_RISK_POLICY",
        request_id="conversation_trade_prefill",
        identity=StrategyIdentity("", "reasoning-strategy/v2", ""),
    )
    return ConversationalStrategyRequest(
        **{**provisional.__dict__, "identity": strategy_identity(provisional)}
    )
