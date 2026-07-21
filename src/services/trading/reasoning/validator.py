from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.reasoning.models import MethodSelectionResult


@dataclass
class MethodSelectionValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "issues": list(self.issues), "warnings": list(self.warnings)}


class MethodSelectionValidator:
    def validate(
        self,
        result: MethodSelectionResult,
        context_pack: RuntimeContextPack,
        user_selected_method_id: str | None = None,
    ) -> MethodSelectionValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        payload = result.as_dict()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        lower = encoded.lower()
        known_methods = {item.get("method_id") for item in context_pack.selected_method_cards}
        known_playbooks = {item.get("playbook_id") for item in context_pack.selected_playbooks}
        known_macros = {item.get("macro_id") for item in context_pack.selected_macro_cards}

        if result.primary_method_id and result.primary_method_id not in known_methods:
            issues.append("unknown_primary_method")
        for method_id in result.supporting_method_ids + result.rejected_method_ids:
            if method_id and method_id not in known_methods:
                issues.append(f"unknown_method:{method_id}")
        for playbook_id in result.selected_playbook_ids:
            if playbook_id and playbook_id not in known_playbooks:
                issues.append(f"unknown_playbook:{playbook_id}")
        for macro_id in result.relevant_macro_ids:
            if macro_id and macro_id not in known_macros:
                issues.append(f"unknown_macro:{macro_id}")
        if user_selected_method_id and result.primary_method_id != user_selected_method_id:
            issues.append("user_selected_method_not_preserved")
        if not result.source_refs:
            issues.append("source_refs_missing")
        if result.source_context_pack_id != context_pack.context_pack_id:
            issues.append("source_context_pack_id_mismatch")
        if not (0.0 <= result.confidence <= 1.0):
            issues.append("confidence_out_of_range")
        if not (0.0 <= result.overall_context_fit <= 1.0):
            issues.append("overall_context_fit_out_of_range")
        for assessment in result.candidate_assessments:
            if assessment.method_id and assessment.method_id not in known_methods:
                issues.append(f"unknown_assessment_method:{assessment.method_id}")
            if not (0.0 <= assessment.compatibility_score <= 1.0):
                issues.append(f"assessment_score_out_of_range:{assessment.method_id}")
        for forbidden in _forbidden_markers():
            if forbidden in lower:
                issues.append(f"forbidden_marker:{forbidden}")
        if any(key in lower for key in ["raw_book_text", "raw_report_text", "full_pdf_text", "raw_candles", "full_document_text"]):
            issues.append("raw_text_or_candles_present")
        if any(key in lower for key in ["api_key", "password", "secret", "account_id"]):
            issues.append("credential_or_account_marker_present")
        risk_state = context_pack.calendar_context_summary.get("calendar_risk_state")
        if risk_state in {"IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE"} and not result.blockers:
            issues.append("calendar_risk_blocker_missing")
        return MethodSelectionValidationResult(not issues, issues, warnings)


def contains_forbidden_output(text: str) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _forbidden_markers())


def _forbidden_markers() -> list[str]:
    return [
        "buy",
        "sell",
        "trade decision",
        "trade_decision",
        "entry",
        "stop loss",
        "stop-loss",
        "take profit",
        "take-profit",
        "lot",
        "account risk",
        "account-risk",
        "order" + "_send",
    ]
