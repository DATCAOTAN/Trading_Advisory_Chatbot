from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class MT5LiveAdapterPreSubmitValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


class MT5LiveAdapterPreSubmitValidator:
    def validate_report(self, report) -> MT5LiveAdapterPreSubmitValidationResult:
        issues: list[str] = []
        if not getattr(report, "source_final_validation_id", ""):
            issues.append("source_final_validation_required")
        if getattr(report, "valid", False) and not getattr(report, "controlled_demo_integration_workflow_allowed", False):
            issues.append("valid_report_must_allow_controlled_demo_workflow")
        for name in [
            "live_submission_allowed",
            "live_execution_allowed",
            "order_send_allowed",
            "execution_allowed",
            "executable",
            "order_sent",
        ]:
            if getattr(report, name, False) is not False:
                issues.append(f"{name}_must_be_false")
        if getattr(report, "ticket", None) is not None or getattr(report, "deal", None) is not None:
            issues.append("ticket_deal_must_be_null")
        if getattr(report, "hard_live_block_required", False) is not True:
            issues.append("hard_live_block_required_must_be_true")
        text = json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False)
        issues.extend(_forbidden_call_issues(text))
        return MT5LiveAdapterPreSubmitValidationResult(not issues, list(dict.fromkeys(issues)))

    def validate_payload_text(self, text: str) -> MT5LiveAdapterPreSubmitValidationResult:
        issues = _forbidden_call_issues(text)
        return MT5LiveAdapterPreSubmitValidationResult(not issues, issues)


def _forbidden_call_issues(text: str) -> list[str]:
    lowered = text.lower()
    patterns = [
        "." + "order_" + "send(",
        "metatrader5." + "order_" + "send(",
        "mt5." + "order_" + "send(",
        "order_" + "send(",
    ]
    return [f"forbidden_execution_call:{pattern}" for pattern in patterns if pattern in lowered]
