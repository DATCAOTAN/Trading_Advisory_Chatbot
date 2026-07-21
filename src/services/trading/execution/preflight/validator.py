from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.preflight.models import (
    LiveExecutionPreflightReadinessReport,
    PreflightJournalRecord,
)
from src.services.trading.execution.preflight.policy import LiveExecutionPreflightPolicy


@dataclass
class LiveExecutionPreflightValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class LiveExecutionPreflightValidator:
    def __init__(self, policy: LiveExecutionPreflightPolicy | None = None):
        self.policy = policy or LiveExecutionPreflightPolicy.from_config()

    def validate_report(self, report: LiveExecutionPreflightReadinessReport) -> LiveExecutionPreflightValidationResult:
        issues: list[str] = []
        payload = report.as_dict()
        if not report.source_design_report_id:
            issues.append("source_design_report_id_required")
        if not report.source_capability_report_id:
            issues.append("source_capability_report_id_required")
        if not report.source_blocked_receipt_id:
            issues.append("source_blocked_receipt_id_required")
        if not report.source_refs:
            issues.append("source_refs_required")
        if report.live_execution_allowed is not False:
            issues.append("live_execution_allowed_must_be_false")
        if report.hard_live_block_required is not True:
            issues.append("hard_live_block_required_must_be_true")
        if not report.check_results:
            issues.append("check_results_required")
        if report.total_checks < 40:
            issues.append("preflight_check_count_below_minimum")
        if report.blocking_failures and not report.blockers:
            issues.append("blocking_failures_not_surfaced")
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_issues(payload, self.policy.max_payload_chars))
        return LiveExecutionPreflightValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: PreflightJournalRecord) -> LiveExecutionPreflightValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        if not record.report_id:
            issues.append("report_id_required")
        if not record.source_design_report_id:
            issues.append("source_design_report_id_required")
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
        return LiveExecutionPreflightValidationResult(not issues, list(dict.fromkeys(issues)))


def _payload_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ["payload_not_json_serializable"]
    return ["payload_too_large"] if len(serialized) > max_payload_chars else []


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    fields = _flatten_keys(payload)
    values = " ".join(_flatten_values(payload)).lower()
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
    value_patterns = {
        "order_submission_marker_present": [r"\border" + r"_send\b"],
        "live_method_marker_present": [r"\bsubmit_live_order\b", r"\bsend_order\b", r"\bplace_order\b", r"\bexecute_trade\b"],
        "executable_order_marker_present": [r"\breal_order_id\b", r"\bmt5_order_request\b", r"\bexecutable_order\b"],
        "mt5_ticket_marker_present": [r"\bmt5_ticket\b", r"\bdeal_id\b"],
        "trade_side_marker_present": [r"\btrade_side\b"],
        "direction_marker_present": [r"\bbuy\b", r"\bsell\b", r"\blong\b", r"\bshort\b"],
        "price_or_size_marker_present": [
            r"\bentry\b",
            r"\bentry_price\b",
            r"\bstop_loss\b",
            r"\btake_profit\b",
            r"\blot\b",
            r"\bposition_size\b",
            r"\baccount_risk\b",
        ],
        "raw_candle_marker_present": [r"\braw_candles\b", r"\braw_ohlcv\b", r"\bohlcv_bars\b"],
        "raw_knowledge_marker_present": [r"\bfull_raw_book\b", r"\bfull_raw_report\b", r"\braw_full_book\b", r"\braw_full_report\b"],
        "account_or_credential_marker_present": [r"\baccount_id\b", r"\bapi_key\b", r"\bpassword\b", r"\bsecret\b", r"\bcredentials\b"],
        "metatrader_marker_present": [r"\bmeta" + r"trader5\b"],
        "llm_prompt_marker_present": [r"\bcompact_prompt\b", r"\bllm_prompt\b"],
    }
    for issue, patterns in value_patterns.items():
        if any(re.search(pattern, values) for pattern in patterns):
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
