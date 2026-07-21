from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.services.trading.execution.live_order_parameter_policy.models import (
    REQUIRED_PARAMETER_POLICY_GROUP_LABELS,
    LiveOrderParameterPolicyRule,
    LiveOrderParameterPolicySpec,
)
from src.services.trading.execution.live_order_parameter_policy.policy import LiveOrderParameterPolicyConfig


class LiveOrderParameterPolicyRuleBuilder:
    def build_rules(self, source_refs: list[str] | None = None) -> list[LiveOrderParameterPolicyRule]:
        refs = list(source_refs or [])
        return [
            self._rule(
                "SIDE_POLICY",
                "Directional source policy",
                "Requires a future human-reviewed directional source boundary and does not resolve a direction.",
                ["human reviewed directional source", "proposal traceability", "permission gate provenance"],
                ["side", "direction", "BUY", "SELL", "LONG", "SHORT", "trade_side"],
                refs,
                human_review=True,
            ),
            self._rule(
                "PRICE_POLICY",
                "Pricing source policy",
                "Requires future data freshness, spread sanity, and symbol mapping evidence without resolving a price.",
                ["market data freshness", "spread sanity", "broker symbol mapping"],
                ["entry", "entry_price", "price", "quote"],
                refs,
            ),
            self._rule(
                "PROTECTION_POLICY",
                "Protection policy evidence",
                "Requires future invalidation and protection evidence without resolving protection values.",
                ["invalidation logic", "protection policy evidence", "human review trace"],
                ["stop_loss", "take_profit", "protection_value"],
                refs,
                human_review=True,
            ),
            self._rule(
                "VOLUME_POLICY",
                "Volume constraint policy",
                "Requires future broker min, max, and step constraints without resolving amount.",
                ["broker minimum constraint", "broker maximum constraint", "broker step constraint"],
                ["lot", "volume", "amount"],
                refs,
            ),
            self._rule(
                "RISK_POLICY",
                "Risk evidence policy",
                "Requires future risk policy evidence without resolving account risk or size.",
                ["risk policy evidence", "risk cap evidence", "human review trace"],
                ["account_risk", "position_size", "risk_value"],
                refs,
                human_review=True,
            ),
            self._rule(
                "BROKER_SYMBOL_POLICY",
                "Broker symbol mapping policy",
                "Requires future broker symbol mapping evidence and must not store raw account identifiers.",
                ["broker symbol mapping", "redacted account metadata"],
                ["unredacted account identifier", "secret material"],
                refs,
            ),
            self._rule(
                "EXECUTION_TIMING_POLICY",
                "Execution timing policy",
                "Requires future spread, calendar, session, and freshness checks without scheduling execution.",
                ["spread check", "calendar check", "session check", "data freshness check"],
                ["execution_time", "schedule_order", "execute_trade"],
                refs,
            ),
            self._rule(
                "IDEMPOTENCY_POLICY",
                "Idempotency policy",
                "Requires artifact hash and idempotency key; duplicate keys block the workflow.",
                ["artifact hash", "idempotency key", "duplicate key journal lookup"],
                ["duplicate_bypass", "idempotency_override"],
                refs,
            ),
            self._rule(
                "AUDIT_POLICY",
                "Audit and redaction policy",
                "Requires source references, append-only journal evidence, and redaction.",
                ["source references", "append-only journal", "redaction evidence"],
                ["raw market series", "raw source document", "credential material"],
                refs,
                human_review=True,
            ),
        ]

    def _rule(
        self,
        group: str,
        title: str,
        description: str,
        future_evidence: list[str],
        forbidden_values: list[str],
        source_refs: list[str],
        human_review: bool = False,
    ) -> LiveOrderParameterPolicyRule:
        return LiveOrderParameterPolicyRule(
            rule_id=f"live_order_parameter_policy_rule_{group.lower()}",
            group=group,
            title=title,
            status="SATISFIED_AS_POLICY_ONLY",
            severity="BLOCKING",
            required=True,
            blocking=True,
            policy_description=description,
            future_evidence_required=future_evidence,
            future_source_boundary_required=True,
            human_review_required=human_review,
            deterministic_validation_required=True,
            forbidden_actual_values=forbidden_values,
            source_refs=source_refs,
        )


