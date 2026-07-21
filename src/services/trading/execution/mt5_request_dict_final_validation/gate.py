from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.mt5_request_dict_final_validation.models import (
    REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES,
    MT5RequestDictFinalValidationBoundary,
    MT5RequestDictFinalValidationReport,
    now_utc_iso,
)
from src.services.trading.execution.mt5_request_dict_final_validation.policy import MT5RequestDictFinalValidationConfig


class MT5RequestDictFinalValidationGate:
    def __init__(self, config: MT5RequestDictFinalValidationConfig | None = None):
        self.config = config or MT5RequestDictFinalValidationConfig.from_config()

    def validate(self, boundary: MT5RequestDictFinalValidationBoundary) -> MT5RequestDictFinalValidationReport:
        fields = list(boundary.validated_fields or [])
        missing = list(boundary.missing_field_categories or [])
        invalid = list(boundary.invalid_field_categories or [])
        approved_integrity = bool(
            boundary.approved_semantic_values_present
            and boundary.approved_semantic_values_verified
            and boundary.approved_semantic_values_hash
            and boundary.artifact_hash == boundary.approved_semantic_values_hash
        )
        checks = {
            "source_boundary_present": bool(boundary.source_dry_run_request_dict_id),
            "source_report_present": bool(boundary.source_dry_run_request_dict_validation_report_id),
            "source_refs_present": bool(boundary.source_refs),
            "idempotency_present": bool(boundary.idempotency_key),
            "required_fields_present": len(fields) == len(REQUIRED_MT5_REQUEST_DICT_FINAL_VALIDATION_FIELD_CATEGORIES),
            "no_missing_fields": not missing,
            "no_invalid_fields": not invalid,
            "no_payload_or_execution": _safety_flags_false(boundary),
            "hard_block_required": boundary.hard_live_block_required is True,
            "approved_semantic_values_integrity": (
                not boundary.approved_semantic_values_required or approved_integrity
            ),
        }
        valid = all(checks.values()) and not boundary.blockers and boundary.status == "FINAL_VALIDATION_PASSED"
        report = MT5RequestDictFinalValidationReport(
            validation_report_id=_report_id(boundary.final_validation_id),
            created_at=now_utc_iso(),
            source_final_validation_id=boundary.final_validation_id,
            valid=valid,
            bridge_write_skeleton_check_allowed=valid,
            validated_fields_count=len(fields),
            missing_fields_count=len(missing),
            invalid_fields_count=len(invalid),
            validation_checks={
                **checks,
                "approved_semantic_values_present": boundary.approved_semantic_values_present,
                "approved_semantic_values_verified": approved_integrity,
            },
            blockers=[] if valid else list(dict.fromkeys(list(boundary.blockers) + [key for key, passed in checks.items() if not passed])),
            warnings=list(boundary.warnings),
            source_refs=list(boundary.source_refs),
        )
        report.payload_size_chars = len(json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False))
        return report


def _safety_flags_false(item) -> bool:
    return not any(
        bool(getattr(item, name, False))
        for name in [
            "live_execution_allowed",
            "order_send_allowed",
            "execution_allowed",
            "executable",
            "real_mt5_payload_created",
            "broker_submittable_request_dict_created",
            "mt5_constants_used",
            "broker_submission_created",
            "order_sent",
        ]
    )


def _report_id(source_id: str) -> str:
    return "mt5_request_dict_final_validation_report_" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
