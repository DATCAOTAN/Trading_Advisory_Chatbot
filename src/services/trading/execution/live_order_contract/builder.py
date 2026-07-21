from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_contract.models import (
    REQUIRED_PARAMETER_GROUP_LABELS,
    LiveOrderContractSkeleton,
)
from src.services.trading.execution.live_order_contract.policy import LiveOrderContractSkeletonPolicy


class LiveOrderContractSkeletonBuilder:
    def __init__(self, policy: LiveOrderContractSkeletonPolicy | None = None):
        self.policy = policy or LiveOrderContractSkeletonPolicy.from_config()

    def build(
        self,
        live_order_intent,
        live_order_intent_validation,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LiveOrderContractSkeleton:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(getattr(live_order_intent, "created_at", "") or getattr(preflight_report, "created_at", ""))
        expires_at_dt = source_time + timedelta(seconds=self.policy.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(live_order_intent, "source_refs", []) or [])
            + list(getattr(live_order_intent_validation, "source_refs", []) or [])
            + list(getattr(permission_decision, "source_refs", []) or [])
            + list(getattr(preflight_report, "source_refs", []) or [])
            + list(getattr(proposal_draft, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
            + list(getattr(simulated_receipt, "source_refs", []) or [])
        )
        artifact_hash = (
            getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "live_order_contract_skeleton_v1",
                    base_idempotency,
                    getattr(live_order_intent_validation, "validation_report_id", ""),
                    getattr(permission_decision, "decision_id", ""),
                    getattr(preflight_report, "report_id", ""),
                    getattr(proposal_draft, "draft_id", ""),
                    getattr(simulated_contract, "contract_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.policy.enabled:
            blockers.append("INVALID_INPUT")
        if live_order_intent is None and self.policy.require_live_order_intent:
            blockers.append("MISSING_LIVE_ORDER_INTENT")
        if live_order_intent_validation is None and self.policy.require_valid_intent:
            blockers.append("MISSING_LIVE_ORDER_INTENT_VALIDATION")
        if self.policy.require_valid_intent:
            if getattr(live_order_intent_validation, "valid", False) is not True:
                blockers.append("MISSING_LIVE_ORDER_INTENT_VALIDATION")
            if getattr(live_order_intent_validation, "order_contract_workflow_allowed", False) is not True:
                blockers.append("ORDER_CONTRACT_WORKFLOW_NOT_ALLOWED")
            if getattr(live_order_intent, "order_contract_workflow_allowed", False) is not True:
                blockers.append("ORDER_CONTRACT_WORKFLOW_NOT_ALLOWED")
        if permission_decision is None and self.policy.require_permission_decision:
            blockers.append("MISSING_PERMISSION_DECISION")
        elif getattr(permission_decision, "gate_allowed", False) is not True:
            blockers.append("MISSING_PERMISSION_DECISION")
        if preflight_report is None:
            blockers.append("MISSING_PREFLIGHT_REPORT")
        elif self.policy.require_preflight_pass and getattr(preflight_report, "preflight_status", "") != "PASS":
            blockers.append("MISSING_PREFLIGHT_REPORT")
        if proposal_draft is None and self.policy.require_proposal_draft:
            blockers.append("MISSING_PROPOSAL_DRAFT")
        if self.policy.require_non_executable_proposal_draft and proposal_draft is not None:
            if getattr(proposal_draft, "non_executable", False) is not True or getattr(proposal_draft, "executable", True) is not False:
                blockers.append("MISSING_PROPOSAL_DRAFT")
        if simulated_contract is None and self.policy.require_simulated_contract:
            blockers.append("MISSING_SIMULATED_CONTRACT")
        if simulated_contract is not None:
            if getattr(simulated_contract, "simulated_only", False) is not True or getattr(simulated_contract, "executable", True) is not False:
                blockers.append("MISSING_SIMULATED_CONTRACT")
        if self.policy.require_source_refs and not source_refs:
            blockers.append("MISSING_SOURCE_REFS")
        if self.policy.require_idempotency and (not artifact_hash or not base_idempotency or not idempotency_key):
            blockers.append("MISSING_IDEMPOTENCY")
        if now > expires_at_dt:
            blockers.append("EXPIRED_CONTRACT_SKELETON")
        existing = set(existing_idempotency_keys or [])
        if idempotency_key and idempotency_key in existing:
            blockers.append("DUPLICATE_CONTRACT_SKELETON")
        if _unsafe_execution_flags(live_order_intent, live_order_intent_validation, permission_decision, preflight_report):
            blockers.append("LIVE_EXECUTION_STILL_DISABLED")
        if _unsafe_draft_or_contract(proposal_draft, simulated_contract):
            blockers.append("FORBIDDEN_EXECUTION_MARKER")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "SKELETON_CREATED" if allowed else "BLOCKED"
        if "EXPIRED_CONTRACT_SKELETON" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_CONTRACT_SKELETON" in blockers:
            status = "DUPLICATE"
        scope = "CONTRACT_PARAMETER_VALIDATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        skeleton = LiveOrderContractSkeleton(
            contract_skeleton_id=f"live_order_contract_skeleton_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(live_order_intent, "mode", getattr(proposal_draft, "mode", "REVIEW_ONLY")),
            symbol=getattr(live_order_intent, "symbol", getattr(proposal_draft, "symbol", "")),
            broker_symbol=getattr(live_order_intent, "broker_symbol", getattr(proposal_draft, "broker_symbol", "")),
            status=status,
            scope=scope,
            contract_parameter_validation_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_order_intent_validation_id=getattr(live_order_intent_validation, "validation_report_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            required_parameter_groups=list(REQUIRED_PARAMETER_GROUP_LABELS),
            missing_parameter_groups=list(REQUIRED_PARAMETER_GROUP_LABELS),
            resolved_parameter_groups=[],
            forbidden_parameter_groups=[],
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        skeleton.payload_size_chars = len(json.dumps(skeleton.as_dict(), ensure_ascii=False, sort_keys=True))
        return skeleton


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
    return False


def _unsafe_draft_or_contract(proposal_draft, simulated_contract) -> bool:
    if proposal_draft is not None and getattr(proposal_draft, "executable", True) is not False:
        return True
    if simulated_contract is not None and getattr(simulated_contract, "executable", True) is not False:
        return True
    return False


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
