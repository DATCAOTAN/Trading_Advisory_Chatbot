from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Protocol, Set

from src.services.agents.projection import compact_agent_payload, log_projection
from src.services.agents.runtime import AgentResultEnvelope, AgentRuntimeContext, AgentStatus, AgentTaskEnvelope


RISK_LEVELS = {"low", "moderate", "elevated", "high", "unclear"}
RISK_POSTURES = {
    "acceptable_with_conditions",
    "caution_required",
    "thesis_fragile",
    "insufficient_context",
    "conflicting_context",
    "unclear",
}
SEVERITY = {"low", "moderate", "elevated", "high", "unclear"}
LIKELIHOOD = {"low", "medium", "high", "unclear"}
CONFIDENCE_CEILING = {"high": 0.85, "medium": 0.65, "low": 0.4}

FORBIDDEN_FIELDS = {
    "entry_price",
    "stop_loss",
    "take_profit",
    "lot_size",
    "position_size",
    "account_risk_percent",
    "order_type",
    "buy_now",
    "sell_now",
    "open_position",
    "close_position",
    "execute_trade",
    "place_order",
    "mt5_action",
    "risk_1_percent",
    "risk_2_percent",
    "leverage",
    "margin_usage",
}

FORBIDDEN_TEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bbuy\s+now\b",
        r"\bsell\s+now\b",
        r"\benter\s+(at|now)\b",
        r"\bentry\s+price\b",
        r"\bstop[-\s]?loss\b",
        r"\btake[-\s]?profit\b",
        r"\blot\s+size\b",
        r"\bposition\s+size\b",
        r"\brisk\s+\d+(\.\d+)?\s*%",
        r"\baccount\s+risk\b",
        r"\bleverage\b",
        r"\bmargin\s+usage\b",
        r"\bopen\s+position\b",
        r"\bclose\s+position\b",
        r"\bexecute\s+trade\b",
        r"\bplace\s+order\b",
        r"\bmt5\b",
    ]
]


@dataclass
class RiskInput:
    request_id: str
    task_id: str
    parent_task_id: str
    intent_family: str
    symbol: str = ""
    as_of: str = ""
    temporal_scope: str = ""
    market_context_assessment_ref: str = ""
    market_context_assessment: Dict[str, Any] = field(default_factory=dict)
    strategy_thesis_ref: str = ""
    strategy_thesis: Dict[str, Any] = field(default_factory=dict)
    evidence_bundle_ref: str = ""
    topic_binding_refs: List[str] = field(default_factory=list)
    allowed_evidence_refs: List[str] = field(default_factory=list)
    allowed_source_refs: List[str] = field(default_factory=list)
    allowed_market_context_refs: List[str] = field(default_factory=list)
    allowed_strategy_thesis_refs: List[str] = field(default_factory=list)
    decision_context_ref: str = "decision_context"
    task_context_ref: str = ""
    confidence_ceiling: str = "high"
    missing_context: List[str] = field(default_factory=list)
    limitations_from_market_context: List[str] = field(default_factory=list)
    limitations_from_strategy_thesis: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "temporal_scope": self.temporal_scope,
            "market_context_assessment_ref": self.market_context_assessment_ref,
            "market_context_assessment": dict(self.market_context_assessment),
            "strategy_thesis_ref": self.strategy_thesis_ref,
            "strategy_thesis": dict(self.strategy_thesis),
            "evidence_bundle_ref": self.evidence_bundle_ref,
            "topic_binding_refs": list(self.topic_binding_refs),
            "allowed_evidence_refs": list(self.allowed_evidence_refs),
            "allowed_source_refs": list(self.allowed_source_refs),
            "allowed_market_context_refs": list(self.allowed_market_context_refs),
            "allowed_strategy_thesis_refs": list(self.allowed_strategy_thesis_refs),
            "decision_context_ref": self.decision_context_ref,
            "task_context_ref": self.task_context_ref,
            "confidence_ceiling": self.confidence_ceiling,
            "missing_context": list(self.missing_context),
            "limitations_from_market_context": list(self.limitations_from_market_context),
            "limitations_from_strategy_thesis": list(self.limitations_from_strategy_thesis),
        }


