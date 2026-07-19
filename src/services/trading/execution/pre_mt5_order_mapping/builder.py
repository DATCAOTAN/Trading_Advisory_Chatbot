from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.pre_mt5_order_mapping.models import (
    REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES,
    PreMT5MappingSlot,
    PreMT5OrderRequestMappingBoundary,
)
from src.services.trading.execution.pre_mt5_order_mapping.policy import (
    PreMT5OrderRequestMappingConfig,
)


CONTRACT_SLOT_BY_MAPPING_SLOT = {
    "ACTION_MAPPING_SLOT": "SIDE_CONTRACT_SLOT",
    "SYMBOL_MAPPING_SLOT": "BROKER_SYMBOL_CONTRACT_SLOT",
    "VOLUME_MAPPING_SLOT": "VOLUME_CONTRACT_SLOT",
    "ORDER_TYPE_MAPPING_SLOT": "SIDE_CONTRACT_SLOT",
    "PRICE_MAPPING_SLOT": "PRICE_CONTRACT_SLOT",
    "PROTECTION_MAPPING_SLOT": "PROTECTION_CONTRACT_SLOT",
    "DEVIATION_MAPPING_SLOT": "EXECUTION_TIMING_CONTRACT_SLOT",
    "MAGIC_MAPPING_SLOT": "AUDIT_CONTRACT_SLOT",
    "COMMENT_MAPPING_SLOT": "AUDIT_CONTRACT_SLOT",
    "IDEMPOTENCY_MAPPING_SLOT": "IDEMPOTENCY_CONTRACT_SLOT",
    "AUDIT_MAPPING_SLOT": "AUDIT_CONTRACT_SLOT",
}
FUTURE_FIELD_LABELS = {
    "ACTION_MAPPING_SLOT": "schema_action",
    "SYMBOL_MAPPING_SLOT": "schema_symbol",
    "VOLUME_MAPPING_SLOT": "schema_volume",
    "ORDER_TYPE_MAPPING_SLOT": "schema_order_type",
    "PRICE_MAPPING_SLOT": "schema_price",
    "PROTECTION_MAPPING_SLOT": "schema_protection",
    "DEVIATION_MAPPING_SLOT": "schema_deviation",
    "MAGIC_MAPPING_SLOT": "schema_magic",
    "COMMENT_MAPPING_SLOT": "schema_comment",
    "IDEMPOTENCY_MAPPING_SLOT": "schema_idempotency",
    "AUDIT_MAPPING_SLOT": "schema_audit",
}


class PreMT5MappingSlotBuilder:
    def build_slots(self, final_review, source_refs: list[str] | None = None) -> list[PreMT5MappingSlot]:
        refs = list(source_refs or [])
        validations_by_type = {
            str(getattr(slot, "slot_type", "")): slot
            for slot in getattr(final_review, "slot_validations", []) or []
        }
        mapping_slots: list[PreMT5MappingSlot] = []
        for slot_type in REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES:
            source_validation = validations_by_type.get(CONTRACT_SLOT_BY_MAPPING_SLOT.get(slot_type, ""))
            blockers: list[str] = []
            if source_validation is None:
                blockers.append("MISSING_REQUIRED_MAPPING_SLOTS")
            elif (
                getattr(source_validation, "raw_value_stored", False)
                or getattr(source_validation, "executable_value", False)
                or getattr(source_validation, "mt5_payload_value", False)
                or getattr(source_validation, "order_request_value", False)
                or getattr(source_validation, "broker_mapping_created", False)
                or not getattr(source_validation, "validation_only_ready", False)
                or not getattr(source_validation, "final_human_review_required", False)
            ):
                blockers.append("INVALID_INPUT")
            mapping_slots.append(
                PreMT5MappingSlot(
                    mapping_slot_id=f"pre_mt5_mapping_slot_{slot_type.lower()}",
                    source_final_review_slot_validation_id=str(getattr(source_validation, "slot_validation_id", "")),
                    source_contract_slot_id=str(getattr(source_validation, "source_contract_slot_id", "")),
                    source_slot_lock_id=str(getattr(source_validation, "source_slot_lock_id", "")),
                    source_value_slot_id=str(getattr(source_validation, "source_value_slot_id", "")),
                    slot_type=slot_type,
                    status="MAPPED_AS_SCHEMA_ONLY" if not blockers else "BLOCKED",
                    value_state="SCHEMA_ONLY" if not blockers else "BLOCKED",
                    mapped_as_schema_only=True,
                    dry_run_payload_validation_required=True,
                    raw_value_stored=False,
                    mt5_payload_value_created=False,
                    mt5_request_field_value_created=False,
                    executable_order_value=False,
                    broker_submission_value=False,
                    source_refs=refs,
                    source_candidate_ids=[],
                    future_mt5_field_label=FUTURE_FIELD_LABELS[slot_type],
                    future_validation_requirements=[
                        "schema_only",
                        "dry_run_payload_validator_required",
                        "no_raw_value",
                        "no_payload_value",
                        "source_chain_required",
                    ],
                    blockers=blockers,
                    warnings=[],
                )
            )
        return mapping_slots


