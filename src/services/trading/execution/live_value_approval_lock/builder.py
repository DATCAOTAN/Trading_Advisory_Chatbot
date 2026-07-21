from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping

from src.services.trading.execution.live_value_approval_lock.confirmation import (
    HumanValueApprovalConfirmationService,
)
from src.services.trading.execution.live_value_approval_lock.models import (
    REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES,
    ApprovedSemanticExecutionParameters,
    HumanValueApprovalLock,
    HumanValueApprovalSlotLock,
)
from src.services.trading.execution.live_value_approval_lock.policy import HumanValueApprovalLockConfig


class HumanValueApprovalSlotLockBuilder:
    def build_slot_locks(
        self,
        value_proposal,
        confirmation_valid: bool,
        source_refs: list[str] | None = None,
    ) -> list[HumanValueApprovalSlotLock]:
        refs = list(source_refs or [])
        slots_by_type = {str(getattr(slot, "slot_type", "")): slot for slot in getattr(value_proposal, "value_slots", []) or []}
        slot_locks: list[HumanValueApprovalSlotLock] = []
        for slot_type in REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES:
            source_slot = slots_by_type.get(slot_type)
            locked = bool(confirmation_valid)
            slot_locks.append(
                HumanValueApprovalSlotLock(
                    slot_lock_id=f"human_value_approval_slot_lock_{slot_type.lower()}",
                    source_value_slot_id=str(getattr(source_slot, "value_slot_id", "")),
                    source_draft_slot_id=str(getattr(source_slot, "source_draft_slot_id", "")),
                    slot_type=slot_type,
                    status="LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY" if locked else "REVIEW_REQUIRED",
                    review_state=(
                        "HUMAN_APPROVED_FOR_FUTURE_PARAMETERIZATION_ONLY" if locked else "NOT_REVIEWED"
                    ),
                    lock_state="LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY" if locked else "NOT_LOCKED",
                    approved_for_future_parameterization=locked,
                    raw_value_stored=False,
                    executable_value=False,
                    mt5_payload_value=False,
                    order_value=False,
                    value_payload_redacted=True,
                    source_candidate_ids=list(getattr(source_slot, "source_candidate_ids", []) or []),
                    source_refs=refs,
                )
            )
        return slot_locks


