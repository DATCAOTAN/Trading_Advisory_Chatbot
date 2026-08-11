from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class MT5LiveAdapterPreSubmitConfig:
    enabled: bool = True
    live_adapter_enabled: bool = False
    live_adapter_hard_block: bool = True
    pre_submit_gate_enabled: bool = True
    allow_live_submission: bool = False
    allow_order_send: bool = False
    require_final_validation: bool = True
    require_bridge_skeleton_check: bool = True
    require_idempotency: bool = True
    require_kill_switch: bool = True
    kill_switch_engaged: bool = True
    idempotency_ttl_seconds: int = 300
    journal_enabled: bool = True
    journal_path: str = "data/trading/execution_journal/mt5_pre_submit_checks.jsonl"
    idempotency_path: str = "data/trading/execution_journal/mt5_pre_submit_idempotency.jsonl"
    max_read_records: int = 100
    controlled_execution_enabled: bool = False
    autonomous_execution_enabled: bool = False
    pending_submission_enabled: bool = False
    pending_submission_hard_block: bool = True
    pending_limit_enabled: bool = False
    pending_stop_enabled: bool = False
    pending_stop_limit_enabled: bool = False
    execution_auth_token: str = field(default="", repr=False)
    execution_confirmation_phrase: str = "SUBMIT CONTROLLED MT5 ORDER"
    bridge_url: str = "http://host.docker.internal:8765"
    bridge_timeout_seconds: float = 3.0
    controlled_execution_http_timeout_seconds: float = 10.0
    reconciliation_enabled: bool = True
    reconciliation_confirmation_phrase: str = "RECONCILE CONTROLLED MT5 EXECUTION"
    controlled_management_enabled: bool = False
    management_hard_block: bool = True
    management_kill_switch_engaged: bool = True
    management_cancel_allowed: bool = False
    management_protection_modification_allowed: bool = False
    management_position_close_allowed: bool = False
    management_max_request_age_seconds: int = 300

    @classmethod
    def from_config(cls, config=None) -> "MT5LiveAdapterPreSubmitConfig":
        if config is None:
            try:
                from src.config import Config

                config = Config
            except Exception:
                config = None
        if config is None:
            return cls()
        return cls(
            enabled=getattr(config, "TRADING_MT5_LIVE_ADAPTER_PRE_SUBMIT_ENABLED", True),
            live_adapter_enabled=getattr(config, "TRADING_MT5_LIVE_ADAPTER_ENABLED", False),
            live_adapter_hard_block=getattr(config, "TRADING_MT5_LIVE_ADAPTER_HARD_BLOCK", True),
            pre_submit_gate_enabled=getattr(config, "TRADING_MT5_PRE_SUBMIT_GATE_ENABLED", True),
            allow_live_submission=getattr(config, "TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION", False),
            allow_order_send=getattr(config, "TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND", False),
            require_final_validation=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_FINAL_VALIDATION", True),
            require_bridge_skeleton_check=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_BRIDGE_SKELETON_CHECK", True),
            require_idempotency=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_IDEMPOTENCY", True),
            require_kill_switch=getattr(config, "TRADING_MT5_PRE_SUBMIT_REQUIRE_KILL_SWITCH", True),
            kill_switch_engaged=getattr(config, "TRADING_MT5_KILL_SWITCH_ENGAGED", True),
            idempotency_ttl_seconds=getattr(config, "TRADING_MT5_IDEMPOTENCY_CHECK_TTL_SECONDS", 300),
            journal_enabled=getattr(config, "TRADING_MT5_PRE_SUBMIT_JOURNAL_ENABLED", True),
            journal_path=getattr(config, "TRADING_MT5_PRE_SUBMIT_JOURNAL_PATH", "data/trading/execution_journal/mt5_pre_submit_checks.jsonl"),
            idempotency_path=getattr(config, "TRADING_MT5_PRE_SUBMIT_IDEMPOTENCY_PATH", "data/trading/execution_journal/mt5_pre_submit_idempotency.jsonl"),
            max_read_records=getattr(config, "TRADING_MT5_PRE_SUBMIT_MAX_READ_RECORDS", 100),
            controlled_execution_enabled=getattr(config, "TRADING_MT5_CONTROLLED_EXECUTION_ENABLED", False),
            autonomous_execution_enabled=getattr(config, "TRADING_EXECUTION_AUTONOMOUS_ENABLED", False),
            pending_submission_enabled=getattr(
                config, "TRADING_MT5_PENDING_SUBMISSION_ENABLED", False
            ),
            pending_submission_hard_block=getattr(
                config, "TRADING_MT5_PENDING_SUBMISSION_HARD_BLOCK", True
            ),
            pending_limit_enabled=getattr(config, "TRADING_MT5_PENDING_LIMIT_ENABLED", False),
            pending_stop_enabled=getattr(config, "TRADING_MT5_PENDING_STOP_ENABLED", False),
            pending_stop_limit_enabled=getattr(
                config, "TRADING_MT5_PENDING_STOP_LIMIT_ENABLED", False
            ),
            execution_auth_token=getattr(config, "TRADING_MT5_CONTROLLED_EXECUTION_AUTH_TOKEN", ""),
            execution_confirmation_phrase=getattr(config, "TRADING_MT5_CONTROLLED_EXECUTION_CONFIRMATION_PHRASE", "SUBMIT CONTROLLED MT5 ORDER"),
            bridge_url=getattr(config, "MT5_BRIDGE_URL", "http://host.docker.internal:8765"),
            bridge_timeout_seconds=getattr(config, "MT5_BRIDGE_TIMEOUT_SECONDS", 3.0),
            controlled_execution_http_timeout_seconds=getattr(
                config, "TRADING_MT5_CONTROLLED_EXECUTION_HTTP_TIMEOUT_SECONDS", 10.0
            ),
            reconciliation_enabled=getattr(config, "TRADING_MT5_RECONCILIATION_ENABLED", True),
            reconciliation_confirmation_phrase=getattr(
                config,
                "TRADING_MT5_RECONCILIATION_CONFIRMATION_PHRASE",
                "RECONCILE CONTROLLED MT5 EXECUTION",
            ),
            controlled_management_enabled=getattr(
                config, "TRADING_MT5_CONTROLLED_MANAGEMENT_ENABLED", False
            ),
            management_hard_block=getattr(
                config, "TRADING_MT5_CONTROLLED_MANAGEMENT_HARD_BLOCK", True
            ),
            management_kill_switch_engaged=getattr(
                config, "TRADING_MT5_MANAGEMENT_KILL_SWITCH_ENGAGED", True
            ),
            management_cancel_allowed=getattr(
                config, "TRADING_MT5_MANAGEMENT_CANCEL_ALLOWED", False
            ),
            management_protection_modification_allowed=getattr(
                config, "TRADING_MT5_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED", False
            ),
            management_position_close_allowed=getattr(
                config, "TRADING_MT5_MANAGEMENT_POSITION_CLOSE_ALLOWED", False
            ),
            management_max_request_age_seconds=getattr(
                config, "TRADING_MT5_MANAGEMENT_MAX_REQUEST_AGE_SECONDS", 300
            ),
        )


