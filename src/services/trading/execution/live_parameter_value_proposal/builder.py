from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_parameter_value_proposal.models import (
    REQUIRED_CONTROLLED_VALUE_SLOT_MAP,
    REQUIRED_CONTROLLED_VALUE_SLOT_TYPES,
    ControlledLiveParameterValueProposal,
    ControlledLiveParameterValueSlot,
)
from src.services.trading.execution.live_parameter_value_proposal.policy import (
    ControlledLiveParameterValueProposalConfig,
)


class ControlledLiveParameterValueSlotBuilder:
    def build_slots(self, parameter_draft, source_refs: list[str] | None = None) -> list[ControlledLiveParameterValueSlot]:
        refs = list(source_refs or [])
        draft_slots = {str(getattr(slot, "slot_type", "")): slot for slot in getattr(parameter_draft, "slots", []) or []}
        value_slots: list[ControlledLiveParameterValueSlot] = []
        for value_slot_type, source_slot_type in REQUIRED_CONTROLLED_VALUE_SLOT_MAP.items():
            source_slot = draft_slots.get(source_slot_type)
            review_requirements = set(getattr(source_slot, "review_requirements", []) or [])
            value_slots.append(
                ControlledLiveParameterValueSlot(
                    value_slot_id=f"controlled_value_proposal_slot_{value_slot_type.lower()}",
                    slot_type=value_slot_type,
                    source_draft_slot_id=str(getattr(source_slot, "slot_id", "")),
                    parameter_group=str(getattr(source_slot, "parameter_group", "")),
                    status="REVIEW_REQUIRED",
                    review_state="HUMAN_REVIEW_REQUIRED",
                    title=f"{value_slot_type} review-required value container",
                    description=f"{value_slot_type} is a controlled proposal container for future human approval and value lock only.",
                    proposed_value_present=False,
                    proposed_value_redacted=True,
                    value_lock_required=True,
                    human_review_required=True,
                    deterministic_validation_required=True,
                    source_trace_required=True,
                    freshness_check_required="FRESHNESS_CHECK_REQUIRED" in review_requirements,
                    broker_capability_check_required="BROKER_CAPABILITY_CHECK_REQUIRED" in review_requirements,
                    risk_policy_check_required="RISK_POLICY_CHECK_REQUIRED" in review_requirements,
                    audit_required="AUDIT_REQUIRED" in review_requirements,
                    redaction_required=True,
                    executable_value=False,
                    source_candidate_ids=list(getattr(source_slot, "source_candidate_ids", []) or []),
                    source_refs=refs,
                )
            )
        return value_slots