@dataclass
class RiskAssessment:
    request_id: str
    task_id: str
    parent_task_id: str
    symbol: str
    as_of: str
    intent_family: str
    assessed_strategy_thesis_ref: str
    assessed_market_context_ref: str
    overall_risk_level: str
    risk_posture: str
    confidence_adjustment: Dict[str, Any] = field(default_factory=dict)
    key_risks: List[Dict[str, Any]] = field(default_factory=list)
    thesis_fragility: Dict[str, Any] = field(default_factory=dict)
    conflicting_factors: List[Dict[str, Any]] = field(default_factory=list)
    missing_or_weak_context: List[str] = field(default_factory=list)
    event_and_volatility_risks: List[str] = field(default_factory=list)
    confirmation_requirements: List[Dict[str, Any]] = field(default_factory=list)
    invalidation_risks: List[Dict[str, Any]] = field(default_factory=list)
    risk_summary: str = ""
    limitations: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    market_context_refs: List[str] = field(default_factory=list)
    strategy_thesis_refs: List[str] = field(default_factory=list)
    prohibited_outputs_detected: bool = False
    risk_ref: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "intent_family": self.intent_family,
            "assessed_strategy_thesis_ref": self.assessed_strategy_thesis_ref,
            "assessed_market_context_ref": self.assessed_market_context_ref,
            "overall_risk_level": self.overall_risk_level,
            "risk_posture": self.risk_posture,
            "confidence_adjustment": dict(self.confidence_adjustment),
            "key_risks": [dict(item) for item in self.key_risks],
            "thesis_fragility": dict(self.thesis_fragility),
            "conflicting_factors": [dict(item) for item in self.conflicting_factors],
            "missing_or_weak_context": list(self.missing_or_weak_context),
            "event_and_volatility_risks": list(self.event_and_volatility_risks),
            "confirmation_requirements": [dict(item) for item in self.confirmation_requirements],
            "invalidation_risks": [dict(item) for item in self.invalidation_risks],
            "risk_summary": self.risk_summary,
            "limitations": list(self.limitations),
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "market_context_refs": list(self.market_context_refs),
            "strategy_thesis_refs": list(self.strategy_thesis_refs),
            "prohibited_outputs_detected": self.prohibited_outputs_detected,
            "risk_ref": self.risk_ref or f"risk_assessment:{self.task_id}",
        }


class RiskReasoningBackend(Protocol):
    def produce(self, risk_input: RiskInput) -> RiskAssessment | Dict[str, Any]:
        ...