def execution_permission_state(
    config: MT5LiveAdapterPreSubmitConfig, global_config=None
) -> dict[str, bool]:
    if global_config is None:
        from src.config import Config

        global_config = Config
    return {
        "live_adapter_enabled": bool(config.live_adapter_enabled),
        "live_adapter_hard_block": bool(config.live_adapter_hard_block),
        "allow_live_submission": bool(config.allow_live_submission),
        "allow_order_send": bool(config.allow_order_send),
        "controlled_execution_enabled": bool(config.controlled_execution_enabled),
        "autonomous_execution_enabled": bool(config.autonomous_execution_enabled),
        "pending_submission_enabled": bool(config.pending_submission_enabled),
        "pending_submission_hard_block": bool(config.pending_submission_hard_block),
        "pending_limit_enabled": bool(config.pending_limit_enabled),
        "pending_stop_enabled": bool(config.pending_stop_enabled),
        "pending_stop_limit_enabled": bool(config.pending_stop_limit_enabled),
        "kill_switch_engaged": bool(config.kill_switch_engaged),
        "global_live_execution_enabled": bool(
            getattr(global_config, "TRADING_MT5_LIVE_EXECUTION_ENABLED", False)
        ),
        "global_order_send_enabled": bool(
            getattr(global_config, "TRADING_MT5_ORDER_SEND_ENABLED", False)
        ),
        "autonomous_policy_gate_enabled": bool(
            getattr(global_config, "TRADING_AUTONOMOUS_POLICY_GATE_ENABLED", False)
        ),
    }


