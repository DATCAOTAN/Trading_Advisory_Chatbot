from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_HUMAN_REVIEWED_PARAMETER_DRAFT",
    "SOURCE_BOUNDARY_VALIDATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_SCOPES = {
    "HUMAN_REVIEWED_PARAMETER_DRAFT_ONLY",
    "EXECUTION_NOT_ALLOWED",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_SOURCE_TYPES = {
    "HUMAN_REVIEW_REQUIRED",
    "MARKET_SNAPSHOT",
    "FEATURE_SNAPSHOT",
    "REGIME_CONTEXT",
    "CALENDAR_CONTEXT",
    "METHOD_SELECTION",
    "SIGNAL_SCORE",
    "READINESS_DECISION",
    "REVIEW_ARTIFACT",
    "PROPOSAL_DRAFT",
    "SIMULATED_CONTRACT",
    "BROKER_SYMBOL_METADATA",
    "BROKER_CAPABILITY_METADATA",
    "CONFIGURED_RISK_CONSTRAINTS",
    "IDEMPOTENCY_AUDIT",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_SOURCE_TRUST_LEVELS = {"REQUIRED", "SUPPORTING", "CONTEXT_ONLY", "REJECTED", "UNKNOWN"}
LIVE_ORDER_PARAMETER_SOURCE_STATUSES = {
    "ALLOWED_AS_FUTURE_SOURCE",
    "REQUIRED_BUT_MISSING",
    "REJECTED",
    "POLICY_ONLY",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_BLOCK_REASONS = {
    "MISSING_PARAMETER_POLICY_SPEC",
    "MISSING_PARAMETER_POLICY_VALIDATION",
    "PARAMETER_SOURCE_BOUNDARY_NOT_ALLOWED",
    "MISSING_CONTRACT_SKELETON",
    "MISSING_LIVE_ORDER_INTENT",
    "MISSING_PERMISSION_DECISION",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_PROPOSAL_DRAFT",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "MISSING_REQUIRED_SOURCE_CANDIDATES",
    "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED",
    "ACTUAL_ORDER_VALUES_NOT_ALLOWED",
    "EXPIRED_SOURCE_BOUNDARY",
    "DUPLICATE_SOURCE_BOUNDARY",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_SOURCE_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_VALIDATED",
    "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_BLOCKED",
    "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_DUPLICATE_DETECTED",
    "LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}

REQUIRED_SOURCE_CANDIDATE_MAP = {
    "SIDE_POLICY": ["HUMAN_REVIEW_REQUIRED", "REVIEW_ARTIFACT", "METHOD_SELECTION", "SIGNAL_SCORE"],
    "PRICE_POLICY": ["MARKET_SNAPSHOT", "FEATURE_SNAPSHOT", "BROKER_SYMBOL_METADATA"],
    "PROTECTION_POLICY": ["REVIEW_ARTIFACT", "REGIME_CONTEXT", "FEATURE_SNAPSHOT"],
    "VOLUME_POLICY": ["BROKER_CAPABILITY_METADATA", "CONFIGURED_RISK_CONSTRAINTS"],
    "RISK_POLICY": ["CONFIGURED_RISK_CONSTRAINTS", "REVIEW_ARTIFACT", "READINESS_DECISION"],
    "BROKER_SYMBOL_POLICY": ["BROKER_SYMBOL_METADATA", "MARKET_SNAPSHOT"],
    "EXECUTION_TIMING_POLICY": ["CALENDAR_CONTEXT", "MARKET_SNAPSHOT", "FEATURE_SNAPSHOT", "READINESS_DECISION"],
    "IDEMPOTENCY_POLICY": ["IDEMPOTENCY_AUDIT"],
    "AUDIT_POLICY": ["IDEMPOTENCY_AUDIT", "PROPOSAL_DRAFT", "SIMULATED_CONTRACT"],
}
REQUIRED_PARAMETER_SOURCE_GROUP_LABELS = list(REQUIRED_SOURCE_CANDIDATE_MAP.keys())
REQUIRED_PARAMETER_SOURCE_TYPE_LABELS = sorted({item for items in REQUIRED_SOURCE_CANDIDATE_MAP.values() for item in items})


@dataclass
class LiveOrderParameterSourceCandidate:
    candidate_id: str
    parameter_group: str
    source_type: str
    trust_level: str
    status: str
    title: str
    description: str
    future_evidence_required: List[str] = field(default_factory=list)
    human_review_required: bool = False
    deterministic_validation_required: bool = True
    freshness_required: bool = False
    redaction_required: bool = False
    audit_required: bool = False
    actual_value_allowed_now: bool = False
    value_resolved_now: bool = False
    source_artifact_id: str = ""
    source_refs: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parameter_group": self.parameter_group,
            "source_type": self.source_type if self.source_type in LIVE_ORDER_PARAMETER_SOURCE_TYPES else "UNKNOWN",
            "trust_level": self.trust_level if self.trust_level in LIVE_ORDER_PARAMETER_SOURCE_TRUST_LEVELS else "UNKNOWN",
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_SOURCE_STATUSES else "UNKNOWN",
            "title": self.title,
            "description": self.description,
            "future_evidence_required": _dedupe(self.future_evidence_required),
            "human_review_required": bool(self.human_review_required),
            "deterministic_validation_required": bool(self.deterministic_validation_required),
            "freshness_required": bool(self.freshness_required),
            "redaction_required": bool(self.redaction_required),
            "audit_required": bool(self.audit_required),
            "actual_value_allowed_now": False,
            "value_resolved_now": False,
            "source_artifact_id": self.source_artifact_id,
            "source_refs": _dedupe(self.source_refs),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
        }


@dataclass
class LiveOrderParameterSourceBoundary:
    boundary_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    human_reviewed_parameter_draft_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    resolved_parameter_values_present: bool = False
    actual_order_values_present: bool = False
    source_parameter_policy_spec_id: str = ""
    source_parameter_policy_validation_id: str = ""
    source_contract_skeleton_id: str = ""
    source_contract_skeleton_validation_id: str = ""
    source_live_order_intent_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    source_candidates: List[LiveOrderParameterSourceCandidate] = field(default_factory=list)
    required_source_types: List[str] = field(default_factory=list)
    missing_source_types: List[str] = field(default_factory=list)
    rejected_source_types: List[str] = field(default_factory=list)
    source_boundary_rules: List[str] = field(default_factory=list)
    artifact_hash: str = ""
    idempotency_key: str = ""
    expires_at: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_SCOPES else "UNKNOWN",
            "human_reviewed_parameter_draft_allowed": bool(self.human_reviewed_parameter_draft_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_parameter_policy_validation_id": self.source_parameter_policy_validation_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_contract_skeleton_validation_id": self.source_contract_skeleton_validation_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "source_candidates": [candidate.as_dict() for candidate in self.source_candidates],
            "required_source_types": _dedupe(self.required_source_types),
            "missing_source_types": _dedupe(self.missing_source_types),
            "rejected_source_types": _dedupe(self.rejected_source_types),
            "source_boundary_rules": _dedupe(self.source_boundary_rules),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "expires_at": self.expires_at,
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "reasons": _dedupe(self.reasons),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderParameterSourceValidationReport:
    validation_report_id: str
    created_at: str
    source_boundary_id: str
    valid: bool
    human_reviewed_parameter_draft_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    source_candidates_count: int
    required_sources_count: int
    missing_sources_count: int
    rejected_sources_count: int
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_boundary_id": self.source_boundary_id,
            "valid": bool(self.valid),
            "human_reviewed_parameter_draft_allowed": bool(self.human_reviewed_parameter_draft_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "source_candidates_count": int(self.source_candidates_count),
            "required_sources_count": int(self.required_sources_count),
            "missing_sources_count": int(self.missing_sources_count),
            "rejected_sources_count": int(self.rejected_sources_count),
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderParameterSourceJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    boundary_id: str
    validation_report_id: str
    status: str
    scope: str
    human_reviewed_parameter_draft_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    source_candidates_count: int
    required_sources_count: int
    missing_sources_count: int
    rejected_sources_count: int
    artifact_hash: str
    idempotency_key: str
    source_parameter_policy_spec_id: str
    source_parameter_policy_validation_id: str
    source_contract_skeleton_id: str
    source_live_order_intent_id: str
    source_live_permission_decision_id: str
    source_preflight_report_id: str
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0
    metadata_redacted: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_record_id": self.journal_record_id,
            "created_at": self.created_at,
            "event_type": self.event_type if self.event_type in LIVE_ORDER_PARAMETER_SOURCE_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "boundary_id": self.boundary_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_PARAMETER_SOURCE_BOUNDARY_SCOPES else "UNKNOWN",
            "human_reviewed_parameter_draft_allowed": bool(self.human_reviewed_parameter_draft_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "source_candidates_count": int(self.source_candidates_count),
            "required_sources_count": int(self.required_sources_count),
            "missing_sources_count": int(self.missing_sources_count),
            "rejected_sources_count": int(self.rejected_sources_count),
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_parameter_policy_spec_id": self.source_parameter_policy_spec_id,
            "source_parameter_policy_validation_id": self.source_parameter_policy_validation_id,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveOrderParameterSourceSummary:
    total_records: int = 0
    total_validated: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_boundary_id: str = ""
    latest_validation_report_id: str = ""
    latest_status: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": int(self.total_records),
            "total_validated": int(self.total_validated),
            "total_blocked": int(self.total_blocked),
            "total_duplicates": int(self.total_duplicates),
            "latest_record_at": self.latest_record_at,
            "latest_boundary_id": self.latest_boundary_id,
            "latest_validation_report_id": self.latest_validation_report_id,
            "latest_status": self.latest_status,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
