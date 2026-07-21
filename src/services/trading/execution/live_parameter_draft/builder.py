from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_parameter_draft.models import (
    REQUIRED_HUMAN_REVIEWED_SLOT_MAP,
    REQUIRED_HUMAN_REVIEWED_SLOT_TYPES,
    HumanReviewedLiveParameterDraft,
    HumanReviewedParameterSlot,
)
from src.services.trading.execution.live_parameter_draft.policy import HumanReviewedLiveParameterDraftConfig


class HumanReviewedParameterSlotBuilder:
    def build_slots(self, source_boundary, source_refs: list[str] | None = None) -> list[HumanReviewedParameterSlot]:
        refs = list(source_refs or [])
        candidate_map: dict[str, list[str]] = {}
        for candidate in getattr(source_boundary, "source_candidates", []) or []:
            candidate_map.setdefault(str(getattr(candidate, "parameter_group", "")), []).append(
                str(getattr(candidate, "candidate_id", ""))
            )
        slots: list[HumanReviewedParameterSlot] = []
        for slot_type, parameter_group in REQUIRED_HUMAN_REVIEWED_SLOT_MAP.items():
            requirements = _requirements(slot_type)
            slots.append(
                HumanReviewedParameterSlot(
                    slot_id=f"human_reviewed_parameter_slot_{slot_type.lower()}",
                    slot_type=slot_type,
                    parameter_group=parameter_group,
                    status="UNRESOLVED",
                    title=f"{slot_type} unresolved review slot",
                    description=f"{slot_type} is reserved for a future controlled value proposal workflow; no value is present now.",
                    value_allowed_now=False,
                    value_resolved_now=False,
                    actual_value_present=False,
                    review_requirements=requirements,
                    source_candidate_ids=[item for item in candidate_map.get(parameter_group, []) if item],
                    future_evidence_required=_future_evidence(slot_type),
                    human_review_required="HUMAN_REVIEW_REQUIRED" in requirements,
                    deterministic_validation_required="DETERMINISTIC_VALIDATION_REQUIRED" in requirements,
                    freshness_required="FRESHNESS_CHECK_REQUIRED" in requirements,
                    broker_capability_required="BROKER_CAPABILITY_CHECK_REQUIRED" in requirements,
                    risk_policy_required="RISK_POLICY_CHECK_REQUIRED" in requirements,
                    audit_required="AUDIT_REQUIRED" in requirements,
                    redaction_required="REDACTION_REQUIRED" in requirements,
                    source_refs=refs,
                )
            )
        return slots


