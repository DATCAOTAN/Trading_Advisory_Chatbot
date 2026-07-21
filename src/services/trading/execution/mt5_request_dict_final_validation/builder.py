from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES,
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationField,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import (
    MT5RequestDictFinalValidationConfig,
)


class MT5RequestDictFinalValidationBuilder:
    def __init__(self, config: MT5RequestDictFinalValidationConfig | None = None):
        self.config = config or MT5RequestDictFinalValidationConfig.from_config()

    def build(
        self,
        dry_run_builder_boundary,
        dry_run_builder_validation_report,
        current_time: datetime | None = None,
        existing_idempotency_keys: set[str] | None = None,
    ) -> MT5RequestDictFinalValidationBoundary:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=max(1, int(self.config.ttl_seconds)))).isoformat()
        blockers: list[str] = []
        warnings: list[str] = []
        source_refs: list[str] = []
        approved_values_required = bool(
            getattr(dry_run_builder_boundary, "approved_semantic_values_required", False)
        )
        approved_values_present = bool(
            getattr(dry_run_builder_boundary, "approved_semantic_values_present", False)
        )
        approved_values_hash = str(
            getattr(dry_run_builder_boundary, "approved_semantic_values_hash", "")
        )
        approved_values_verified = bool(
            approved_values_present
            and getattr(dry_run_builder_boundary, "approved_semantic_values_verified", False) is True
            and approved_values_hash
            and getattr(dry_run_builder_boundary, "artifact_hash", "") == approved_values_hash
        )

        if approved_values_present and not approved_values_verified:
            blockers.append("APPROVED_SEMANTIC_VALUES_INTEGRITY_FAILED")
        if approved_values_required and not approved_values_verified:
            blockers.append("APPROVED_SEMANTIC_VALUES_REQUIRED")
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if dry_run_builder_boundary is None:
            blockers.append("MISSING_DRY_RUN_BUILDER_BOUNDARY")
        if dry_run_builder_validation_report is None:
            blockers.append("MISSING_DRY_RUN_BUILDER_VALIDATION_REPORT")

        if dry_run_builder_boundary is not None:
            source_refs = list(getattr(dry_run_builder_boundary, "source_refs", []) or [])
            if self.config.require_source_refs and not source_refs:
                blockers.append("MISSING_SOURCE_REFS")
            if self.config.require_idempotency and not getattr(dry_run_builder_boundary, "idempotency_key", ""):
                blockers.append("MISSING_IDEMPOTENCY")
            if self.config.reject_raw_values and getattr(dry_run_builder_boundary, "raw_values_stored", False):
                blockers.append("RAW_VALUES_NOT_ALLOWED")
            if self.config.reject_real_mt5_payload and getattr(dry_run_builder_boundary, "real_mt5_payload_created", False):
                blockers.append("REAL_MT5_PAYLOAD_NOT_ALLOWED")
            if self.config.reject_broker_submittable_request_dict and getattr(dry_run_builder_boundary, "broker_submittable_request_dict_created", False):
                blockers.append("BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED")
            if self.config.reject_mt5_constants and getattr(dry_run_builder_boundary, "mt5_constants_used", False):
                blockers.append("MT5_CONSTANT_NOT_ALLOWED")
            if self.config.reject_broker_submission and getattr(dry_run_builder_boundary, "broker_submission_created", False):
                blockers.append("BROKER_SUBMISSION_NOT_ALLOWED")
            if self.config.reject_executable_order and getattr(dry_run_builder_boundary, "executable_order_created", False):
                blockers.append("EXECUTABLE_ORDER_NOT_ALLOWED")
            if getattr(dry_run_builder_boundary, "order_send_allowed", False):
                blockers.append("ORDER_SEND_NOT_ALLOWED")
            if getattr(dry_run_builder_boundary, "live_execution_allowed", False) or getattr(dry_run_builder_boundary, "execution_allowed", False):
                blockers.append("LIVE_EXECUTION_STILL_DISABLED")
            if now > _parse_time(getattr(dry_run_builder_boundary, "expires_at", "")):
                blockers.append("EXPIRED_FINAL_VALIDATION")

        if dry_run_builder_validation_report is not None:
            if not getattr(dry_run_builder_validation_report, "valid", False):
                blockers.append("MISSING_DRY_RUN_BUILDER_VALIDATION_REPORT")
            if self.config.require_workflow_allowed and not getattr(
                dry_run_builder_validation_report,
                "mt5_request_dict_final_validation_workflow_allowed",
                False,
            ):
                blockers.append("REQUEST_DICT_FINAL_VALIDATION_WORKFLOW_NOT_ALLOWED")

        fields = _build_fields(dry_run_builder_boundary, source_refs, blockers)
        validated_categories = [item.field_category for item in fields if item.validation_passed]
        missing_categories = [
            category
            for category in REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES
            if category not in validated_categories
        ]
        invalid_categories = [item.field_category for item in fields if not item.validation_passed]
        if missing_categories or invalid_categories:
            blockers.append("MISSING_REQUIRED_DRY_RUN_FIELDS")

        base_hash = hashlib.sha256(
            json.dumps(
                {
                    "source": getattr(dry_run_builder_boundary, "dry_run_request_dict_id", ""),
                    "report": getattr(dry_run_builder_validation_report, "validation_report_id", ""),
                    "categories": validated_categories,
                    "source_refs": source_refs,
                    "approved_semantic_values_hash": (
                        approved_values_hash if approved_values_verified else ""
                    ),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        idempotency_key = f"mt5-request-dict-final-validation:{base_hash[:24]}"
        if existing_idempotency_keys and idempotency_key in existing_idempotency_keys:
            blockers.append("DUPLICATE_FINAL_VALIDATION")

        status = "FINAL_VALIDATION_PASSED" if not blockers else "BLOCKED"
        if "DUPLICATE_FINAL_VALIDATION" in blockers:
            status = "DUPLICATE"
        if "EXPIRED_FINAL_VALIDATION" in blockers:
            status = "EXPIRED"
        boundary = MT5RequestDictFinalValidationBoundary(
            final_validation_id=f"mt5_request_dict_final_validation_{base_hash[:16]}",
            created_at=created_at,
            symbol=getattr(dry_run_builder_boundary, "symbol", ""),
            broker_symbol=getattr(dry_run_builder_boundary, "broker_symbol", ""),
            status=status,
            scope="BRIDGE_WRITE_SKELETON_CHECK_ONLY" if status == "FINAL_VALIDATION_PASSED" else "EXECUTION_NOT_ALLOWED",
            bridge_write_skeleton_check_allowed=status == "FINAL_VALIDATION_PASSED",
            approved_semantic_values_required=approved_values_required,
            approved_semantic_values_present=approved_values_present,
            approved_semantic_values_verified=approved_values_verified,
            approved_semantic_values_hash=(approved_values_hash if approved_values_verified else ""),
            source_dry_run_request_dict_id=getattr(dry_run_builder_boundary, "dry_run_request_dict_id", ""),
            source_dry_run_request_dict_validation_report_id=getattr(dry_run_builder_validation_report, "validation_report_id", ""),
            validated_fields=fields,
            required_field_categories=list(REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES),
            validated_field_categories=validated_categories,
            missing_field_categories=missing_categories,
            invalid_field_categories=invalid_categories,
            artifact_hash=(approved_values_hash if approved_values_verified else base_hash),
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=list(dict.fromkeys(blockers)),
            warnings=warnings,
            source_refs=list(dict.fromkeys(source_refs)),
        )
        boundary.payload_size_chars = len(json.dumps(boundary.as_dict(), sort_keys=True, ensure_ascii=False))
        return boundary


def _build_fields(boundary, source_refs: list[str], blockers: list[str]) -> list[MT5RequestDictFinalValidationField]:
    if boundary is None:
        return []
    by_category = {getattr(item, "field_category", ""): item for item in getattr(boundary, "dry_run_fields", []) or []}
    fields: list[MT5RequestDictFinalValidationField] = []
    for category in REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES:
        src = by_category.get(category)
        if src is None:
            continue
        field_blockers: list[str] = []
        checks = {
            "dry_run_field_present": getattr(src, "dry_run_field_present", False) is True,
            "concrete_value_created": getattr(src, "concrete_value_created", True) is False,
            "value_redacted": getattr(src, "value_redacted", False) is True,
            "raw_value_stored": getattr(src, "raw_value_stored", True) is False,
            "real_mt5_payload_value_created": getattr(src, "real_mt5_payload_value_created", True) is False,
            "broker_submittable_request_field_created": getattr(src, "broker_submittable_request_field_created", True) is False,
            "mt5_constant_used": getattr(src, "mt5_constant_used", True) is False,
            "executable_order_value": getattr(src, "executable_order_value", True) is False,
            "broker_submission_value": getattr(src, "broker_submission_value", True) is False,
        }
        if not all(checks.values()):
            field_blockers.append("INVALID_INPUT")
            blockers.append("MISSING_REQUIRED_DRY_RUN_FIELDS")
        fields.append(
            MT5RequestDictFinalValidationField(
                field_id=f"mt5_request_dict_final_validation_field_{category.lower()}_{_short_hash(getattr(src, 'dry_run_field_id', category))}",
                source_dry_run_field_id=getattr(src, "dry_run_field_id", ""),
                field_category=category,
                key_label=getattr(src, "dry_run_key_label", ""),
                validation_passed=not field_blockers,
                schema_only=True,
                source_refs=list(dict.fromkeys(list(getattr(src, "source_refs", []) or []) + source_refs)),
                blockers=field_blockers,
            )
        )
    return fields


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _short_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]
