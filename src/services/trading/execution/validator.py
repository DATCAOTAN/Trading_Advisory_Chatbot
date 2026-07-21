from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.models import DryRunExecutionReceipt, ExecutionGateDecision


@dataclass
class ExecutionGateValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExecutionGateValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = max_payload_chars

    def validate_decision(self, decision: ExecutionGateDecision) -> ExecutionGateValidationResult:
        issues: list[str] = []
        data = decision.as_dict()
        if not data.get("source_review_artifact_id"):
            issues.append("missing_source_review_artifact_id")
        if not data.get("source_readiness_decision_id"):
            issues.append("missing_source_readiness_decision_id")
        if not data.get("source_refs"):
            issues.append("missing_source_refs")
        if not data.get("dry_run_only"):
            issues.append("dry_run_only_must_be_true")
        if int(data.get("payload_size_chars") or 0) > self.max_payload_chars:
            issues.append("payload_size_exceeds_limit")
        issues.extend(_payload_issues(data))
        return ExecutionGateValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))

    def validate_receipt(self, receipt: DryRunExecutionReceipt) -> ExecutionGateValidationResult:
        issues: list[str] = []
        data = receipt.as_dict()
        if not data.get("source_gate_decision_id"):
            issues.append("missing_source_gate_decision_id")
        if not data.get("source_review_artifact_id"):
            issues.append("missing_source_review_artifact_id")
        if not data.get("source_refs"):
            issues.append("missing_source_refs")
        if not data.get("dry_run_only"):
            issues.append("dry_run_only_must_be_true")
        if data.get("executed"):
            issues.append("executed_must_be_false")
        if int(data.get("payload_size_chars") or 0) > self.max_payload_chars:
            issues.append("payload_size_exceeds_limit")
        issues.extend(_payload_issues(data))
        return ExecutionGateValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))


def _payload_issues(data: dict[str, Any]) -> list[str]:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).lower()
    issues: list[str] = []
    for marker in _forbidden_markers():
        if marker in payload:
            issues.append(f"forbidden_marker:{marker}")
    for marker in _raw_content_markers():
        if marker in payload:
            issues.append(f"raw_content_marker:{marker}")
    for marker in _sensitive_markers():
        if marker in payload:
            issues.append(f"sensitive_marker:{marker}")
    return issues


def _forbidden_markers() -> list[str]:
    return [
        "buy",
        "sell",
        "entry_price",
        "entry price",
        "stop_loss",
        "stop loss",
        "take_profit",
        "take profit",
        "lot_size",
        "lot size",
        "account_risk",
        "account risk",
        "real_order_id",
        "mt5_order_request",
        "executable_order",
        "order" + "_send",
    ]


def _raw_content_markers() -> list[str]:
    return ["raw_candles", "raw_ohlcv", "full_raw_book", "full_raw_report", "raw_book_text", "raw_report_text"]


def _sensitive_markers() -> list[str]:
    return ["api_key", "password", "secret", "credential", "account_id", "login", "metatrader5", "compact_prompt"]
