from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


PROPOSAL_DRAFT_STATUSES = {
    "DRAFT_CREATED",
    "BLOCKED",
    "WAITING",
    "EXPIRED",
    "INVALID",
    "DUPLICATE",
    "UNKNOWN",
}


@dataclass
class ProposalDraftSection:
    section_id: str
    title: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "summary": self.summary,
            "details": dict(self.details),
            "warnings": _dedupe(self.warnings),
            "blockers": _dedupe(self.blockers),
            "source_refs": list(dict.fromkeys(self.source_refs)),
        }


@dataclass
class NonExecutableTradeProposalDraft:
    draft_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    status: str = "UNKNOWN"
    non_executable: bool = True
    executable: bool = False
    proposal_workflow_allowed: bool = False
    source_intent_id: str = ""
    source_review_artifact_id: str = ""
    source_score_report_id: str = ""
    source_method_selection_id: str = ""
    source_context_pack_id: str = ""
    source_calendar_context_id: str = ""
    source_regime_snapshot_id: str = ""
    primary_method_id: str = ""
    supporting_method_ids: List[str] = field(default_factory=list)
    selected_playbook_ids: List[str] = field(default_factory=list)
    primary_regime: str = "UNKNOWN"
    calendar_risk_state: str = "UNKNOWN"
    readiness_action: str = "UNKNOWN"
    review_status: str = "UNKNOWN"
    final_context_score: float = 0.0
    grade: str = "UNKNOWN"
    method_thesis_summary: str = ""
    market_context_summary: str = ""
    calendar_context_summary: str = ""
    risk_context_summary: str = ""
    score_summary: Dict[str, Any] = field(default_factory=dict)
    required_human_checks: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sections: List[ProposalDraftSection] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in PROPOSAL_DRAFT_STATUSES else "UNKNOWN",
            "non_executable": True,
            "executable": False,
            "proposal_workflow_allowed": bool(self.proposal_workflow_allowed),
            "source_intent_id": self.source_intent_id,
            "source_review_artifact_id": self.source_review_artifact_id,
            "source_score_report_id": self.source_score_report_id,
            "source_method_selection_id": self.source_method_selection_id,
            "source_context_pack_id": self.source_context_pack_id,
            "source_calendar_context_id": self.source_calendar_context_id,
            "source_regime_snapshot_id": self.source_regime_snapshot_id,
            "primary_method_id": self.primary_method_id,
            "supporting_method_ids": list(dict.fromkeys(self.supporting_method_ids)),
            "selected_playbook_ids": list(dict.fromkeys(self.selected_playbook_ids)),
            "primary_regime": self.primary_regime,
            "calendar_risk_state": self.calendar_risk_state,
            "readiness_action": self.readiness_action,
            "review_status": self.review_status,
            "final_context_score": _clamp(self.final_context_score),
            "grade": self.grade,
            "method_thesis_summary": self.method_thesis_summary,
            "market_context_summary": self.market_context_summary,
            "calendar_context_summary": self.calendar_context_summary,
            "risk_context_summary": self.risk_context_summary,
            "score_summary": dict(self.score_summary),
            "required_human_checks": list(dict.fromkeys(self.required_human_checks)),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "sections": [section.as_dict() for section in self.sections],
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ProposalDraftCard:
    title: str
    status_label: str
    non_executable_label: str
    summary: str
    method_section: Dict[str, Any] = field(default_factory=dict)
    market_section: Dict[str, Any] = field(default_factory=dict)
    calendar_section: Dict[str, Any] = field(default_factory=dict)
    score_section: Dict[str, Any] = field(default_factory=dict)
    risk_section: Dict[str, Any] = field(default_factory=dict)
    human_checks_section: Dict[str, Any] = field(default_factory=dict)
    blockers_section: Dict[str, Any] = field(default_factory=dict)
    source_section: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Non-executable proposal draft. No live order is sent."
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "status_label": self.status_label,
            "non_executable_label": self.non_executable_label,
            "summary": self.summary,
            "method_section": dict(self.method_section),
            "market_section": dict(self.market_section),
            "calendar_section": dict(self.calendar_section),
            "score_section": dict(self.score_section),
            "risk_section": dict(self.risk_section),
            "human_checks_section": dict(self.human_checks_section),
            "blockers_section": dict(self.blockers_section),
            "source_section": dict(self.source_section),
            "disclaimer": self.disclaimer,
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class ProposalDraftJournalRecord:
    journal_record_id: str
    created_at: str
    draft_id: str
    status: str
    non_executable: bool
    executable: bool
    source_intent_id: str
    artifact_hash: str
    primary_method_id: str
    primary_regime: str
    calendar_risk_state: str
    readiness_action: str
    final_context_score: float
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "draft_id": self.draft_id,
            "status": self.status if self.status in PROPOSAL_DRAFT_STATUSES else "UNKNOWN",
            "non_executable": True,
            "executable": False,
            "source_intent_id": self.source_intent_id,
            "artifact_hash": self.artifact_hash,
            "primary_method_id": self.primary_method_id,
            "primary_regime": self.primary_regime,
            "calendar_risk_state": self.calendar_risk_state,
            "readiness_action": self.readiness_action,
            "final_context_score": _clamp(self.final_context_score),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class ProposalDraftSummary:
    total_records: int = 0
    total_created: int = 0
    total_blocked: int = 0
    total_waiting: int = 0
    latest_record_at: str = ""
    latest_draft_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_created": int(self.total_created),
            "total_blocked": int(self.total_blocked),
            "total_waiting": int(self.total_waiting),
            "latest_record_at": self.latest_record_at,
            "latest_draft_id": self.latest_draft_id,
            "latest_status": self.latest_status,
            "warnings": list(dict.fromkeys(self.warnings)),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0


def _dedupe(items: List[Any]) -> List[Any]:
    result: List[Any] = []
    seen: set[str] = set()
    for item in items:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result
