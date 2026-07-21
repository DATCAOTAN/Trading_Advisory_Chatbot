from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.mt5_skeleton_models import (
    LiveExecutionBlockJournalRecord,
    LiveExecutionBlockedReceipt,
    LiveExecutionCapabilityReport,
)


@dataclass
class HardLiveBlockValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class HardLiveBlockValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = int(max_payload_chars)

    def validate_report(self, report: LiveExecutionCapabilityReport) -> HardLiveBlockValidationResult:
        issues: list[str] = []
        payload = report.as_dict()
        if report.live_execution_supported is not False:
            issues.append("live_execution_supported_must_be_false")
        if report.live_execution_enabled is not False:
            issues.append("live_execution_enabled_must_be_false")
        if report.mt5_order_send_available is not False:
            issues.append("mt5_order_submission_available_must_be_false")
        if report.docker_side_mt5_import_allowed is not False:
            issues.append("docker_side_mt5_import_allowed_must_be_false")
        if report.hard_live_block_enabled is not True:
            issues.append("hard_live_block_enabled_must_be_true")
        if not report.source_refs:
            issues.append("source_refs_required")
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_size_issues(payload, self.max_payload_chars))
        return HardLiveBlockValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_receipt(self, receipt: LiveExecutionBlockedReceipt) -> HardLiveBlockValidationResult:
        issues: list[str] = []
        payload = receipt.as_dict()
        if not receipt.source_contract_id:
            issues.append("source_contract_id_required")
        if not receipt.source_simulated_receipt_id:
            issues.append("source_simulated_receipt_id_required")
        if not receipt.source_refs:
            issues.append("source_refs_required")
        if receipt.blocked is not True:
            issues.append("blocked_must_be_true")
        if receipt.executed is not False:
            issues.append("executed_must_be_false")
        if receipt.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if receipt.live_execution_supported is not False:
            issues.append("live_execution_supported_must_be_false")
        if receipt.hard_live_block_enabled is not True:
            issues.append("hard_live_block_enabled_must_be_true")
        issues.extend(_forbidden_payload_issues(payload))
        issues.extend(_payload_size_issues(payload, self.max_payload_chars))
        return HardLiveBlockValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_record(self, record: LiveExecutionBlockJournalRecord) -> HardLiveBlockValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        if not record.receipt_id:
            issues.append("receipt_id_required")
        if not record.source_contract_id:
            issues.append("source_contract_id_required")
        if not record.source_simulated_receipt_id:
            issues.append("source_simulated_receipt_id_required")
        if not record.source_refs:
            issues.append("source_refs_required")
        if record.blocked is not True:
            issues.append("blocked_must_be_true")
        if record.executed is not False:
            issues.append("executed_must_be_false")
        if record.order_sent is not False:
            issues.append("order_sent_must_be_false")
        if record.live_execution_supported is not False:
            issues.append("live_execution_supported_must_be_false")
        if record.hard_live_block_enabled is not True:
            issues.append("hard_live_block_enabled_must_be_true")
        issues.extend(_forbidden_payload_issues(payload))
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except Exception:
            issues.append("record_not_json_serializable")
            serialized = ""
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return HardLiveBlockValidationResult(not issues, list(dict.fromkeys(issues)))


def _payload_size_issues(payload: dict[str, Any], max_payload_chars: int) -> list[str]:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ["payload_not_json_serializable"]
    return ["payload_too_large"] if len(serialized) > max_payload_chars else []


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    fields = _flatten_keys(payload)
    lower_values = " ".join(_flatten_values(payload)).lower()
    if any(field in fields for field in {"buy", "sell"}):
        issues.append("buy_sell_marker_present")
    if any(field in fields for field in {"long", "short", "trade_side"}):
        issues.append("side_marker_present")
    if any(
        field in fields
        for field in {
            "entry",
            "entry_price",
            "stop_loss",
            "take_profit",
            "lot",
            "lot_size",
            "position_size",
            "account_risk",
        }
    ):
        issues.append("price_or_size_marker_present")
    if any(field in fields for field in {"order" + "_send", "real_order_id", "mt5_order_request", "executable_order"}):
        issues.append("order_marker_present")
    if any(field in fields for field in {"mt5_ticket", "deal_id"}):
        issues.append("mt5_ticket_marker_present")
    if any(field in fields for field in {"raw_candles", "ohlcv_bars"}):
        issues.append("raw_candle_marker_present")
    if any(field in fields for field in {"full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"}):
        issues.append("raw_knowledge_marker_present")
    if any(field in fields for field in {"account_id", "api_key", "password", "secret", "credentials"}):
        issues.append("account_or_credential_marker_present")
    value_markers = {
        "buy_sell_marker_present": [" buy ", " sell "],
        "side_marker_present": [" long ", " short ", "trade_side"],
        "price_or_size_marker_present": [
            "entry_price",
            "stop_loss",
            "take_profit",
            "lot_size",
            "position_size",
            "account_risk",
        ],
        "order_marker_present": [
            "order" + "_send",
            "real_order_id",
            "mt5_order_request",
            "executable_order",
            "submit_live_order",
            "send_order",
            "place_order",
            "execute_trade",
        ],
        "mt5_ticket_marker_present": ["mt5_ticket", "deal_id"],
        "raw_candle_marker_present": ["raw_candles", "ohlcv_bars"],
        "raw_knowledge_marker_present": ["full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"],
        "account_or_credential_marker_present": ["account_id", "api_key", "password", "secret", "credentials"],
        "metatrader_marker_present": ["meta" + "trader5"],
        "llm_prompt_marker_present": ["compact_prompt", "llm_prompt"],
    }
    padded_values = f" {lower_values} "
    for issue, markers in value_markers.items():
        if any(marker in padded_values for marker in markers):
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