class LiveOrderParameterPolicySpecBuilder:
    def __init__(
        self,
        config: LiveOrderParameterPolicyConfig | None = None,
        rule_builder: LiveOrderParameterPolicyRuleBuilder | None = None,
    ):
        self.config = config or LiveOrderParameterPolicyConfig.from_config()
        self.rule_builder = rule_builder or LiveOrderParameterPolicyRuleBuilder()

    def build(
        self,
        contract_skeleton,
        contract_skeleton_validation,
        live_order_intent,
        live_order_intent_validation,
        permission_decision,
        preflight_report,
        proposal_draft,
        simulated_contract,
        simulated_receipt=None,
        current_time: datetime | None = None,
        existing_idempotency_keys: Iterable[str] | None = None,
    ) -> LiveOrderParameterPolicySpec:
        now = current_time or datetime.now(timezone.utc)
        created_at = now.isoformat()
        source_time = _parse_datetime(
            getattr(contract_skeleton, "created_at", "")
            or getattr(live_order_intent, "created_at", "")
            or getattr(preflight_report, "created_at", "")
        )
        expires_at_dt = source_time + timedelta(seconds=self.config.ttl_seconds)
        expires_at = expires_at_dt.isoformat()
        source_refs = _dedupe(
            list(getattr(contract_skeleton, "source_refs", []) or [])
            + list(getattr(contract_skeleton_validation, "source_refs", []) or [])
            + list(getattr(live_order_intent, "source_refs", []) or [])
            + list(getattr(live_order_intent_validation, "source_refs", []) or [])
            + list(getattr(permission_decision, "source_refs", []) or [])
            + list(getattr(preflight_report, "source_refs", []) or [])
            + list(getattr(proposal_draft, "source_refs", []) or [])
            + list(getattr(simulated_contract, "source_refs", []) or [])
            + list(getattr(simulated_receipt, "source_refs", []) or [])
        )
        artifact_hash = (
            getattr(contract_skeleton, "artifact_hash", "")
            or getattr(live_order_intent, "artifact_hash", "")
            or getattr(simulated_contract, "artifact_hash", "")
            or getattr(simulated_receipt, "artifact_hash", "")
        )
        base_idempotency = (
            getattr(contract_skeleton, "idempotency_key", "")
            or getattr(live_order_intent, "idempotency_key", "")
            or getattr(simulated_contract, "idempotency_key", "")
            or getattr(simulated_receipt, "idempotency_key", "")
        )
        idempotency_key = _stable_hash(
            "|".join(
                [
                    "live_order_parameter_policy_v1",
                    base_idempotency,
                    getattr(live_order_intent, "intent_id", ""),
                    getattr(permission_decision, "decision_id", ""),
                    getattr(preflight_report, "report_id", ""),
                    getattr(proposal_draft, "draft_id", ""),
                    getattr(simulated_contract, "contract_id", ""),
                ]
            )
        )

        blockers: list[str] = []
        if not self.config.enabled:
            blockers.append("INVALID_INPUT")
        if contract_skeleton is None and self.config.require_contract_skeleton:
            blockers.append("MISSING_CONTRACT_SKELETON")
        if contract_skeleton_validation is None and self.config.require_valid_contract_skeleton:
            blockers.append("MISSING_CONTRACT_SKELETON_VALIDATION")
        if self.config.require_valid_contract_skeleton:
            if getattr(contract_skeleton_validation, "valid", False) is not True:
                blockers.append("MISSING_CONTRACT_SKELETON_VALIDATION")
            if getattr(contract_skeleton_validation, "contract_parameter_validation_allowed", False) is not True:
                blockers.append("CONTRACT_PARAMETER_VALIDATION_NOT_ALLOWED")
            if getattr(contract_skeleton, "contract_parameter_validation_allowed", False) is not True:
                blockers.append("CONTRACT_PARAMETER_VALIDATION_NOT_ALLOWED")
        if live_order_intent is None and self.config.require_live_order_intent:
            blockers.append("MISSING_LIVE_ORDER_INTENT")
        if permission_decision is None and self.config.require_permission_decision:
            blockers.append("MISSING_PERMISSION_DECISION")
        elif getattr(permission_decision, "gate_allowed", False) is not True:
            blockers.append("MISSING_PERMISSION_DECISION")
        if preflight_report is None:
            blockers.append("MISSING_PREFLIGHT_REPORT")
        elif self.config.require_preflight_pass and getattr(preflight_report, "preflight_status", "") != "PASS":
            blockers.append("MISSING_PREFLIGHT_REPORT")
        if proposal_draft is None and self.config.require_proposal_draft:
            blockers.append("MISSING_PROPOSAL_DRAFT")
        if simulated_contract is None and self.config.require_simulated_contract:
            blockers.append("MISSING_SIMULATED_CONTRACT")
        required_groups = list(getattr(contract_skeleton, "required_parameter_groups", []) or [])
        if not required_groups or set(required_groups) != set(REQUIRED_PARAMETER_POLICY_GROUP_LABELS):
            blockers.append("MISSING_PARAMETER_GROUPS")
        if getattr(contract_skeleton, "resolved_parameter_groups", []) or _actual_values_present(contract_skeleton):
            blockers.append("RESOLVED_PARAMETER_VALUES_NOT_ALLOWED")
        if self.config.require_source_refs and not source_refs:
            blockers.append("MISSING_SOURCE_REFS")
        if self.config.require_idempotency and (not artifact_hash or not base_idempotency or not idempotency_key):
            blockers.append("MISSING_IDEMPOTENCY")
        if now > expires_at_dt:
            blockers.append("EXPIRED_POLICY_SPEC")
        if idempotency_key and idempotency_key in set(existing_idempotency_keys or []):
            blockers.append("DUPLICATE_POLICY_SPEC")
        if _unsafe_execution_flags(
            contract_skeleton,
            contract_skeleton_validation,
            live_order_intent,
            live_order_intent_validation,
            permission_decision,
            preflight_report,
        ):
            blockers.append("LIVE_EXECUTION_STILL_DISABLED")
        if _unsafe_sources(proposal_draft, simulated_contract):
            blockers.append("FORBIDDEN_EXECUTION_MARKER")

        blockers = _dedupe(blockers)
        allowed = not blockers
        status = "POLICY_VALIDATED" if allowed else "BLOCKED"
        if "EXPIRED_POLICY_SPEC" in blockers:
            status = "EXPIRED"
        if "DUPLICATE_POLICY_SPEC" in blockers:
            status = "DUPLICATE"
        scope = "PARAMETER_SOURCE_BOUNDARY_ONLY" if allowed else "EXECUTION_NOT_ALLOWED"
        rules = self.rule_builder.build_rules(source_refs)
        spec = LiveOrderParameterPolicySpec(
            policy_spec_id=f"live_order_parameter_policy_{_stable_hash(f'{idempotency_key}|{created_at}')[:16]}",
            created_at=created_at,
            mode=getattr(contract_skeleton, "mode", getattr(live_order_intent, "mode", "REVIEW_ONLY")),
            symbol=getattr(contract_skeleton, "symbol", getattr(live_order_intent, "symbol", "")),
            broker_symbol=getattr(contract_skeleton, "broker_symbol", getattr(live_order_intent, "broker_symbol", "")),
            status=status,
            scope=scope,
            parameter_source_boundary_allowed=allowed,
            live_execution_allowed=False,
            order_send_allowed=False,
            execution_allowed=False,
            executable=False,
            mt5_payload_created=False,
            order_sent=False,
            hard_live_block_required=True,
            source_contract_skeleton_id=getattr(contract_skeleton, "contract_skeleton_id", ""),
            source_contract_skeleton_validation_id=getattr(contract_skeleton_validation, "validation_report_id", ""),
            source_live_order_intent_id=getattr(live_order_intent, "intent_id", ""),
            source_live_order_intent_validation_id=getattr(live_order_intent_validation, "validation_report_id", ""),
            source_live_permission_decision_id=getattr(permission_decision, "decision_id", ""),
            source_preflight_report_id=getattr(preflight_report, "report_id", ""),
            source_proposal_draft_id=getattr(proposal_draft, "draft_id", ""),
            source_simulated_contract_id=getattr(simulated_contract, "contract_id", ""),
            required_parameter_groups=list(REQUIRED_PARAMETER_POLICY_GROUP_LABELS),
            unresolved_parameter_groups=list(REQUIRED_PARAMETER_POLICY_GROUP_LABELS),
            policy_rules=rules,
            resolved_parameter_values_present=False,
            actual_order_values_present=False,
            artifact_hash=artifact_hash,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            blockers=blockers,
            warnings=[],
            reasons=list(blockers),
            source_refs=source_refs,
        )
        spec.payload_size_chars = len(json.dumps(spec.as_dict(), ensure_ascii=False, sort_keys=True))
        return spec


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
        if getattr(item, "executable", False) is not False:
            return True
        if getattr(item, "mt5_payload_created", False) is not False:
            return True
        if getattr(item, "order_sent", False) is not False:
            return True
    return False


def _unsafe_sources(proposal_draft, simulated_contract) -> bool:
    if proposal_draft is not None and getattr(proposal_draft, "executable", True) is not False:
        return True
    if simulated_contract is not None:
        if getattr(simulated_contract, "simulated_only", False) is not True:
            return True
        if getattr(simulated_contract, "executable", True) is not False:
            return True
    return False


def _actual_values_present(item) -> bool:
    if item is None:
        return False
    markers = [
        "resolved_parameter_values_present",
        "actual_order_values_present",
        "mt5_payload_created",
        "executable",
        "order_sent",
    ]
    return any(getattr(item, marker, False) is True for marker in markers)


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
