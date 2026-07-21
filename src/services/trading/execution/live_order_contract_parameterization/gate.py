from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.live_order_contract_parameterization.models import (
    REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES,
    LiveOrderContractParameterizationBoundary,
    LiveOrderContractParameterizationValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.live_order_contract_parameterization.policy import (
    LiveOrderContractParameterizationConfig,
)


class LiveOrderContractParameterizationGate:
    def __init__(self, config: LiveOrderContractParameterizationConfig | None = None):
        self.config = config or LiveOrderContractParameterizationConfig.from_config()

    def validate(
        self, parameterization: LiveOrderContractParameterizationBoundary
    ) -> LiveOrderContractParameterizationValidationReport:
        slot_types = {slot.slot_type for slot in parameterization.contract_slots}
        checks = [
            _check("parameterization_boundary_created", parameterization.status == "PARAMETERIZATION_BOUNDARY_CREATED"),
            _check("scope_contract_validation_only", parameterization.scope == "CONTRACT_VALIDATION_ONLY"),
            _check("contract_validation_workflow_allowed", parameterization.contract_validation_workflow_allowed is True),
            _check("live_execution_disabled", parameterization.live_execution_allowed is False),
            _check("order_submission_disabled", parameterization.order_send_allowed is False),
            _check("execution_disabled", parameterization.execution_allowed is False),
            _check("not_executable", parameterization.executable is False),
            _check("mt5_payload_not_created", parameterization.mt5_payload_created is False),
            _check("order_not_sent", parameterization.order_sent is False),
            _check("hard_block_required", parameterization.hard_live_block_required is True),
            _check("order_contract_not_ready", parameterization.order_contract_ready is False),
            _check("order_request_mapping_not_allowed", parameterization.order_request_mapping_allowed is False),
            _check("raw_values_not_stored", parameterization.raw_values_stored is False),
            _check("executable_order_not_created", parameterization.executable_order_created is False),
            _check("exactly_nine_contract_slots", len(parameterization.contract_slots) == len(REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES)),
            _check("required_contract_slot_types_present", slot_types == set(REQUIRED_CONTRACT_PARAMETER_SLOT_TYPES)),
            _check(
                "contract_slots_validation_only",
                all(
                    slot.parameterized_for_validation_only
                    and not slot.raw_value_stored
                    and slot.redacted_value_reference_present
                    and not slot.executable_value
                    and not slot.mt5_payload_value
                    and not slot.order_request_value
                    and slot.contract_validation_required
                    and slot.final_human_review_required
                    for slot in parameterization.contract_slots
                ),
            ),
            _check("source_refs_present", bool(parameterization.source_refs)),
            _check("idempotency_present", bool(parameterization.idempotency_key)),
            _check("artifact_hash_present", bool(parameterization.artifact_hash)),
        ]
        valid = all(item["passed"] for item in checks) and not parameterization.blockers
        blockers = [] if valid else list(dict.fromkeys(list(parameterization.blockers) + [item["check_id"] for item in checks if not item["passed"]]))
        report = LiveOrderContractParameterizationValidationReport(
            validation_report_id=f"live_order_contract_parameterization_validation_{_hash(parameterization.parameterization_id + now_utc_iso())[:16]}",
            created_at=now_utc_iso(),
            source_parameterization_id=parameterization.parameterization_id,
            valid=valid,
            contract_validation_workflow_allowed=valid,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            order_contract_ready=False,
            order_request_mapping_allowed=False,
            raw_values_stored=False,
            executable_order_created=False,
            contract_slots_count=len(parameterization.contract_slots),
            parameterized_slots_count=sum(1 for slot in parameterization.contract_slots if slot.parameterized_for_validation_only),
            missing_slots_count=len(parameterization.missing_contract_slot_types),
            invalid_slots_count=len(parameterization.invalid_contract_slot_types),
            validation_checks=checks,
            blockers=blockers,
            warnings=list(parameterization.warnings),
            source_refs=list(parameterization.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return report


def _check(check_id: str, passed: bool) -> dict:
    return {"check_id": check_id, "passed": bool(passed)}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