class PreMT5OrderRequestMappingBuilder:
    def __init__(
        self,
        config: PreMT5OrderRequestMappingConfig | None = None,
        slot_builder: PreMT5MappingSlotBuilder | None = None,
    ):
        self.config = config or PreMT5OrderRequestMappingConfig.from_config()
        self.slot_builder = slot_builder or PreMT5MappingSlotBuilder()

    def build(
        self,
        final_review,
        final_review_validation,
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
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> PreMT5OrderRequestMappingBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(final_review, "created_at", "")
            or getattr(parameterization, "created_at", "")
            or getattr(approval_lock, "created_at", "")
            or getattr(value_proposal, "created_at", "")
            or getattr(parameter_draft, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(final_review, "source_refs", []) or [])
            + list(getattr(final_review_validation, "source_refs", []) or [])
            + list(getattr(parameterization, "source_refs", []) or [])
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
        artifact_hash = (
            getattr(final_review, "artifact_hash", "")
            or getattr(parameterization, "artifact_hash", "")
            or getattr(approval_lock, "artifact_hash", "")
            or getattr(value_proposal, "artifact_hash", "")
            or getattr(parameter_draft, "artifact_hash", "")
            or getattr(parameter_source_boundary, "artifact_hash", "")
            or getattr(parameter_policy_spec, "artifact_hash", "")
            or getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(final_review, "idempotency_key", "")
            or getattr(parameterization, "idempotency_key", "")
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
                    "pre_mt5_order_request_mapping_v1",
                    base_idempotency,
                    getattr(final_review, "final_review_id", ""),
                    getattr(final_review_validation, "validation_report_id", ""),
                    getattr(parameterization, "parameterization_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if final_review is None and self.config.require_final_review:
            blockers.append("MISSING_FINAL_REVIEW")
        if final_review_validation is None and self.config.require_final_review_validation:
            blockers.append("MISSING_FINAL_REVIEW_VALIDATION")
        if self.config.require_final_review_validation and getattr(final_review_validation, "valid", False) is not True:
            blockers.append("MISSING_FINAL_REVIEW_VALIDATION")
        if self.config.require_pre_mt5_workflow_allowed:
            if getattr(final_review_validation, "pre_mt5_mapping_boundary_workflow_allowed", False) is not True:
                blockers.append("PRE_MT5_MAPPING_WORKFLOW_NOT_ALLOWED")
            if getattr(final_review, "pre_mt5_mapping_boundary_workflow_allowed", False) is not True:
                blockers.append("PRE_MT5_MAPPING_WORKFLOW_NOT_ALLOWED")
        if parameterization is None and self.config.require_parameterization:
            blockers.append("MISSING_PARAMETERIZATION")
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
        if now > expires_at_dt:
            blockers.append("EXPIRED_MAPPING_BOUNDARY")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_MAPPING_BOUNDARY")
        if _raw_values_present(final_review, parameterization, approval_lock, value_proposal, parameter_draft):
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(final_review, parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if self.config.reject_mt5_payload and _mt5_payload_present(
            final_review,
            parameterization,
            approval_lock,
            value_proposal,
            parameter_draft,
            parameter_source_boundary,
            parameter_policy_spec,
            contract_skeleton,
        ):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if self.config.reject_mt5_request_dict and _mt5_request_dict_present(final_review, parameterization, contract_skeleton):
            blockers.append("MT5_REQUEST_DICT_NOT_ALLOWED")
        if _order_contract_ready_present(final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
            final_review,
            final_review_validation,
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

        mapping_slots = self.slot_builder.build_slots(final_review, source_refs)
        slot_types = {slot.slot_type for slot in mapping_slots}
        missing_mapping_slot_types = [item for item in REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES if item not in slot_types]
        invalid_mapping_slot_types = [
            slot.slot_type
            for slot in mapping_slots
            if slot.blockers
            or slot.status != "MAPPED_AS_SCHEMA_ONLY"
            or not slot.mapped_as_schema_only
            or not slot.dry_run_payload_validation_required
            or slot.raw_value_stored
            or slot.mt5_payload_value_created
            or slot.mt5_request_field_value_created
            or slot.executable_order_value
            or slot.broker_submission_value
        ]
        if missing_mapping_slot_types or len(mapping_slots) != len(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES):
            blockers.append("MISSING_REQUIRED_MAPPING_SLOTS")
        if invalid_mapping_slot_types:
            blockers.append("MISSING_REQUIRED_MAPPING_SLOTS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "MAPPING_BOUNDARY_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_MAPPING_BOUNDARY" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_MAPPING_BOUNDARY" in blockers:
            status = "DUPLICATE"
        scope = "MT5_DRY_RUN_PAYLOAD_VALIDATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        mapped_slot_types = [slot.slot_type for slot in mapping_slots if allowed and slot.status == "MAPPED_AS_SCHEMA_ONLY"]
        boundary = PreMT5OrderRequestMappingBoundary(
            mapping_boundary_id=f"pre_mt5_mapping_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(final_review, "mode", getattr(parameterization, "mode", "MAPPING_BOUNDARY_ONLY")),
            symbol=getattr(final_review, "symbol", getattr(parameterization, "symbol", "")),
            broker_symbol=getattr(final_review, "broker_symbol", getattr(parameterization, "broker_symbol", "")),
            status=status,
            scope=scope,
            mt5_dry_run_payload_validation_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            source_final_review_id=getattr(final_review, "final_review_id", ""),
            source_final_review_validation_id=getattr(final_review_validation, "validation_report_id", ""),
            source_parameterization_id=getattr(parameterization, "parameterization_id", ""),
            source_parameterization_validation_id=getattr(parameterization_validation, "validation_report_id", ""),
            source_approval_lock_id=getattr(approval_lock, "approval_lock_id", ""),
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
            mapping_slots=mapping_slots,
            required_mapping_slot_types=list(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES),
            mapped_slot_types=mapped_slot_types,
            missing_mapping_slot_types=missing_mapping_slot_types,
            invalid_mapping_slot_types=invalid_mapping_slot_types,
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
        if getattr(item, "mt5_request_dict_created", False) is not False:
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


def _mt5_request_dict_present(*items) -> bool:
    return any(getattr(item, "mt5_request_dict_created", False) is not False for item in items if item is not None)


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
