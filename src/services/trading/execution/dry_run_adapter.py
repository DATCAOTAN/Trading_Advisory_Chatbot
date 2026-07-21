from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.idempotency import IdempotencyKeyBuilder
from src.services.trading.execution.models import DryRunExecutionReceipt, ExecutionGateDecision, now_utc_iso
from src.services.trading.execution.validator import ExecutionGateValidator
from src.services.trading.review.models import HumanReviewArtifact


class DryRunExecutionAdapter:
    def __init__(self, validator: ExecutionGateValidator | None = None):
        self.validator = validator or ExecutionGateValidator()
        self.key_builder = IdempotencyKeyBuilder()

    def run(self, gate_decision: ExecutionGateDecision, artifact: HumanReviewArtifact) -> DryRunExecutionReceipt:
        created_at = now_utc_iso()
        idempotency_key = self.key_builder.build(
            artifact.artifact_id,
            gate_decision.artifact_hash,
            gate_decision.mode,
            artifact.symbol,
            artifact.created_at,
        )
        allowed = bool(gate_decision.allowed and gate_decision.action == "ALLOW_DRY_RUN")
        receipt = DryRunExecutionReceipt(
            receipt_id=_receipt_id(gate_decision.gate_decision_id, created_at),
            created_at=created_at,
            mode=gate_decision.mode,
            symbol=gate_decision.symbol,
            broker_symbol=gate_decision.broker_symbol,
            dry_run_only=True,
            gate_action=gate_decision.action,
            allowed=allowed,
            executed=False,
            execution_provider="dry_run_gate",
            artifact_id=artifact.artifact_id,
            artifact_hash=gate_decision.artifact_hash,
            idempotency_key=idempotency_key,
            blockers=list(gate_decision.blockers),
            warnings=list(gate_decision.warnings),
            message="Dry-run gate passed; no real execution was attempted." if allowed else f"Dry-run gate blocked: {gate_decision.reason}",
            source_gate_decision_id=gate_decision.gate_decision_id,
            source_review_artifact_id=artifact.artifact_id,
            source_refs=list(gate_decision.source_refs),
        )
        receipt.payload_size_chars = len(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
        validation = self.validator.validate_receipt(receipt)
        if not validation.passed:
            receipt.allowed = False
            receipt.blockers.extend(validation.issues)
            receipt.blockers = list(dict.fromkeys(receipt.blockers))
            receipt.message = "Dry-run receipt validation failed; no real execution was attempted."
            receipt.payload_size_chars = len(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
        return receipt


def _receipt_id(gate_decision_id: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{gate_decision_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"dry_run_receipt_{digest}"
