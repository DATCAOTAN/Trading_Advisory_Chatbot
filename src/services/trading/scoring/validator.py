from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.scoring.models import COMPONENT_NAMES, SCORE_GRADES, SignalScoreReport


@dataclass
class SignalScoreValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SignalScoreValidator:
    def validate(self, report: SignalScoreReport) -> SignalScoreValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        data = report.as_dict()

        for field_name in (
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

        components = data.get("components") or {}
        weights = []
        for name in COMPONENT_NAMES:
            component = components.get(name)
            if not component:
                issues.append(f"missing_component:{name}")
                continue
            if component.get("name") != name:
                issues.append(f"component_name_mismatch:{name}")
            for numeric_field in ("score", "weight", "weighted_score"):
                if not _in_unit_interval(component.get(numeric_field)):
                    issues.append(f"{name}_{numeric_field}_out_of_range")
            weights.append(float(component.get("weight") or 0.0))
            if component.get("grade") not in SCORE_GRADES:
                warnings.append(f"{name}_unknown_grade")

        if weights and abs(sum(weights) - 1.0) > 0.001:
            issues.append("component_weights_not_normalized")
        if not _in_unit_interval(data.get("final_context_score")):
            issues.append("final_context_score_out_of_range")
        if data.get("grade") not in SCORE_GRADES:
            warnings.append("unknown_report_grade")

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

        return SignalScoreValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)), warnings=warnings)


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
        "trade_decision",
        "trade decision",
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
