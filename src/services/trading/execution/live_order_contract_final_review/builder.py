from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_contract_final_review.confirmation import (
    LiveOrderContractFinalReviewConfirmationService,
)
from src.services.trading.execution.live_order_contract_final_review.models import (
    REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES,
    LiveOrderContractFinalReview,
    LiveOrderContractFinalReviewConfirmation,
    LiveOrderContractSlotValidation,
)
from src.services.trading.execution.live_order_contract_final_review.policy import (
    LiveOrderContractFinalReviewConfig,
)


class LiveOrderContractSlotValidationBuilder:
    def build_slot_validations(
        self, parameterization, source_refs: list[str] | None = None
    ) -> list[LiveOrderContractSlotValidation]:
        refs = list(source_refs or [])
        slots_by_type = {
            str(getattr(slot, "slot_type", "")): slot
            for slot in getattr(parameterization, "contract_slots", []) or []
        }
        validations: list[LiveOrderContractSlotValidation] = []
        for slot_type in REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES:
            source_slot = slots_by_type.get(slot_type)
            blockers: list[str] = []
            if source_slot is None:
                blockers.append("MISSING_REQUIRED_SLOT_VALIDATIONS")
            elif (
                getattr(source_slot, "raw_value_stored", False)
                or getattr(source_slot, "executable_value", False)
                or getattr(source_slot, "mt5_payload_value", False)
                or getattr(source_slot, "order_request_value", False)
                or not getattr(source_slot, "parameterized_for_validation_only", False)
                or not getattr(source_slot, "final_human_review_required", False)
            ):
                blockers.append("INVALID_INPUT")
            validations.append(
                LiveOrderContractSlotValidation(
                    slot_validation_id=f"live_order_contract_slot_validation_{slot_type.lower()}",
                    source_contract_slot_id=str(getattr(source_slot, "contract_slot_id", "")),
                    source_slot_lock_id=str(getattr(source_slot, "source_slot_lock_id", "")),
                    source_value_slot_id=str(getattr(source_slot, "source_value_slot_id", "")),
                    slot_type=slot_type,
                    status="VALIDATION_ONLY_READY" if not blockers else "BLOCKED",
                    severity="INFO" if not blockers else "BLOCKING",
                    validation_only_ready=not blockers,
                    raw_value_stored=False,
                    executable_value=False,
                    mt5_payload_value=False,
                    order_request_value=False,
                    broker_mapping_created=False,
                    final_human_review_required=True,
                    source_refs=refs,
                    blockers=blockers,
                    warnings=[],
                )
            )
        return validations


