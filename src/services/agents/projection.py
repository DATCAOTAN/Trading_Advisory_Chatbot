from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence


COMPACT_LIST_LIMIT = 3
LIMITATION_LIMIT = 5


@dataclass
class TaskAnalysisSnapshot:
    request_id: str = ""
    task_id: str = ""
    parent_task_id: str = ""
    intent_family: str = ""
    symbol: str = ""
    temporal_scope: str = ""
    as_of: str = ""
    evidence_bundle_ref: str = ""
    allowed_evidence_refs: List[str] = field(default_factory=list)
    allowed_source_refs: List[str] = field(default_factory=list)
    market_context: Dict[str, Any] = field(default_factory=dict)
    strategy: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    consistency: Dict[str, Any] = field(default_factory=dict)
    compliance: Dict[str, Any] = field(default_factory=dict)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "temporal_scope": self.temporal_scope,
            "as_of": self.as_of,
            "evidence_bundle_ref": self.evidence_bundle_ref,
            "allowed_evidence_refs": list(self.allowed_evidence_refs),
            "allowed_source_refs": list(self.allowed_source_refs),
            "market_context": dict(self.market_context),
            "strategy": dict(self.strategy),
            "risk": dict(self.risk),
            "consistency": dict(self.consistency),
            "compliance": dict(self.compliance),
            "execution_allowed": self.execution_allowed,
        }