class RiskInputAssembler:
    @classmethod
    def assemble(cls, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> RiskInput:
        decision_context = context.decision_context_ref
        query_plan = getattr(decision_context, "query_plan", None) or context.query_plan_ref or {}
        parent_task_id = task.parent_task_id or str(query_plan.get("task_id") or "task_1")
        task_view = cls._task_view(context, parent_task_id)
        strategy_result = cls._agent_result(context, parent_task_id, "StrategyAgent")
        market_result = cls._agent_result(context, parent_task_id, "MarketContextAgent")
        raw_strategy_payload = dict(strategy_result.structured_payload) if strategy_result else {}
        raw_market_payload = dict(market_result.structured_payload) if market_result else {}
        strategy_payload = compact_agent_payload("StrategyAgent", raw_strategy_payload)
        market_payload = compact_agent_payload("MarketContextAgent", raw_market_payload)
        if raw_market_payload:
            log_projection(parent_task_id, "market_context_for_risk", raw_market_payload, market_payload)
        if raw_strategy_payload:
            log_projection(parent_task_id, "strategy_thesis_for_risk", raw_strategy_payload, strategy_payload)
        thesis_ref = str(strategy_payload.get("thesis_ref") or "")
        market_ref = str(market_payload.get("assessment_ref") or "")
        missing_context = list(task_view.get("missing_required") or task_view.get("missing_context") or [])
        if not thesis_ref:
            missing_context.append("strategy_thesis")
        if not market_ref:
            missing_context.append("market_context_assessment")
        confidence_ceiling = str(task_view.get("confidence_ceiling") or getattr(decision_context, "confidence_ceiling", "") or "high")
        strategy_confidence = strategy_payload.get("confidence") if isinstance(strategy_payload.get("confidence"), dict) else {}
        market_uncertainty = market_payload.get("uncertainty") if isinstance(market_payload.get("uncertainty"), dict) else {}
        assembled = RiskInput(
            request_id=str(getattr(decision_context, "request_id", "") or "agent_request"),
            task_id=task.task_id,
            parent_task_id=parent_task_id,
            intent_family=task.intent_family,
            symbol=str(strategy_payload.get("symbol") or market_payload.get("symbol") or cls._symbol(query_plan)),
            as_of=str(strategy_payload.get("as_of") or market_payload.get("as_of") or ""),
            temporal_scope=str(cls._child_query_plan(query_plan, parent_task_id).get("temporal_scope") or query_plan.get("temporal_scope") or ""),
            market_context_assessment_ref=market_ref,
            market_context_assessment=market_payload,
            strategy_thesis_ref=thesis_ref,
            strategy_thesis=strategy_payload,
            evidence_bundle_ref=f"evidence_bundle:{parent_task_id}",
            allowed_evidence_refs=list(task.evidence_refs or []),
            allowed_source_refs=list(task.source_refs or task.metadata.get("allowed_source_refs", []) or []),
            allowed_market_context_refs=[market_ref] if market_ref else [],
            allowed_strategy_thesis_refs=[thesis_ref] if thesis_ref else [],
            task_context_ref=f"task_context:{parent_task_id}",
            confidence_ceiling=confidence_ceiling,
            missing_context=_ordered_unique(missing_context),
            limitations_from_market_context=list(market_uncertainty.get("limitations") or []),
            limitations_from_strategy_thesis=list(strategy_payload.get("limitations") or []),
        )
        print(
            "[RiskInput] "
            f"task_id={assembled.task_id} symbol={assembled.symbol} "
            f"market_context_ref={assembled.market_context_assessment_ref} "
            f"strategy_thesis_ref={assembled.strategy_thesis_ref} "
            f"allowed_evidence_refs={assembled.allowed_evidence_refs} "
            f"confidence_ceiling={assembled.confidence_ceiling} "
            f"missing_context={assembled.missing_context} "
            f"serialized_chars={len(json.dumps(assembled.as_dict(), ensure_ascii=False, default=str))}"
        )
        return assembled

    @staticmethod
    def _agent_result(context: AgentRuntimeContext, parent_task_id: str, agent_type: str) -> AgentResultEnvelope | None:
        results = (context.metadata or {}).get("agent_results_by_task") or {}
        result = results.get(f"{parent_task_id}:{agent_type}")
        if isinstance(result, AgentResultEnvelope) and result.status in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}:
            return result
        return None

    @staticmethod
    def _task_view(context: AgentRuntimeContext, task_id: str) -> Dict[str, Any]:
        item = (context.task_context_refs or {}).get(task_id)
        return dict(item) if isinstance(item, dict) else {}

    @staticmethod
    def _child_query_plan(query_plan: Mapping[str, Any], task_id: str) -> Dict[str, Any]:
        for child in query_plan.get("child_plans", []) or []:
            if isinstance(child, dict) and str(child.get("task_id") or "") == task_id:
                return dict(child)
        return dict(query_plan)

    @staticmethod
    def _symbol(query_plan: Mapping[str, Any]) -> str:
        entities = query_plan.get("entities") if isinstance(query_plan, dict) else {}
        symbols = entities.get("symbols") if isinstance(entities, dict) else []
        return str(symbols[0]) if symbols else ""


