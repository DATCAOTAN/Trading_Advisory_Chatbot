from __future__ import annotations

from dataclasses import dataclass, field

from src.services.trading.execution.mt5_bridge_write_skeleton.models import MT5BridgeWriteSkeletonCheckResult


@dataclass
class MT5BridgeWriteSkeletonValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5BridgeWriteSkeletonValidator:
    def validate(self, result: MT5BridgeWriteSkeletonCheckResult) -> MT5BridgeWriteSkeletonValidationResult:
        issues: list[str] = []
        if result.reachable is not True:
            issues.append("reachable_required")
        if result.status != "BLOCKED":
            issues.append("status_must_be_blocked")
        if result.write_skeleton_available is not True:
            issues.append("write_skeleton_available_required")
        if result.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if result.order_send_allowed is not False:
            issues.append("order_send_allowed_must_be_false")
        if result.execution_allowed is not False:
            issues.append("execution_allowed_must_be_false")
        if result.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if result.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if result.ticket is not None:
            issues.append("ticket_must_be_null")
        if result.deal is not None:
            issues.append("deal_must_be_null")
        if result.metadata_redacted is not True:
            issues.append("metadata_redacted_required")
        return MT5BridgeWriteSkeletonValidationResult(not issues, issues)
