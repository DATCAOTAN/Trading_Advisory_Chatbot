from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5PreSubmitGateReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig


class MT5PreSubmitGate:
    def __init__(self, config: MT5LiveAdapterPreSubmitConfig | None = None):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()

    def evaluate(
        self,
        final_validation,
        final_validation_report,
        bridge_check,
        kill_switch_check,
        idempotency_check,
        adapter_receipt,
    ) -> MT5PreSubmitGateReport:
        blockers: list[str] = []
        if final_validation is None or final_validation_report is None:
            blockers.append("MISSING_FINAL_VALIDATION")
        elif not getattr(final_validation_report, "valid", False):
            blockers.append("FINAL_VALIDATION_NOT_VALID")
        if final_validation_report is not None and not getattr(final_validation_report, "bridge_write_skeleton_check_allowed", False):
            blockers.append("BRIDGE_WRITE_SKELETON_NOT_ALLOWED")
        if bridge_check is None or getattr(bridge_check, "reachable", False) is not True:
            blockers.append("BRIDGE_WRITE_SKELETON_UNREACHABLE")
        if bridge_check is None or getattr(bridge_check, "status", "") != "BLOCKED":
            blockers.append("BRIDGE_WRITE_SKELETON_NOT_BLOCKED")
        if adapter_receipt is None or getattr(adapter_receipt, "adapter_enabled", False) is not False:
            blockers.append("INVALID_INPUT")
        else:
            blockers.append("LIVE_ADAPTER_DISABLED")
        if idempotency_check is None:
            blockers.append("IDEMPOTENCY_MISSING")
        elif getattr(idempotency_check, "status", "") == "DUPLICATE_BLOCKED":
            blockers.append("IDEMPOTENCY_DUPLICATE")
        elif getattr(idempotency_check, "status", "") != "CHECK_REGISTERED":
            blockers.append("IDEMPOTENCY_MISSING")
        if any(getattr(item, "order_send_allowed", False) for item in [final_validation_report, bridge_check, adapter_receipt] if item is not None):
            blockers.append("ORDER_SEND_NOT_ALLOWED")
        if any(getattr(item, "live_execution_allowed", False) for item in [final_validation_report, bridge_check, adapter_receipt] if item is not None):
            blockers.append("LIVE_EXECUTION_DISABLED")
        if any(getattr(item, "execution_allowed", False) for item in [final_validation_report, bridge_check, adapter_receipt] if item is not None):
            blockers.append("EXECUTION_DISABLED")
        if final_validation_report is not None:
            if getattr(final_validation_report, "real_mt5_payload_created", False):
                blockers.append("REAL_MT5_PAYLOAD_NOT_ALLOWED")
            if getattr(final_validation_report, "broker_submittable_request_dict_created", False):
                blockers.append("BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED")
            if getattr(final_validation_report, "mt5_constants_used", False):
                blockers.append("MT5_CONSTANT_NOT_ALLOWED")
            if getattr(final_validation_report, "broker_submission_created", False):
                blockers.append("BROKER_SUBMISSION_NOT_ALLOWED")
            if getattr(final_validation_report, "executable", False):
                blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if any(getattr(item, "ticket", None) is not None or getattr(item, "deal", None) is not None for item in [bridge_check, adapter_receipt] if item is not None):
            blockers.append("TICKET_DEAL_NOT_ALLOWED")

        blocking = [item for item in blockers if item not in {"LIVE_ADAPTER_DISABLED", "KILL_SWITCH_ENGAGED"}]
        valid = not blocking
        status = "PASSED_DISABLED_PRE_SUBMIT_CHECK" if valid else ("DUPLICATE" if "IDEMPOTENCY_DUPLICATE" in blockers else "BLOCKED")
        report = MT5PreSubmitGateReport(
            report_id=_report_id(getattr(final_validation, "final_validation_id", ""), getattr(idempotency_check, "check_id", "")),
            created_at=now_utc_iso(),
            status=status,
            valid=valid,
            controlled_demo_integration_workflow_allowed=valid,
            live_submission_allowed=False,
            source_final_validation_id=getattr(final_validation, "final_validation_id", ""),
            source_final_validation_report_id=getattr(final_validation_report, "validation_report_id", ""),
            source_bridge_skeleton_check_id=getattr(bridge_check, "check_id", ""),
            source_kill_switch_check_id=getattr(kill_switch_check, "check_id", ""),
            source_idempotency_check_id=getattr(idempotency_check, "check_id", ""),
            adapter_receipt_id=getattr(adapter_receipt, "receipt_id", ""),
            kill_switch_engaged=bool(getattr(kill_switch_check, "engaged", True)),
            idempotency_status=getattr(idempotency_check, "status", "UNKNOWN"),
            bridge_write_skeleton_reachable=bool(getattr(bridge_check, "reachable", False)),
            bridge_write_skeleton_status=getattr(bridge_check, "status", "UNKNOWN"),
            blockers=list(dict.fromkeys(blockers)),
            source_refs=list(getattr(final_validation, "source_refs", []) or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False))
        return report


def _report_id(final_validation_id: str, idempotency_check_id: str) -> str:
    return "mt5_pre_submit_gate_report_" + hashlib.sha256(f"{final_validation_id}:{idempotency_check_id}".encode("utf-8")).hexdigest()[:16]
