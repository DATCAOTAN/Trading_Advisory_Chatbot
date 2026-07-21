from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.decision.models import TRADE_READINESS_ACTIONS, TradeReadinessDecision


@dataclass
class TradeReadinessDecisionValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TradeReadinessDecisionValidator:
    def validate(self, decision: TradeReadinessDecision) -> TradeReadinessDecisionValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        data = decision.as_dict()

        if data.get("action") not in TRADE_READINESS_ACTIONS:
            issues.append("invalid_action")
        for field_name in (
            "source_score_report_id",
            "source_feature_snapshot_id",
            "source_calendar_context_id",
            "source_regime_snapshot_id",
            "source_context_pack_id",
            "source_method_selection_id",
        ):
            if not str(data.get(field_name) or "").strip():
                issues.append(f"missing_{field_name}")
        if not data.get("source_refs"):
            issues.append("missing_source_refs")
        if not _in_unit_interval(data.get("readiness_score")):
            issues.append("readiness_score_out_of_range")
        if not _in_unit_interval(data.get("confidence")):
            issues.append("confidence_out_of_range")

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
        return TradeReadinessDecisionValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)), warnings=warnings)


def _in_unit_interval(value: Any) -> bool:
    try:
        number = float(value)
        return number == number and 0.0 <= number <= 1.0
    except Exception:
        return False


def _forbidden_markers() -> list[str]:
    return [
        "buy",
        "sell",
        "trade_side",
        "execution_intent",
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
        "executable_order",
        "order" + "_send",
    ]


def _raw_content_markers() -> list[str]:
    return [
        "raw_candles",
        "raw_ohlcv",
        "full_raw_book",
        "full_raw_report",
        "raw_book_text",
        "raw_report_text",
        "full_document_text",
        "full_pdf_text",
    ]


def _sensitive_markers() -> list[str]:
    return [
        "api_key",
        "password",
        "secret",
        "credential",
        "account_id",
        "login",
        "metatrader5",
        "llm_reasoning_request",
        "compact_prompt",
    ]