class LiveOrderContractFinalReviewBuilder:
    def __init__(
        self,
        config: LiveOrderContractFinalReviewConfig | None = None,
        slot_validation_builder: LiveOrderContractSlotValidationBuilder | None = None,
        confirmation_service: LiveOrderContractFinalReviewConfirmationService | None = None,
    ):
        self.config = config or LiveOrderContractFinalReviewConfig.from_config()
        self.slot_validation_builder = slot_validation_builder or LiveOrderContractSlotValidationBuilder()
        self.confirmation_service = confirmation_service or LiveOrderContractFinalReviewConfirmationService(self.config)

    def build(
        self,
        parameterization,
        parameterization_validation,
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
        confirmation_phrase: str | None = None,
        confirmation: LiveOrderContractFinalReviewConfirmation | None = None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LiveOrderContractFinalReview:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(parameterization, "created_at", "")
            or getattr(approval_lock, "created_at", "")
            or getattr(value_proposal, "created_at", "")
            or getattr(parameter_draft, "created_at", "")
            or getattr(parameter_source_boundary, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(parameterization, "source_refs", []) or [])
            + list(getattr(parameterization_validation, "source_refs", []) or [])
            + list(getattr(approval_lock, "source_refs", []) or [])
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
        confirmation = confirmation or self.confirmation_service.confirm(confirmation_phrase, now, source_refs)
        artifact_hash = (
            getattr(parameterization, "artifact_hash", "")
            or getattr(approval_lock, "artifact_hash", "")
            or getattr(value_proposal, "artifact_hash", "")
            or getattr(parameter_draft, "artifact_hash", "")
            or getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(parameterization, "idempotency_key", "")
            or getattr(approval_lock, "idempotency_key", "")
            or getattr(value_proposal, "idempotency_key", "")
            or getattr(parameter_draft, "idempotency_key", "")
            or getattr(parameter_source_boundary, "idempotency_key", "")
            or getattr(parameter_policy_spec, "idempotency_key", "")
            or getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "live_order_contract_final_review_v1",
                    base_idempotency,
                    getattr(parameterization, "parameterization_id", ""),
                    getattr(parameterization_validation, "validation_report_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if parameterization is None and self.config.require_parameterization:
            blockers.append("MISSING_PARAMETERIZATION")
        if parameterization_validation is None and self.config.require_parameterization_validation:
            blockers.append("MISSING_PARAMETERIZATION_VALIDATION")
        if self.config.require_parameterization_validation and getattr(parameterization_validation, "valid", False) is not True:
            blockers.append("MISSING_PARAMETERIZATION_VALIDATION")
        if self.config.require_contract_validation_workflow_allowed:
            if getattr(parameterization_validation, "contract_validation_workflow_allowed", False) is not True:
                blockers.append("CONTRACT_VALIDATION_WORKFLOW_NOT_ALLOWED")
            if getattr(parameterization, "contract_validation_workflow_allowed", False) is not True:
                blockers.append("CONTRACT_VALIDATION_WORKFLOW_NOT_ALLOWED")
        if approval_lock is None and self.config.require_approval_lock:
            blockers.append("MISSING_APPROVAL_LOCK")
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
        if self.config.require_exact_confirmation and getattr(confirmation, "phrase_valid", False) is not True:
            blockers.append("WRONG_CONFIRMATION_PHRASE")
        if "CONFIRMATION_EXPIRED" in list(getattr(confirmation, "blockers", []) or []):
            blockers.append("CONFIRMATION_EXPIRED")
        if getattr(confirmation, "action", "") != "APPROVE_FOR_FUTURE_PRE_MT5_MAPPING_ONLY":
            blockers.append("FINAL_HUMAN_REVIEW_NOT_APPROVED")
        if now > expires_at_dt:
            blockers.append("EXPIRED_FINAL_REVIEW")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_FINAL_REVIEW")
        if _raw_values_present(parameterization, approval_lock, value_proposal, parameter_draft) and self.config.reject_raw_values:
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if _mt5_payload_present(parameterization, approval_lock, value_proposal, parameter_draft, parameter_source_boundary, parameter_policy_spec, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if _order_contract_ready_present(parameterization, approval_lock, value_proposal, parameter_draft, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(parameterization, approval_lock, value_proposal, contract_skeleton) and self.config.reject_broker_mapping:
            blockers.append("PRE_MT5_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
            parameterization,
            parameterization_validation,
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

        slot_validations = self.slot_validation_builder.build_slot_validations(parameterization, source_refs)
        slot_types = {slot.slot_type for slot in slot_validations}
        missing_slot_validation_types = [item for item in REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES if item not in slot_types]
        blocked_slot_validation_types = [slot.slot_type for slot in slot_validations if slot.blockers or slot.status != "VALIDATION_ONLY_READY"]
        if missing_slot_validation_types or len(slot_validations) != len(REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES):
            blockers.append("MISSING_REQUIRED_SLOT_VALIDATIONS")
        if blocked_slot_validation_types:
            blockers.append("MISSING_REQUIRED_SLOT_VALIDATIONS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "FINAL_REVIEW_APPROVED_FOR_MAPPING_BOUNDARY" if allowed else "BLOCKED"
        if "EXPIRED_FINAL_REVIEW" in blockers or "CONFIRMATION_EXPIRED" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_FINAL_REVIEW" in blockers:
            status = "DUPLICATE"
        if "WRONG_CONFIRMATION_PHRASE" in blockers or "FINAL_HUMAN_REVIEW_NOT_APPROVED" in blockers:
            status = "REJECTED"
        scope = "PRE_MT5_MAPPING_BOUNDARY_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        passed_slot_validation_types = [
            slot.slot_type for slot in slot_validations if allowed and slot.status == "VALIDATION_ONLY_READY"
        ]
        final_review = LiveOrderContractFinalReview(
            final_review_id=f"live_order_contract_final_review_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(parameterization, "mode", getattr(approval_lock, "mode", "REVIEW_ONLY")),
            symbol=getattr(parameterization, "symbol", getattr(approval_lock, "symbol", "")),
            broker_symbol=getattr(parameterization, "broker_symbol", getattr(approval_lock, "broker_symbol", "")),
            status=status,
            scope=scope,
            pre_mt5_mapping_boundary_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            source_parameterization_id=getattr(parameterization, "parameterization_id", ""),
            source_parameterization_validation_id=getattr(parameterization_validation, "validation_report_id", ""),
            source_approval_lock_id=getattr(approval_lock, "approval_lock_id", ""),
            source_approval_lock_validation_id=getattr(approval_lock_validation, "validation_report_id", ""),
            source_value_proposal_id=getattr(value_proposal, "proposal_id", ""),
            source_parameter_draft_id=getattr(parameter_draft, "draft_id", ""),
            source_parameter_source_boundary_id=getattr(parameter_source_boundary, "boundary_id", ""),
            source_parameter_policy_spec_id=getattr(parameter_policy_spec, "policy_spec_id", ""),
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            confirmation_id=getattr(confirmation, "confirmation_id", ""),
            confirmation_phrase_valid=bool(getattr(confirmation, "phrase_valid", False)) and allowed,
            final_review_action=getattr(confirmation, "action", "UNKNOWN"),
            final_review_state=getattr(confirmation, "review_state", "UNKNOWN"),
            slot_validations=slot_validations,
            required_slot_validation_types=list(REQUIRED_CONTRACT_SLOT_VALIDATION_TYPES),
            passed_slot_validation_types=passed_slot_validation_types,
            blocked_slot_validation_types=blocked_slot_validation_types,
            missing_slot_validation_types=missing_slot_validation_types,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        final_review.payload_size_chars = len(json.dumps(final_review.as_dict(), ensure_ascii=False, sort_keys=True))
        return final_review


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
        if getattr(item, "broker_mapping_created", False) is not False:
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
    return any(
        getattr(item, "executable", False) is not False
        or getattr(item, "executable_order_created", False) is not False
        for item in items
        if item is not None
    )


def _mt5_payload_present(*items) -> bool:
    return any(getattr(item, "mt5_payload_created", False) is not False for item in items if item is not None)


def _order_contract_ready_present(*items) -> bool:
    return any(getattr(item, "order_contract_ready", False) is not False for item in items if item is not None)


def _order_request_mapping_present(*items) -> bool:
    return any(getattr(item, "order_request_mapping_allowed", False) is not False for item in items if item is not None)


def _broker_mapping_present(*items) -> bool:
    return any(getattr(item, "broker_mapping_created", False) is not False for item in items if item is not None)


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
