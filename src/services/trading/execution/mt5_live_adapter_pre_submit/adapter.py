from __future__ import annotations

import hmac
from time import perf_counter

from src.services.trading.execution.mt5_bridge_write_skeleton import MT5BridgeWriteSkeletonService
from src.services.trading.execution.mt5_bridge_write_skeleton.client import MT5BridgeWriteSkeletonClient
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled import (
    AUTONOMOUS_EXECUTION_REQUEST_VERSION,
    PENDING_EXECUTION_REQUEST_VERSION,
    MT5ControlledExecutionReceipt,
    MT5ControlledExecutionRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.controlled_management import (
    MT5ControlledManagementReceipt,
    MT5ControlledManagementRequest,
    management_confirmation_phrase,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.reconciliation import (
    MT5ReconciliationReceipt,
    MT5ReconciliationRequest,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5LiveAdapterDisabledReceipt,
    hash_text,
    now_utc_iso,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


class MT5LiveAdapterDisabled:
    def __init__(
        self,
        config: MT5LiveAdapterPreSubmitConfig | None = None,
        bridge_service: MT5BridgeWriteSkeletonService | None = None,
        execution_client: MT5BridgeWriteSkeletonClient | None = None,
    ):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()
        self.bridge_service = bridge_service or MT5BridgeWriteSkeletonService()
        self.execution_client = execution_client or MT5BridgeWriteSkeletonClient(
            self.config.bridge_url,
            timeout_seconds=self.config.controlled_execution_http_timeout_seconds,
        )

    def health_check(self) -> dict:
        return {
            "adapter_status": "DISABLED_READY",
            "adapter_enabled": False,
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
        }

    def check_bridge_write_skeleton(self):
        return self.bridge_service.run()

    def capture_account_context(self) -> dict:
        payload = self.execution_client.account_context()
        fingerprint = str(payload.get("account_context_fingerprint", ""))
        if payload.get("status") != "OK" or not fingerprint:
            raise ValueError("MT5 account context is unavailable")
        return {
            "account_context_fingerprint": fingerprint,
            "account_id_hash": str(payload.get("account_id_hash", "")),
            "server_redacted": str(payload.get("server_redacted", "")),
            "currency": payload.get("currency"),
            "trade_mode": payload.get("trade_mode"),
            "account_environment": str(payload.get("account_environment", "UNKNOWN")),
            "trade_allowed": payload.get("trade_allowed") is True,
            "redacted": True,
        }

    def submit_controlled(
        self,
        approval_lock,
        final_validation,
        final_validation_report,
        pre_submit_report,
        *,
        expected_account_context_fingerprint: str,
        typed_confirmation: str,
    ) -> MT5ControlledExecutionReceipt:
        blocker = self._controlled_submission_blocker(typed_confirmation)
        if blocker:
            return MT5ControlledExecutionReceipt("BLOCKED", "NOT_RESERVED", False, False, False, blocker)
        current_context = self.capture_account_context()
        if not hmac.compare_digest(
            current_context["account_context_fingerprint"],
            str(expected_account_context_fingerprint or ""),
        ):
            return MT5ControlledExecutionReceipt(
                "BLOCKED", "NOT_RESERVED", False, False, False, "ACCOUNT_CONTEXT_CHANGED"
            )
        request = MT5ControlledExecutionRequest.from_artifacts(
            approval_lock,
            final_validation,
            final_validation_report,
            pre_submit_report,
            expected_account_context_fingerprint=current_context["account_context_fingerprint"],
            human_confirmation_phrase=typed_confirmation,
        )
        try:
            payload = self.execution_client.submit_controlled(
                request.as_protected_dict(), self.config.execution_auth_token
            )
        except Exception:
            return MT5ControlledExecutionReceipt(
                "UNKNOWN", "RESULT_UNKNOWN", False, False, False, "BRIDGE_RESULT_UNKNOWN"
            )
        return MT5ControlledExecutionReceipt.from_payload(payload)

    def submit_prepared_request(
        self, request: MT5ControlledExecutionRequest, *, typed_confirmation: str = ""
    ) -> MT5ControlledExecutionReceipt:
        blocker = self._controlled_submission_blocker(typed_confirmation, request)
        if blocker:
            return MT5ControlledExecutionReceipt("BLOCKED", "NOT_RESERVED", False, False, False, blocker)
        if request.authorization_source == "STANDING_MANDATE":
            if (
                request.request_version != AUTONOMOUS_EXECUTION_REQUEST_VERSION
                or not request.authorization_reference
                or request.human_confirmation_phrase
                or request.human_confirmation_reference
            ):
                return MT5ControlledExecutionReceipt(
                    "BLOCKED", "NOT_RESERVED", False, False, False, "MANDATE_AUTHORIZATION_INVALID"
                )
        elif not hmac.compare_digest(request.human_confirmation_phrase, typed_confirmation.strip()):
            return MT5ControlledExecutionReceipt(
                "BLOCKED", "NOT_RESERVED", False, False, False, "HUMAN_CONFIRMATION_INVALID"
            )
        expected_ref = hash_text(
            f"{typed_confirmation.strip()}|{request.idempotency_key}|{request.expected_account_context_fingerprint}"
        )
        if request.authorization_source != "STANDING_MANDATE" and not hmac.compare_digest(request.human_confirmation_reference, expected_ref):
            return MT5ControlledExecutionReceipt(
                "BLOCKED", "NOT_RESERVED", False, False, False, "HUMAN_CONFIRMATION_INVALID"
            )
        current_context = self.capture_account_context()
        if not hmac.compare_digest(
            current_context["account_context_fingerprint"], request.expected_account_context_fingerprint
        ):
            return MT5ControlledExecutionReceipt(
                "BLOCKED", "NOT_RESERVED", False, False, False, "ACCOUNT_CONTEXT_CHANGED"
            )
        if request.authorization_source == "STANDING_MANDATE" and current_context.get("account_environment") != "DEMO":
            return MT5ControlledExecutionReceipt(
                "BLOCKED", "NOT_RESERVED", False, False, False, "REAL_ACCOUNT_EXECUTION_FORBIDDEN"
            )
        try:
            payload = self.execution_client.submit_controlled(
                request.as_protected_dict(), self.config.execution_auth_token
            )
        except Exception:
            return MT5ControlledExecutionReceipt(
                "UNKNOWN", "RESULT_UNKNOWN", False, False, False, "BRIDGE_RESULT_UNKNOWN"
            )
        return MT5ControlledExecutionReceipt.from_payload(payload)

    def manage_prepared_request(
        self,
        request: MT5ControlledManagementRequest,
        *,
        typed_confirmation: str = "",
    ) -> MT5ControlledManagementReceipt:
        blocker = self._management_blocker(
            request.management_intent,
            typed_confirmation,
            authorization_source=request.authorization_source,
        )
        if blocker:
            return _blocked_management_receipt(request.management_intent, blocker)
        try:
            request.validate()
        except ValueError as exc:
            return _blocked_management_receipt(request.management_intent, str(exc))
        if request.authorization_source == "HUMAN_CONFIRMATION" and not hmac.compare_digest(
            request.human_confirmation_phrase, str(typed_confirmation or "").strip()
        ):
            return _blocked_management_receipt(
                request.management_intent, "MANAGEMENT_CONFIRMATION_INVALID"
            )
        current_context = self.capture_account_context()
        if not hmac.compare_digest(
            current_context["account_context_fingerprint"],
            request.expected_account_context_fingerprint,
        ):
            return _blocked_management_receipt(
                request.management_intent, "ACCOUNT_CONTEXT_CHANGED"
            )
        try:
            payload = self.execution_client.manage_controlled(
                request.as_protected_dict(), self.config.execution_auth_token
            )
        except Exception:
            return MT5ControlledManagementReceipt(
                "UNKNOWN", request.management_intent, "RESULT_UNKNOWN", False,
                True, True, False, False, False, False, "BRIDGE_RESULT_UNKNOWN"
            )
        return MT5ControlledManagementReceipt.from_payload(payload)

    def reconcile_controlled(
        self,
        request: MT5ReconciliationRequest,
        *,
        typed_confirmation: str,
    ) -> MT5ReconciliationReceipt:
        phrase = str(typed_confirmation or "").strip()
        if not self.config.reconciliation_enabled or not self.config.execution_auth_token:
            return MT5ReconciliationReceipt.from_payload(
                {"status": "BLOCKED", "reason": "RECONCILIATION_DISABLED"}
            )
        if not hmac.compare_digest(phrase, self.config.reconciliation_confirmation_phrase):
            return MT5ReconciliationReceipt.from_payload(
                {"status": "BLOCKED", "reason": "HUMAN_CONFIRMATION_INVALID"}
            )
        current_context = self.capture_account_context()
        if not hmac.compare_digest(
            current_context["account_context_fingerprint"],
            request.expected_account_context_fingerprint,
        ):
            return MT5ReconciliationReceipt.from_payload(
                {"status": "BLOCKED", "reason": "ACCOUNT_CONTEXT_CHANGED"}
            )
        try:
            payload = self.execution_client.reconcile(
                request.as_protected_dict(), self.config.execution_auth_token
            )
        except Exception:
            return MT5ReconciliationReceipt.from_payload(
                {"status": "FAILED", "reason": "RECONCILIATION_TRANSPORT_FAILED"}
            )
        return MT5ReconciliationReceipt.from_payload(payload)

    def _controlled_submission_blocker(
        self,
        typed_confirmation: str,
        request: MT5ControlledExecutionRequest | None = None,
    ) -> str:
        if (
            not self.config.controlled_execution_enabled
            or not self.config.live_adapter_enabled
            or self.config.live_adapter_hard_block
            or not self.config.allow_live_submission
            or not self.config.allow_order_send
            or self.config.kill_switch_engaged
        ):
            return "CONTROLLED_EXECUTION_DISABLED"
        if request is not None and request.authorization_source == "STANDING_MANDATE":
            if not self.config.autonomous_execution_enabled:
                return "AUTONOMOUS_EXECUTION_DISABLED"
            if typed_confirmation:
                return "MANDATE_AUTHORIZATION_INVALID"
        if request is not None and request.request_version == PENDING_EXECUTION_REQUEST_VERSION:
            order_type = str(
                request.approved_semantic_parameters.get("order_type", "")
            ).upper()
            family_allowed = (
                self.config.pending_limit_enabled
                if order_type in {"BUY_LIMIT", "SELL_LIMIT"}
                else self.config.pending_stop_enabled
                if order_type in {"BUY_STOP", "SELL_STOP"}
                else self.config.pending_stop_limit_enabled
                if order_type in {"BUY_STOP_LIMIT", "SELL_STOP_LIMIT"}
                else False
            )
            if (
                not self.config.pending_submission_enabled
                or self.config.pending_submission_hard_block
                or not family_allowed
            ):
                return "PENDING_SUBMISSION_DISABLED"
        if not self.config.execution_auth_token:
            return "CONTROLLED_EXECUTION_AUTHENTICATION_MISSING"
        if request is None or request.authorization_source != "STANDING_MANDATE":
            if not hmac.compare_digest(
            str(typed_confirmation or "").strip(), self.config.execution_confirmation_phrase
            ):
                return "HUMAN_CONFIRMATION_INVALID"
        return ""

    def _management_blocker(
        self,
        intent: str,
        typed_confirmation: str,
        *,
        authorization_source: str = "HUMAN_CONFIRMATION",
    ) -> str:
        allowed = {
            "CANCEL_PENDING_ORDER": self.config.management_cancel_allowed,
            "MODIFY_POSITION_PROTECTION": self.config.management_protection_modification_allowed,
            "CLOSE_POSITION": self.config.management_position_close_allowed,
        }.get(intent, False)
        if (
            not self.config.controlled_management_enabled
            or self.config.management_hard_block
            or self.config.management_kill_switch_engaged
            or self.config.kill_switch_engaged
            or not self.config.live_adapter_enabled
            or self.config.live_adapter_hard_block
            or not self.config.allow_live_submission
            or not self.config.allow_order_send
            or not allowed
        ):
            return "CONTROLLED_MANAGEMENT_DISABLED"
        if not self.config.execution_auth_token:
            return "CONTROLLED_MANAGEMENT_AUTHENTICATION_MISSING"
        try:
            expected = management_confirmation_phrase(intent)
        except ValueError:
            return "MANAGEMENT_INTENT_INVALID"
        if authorization_source not in {"HUMAN_CONFIRMATION", "STANDING_MANDATE"}:
            return "MANAGEMENT_AUTHORIZATION_SOURCE_INVALID"
        if authorization_source == "HUMAN_CONFIRMATION" and not hmac.compare_digest(
            str(typed_confirmation or "").strip(), expected
        ):
            return "MANAGEMENT_CONFIRMATION_INVALID"
        return ""

    def pre_submit_check(self) -> MT5LiveAdapterDisabledReceipt:
        bridge_result = self.check_bridge_write_skeleton()
        return self.submit_disabled(bridge_result.check)

    def submit_disabled(self, bridge_check=None) -> MT5LiveAdapterDisabledReceipt:
        started = perf_counter()
        created_at = now_utc_iso()
        reachable = bool(getattr(bridge_check, "reachable", False))
        status = str(getattr(bridge_check, "status", "UNKNOWN"))
        endpoint = str(getattr(bridge_check, "endpoint", "/execution/write-skeleton/check"))
        blockers = ["LIVE_ADAPTER_DISABLED"]
        if not reachable:
            blockers.append("BRIDGE_WRITE_SKELETON_UNREACHABLE")
        if status != "BLOCKED":
            blockers.append("BRIDGE_WRITE_SKELETON_NOT_BLOCKED")
        return MT5LiveAdapterDisabledReceipt(
            receipt_id="mt5_live_adapter_disabled_receipt_" + hash_text(created_at + status)[:16],
            created_at=created_at,
            adapter_status="BLOCKED_BY_DISABLED_ADAPTER",
            bridge_check_reachable=reachable,
            bridge_check_status=status,
            bridge_endpoint=endpoint,
            adapter_enabled=False,
            blockers=blockers,
            latency_ms=(perf_counter() - started) * 1000,
        )

    def close(self) -> None:
        return None


def _blocked_management_receipt(intent: str, reason: str) -> MT5ControlledManagementReceipt:
    return MT5ControlledManagementReceipt(
        "BLOCKED", intent, "NOT_RESERVED", False, False, False,
        False, False, False, False, reason
    )
