from __future__ import annotations

import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
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


class TradingAuthorityOperatorService:
    """Operator commands; protected stores and current account remain authoritative."""

    def __init__(
        self,
        *,
        authority_service: TradingAuthorityService | None = None,
        account_adapter: Any | None = None,
        lifecycle_supervisor: Any | None = None,
        pre_submit_store: Any | None = None,
    ) -> None:
        self.authority = authority_service or TradingAuthorityService(TradingAuthorityStore())
        self.account_adapter = account_adapter or MT5LiveAdapterDisabled()
        self.lifecycle_supervisor = lifecycle_supervisor or MT5PositionLifecycleSupervisor()
        self.pre_submit_store = pre_submit_store or MT5PreSubmitJournalStore()

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

    def _demo_account(self) -> dict[str, Any]:
        account = self.account_adapter.capture_account_context()
        if account.get("account_environment") != "DEMO":
            raise RuntimeError("REAL_ACCOUNT_AUTHORITY_FORBIDDEN")
        return account
