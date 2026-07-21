from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.mt5_request_dict_dry_run_builder.models import (
    DRY_RUN_KEY_LABEL_BY_CATEGORY,
    REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES,
    MT5RequestDictDryRunBuilderBoundary,
    MT5RequestDictDryRunField,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.policy import (
    MT5RequestDictDryRunBuilderConfig,
)


DRY_RUN_CATEGORY_BY_APPROVED_CATEGORY = {
    "ACTION_DRAFT_FIELD": "ACTION_KEY",
    "SYMBOL_DRAFT_FIELD": "SYMBOL_KEY",
    "VOLUME_DRAFT_FIELD": "VOLUME_KEY",
    "ORDER_TYPE_DRAFT_FIELD": "ORDER_TYPE_KEY",
    "PRICE_DRAFT_FIELD": "PRICE_KEY",
    "STOP_LOSS_DRAFT_FIELD": "STOP_LOSS_KEY",
    "TAKE_PROFIT_DRAFT_FIELD": "TAKE_PROFIT_KEY",
    "DEVIATION_DRAFT_FIELD": "DEVIATION_KEY",
    "MAGIC_DRAFT_FIELD": "MAGIC_KEY",
    "COMMENT_DRAFT_FIELD": "COMMENT_KEY",
    "IDEMPOTENCY_DRAFT_FIELD": "IDEMPOTENCY_KEY",
    "AUDIT_DRAFT_FIELD": "AUDIT_KEY",
}
APPROVED_CATEGORY_BY_DRY_RUN_CATEGORY = {value: key for key, value in DRY_RUN_CATEGORY_BY_APPROVED_CATEGORY.items()}


class MT5RequestDictDryRunFieldBuilder:
    def build_dry_run_fields(self, final_approval, source_refs: list[str] | None = None) -> list[MT5RequestDictDryRunField]:
        refs = list(source_refs or [])
        approved_by_category = {
            str(getattr(item, "field_category", "")): item
            for item in getattr(final_approval, "approved_fields", []) or []
        }
        fields: list[MT5RequestDictDryRunField] = []
        for category in REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES:
            source_category = APPROVED_CATEGORY_BY_DRY_RUN_CATEGORY.get(category, "")
            source_field = approved_by_category.get(source_category)
            blockers: list[str] = []
            if source_field is None:
                blockers.append("MISSING_REQUIRED_DRY_RUN_FIELDS")
            elif (
                getattr(source_field, "status", "") != "APPROVED_AS_REFERENCE_ONLY"
                or getattr(source_field, "approved_as_reference_only", False) is not True
                or getattr(source_field, "dry_run_request_dict_builder_validation_required", False) is not True
                or getattr(source_field, "draft_field_present", False) is not True
                or getattr(source_field, "draft_value_created", False) is not False
                or getattr(source_field, "draft_value_redacted", False) is not True
                or getattr(source_field, "raw_value_stored", False) is not False
                or getattr(source_field, "mt5_payload_value_created", False) is not False
                or getattr(source_field, "mt5_request_field_value_created", False) is not False
                or getattr(source_field, "mt5_constant_used", False) is not False
                or getattr(source_field, "executable_order_value", False) is not False
                or getattr(source_field, "broker_submission_value", False) is not False
                or getattr(source_field, "final_human_approval_required", False) is not True
                or bool(getattr(source_field, "blockers", []) or [])
            ):
                blockers.append("INVALID_INPUT")
            fields.append(
                MT5RequestDictDryRunField(
                    dry_run_field_id=f"mt5_request_dict_dry_run_field_{category.lower()}",
                    source_approved_field_id=str(getattr(source_field, "approved_field_id", "")),
                    source_draft_field_id=str(getattr(source_field, "source_draft_field_id", "")),
                    source_field_validation_id=str(getattr(source_field, "source_field_validation_id", "")),
                    source_mapping_slot_id=str(getattr(source_field, "source_mapping_slot_id", "")),
                    source_final_review_slot_validation_id=str(
                        getattr(source_field, "source_final_review_slot_validation_id", "")
                    ),
                    field_category=category,
                    status="DRY_RUN_FIELD_CREATED_AS_SCHEMA_ONLY" if not blockers else "BLOCKED",
                    value_state="SCHEMA_ONLY" if not blockers else "BLOCKED",
                    dry_run_key_label=DRY_RUN_KEY_LABEL_BY_CATEGORY.get(category, ""),
                    dry_run_field_present=not blockers,
                    concrete_value_created=False,
                    value_redacted=True,
                    raw_value_stored=False,
                    real_mt5_payload_value_created=False,
                    broker_submittable_request_field_created=False,
                    mt5_constant_used=False,
                    executable_order_value=False,
                    broker_submission_value=False,
                    final_validation_required=True,
                    source_refs=refs,
                    blockers=blockers,
                    warnings=[],
                )
            )
        return fields


class MT5RequestDictDryRunBuilder:
    def __init__(
        self,
        config: MT5RequestDictDryRunBuilderConfig | None = None,
        field_builder: MT5RequestDictDryRunFieldBuilder | None = None,
    ):
        self.config = config or MT5RequestDictDryRunBuilderConfig.from_config()
        self.field_builder = field_builder or MT5RequestDictDryRunFieldBuilder()

    def build(
        self,
        draft_final_approval,
        draft_final_approval_validation_report,
        request_draft,
        request_draft_validation_report,
        dry_run_validation,
        dry_run_validation_report,
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
        require_approved_semantic_values: bool = False,
    ) -> MT5RequestDictDryRunBuilderBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(draft_final_approval, "created_at", "")
            or getattr(request_draft, "created_at", "")
            or getattr(dry_run_validation, "created_at", "")
            or getattr(final_review, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(draft_final_approval, "source_refs", []) or [])
            + list(getattr(draft_final_approval_validation_report, "source_refs", []) or [])
            + list(getattr(request_draft, "source_refs", []) or [])
            + list(getattr(request_draft_validation_report, "source_refs", []) or [])
            + list(getattr(dry_run_validation, "source_refs", []) or [])
            + list(getattr(dry_run_validation_report, "source_refs", []) or [])
            + list(getattr(pre_mt5_mapping, "source_refs", []) or [])
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
        approved_parameters = getattr(approval_lock, "approved_semantic_parameters", None)
        approved_values_hash = (
            approved_parameters.canonical_values_hash if approved_parameters is not None else ""
        )
        approved_values_verified = bool(
            approved_parameters is not None
            and callable(getattr(approval_lock, "approved_semantic_integrity_valid", None))
            and approval_lock.approved_semantic_integrity_valid()
            and getattr(approval_lock_validation, "valid", False) is True
            and getattr(parameterization, "artifact_hash", "") == approved_values_hash
            and getattr(parameterization_validation, "valid", False) is True
            and getattr(final_review, "artifact_hash", "") == approved_values_hash
            and getattr(final_review_validation, "valid", False) is True
            and getattr(request_draft, "artifact_hash", "") == approved_values_hash
            and getattr(request_draft_validation_report, "valid", False) is True
            and getattr(draft_final_approval, "artifact_hash", "") == approved_values_hash
            and getattr(draft_final_approval_validation_report, "valid", False) is True
        )
        artifact_hash = (
            approved_values_hash if approved_values_verified else ""
        ) or (
            getattr(draft_final_approval, "artifact_hash", "")
            or getattr(request_draft, "artifact_hash", "")
            or getattr(dry_run_validation, "artifact_hash", "")
            or getattr(pre_mt5_mapping, "artifact_hash", "")
            or getattr(final_review, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(draft_final_approval, "idempotency_key", "")
            or getattr(request_draft, "idempotency_key", "")
            or getattr(dry_run_validation, "idempotency_key", "")
            or getattr(pre_mt5_mapping, "idempotency_key", "")
            or getattr(final_review, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "mt5_request_dict_dry_run_builder_v1",
                    base_idempotency,
                    getattr(draft_final_approval, "final_approval_id", ""),
                    getattr(draft_final_approval_validation_report, "validation_report_id", ""),
                    approved_values_hash if approved_values_verified else "",
                ]
            )
        )

        blockers: list[str] = []
        if approved_parameters is not None and not approved_values_verified:
            blockers.append("APPROVED_SEMANTIC_VALUES_INTEGRITY_FAILED")
        if require_approved_semantic_values and not approved_values_verified:
            blockers.append("APPROVED_SEMANTIC_VALUES_REQUIRED")
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if draft_final_approval is None and self.config.require_draft_final_approval:
            blockers.append("MISSING_DRAFT_FINAL_APPROVAL")
        if draft_final_approval_validation_report is None and self.config.require_draft_final_approval_validation_report:
            blockers.append("MISSING_DRAFT_FINAL_APPROVAL_VALIDATION_REPORT")
        if self.config.require_draft_final_approval_validation_report and getattr(draft_final_approval_validation_report, "valid", False) is not True:
            blockers.append("MISSING_DRAFT_FINAL_APPROVAL_VALIDATION_REPORT")
        if self.config.require_workflow_allowed:
            if getattr(draft_final_approval_validation_report, "mt5_request_dict_dry_run_builder_workflow_allowed", False) is not True:
                blockers.append("REQUEST_DICT_DRY_RUN_BUILDER_WORKFLOW_NOT_ALLOWED")
            if getattr(draft_final_approval, "mt5_request_dict_dry_run_builder_workflow_allowed", False) is not True:
                blockers.append("REQUEST_DICT_DRY_RUN_BUILDER_WORKFLOW_NOT_ALLOWED")
        if request_draft is None and self.config.require_request_draft:
            blockers.append("MISSING_REQUEST_DRAFT")
        if dry_run_validation is None and self.config.require_dry_run_validation:
            blockers.append("MISSING_DRY_RUN_PAYLOAD_VALIDATION")
        if pre_mt5_mapping is None and self.config.require_pre_mt5_mapping:
            blockers.append("MISSING_PRE_MT5_MAPPING")
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
            blockers.append("EXPIRED_DRY_RUN_REQUEST_DICT")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_DRY_RUN_REQUEST_DICT")
        if self.config.reject_raw_values and _raw_values_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, parameter_draft):
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if self.config.reject_real_mt5_payload and _real_mt5_payload_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("REAL_MT5_PAYLOAD_NOT_ALLOWED")
        if self.config.reject_broker_submittable_request_dict and _broker_submittable_request_dict_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED")
        if self.config.reject_mt5_constants and _mt5_constants_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_CONSTANT_NOT_ALLOWED")
        if self.config.reject_broker_submission and _broker_submission_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("BROKER_SUBMISSION_NOT_ALLOWED")
        if _order_contract_ready_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(draft_final_approval, request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("BROKER_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
            draft_final_approval,
            draft_final_approval_validation_report,
            request_draft,
            request_draft_validation_report,
            dry_run_validation,
            dry_run_validation_report,
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

        dry_run_fields = self.field_builder.build_dry_run_fields(draft_final_approval, source_refs)
        categories = {item.field_category for item in dry_run_fields}
        missing = [item for item in REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES if item not in categories]
        invalid = [
            item.field_category
            for item in dry_run_fields
            if item.blockers
            or item.status != "DRY_RUN_FIELD_CREATED_AS_SCHEMA_ONLY"
            or not item.dry_run_field_present
            or item.concrete_value_created
            or not item.value_redacted
            or item.raw_value_stored
            or item.real_mt5_payload_value_created
            or item.broker_submittable_request_field_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
            or not item.final_validation_required
        ]
        if missing or len(dry_run_fields) != len(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES) or invalid:
            blockers.append("MISSING_REQUIRED_DRY_RUN_FIELDS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_DRY_RUN_REQUEST_DICT" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_DRY_RUN_REQUEST_DICT" in blockers:
            status = "DUPLICATE"
        scope = "REQUEST_DICT_FINAL_VALIDATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        created_categories = [item.field_category for item in dry_run_fields if allowed and item.status == "DRY_RUN_FIELD_CREATED_AS_SCHEMA_ONLY"]
        boundary = MT5RequestDictDryRunBuilderBoundary(
            dry_run_request_dict_id=f"mt5_request_dict_dry_run_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode="REQUEST_DICT_DRY_RUN_BUILDER_BOUNDARY_ONLY",
            symbol=getattr(draft_final_approval, "symbol", getattr(request_draft, "symbol", "")),
            broker_symbol=getattr(draft_final_approval, "broker_symbol", getattr(request_draft, "broker_symbol", "")),
            status=status,
            scope=scope,
            mt5_request_dict_final_validation_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            real_mt5_payload_created=False,
            broker_submittable_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            approved_semantic_values_required=require_approved_semantic_values,
            approved_semantic_values_present=approved_parameters is not None,
            approved_semantic_values_verified=approved_values_verified,
            approved_semantic_values_hash=(approved_values_hash if approved_values_verified else ""),
            executable_order_created=False,
            source_draft_final_approval_id=getattr(draft_final_approval, "final_approval_id", ""),
            source_draft_final_approval_validation_report_id=getattr(draft_final_approval_validation_report, "validation_report_id", ""),
            source_request_draft_id=getattr(request_draft, "request_draft_id", ""),
            source_request_draft_validation_report_id=getattr(request_draft_validation_report, "validation_report_id", ""),
            source_dry_run_validation_id=getattr(dry_run_validation, "dry_run_validation_id", ""),
            source_dry_run_validation_report_id=getattr(dry_run_validation_report, "validation_report_id", ""),
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
            dry_run_fields=dry_run_fields,
            required_dry_run_field_categories=list(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES),
            created_dry_run_field_categories=created_categories,
            missing_dry_run_field_categories=missing,
            invalid_dry_run_field_categories=invalid,
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
        checks = {
            "live_execution_allowed": False,
            "order_send_allowed": False,
            "execution_allowed": False,
            "hard_live_block_required": True,
            "executable": False,
            "order_sent": False,
            "order_contract_ready": False,
            "order_request_mapping_allowed": False,
            "broker_mapping_created": False,
            "broker_submission_created": False,
            "mt5_constants_used": False,
            "real_mt5_payload_created": False,
            "broker_submittable_request_dict_created": False,
        }
        for name, expected in checks.items():
            if getattr(item, name, expected) is not expected:
                return True
        if getattr(item, "mt5_payload_created", False) is not False:
            return True
        if getattr(item, "mt5_request_dict_created", False) is not False:
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


def _real_mt5_payload_present(*items) -> bool:
    return any(
        getattr(item, "real_mt5_payload_created", False) is not False
        or getattr(item, "mt5_payload_created", False) is not False
        for item in items
        if item is not None
    )


def _broker_submittable_request_dict_present(*items) -> bool:
    return any(
        getattr(item, "broker_submittable_request_dict_created", False) is not False
        or getattr(item, "mt5_request_dict_created", False) is not False
        for item in items
        if item is not None
    )


def _mt5_constants_present(*items) -> bool:
    return any(getattr(item, "mt5_constants_used", False) is not False for item in items if item is not None)


def _broker_submission_present(*items) -> bool:
    return any(
        getattr(item, "broker_submission_created", False) is not False
        or getattr(item, "broker_submission_value", False) is not False
        for item in items
        if item is not None
    )


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
