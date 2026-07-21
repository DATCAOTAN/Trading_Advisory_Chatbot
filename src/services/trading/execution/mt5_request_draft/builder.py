from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.mt5_request_draft.models import (
    REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES,
    MT5RequestDraftBoundary,
    MT5RequestDraftField,
)
from src.services.trading.execution.mt5_request_draft.policy import MT5RequestDraftConfig


DRAFT_CATEGORY_BY_FIELD_CATEGORY = {
    "ACTION_FIELD": "ACTION_DRAFT_FIELD",
    "SYMBOL_FIELD": "SYMBOL_DRAFT_FIELD",
    "VOLUME_FIELD": "VOLUME_DRAFT_FIELD",
    "ORDER_TYPE_FIELD": "ORDER_TYPE_DRAFT_FIELD",
    "PRICE_FIELD": "PRICE_DRAFT_FIELD",
    "STOP_LOSS_FIELD": "STOP_LOSS_DRAFT_FIELD",
    "TAKE_PROFIT_FIELD": "TAKE_PROFIT_DRAFT_FIELD",
    "DEVIATION_FIELD": "DEVIATION_DRAFT_FIELD",
    "MAGIC_FIELD": "MAGIC_DRAFT_FIELD",
    "COMMENT_FIELD": "COMMENT_DRAFT_FIELD",
    "IDEMPOTENCY_FIELD": "IDEMPOTENCY_DRAFT_FIELD",
    "AUDIT_FIELD": "AUDIT_DRAFT_FIELD",
}
FIELD_CATEGORY_BY_DRAFT_CATEGORY = {value: key for key, value in DRAFT_CATEGORY_BY_FIELD_CATEGORY.items()}


class MT5RequestDraftFieldBuilder:
    def build_draft_fields(self, dry_run_validation, source_refs: list[str] | None = None) -> list[MT5RequestDraftField]:
        refs = list(source_refs or [])
        validations_by_category = {
            str(getattr(item, "field_category", "")): item
            for item in getattr(dry_run_validation, "field_validations", []) or []
        }
        draft_fields: list[MT5RequestDraftField] = []
        for draft_category in REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES:
            source_category = FIELD_CATEGORY_BY_DRAFT_CATEGORY.get(draft_category, "")
            source_validation = validations_by_category.get(source_category)
            blockers: list[str] = []
            if source_validation is None:
                blockers.append("MISSING_REQUIRED_DRAFT_FIELDS")
            elif (
                getattr(source_validation, "status", "") != "SCHEMA_VALIDATED"
                or getattr(source_validation, "schema_present", False) is not True
                or getattr(source_validation, "value_created", False) is not False
                or getattr(source_validation, "value_redacted", False) is not True
                or getattr(source_validation, "raw_value_stored", False) is not False
                or getattr(source_validation, "mt5_payload_value_created", False) is not False
                or getattr(source_validation, "mt5_request_field_value_created", False) is not False
                or getattr(source_validation, "mt5_constant_used", False) is not False
                or getattr(source_validation, "executable_order_value", False) is not False
                or getattr(source_validation, "broker_submission_value", False) is not False
                or bool(getattr(source_validation, "blockers", []) or [])
            ):
                blockers.append("INVALID_INPUT")
            draft_fields.append(
                MT5RequestDraftField(
                    draft_field_id=f"mt5_request_draft_field_{draft_category.lower()}",
                    source_field_validation_id=str(getattr(source_validation, "field_validation_id", "")),
                    source_mapping_slot_id=str(getattr(source_validation, "source_mapping_slot_id", "")),
                    source_final_review_slot_validation_id=str(
                        getattr(source_validation, "source_final_review_slot_validation_id", "")
                    ),
                    field_category=draft_category,
                    status="DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY" if not blockers else "BLOCKED",
                    value_state="REFERENCE_ONLY" if not blockers else "BLOCKED",
                    draft_field_present=not blockers,
                    draft_value_created=False,
                    draft_value_redacted=True,
                    raw_value_stored=False,
                    mt5_payload_value_created=False,
                    mt5_request_field_value_created=False,
                    mt5_constant_used=False,
                    executable_order_value=False,
                    broker_submission_value=False,
                    final_draft_approval_required=True,
                    source_refs=refs,
                    blockers=blockers,
                    warnings=[],
                )
            )
        return draft_fields


