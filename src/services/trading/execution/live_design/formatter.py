from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict

from src.services.trading.execution.live_design.readiness_models import LiveExecutionReadinessSpecReport


@dataclass
class LiveExecutionDesignSpecCard:
    title: str
    status_label: str
    summary: str
    counts_section: Dict[str, Any] = field(default_factory=dict)
    blocker_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Design spec only. Live execution remains disabled. No live order is sent."
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


class LiveExecutionDesignSpecFormatter:
    def to_card(self, report: LiveExecutionReadinessSpecReport) -> LiveExecutionDesignSpecCard:
        critical_or_high = sum(1 for item in report.threats if item.severity in {"CRITICAL", "HIGH"})
        card = LiveExecutionDesignSpecCard(
            title="Live Execution Design Spec & Threat Model",
            status_label=report.design_status,
            summary=(
                "Machine-checkable design artifact only; live_execution_allowed=false and "
                "hard_live_block_required=true."
            ),
            counts_section={
                "threats_count": len(report.threats),
                "critical_or_high_threats_count": critical_or_high,
                "preflight_checks_count": len(report.preflight_checks),
                "approval_requirements_count": len(report.approval_requirements),
                "failure_modes_count": len(report.failure_modes),
                "audit_requirements_count": len(report.audit_requirements),
                "readiness_score_design_completeness_only": report.readiness_score,
            },
            blocker_section={
                "blockers": list(report.blockers),
                "warnings": list(report.warnings),
            },
            source_section={
                "source_capability_report_id": report.source_capability_report_id,
                "source_blocked_receipt_id": report.source_blocked_receipt_id,
                "source_contract_id": report.source_contract_id,
                "source_refs_count": len(report.source_refs),
            },
        )
        card.payload_size_chars = len(json.dumps(card.as_dict(), ensure_ascii=False, sort_keys=True))
        return card

    def to_markdown(self, report: LiveExecutionReadinessSpecReport) -> str:
        critical_or_high = sum(1 for item in report.threats if item.severity in {"CRITICAL", "HIGH"})
        lines = [
            "### Live Execution Design Spec & Threat Model",
            "",
            "Design spec only. Live execution remains disabled. No live order is sent.",
            "",
            f"- design_status: {report.design_status}",
            "- live_execution_allowed: false",
            "- hard_live_block_required: true",
            f"- threats_count: {len(report.threats)}",
            f"- critical_or_high_threats_count: {critical_or_high}",
            f"- preflight_checks_count: {len(report.preflight_checks)}",
            f"- approval_requirements_count: {len(report.approval_requirements)}",
            f"- failure_modes_count: {len(report.failure_modes)}",
            f"- audit_requirements_count: {len(report.audit_requirements)}",
            f"- readiness_score_design_completeness_only: {report.readiness_score:.2f}",
            f"- blockers_count: {len(report.blockers)}",
            f"- warnings_count: {len(report.warnings)}",
            f"- source_refs_count: {len(report.source_refs)}",
        ]
        return "\n".join(lines)