class HumanValueApprovalLockBuilder:
    def __init__(
        self,
        config: HumanValueApprovalLockConfig | None = None,
        slot_lock_builder: HumanValueApprovalSlotLockBuilder | None = None,
        confirmation_service: HumanValueApprovalConfirmationService | None = None,
    ):
        self.config = config or HumanValueApprovalLockConfig.from_config()
        self.slot_lock_builder = slot_lock_builder or HumanValueApprovalSlotLockBuilder()
        self.confirmation_service = confirmation_service or HumanValueApprovalConfirmationService(self.config)

    def build(
        self,
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
        confirmation_phrase: str | None = None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
        existing_confirmation_ids: Iterable[str] | None = None,
        approved_semantic_values: Mapping[str, object] | None = None,
    ) -> HumanValueApprovalLock:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(value_proposal, "created_at", "")
            or getattr(parameter_draft, "created_at", "")
            or getattr(parameter_source_boundary, "created_at", "")
            or getattr(parameter_policy_spec, "created_at", "")
            or getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(value_proposal, "source_refs", []) or [])
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
        artifact_hash = (
            getattr(value_proposal, "artifact_hash", "")
            or getattr(parameter_draft, "artifact_hash", "")
            or getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(value_proposal, "idempotency_key", "")
            or getattr(parameter_draft, "idempotency_key", "")
            or getattr(parameter_source_boundary, "idempotency_key", "")
            or getattr(parameter_policy_spec, "idempotency_key", "")
            or getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        confirmation = self.confirmation_service.confirm(
            confirmation_phrase,
            source_refs=source_refs,
            current_time=now,
            existing_confirmation_ids=existing_confirmation_ids,
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "human_value_approval_lock_v1",
                    base_idempotency,
                    getattr(value_proposal, "proposal_id", ""),
                    getattr(value_proposal_validation, "validation_report_id", ""),
                    getattr(parameter_draft, "draft_id", ""),
                    confirmation.phrase,
                ]
            )
        )
        approval_lock_id = f"human_value_approval_lock_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}"
        approved_parameters = None
        approved_parameters_invalid = False
        if approved_semantic_values is not None:
            try:
                approved_parameters = ApprovedSemanticExecutionParameters.from_mapping(
                    approved_semantic_values,
                    approval_artifact_ref=confirmation.confirmation_id,
                    lock_artifact_ref=approval_lock_id,
                    source_artifact_ref=str(getattr(value_proposal, "proposal_id", "")),
                    approved_at=confirmation.created_at,
                    locked_at=created_at,
                )
                confirmation.approved_semantic_values_hash = approved_parameters.canonical_values_hash
                artifact_hash = approved_parameters.canonical_values_hash
            except (TypeError, ValueError):
                approved_parameters_invalid = True

        blockers: list[str] = []
        if approved_parameters_invalid:
            blockers.append("INVALID_APPROVED_SEMANTIC_VALUES")
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if value_proposal is None and self.config.require_value_proposal:
            blockers.append("MISSING_VALUE_PROPOSAL")
        if value_proposal_validation is None and self.config.require_value_proposal_validation:
            blockers.append("MISSING_VALUE_PROPOSAL_VALIDATION")
        if self.config.require_value_proposal_validation and getattr(value_proposal_validation, "valid", False) is not True:
            blockers.append("MISSING_VALUE_PROPOSAL_VALIDATION")
        if self.config.require_human_value_approval_allowed:
            if getattr(value_proposal_validation, "human_value_approval_allowed", False) is not True:
                blockers.append("HUMAN_VALUE_APPROVAL_NOT_ALLOWED")
            if getattr(value_proposal, "human_value_approval_allowed", False) is not True:
                blockers.append("HUMAN_VALUE_APPROVAL_NOT_ALLOWED")
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
        if self.config.require_exact_confirmation and not confirmation.phrase_valid:
            blockers.extend(confirmation.blockers or ["WRONG_CONFIRMATION_PHRASE"])
        if now > expires_at_dt:
            blockers.append("EXPIRED_APPROVAL_LOCK")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_APPROVAL_LOCK")
        if self.config.require_value_lock and getattr(value_proposal, "value_lock_required", False) is not True:
            blockers.append("VALUE_LOCK_NOT_REQUIRED")
        if getattr(value_proposal, "human_review_required", False) is not True:
            blockers.append("HUMAN_REVIEW_NOT_APPROVED")
        if _unsafe_execution_flags(
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
        if _executable_order_present(value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if _mt5_payload_present(value_proposal, parameter_draft, parameter_source_boundary, parameter_policy_spec, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if getattr(value_proposal, "order_contract_ready", False) is not False:
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")

        slot_locks = self.slot_lock_builder.build_slot_locks(value_proposal, confirmation.phrase_valid, source_refs)
        slot_types = {slot_lock.slot_type for slot_lock in slot_locks}
        missing_slot_lock_types = [item for item in REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES if item not in slot_types]
        if missing_slot_lock_types or len(slot_locks) != len(REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES):
            blockers.append("MISSING_REQUIRED_LOCK_SLOTS")
        if any(slot.raw_value_stored for slot in slot_locks):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if any(slot.executable_value or slot.mt5_payload_value or slot.order_value for slot in slot_locks):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if any(slot.value_payload_redacted is not True for slot in slot_locks):
            blockers.append("VALUE_LOCK_NOT_ALLOWED")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "VALUES_LOCKED_FOR_CONTRACT_PARAMETERIZATION" if allowed else "BLOCKED"
        if "EXPIRED_APPROVAL_LOCK" in blockers or "CONFIRMATION_EXPIRED" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_APPROVAL_LOCK" in blockers:
            status = "DUPLICATE"
        if "WRONG_CONFIRMATION_PHRASE" in blockers:
            status = "REJECTED"
        scope = "CONTRACT_PARAMETERIZATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        locked_types = [slot.slot_type for slot in slot_locks if allowed and slot.approved_for_future_parameterization]
        lock = HumanValueApprovalLock(
            approval_lock_id=approval_lock_id,
            created_at=created_at,
            mode=getattr(value_proposal, "mode", getattr(parameter_draft, "mode", "REVIEW_ONLY")),
            symbol=getattr(value_proposal, "symbol", getattr(parameter_draft, "symbol", "")),
            broker_symbol=getattr(value_proposal, "broker_symbol", getattr(parameter_draft, "broker_symbol", "")),
            status=status,
            scope=scope,
            contract_parameterization_workflow_allowed=allowed,
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
            raw_values_stored=False,
            approved_semantic_parameters=approved_parameters,
            approved_semantic_values_hash=(approved_parameters.canonical_values_hash if approved_parameters else ""),
            approval_value_hash=(approved_parameters.canonical_values_hash if approved_parameters else ""),
            lock_value_hash=(approved_parameters.canonical_values_hash if approved_parameters else ""),
            executable_order_created=False,
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
            confirmation_id=confirmation.confirmation_id,
            confirmation_phrase_valid=confirmation.phrase_valid,
            approval_action=confirmation.action,
            review_state=confirmation.review_state if allowed else "REJECTED",
            lock_state="LOCKED_FOR_FUTURE_PARAMETERIZATION_ONLY" if allowed else "BLOCKED",
            slot_locks=slot_locks,
            required_slot_lock_types=list(REQUIRED_HUMAN_VALUE_SLOT_LOCK_TYPES),
            locked_slot_types=locked_types,
            rejected_slot_types=[],
            missing_slot_lock_types=missing_slot_lock_types,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        lock.payload_size_chars = len(json.dumps(lock.as_dict(), ensure_ascii=False, sort_keys=True))
        return lock


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