class MT5RequestDraftBuilder:
    def __init__(
        self,
        config: MT5RequestDraftConfig | None = None,
        field_builder: MT5RequestDraftFieldBuilder | None = None,
    ):
        self.config = config or MT5RequestDraftConfig.from_config()
        self.field_builder = field_builder or MT5RequestDraftFieldBuilder()

    def build(
        self,
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
    ) -> MT5RequestDraftBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(dry_run_validation, "created_at", "")
            or getattr(pre_mt5_mapping, "created_at", "")
            or getattr(final_review, "created_at", "")
            or getattr(parameterization, "created_at", "")
            or getattr(approval_lock, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(dry_run_validation, "source_refs", []) or [])
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
        artifact_hash = (
            getattr(dry_run_validation, "artifact_hash", "")
            or getattr(pre_mt5_mapping, "artifact_hash", "")
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
            getattr(dry_run_validation, "idempotency_key", "")
            or getattr(pre_mt5_mapping, "idempotency_key", "")
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
                    "mt5_request_draft_v1",
                    base_idempotency,
                    getattr(dry_run_validation, "dry_run_validation_id", ""),
                    getattr(dry_run_validation_report, "validation_report_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if dry_run_validation is None and self.config.require_dry_run_validation:
            blockers.append("MISSING_DRY_RUN_PAYLOAD_VALIDATION")
        if dry_run_validation_report is None and self.config.require_dry_run_validation_report:
            blockers.append("MISSING_DRY_RUN_PAYLOAD_VALIDATION_REPORT")
        if self.config.require_dry_run_validation_report and getattr(dry_run_validation_report, "valid", False) is not True:
            blockers.append("MISSING_DRY_RUN_PAYLOAD_VALIDATION_REPORT")
        if self.config.require_workflow_allowed:
            if getattr(dry_run_validation_report, "mt5_request_draft_workflow_allowed", False) is not True:
                blockers.append("MT5_REQUEST_DRAFT_WORKFLOW_NOT_ALLOWED")
            if getattr(dry_run_validation, "mt5_request_draft_workflow_allowed", False) is not True:
                blockers.append("MT5_REQUEST_DRAFT_WORKFLOW_NOT_ALLOWED")
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
            blockers.append("EXPIRED_REQUEST_DRAFT")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_REQUEST_DRAFT")
        if self.config.reject_raw_values and _raw_values_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, parameter_draft):
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if self.config.reject_mt5_payload and _mt5_payload_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if self.config.reject_mt5_request_dict and _mt5_request_dict_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_REQUEST_DICT_NOT_ALLOWED")
        if self.config.reject_mt5_constants and _mt5_constants_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_CONSTANT_NOT_ALLOWED")
        if self.config.reject_broker_submission and _broker_submission_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("BROKER_SUBMISSION_NOT_ALLOWED")
        if _order_contract_ready_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("BROKER_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
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

        draft_fields = self.field_builder.build_draft_fields(dry_run_validation, source_refs)
        field_categories = {item.field_category for item in draft_fields}
        missing_draft_field_categories = [item for item in REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES if item not in field_categories]
        invalid_draft_field_categories = [
            item.field_category
            for item in draft_fields
            if item.blockers
            or item.status != "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY"
            or not item.draft_field_present
            or item.draft_value_created
            or not item.draft_value_redacted
            or item.raw_value_stored
            or item.mt5_payload_value_created
            or item.mt5_request_field_value_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
            or not item.final_draft_approval_required
        ]
        if missing_draft_field_categories or len(draft_fields) != len(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES):
            blockers.append("MISSING_REQUIRED_DRAFT_FIELDS")
        if invalid_draft_field_categories:
            blockers.append("MISSING_REQUIRED_DRAFT_FIELDS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "REQUEST_DRAFT_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_REQUEST_DRAFT" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_REQUEST_DRAFT" in blockers:
            status = "DUPLICATE"
        scope = "FINAL_DRAFT_APPROVAL_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        created_draft_field_categories = [
            item.field_category for item in draft_fields if allowed and item.status == "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY"
        ]
        request_draft = MT5RequestDraftBoundary(
            request_draft_id=f"mt5_request_draft_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode="REQUEST_DRAFT_BOUNDARY_ONLY",
            symbol=getattr(dry_run_validation, "symbol", getattr(pre_mt5_mapping, "symbol", "")),
            broker_symbol=getattr(dry_run_validation, "broker_symbol", getattr(pre_mt5_mapping, "broker_symbol", "")),
            status=status,
            scope=scope,
            mt5_request_draft_final_approval_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            mt5_request_dict_created=False,
            mt5_constants_used=False,
            broker_submission_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            broker_mapping_created=False,
            raw_values_stored=False,
            executable_order_created=False,
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
            draft_fields=draft_fields,
            required_draft_field_categories=list(REQUIRED_MT5_REQUEST_DRAFT_FIELD_CATEGORIES),
            created_draft_field_categories=created_draft_field_categories,
            missing_draft_field_categories=missing_draft_field_categories,
            invalid_draft_field_categories=invalid_draft_field_categories,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        request_draft.payload_size_chars = len(json.dumps(request_draft.as_dict(), ensure_ascii=False, sort_keys=True))
        return request_draft


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
        if getattr(item, "broker_submission_created", False) is not False:
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
