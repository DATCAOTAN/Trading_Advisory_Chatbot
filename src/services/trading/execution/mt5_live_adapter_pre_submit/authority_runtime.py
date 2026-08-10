from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.config import Config
from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import (
    MT5LiveAdapterDisabled,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.approval_pre_submit import (
    terminal_capability_from_lifecycle,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.lifecycle_supervisor import (
    MT5PositionLifecycleSupervisor,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.protected_artifact_capture import (
    ProtectedAccountContextCapture,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import (
    MT5PreSubmitJournalStore,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.trading_authority import (
    TradingAuthorityService,
    TradingAuthorityStore,
)
from src.services.trading.market.mt5_bridge_provider import MT5BridgeMarketDataProvider
from src.services.trading.market.timeframes import broker_symbol_for


@dataclass(frozen=True)
class MandateGrantCommand:
    mandate_id: str
    mandate_version: int
    permitted_symbols: tuple[str, ...]
    permitted_broker_symbols: tuple[str, ...]
    permitted_order_families: tuple[str, ...]
    permitted_management_actions: tuple[str, ...]
    maximum_volume: str
    maximum_risk_per_trade: str
    maximum_concurrent_positions: int
    maximum_trades_per_day: int
    maximum_loss_per_day: str
    active_from: str
    active_until: str
    expires_at: str
    kill_switch_engaged: bool


@dataclass(frozen=True)
class MandateSetupProjection:
    mandate_id: str
    mandate_version: int
    strategy_id: str
    strategy_version: str
    strategy_description: str
    operating_mode: str
    account_environment: str
    account_binding_status: str
    canonical_symbol: str
    broker_symbol: str
    permitted_order_families: tuple[str, ...]
    suggested_management_actions: tuple[str, ...]
    volume_min: str
    volume_max: str
    volume_step: str
    active_from: str
    active_until: str
    expires_at: str
    unresolved_fields: tuple[str, ...]
    field_sources: tuple[tuple[str, str], ...]


class TradingAuthorityOperatorService:
    """Operator commands; protected stores and current account remain authoritative."""

    def __init__(
        self,
        *,
        authority_service: TradingAuthorityService | None = None,
        account_adapter: Any | None = None,
        lifecycle_supervisor: Any | None = None,
        pre_submit_store: Any | None = None,
        market_provider: Any | None = None,
    ) -> None:
        self.authority = authority_service or TradingAuthorityService(TradingAuthorityStore())
        self.account_adapter = account_adapter or MT5LiveAdapterDisabled()
        self.lifecycle_supervisor = lifecycle_supervisor or MT5PositionLifecycleSupervisor()
        self.pre_submit_store = pre_submit_store or MT5PreSubmitJournalStore()
        self.market_provider = market_provider or MT5BridgeMarketDataProvider()

    def build_mandate_setup(
        self,
        strategy: Any,
        *,
        order_family: str,
        duration_minutes: int = 60,
        now: datetime | None = None,
    ) -> MandateSetupProjection:
        """Project authoritative facts into an editable, non-authoritative setup."""
        if duration_minutes not in {30, 60, 240}:
            raise ValueError("MANDATE_DURATION_PRESET_INVALID")
        if (
            strategy is None
            or strategy.requested_mode != "autonomous_live"
            or strategy.semantic_unresolved_fields
            or not strategy.canonical_symbol
            or not strategy.identity.strategy_id
            or order_family not in {"MARKET", "PENDING"}
        ):
            raise ValueError("MANDATE_STRATEGY_NOT_READY")

        generated_at = _utc(now)
        account = self._demo_account()
        account_capture = ProtectedAccountContextCapture.from_read_only_payload(
            account, generated_at
        )
        mode = self.authority.store.latest_mode()
        if (
            mode is None
            or mode.operating_mode != "autonomous_live"
            or not mode.integrity_valid()
        ):
            raise ValueError("MANDATE_MODE_NOT_READY")
        fingerprint_hash = hashlib.sha256(
            account_capture.account_context_fingerprint.encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(mode.account_fingerprint_hash, fingerprint_hash):
            raise ValueError("MANDATE_ACCOUNT_MISMATCH")

        canonical_symbol = str(strategy.canonical_symbol).upper()
        broker_symbol = broker_symbol_for(canonical_symbol)
        tick = self.market_provider.get_latest_tick(canonical_symbol)
        volume_min = _positive_decimal_text(tick.volume_min, "BROKER_VOLUME_MIN_INVALID")
        volume_max = _positive_decimal_text(tick.volume_max, "BROKER_VOLUME_MAX_INVALID")
        volume_step = _positive_decimal_text(tick.volume_step, "BROKER_VOLUME_STEP_INVALID")
        if Decimal(volume_min) > Decimal(volume_max):
            raise ValueError("BROKER_VOLUME_RANGE_INVALID")

        active_until = generated_at + timedelta(minutes=duration_minutes)
        mandate_id = "mandate_" + hashlib.sha256(
            f"{strategy.identity.strategy_id}|{canonical_symbol}|{broker_symbol}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        previous = self.authority.store.latest_mandate(mandate_id)
        mandate_version = 1 if previous is None else previous.mandate_version + 1
        return MandateSetupProjection(
            mandate_id=mandate_id,
            mandate_version=mandate_version,
            strategy_id=strategy.identity.strategy_id,
            strategy_version=strategy.identity.strategy_version,
            strategy_description=strategy.strategy_description,
            operating_mode="autonomous_live",
            account_environment=str(account["account_environment"]),
            account_binding_status="DEMO_ACCOUNT_MATCHED",
            canonical_symbol=canonical_symbol,
            broker_symbol=broker_symbol,
            permitted_order_families=(order_family,),
            suggested_management_actions=("OBSERVE", "NO_ACTION"),
            volume_min=volume_min,
            volume_max=volume_max,
            volume_step=volume_step,
            active_from=generated_at.isoformat(),
            active_until=active_until.isoformat(),
            expires_at=active_until.isoformat(),
            unresolved_fields=(
                "maximum_volume",
                "maximum_risk_per_trade",
                "maximum_concurrent_positions",
                "maximum_trades_per_day",
                "maximum_loss_per_day",
            ),
            field_sources=(
                ("canonical_symbol", "STRATEGY_DERIVED"),
                ("broker_symbol", "BROKER_MAPPING"),
                ("account_environment", "ACCOUNT_CONTEXT"),
                ("operating_mode", "MODE_AUTHORITY"),
                ("volume_constraints", "BROKER_METADATA"),
                ("mandate_id", "SYSTEM_CALCULATED"),
                ("mandate_version", "AUTHORITY_STORE"),
                ("validity_window", "SYSTEM_CALCULATED"),
                ("management_actions", "POLICY_SUGGESTION"),
            ),
        )

    def command_from_mandate_setup(
        self,
        setup: MandateSetupProjection,
        *,
        maximum_volume: str,
        maximum_risk_per_trade: str,
        maximum_concurrent_positions: int | None,
        maximum_trades_per_day: int | None,
        maximum_loss_per_day: str,
        permitted_management_actions: tuple[str, ...],
        kill_switch_engaged: bool,
    ) -> MandateGrantCommand:
        volume = Decimal(_positive_decimal_text(maximum_volume, "MANDATE_MAXIMUM_VOLUME_INVALID"))
        minimum = Decimal(setup.volume_min)
        maximum = Decimal(setup.volume_max)
        step = Decimal(setup.volume_step)
        if volume < minimum or volume > maximum or (volume - minimum) % step != 0:
            raise ValueError("MANDATE_MAXIMUM_VOLUME_OUTSIDE_BROKER_CONSTRAINTS")
        risk = _positive_decimal_text(
            maximum_risk_per_trade, "MANDATE_MAXIMUM_RISK_INVALID"
        )
        loss = _positive_decimal_text(
            maximum_loss_per_day, "MANDATE_MAXIMUM_LOSS_INVALID"
        )
        if not maximum_concurrent_positions or not maximum_trades_per_day:
            raise ValueError("MANDATE_COUNT_LIMIT_REQUIRED")
        allowed_management = {
            "OBSERVE",
            "NO_ACTION",
            "CANCEL_PENDING_ORDER",
            "MODIFY_POSITION_PROTECTION",
            "PARTIAL_CLOSE",
            "CLOSE_POSITION",
        }
        if any(item not in allowed_management for item in permitted_management_actions):
            raise ValueError("MANDATE_MANAGEMENT_ACTION_INVALID")
        return MandateGrantCommand(
            mandate_id=setup.mandate_id,
            mandate_version=setup.mandate_version,
            permitted_symbols=(setup.canonical_symbol,),
            permitted_broker_symbols=(setup.broker_symbol,),
            permitted_order_families=setup.permitted_order_families,
            permitted_management_actions=permitted_management_actions,
            maximum_volume=str(volume),
            maximum_risk_per_trade=risk,
            maximum_concurrent_positions=int(maximum_concurrent_positions),
            maximum_trades_per_day=int(maximum_trades_per_day),
            maximum_loss_per_day=loss,
            active_from=setup.active_from,
            active_until=setup.active_until,
            expires_at=setup.expires_at,
            kill_switch_engaged=bool(kill_switch_engaged),
        )

    def status(self, *, refresh_runtime: bool = False) -> dict[str, Any]:
        account = self.account_adapter.capture_account_context()
        mode = self.authority.store.latest_mode()
        mandates = self.authority.store.latest_mandates()
        lifecycle = (
            self.lifecycle_supervisor.run_once()
            if refresh_runtime
            else self.lifecycle_supervisor.status()
        )
        executions = self.lifecycle_supervisor.execution_journal.execution_records()
        execution_states = Counter(str(item.get("state", "UNKNOWN")) for item in executions)
        reconciliation_states = Counter(
            str(item["latest_reconciliation"].get("reconciliation_status", "UNKNOWN"))
            for item in executions
            if item.get("latest_reconciliation")
        )
        unresolved_execution_count = sum(
            execution_states.get(state, 0)
            for state in (
                "RESERVED",
                "SUBMISSION_STARTED",
                "RESULT_UNKNOWN",
                "RECONCILIATION_REQUIRED",
            )
        )
        pre_submit = self.pre_submit_store.summarize()
        return {
            "account_environment": account.get("account_environment", "UNKNOWN"),
            "account_trade_allowed": account.get("trade_allowed") is True,
            "mode": mode.operating_mode if mode else "NOT_SET",
            "mode_integrity_valid": bool(mode and mode.integrity_valid()),
            "mandates": tuple(item.to_public_dict() for item in mandates),
            "lifecycle": lifecycle.to_safe_dict(),
            "pre_submit": {
                "total_records": pre_submit.total_records,
                "total_valid": pre_submit.total_valid,
                "total_blocked": pre_submit.total_blocked,
                "latest_status": pre_submit.latest_status,
                "warnings": list(pre_submit.warnings),
            },
            "execution_state_counts": dict(sorted(execution_states.items())),
            "reconciliation_state_counts": dict(sorted(reconciliation_states.items())),
            "unresolved_execution_count": unresolved_execution_count,
            "permission_state": {
                "live_adapter_enabled": Config.TRADING_MT5_LIVE_ADAPTER_ENABLED,
                "live_submission_allowed": Config.TRADING_MT5_PRE_SUBMIT_ALLOW_LIVE_SUBMISSION,
                "order_send_allowed": Config.TRADING_MT5_PRE_SUBMIT_ALLOW_ORDER_SEND,
                "controlled_execution_enabled": Config.TRADING_MT5_CONTROLLED_EXECUTION_ENABLED,
                "pending_submission_enabled": Config.TRADING_MT5_PENDING_SUBMISSION_ENABLED,
                "autonomous_policy_gate_enabled": Config.TRADING_AUTONOMOUS_POLICY_GATE_ENABLED,
                "autonomous_open_eligibility_enabled": Config.TRADING_AUTONOMOUS_OPEN_ELIGIBILITY_ENABLED,
                "autonomous_management_eligibility_enabled": Config.TRADING_AUTONOMOUS_MANAGEMENT_ELIGIBILITY_ENABLED,
                "autonomous_execution_enabled": Config.TRADING_EXECUTION_AUTONOMOUS_ENABLED,
                "controlled_management_enabled": Config.TRADING_MT5_CONTROLLED_MANAGEMENT_ENABLED,
                "cancel_allowed": Config.TRADING_MT5_MANAGEMENT_CANCEL_ALLOWED,
                "protection_modification_allowed": Config.TRADING_MT5_MANAGEMENT_PROTECTION_MODIFICATION_ALLOWED,
                "position_close_allowed": Config.TRADING_MT5_MANAGEMENT_POSITION_CLOSE_ALLOWED,
                "execution_kill_switch_engaged": Config.TRADING_EXECUTION_KILL_SWITCH,
                "management_kill_switch_engaged": Config.TRADING_MT5_MANAGEMENT_KILL_SWITCH_ENGAGED,
            },
            "metadata_redacted": True,
        }

    def set_mode(
        self,
        operating_mode: str,
        *,
        operator_grant: bool,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        account = self._demo_account()
        record = self.authority.set_mode(
            operating_mode,
            account_fingerprint=account["account_context_fingerprint"],
            account_is_demo=True,
            operator_grant=operator_grant,
            nonce=idempotency_key or secrets.token_hex(16),
        )
        return record.to_public_dict()

    def grant_mandate(
        self, command: MandateGrantCommand, *, operator_grant: bool
    ) -> dict[str, Any]:
        account = self._demo_account()
        record = self.authority.grant_mandate(
            **command.__dict__,
            account_fingerprint=account["account_context_fingerprint"],
            account_is_demo=True,
            nonce=secrets.token_hex(16),
            idempotency_key=secrets.token_hex(24),
            operator_grant=operator_grant,
        )
        return record.to_public_dict()

    def revoke_mandate(
        self, mandate_id: str, *, operator_grant: bool
    ) -> dict[str, Any]:
        record = self.authority.revoke_mandate(
            mandate_id,
            operator_grant=operator_grant,
            revocation_nonce=secrets.token_hex(16),
        )
        return record.to_public_dict()

    def pre_submit_evidence(self, candidate: Any) -> dict[str, Any]:
        """Collect current read-only evidence for the existing pre-submit lifecycle."""
        account = self._demo_account()
        capture = ProtectedAccountContextCapture.from_read_only_payload(
            account, datetime.now(timezone.utc)
        )
        lifecycle = self.lifecycle_supervisor.run_once()
        return {
            "account_context": capture,
            "expected_account_fingerprint": capture.account_context_fingerprint,
            "terminal_capability": terminal_capability_from_lifecycle(
                candidate, lifecycle, capture.account_context_fingerprint
            ),
            "current_lifecycle_status": lifecycle,
            "account_is_demo": True,
        }

    def close(self) -> None:
        self.account_adapter.close()
        close_market_provider = getattr(self.market_provider, "close", None)
        if close_market_provider is not None:
            close_market_provider()

    def _demo_account(self) -> dict[str, Any]:
        account = self.account_adapter.capture_account_context()
        if account.get("account_environment") != "DEMO":
            raise RuntimeError("REAL_ACCOUNT_AUTHORITY_FORBIDDEN")
        return account


def _positive_decimal_text(value: Any, error: str) -> str:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(error)
    return format(result.normalize(), "f")


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)
