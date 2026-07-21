from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from src.services.trading.execution.mt5_live_adapter_pre_submit.adapter import MT5LiveAdapterDisabled
from src.services.trading.execution.mt5_live_adapter_pre_submit.gate import MT5PreSubmitGate
from src.services.trading.execution.mt5_live_adapter_pre_submit.idempotency import MT5PreSubmitIdempotencyGuard
from src.services.trading.execution.mt5_live_adapter_pre_submit.kill_switch import MT5KillSwitchService
from src.services.trading.execution.mt5_live_adapter_pre_submit.models import (
    MT5PreSubmitGateReport,
    MT5PreSubmitJournalRecord,
    MT5PreSubmitSummary,
    hash_text,
    now_utc_iso,
)
from src.services.trading.execution.mt5_live_adapter_pre_submit.policy import MT5LiveAdapterPreSubmitConfig
from src.services.trading.execution.mt5_live_adapter_pre_submit.store import MT5PreSubmitJournalStore
from src.services.trading.execution.mt5_live_adapter_pre_submit.validator import MT5LiveAdapterPreSubmitValidator


@dataclass
class MT5LiveAdapterPreSubmitServiceResult:
    report: MT5PreSubmitGateReport
    adapter_receipt: object
    bridge_check: object
    kill_switch_check: object
    idempotency_check: object
    journal_record: MT5PreSubmitJournalRecord | None
    summary: MT5PreSubmitSummary
    warning: str = ""


class MT5LiveAdapterPreSubmitService:
    def __init__(
        self,
        config: MT5LiveAdapterPreSubmitConfig | None = None,
        adapter: MT5LiveAdapterDisabled | None = None,
        store: MT5PreSubmitJournalStore | None = None,
        idempotency_guard: MT5PreSubmitIdempotencyGuard | None = None,
    ):
        self.config = config or MT5LiveAdapterPreSubmitConfig.from_config()
        self.adapter = adapter or MT5LiveAdapterDisabled(self.config)
        self.store = store or MT5PreSubmitJournalStore(self.config.journal_path, self.config.max_read_records)
        self.idempotency_guard = idempotency_guard or MT5PreSubmitIdempotencyGuard(self.config)
        self.kill_switch = MT5KillSwitchService(self.config)
        self.gate = MT5PreSubmitGate(self.config)
        self.validator = MT5LiveAdapterPreSubmitValidator()

    def run(self, final_validation, final_validation_report) -> MT5LiveAdapterPreSubmitServiceResult:
        bridge_result = self.adapter.check_bridge_write_skeleton()
        adapter_receipt = self.adapter.submit_disabled(bridge_result.check)
        kill_switch_check = self.kill_switch.check()
        idempotency_check = self.idempotency_guard.check(getattr(final_validation, "idempotency_key", ""))
        report = self.gate.evaluate(
            final_validation,
            final_validation_report,
            bridge_result.check,
            kill_switch_check,
            idempotency_check,
            adapter_receipt,
        )
        validation = self.validator.validate_report(report)
        warning = ""
        if not validation.passed:
            report.valid = False
            report.controlled_demo_integration_workflow_allowed = False
            warning = "mt5_pre_submit_validation_failed:" + ",".join(validation.issues)
        record = None
        if self.config.journal_enabled:
            record = self._build_record(report, adapter_receipt, final_validation)
            self.store.append(record)
        summary = self.store.summarize()
        return MT5LiveAdapterPreSubmitServiceResult(
            report=report,
            adapter_receipt=adapter_receipt,
            bridge_check=bridge_result.check,
            kill_switch_check=kill_switch_check,
            idempotency_check=idempotency_check,
            journal_record=record,
            summary=summary,
            warning=warning,
        )

    def _build_record(self, report, adapter_receipt, final_validation) -> MT5PreSubmitJournalRecord:
        created_at = now_utc_iso()
        payload_size = len(json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False))
        return MT5PreSubmitJournalRecord(
            journal_record_id="mt5_pre_submit_journal_" + hashlib.sha256(f"{report.report_id}:{created_at}".encode("utf-8")).hexdigest()[:16],
            created_at=created_at,
            event_type="MT5_PRE_SUBMIT_DISABLED_CHECK_PASSED" if report.valid else "MT5_PRE_SUBMIT_DISABLED_CHECK_BLOCKED",
            pre_submit_report_id=report.report_id,
            adapter_receipt_id=getattr(adapter_receipt, "receipt_id", ""),
            status=report.status,
            valid=report.valid,
            controlled_demo_integration_workflow_allowed=report.controlled_demo_integration_workflow_allowed,
            live_submission_allowed=False,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            order_sent=False,
            ticket=None,
            deal=None,
            hard_live_block_required=True,
            kill_switch_engaged=report.kill_switch_engaged,
            idempotency_status=report.idempotency_status,
            bridge_write_skeleton_reachable=report.bridge_write_skeleton_reachable,
            bridge_write_skeleton_status=report.bridge_write_skeleton_status,
            source_final_validation_id=report.source_final_validation_id,
            artifact_hash=getattr(final_validation, "artifact_hash", ""),
            idempotency_key_hash=hash_text(getattr(final_validation, "idempotency_key", "")),
            payload_size_chars=payload_size,
            metadata_redacted=True,
        )
