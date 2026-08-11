from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.test_autonomous_mandate_controlled_execution import _request
from scripts.test_autonomous_execution_policy_gate import policy_inputs, run as run_policy
from scripts.test_mt5_controlled_execution_integration import ACCOUNT_A, AUTH_TOKEN
from src.config import Config
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import (
    MT5LiveAdapterPreSubmitConfig,
    execution_permission_state,
    mandate_permissions_execution_ready,
)


class AdmissionOnlyClient:
    def __init__(self):
        self.submissions = 0

    def account_context(self):
        return {
            "status": "OK",
            "account_context_fingerprint": ACCOUNT_A,
            "account_id_hash": "c" * 64,
            "server_redacted": "de***mo",
            "currency": "USD",
            "trade_mode": 0,
            "account_environment": "DEMO",
            "trade_allowed": True,
            "redacted": True,
        }

    def submit_controlled(self, _payload, auth_token):
        self.submissions += 1
        assert auth_token == AUTH_TOKEN
        return {
            "status": "BLOCKED",
            "reason": "TEST_BROKER_SEAM_REPLACED",
            "idempotency_status": "NOT_RESERVED",
            "order_sent": False,
        }


def _ready_config() -> MT5LiveAdapterPreSubmitConfig:
    return MT5LiveAdapterPreSubmitConfig(
        live_adapter_enabled=True,
        live_adapter_hard_block=False,
        allow_live_submission=True,
        allow_order_send=True,
        controlled_execution_enabled=True,
        autonomous_execution_enabled=True,
        kill_switch_engaged=False,
        execution_auth_token=AUTH_TOKEN,
    )


def _enable_global_policy(monkeypatch) -> None:
    monkeypatch.setattr(Config, "TRADING_MT5_LIVE_EXECUTION_ENABLED", True)
    monkeypatch.setattr(Config, "TRADING_MT5_ORDER_SEND_ENABLED", True)
    monkeypatch.setattr(Config, "TRADING_AUTONOMOUS_POLICY_GATE_ENABLED", True)


def test_one_permission_snapshot_passes_pre_submit_and_adapter_admission(
    tmp_path, monkeypatch
):
    policy_result = run_policy(tmp_path / "policy", policy_inputs()).policy_result
    assert policy_result.decision == "ELIGIBLE_FOR_CONTROLLED_BOUNDARY"
    config = _ready_config()
    request, _ = _request(
        tmp_path,
        pre_submit_config=config,
        permission_setup=lambda: _enable_global_policy(monkeypatch),
    )
    client = AdmissionOnlyClient()

    receipt = MT5LiveAdapterDisabled(config=config, execution_client=client).submit_prepared_request(
        request
    )

    assert receipt.reason == "TEST_BROKER_SEAM_REPLACED"
    assert client.submissions == 1
    assert receipt.order_sent is False


def test_non_executable_acceptance_remains_blocked_before_controlled_client(tmp_path):
    config = MT5LiveAdapterPreSubmitConfig(kill_switch_engaged=False)
    request, _ = _request(tmp_path, pre_submit_config=config)
    client = AdmissionOnlyClient()

    receipt = MT5LiveAdapterDisabled(config=config, execution_client=client).submit_prepared_request(
        request
    )

    assert receipt.reason == "CONTROLLED_EXECUTION_DISABLED"
    assert client.submissions == 0
    assert receipt.order_sent is False


def test_adapter_rejects_permission_snapshot_mismatch(tmp_path, monkeypatch):
    config = _ready_config()
    request, _ = _request(
        tmp_path,
        pre_submit_config=config,
        permission_setup=lambda: _enable_global_policy(monkeypatch),
    )
    protected = dict(request.approved_semantic_parameters)
    protected["permission_state"] = {
        **protected["permission_state"],
        "allow_order_send": False,
    }
    request = replace(request, approved_semantic_parameters=protected)
    client = AdmissionOnlyClient()

    receipt = MT5LiveAdapterDisabled(config=config, execution_client=client).submit_prepared_request(
        request
    )

    assert receipt.reason == "PERMISSION_SNAPSHOT_MISMATCH"
    assert client.submissions == 0


@pytest.mark.parametrize(
    ("field", "blocked_value"),
    [
        ("live_adapter_enabled", False),
        ("live_adapter_hard_block", True),
        ("allow_live_submission", False),
        ("allow_order_send", False),
        ("controlled_execution_enabled", False),
        ("autonomous_execution_enabled", False),
        ("kill_switch_engaged", True),
        ("global_live_execution_enabled", False),
        ("global_order_send_enabled", False),
        ("autonomous_policy_gate_enabled", False),
    ],
)
def test_execution_ready_predicate_fails_closed_for_each_required_permission(
    monkeypatch, field, blocked_value
):
    _enable_global_policy(monkeypatch)
    state = execution_permission_state(_ready_config())
    state[field] = blocked_value

    assert not mandate_permissions_execution_ready(
        state, action="MARKET", order_type="BUY"
    )
