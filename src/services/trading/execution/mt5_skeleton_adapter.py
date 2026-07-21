from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.adapter_models import ExecutionAdapterHealth
from src.services.trading.execution.adapter_models import SimulatedExecutionReceipt, SimulatedOrderContract
from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockedReceipt,
    LiveExecutionCapabilityReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_skeleton_policy import MT5ExecutionSkeletonPolicy
from src.services.trading.execution.mt5_skeleton_validator import HardLiveBlockValidationResult, HardLiveBlockValidator


class MT5ExecutionAdapterSkeleton:
    def __init__(
        self,
        policy: MT5ExecutionSkeletonPolicy | None = None,
        validator: HardLiveBlockValidator | None = None,
    ):
        self.policy = policy or MT5ExecutionSkeletonPolicy.from_config()
        self.validator = validator or HardLiveBlockValidator(self.policy.max_payload_chars)

    def adapter_type(self) -> str:
        return "RESERVED_MT5_LIVE"

    def health_check(self) -> ExecutionAdapterHealth:
        report = self.capability_report()
        return ExecutionAdapterHealth(
            adapter_type="RESERVED_MT5_LIVE",
            status="BLOCKED" if self.policy.hard_live_block_enabled else "DISABLED",
            message=report.message,
            live_execution_supported=False,
            simulated_only=True,
            details_redacted={
                "skeleton_status": report.skeleton_status,
                "live_execution_enabled": False,
                "hard_live_block_enabled": True,
            },
        )

    def capability_report(
        self,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
    ) -> LiveExecutionCapabilityReport:
        created_at = now_utc_iso()
        source_refs = _source_refs(contract, simulated_receipt)
        blockers = [
            "hard_live_block_enabled",
            "live_execution_disabled",
            "mt5_live_adapter_not_implemented",
            "order_submission_disabled",
        ]
        if contract is None and self.policy.require_simulated_contract:
            blockers.append("simulated_contract_required")
        if simulated_receipt is None and self.policy.require_simulated_receipt:
            blockers.append("simulated_receipt_required")
        if self.policy.require_source_refs and not source_refs:
            blockers.append("source_refs_required")
        report = LiveExecutionCapabilityReport(
            report_id=_stable_id("live_capability_report", created_at, getattr(contract, "contract_id", "")),
            created_at=created_at,
            skeleton_status="HARD_BLOCKED" if self.policy.hard_live_block_enabled else "DISABLED",
            live_execution_supported=False,
            live_execution_enabled=False,
            mt5_order_send_available=False,
            mt5_terminal_required=True,
            docker_side_mt5_import_allowed=False,
            hard_live_block_enabled=True,
            message="MT5 live execution skeleton is reserved and hard-blocked; no live order path exists.",
            blockers=blockers,
            warnings=["capability_check_only"],
            source_contract_id=getattr(contract, "contract_id", ""),
            source_simulated_receipt_id=getattr(simulated_receipt, "receipt_id", ""),
            source_draft_id=getattr(contract, "source_draft_id", ""),
            source_refs=source_refs,
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report

    def validate_live_block_inputs(
        self,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
    ) -> HardLiveBlockValidationResult:
        issues: list[str] = []
        if contract is None:
            issues.append("simulated_contract_required")
        else:
            if getattr(contract, "simulated_only", True) is not True:
                issues.append("contract_simulated_only_required")
            if getattr(contract, "executable", False) is not False:
                issues.append("contract_executable_must_be_false")
            if self.policy.require_source_refs and not getattr(contract, "source_refs", []):
                issues.append("contract_source_refs_required")
        if simulated_receipt is None:
            issues.append("simulated_receipt_required")
        else:
            if getattr(simulated_receipt, "simulated_only", True) is not True:
                issues.append("receipt_simulated_only_required")
            if getattr(simulated_receipt, "executable", False) is not False:
                issues.append("receipt_executable_must_be_false")
            if getattr(simulated_receipt, "executed", False) is not False:
                issues.append("receipt_executed_must_be_false")
        if self.policy.require_source_refs and not _source_refs(contract, simulated_receipt):
            issues.append("source_refs_required")
        return HardLiveBlockValidationResult(not issues, list(dict.fromkeys(issues)))

    def attempt_live_execution_blocked(
        self,
        contract: SimulatedOrderContract | None = None,
        simulated_receipt: SimulatedExecutionReceipt | None = None,
        simulated_journal_record=None,
    ) -> LiveExecutionBlockedReceipt:
        created_at = now_utc_iso()
        validation = self.validate_live_block_inputs(contract, simulated_receipt)
        blockers = [
            "hard_live_block_enabled",
            "live_execution_disabled",
            "mt5_live_adapter_not_implemented",
            "executable_artifact_forbidden",
        ]
        blockers.extend(validation.issues)
        receipt = LiveExecutionBlockedReceipt(
            receipt_id=_stable_id(
                "live_execution_blocked_receipt",
                created_at,
                getattr(contract, "contract_id", ""),
                getattr(simulated_receipt, "receipt_id", ""),
            ),
            created_at=created_at,
            skeleton_status="HARD_BLOCKED",
            blocked=True,
            executed=False,
            order_sent=False,
            live_execution_supported=False,
            hard_live_block_enabled=True,
            block_reason="HARD_LIVE_BLOCK_ENABLED" if validation.passed else "INVALID_SOURCE_CONTRACT",
            message="Live execution blocked by skeleton before any executable order path.",
            source_contract_id=getattr(contract, "contract_id", ""),
            source_simulated_receipt_id=getattr(simulated_receipt, "receipt_id", ""),
            source_simulated_journal_record_id=getattr(simulated_journal_record, "journal_record_id", ""),
            artifact_hash=getattr(contract, "artifact_hash", "") or getattr(simulated_receipt, "artifact_hash", ""),
            idempotency_key=getattr(contract, "idempotency_key", "") or getattr(simulated_receipt, "idempotency_key", ""),
            blockers=blockers,
            warnings=["mt5_execution_skeleton_only"],
            source_refs=_source_refs(contract, simulated_receipt),
        )
        receipt.payload_size_chars = len(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
        return receipt

    def close(self) -> None:
        return None


def _source_refs(contract, simulated_receipt) -> list[str]:
    refs: list[str] = []
    refs.extend(list(getattr(contract, "source_refs", []) or []))
    refs.extend(list(getattr(simulated_receipt, "source_refs", []) or []))
    return list(dict.fromkeys(refs))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
