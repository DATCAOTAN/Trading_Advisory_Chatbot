from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.live_design.policy import LiveExecutionDesignPolicy
from src.services.trading.execution.live_design.readiness_models import (
    LiveExecutionDesignReportRecord,
    LiveExecutionReadinessSpecReport,
)


@dataclass
class LiveExecutionDesignSpecValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class LiveExecutionDesignSpecValidator:
    def __init__(self, policy: LiveExecutionDesignPolicy | None = None):
        self.policy = policy or LiveExecutionDesignPolicy.from_config()

    def validate_report(self, report: LiveExecutionReadinessSpecReport) -> LiveExecutionDesignSpecValidationResult:
        issues: list[str] = []
        payload = report.as_dict()
        if not report.source_capability_report_id:
            issues.append("source_capability_report_id_required")
        if not report.source_blocked_receipt_id:
            issues.append("source_blocked_receipt_id_required")
        if not report.source_contract_id:
            issues.append("source_contract_id_required")
        if not report.source_refs:
            issues.append("source_refs_required")
        if report.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if report.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        critical_or_high = sum(1 for item in report.threats if item.severity in {"CRITICAL", "HIGH"})
        critical_count = sum(1 for item in report.threats if item.severity == "CRITICAL")
        if len(report.threats) < self.policy.min_critical_threats:
            issues.append("threat_count_below_minimum")
        if critical_count < self.policy.min_critical_threats:
            issues.append("critical_threat_count_below_minimum")
        if critical_or_high < self.policy.min_critical_threats:
            issues.append("critical_or_high_threat_count_below_minimum")
        if len(report.preflight_checks) < self.policy.min_preflight_checks:
            issues.append("preflight_check_count_below_minimum")
        if len(report.approval_requirements) < self.policy.min_approval_requirements:
            issues.append("approval_requirement_count_below_minimum")
        if len(report.failure_modes) < self.policy.min_failure_modes:
            issues.append("failure_mode_count_below_minimum")
        if len(report.audit_requirements) < self.policy.min_audit_requirements:
            issues.append("audit_requirement_count_below_minimum")
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.policy.max_payload_chars))
        return LiveExecutionDesignSpecValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: LiveExecutionDesignReportRecord) -> LiveExecutionDesignSpecValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        if not record.report_id:
            issues.append("report_id_required")
        if not record.source_capability_report_id:
            issues.append("source_capability_report_id_required")
        if not record.source_blocked_receipt_id:
            issues.append("source_blocked_receipt_id_required")
        if not record.source_refs:
            issues.append("source_refs_required")
        if record.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if record.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.policy.max_payload_chars))
        return LiveExecutionDesignSpecValidationResult(not issues, list(dict.fromkeys(issues)))


def _payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ["payload_not_json_serializable"]
    return ["payload_too_large"] if len(serialized) > max_payload_chars else []


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    fields = _flatten_keys(payload)
    values = f" {' '.join(_flatten_values(payload)).lower()} "
    issues: list[str] = []
    field_markers = {
        "order_submission_marker_present": {"order" + "_send"},
        "live_method_marker_present": {"submit_live_order", "send_order", "place_order", "execute_trade"},
        "executable_order_marker_present": {"real_order_id", "mt5_order_request", "executable_order"},
        "mt5_ticket_marker_present": {"mt5_ticket", "deal_id"},
        "trade_side_marker_present": {"trade_side"},
        "price_or_size_marker_present": {
            "entry",
            "entry_price",
            "stop_loss",
            "take_profit",
            "lot",
            "position_size",
            "account_risk",
        },
        "raw_candle_marker_present": {"raw_candles", "raw_ohlcv", "ohlcv_bars"},
        "raw_knowledge_marker_present": {"full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"},
        "account_or_credential_marker_present": {"account_id", "api_key", "password", "secret", "credentials"},
    }
    for issue, markers in field_markers.items():
        if fields.intersection(markers):
            issues.append(issue)
    value_markers = {
        "order_submission_marker_present": ["order" + "_send"],
        "live_method_marker_present": ["submit_live_order", "send_order", "place_order", "execute_trade"],
        "executable_order_marker_present": ["real_order_id", "mt5_order_request", "executable_order"],
        "mt5_ticket_marker_present": ["mt5_ticket", "deal_id"],
        "trade_side_marker_present": ["trade_side"],
        "price_or_size_marker_present": [
            "entry_price",
            "stop_loss",
            "take_profit",
            "position_size",
            "account_risk",
        ],
        "raw_candle_marker_present": ["raw_candles", "raw_ohlcv", "ohlcv_bars"],
        "raw_knowledge_marker_present": ["full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"],
        "account_or_credential_marker_present": ["account_id", "api_key", "password", "secret", "credentials"],
        "metatrader_marker_present": ["meta" + "trader5"],
        "llm_prompt_marker_present": ["compact_prompt", "llm_prompt"],
    }
    for issue, markers in value_markers.items():
        if any(marker in values for marker in markers):
            issues.append(issue)
    return list(dict.fromkeys(issues))


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_flatten_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_flatten_keys(item))
    return keys


def _flatten_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_flatten_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_flatten_values(item))
    elif isinstance(value, str):
        values.append(value)
    return values
