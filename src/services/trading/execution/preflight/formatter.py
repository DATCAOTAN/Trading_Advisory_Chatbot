from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.execution.preflight.models import LiveExecutionPreflightReadinessReport


@dataclass
class LiveExecutionPreflightCard:
    title: str
    status_label: str
    summary: str
    counts_section: Dict[str, Any] = field(default_factory=dict)
    blocker_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Preflight only. Live execution remains disabled. No live order is sent."
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "summary": self.summary,
            "counts_section": dict(self.counts_section),
            "blocker_section": dict(self.blocker_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


class LiveExecutionPreflightFormatter:
    def to_card(self, report: LiveExecutionPreflightReadinessReport) -> LiveExecutionPreflightCard:
        card = LiveExecutionPreflightCard(
            title="Live Execution Preflight Readiness Harness",
            status_label=report.preflight_status,
            summary="Machine-checkable preflight only; live_execution_allowed=false and hard_live_block_required=true.",
            counts_section={
                "total_checks": report.total_checks,
                "passed_checks": report.passed_checks,
                "failed_checks": report.failed_checks,
                "warning_checks": report.warning_checks,
                "blocking_failures": report.blocking_failures,
                "critical_failures": report.critical_failures,
                "readiness_score_preflight_completeness_only": report.readiness_score,
            },
            blocker_section={
                "blockers": list(report.blockers),
                "warnings": list(report.warnings),
            },
            source_section={
                "source_design_report_id": report.source_design_report_id,
                "source_capability_report_id": report.source_capability_report_id,
                "source_blocked_receipt_id": report.source_blocked_receipt_id,
                "source_refs_count": len(report.source_refs),
            },
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(self, report: LiveExecutionPreflightReadinessReport) -> str:
        lines = [
            "### Live Execution Preflight Readiness Harness",
            "",
            "Preflight only. Live execution remains disabled. No live order is sent.",
            "",
            f"- preflight_status: {report.preflight_status}",
            "- live_execution_allowed: false",
            "- hard_live_block_required: true",
            f"- total_checks: {report.total_checks}",
            f"- passed_checks: {report.passed_checks}",
            f"- failed_checks: {report.failed_checks}",
            f"- warning_checks: {report.warning_checks}",
            f"- blocking_failures: {report.blocking_failures}",
            f"- critical_failures: {report.critical_failures}",
            f"- readiness_score_preflight_completeness_only: {report.readiness_score:.2f}",
            f"- source_refs_count: {len(report.source_refs)}",
        ]
        return "\n".join(lines)