class HumanReviewedLiveParameterDraftBuilder:
    def __init__(
        self,
        config: HumanReviewedLiveParameterDraftConfig | None = None,
        slot_builder: HumanReviewedParameterSlotBuilder | None = None,
    ):
        self.config = config or HumanReviewedLiveParameterDraftConfig.from_config()
        self.slot_builder = slot_builder or HumanReviewedParameterSlotBuilder()

    def build(
        self,
        parameter_source_boundary,
        parameter_source_validation,
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
    ) -> HumanReviewedLiveParameterDraft:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(parameter_source_boundary, "created_at", "")
            or getattr(parameter_policy_spec, "created_at", "")
            or getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(parameter_source_boundary, "source_refs", []) or [])
            + list(getattr(parameter_source_validation, "source_refs", []) or [])
            + list(getattr(parameter_policy_spec, "source_refs", []) or [])
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
            getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(parameter_source_boundary, "idempotency_key", "")
            or getattr(parameter_policy_spec, "idempotency_key", "")
            or getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "human_reviewed_live_parameter_draft_v1",
                    base_idempotency,
                    getattr(parameter_source_boundary, "boundary_id", ""),
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
        if parameter_source_boundary is None and self.config.require_source_boundary:
            blockers.append("MISSING_SOURCE_BOUNDARY")
        if parameter_source_validation is None and self.config.require_source_boundary_validation:
            blockers.append("MISSING_SOURCE_BOUNDARY_VALIDATION")
        if self.config.require_source_boundary_validation:
            if getattr(parameter_source_validation, "valid", False) is not True:
                blockers.append("MISSING_SOURCE_BOUNDARY_VALIDATION")
        if self.config.require_human_review_allowed:
            if getattr(parameter_source_validation, "human_reviewed_parameter_draft_allowed", False) is not True:
                blockers.append("HUMAN_REVIEWED_PARAMETER_DRAFT_NOT_ALLOWED")
            if getattr(parameter_source_boundary, "human_reviewed_parameter_draft_allowed", False) is not True:
                blockers.append("HUMAN_REVIEWED_PARAMETER_DRAFT_NOT_ALLOWED")
        if parameter_policy_spec is None and self.config.require_policy_spec:
            blockers.append("MISSING_PARAMETER_POLICY_SPEC")
        if contract_skeleton is None and self.config.require_contract_skeleton:
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
        if _resolved_values_present(parameter_source_boundary, parameter_source_validation, parameter_policy_spec, contract_skeleton):
            blockers.append("RESOLVED_PARAMETER_VALUES_NOT_ALLOWED")
        if _actual_order_values_present(parameter_source_boundary, parameter_source_validation, parameter_policy_spec, contract_skeleton):
            blockers.append("ACTUAL_ORDER_VALUES_NOT_ALLOWED")
        if now > expires_at_dt:
            blockers.append("EXPIRED_PARAMETER_DRAFT")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_PARAMETER_DRAFT")
        if _unsafe_execution_flags(
            parameter_source_boundary,
            parameter_source_validation,
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

        slots = self.slot_builder.build_slots(parameter_source_boundary, source_refs)
        slot_types = {slot.slot_type for slot in slots}
        missing_slot_types = [item for item in REQUIRED_HUMAN_REVIEWED_SLOT_TYPES if item not in slot_types]
        if missing_slot_types or len(slots) != len(REQUIRED_HUMAN_REVIEWED_SLOT_TYPES):
            blockers.append("MISSING_REQUIRED_SLOTS")
        if any(slot.value_allowed_now or slot.value_resolved_now or slot.actual_value_present for slot in slots):
            blockers.append("SLOT_VALUE_NOT_ALLOWED")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "DRAFT_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_PARAMETER_DRAFT" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_PARAMETER_DRAFT" in blockers:
            status = "DUPLICATE"
        scope = "VALUE_PROPOSAL_WORKFLOW_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        draft = HumanReviewedLiveParameterDraft(
            draft_id=f"human_reviewed_live_parameter_draft_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(parameter_source_boundary, "mode", getattr(parameter_policy_spec, "mode", "REVIEW_ONLY")),
            symbol=getattr(parameter_source_boundary, "symbol", getattr(parameter_policy_spec, "symbol", "")),
            broker_symbol=getattr(parameter_source_boundary, "broker_symbol", getattr(parameter_policy_spec, "broker_symbol", "")),
            status=status,
            scope=scope,
            value_proposal_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            source_parameter_source_boundary_id=getattr(parameter_source_boundary, "boundary_id", ""),
            source_parameter_source_validation_id=getattr(parameter_source_validation, "validation_report_id", ""),
            source_parameter_policy_spec_id=getattr(parameter_policy_spec, "policy_spec_id", ""),
            source_parameter_policy_validation_id=getattr(parameter_policy_validation, "validation_report_id", ""),
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_contract_skeleton_validation_id=getattr(contract_skeleton_validation, "validation_report_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            slots=slots,
            required_slot_types=list(REQUIRED_HUMAN_REVIEWED_SLOT_TYPES),
            missing_slot_types=missing_slot_types,
            unresolved_slot_types=list(REQUIRED_HUMAN_REVIEWED_SLOT_TYPES) if not missing_slot_types else [slot.slot_type for slot in slots],
            resolved_slot_types=[],
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        draft.payload_size_chars = len(json.dumps(draft.as_dict(), ensure_ascii=False, sort_keys=True))
        return draft


def _requirements(slot_type: str) -> list[str]:
    return {
        "SIDE_SLOT": ["HUMAN_REVIEW_REQUIRED", "SOURCE_TRACE_REQUIRED", "DETERMINISTIC_VALIDATION_REQUIRED"],
        "PRICE_SLOT": ["SOURCE_TRACE_REQUIRED", "DETERMINISTIC_VALIDATION_REQUIRED", "FRESHNESS_CHECK_REQUIRED"],
        "PROTECTION_SLOT": [
            "HUMAN_REVIEW_REQUIRED",
            "SOURCE_TRACE_REQUIRED",
            "DETERMINISTIC_VALIDATION_REQUIRED",
            "RISK_POLICY_CHECK_REQUIRED",
        ],
        "VOLUME_SLOT": [
            "HUMAN_REVIEW_REQUIRED",
            "BROKER_CAPABILITY_CHECK_REQUIRED",
            "RISK_POLICY_CHECK_REQUIRED",
            "DETERMINISTIC_VALIDATION_REQUIRED",
        ],
        "RISK_SLOT": ["HUMAN_REVIEW_REQUIRED", "SOURCE_TRACE_REQUIRED", "RISK_POLICY_CHECK_REQUIRED", "AUDIT_REQUIRED"],
        "BROKER_SYMBOL_SLOT": ["SOURCE_TRACE_REQUIRED", "DETERMINISTIC_VALIDATION_REQUIRED", "REDACTION_REQUIRED"],
        "EXECUTION_TIMING_SLOT": [
            "SOURCE_TRACE_REQUIRED",
            "FRESHNESS_CHECK_REQUIRED",
            "DETERMINISTIC_VALIDATION_REQUIRED",
        ],
        "IDEMPOTENCY_SLOT": ["AUDIT_REQUIRED", "DETERMINISTIC_VALIDATION_REQUIRED"],
        "AUDIT_SLOT": ["AUDIT_REQUIRED", "REDACTION_REQUIRED", "SOURCE_TRACE_REQUIRED"],
    }.get(slot_type, ["UNKNOWN"])


def _future_evidence(slot_type: str) -> list[str]:
    evidence = ["source traceability", "future controlled value proposal", "append-only audit evidence"]
    if slot_type in {"SIDE_SLOT", "PROTECTION_SLOT", "VOLUME_SLOT", "RISK_SLOT"}:
        evidence.append("future human review evidence")
    if slot_type in {"PRICE_SLOT", "EXECUTION_TIMING_SLOT"}:
        evidence.append("freshness evidence")
    if slot_type in {"VOLUME_SLOT", "BROKER_SYMBOL_SLOT"}:
        evidence.append("broker metadata evidence")
    return evidence


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
    if proposal_draft is not None:
        if getattr(proposal_draft, "executable", True) is not False:
            return True
        if getattr(proposal_draft, "non_executable", False) is not True:
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
