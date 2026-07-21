from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.mt5_request_draft_final_approval.confirmation import (
    MT5RequestDraftFinalApprovalConfirmationService,
)
from src.services.trading.execution.mt5_request_draft_final_approval.models import (
    REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES,
    MT5RequestDraftApprovedField,
    MT5RequestDraftFinalApprovalBoundary,
)
from src.services.trading.execution.mt5_request_draft_final_approval.policy import (
    MT5RequestDraftFinalApprovalConfig,
)


class MT5RequestDraftApprovedFieldBuilder:
    def build_approved_fields(self, request_draft, source_refs: list[str] | None = None) -> list[MT5RequestDraftApprovedField]:
        refs = list(source_refs or [])
        draft_fields_by_category = {
            str(getattr(item, "field_category", "")): item
            for item in getattr(request_draft, "draft_fields", []) or []
        }
        approved_fields: list[MT5RequestDraftApprovedField] = []
        for category in REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES:
            source_field = draft_fields_by_category.get(category)
            blockers: list[str] = []
            if source_field is None:
                blockers.append("MISSING_REQUIRED_APPROVED_FIELDS")
            elif (
                getattr(source_field, "status", "") != "DRAFT_FIELD_CREATED_AS_REFERENCE_ONLY"
                or getattr(source_field, "draft_field_present", False) is not True
                or getattr(source_field, "draft_value_created", False) is not False
                or getattr(source_field, "draft_value_redacted", False) is not True
                or getattr(source_field, "raw_value_stored", False) is not False
                or getattr(source_field, "mt5_payload_value_created", False) is not False
                or getattr(source_field, "mt5_request_field_value_created", False) is not False
                or getattr(source_field, "mt5_constant_used", False) is not False
                or getattr(source_field, "executable_order_value", False) is not False
                or getattr(source_field, "broker_submission_value", False) is not False
                or getattr(source_field, "final_draft_approval_required", False) is not True
                or bool(getattr(source_field, "blockers", []) or [])
            ):
                blockers.append("INVALID_INPUT")
            approved_fields.append(
                MT5RequestDraftApprovedField(
                    approved_field_id=f"mt5_request_draft_approved_field_{category.lower()}",
                    source_draft_field_id=str(getattr(source_field, "draft_field_id", "")),
                    source_field_validation_id=str(getattr(source_field, "source_field_validation_id", "")),
                    source_mapping_slot_id=str(getattr(source_field, "source_mapping_slot_id", "")),
                    source_final_review_slot_validation_id=str(
                        getattr(source_field, "source_final_review_slot_validation_id", "")
                    ),
                    field_category=category,
                    status="APPROVED_AS_REFERENCE_ONLY" if not blockers else "BLOCKED",
                    value_state="REFERENCE_ONLY" if not blockers else "BLOCKED",
                    approved_as_reference_only=not blockers,
                    dry_run_request_dict_builder_validation_required=True,
                    draft_field_present=not blockers,
                    draft_value_created=False,
                    draft_value_redacted=True,
                    raw_value_stored=False,
                    mt5_payload_value_created=False,
                    mt5_request_field_value_created=False,
                    mt5_constant_used=False,
                    executable_order_value=False,
                    broker_submission_value=False,
                    final_human_approval_required=True,
                    source_refs=refs,
                    blockers=blockers,
                    warnings=[],
                )
            )
        return approved_fields


