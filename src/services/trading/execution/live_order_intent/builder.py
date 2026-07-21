from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_intent.models import LiveOrderIntent
from src.services.trading.execution.live_order_intent.policy import LiveOrderIntentPolicy


class LiveOrderIntentBuilder:
    def __init__(self, policy: LiveOrderIntentPolicy | None = None):
        self.policy = policy or LiveOrderIntentPolicy.from_config()

    def build(
        self,
        permission_intent,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LiveOrderIntent:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(getattr(permission_intent, "created_at", "") or getattr(preflight_report, "created_at", ""))
        expires_at_dt = source_time + timedelta(seconds=self.policy.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(permission_intent, "source_refs", []) or [])
            + list(getattr(permission_decision, "source_refs", []) or [])
            + list(getattr(preflight_report, "source_refs", []) or [])
            + list(getattr(proposal_draft, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
            + list(getattr(simulated_receipt, "source_refs", []) or [])
        )
        artifact_hash = (
            getattr(permission_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(permission_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "live_order_intent_v1",
                    base_idempotency,
                    getattr(permission_decision, "decision_id", ""),
                    getattr(preflight_report, "report_id", ""),
                    getattr(proposal_draft, "draft_id", ""),
                    getattr(simulated_contract, "contract_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        warnings: list[str] = []
        if not self.policy.enabled:
            blockers.append("INVALID_INPUT")
        if permission_intent is None and self.policy.require_permission_gate:
            blockers.append("MISSING_PERMISSION_INTENT")
        if permission_decision is None and self.policy.require_permission_gate:
            blockers.append("MISSING_PERMISSION_DECISION")
        if self.policy.require_permission_granted:
            if getattr(permission_intent, "permission_status", "") != "PERMISSION_GRANTED_FOR_ORDER_INTENT_WORKFLOW":
                blockers.append("PERMISSION_NOT_GRANTED")
            if getattr(permission_decision, "gate_allowed", False) is not True:
                blockers.append("PERMISSION_NOT_GRANTED")
            if getattr(permission_decision, "order_intent_workflow_allowed", False) is not True:
                blockers.append("ORDER_INTENT_WORKFLOW_NOT_ALLOWED")
        if self.policy.require_preflight_pass and getattr(preflight_report, "preflight_status", "") != "PASS":
            blockers.append("PREFLIGHT_NOT_PASS")
        if proposal_draft is None and self.policy.require_proposal_draft:
            blockers.append("MISSING_PROPOSAL_DRAFT")
        if self.policy.require_non_executable_proposal_draft and proposal_draft is not None:
            if getattr(proposal_draft, "non_executable", False) is not True or getattr(proposal_draft, "executable", True) is not False:
                blockers.append("PROPOSAL_DRAFT_NOT_NON_EXECUTABLE")
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
            blockers.append("EXPIRED_INTENT")
        existing = set(existing_idempotency_keys or [])
        if idempotency_key and idempotency_key in existing:
            blockers.append("DUPLICATE_INTENT")
        if _unsafe_execution_flags(permission_intent, permission_decision, preflight_report):
            blockers.append("LIVE_EXECUTION_STILL_DISABLED")
        if _unsafe_draft_or_contract(proposal_draft, simulated_contract):
            blockers.append("FORBIDDEN_EXECUTION_MARKER")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "CREATED_FOR_CONTRACT_WORKFLOW" if allowed else "BLOCKED"
        if "EXPIRED_INTENT" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_INTENT" in blockers:
            status = "DUPLICATE"
        scope = "ORDER_CONTRACT_PREPARATION_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        intent = LiveOrderIntent(
            intent_id=f"live_order_intent_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(simulated_contract, "mode", getattr(proposal_draft, "mode", "REVIEW_ONLY")),
            symbol=getattr(simulated_contract, "symbol", getattr(proposal_draft, "symbol", "")),
            broker_symbol=getattr(simulated_contract, "broker_symbol", getattr(proposal_draft, "broker_symbol", "")),
            status=status,
            scope=scope,
            order_contract_workflow_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            hard_live_block_required=True,
            source_live_permission_intent_id=getattr(permission_intent, "intent_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_design_report_id=getattr(preflight_report, "source_design_report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            source_simulated_receipt_id=getattr(simulated_receipt, "receipt_id", ""),
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            permission_status=getattr(permission_intent, "permission_status", "UNKNOWN"),
            permission_scope=getattr(permission_decision, "permission_scope", "UNKNOWN"),
            preflight_status=getattr(preflight_report, "preflight_status", "UNKNOWN"),
            proposal_draft_status=getattr(proposal_draft, "status", "UNKNOWN"),
            simulated_contract_status=getattr(simulated_contract, "contract_status", "UNKNOWN"),
            blockers=blockers,
            warnings=warnings,
            reasons=list(blockers),
            source_refs=source_refs,
        )
        intent.payload_size_chars = len(json.dumps(intent.as_dict(), ensure_ascii=False, sort_keys=True))
        return intent


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