def compact_agent_payload(agent_type: str, payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    data = dict(payload or {})
    if not data:
        return {}
    if agent_type == "MarketContextAgent":
        return compact_market_context_assessment(data)
    if agent_type == "StrategyAgent":
        return compact_strategy_thesis(data)
    if agent_type == "RiskAgent":
        return compact_risk_assessment(data)
    if agent_type == "StrategyRiskConsistencyAgent":
        return compact_consistency_assessment(data)
    return _strip_diagnostics(data)


def compact_market_context_assessment(data: Mapping[str, Any]) -> Dict[str, Any]:
    uncertainty = data.get("uncertainty") if isinstance(data.get("uncertainty"), Mapping) else {}
    macro_context = data.get("macro_context") if isinstance(data.get("macro_context"), Mapping) else {}
    return {
        "request_id": data.get("request_id", ""),
        "task_id": data.get("task_id", ""),
        "symbol": data.get("symbol", ""),
        "as_of": data.get("as_of", ""),
        "assessment_ref": data.get("assessment_ref", ""),
        "market_state": dict(data.get("market_state") or {}),
        "macro_context": {
            "active_events": list(macro_context.get("active_events") or [])[:COMPACT_LIST_LIMIT],
            "macro_pressure": macro_context.get("macro_pressure", ""),
            "inflation_context": macro_context.get("inflation_context", False),
            "rates_context": macro_context.get("rates_context", False),
            "usd_context": macro_context.get("usd_context", False),
        },
        "dominant_factors": _compact_items(data.get("dominant_factors") or []),
        "conflicting_signals": _compact_items(data.get("conflicting_signals") or []),
        "confirmation_conditions": dict(data.get("confirmation_conditions") or {}),
        "invalidation_conditions": list(data.get("invalidation_conditions") or [])[:COMPACT_LIST_LIMIT],
        "uncertainty": {
            "confidence": uncertainty.get("confidence"),
            "confidence_ceiling": uncertainty.get("confidence_ceiling"),
            "missing_context": list(uncertainty.get("missing_context") or [])[:LIMITATION_LIMIT],
            "conflicting_context": list(uncertainty.get("conflicting_context") or [])[:COMPACT_LIST_LIMIT],
            "assumptions": list(uncertainty.get("assumptions") or [])[:COMPACT_LIST_LIMIT],
            "limitations": list(uncertainty.get("limitations") or [])[:LIMITATION_LIMIT],
        },
        "summary": data.get("summary", ""),
        "evidence_refs": list(data.get("evidence_refs") or []),
        "source_refs": list(data.get("source_refs") or []),
    }


def compact_strategy_thesis(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": data.get("request_id", ""),
        "task_id": data.get("task_id", ""),
        "parent_task_id": data.get("parent_task_id", ""),
        "symbol": data.get("symbol", ""),
        "as_of": data.get("as_of", ""),
        "intent_family": data.get("intent_family", ""),
        "thesis_ref": data.get("thesis_ref", ""),
        "thesis_type": data.get("thesis_type", ""),
        "thesis_direction": data.get("thesis_direction", ""),
        "thesis_summary": data.get("thesis_summary", ""),
        "rationale": _compact_items(data.get("rationale") or []),
        "supporting_factors": _compact_items(data.get("supporting_factors") or []),
        "conflicting_factors": _compact_items(data.get("conflicting_factors") or []),
        "activation_conditions": _compact_items(data.get("activation_conditions") or []),
        "invalidation_conditions": _compact_items(data.get("invalidation_conditions") or []),
        "scenario_map": dict(data.get("scenario_map") or {}),
        "assumptions": list(data.get("assumptions") or [])[:COMPACT_LIST_LIMIT],
        "limitations": list(data.get("limitations") or [])[:LIMITATION_LIMIT],
        "missing_context": list(data.get("missing_context") or [])[:LIMITATION_LIMIT],
        "confidence": dict(data.get("confidence") or {}),
        "evidence_refs": list(data.get("evidence_refs") or []),
        "source_refs": list(data.get("source_refs") or []),
        "market_context_refs": list(data.get("market_context_refs") or []),
        "prohibited_outputs_detected": bool(data.get("prohibited_outputs_detected") or False),
    }


def compact_risk_assessment(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": data.get("request_id", ""),
        "task_id": data.get("task_id", ""),
        "parent_task_id": data.get("parent_task_id", ""),
        "symbol": data.get("symbol", ""),
        "as_of": data.get("as_of", ""),
        "intent_family": data.get("intent_family", ""),
        "risk_ref": data.get("risk_ref", ""),
        "assessed_strategy_thesis_ref": data.get("assessed_strategy_thesis_ref", ""),
        "assessed_market_context_ref": data.get("assessed_market_context_ref", ""),
        "overall_risk_level": data.get("overall_risk_level", ""),
        "risk_posture": data.get("risk_posture", ""),
        "confidence_adjustment": dict(data.get("confidence_adjustment") or {}),
        "key_risks": _compact_items(data.get("key_risks") or []),
        "thesis_fragility": _compact_mapping(data.get("thesis_fragility") or {}),
        "conflicting_factors": _compact_items(data.get("conflicting_factors") or []),
        "missing_or_weak_context": list(data.get("missing_or_weak_context") or [])[:LIMITATION_LIMIT],
        "event_and_volatility_risks": list(data.get("event_and_volatility_risks") or [])[:COMPACT_LIST_LIMIT],
        "confirmation_requirements": _compact_items(data.get("confirmation_requirements") or []),
        "invalidation_risks": _compact_items(data.get("invalidation_risks") or []),
        "risk_summary": data.get("risk_summary", ""),
        "limitations": list(data.get("limitations") or [])[:LIMITATION_LIMIT],
        "evidence_refs": list(data.get("evidence_refs") or []),
        "source_refs": list(data.get("source_refs") or []),
        "market_context_refs": list(data.get("market_context_refs") or []),
        "strategy_thesis_refs": list(data.get("strategy_thesis_refs") or []),
        "prohibited_outputs_detected": bool(data.get("prohibited_outputs_detected") or False),
    }


def compact_consistency_assessment(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": data.get("request_id", ""),
        "task_id": data.get("task_id", ""),
        "parent_task_id": data.get("parent_task_id", ""),
        "symbol": data.get("symbol", ""),
        "as_of": data.get("as_of", ""),
        "intent_family": data.get("intent_family", ""),
        "consistency_ref": data.get("consistency_ref", ""),
        "assessed_market_context_ref": data.get("assessed_market_context_ref", ""),
        "assessed_strategy_thesis_ref": data.get("assessed_strategy_thesis_ref", ""),
        "assessed_risk_assessment_ref": data.get("assessed_risk_assessment_ref", ""),
        "consistency_status": data.get("consistency_status", ""),
        "final_presentation_mode": data.get("final_presentation_mode", ""),
        "thesis_strength_after_risk": data.get("thesis_strength_after_risk", ""),
        "confidence_reconciliation": dict(data.get("confidence_reconciliation") or {}),
        "agreement_points": _compact_items(data.get("agreement_points") or []),
        "contradiction_points": _compact_items(data.get("contradiction_points") or []),
        "required_final_answer_emphasis": list(data.get("required_final_answer_emphasis") or []),
        "prohibited_final_answer_patterns": list(data.get("prohibited_final_answer_patterns") or []),
        "final_synthesis_guidance": data.get("final_synthesis_guidance", ""),
        "limitations": list(data.get("limitations") or [])[:LIMITATION_LIMIT],
        "evidence_refs": list(data.get("evidence_refs") or []),
        "source_refs": list(data.get("source_refs") or []),
        "market_context_refs": list(data.get("market_context_refs") or []),
        "strategy_thesis_refs": list(data.get("strategy_thesis_refs") or []),
        "risk_assessment_refs": list(data.get("risk_assessment_refs") or []),
        "prohibited_outputs_detected": bool(data.get("prohibited_outputs_detected") or False),
    }


def compact_compliance_result(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": data.get("status", ""),
        "aggregate_status": data.get("aggregate_status", ""),
        "reason_codes": list(data.get("reason_codes") or []),
        "final_answer_action": data.get("final_answer_action", ""),
        "task_results": _compact_items(data.get("task_results") or []),
        "repair_guidance": list(data.get("repair_guidance") or [])[:LIMITATION_LIMIT],
    }


def log_projection(task_id: str, projection_type: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    before_chars = _chars(before)
    after_chars = _chars(after)
    preserved_refs = sorted(_refs(after))
    dropped = sorted(set(before.keys()) - set(after.keys())) if isinstance(before, Mapping) else []
    print(
        "[AgentInputProjection] "
        f"task_id={task_id} projection_type={projection_type} "
        f"before_chars={before_chars} after_chars={after_chars} "
        f"preserved_refs={preserved_refs} "
        f"dropped_diagnostic_fields={dropped} status=PASS"
    )


def _compact_items(items: Sequence[Any], limit: int = COMPACT_LIST_LIMIT) -> List[Any]:
    output: List[Any] = []
    for item in list(items or [])[:limit]:
        if isinstance(item, Mapping):
            output.append(_compact_mapping(item))
        else:
            output.append(item)
    return output


def _compact_mapping(item: Mapping[str, Any]) -> Dict[str, Any]:
    keep = {
        "factor",
        "category",
        "direction",
        "directional_pressure",
        "support_strength",
        "confidence",
        "severity",
        "likelihood",
        "risk_type",
        "description",
        "statement",
        "signal_a",
        "signal_b",
        "explanation",
        "conflict_with",
        "condition",
        "requirement",
        "reason",
        "strategy_claim",
        "risk_objection",
        "point",
        "evidence_refs",
        "source_refs",
        "market_context_refs",
        "strategy_thesis_refs",
        "risk_assessment_refs",
        "context_refs",
    }
    compact: Dict[str, Any] = {}
    for key, value in item.items():
        if key not in keep:
            continue
        if isinstance(value, list):
            compact[key] = list(value)[:LIMITATION_LIMIT]
        elif isinstance(value, Mapping):
            compact[key] = dict(value)
        else:
            compact[key] = value
    return compact


def _strip_diagnostics(data: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(data)
    output.pop("market_context_input", None)
    return output


def _refs(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).endswith("_ref") and item:
                yield str(item)
            elif str(key).endswith("_refs") and isinstance(item, list):
                for ref in item:
                    if ref:
                        yield str(ref)
            yield from _refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _refs(item)


def _chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))
