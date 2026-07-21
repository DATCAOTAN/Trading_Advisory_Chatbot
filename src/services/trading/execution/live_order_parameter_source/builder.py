from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_parameter_source.models import (
    REQUIRED_PARAMETER_SOURCE_TYPE_LABELS,
    REQUIRED_SOURCE_CANDIDATE_MAP,
    LiveOrderParameterSourceBoundary,
    LiveOrderParameterSourceCandidate,
)
from src.services.trading.execution.live_order_parameter_source.policy import LiveOrderParameterSourceBoundaryConfig


class LiveOrderParameterSourceCandidateBuilder:
    def build_candidates(self, source_refs: list[str] | None = None, artifact_ids: dict[str, str] | None = None) -> list[LiveOrderParameterSourceCandidate]:
        refs = list(source_refs or [])
        ids = dict(artifact_ids or {})
        candidates: list[LiveOrderParameterSourceCandidate] = []
        for group, source_types in REQUIRED_SOURCE_CANDIDATE_MAP.items():
            for source_type in source_types:
                candidates.append(
                    LiveOrderParameterSourceCandidate(
                        candidate_id=f"live_order_parameter_source_candidate_{group.lower()}_{source_type.lower()}",
                        parameter_group=group,
                        source_type=source_type,
                        trust_level="REQUIRED",
                        status="ALLOWED_AS_FUTURE_SOURCE",
                        title=f"{group} future source: {source_type}",
                        description=f"{source_type} is declared as an allowed future source for {group}; no value is resolved now.",
                        future_evidence_required=_future_evidence(group, source_type),
                        human_review_required=group in {"SIDE_POLICY", "PROTECTION_POLICY", "VOLUME_POLICY", "RISK_POLICY"} or source_type == "HUMAN_REVIEW_REQUIRED",
                        deterministic_validation_required=True,
                        freshness_required=group in {"PRICE_POLICY", "EXECUTION_TIMING_POLICY"} or source_type in {"MARKET_SNAPSHOT", "FEATURE_SNAPSHOT"},
                        redaction_required=group in {"BROKER_SYMBOL_POLICY", "AUDIT_POLICY"},
                        audit_required=group in {"IDEMPOTENCY_POLICY", "AUDIT_POLICY"} or source_type == "IDEMPOTENCY_AUDIT",
                        actual_value_allowed_now=False,
                        value_resolved_now=False,
                        source_artifact_id=ids.get(source_type, f"future_{source_type.lower()}_required"),
                        source_refs=refs,
                    )
                )
        return candidates


