from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.services.trading.review.models import HumanReviewArtifact, REVIEW_STATUSES


@dataclass
class HumanReviewArtifactValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class HumanReviewArtifactValidator:
    def __init__(self, max_payload_chars: int = 12000):
        self.max_payload_chars = max_payload_chars

    def validate(self, artifact: HumanReviewArtifact) -> HumanReviewArtifactValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        data = artifact.as_dict()

        if data.get("review_status") not in REVIEW_STATUSES:
            issues.append("invalid_review_status")
        expected_status = expected_review_status(data.get("readiness_action", ""))
        if expected_status != "UNKNOWN" and data.get("review_status") != expected_status:
            issues.append("review_status_action_mismatch")
        for field_name in (
            "source_readiness_decision_id",
            "source_score_report_id",
            "source_method_selection_id",
            "source_context_pack_id",
        ):
            if not str(data.get(field_name) or "").strip():
                issues.append(f"missing_{field_name}")
        if not data.get("source_refs"):
            issues.append("missing_source_refs")
        if int(data.get("payload_size_chars") or 0) > self.max_payload_chars:
            issues.append("payload_size_exceeds_limit")

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
        return HumanReviewArtifactValidationResult(passed=not issues, issues=list(dict.fromkeys(issues)), warnings=warnings)


def expected_review_status(action: str) -> str:
    return {
        "REVIEW_READY": "READY_FOR_REVIEW",
        "WAIT": "WAITING",
        "NO_TRADE": "NO_TRADE_CONTEXT",
        "BLOCKED": "BLOCKED",
        "MANAGE_EXISTING_POSITION": "MANAGE_EXISTING_POSITION",
    }.get(str(action or ""), "UNKNOWN")


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
        "executable_order",
        "mt5_order_request",
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
        "compact_prompt",
    ]
