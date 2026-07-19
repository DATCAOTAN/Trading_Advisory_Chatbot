from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.pre_mt5_order_mapping.models import (
    REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES,
    PreMT5OrderRequestMappingBoundary,
    PreMT5OrderRequestMappingValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.pre_mt5_order_mapping.policy import (
    PreMT5OrderRequestMappingConfig,
)


class PreMT5OrderRequestMappingGate:
    def __init__(self, config: PreMT5OrderRequestMappingConfig | None = None):
        self.config = config or PreMT5OrderRequestMappingConfig.from_config()

    def validate(self, boundary: PreMT5OrderRequestMappingBoundary) -> PreMT5OrderRequestMappingValidationReport:
        blockers = list(boundary.blockers or [])
        checks = []

        def check(name: str, passed: bool, blocker: str):
            checks.append({"name": name, "passed": bool(passed), "blocker": "" if passed else blocker})
            if not passed:
                blockers.append(blocker)

        check("status_boundary_created", boundary.status == "MAPPING_BOUNDARY_CREATED", "INVALID_INPUT")
        check(
            "scope_dry_run_payload_validation_only",
            boundary.scope == "MT5_DRY_RUN_PAYLOAD_VALIDATION_ONLY",
            "INVALID_INPUT",
        )
        check(
            "dry_run_payload_validation_workflow_allowed",
            boundary.mt5_dry_run_payload_validation_workflow_allowed is True,
            "PRE_MT5_MAPPING_WORKFLOW_NOT_ALLOWED",
        )
        check("live_execution_disabled", boundary.live_execution_allowed is False, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_submission_disabled", boundary.order_send_allowed is False, "ORDER_SEND_STILL_FORBIDDEN")
        check("execution_disabled", boundary.execution_allowed is False, "EXECUTION_STILL_FORBIDDEN")
        check("non_executable", boundary.executable is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("no_mt5_payload", boundary.mt5_payload_created is False, "MT5_PAYLOAD_NOT_ALLOWED")
        check("no_mt5_request_dict", boundary.mt5_request_dict_created is False, "MT5_REQUEST_DICT_NOT_ALLOWED")
        check("not_order_sent", boundary.order_sent is False, "FORBIDDEN_EXECUTION_MARKER")
        check("hard_live_block", boundary.hard_live_block_required is True, "LIVE_EXECUTION_STILL_DISABLED")
        check("order_contract_not_ready", boundary.order_contract_ready is False, "ORDER_CONTRACT_READY_NOT_ALLOWED")
        check("order_mapping_disabled", boundary.order_request_mapping_allowed is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("broker_mapping_absent", boundary.broker_mapping_created is False, "ORDER_REQUEST_MAPPING_NOT_ALLOWED")
        check("raw_values_absent", boundary.raw_values_stored is False, "RAW_VALUES_NOT_ALLOWED")
        check("executable_order_absent", boundary.executable_order_created is False, "EXECUTABLE_ORDER_NOT_ALLOWED")
        check("source_refs_present", bool(boundary.source_refs), "MISSING_SOURCE_REFS")
        check("artifact_hash_present", bool(boundary.artifact_hash), "MISSING_IDEMPOTENCY")
        check("idempotency_present", bool(boundary.idempotency_key), "MISSING_IDEMPOTENCY")

        slots = list(boundary.mapping_slots or [])
        slot_types = {slot.slot_type for slot in slots}
        missing = [item for item in REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES if item not in slot_types]
        invalid = [
            slot.slot_type
            for slot in slots
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
        check(
            "required_mapping_slots_present",
            len(slots) == len(REQUIRED_PRE_MT5_MAPPING_SLOT_TYPES) and not missing,
            "MISSING_REQUIRED_MAPPING_SLOTS",
        )
        check("mapping_slots_schema_only", not invalid, "MISSING_REQUIRED_MAPPING_SLOTS")

        blockers = list(dict.fromkeys(blockers))
        valid = not blockers
        report = PreMT5OrderRequestMappingValidationReport(
            validation_report_id=f"pre_mt5_mapping_validation_{_digest(boundary.mapping_boundary_id)[:16]}",
            created_at=now_utc_iso(),
            source_mapping_boundary_id=boundary.mapping_boundary_id,
            valid=valid,
            mt5_dry_run_payload_validation_workflow_allowed=valid,
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
            mapping_slots_count=len(slots),
            mapped_slots_count=len(slots) if valid else 0,
            missing_slots_count=len(missing),
            invalid_slots_count=len(invalid),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(boundary.warnings or []),
            source_refs=list(boundary.source_refs or []),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
