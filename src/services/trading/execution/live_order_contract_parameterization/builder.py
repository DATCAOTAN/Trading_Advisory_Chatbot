from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_contract_parameterization.models import (
    REQUIRED_CONTRACT_PARAMETER_SLOT_MAP,
    REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES,
    LiveOrderContractParameterizationBoundary,
    LiveOrderContractParameterSlot,
)
from src.services.trading.execution.live_order_contract_parameterization.policy import (
    LiveOrderContractParameterizationConfig,
)


class LiveOrderContractParameterSlotBuilder:
    def build_contract_slots(
        self, approval_lock, source_refs: list[str] | None = None
    ) -> list[LiveOrderContractParameterSlot]:
        return self.build_slots(approval_lock, source_refs)

    def build_slots(self, approval_lock, source_refs: list[str] | None = None) -> list[LiveOrderContractParameterSlot]:
        refs = list(source_refs or [])
        locks_by_type = {str(getattr(slot, "slot_type", "")): slot for slot in getattr(approval_lock, "slot_locks", []) or []}
        contract_slots: list[LiveOrderContractParameterSlot] = []
        for contract_slot_type, source_lock_type in REQUIRED_CONTRACT_PARAMETER_SLOT_MAP.items():
            source_lock = locks_by_type.get(source_lock_type)
            contract_slots.append(
                LiveOrderContractParameterSlot(
                    contract_slot_id=f"live_order_contract_parameter_slot_{contract_slot_type.lower()}",
                    source_slot_lock_id=str(getattr(source_lock, "slot_lock_id", "")),
                    source_value_slot_id=str(getattr(source_lock, "source_value_slot_id", "")),
                    source_draft_slot_id=str(getattr(source_lock, "source_draft_slot_id", "")),
                    slot_type=contract_slot_type,
                    parameter_group=_parameter_group_from_slot(contract_slot_type),
                    status="PARAMETERIZED_FOR_VALIDATION_ONLY",
                    value_state="REDACTED_REFERENCE_ONLY",
                    parameterized_for_validation_only=True,
                    raw_value_stored=False,
                    redacted_value_reference_present=True,
                    executable_value=False,
                    mt5_payload_value=False,
                    order_request_value=False,
                    broker_mapping_required=contract_slot_type
                    in {
                        "BROKER_SYMBOL_CONTRACT_SLOT",
                        "PRICE_CONTRACT_SLOT",
                        "PROTECTION_CONTRACT_SLOT",
                        "VOLUME_CONTRACT_SLOT",
                        "EXECUTION_TIMING_CONTRACT_SLOT",
                    },
                    contract_validation_required=True,
                    final_human_review_required=True,
                    source_candidate_ids=list(getattr(source_lock, "source_candidate_ids", []) or []),
                    source_refs=refs,
                )
            )
        return contract_slots


