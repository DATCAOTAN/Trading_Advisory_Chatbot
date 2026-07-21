from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


ASSESSMENT_ROLES = {"PRIMARY_CANDIDATE", "SUPPORTING_CONFIRMATION", "REJECTED", "RISK_ONLY"}
PARSE_STATUSES = {"OK", "PARTIAL", "FAILED"}


@dataclass
class MethodCandidateAssessment:
    method_id: str
    method_name: str = ""
    role: str = "REJECTED"
    compatibility_score: float = 0.0
    regime_fit: str = ""
    feature_fit: str = ""
    calendar_fit: str = ""
    macro_fit: str = ""
    risk_fit: str = ""
    reasons: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "method_id": self.method_id,
            "method_name": self.method_name,
            "role": self.role,
            "compatibility_score": _clamp(self.compatibility_score),
            "regime_fit": self.regime_fit,
            "feature_fit": self.feature_fit,
            "calendar_fit": self.calendar_fit,
            "macro_fit": self.macro_fit,
            "risk_fit": self.risk_fit,
            "reasons": list(self.reasons),
            "conflicts": list(self.conflicts),
            "source_refs": list(dict.fromkeys(self.source_refs)),
        }


@dataclass
class MethodSelectionResult:
    result_id: str
    created_at: str
    mode: str
    symbol: str
    primary_method_id: str = ""
    supporting_method_ids: List[str] = field(default_factory=list)
    rejected_method_ids: List[str] = field(default_factory=list)
    selected_playbook_ids: List[str] = field(default_factory=list)
    relevant_macro_ids: List[str] = field(default_factory=list)
    overall_context_fit: float = 0.0
    confidence: float = 0.0
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasoning_summary: str = ""
    candidate_assessments: List[MethodCandidateAssessment] = field(default_factory=list)
    source_context_pack_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "primary_method_id": self.primary_method_id,
            "supporting_method_ids": list(dict.fromkeys(self.supporting_method_ids)),
            "rejected_method_ids": list(dict.fromkeys(self.rejected_method_ids)),
            "selected_playbook_ids": list(dict.fromkeys(self.selected_playbook_ids)),
            "relevant_macro_ids": list(dict.fromkeys(self.relevant_macro_ids)),
            "overall_context_fit": _clamp(self.overall_context_fit),
            "confidence": _clamp(self.confidence),
            "blockers": list(dict.fromkeys(self.blockers)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "reasoning_summary": self.reasoning_summary,
            "candidate_assessments": [item.as_dict() for item in self.candidate_assessments],
            "source_context_pack_id": self.source_context_pack_id,
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LLMReasoningRequest:
    request_id: str
    created_at: str
    mode: str
    symbol: str
    context_pack_id: str
    compact_prompt: str
    max_tokens: int
    temperature: float
    provider_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class LLMReasoningResponse:
    response_id: str
    request_id: str
    provider_name: str
    raw_text_redacted: str = ""
    parsed_result: MethodSelectionResult | None = None
    parse_status: str = "FAILED"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    token_usage_estimate: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "provider_name": self.provider_name,
            "raw_text_redacted": self.raw_text_redacted,
            "parsed_result": self.parsed_result.as_dict() if self.parsed_result else None,
            "parse_status": self.parse_status,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "latency_ms": round(float(self.latency_ms), 3),
            "token_usage_estimate": int(self.token_usage_estimate),
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