class LiveOrderParameterSourceBoundaryBuilder:
    def __init__(
        self,
        config: LiveOrderParameterSourceBoundaryConfig | None = None,
        candidate_builder: LiveOrderParameterSourceCandidateBuilder | None = None,
    ):
        self.config = config or LiveOrderParameterSourceBoundaryConfig.from_config()
        self.candidate_builder = candidate_builder or LiveOrderParameterSourceCandidateBuilder()

    def build(
        self,
        parameter_policy_spec,
        parameter_policy_validation,
        contract_skeleton,
        contract_skeleton_validation,
        live_order_intent,
        live_order_intent_validation,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LiveOrderParameterSourceBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(parameter_policy_spec, "created_at", "")
            or getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(parameter_policy_spec, "source_refs", []) or [])
            + list(getattr(parameter_policy_validation, "source_refs", []) or [])
            + list(getattr(contract_skeleton, "source_refs", []) or [])
            + list(getattr(contract_skeleton_validation, "source_refs", []) or [])
            + list(getattr(live_order_intent, "source_refs", []) or [])
            + list(getattr(live_order_intent_validation, "source_refs", []) or [])
            + list(getattr(permission_decision, "source_refs", []) or [])
            + list(getattr(preflight_report, "source_refs", []) or [])
            + list(getattr(proposal_draft, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
            + list(getattr(simulated_receipt, "source_refs", []) or [])
        )
        artifact_hash = (
            getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(parameter_policy_spec, "idempotency_key", "")
            or getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "live_order_parameter_source_boundary_v1",
                    base_idempotency,
                    getattr(parameter_policy_spec, "policy_spec_id", ""),
                    getattr(contract_skeleton, "contract_skeleton_id", ""),
                    getattr(live_order_intent, "intent_id", ""),
                    getattr(permission_decision, "decision_id", ""),
                    getattr(preflight_report, "report_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if parameter_policy_spec is None and self.config.require_policy_spec:
            blockers.append("MISSING_PARAMETER_POLICY_SPEC")
        if parameter_policy_validation is None and self.config.require_policy_validation:
            blockers.append("MISSING_PARAMETER_POLICY_VALIDATION")
        if self.config.require_policy_validation:
            if getattr(parameter_policy_validation, "valid", False) is not True:
                blockers.append("MISSING_PARAMETER_POLICY_VALIDATION")
            if getattr(parameter_policy_validation, "parameter_source_boundary_allowed", False) is not True:
                blockers.append("PARAMETER_SOURCE_BOUNDARY_NOT_ALLOWED")
            if getattr(parameter_policy_spec, "parameter_source_boundary_allowed", False) is not True:
                blockers.append("PARAMETER_SOURCE_BOUNDARY_NOT_ALLOWED")
        if contract_skeleton is None and self.config.require_contract_skeleton:
            blockers.append("MISSING_CONTRACT_SKELETON")
        if getattr(contract_skeleton_validation, "valid", True) is not True:
            blockers.append("MISSING_CONTRACT_SKELETON")
        if live_order_intent is None and self.config.require_live_order_intent:
            blockers.append("MISSING_LIVE_ORDER_INTENT")
        if permission_decision is None and self.config.require_permission_decision:
            blockers.append("MISSING_PERMISSION_DECISION")
        elif getattr(permission_decision, "gate_allowed", False) is not True:
            blockers.append("MISSING_PERMISSION_DECISION")
        if preflight_report is None:
            blockers.append("MISSING_PREFLIGHT_REPORT")
        elif self.config.require_preflight_pass and getattr(preflight_report, "preflight_status", "") != "PASS":
            blockers.append("MISSING_PREFLIGHT_REPORT")
        if proposal_draft is None and self.config.require_proposal_draft:
            blockers.append("MISSING_PROPOSAL_DRAFT")
        if simulated_contract is None and self.config.require_simulated_contract:
            blockers.append("MISSING_SIMULATED_CONTRACT")
        if self.config.require_source_refs and not source_refs:
            blockers.append("MISSING_SOURCE_REFS")
        if self.config.require_idempotency and (not artifact_hash or not base_idempotency or not idempotency_key):
            blockers.append("MISSING_IDEMPOTENCY")
        if _resolved_values_present(parameter_policy_spec, parameter_policy_validation, contract_skeleton):
            blockers.append("RESOLVED_PARAMETER_VALUES_NOT_ALLOWED")
        if _actual_order_values_present(parameter_policy_spec, parameter_policy_validation, contract_skeleton):
            blockers.append("ACTUAL_ORDER_VALUES_NOT_ALLOWED")
        if now > expires_at_dt:
            blockers.append("EXPIRED_SOURCE_BOUNDARY")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_SOURCE_BOUNDARY")
        if _unsafe_execution_flags(
            parameter_policy_spec,
            parameter_policy_validation,
            contract_skeleton,
            contract_skeleton_validation,
            live_order_intent,
            live_order_intent_validation,
            permission_decision,
            preflight_report,
        ):
            blockers.append("LIVE_EXECUTION_STILL_DISABLED")
        if _unsafe_sources(proposal_draft, simulated_contract):
            blockers.append("FORBIDDEN_EXECUTION_MARKER")

        artifact_ids = _artifact_ids(
            parameter_policy_spec,
            contract_skeleton,
            live_order_intent,
            permission_decision,
            preflight_report,
            proposal_draft,
            simulated_contract,
        )
        candidates = self.candidate_builder.build_candidates(source_refs, artifact_ids)
        declared_types = {candidate.source_type for candidate in candidates}
        missing_types = [item for item in REQUIRED_PARAMETER_SOURCE_TYPE_LABELS if item not in declared_types]
        if missing_types:
            blockers.append("MISSING_REQUIRED_SOURCE_CANDIDATES")
        if any(candidate.actual_value_allowed_now or candidate.value_resolved_now for candidate in candidates):
            blockers.append("ACTUAL_ORDER_VALUES_NOT_ALLOWED")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "SOURCE_BOUNDARY_VALIDATED" if allowed else "BLOCKED"
        if "EXPIRED_SOURCE_BOUNDARY" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_SOURCE_BOUNDARY" in blockers:
            status = "DUPLICATE"
        scope = "HUMAN_REVIEWED_PARAMETER_DRAFT_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        boundary = LiveOrderParameterSourceBoundary(
            boundary_id=f"live_order_parameter_source_boundary_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(parameter_policy_spec, "mode", getattr(contract_skeleton, "mode", "REVIEW_ONLY")),
            symbol=getattr(parameter_policy_spec, "symbol", getattr(contract_skeleton, "symbol", "")),
            broker_symbol=getattr(parameter_policy_spec, "broker_symbol", getattr(contract_skeleton, "broker_symbol", "")),
            status=status,
            scope=scope,
            human_reviewed_parameter_draft_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            source_parameter_policy_spec_id=getattr(parameter_policy_spec, "policy_spec_id", ""),
            source_parameter_policy_validation_id=getattr(parameter_policy_validation, "validation_report_id", ""),
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_contract_skeleton_validation_id=getattr(contract_skeleton_validation, "validation_report_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            source_candidates=candidates,
            required_source_types=list(REQUIRED_PARAMETER_SOURCE_TYPE_LABELS),
            missing_source_types=missing_types,
            rejected_source_types=[],
            source_boundary_rules=[
                "All declared candidates are future sources only.",
                "Human review is required before parameter draft creation.",
                "Deterministic validation is required before any value can be resolved.",
                "Redaction and append-only audit remain required.",
            ],
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        boundary.payload_size_chars = len(json.dumps(boundary.as_dict(), ensure_ascii=False, sort_keys=True))
        return boundary


def _future_evidence(group: str, source_type: str) -> list[str]:
    base = ["source traceability", "future human review gate", "deterministic validation evidence"]
    if source_type in {"MARKET_SNAPSHOT", "FEATURE_SNAPSHOT"}:
        base.append("freshness evidence")
    if source_type in {"BROKER_SYMBOL_METADATA", "BROKER_CAPABILITY_METADATA"}:
        base.append("broker metadata evidence")
    if group in {"IDEMPOTENCY_POLICY", "AUDIT_POLICY"}:
        base.append("append-only audit evidence")
    return base


def _artifact_ids(*items) -> dict[str, str]:
    keys = {
        "REVIEW_ARTIFACT": "future_review_artifact_required",
        "PROPOSAL_DRAFT": "draft_id",
        "SIMULATED_CONTRACT": "contract_id",
        "IDEMPOTENCY_AUDIT": "idempotency_key",
    }
    result: dict[str, str] = {}
    for source_type, attr in keys.items():
        for item in items:
            value = getattr(item, attr, "")
            if value:
                result[source_type] = str(value)
                break
    return result


def _resolved_values_present(*items) -> bool:
    return any(getattr(item, "resolved_parameter_values_present", False) is True for item in items if item is not None)


def _actual_order_values_present(*items) -> bool:
    return any(getattr(item, "actual_order_values_present", False) is True for item in items if item is not None)


def _unsafe_execution_flags(*items) -> bool:
    for item in items:
        if item is None:
            continue
        if getattr(item, "live_execution_allowed", False) is not False:
            return True
        if getattr(item, "order_send_allowed", False) is not False:
            return True
        if getattr(item, "execution_allowed", False) is not False:
            return True
        if getattr(item, "hard_live_block_required", True) is not True:
            return True
        if getattr(item, "executable", False) is not False:
            return True
        if getattr(item, "mt5_payload_created", False) is not False:
            return True
        if getattr(item, "order_sent", False) is not False:
            return True
    return False


def _unsafe_sources(proposal_draft, simulated_contract) -> bool:
    if proposal_draft is not None and getattr(proposal_draft, "executable", True) is not False:
        return True
    if simulated_contract is not None:
        if getattr(simulated_contract, "simulated_only", False) is not True:
            return True
        if getattr(simulated_contract, "executable", True) is not False:
            return True
    return False


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.now(timezone.utc)


def _stable_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _dedupe(items):
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