class ControlledLiveParameterValueProposalBuilder:
    def __init__(
        self,
        config: ControlledLiveParameterValueProposalConfig | None = None,
        slot_builder: ControlledLiveParameterValueSlotBuilder | None = None,
    ):
        self.config = config or ControlledLiveParameterValueProposalConfig.from_config()
        self.slot_builder = slot_builder or ControlledLiveParameterValueSlotBuilder()

    def build(
        self,
        parameter_draft,
        parameter_draft_validation,
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
    ) -> ControlledLiveParameterValueProposal:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(parameter_draft, "created_at", "")
            or getattr(parameter_source_boundary, "created_at", "")
            or getattr(parameter_policy_spec, "created_at", "")
            or getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(parameter_draft, "source_refs", []) or [])
            + list(getattr(parameter_draft_validation, "source_refs", []) or [])
            + list(getattr(parameter_source_boundary, "source_refs", []) or [])
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
            getattr(parameter_draft, "artifact_hash", "")
            or getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(parameter_draft, "idempotency_key", "")
            or getattr(parameter_source_boundary, "idempotency_key", "")
            or getattr(parameter_policy_spec, "idempotency_key", "")
            or getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "controlled_live_parameter_value_proposal_v1",
                    base_idempotency,
                    getattr(parameter_draft, "draft_id", ""),
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
        if parameter_draft is None and self.config.require_parameter_draft:
            blockers.append("MISSING_PARAMETER_DRAFT")
        if parameter_draft_validation is None and self.config.require_parameter_draft_validation:
            blockers.append("MISSING_PARAMETER_DRAFT_VALIDATION")
        if self.config.require_parameter_draft_validation and getattr(parameter_draft_validation, "valid", False) is not True:
            blockers.append("MISSING_PARAMETER_DRAFT_VALIDATION")
        if self.config.require_value_proposal_workflow_allowed:
            if getattr(parameter_draft_validation, "value_proposal_workflow_allowed", False) is not True:
                blockers.append("VALUE_PROPOSAL_WORKFLOW_NOT_ALLOWED")
            if getattr(parameter_draft, "value_proposal_workflow_allowed", False) is not True:
                blockers.append("VALUE_PROPOSAL_WORKFLOW_NOT_ALLOWED")
        if parameter_source_boundary is None and self.config.require_source_boundary:
            blockers.append("MISSING_SOURCE_BOUNDARY")
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
        if now > expires_at_dt:
            blockers.append("EXPIRED_VALUE_PROPOSAL")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_VALUE_PROPOSAL")
        if _unsafe_execution_flags(
            parameter_draft,
            parameter_draft_validation,
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
        if _executable_order_present(parameter_draft, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if _mt5_payload_present(parameter_draft, parameter_source_boundary, parameter_policy_spec, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")

        value_slots = self.slot_builder.build_slots(parameter_draft, source_refs)
        slot_types = {slot.slot_type for slot in value_slots}
        missing_value_slot_types = [item for item in REQUIRED_CONTROLLED_VALUE_SLOT_TYPES if item not in slot_types]
        if missing_value_slot_types or len(value_slots) != len(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES):
            blockers.append("MISSING_REQUIRED_VALUE_SLOTS")
        if self.config.require_human_review and (
            any(slot.human_review_required is not True for slot in value_slots) or not True
        ):
            blockers.append("HUMAN_REVIEW_NOT_COMPLETED")
        if self.config.require_value_lock and any(slot.value_lock_required is not True for slot in value_slots):
            blockers.append("VALUE_LOCK_NOT_ALLOWED")
        if any(slot.executable_value is not False for slot in value_slots):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "PROPOSAL_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_VALUE_PROPOSAL" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_VALUE_PROPOSAL" in blockers:
            status = "DUPLICATE"
        scope = "HUMAN_VALUE_APPROVAL_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        proposal = ControlledLiveParameterValueProposal(
            proposal_id=f"controlled_live_parameter_value_proposal_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(parameter_draft, "mode", getattr(parameter_source_boundary, "mode", "REVIEW_ONLY")),
            symbol=getattr(parameter_draft, "symbol", getattr(parameter_source_boundary, "symbol", "")),
            broker_symbol=getattr(parameter_draft, "broker_symbol", getattr(parameter_source_boundary, "broker_symbol", "")),
            status=status,
            scope=scope,
            human_value_approval_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            value_lock_required=True,
            human_review_required=True,
            source_parameter_draft_id=getattr(parameter_draft, "draft_id", ""),
            source_parameter_draft_validation_id=getattr(parameter_draft_validation, "validation_report_id", ""),
            source_parameter_source_boundary_id=getattr(parameter_source_boundary, "boundary_id", ""),
            source_parameter_source_validation_id=getattr(parameter_source_validation, "validation_report_id", ""),
            source_parameter_policy_spec_id=getattr(parameter_policy_spec, "policy_spec_id", ""),
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            value_slots=value_slots,
            required_value_slot_types=list(REQUIRED_CONTROLLED_VALUE_SLOT_TYPES),
            missing_value_slot_types=missing_value_slot_types,
            reviewed_value_slot_types=[],
            approved_value_slot_types=[],
            rejected_value_slot_types=[],
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        proposal.payload_size_chars = len(json.dumps(proposal.as_dict(), ensure_ascii=False, sort_keys=True))
        return proposal


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
        if getattr(item, "order_contract_ready", False) is not False:
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


def _executable_order_present(*items) -> bool:
    return any(getattr(item, "executable", False) is not False for item in items if item is not None)


def _mt5_payload_present(*items) -> bool:
    return any(getattr(item, "mt5_payload_created", False) is not False for item in items if item is not None)


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