class LiveOrderContractParameterizationBuilder:
    def __init__(
        self,
        config: LiveOrderContractParameterizationConfig | None = None,
        slot_builder: LiveOrderContractParameterSlotBuilder | None = None,
    ):
        self.config = config or LiveOrderContractParameterizationConfig.from_config()
        self.slot_builder = slot_builder or LiveOrderContractParameterSlotBuilder()

    def build(
        self,
        approval_lock,
        approval_lock_validation,
        value_proposal,
        value_proposal_validation,
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
        require_approved_semantic_values: bool = False,
    ) -> LiveOrderContractParameterizationBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(approval_lock, "created_at", "")
            or getattr(value_proposal, "created_at", "")
            or getattr(parameter_draft, "created_at", "")
            or getattr(parameter_source_boundary, "created_at", "")
            or getattr(parameter_policy_spec, "created_at", "")
            or getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(approval_lock, "source_refs", []) or [])
            + list(getattr(approval_lock_validation, "source_refs", []) or [])
            + list(getattr(value_proposal, "source_refs", []) or [])
            + list(getattr(value_proposal_validation, "source_refs", []) or [])
            + list(getattr(parameter_draft, "source_refs", []) or [])
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
        approved_parameters = getattr(approval_lock, "approved_semantic_parameters", None)
        approved_integrity_valid = bool(
            approved_parameters is not None
            and callable(getattr(approval_lock, "approved_semantic_integrity_valid", None))
            and approval_lock.approved_semantic_integrity_valid()
        )
        approved_values_hash = approved_parameters.canonical_values_hash if approved_integrity_valid else ""
        artifact_hash = (
            approved_values_hash
            or getattr(approval_lock, "artifact_hash", "")
            or getattr(value_proposal, "artifact_hash", "")
            or getattr(parameter_draft, "artifact_hash", "")
            or getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(approval_lock, "idempotency_key", "")
            or getattr(value_proposal, "idempotency_key", "")
            or getattr(parameter_draft, "idempotency_key", "")
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
                    "live_order_contract_parameterization_v1",
                    base_idempotency,
                    getattr(approval_lock, "approval_lock_id", ""),
                    getattr(approval_lock_validation, "validation_report_id", ""),
                    getattr(value_proposal, "proposal_id", ""),
                    getattr(contract_skeleton, "contract_skeleton_id", ""),
                    approved_values_hash,
                ]
            )
        )

        blockers: list[str] = []
        if approved_parameters is not None and not approved_integrity_valid:
            blockers.append("APPROVED_SEMANTIC_VALUES_INTEGRITY_FAILED")
        if require_approved_semantic_values and not approved_integrity_valid:
            blockers.append("APPROVED_SEMANTIC_VALUES_REQUIRED")
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if approval_lock is None and self.config.require_approval_lock:
            blockers.append("MISSING_APPROVAL_LOCK")
        if approval_lock_validation is None and self.config.require_approval_lock_validation:
            blockers.append("MISSING_APPROVAL_LOCK_VALIDATION")
        if self.config.require_approval_lock_validation and getattr(approval_lock_validation, "valid", False) is not True:
            blockers.append("MISSING_APPROVAL_LOCK_VALIDATION")
        if self.config.require_parameterization_workflow_allowed:
            if getattr(approval_lock_validation, "contract_parameterization_workflow_allowed", False) is not True:
                blockers.append("CONTRACT_PARAMETERIZATION_NOT_ALLOWED")
            if getattr(approval_lock, "contract_parameterization_workflow_allowed", False) is not True:
                blockers.append("CONTRACT_PARAMETERIZATION_NOT_ALLOWED")
        if value_proposal is None and self.config.require_value_proposal:
            blockers.append("MISSING_VALUE_PROPOSAL")
        if parameter_draft is None and self.config.require_parameter_draft:
            blockers.append("MISSING_PARAMETER_DRAFT")
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
            blockers.append("EXPIRED_PARAMETERIZATION")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_PARAMETERIZATION")
        if _raw_values_present(approval_lock, value_proposal, parameter_draft) and self.config.reject_raw_values:
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if getattr(approval_lock, "executable_order_created", False) is not False:
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if _mt5_payload_present(approval_lock, value_proposal, parameter_draft, parameter_source_boundary, parameter_policy_spec, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if _order_contract_ready_present(approval_lock, value_proposal, parameter_draft, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if any(getattr(item, "order_request_mapping_allowed", False) is not False for item in [approval_lock, value_proposal, contract_skeleton] if item is not None):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
            approval_lock,
            approval_lock_validation,
            value_proposal,
            value_proposal_validation,
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

        contract_slots = self.slot_builder.build_slots(approval_lock, source_refs)
        slot_types = {slot.slot_type for slot in contract_slots}
        missing_contract_slot_types = [item for item in REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES if item not in slot_types]
        invalid_contract_slot_types = [
            slot.slot_type
            for slot in contract_slots
            if slot.raw_value_stored
            or slot.executable_value
            or slot.mt5_payload_value
            or slot.order_request_value
            or not slot.parameterized_for_validation_only
            or not slot.contract_validation_required
            or not slot.final_human_review_required
        ]
        if missing_contract_slot_types or len(contract_slots) != len(REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES):
            blockers.append("MISSING_REQUIRED_CONTRACT_SLOTS")
        if invalid_contract_slot_types:
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if self.config.require_final_human_review and any(slot.final_human_review_required is not True for slot in contract_slots):
            blockers.append("INVALID_INPUT")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "PARAMETERIZATION_BOUNDARY_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_PARAMETERIZATION" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_PARAMETERIZATION" in blockers:
            status = "DUPLICATE"
        scope = "CONTRACT_VALIDATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        parameterized_slot_types = [slot.slot_type for slot in contract_slots if allowed and slot.parameterized_for_validation_only]
        parameterization = LiveOrderContractParameterizationBoundary(
            parameterization_id=f"live_order_contract_parameterization_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(approval_lock, "mode", getattr(value_proposal, "mode", "REVIEW_ONLY")),
            symbol=getattr(approval_lock, "symbol", getattr(value_proposal, "symbol", "")),
            broker_symbol=getattr(approval_lock, "broker_symbol", getattr(value_proposal, "broker_symbol", "")),
            status=status,
            scope=scope,
            contract_validation_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            raw_values_stored=False,
            executable_order_created=False,
            source_approval_lock_id=getattr(approval_lock, "approval_lock_id", ""),
            source_approval_lock_validation_id=getattr(approval_lock_validation, "validation_report_id", ""),
            source_value_proposal_id=getattr(value_proposal, "proposal_id", ""),
            source_value_proposal_validation_id=getattr(value_proposal_validation, "validation_report_id", ""),
            source_parameter_draft_id=getattr(parameter_draft, "draft_id", ""),
            source_parameter_draft_validation_id=getattr(parameter_draft_validation, "validation_report_id", ""),
            source_parameter_source_boundary_id=getattr(parameter_source_boundary, "boundary_id", ""),
            source_parameter_policy_spec_id=getattr(parameter_policy_spec, "policy_spec_id", ""),
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            contract_slots=contract_slots,
            required_contract_slot_types=list(REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES),
            parameterized_slot_types=parameterized_slot_types,
            missing_contract_slot_types=missing_contract_slot_types,
            invalid_contract_slot_types=invalid_contract_slot_types,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        parameterization.payload_size_chars = len(json.dumps(parameterization.as_dict(), ensure_ascii=False, sort_keys=True))
        return parameterization


def _parameter_group_from_slot(slot_type: str) -> str:
    return slot_type.replace("_CONTRACT_SLOT", "_POLICY")


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
        if getattr(item, "order_request_mapping_allowed", False) is not False:
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


def _raw_values_present(*items) -> bool:
    return any(getattr(item, "raw_values_stored", False) is not False for item in items if item is not None)


def _executable_order_present(*items) -> bool:
    return any(getattr(item, "executable", False) is not False for item in items if item is not None)


def _mt5_payload_present(*items) -> bool:
    return any(getattr(item, "mt5_payload_created", False) is not False for item in items if item is not None)


def _order_contract_ready_present(*items) -> bool:
    return any(getattr(item, "order_contract_ready", False) is not False for item in items if item is not None)


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
