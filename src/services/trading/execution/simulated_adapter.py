from __future__ import annotations

import hashlib
import json

from src.services.trading.execution.adapter_models import (
    ExecutionAdapterHealth,
    SimulatedExecutionReceipt,
    SimulatedOrderContract,
    now_utc_iso,
)
from src.services.trading.execution.adapter_policy import ExecutionAdapterPolicy
from src.services.trading.execution.adapter_validator import ExecutionAdapterContractValidator


class SimulatedExecutionAdapter:
    provider_name = "simulated_execution_adapter"

    def __init__(
        self,
        policy: ExecutionAdapterPolicy | None = None,
        validator: ExecutionAdapterContractValidator | None = None,
    ):
        self.policy = policy or ExecutionAdapterPolicy.from_config()
        self.validator = validator or ExecutionAdapterContractValidator(max_payload_chars=self.policy.max_payload_chars)

    def adapter_type(self) -> str:
        return "SIMULATED"

    def health_check(self) -> ExecutionAdapterHealth:
        if not self.policy.simulated_adapter_enabled:
            return ExecutionAdapterHealth(
                adapter_type="SIMULATED",
                status="DISABLED",
                message="simulated_adapter_disabled",
                live_execution_supported=False,
                simulated_only=True,
            )
        return ExecutionAdapterHealth(
            adapter_type="SIMULATED",
            status="OK",
            message="simulated_adapter_ready",
            live_execution_supported=False,
            simulated_only=True,
        )

    def validate_contract(self, contract: SimulatedOrderContract):
        return self.validator.validate_contract(contract)

    def submit_simulated(self, contract: SimulatedOrderContract) -> SimulatedExecutionReceipt:
        health = self.health_check()
        validation = self.validate_contract(contract)
        accepted = (
            health.status == "OK"
            and validation.passed
            and contract.contract_status == "CREATED"
            and contract.simulated_only
            and not contract.executable
        )
        blockers = list(contract.blockers)
        warnings = list(contract.warnings)
        if health.status != "OK":
            blockers.append(f"adapter_health_{health.status.lower()}")
        if not validation.passed:
            blockers.extend(validation.issues)
        receipt = SimulatedExecutionReceipt(
            receipt_id=_receipt_id(contract.contract_id, contract.idempotency_key),
            created_at=now_utc_iso(),
            adapter_type="SIMULATED",
            contract_id=contract.contract_id,
            contract_status=contract.contract_status,
            simulated_only=True,
            executable=False,
            executed=False,
            accepted_by_adapter=accepted,
            provider_name=self.provider_name,
            source_draft_id=contract.source_draft_id,
            source_contract_id=contract.contract_id,
            idempotency_key=contract.idempotency_key,
            artifact_hash=contract.artifact_hash,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            message="simulated_contract_accepted" if accepted else "simulated_contract_not_accepted",
            source_refs=list(dict.fromkeys(contract.source_refs)),
        )
        receipt.payload_size_chars = len(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
        receipt_validation = self.validator.validate_receipt(receipt)
        if not receipt_validation.passed:
            receipt.accepted_by_adapter = False
            receipt.blockers.extend(receipt_validation.issues)
            receipt.blockers = list(dict.fromkeys(receipt.blockers))
            receipt.payload_size_chars = len(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
        return receipt

    def close(self) -> None:
        return None


def _receipt_id(contract_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{contract_id}|{idempotency_key}".encode("utf-8")).hexdigest()[:16]
    return f"simulated_receipt_{digest}"