def mandate_permissions_safely_disabled(state: Mapping[str, bool]) -> bool:
    return (
        state.get("live_adapter_hard_block") is True
        and state.get("pending_submission_hard_block") is True
        and state.get("kill_switch_engaged") is False
        and all(
            state.get(name) is False
            for name in (
                "live_adapter_enabled",
                "allow_live_submission",
                "allow_order_send",
                "controlled_execution_enabled",
                "autonomous_execution_enabled",
                "pending_submission_enabled",
                "global_live_execution_enabled",
                "global_order_send_enabled",
                "autonomous_policy_gate_enabled",
            )
        )
    )


def mandate_permissions_execution_ready(
    state: Mapping[str, bool], *, action: str, order_type: str
) -> bool:
    if not (
        state.get("live_adapter_enabled") is True
        and state.get("live_adapter_hard_block") is False
        and state.get("allow_live_submission") is True
        and state.get("allow_order_send") is True
        and state.get("controlled_execution_enabled") is True
        and state.get("autonomous_execution_enabled") is True
        and state.get("kill_switch_engaged") is False
        and state.get("global_live_execution_enabled") is True
        and state.get("global_order_send_enabled") is True
        and state.get("autonomous_policy_gate_enabled") is True
    ):
        return False
    if str(action).upper() != "PENDING":
        return True
    order_type = str(order_type).upper()
    family_enabled = (
        state.get("pending_limit_enabled") is True
        if order_type in {"BUY_LIMIT", "SELL_LIMIT"}
        else state.get("pending_stop_enabled") is True
        if order_type in {"BUY_STOP", "SELL_STOP"}
        else state.get("pending_stop_limit_enabled") is True
        if order_type in {"BUY_STOP_LIMIT", "SELL_STOP_LIMIT"}
        else False
    )
    return (
        state.get("pending_submission_enabled") is True
        and state.get("pending_submission_hard_block") is False
        and family_enabled
    )


def autonomous_monitor_permissions_coherent(
    config: MT5LiveAdapterPreSubmitConfig, global_config=None
) -> bool:
    """Allow observation-only or fully execution-ready autonomous monitoring."""
    if global_config is None:
        from src.config import Config

        global_config = Config
    state = execution_permission_state(config, global_config)
    pending_disabled = (
        state["pending_submission_enabled"] is False
        and state["pending_submission_hard_block"] is True
        and state["pending_limit_enabled"] is False
        and state["pending_stop_enabled"] is False
        and state["pending_stop_limit_enabled"] is False
    )
    pending_ready = (
        state["pending_submission_enabled"] is True
        and state["pending_submission_hard_block"] is False
        and any(
            state[name] is True
            for name in (
                "pending_limit_enabled",
                "pending_stop_enabled",
                "pending_stop_limit_enabled",
            )
        )
    )
    observation_only = (
        state["live_adapter_hard_block"] is True
        and state["kill_switch_engaged"] is True
        and pending_disabled
        and all(
            state[name] is False
            for name in (
                "live_adapter_enabled",
                "allow_live_submission",
                "allow_order_send",
                "controlled_execution_enabled",
                "autonomous_execution_enabled",
                "global_live_execution_enabled",
                "global_order_send_enabled",
                "autonomous_policy_gate_enabled",
            )
        )
        and getattr(global_config, "TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED", False)
        is False
        and getattr(global_config, "TRADING_AUTONOMOUS_POLICY_HARD_BLOCK", True) is True
        and getattr(global_config, "TRADING_EXECUTION_LIVE_ENABLED", False) is False
        and getattr(global_config, "TRADING_EXECUTION_AUTONOMOUS_ENABLED", False)
        is False
        and getattr(global_config, "TRADING_EXECUTION_KILL_SWITCH", True) is True
    )
    execution_ready = (
        mandate_permissions_execution_ready(state, action="MARKET", order_type="BUY")
        and (pending_disabled or pending_ready)
        and getattr(global_config, "TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED", False)
        is True
        and getattr(global_config, "TRADING_AUTONOMOUS_POLICY_HARD_BLOCK", True) is False
        and getattr(global_config, "TRADING_EXECUTION_LIVE_ENABLED", False) is True
        and getattr(global_config, "TRADING_EXECUTION_AUTONOMOUS_ENABLED", False) is True
        and getattr(global_config, "TRADING_EXECUTION_KILL_SWITCH", True) is False
    )
    return observation_only or execution_ready
