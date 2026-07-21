from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.execution.adapter_models import (
    SimulatedExecutionJournalRecord,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
)


@dataclass
class ExecutionAdapterValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class ExecutionAdapterContractValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = int(max_payload_chars)

    def validate_contract(self, contract: SimulatedOrderContract) -> ExecutionAdapterValidationResult:
        issues: list[str] = []
        payload = contract.as_dict()
        for key in ["source_draft_id", "source_intent_id"]:
            if not getattr(contract, key):
                issues.append(f"{key}_required")
        if not contract.source_refs:
            issues.append("source_refs_required")
        if contract.simulated_only is not True:
            issues.append("simulated_only_must_be_true")
        if contract.executable is not False:
            issues.append("executable_must_be_false")
        if contract.adapter_type != "SIMULATED":
            issues.append("adapter_type_must_be_simulated")
        issues.extend(_forbidden_payload_issues(payload))
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return ExecutionAdapterValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))

    def validate_receipt(self, receipt: SimulatedExecutionReceipt) -> ExecutionAdapterValidationResult:
        issues: list[str] = []
        payload = receipt.as_dict()
        if not receipt.contract_id:
            issues.append("contract_id_required")
        if receipt.simulated_only is not True:
            issues.append("simulated_only_must_be_true")
        if receipt.executable is not False:
            issues.append("executable_must_be_false")
        if receipt.executed is not False:
            issues.append("executed_must_be_false")
        if receipt.adapter_type != "SIMULATED":
            issues.append("adapter_type_must_be_simulated")
        issues.extend(_forbidden_payload_issues(payload))
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return ExecutionAdapterValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))

    def validate_record(self, record: SimulatedExecutionJournalRecord) -> ExecutionAdapterValidationResult:
        issues: list[str] = []
        payload = record.as_dict()
        if not record.contract_id:
            issues.append("contract_id_required")
        if not record.receipt_id:
            issues.append("receipt_id_required")
        if not record.source_refs:
            issues.append("source_refs_required")
        if record.simulated_only is not True:
            issues.append("simulated_only_must_be_true")
        if record.executable is not False:
            issues.append("executable_must_be_false")
        if record.executed is not False:
            issues.append("executed_must_be_false")
        issues.extend(_forbidden_payload_issues(payload))
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except Exception:
            issues.append("record_not_json_serializable")
            serialized = ""
        if len(serialized) > self.max_payload_chars:
            issues.append("payload_too_large")
        return ExecutionAdapterValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))


def _forbidden_payload_issues(payload: dict[str, Any]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    checks = {
        "buy_marker_present": ["buy"],
        "sell_marker_present": ["sell"],
        "side_marker_present": ["long", "short", "trade_side"],
        "price_or_size_marker_present": [
            "entry_price",
            "stop_loss",
            "take_profit",
            "lot_size",
            "position_size",
            "account_risk",
        ],
        "order_submission_marker_present": ["order" + "_send"],
        "executable_order_marker_present": ["real_order_id", "mt5_order_request", "executable_order"],
        "mt5_ticket_marker_present": ["mt5_ticket", "deal_id"],
        "raw_candle_marker_present": ["raw_candles", "ohlcv_bars"],
        "raw_knowledge_marker_present": ["full_raw_book", "full_raw_report", "raw_full_book", "raw_full_report"],
        "account_or_credential_marker_present": ["account_id", "api_key", "password", "secret"],
        "metatrader_marker_present": ["meta" + "trader5"],
        "llm_prompt_marker_present": ["compact_prompt", "llm_prompt"],
    }
    issues: list[str] = []
    for issue, markers in checks.items():
        if any(marker in text for marker in markers):
            issues.append(issue)
    return issues