class DeterministicRiskReasoningBackend:
    def produce(self, risk_input: RiskInput) -> RiskAssessment:
        strategy = risk_input.strategy_thesis or {}
        market = risk_input.market_context_assessment or {}
        conflicts = list(strategy.get("conflicting_factors") or []) + list(market.get("conflicting_signals") or [])
        missing = list(risk_input.missing_context or []) + list(strategy.get("missing_context") or [])
        strategy_confidence = self._strategy_confidence(strategy)
        adjusted_confidence = self._adjusted_confidence(risk_input, strategy_confidence, bool(conflicts), bool(missing))
        risk_level = self._risk_level(adjusted_confidence, bool(conflicts), bool(missing))
        posture = self._posture(risk_level, bool(conflicts), bool(missing))
        evidence_refs = list(risk_input.allowed_evidence_refs)
        market_refs = [risk_input.market_context_assessment_ref] if risk_input.market_context_assessment_ref else []
        thesis_refs = [risk_input.strategy_thesis_ref] if risk_input.strategy_thesis_ref else []
        return RiskAssessment(
            request_id=risk_input.request_id,
            task_id=risk_input.task_id,
            parent_task_id=risk_input.parent_task_id,
            symbol=risk_input.symbol,
            as_of=risk_input.as_of,
            intent_family=risk_input.intent_family,
            assessed_strategy_thesis_ref=risk_input.strategy_thesis_ref,
            assessed_market_context_ref=risk_input.market_context_assessment_ref,
            overall_risk_level=risk_level,
            risk_posture=posture,
            confidence_adjustment={
                "original_strategy_confidence": strategy_confidence,
                "adjusted_confidence": adjusted_confidence,
                "adjustment_reason": "Adjusted for conflicts, missing context, and upstream confidence ceiling.",
            },
            key_risks=self._key_risks(risk_input, risk_level, conflicts),
            thesis_fragility={
                "weak_points": missing or ["Thesis remains conditional on confirmation context."],
                "assumptions_under_stress": list(strategy.get("assumptions") or []),
                "conditions_that_weaken_thesis": [item.get("condition") for item in strategy.get("invalidation_conditions", []) if isinstance(item, dict)],
            },
            conflicting_factors=self._conflicts(conflicts, evidence_refs, market_refs, thesis_refs),
            missing_or_weak_context=_ordered_unique(missing),
            event_and_volatility_risks=self._event_risks(risk_input, market),
            confirmation_requirements=self._requirements(strategy, evidence_refs, market_refs, thesis_refs),
            invalidation_risks=self._invalidation_risks(strategy, evidence_refs, market_refs, thesis_refs),
            risk_summary=f"Risk posture is {posture}; confidence is capped at {adjusted_confidence}.",
            limitations=_ordered_unique(list(risk_input.limitations_from_market_context) + list(risk_input.limitations_from_strategy_thesis)),
            evidence_refs=evidence_refs,
            source_refs=list(risk_input.allowed_source_refs),
            market_context_refs=market_refs,
            strategy_thesis_refs=thesis_refs,
            prohibited_outputs_detected=False,
            risk_ref=f"risk_assessment:{risk_input.task_id}",
        )

    @staticmethod
    def _strategy_confidence(strategy: Mapping[str, Any]) -> float:
        confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), dict) else {}
        return round(float(confidence.get("value") or 0.0), 2)

    @staticmethod
    def _adjusted_confidence(risk_input: RiskInput, strategy_confidence: float, has_conflicts: bool, has_missing: bool) -> float:
        ceiling = CONFIDENCE_CEILING.get(risk_input.confidence_ceiling, 0.65)
        value = min(strategy_confidence, ceiling)
        if has_conflicts:
            value = min(value, 0.55)
        if has_missing:
            value = min(value, 0.45)
        return round(max(0.0, min(value, 1.0)), 2)

    @staticmethod
    def _risk_level(adjusted_confidence: float, has_conflicts: bool, has_missing: bool) -> str:
        if has_missing:
            return "high"
        if has_conflicts:
            return "elevated"
        if adjusted_confidence >= 0.7:
            return "moderate"
        if adjusted_confidence >= 0.5:
            return "elevated"
        return "unclear"

    @staticmethod
    def _posture(risk_level: str, has_conflicts: bool, has_missing: bool) -> str:
        if has_missing:
            return "insufficient_context"
        if has_conflicts:
            return "conflicting_context"
        if risk_level in {"elevated", "high"}:
            return "caution_required"
        if risk_level == "moderate":
            return "acceptable_with_conditions"
        return "unclear"

    @staticmethod
    def _key_risks(risk_input: RiskInput, risk_level: str, conflicts: List[Any]) -> List[Dict[str, Any]]:
        risks = [{
            "risk_type": "thesis_uncertainty",
            "description": "Strategy thesis remains conditional and should not be treated as an execution signal.",
            "severity": risk_level if risk_level in SEVERITY else "unclear",
            "likelihood": "medium",
            "evidence_refs": list(risk_input.allowed_evidence_refs),
            "market_context_refs": [risk_input.market_context_assessment_ref] if risk_input.market_context_assessment_ref else [],
            "strategy_thesis_refs": [risk_input.strategy_thesis_ref] if risk_input.strategy_thesis_ref else [],
        }]
        if conflicts:
            risks.append({
                "risk_type": "conflicting_context",
                "description": "Supplied thesis or market context contains conflicting factors.",
                "severity": "elevated",
                "likelihood": "medium",
                "evidence_refs": list(risk_input.allowed_evidence_refs),
                "market_context_refs": [risk_input.market_context_assessment_ref] if risk_input.market_context_assessment_ref else [],
                "strategy_thesis_refs": [risk_input.strategy_thesis_ref] if risk_input.strategy_thesis_ref else [],
            })
        return risks

    @staticmethod
    def _conflicts(conflicts: List[Any], evidence_refs: List[str], market_refs: List[str], thesis_refs: List[str]) -> List[Dict[str, Any]]:
        output = []
        for item in conflicts[:4]:
            if isinstance(item, dict):
                output.append({
                    "factor": str(item.get("factor") or item.get("signal_a") or "context factor"),
                    "conflict_with": str(item.get("conflict_with") or item.get("signal_b") or "opposing context"),
                    "explanation": str(item.get("explanation") or "Conflict exists in supplied context."),
                    "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(evidence_refs)] or list(evidence_refs),
                    "context_refs": list(market_refs + thesis_refs),
                })
        return output

    @staticmethod
    def _event_risks(risk_input: RiskInput, market: Mapping[str, Any]) -> List[str]:
        risks = []
        macro_context = market.get("macro_context") if isinstance(market.get("macro_context"), dict) else {}
        if macro_context.get("active_events"):
            risks.append("Event context is active and can make thesis outcomes unstable.")
        if risk_input.intent_family == "macro_market_impact":
            risks.append("Macro-impact thesis is sensitive to release interpretation and market repricing.")
        return risks

    @staticmethod
    def _requirements(strategy: Mapping[str, Any], evidence_refs: List[str], market_refs: List[str], thesis_refs: List[str]) -> List[Dict[str, Any]]:
        output = []
        for item in list(strategy.get("activation_conditions") or [])[:3]:
            if isinstance(item, dict):
                output.append({
                    "requirement": str(item.get("condition") or "confirmation required"),
                    "reason": str(item.get("reason") or "Needed before treating thesis as stronger."),
                    "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(evidence_refs)] or list(evidence_refs),
                    "context_refs": list(market_refs + thesis_refs),
                })
        return output

    @staticmethod
    def _invalidation_risks(strategy: Mapping[str, Any], evidence_refs: List[str], market_refs: List[str], thesis_refs: List[str]) -> List[Dict[str, Any]]:
        output = []
        for item in list(strategy.get("invalidation_conditions") or [])[:3]:
            if isinstance(item, dict):
                output.append({
                    "condition": str(item.get("condition") or "invalidation condition"),
                    "reason": str(item.get("reason") or "This weakens the thesis."),
                    "severity": "elevated",
                    "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(evidence_refs)] or list(evidence_refs),
                    "context_refs": list(market_refs + thesis_refs),
                })
        return output


