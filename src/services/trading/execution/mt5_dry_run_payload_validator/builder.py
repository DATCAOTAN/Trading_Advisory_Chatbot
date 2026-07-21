from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.mt5_dry_run_payload_validator.models import (
    REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES,
    MT5DryRunPayloadFieldValidation,
    MT5OrderRequestDryRunPayloadValidation,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.policy import (
    MT5DryRunPayloadValidationConfig,
)


MAPPING_SLOT_BY_FIELD_CATEGORY = {
    "ACTION_FIELD": "ACTION_MAPPING_SLOT",
    "SYMBOL_FIELD": "SYMBOL_MAPPING_SLOT",
    "VOLUME_FIELD": "VOLUME_MAPPING_SLOT",
    "ORDER_TYPE_FIELD": "ORDER_TYPE_MAPPING_SLOT",
    "PRICE_FIELD": "PRICE_MAPPING_SLOT",
    "STOP_LOSS_FIELD": "PROTECTION_MAPPING_SLOT",
    "TAKE_PROFIT_FIELD": "PROTECTION_MAPPING_SLOT",
    "DEVIATION_FIELD": "DEVIATION_MAPPING_SLOT",
    "MAGIC_FIELD": "MAGIC_MAPPING_SLOT",
    "COMMENT_FIELD": "COMMENT_MAPPING_SLOT",
    "IDEMPOTENCY_FIELD": "IDEMPOTENCY_MAPPING_SLOT",
    "AUDIT_FIELD": "AUDIT_MAPPING_SLOT",
}
FUTURE_FIELD_LABELS = {
    "ACTION_FIELD": "schema_action",
    "SYMBOL_FIELD": "schema_symbol",
    "VOLUME_FIELD": "schema_volume",
    "ORDER_TYPE_FIELD": "schema_order_type",
    "PRICE_FIELD": "schema_price",
    "STOP_LOSS_FIELD": "schema_stop_loss",
    "TAKE_PROFIT_FIELD": "schema_take_profit",
    "DEVIATION_FIELD": "schema_deviation",
    "MAGIC_FIELD": "schema_magic",
    "COMMENT_FIELD": "schema_comment",
    "IDEMPOTENCY_FIELD": "schema_idempotency",
    "AUDIT_FIELD": "schema_audit",
}


class MT5DryRunPayloadFieldValidationBuilder:
    def build_field_validations(self, pre_mt5_mapping, source_refs: list[str] | None = None) -> list[MT5DryRunPayloadFieldValidation]:
        refs = list(source_refs or [])
        slots_by_type = {
            str(getattr(slot, "slot_type", "")): slot
            for slot in getattr(pre_mt5_mapping, "mapping_slots", []) or []
        }
        field_validations: list[MT5DryRunPayloadFieldValidation] = []
        for category in REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES:
            source_slot = slots_by_type.get(MAPPING_SLOT_BY_FIELD_CATEGORY.get(category, ""))
            blockers: list[str] = []
            if source_slot is None:
                blockers.append("MISSING_REQUIRED_PAYLOAD_FIELDS")
            elif (
                not getattr(source_slot, "mapped_as_schema_only", False)
                or not getattr(source_slot, "dry_run_payload_validation_required", False)
                or getattr(source_slot, "raw_value_stored", False)
                or getattr(source_slot, "mt5_payload_value_created", False)
                or getattr(source_slot, "mt5_request_field_value_created", False)
                or getattr(source_slot, "executable_order_value", False)
                or getattr(source_slot, "broker_submission_value", False)
            ):
                blockers.append("INVALID_INPUT")
            field_validations.append(
                MT5DryRunPayloadFieldValidation(
                    field_validation_id=f"mt5_dry_run_payload_field_{category.lower()}",
                    source_mapping_slot_id=str(getattr(source_slot, "mapping_slot_id", "")),
                    source_final_review_slot_validation_id=str(
                        getattr(source_slot, "source_final_review_slot_validation_id", "")
                    ),
                    field_category=category,
                    status="SCHEMA_VALIDATED" if not blockers else "BLOCKED",
                    value_state="SCHEMA_ONLY" if not blockers else "BLOCKED",
                    schema_present=not blockers,
                    value_created=False,
                    value_redacted=True,
                    raw_value_stored=False,
                    mt5_payload_value_created=False,
                    mt5_request_field_value_created=False,
                    mt5_constant_used=False,
                    executable_order_value=False,
                    broker_submission_value=False,
                    future_mt5_field_label=FUTURE_FIELD_LABELS[category],
                    validation_requirements=[
                        "schema_presence_only",
                        "value_redacted",
                        "no_value_created",
                        "no_payload_value",
                        "no_constant_used",
                    ],
                    source_refs=refs,
                    blockers=blockers,
                    warnings=[],
                )
            )
        return field_validations


class MT5OrderRequestDryRunPayloadValidationBuilder:
    def __init__(
        self,
        config: MT5DryRunPayloadValidationConfig | None = None,
        field_builder: MT5DryRunPayloadFieldValidationBuilder | None = None,
    ):
        self.config = config or MT5DryRunPayloadValidationConfig.from_config()
        self.field_builder = field_builder or MT5DryRunPayloadFieldValidationBuilder()

    def build(
        self,
        pre_mt5_mapping,
        pre_mt5_mapping_validation,
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
    ) -> MT5OrderRequestDryRunPayloadValidation:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(pre_mt5_mapping, "created_at", "")
            or getattr(final_review, "created_at", "")
            or getattr(parameterization, "created_at", "")
            or getattr(approval_lock, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(pre_mt5_mapping, "source_refs", []) or [])
            + list(getattr(pre_mt5_mapping_validation, "source_refs", []) or [])
            + list(getattr(final_review, "source_refs", []) or [])
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
            getattr(pre_mt5_mapping, "artifact_hash", "")
            or getattr(final_review, "artifact_hash", "")
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
            getattr(pre_mt5_mapping, "idempotency_key", "")
            or getattr(final_review, "idempotency_key", "")
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
                    "mt5_dry_run_payload_validation_v1",
                    base_idempotency,
                    getattr(pre_mt5_mapping, "mapping_boundary_id", ""),
                    getattr(pre_mt5_mapping_validation, "validation_report_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if pre_mt5_mapping is None and self.config.require_pre_mt5_mapping:
            blockers.append("MISSING_PRE_MT5_MAPPING")
        if pre_mt5_mapping_validation is None and self.config.require_pre_mt5_mapping_validation:
            blockers.append("MISSING_PRE_MT5_MAPPING_VALIDATION")
        if self.config.require_pre_mt5_mapping_validation and getattr(pre_mt5_mapping_validation, "valid", False) is not True:
            blockers.append("MISSING_PRE_MT5_MAPPING_VALIDATION")
        if self.config.require_workflow_allowed:
            if getattr(pre_mt5_mapping_validation, "mt5_dry_run_payload_validation_workflow_allowed", False) is not True:
                blockers.append("DRY_RUN_PAYLOAD_VALIDATION_WORKFLOW_NOT_ALLOWED")
            if getattr(pre_mt5_mapping, "mt5_dry_run_payload_validation_workflow_allowed", False) is not True:
                blockers.append("DRY_RUN_PAYLOAD_VALIDATION_WORKFLOW_NOT_ALLOWED")
        if final_review is None and self.config.require_final_review:
            blockers.append("MISSING_FINAL_REVIEW")
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
            blockers.append("EXPIRED_DRY_RUN_VALIDATION")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_DRY_RUN_VALIDATION")
        if self.config.reject_raw_values and _raw_values_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, parameter_draft):
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if self.config.reject_mt5_payload and _mt5_payload_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if self.config.reject_mt5_request_dict and _mt5_request_dict_present(pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_REQUEST_DICT_NOT_ALLOWED")
        if self.config.reject_mt5_constants and _mt5_constants_present(pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_CONSTANT_NOT_ALLOWED")
        if _order_contract_ready_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("BROKER_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
            pre_mt5_mapping,
            pre_mt5_mapping_validation,
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

        field_validations = self.field_builder.build_field_validations(pre_mt5_mapping, source_refs)
        field_categories = {item.field_category for item in field_validations}
        missing_field_categories = [item for item in REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES if item not in field_categories]
        invalid_field_categories = [
            item.field_category
            for item in field_validations
            if item.blockers
            or item.status != "SCHEMA_VALIDATED"
            or not item.schema_present
            or item.value_created
            or not item.value_redacted
            or item.raw_value_stored
            or item.mt5_payload_value_created
            or item.mt5_request_field_value_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
        ]
        if missing_field_categories or len(field_validations) != len(REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES):
            blockers.append("MISSING_REQUIRED_PAYLOAD_FIELDS")
        if invalid_field_categories:
            blockers.append("MISSING_REQUIRED_PAYLOAD_FIELDS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "DRY_RUN_PAYLOAD_VALIDATED" if allowed else "BLOCKED"
        if "EXPIRED_DRY_RUN_VALIDATION" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_DRY_RUN_VALIDATION" in blockers:
            status = "DUPLICATE"
        scope = "MT5_REQUEST_DRAFT_BOUNDARY_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        validated_field_categories = [
            item.field_category for item in field_validations if allowed and item.status == "SCHEMA_VALIDATED"
        ]
        validation = MT5OrderRequestDryRunPayloadValidation(
            dry_run_validation_id=f"mt5_dry_run_payload_validation_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(pre_mt5_mapping, "mode", getattr(final_review, "mode", "DRY_RUN_PAYLOAD_VALIDATION_ONLY")),
            symbol=getattr(pre_mt5_mapping, "symbol", getattr(final_review, "symbol", "")),
            broker_symbol=getattr(pre_mt5_mapping, "broker_symbol", getattr(final_review, "broker_symbol", "")),
            status=status,
            scope=scope,
            mt5_request_draft_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            mt5_constants_used=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
            source_pre_mt5_mapping_id=getattr(pre_mt5_mapping, "mapping_boundary_id", ""),
            source_pre_mt5_mapping_validation_id=getattr(pre_mt5_mapping_validation, "validation_report_id", ""),
            source_final_review_id=getattr(final_review, "final_review_id", ""),
            source_parameterization_id=getattr(parameterization, "parameterization_id", ""),
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
            field_validations=field_validations,
            required_field_categories=list(REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES),
            validated_field_categories=validated_field_categories,
            missing_field_categories=missing_field_categories,
            invalid_field_categories=invalid_field_categories,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        validation.payload_size_chars = len(json.dumps(validation.as_dict(), ensure_ascii=False, sort_keys=True))
        return validation


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
        if getattr(item, "mt5_constants_used", False) is not False:
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


def _mt5_constants_present(*items) -> bool:
    return any(getattr(item, "mt5_constants_used", False) is not False for item in items if item is not None)


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