class MT5RequestDraftFinalApprovalBuilder:
    def __init__(
        self,
        config: MT5RequestDraftFinalApprovalConfig | None = None,
        field_builder: MT5RequestDraftApprovedFieldBuilder | None = None,
        confirmation_service: MT5RequestDraftFinalApprovalConfirmationService | None = None,
    ):
        self.config = config or MT5RequestDraftFinalApprovalConfig.from_config()
        self.field_builder = field_builder or MT5RequestDraftApprovedFieldBuilder()
        self.confirmation_service = confirmation_service or MT5RequestDraftFinalApprovalConfirmationService(self.config)

    def build(
        self,
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
        confirmation_phrase: str | None = None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> MT5RequestDraftFinalApprovalBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(request_draft, "created_at", "")
            or getattr(dry_run_validation, "created_at", "")
            or getattr(pre_mt5_mapping, "created_at", "")
            or getattr(final_review, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(request_draft, "source_refs", []) or [])
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
        confirmation = self.confirmation_service.confirm(
            confirmation_phrase,
            source_refs=source_refs,
            current_time=now,
        )
        artifact_hash = (
            getattr(request_draft, "artifact_hash", "")
            or getattr(dry_run_validation, "artifact_hash", "")
            or getattr(pre_mt5_mapping, "artifact_hash", "")
            or getattr(final_review, "artifact_hash", "")
            or getattr(parameterization, "artifact_hash", "")
            or getattr(approval_lock, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(request_draft, "idempotency_key", "")
            or getattr(dry_run_validation, "idempotency_key", "")
            or getattr(pre_mt5_mapping, "idempotency_key", "")
            or getattr(final_review, "idempotency_key", "")
            or getattr(parameterization, "idempotency_key", "")
            or getattr(approval_lock, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "mt5_request_draft_final_approval_v1",
                    base_idempotency,
                    getattr(request_draft, "request_draft_id", ""),
                    getattr(request_draft_validation_report, "validation_report_id", ""),
                    confirmation.confirmation_id,
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if request_draft is None and self.config.require_request_draft:
            blockers.append("MISSING_REQUEST_DRAFT")
        if request_draft_validation_report is None and self.config.require_request_draft_validation_report:
            blockers.append("MISSING_REQUEST_DRAFT_VALIDATION_REPORT")
        if self.config.require_request_draft_validation_report and getattr(request_draft_validation_report, "valid", False) is not True:
            blockers.append("MISSING_REQUEST_DRAFT_VALIDATION_REPORT")
        if self.config.require_workflow_allowed:
            if getattr(request_draft_validation_report, "mt5_request_draft_final_approval_workflow_allowed", False) is not True:
                blockers.append("REQUEST_DRAFT_FINAL_APPROVAL_WORKFLOW_NOT_ALLOWED")
            if getattr(request_draft, "mt5_request_draft_final_approval_workflow_allowed", False) is not True:
                blockers.append("REQUEST_DRAFT_FINAL_APPROVAL_WORKFLOW_NOT_ALLOWED")
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
        if self.config.require_exact_confirmation and confirmation.phrase_valid is not True:
            blockers.extend(confirmation.blockers or ["WRONG_CONFIRMATION_PHRASE"])
        if now > _parse_datetime(confirmation.expires_at):
            blockers.append("CONFIRMATION_EXPIRED")
        if now > expires_at_dt:
            blockers.append("EXPIRED_FINAL_APPROVAL")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_FINAL_APPROVAL")
        if self.config.reject_raw_values and _raw_values_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, parameter_draft):
            blockers.append("RAW_VALUES_NOT_ALLOWED")
        if _executable_order_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, proposal_draft, simulated_contract):
            blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
        if self.config.reject_mt5_payload and _mt5_payload_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("MT5_PAYLOAD_NOT_ALLOWED")
        if self.config.reject_mt5_request_dict and _mt5_request_dict_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_REQUEST_DICT_NOT_ALLOWED")
        if self.config.reject_mt5_constants and _mt5_constants_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("MT5_CONSTANT_NOT_ALLOWED")
        if self.config.reject_broker_submission and _broker_submission_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, contract_skeleton):
            blockers.append("BROKER_SUBMISSION_NOT_ALLOWED")
        if _order_contract_ready_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_CONTRACT_READY_NOT_ALLOWED")
        if _order_request_mapping_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        if _broker_mapping_present(request_draft, dry_run_validation, pre_mt5_mapping, final_review, parameterization, approval_lock, value_proposal, contract_skeleton):
            blockers.append("BROKER_MAPPING_NOT_ALLOWED")
        if _unsafe_execution_flags(
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

        approved_fields = self.field_builder.build_approved_fields(request_draft, source_refs)
        field_categories = {item.field_category for item in approved_fields}
        missing = [item for item in REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES if item not in field_categories]
        invalid = [
            item.field_category
            for item in approved_fields
            if item.blockers
            or item.status != "APPROVED_AS_REFERENCE_ONLY"
            or not item.approved_as_reference_only
            or not item.dry_run_request_dict_builder_validation_required
            or not item.draft_field_present
            or item.draft_value_created
            or not item.draft_value_redacted
            or item.raw_value_stored
            or item.mt5_payload_value_created
            or item.mt5_request_field_value_created
            or item.mt5_constant_used
            or item.executable_order_value
            or item.broker_submission_value
            or not item.final_human_approval_required
        ]
        if missing or len(approved_fields) != len(REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES) or invalid:
            blockers.append("MISSING_REQUIRED_APPROVED_FIELDS")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "FINAL_APPROVAL_GRANTED_FOR_DRY_RUN_REQUEST_DICT_BUILDER" if allowed else "BLOCKED"
        if "FINAL_APPROVAL_REJECTED" in blockers:
            status = "REJECTED"
        if "EXPIRED_FINAL_APPROVAL" in blockers or "CONFIRMATION_EXPIRED" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_FINAL_APPROVAL" in blockers:
            status = "DUPLICATE"
        scope = "DRY_RUN_REQUEST_DICT_BUILDER_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        approved_categories = [item.field_category for item in approved_fields if allowed and item.status == "APPROVED_AS_REFERENCE_ONLY"]
        approval = MT5RequestDraftFinalApprovalBoundary(
            final_approval_id=f"mt5_request_draft_final_approval_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode="REQUEST_DRAFT_FINAL_APPROVAL_BOUNDARY_ONLY",
            symbol=getattr(request_draft, "symbol", getattr(dry_run_validation, "symbol", "")),
            broker_symbol=getattr(request_draft, "broker_symbol", getattr(dry_run_validation, "broker_symbol", "")),
            status=status,
            scope=scope,
            mt5_request_dict_dry_run_builder_workflow_allowed=allowed,
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
            confirmation_id=confirmation.confirmation_id,
            confirmation_phrase_valid=confirmation.phrase_valid and allowed,
            final_approval_action=confirmation.action,
            final_approval_review_state=confirmation.review_state,
            approved_fields=approved_fields,
            required_approved_field_categories=list(REQUIRED_MT5_REQUEST_DRAFT_APPROVED_FIELD_CATEGORIES),
            approved_field_categories=approved_categories,
            missing_approved_field_categories=missing,
            invalid_approved_field_categories=invalid,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        approval.payload_size_chars = len(json.dumps(approval.as_dict(), ensure_ascii=False, sort_keys=True))
        return approval


def _unsafe_execution_flags(*items) -> bool:
    for item in items:
        if item is None:
            continue
        for name, expected in [
            ("live_execution_allowed", False),
            ("order_send_allowed", False),
            ("execution_allowed", False),
            ("hard_live_block_required", True),
            ("executable", False),
            ("mt5_payload_created", False),
            ("mt5_request_dict_created", False),
            ("mt5_constants_used", False),
            ("broker_submission_created", False),
            ("order_sent", False),
            ("order_contract_ready", False),
            ("order_request_mapping_allowed", False),
            ("broker_mapping_created", False),
        ]:
            if getattr(item, name, expected) is not expected:
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
