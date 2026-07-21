from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


LIVE_ORDER_PARAMETER_POLICY_STATUSES = {
    "NOT_REQUESTED",
    "READY_FOR_SOURCE_BOUNDARY",
    "POLICY_VALIDATED",
    "BLOCKED",
    "EXPIRED",
    "DUPLICATE",
    "INVALID",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_POLICY_SCOPES = {"PARAMETER_SOURCE_BOUNDARY_ONLY", "EXECUTION_NOT_ALLOWED", "UNKNOWN"}
LIVE_ORDER_PARAMETER_POLICY_GROUPS = {
    "SIDE_POLICY",
    "PRICE_POLICY",
    "PROTECTION_POLICY",
    "VOLUME_POLICY",
    "RISK_POLICY",
    "BROKER_SYMBOL_POLICY",
    "EXECUTION_TIMING_POLICY",
    "IDEMPOTENCY_POLICY",
    "AUDIT_POLICY",
    "UNKNOWN",
}
REQUIRED_PARAMETER_POLICY_GROUP_LABELS = [
    "SIDE_POLICY",
    "PRICE_POLICY",
    "PROTECTION_POLICY",
    "VOLUME_POLICY",
    "RISK_POLICY",
    "BROKER_SYMBOL_POLICY",
    "EXECUTION_TIMING_POLICY",
    "IDEMPOTENCY_POLICY",
    "AUDIT_POLICY",
]
LIVE_ORDER_PARAMETER_POLICY_RULE_STATUSES = {
    "SATISFIED_AS_POLICY_ONLY",
    "MISSING_FUTURE_SOURCE",
    "BLOCKED",
    "NOT_APPLICABLE",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_POLICY_SEVERITIES = {"INFO", "WARNING", "BLOCKING", "CRITICAL"}
LIVE_ORDER_PARAMETER_POLICY_BLOCK_REASONS = {
    "MISSING_CONTRACT_SKELETON",
    "MISSING_CONTRACT_SKELETON_VALIDATION",
    "CONTRACT_PARAMETER_VALIDATION_NOT_ALLOWED",
    "MISSING_LIVE_ORDER_INTENT",
    "MISSING_PERMISSION_DECISION",
    "MISSING_PREFLIGHT_REPORT",
    "MISSING_PROPOSAL_DRAFT",
    "MISSING_SIMULATED_CONTRACT",
    "MISSING_PARAMETER_GROUPS",
    "RESOLVED_PARAMETER_VALUES_NOT_ALLOWED",
    "MISSING_SOURCE_REFS",
    "MISSING_IDEMPOTENCY",
    "EXPIRED_POLICY_SPEC",
    "DUPLICATE_POLICY_SPEC",
    "LIVE_EXECUTION_STILL_DISABLED",
    "ORDER_SEND_STILL_FORBIDDEN",
    "EXECUTION_STILL_FORBIDDEN",
    "FORBIDDEN_EXECUTION_MARKER",
    "INVALID_INPUT",
    "UNKNOWN",
}
LIVE_ORDER_PARAMETER_POLICY_JOURNAL_EVENT_TYPES = {
    "LIVE_ORDER_PARAMETER_POLICY_VALIDATED",
    "LIVE_ORDER_PARAMETER_POLICY_BLOCKED",
    "LIVE_ORDER_PARAMETER_POLICY_DUPLICATE_DETECTED",
    "LIVE_ORDER_PARAMETER_POLICY_JOURNAL_WRITE_FAILED",
    "UNKNOWN",
}


@dataclass
class LiveOrderParameterPolicyRule:
    rule_id: str
    group: str
    title: str
    status: str
    severity: str
    required: bool
    blocking: bool
    policy_description: str
    future_evidence_required: List[str] = field(default_factory=list)
    future_source_boundary_required: bool = True
    human_review_required: bool = False
    deterministic_validation_required: bool = True
    forbidden_actual_values: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "group": self.group if self.group in LIVE_ORDER_PARAMETER_POLICY_GROUPS else "UNKNOWN",
            "title": self.title,
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_POLICY_RULE_STATUSES else "UNKNOWN",
            "severity": self.severity if self.severity in LIVE_ORDER_PARAMETER_POLICY_SEVERITIES else "WARNING",
            "required": bool(self.required),
            "blocking": bool(self.blocking),
            "policy_description": self.policy_description,
            "future_evidence_required": _dedupe(self.future_evidence_required),
            "future_source_boundary_required": bool(self.future_source_boundary_required),
            "human_review_required": bool(self.human_review_required),
            "deterministic_validation_required": bool(self.deterministic_validation_required),
            "forbidden_actual_values": _dedupe(self.forbidden_actual_values),
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
        }


@dataclass
class LiveOrderParameterPolicySpec:
    policy_spec_id: str
    created_at: str
    mode: str = "REVIEW_ONLY"
    symbol: str = ""
    broker_symbol: str = ""
    status: str = "UNKNOWN"
    scope: str = "EXECUTION_NOT_ALLOWED"
    parameter_source_boundary_allowed: bool = False
    live_execution_allowed: bool = False
    order_send_allowed: bool = False
    execution_allowed: bool = False
    executable: bool = False
    mt5_payload_created: bool = False
    order_sent: bool = False
    hard_live_block_required: bool = True
    source_contract_skeleton_id: str = ""
    source_contract_skeleton_validation_id: str = ""
    source_live_order_intent_id: str = ""
    source_live_order_intent_validation_id: str = ""
    source_live_permission_decision_id: str = ""
    source_preflight_report_id: str = ""
    source_proposal_draft_id: str = ""
    source_simulated_contract_id: str = ""
    required_parameter_groups: List[str] = field(default_factory=list)
    unresolved_parameter_groups: List[str] = field(default_factory=list)
    policy_rules: List[LiveOrderParameterPolicyRule] = field(default_factory=list)
    resolved_parameter_values_present: bool = False
    actual_order_values_present: bool = False
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
            "policy_spec_id": self.policy_spec_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_POLICY_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_PARAMETER_POLICY_SCOPES else "UNKNOWN",
            "parameter_source_boundary_allowed": bool(self.parameter_source_boundary_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_contract_skeleton_validation_id": self.source_contract_skeleton_validation_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_order_intent_validation_id": self.source_live_order_intent_validation_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_proposal_draft_id": self.source_proposal_draft_id,
            "source_simulated_contract_id": self.source_simulated_contract_id,
            "required_parameter_groups": _parameter_labels(self.required_parameter_groups),
            "unresolved_parameter_groups": _parameter_labels(self.unresolved_parameter_groups),
            "policy_rules": [rule.as_dict() for rule in self.policy_rules],
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
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
class LiveOrderParameterPolicyValidationReport:
    validation_report_id: str
    created_at: str
    source_policy_spec_id: str
    valid: bool
    parameter_source_boundary_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    policy_groups_count: int
    policy_rules_count: int
    unresolved_groups_count: int
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    validation_checks: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "validation_report_id": self.validation_report_id,
            "created_at": self.created_at,
            "source_policy_spec_id": self.source_policy_spec_id,
            "valid": bool(self.valid),
            "parameter_source_boundary_allowed": bool(self.parameter_source_boundary_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "policy_groups_count": int(self.policy_groups_count),
            "policy_rules_count": int(self.policy_rules_count),
            "unresolved_groups_count": int(self.unresolved_groups_count),
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "validation_checks": [dict(item) for item in self.validation_checks],
            "blockers": _dedupe(self.blockers),
            "warnings": _dedupe(self.warnings),
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
        }


@dataclass
class LiveOrderParameterPolicyJournalRecord:
    journal_record_id: str
    created_at: str
    event_type: str
    policy_spec_id: str
    validation_report_id: str
    status: str
    scope: str
    parameter_source_boundary_allowed: bool
    live_execution_allowed: bool
    order_send_allowed: bool
    execution_allowed: bool
    executable: bool
    mt5_payload_created: bool
    order_sent: bool
    hard_live_block_required: bool
    policy_groups_count: int
    policy_rules_count: int
    unresolved_groups_count: int
    resolved_parameter_values_present: bool
    actual_order_values_present: bool
    artifact_hash: str
    idempotency_key: str
    source_contract_skeleton_id: str
    source_contract_skeleton_validation_id: str
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
            "event_type": self.event_type if self.event_type in LIVE_ORDER_PARAMETER_POLICY_JOURNAL_EVENT_TYPES else "UNKNOWN",
            "policy_spec_id": self.policy_spec_id,
            "validation_report_id": self.validation_report_id,
            "status": self.status if self.status in LIVE_ORDER_PARAMETER_POLICY_STATUSES else "UNKNOWN",
            "scope": self.scope if self.scope in LIVE_ORDER_PARAMETER_POLICY_SCOPES else "UNKNOWN",
            "parameter_source_boundary_allowed": bool(self.parameter_source_boundary_allowed),
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "executable": False,
            "mt5_payload_created": False,
            "order_sent": False,
            "hard_live_block_required": True,
            "policy_groups_count": int(self.policy_groups_count),
            "policy_rules_count": int(self.policy_rules_count),
            "unresolved_groups_count": int(self.unresolved_groups_count),
            "resolved_parameter_values_present": False,
            "actual_order_values_present": False,
            "artifact_hash": self.artifact_hash,
            "idempotency_key": self.idempotency_key,
            "source_contract_skeleton_id": self.source_contract_skeleton_id,
            "source_contract_skeleton_validation_id": self.source_contract_skeleton_validation_id,
            "source_live_order_intent_id": self.source_live_order_intent_id,
            "source_live_permission_decision_id": self.source_live_permission_decision_id,
            "source_preflight_report_id": self.source_preflight_report_id,
            "source_refs": _dedupe(self.source_refs),
            "payload_size_chars": int(self.payload_size_chars),
            "metadata_redacted": dict(self.metadata_redacted),
        }


@dataclass
class LiveOrderParameterPolicySummary:
    total_records: int = 0
    total_validated: int = 0
    total_blocked: int = 0
    total_duplicates: int = 0
    latest_record_at: str = ""
    latest_policy_spec_id: str = ""
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
            "latest_policy_spec_id": self.latest_policy_spec_id,
            "latest_validation_report_id": self.latest_validation_report_id,
            "latest_status": self.latest_status,
            "warnings": _dedupe(self.warnings),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parameter_labels(items: List[Any] | None) -> List[str]:
    return [str(item) for item in _dedupe(items or [])]


def _dedupe(items: List[Any] | None) -> List[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
