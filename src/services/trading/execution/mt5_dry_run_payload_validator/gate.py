from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_dry_run_payload_validator.models import (
    REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES,
    MT5OrderRequestDryRunPayloadValidation,
    MT5OrderRequestDryRunPayloadValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_dry_run_payload_validator.policy import (
    MT5DryRunPayloadValidationConfig,
)


class MT5OrderRequestDryRunPayloadValidationGate:
    def __init__(self, config: MT5DryRunPayloadValidationConfig | None = None):
        self.config = config or MT5DryRunPayloadValidationConfig.from_config()

    def validate(
        self, validation: MT5OrderRequestDryRunPayloadValidation
    ) -> MT5OrderRequestDryRunPayloadValidationReport:
        blockers = list(validation.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check("status_validated", validation.status == "DRY_RUN_PAYLOAD_VALIDATED", "INVALID_INPUT")
        check("scope_request_draft_only", validation.scope == "MT5_REQUEST_DRAFT_BOUNDARY_ONLY", "INVALID_INPUT")
        check(
            "request_draft_workflow_allowed",
            validation.mt5_request_draft_workflow_allowed is True,
            "DRY_RUN_PAYLOAD_VALIDATION_WORKFLOW_NOT_ALLOWED",
        )
        check("live_execution_disabled", validation.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_submission_disabled", validation.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
        check("execution_disabled", validation.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
        check("non_executable", validation.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("no_mt5_payload", validation.mt5_payload_created is False, "MT5_PAYLOAD_NOT_ALLOWED")
        check("no_mt5_request_dict", validation.mt5_request_dict_created is False, "MT5_REQUEST_DICT_NOT_ALLOWED")
        check("no_mt5_constants", validation.mt5_constants_used is False, "MT5_CONSTANT_NOT_ALLOWED")
        check("not_order_sent", validation.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
        check("hard_live_block", validation.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_contract_not_ready", validation.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
        check("order_mapping_disabled", validation.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("broker_mapping_absent", validation.broker_mapping_created is False, "BROKER_MAPPING_NOT_ALLOWED")
        check("raw_values_absent", validation.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
        check("executable_order_absent", validation.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("source_refs_present", bool(validation.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(validation.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(validation.idempotency_key), "MISSING_IDEMPOTENCY")

        fields = list(validation.field_validations or [])
        field_categories = {item.field_category for item in fields}
        missing = [item for item in REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES if item not in field_categories]
        invalid = [
            item.field_category
            for item in fields
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
        check(
            "required_field_categories_present",
            len(fields) == len(REQUIRED_MT5_DRY_RUN_PAYLOAD_FIELD_CATEGORIES) and not missing,
            "MISSING_REQUIRED_PAYLOAD_FIELDS",
        )
        check("field_validations_schema_only", not invalid, "MISSING_REQUIRED_PAYLOAD_FIELDS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = MT5OrderRequestDryRunPayloadValidationReport(
            validation_report_id=f"mt5_dry_run_payload_validation_report_{_digest(validation.dry_run_validation_id)[:16]}",
            created_at=now_utc_iso(),
            source_dry_run_validation_id=validation.dry_run_validation_id,
            valid=valid,
            mt5_request_draft_workflow_allowed=valid,
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
            field_validations_count=len(fields),
            validated_fields_count=len(fields) if valid else 0,
            missing_fields_count=len(missing),
            invalid_fields_count=len(invalid),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(validation.warnings or []),
            source_refs=list(validation.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