class RiskAssessmentValidator:
    @classmethod
    def validate(cls, assessment: RiskAssessment | Dict[str, Any], risk_input: RiskInput) -> List[str]:
        data = assessment.as_dict() if isinstance(assessment, RiskAssessment) else dict(assessment or {})
        reasons: List[str] = []
        if data.get("task_id") != risk_input.task_id:
            reasons.append("task_id_mismatch")
        if data.get("parent_task_id") != risk_input.parent_task_id:
            reasons.append("parent_task_id_mismatch")
        if data.get("overall_risk_level") not in RISK_LEVELS:
            reasons.append("invalid_risk_level")
        if data.get("risk_posture") not in RISK_POSTURES:
            reasons.append("invalid_risk_posture")
        adjustment = data.get("confidence_adjustment") if isinstance(data.get("confidence_adjustment"), dict) else {}
        adjusted = float(adjustment.get("adjusted_confidence") or 0.0)
        original = float(adjustment.get("original_strategy_confidence") or 0.0)
        ceiling = CONFIDENCE_CEILING.get(risk_input.confidence_ceiling, 0.65)
        strategy_confidence = cls._strategy_confidence(risk_input.strategy_thesis)
        if not 0.0 <= adjusted <= 1.0 or adjusted > ceiling:
            reasons.append("confidence_ceiling_exceeded")
        if adjusted > strategy_confidence or adjusted > original:
            reasons.append("adjusted_confidence_exceeds_strategy")
        if not set(data.get("evidence_refs") or []) <= set(risk_input.allowed_evidence_refs or []):
            reasons.append("evidence_ref_out_of_scope")
        if not set(data.get("source_refs") or []) <= set(risk_input.allowed_source_refs or []):
            reasons.append("source_ref_out_of_scope")
        if not set(data.get("market_context_refs") or []) <= set(risk_input.allowed_market_context_refs or []):
            reasons.append("market_context_ref_out_of_scope")
        if not set(data.get("strategy_thesis_refs") or []) <= set(risk_input.allowed_strategy_thesis_refs or []):
            reasons.append("strategy_thesis_ref_out_of_scope")
        if risk_input.market_context_assessment_ref and risk_input.market_context_assessment_ref not in set(data.get("market_context_refs") or []):
            reasons.append("missing_market_context_ref")
        if risk_input.strategy_thesis_ref and risk_input.strategy_thesis_ref not in set(data.get("strategy_thesis_refs") or []):
            reasons.append("missing_strategy_thesis_ref")
        if not risk_input.strategy_thesis_ref:
            reasons.append("missing_strategy_thesis")
        if data.get("prohibited_outputs_detected") is True:
            reasons.append("prohibited_output_detected")
        if cls._has_forbidden_field(data):
            reasons.append("forbidden_trading_field")
        if cls._has_forbidden_text(data):
            reasons.append("forbidden_trading_instruction")
        return _ordered_unique(reasons)

    @staticmethod
    def _strategy_confidence(strategy: Mapping[str, Any]) -> float:
        confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), dict) else {}
        return float(confidence.get("value") or 0.0)

    @classmethod
    def _has_forbidden_field(cls, value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in FORBIDDEN_FIELDS:
                    return True
                if cls._has_forbidden_field(item):
                    return True
        elif isinstance(value, list):
            return any(cls._has_forbidden_field(item) for item in value)
        return False

    @classmethod
    def _has_forbidden_text(cls, value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(cls._has_forbidden_text(item) for item in value.values())
        if isinstance(value, list):
            return any(cls._has_forbidden_text(item) for item in value)
        if isinstance(value, str):
            return any(pattern.search(value) for pattern in FORBIDDEN_TEXT_PATTERNS)
        return False


class RiskAgentRuntime:
    agent_type = "RiskAgent"

    def __init__(self, backend: RiskReasoningBackend | None = None):
        self.backend = backend or DeterministicRiskReasoningBackend()

    def execute(self, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> AgentResultEnvelope:
        print(f"[RiskAgent] task_id={task.task_id} status=start")
        started = time.perf_counter()
        risk_input = RiskInputAssembler.assemble(task, context)
        produced = self.backend.produce(risk_input)
        raw_reasons = RiskAssessmentValidator.validate(produced, risk_input)
        assessment = self._coerce(produced)
        reasons = _ordered_unique(raw_reasons + RiskAssessmentValidator.validate(assessment, risk_input))
        if reasons:
            print(f"[RiskValidation] task_id={task.task_id} status=FAIL reason_codes={reasons}")
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=self.agent_type,
                status=AgentStatus.INVALID_RESULT,
                result_type="risk_assessment",
                structured_payload=assessment.as_dict(),
                summary="Invalid risk assessment.",
                evidence_refs=[],
                source_refs=[],
                confidence=0.0,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                failure_code="AGENT_RESULT_INVALID",
                failure_reason=",".join(reasons),
            )
        payload = assessment.as_dict()
        adjusted = float((payload.get("confidence_adjustment") or {}).get("adjusted_confidence") or 0.0)
        print(f"[RiskValidation] task_id={task.task_id} status=PASS reason_codes=[]")
        print(
            "[RiskAssessment] "
            f"task_id={task.task_id} overall_risk_level={payload.get('overall_risk_level')} "
            f"risk_posture={payload.get('risk_posture')} "
            f"adjusted_confidence={adjusted} "
            f"key_risks={len(payload.get('key_risks') or [])} "
            f"conflicting_factors={len(payload.get('conflicting_factors') or [])} "
            f"confirmation_requirements={len(payload.get('confirmation_requirements') or [])} "
            f"invalidation_risks={len(payload.get('invalidation_risks') or [])} "
            f"payload_chars={len(json.dumps(payload, ensure_ascii=False, default=str))}"
        )
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=self.agent_type,
            status=AgentStatus.SUCCESS,
            result_type="risk_assessment",
            structured_payload=payload,
            summary=assessment.risk_summary,
            evidence_refs=list(assessment.evidence_refs),
            source_refs=list(assessment.source_refs),
            confidence=adjusted,
            limitations=list(assessment.limitations),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            metadata={"risk_assessment_is_not_evidence": True},
        )

    @staticmethod
    def _coerce(produced: RiskAssessment | Dict[str, Any]) -> RiskAssessment:
        if isinstance(produced, RiskAssessment):
            return produced
        data = dict(produced or {})
        return RiskAssessment(
            request_id=str(data.get("request_id") or ""),
            task_id=str(data.get("task_id") or ""),
            parent_task_id=str(data.get("parent_task_id") or ""),
            symbol=str(data.get("symbol") or ""),
            as_of=str(data.get("as_of") or ""),
            intent_family=str(data.get("intent_family") or ""),
            assessed_strategy_thesis_ref=str(data.get("assessed_strategy_thesis_ref") or ""),
            assessed_market_context_ref=str(data.get("assessed_market_context_ref") or ""),
            overall_risk_level=str(data.get("overall_risk_level") or ""),
            risk_posture=str(data.get("risk_posture") or ""),
            confidence_adjustment=dict(data.get("confidence_adjustment") or {}),
            key_risks=list(data.get("key_risks") or []),
            thesis_fragility=dict(data.get("thesis_fragility") or {}),
            conflicting_factors=list(data.get("conflicting_factors") or []),
            missing_or_weak_context=list(data.get("missing_or_weak_context") or []),
            event_and_volatility_risks=list(data.get("event_and_volatility_risks") or []),
            confirmation_requirements=list(data.get("confirmation_requirements") or []),
            invalidation_risks=list(data.get("invalidation_risks") or []),
            risk_summary=str(data.get("risk_summary") or ""),
            limitations=list(data.get("limitations") or []),
            evidence_refs=list(data.get("evidence_refs") or []),
            source_refs=list(data.get("source_refs") or []),
            market_context_refs=list(data.get("market_context_refs") or []),
            strategy_thesis_refs=list(data.get("strategy_thesis_refs") or []),
            prohibited_outputs_detected=bool(data.get("prohibited_outputs_detected") or False),
            risk_ref=str(data.get("risk_ref") or ""),
        )


def _ordered_unique(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
