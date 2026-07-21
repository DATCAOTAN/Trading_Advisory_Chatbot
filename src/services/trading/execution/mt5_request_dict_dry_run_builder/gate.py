from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_request_dict_dry_run_builder.models import (
    REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES,
    MT5RequestDictDryRunBuilderBoundary,
    MT5RequestDictDryRunBuilderValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_dict_dry_run_builder.policy import (
    MT5RequestDictDryRunBuilderConfig,
)


class MT5RequestDictDryRunBuilderGate:
    def __init__(self, config: MT5RequestDictDryRunBuilderConfig | None = None):
        self.config = config or MT5RequestDictDryRunBuilderConfig.from_config()

    def validate(self, boundary: MT5RequestDictDryRunBuilderBoundary) -> MT5RequestDictDryRunBuilderValidationReport:
        blockers = list(boundary.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check("status_created", boundary.status == "DRY_RUN_REQUEST_DICT_BOUNDARY_CREATED", "INVALID_INPUT")
        check("scope_final_validation_only", boundary.scope == "REQUEST_DICT_FINAL_VALIDATION_ONLY", "INVALID_INPUT")
        check("final_validation_workflow_allowed", boundary.mt5_request_dict_final_validation_workflow_allowed is True, "REQUEST_DICT_DRY_RUN_BUILDER_WORKFLOW_NOT_ALLOWED")
        _check_safety(boundary, check)
        check("source_refs_present", bool(boundary.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(boundary.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(boundary.idempotency_key), "MISSING_IDEMPOTENCY")

        fields = list(boundary.dry_run_fields or [])
        field_categories = {item.field_category for item in fields}
        missing = [item for item in REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES if item not in field_categories]
        invalid = [
            item.field_category
            for item in fields
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
        check(
            "required_dry_run_field_categories_present",
            len(fields) == len(REQUIRED_MT5_REQUEST_DICT_DRY_RUN_FIELD_CATEGORIES) and not missing,
            "MISSING_REQUIRED_DRY_RUN_FIELDS",
        )
        check("dry_run_fields_schema_only", not invalid, "MISSING_REQUIRED_DRY_RUN_FIELDS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = MT5RequestDictDryRunBuilderValidationReport(
            validation_report_id=f"mt5_request_dict_dry_run_builder_report_{_digest(boundary.dry_run_request_dict_id)[:16]}",
            created_at=now_utc_iso(),
            source_dry_run_request_dict_id=boundary.dry_run_request_dict_id,
            valid=valid,
            mt5_request_dict_final_validation_workflow_allowed=valid,
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
            executable_order_created=False,
            dry_run_fields_count=len(fields),
            created_dry_run_fields_count=len(fields) if valid else 0,
            missing_dry_run_fields_count=len(missing),
            invalid_dry_run_fields_count=len(invalid),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(boundary.warnings or []),
            source_refs=list(boundary.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check_safety(item, check) -> None:
    check("live_execution_disabled", item.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
    check("order_submission_disabled", item.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
    check("execution_disabled", item.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
    check("non_executable", item.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
    check("no_real_mt5_payload", item.real_mt5_payload_created is False, "REAL_MT5_PAYLOAD_NOT_ALLOWED")
    check("no_broker_submittable_request_dict", item.broker_submittable_request_dict_created is False, "BROKER_SUBMITTABLE_REQUEST_DICT_NOT_ALLOWED")
    check("no_mt5_constants", item.mt5_constants_used is False, "MT5_CONSTANT_NOT_ALLOWED")
    check("no_broker_submission", item.broker_submission_created is False, "BROKER_SUBMISSION_NOT_ALLOWED")
    check("not_order_sent", item.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
    check("hard_live_block", item.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
    check("order_contract_not_ready", item.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
    check("order_mapping_disabled", item.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
    check("broker_mapping_absent", item.broker_mapping_created is False, "BROKER_MAPPING_NOT_ALLOWED")
    check("raw_values_absent", item.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
    check("executable_order_absent", item.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
