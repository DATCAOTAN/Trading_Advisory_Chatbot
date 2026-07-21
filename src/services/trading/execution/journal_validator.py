from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.services.trading.execution.journal_models import ExecutionJournalRecord


@dataclass
class ExecutionJournalValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExecutionJournalValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = max_payload_chars

    def validate(self, record: ExecutionJournalRecord) -> ExecutionJournalValidationResult:
        issues: list[str] = []
        data = record.as_dict()
        for field_name in ("journal_record_id", "artifact_id", "artifact_hash", "gate_decision_id", "receipt_id"):
            if not str(data.get(field_name) or "").strip():
                issues.append(f"missing_{field_name}")
        if not data.get("source_refs"):
            issues.append("missing_source_refs")
        if not data.get("dry_run_only"):
            issues.append("dry_run_only_must_be_true")
        if data.get("executed"):
            issues.append("executed_must_be_false")
        if int(data.get("payload_size_chars") or 0) > self.max_payload_chars:
            issues.append("payload_size_exceeds_limit")
        try:
            json.dumps(data, ensure_ascii=False, sort_keys=True)
        except Exception:
            issues.append("json_serialization_failed")
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True).lower()
        for marker in _forbidden_markers():
            if marker in payload:
                issues.append(f"forbidden_marker:{marker}")
        for marker in _raw_content_markers():
            if marker in payload:
                issues.append(f"raw_content_marker:{marker}")
        for marker in _sensitive_markers():
            if marker in payload:
                issues.append(f"sensitive_marker:{marker}")
        return ExecutionJournalValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)))


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
