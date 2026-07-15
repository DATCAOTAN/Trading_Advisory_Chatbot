from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Protocol, Set

from src.services.agents.projection import compact_agent_payload, log_projection
from src.services.agents.risk import CONFIDENCE_CEILING
from src.services.agents.runtime import AgentResultEnvelope, AgentRuntimeContext, AgentStatus, AgentTaskEnvelope


CONSISTENCY_STATUSES = {
    "aligned",
    "partially_aligned",
    "risk_weakened",
    "contradicted",
    "insufficient_context",
    "unclear",
}
FINAL_PRESENTATION_MODES = {
    "standard_conditional",
    "cautious_conditional",
    "mixed_or_uncertain",
    "risk_first",
    "no_clear_thesis",
    "insufficient_context",
}
THESIS_STRENGTH_AFTER_RISK = {"strong", "adequate", "weak", "very_weak", "unclear"}
CONTRADICTION_SEVERITY = {"low", "moderate", "elevated", "high", "unclear"}

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
class ConsistencyInput:
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
    risk_assessment_ref: str = ""
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    evidence_bundle_ref: str = ""
    topic_binding_refs: List[str] = field(default_factory=list)
    allowed_evidence_refs: List[str] = field(default_factory=list)
    allowed_source_refs: List[str] = field(default_factory=list)
    allowed_market_context_refs: List[str] = field(default_factory=list)
    allowed_strategy_thesis_refs: List[str] = field(default_factory=list)
    allowed_risk_assessment_refs: List[str] = field(default_factory=list)
    decision_context_ref: str = "decision_context"
    task_context_ref: str = ""
    confidence_ceiling: str = "high"
    missing_context: List[str] = field(default_factory=list)
    limitations_from_market_context: List[str] = field(default_factory=list)
    limitations_from_strategy_thesis: List[str] = field(default_factory=list)
    limitations_from_risk_assessment: List[str] = field(default_factory=list)

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
            "risk_assessment_ref": self.risk_assessment_ref,
            "risk_assessment": dict(self.risk_assessment),
            "evidence_bundle_ref": self.evidence_bundle_ref,
            "topic_binding_refs": list(self.topic_binding_refs),
            "allowed_evidence_refs": list(self.allowed_evidence_refs),
            "allowed_source_refs": list(self.allowed_source_refs),
            "allowed_market_context_refs": list(self.allowed_market_context_refs),
            "allowed_strategy_thesis_refs": list(self.allowed_strategy_thesis_refs),
            "allowed_risk_assessment_refs": list(self.allowed_risk_assessment_refs),
            "decision_context_ref": self.decision_context_ref,
            "task_context_ref": self.task_context_ref,
            "confidence_ceiling": self.confidence_ceiling,
            "missing_context": list(self.missing_context),
            "limitations_from_market_context": list(self.limitations_from_market_context),
            "limitations_from_strategy_thesis": list(self.limitations_from_strategy_thesis),
            "limitations_from_risk_assessment": list(self.limitations_from_risk_assessment),
        }


@dataclass
class ConsistencyAssessment:
    request_id: str
    task_id: str
    parent_task_id: str
    symbol: str
    as_of: str
    intent_family: str
    assessed_market_context_ref: str
    assessed_strategy_thesis_ref: str
    assessed_risk_assessment_ref: str
    consistency_status: str
    final_presentation_mode: str
    thesis_strength_after_risk: str
    confidence_reconciliation: Dict[str, Any] = field(default_factory=dict)
    agreement_points: List[Dict[str, Any]] = field(default_factory=list)
    contradiction_points: List[Dict[str, Any]] = field(default_factory=list)
    required_final_answer_emphasis: List[str] = field(default_factory=list)
    prohibited_final_answer_patterns: List[str] = field(default_factory=list)
    final_synthesis_guidance: str = ""
    limitations: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    market_context_refs: List[str] = field(default_factory=list)
    strategy_thesis_refs: List[str] = field(default_factory=list)
    risk_assessment_refs: List[str] = field(default_factory=list)
    prohibited_outputs_detected: bool = False
    consistency_ref: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "intent_family": self.intent_family,
            "consistency_ref": self.consistency_ref or f"consistency_assessment:{self.task_id}",
            "assessed_market_context_ref": self.assessed_market_context_ref,
            "assessed_strategy_thesis_ref": self.assessed_strategy_thesis_ref,
            "assessed_risk_assessment_ref": self.assessed_risk_assessment_ref,
            "consistency_status": self.consistency_status,
            "final_presentation_mode": self.final_presentation_mode,
            "thesis_strength_after_risk": self.thesis_strength_after_risk,
            "confidence_reconciliation": dict(self.confidence_reconciliation),
            "agreement_points": [dict(item) for item in self.agreement_points],
            "contradiction_points": [dict(item) for item in self.contradiction_points],
            "required_final_answer_emphasis": list(self.required_final_answer_emphasis),
            "prohibited_final_answer_patterns": list(self.prohibited_final_answer_patterns),
            "final_synthesis_guidance": self.final_synthesis_guidance,
            "limitations": list(self.limitations),
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "market_context_refs": list(self.market_context_refs),
            "strategy_thesis_refs": list(self.strategy_thesis_refs),
            "risk_assessment_refs": list(self.risk_assessment_refs),
            "prohibited_outputs_detected": self.prohibited_outputs_detected,
        }


class ConsistencyReasoningBackend(Protocol):
    def produce(self, consistency_input: ConsistencyInput) -> ConsistencyAssessment | Dict[str, Any]:
        ...


class ConsistencyInputAssembler:
    @classmethod
    def assemble(cls, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> ConsistencyInput:
        decision_context = context.decision_context_ref
        query_plan = getattr(decision_context, "query_plan", None) or context.query_plan_ref or {}
        parent_task_id = task.parent_task_id or str(query_plan.get("task_id") or "task_1")
        task_view = cls._task_view(context, parent_task_id)
        market_result = cls._agent_result(context, parent_task_id, "MarketContextAgent")
        strategy_result = cls._agent_result(context, parent_task_id, "StrategyAgent")
        risk_result = cls._agent_result(context, parent_task_id, "RiskAgent")
        raw_market_payload = dict(market_result.structured_payload) if market_result else {}
        raw_strategy_payload = dict(strategy_result.structured_payload) if strategy_result else {}
        raw_risk_payload = dict(risk_result.structured_payload) if risk_result else {}
        market_payload = compact_agent_payload("MarketContextAgent", raw_market_payload)
        strategy_payload = compact_agent_payload("StrategyAgent", raw_strategy_payload)
        risk_payload = compact_agent_payload("RiskAgent", raw_risk_payload)
        if raw_market_payload:
            log_projection(parent_task_id, "market_context_for_consistency", raw_market_payload, market_payload)
        if raw_strategy_payload:
            log_projection(parent_task_id, "strategy_thesis_for_consistency", raw_strategy_payload, strategy_payload)
        if raw_risk_payload:
            log_projection(parent_task_id, "risk_assessment_for_consistency", raw_risk_payload, risk_payload)
        market_ref = str(market_payload.get("assessment_ref") or "")
        thesis_ref = str(strategy_payload.get("thesis_ref") or "")
        risk_ref = str(risk_payload.get("risk_ref") or "")
        missing_context = list(task_view.get("missing_required") or task_view.get("missing_context") or [])
        if not thesis_ref:
            missing_context.append("strategy_thesis")
        if not risk_ref:
            missing_context.append("risk_assessment")
        if not market_ref:
            missing_context.append("market_context_assessment")
        risk_adjustment = risk_payload.get("confidence_adjustment") if isinstance(risk_payload.get("confidence_adjustment"), dict) else {}
        market_uncertainty = market_payload.get("uncertainty") if isinstance(market_payload.get("uncertainty"), dict) else {}
        confidence_ceiling = str(task_view.get("confidence_ceiling") or getattr(decision_context, "confidence_ceiling", "") or "high")
        assembled = ConsistencyInput(
            request_id=str(getattr(decision_context, "request_id", "") or "agent_request"),
            task_id=task.task_id,
            parent_task_id=parent_task_id,
            intent_family=task.intent_family,
            symbol=str(strategy_payload.get("symbol") or risk_payload.get("symbol") or market_payload.get("symbol") or cls._symbol(query_plan)),
            as_of=str(strategy_payload.get("as_of") or risk_payload.get("as_of") or market_payload.get("as_of") or ""),
            temporal_scope=str(cls._child_query_plan(query_plan, parent_task_id).get("temporal_scope") or query_plan.get("temporal_scope") or ""),
            market_context_assessment_ref=market_ref,
            market_context_assessment=market_payload,
            strategy_thesis_ref=thesis_ref,
            strategy_thesis=strategy_payload,
            risk_assessment_ref=risk_ref,
            risk_assessment=risk_payload,
            evidence_bundle_ref=f"evidence_bundle:{parent_task_id}",
            allowed_evidence_refs=list(task.evidence_refs or []),
            allowed_source_refs=list(task.source_refs or task.metadata.get("allowed_source_refs", []) or []),
            allowed_market_context_refs=[market_ref] if market_ref else [],
            allowed_strategy_thesis_refs=[thesis_ref] if thesis_ref else [],
            allowed_risk_assessment_refs=[risk_ref] if risk_ref else [],
            task_context_ref=f"task_context:{parent_task_id}",
            confidence_ceiling=confidence_ceiling,
            missing_context=_ordered_unique(missing_context),
            limitations_from_market_context=list(market_uncertainty.get("limitations") or []),
            limitations_from_strategy_thesis=list(strategy_payload.get("limitations") or []),
            limitations_from_risk_assessment=list(risk_payload.get("limitations") or []),
        )
        print(
            "[ConsistencyInput] "
            f"task_id={assembled.task_id} symbol={assembled.symbol} "
            f"market_context_ref={assembled.market_context_assessment_ref} "
            f"strategy_thesis_ref={assembled.strategy_thesis_ref} "
            f"risk_assessment_ref={assembled.risk_assessment_ref} "
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


class DeterministicConsistencyReasoningBackend:
    def produce(self, consistency_input: ConsistencyInput) -> ConsistencyAssessment:
        strategy = consistency_input.strategy_thesis or {}
        risk = consistency_input.risk_assessment or {}
        strategy_confidence = self._strategy_confidence(strategy)
        risk_confidence = self._risk_adjusted_confidence(risk)
        final_confidence = self._final_confidence(consistency_input, strategy_confidence, risk_confidence)
        risk_posture = str(risk.get("risk_posture") or "unclear")
        risk_level = str(risk.get("overall_risk_level") or "unclear")
        status = self._status(strategy, risk_posture, risk_level, consistency_input.missing_context)
        mode = self._presentation_mode(status, risk_posture, consistency_input.missing_context)
        strength = self._strength(status, final_confidence)
        evidence_refs = list(consistency_input.allowed_evidence_refs)
        market_refs = [consistency_input.market_context_assessment_ref] if consistency_input.market_context_assessment_ref else []
        thesis_refs = [consistency_input.strategy_thesis_ref] if consistency_input.strategy_thesis_ref else []
        risk_refs = [consistency_input.risk_assessment_ref] if consistency_input.risk_assessment_ref else []
        contradictions = self._contradictions(strategy, risk, evidence_refs, thesis_refs, risk_refs)
        emphasis = self._emphasis(mode, consistency_input.missing_context, contradictions)
        return ConsistencyAssessment(
            request_id=consistency_input.request_id,
            task_id=consistency_input.task_id,
            parent_task_id=consistency_input.parent_task_id,
            symbol=consistency_input.symbol,
            as_of=consistency_input.as_of,
            intent_family=consistency_input.intent_family,
            assessed_market_context_ref=consistency_input.market_context_assessment_ref,
            assessed_strategy_thesis_ref=consistency_input.strategy_thesis_ref,
            assessed_risk_assessment_ref=consistency_input.risk_assessment_ref,
            consistency_status=status,
            final_presentation_mode=mode,
            thesis_strength_after_risk=strength,
            confidence_reconciliation={
                "strategy_confidence": strategy_confidence,
                "risk_adjusted_confidence": risk_confidence,
                "final_confidence": final_confidence,
                "reason": "Final confidence is capped by strategy confidence, risk-adjusted confidence, and task ceiling.",
            },
            agreement_points=self._agreements(strategy, risk, evidence_refs, market_refs, thesis_refs, risk_refs),
            contradiction_points=contradictions,
            required_final_answer_emphasis=emphasis,
            prohibited_final_answer_patterns=[
                "strong_directional_claim",
                "guaranteed_prediction",
                "trading_instruction",
                "entry_sl_tp",
                "position_sizing",
            ],
            final_synthesis_guidance=self._guidance(mode, status, strength),
            limitations=_ordered_unique(
                list(consistency_input.limitations_from_market_context)
                + list(consistency_input.limitations_from_strategy_thesis)
                + list(consistency_input.limitations_from_risk_assessment)
            ),
            evidence_refs=evidence_refs,
            source_refs=list(consistency_input.allowed_source_refs),
            market_context_refs=market_refs,
            strategy_thesis_refs=thesis_refs,
            risk_assessment_refs=risk_refs,
            prohibited_outputs_detected=False,
            consistency_ref=f"consistency_assessment:{consistency_input.task_id}",
        )

    @staticmethod
    def _strategy_confidence(strategy: Mapping[str, Any]) -> float:
        confidence = strategy.get("confidence") if isinstance(strategy.get("confidence"), dict) else {}
        return round(float(confidence.get("value") or 0.0), 2)

    @staticmethod
    def _risk_adjusted_confidence(risk: Mapping[str, Any]) -> float:
        adjustment = risk.get("confidence_adjustment") if isinstance(risk.get("confidence_adjustment"), dict) else {}
        return round(float(adjustment.get("adjusted_confidence") or 0.0), 2)

    @staticmethod
    def _final_confidence(consistency_input: ConsistencyInput, strategy_confidence: float, risk_confidence: float) -> float:
        ceiling = CONFIDENCE_CEILING.get(consistency_input.confidence_ceiling, 0.65)
        value = min(strategy_confidence, risk_confidence, ceiling)
        if consistency_input.missing_context:
            value = min(value, 0.4)
        return round(max(0.0, min(value, 1.0)), 2)

    @staticmethod
    def _status(strategy: Mapping[str, Any], risk_posture: str, risk_level: str, missing: List[str]) -> str:
        if missing:
            return "insufficient_context"
        if risk_posture in {"insufficient_context"}:
            return "insufficient_context"
        if risk_posture in {"conflicting_context", "thesis_fragile"}:
            return "risk_weakened"
        if risk_level in {"elevated", "high"}:
            return "risk_weakened"
        if str(strategy.get("thesis_direction") or "") in {"mixed", "no_clear_bias"}:
            return "partially_aligned"
        return "aligned"

    @staticmethod
    def _presentation_mode(status: str, risk_posture: str, missing: List[str]) -> str:
        if missing or status == "insufficient_context":
            return "insufficient_context"
        if risk_posture == "conflicting_context":
            return "mixed_or_uncertain"
        if status == "risk_weakened":
            return "cautious_conditional"
        if status == "contradicted":
            return "risk_first"
        if status == "unclear":
            return "no_clear_thesis"
        return "standard_conditional"

    @staticmethod
    def _strength(status: str, final_confidence: float) -> str:
        if status in {"insufficient_context", "unclear"}:
            return "unclear"
        if final_confidence >= 0.7 and status == "aligned":
            return "strong"
        if final_confidence >= 0.55 and status in {"aligned", "partially_aligned"}:
            return "adequate"
        if final_confidence >= 0.4:
            return "weak"
        return "very_weak"

    @staticmethod
    def _agreements(
        strategy: Mapping[str, Any],
        risk: Mapping[str, Any],
        evidence_refs: List[str],
        market_refs: List[str],
        thesis_refs: List[str],
        risk_refs: List[str],
    ) -> List[Dict[str, Any]]:
        return [{
            "point": "Both strategy and risk layers keep the thesis conditional.",
            "evidence_refs": list(evidence_refs),
            "strategy_thesis_refs": list(thesis_refs),
            "risk_assessment_refs": list(risk_refs),
            "market_context_refs": list(market_refs),
        }]

    @staticmethod
    def _contradictions(
        strategy: Mapping[str, Any],
        risk: Mapping[str, Any],
        evidence_refs: List[str],
        thesis_refs: List[str],
        risk_refs: List[str],
    ) -> List[Dict[str, Any]]:
        points = []
        conflicts = list(strategy.get("conflicting_factors") or []) + list(risk.get("conflicting_factors") or [])
        for item in conflicts[:4]:
            if isinstance(item, dict):
                points.append({
                    "strategy_claim": str(item.get("factor") or item.get("signal_a") or "strategy context"),
                    "risk_objection": str(item.get("conflict_with") or item.get("signal_b") or "risk context"),
                    "severity": "elevated",
                    "explanation": str(item.get("explanation") or "Risk layer weakens or qualifies the thesis."),
                    "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(evidence_refs)] or list(evidence_refs),
                    "strategy_thesis_refs": list(thesis_refs),
                    "risk_assessment_refs": list(risk_refs),
                })
        return points

    @staticmethod
    def _emphasis(mode: str, missing: List[str], contradictions: List[Dict[str, Any]]) -> List[str]:
        emphasis = ["cautious_language", "confirmation_conditions", "invalidation_risks"]
        if mode in {"mixed_or_uncertain", "risk_first"} or contradictions:
            emphasis.extend(["uncertainty", "conflicting_context"])
        if missing:
            emphasis.append("missing_context")
        return _ordered_unique(emphasis)

    @staticmethod
    def _guidance(mode: str, status: str, strength: str) -> str:
        return (
            f"Present the thesis with {mode} framing because consistency_status={status} "
            f"and thesis_strength_after_risk={strength}. Keep claims conditional and grounded in existing evidence."
        )


class ConsistencyAssessmentValidator:
    @classmethod
    def validate(cls, assessment: ConsistencyAssessment | Dict[str, Any], consistency_input: ConsistencyInput) -> List[str]:
        data = assessment.as_dict() if isinstance(assessment, ConsistencyAssessment) else dict(assessment or {})
        reasons: List[str] = []
        if data.get("task_id") != consistency_input.task_id:
            reasons.append("task_id_mismatch")
        if data.get("parent_task_id") != consistency_input.parent_task_id:
            reasons.append("parent_task_id_mismatch")
        if data.get("consistency_status") not in CONSISTENCY_STATUSES:
            reasons.append("invalid_consistency_status")
        if data.get("final_presentation_mode") not in FINAL_PRESENTATION_MODES:
            reasons.append("invalid_final_presentation_mode")
        if data.get("thesis_strength_after_risk") not in THESIS_STRENGTH_AFTER_RISK:
            reasons.append("invalid_thesis_strength_after_risk")
        confidence = data.get("confidence_reconciliation") if isinstance(data.get("confidence_reconciliation"), dict) else {}
        final_confidence = float(confidence.get("final_confidence") or 0.0)
        strategy_confidence = float(confidence.get("strategy_confidence") or 0.0)
        risk_confidence = float(confidence.get("risk_adjusted_confidence") or 0.0)
        ceiling = CONFIDENCE_CEILING.get(consistency_input.confidence_ceiling, 0.65)
        if not 0.0 <= final_confidence <= 1.0 or final_confidence > ceiling:
            reasons.append("confidence_ceiling_exceeded")
        if final_confidence > strategy_confidence:
            reasons.append("final_confidence_exceeds_strategy")
        if final_confidence > risk_confidence:
            reasons.append("final_confidence_exceeds_risk")
        if not set(data.get("evidence_refs") or []) <= set(consistency_input.allowed_evidence_refs or []):
            reasons.append("evidence_ref_out_of_scope")
        if not set(data.get("source_refs") or []) <= set(consistency_input.allowed_source_refs or []):
            reasons.append("source_ref_out_of_scope")
        if not set(data.get("market_context_refs") or []) <= set(consistency_input.allowed_market_context_refs or []):
            reasons.append("market_context_ref_out_of_scope")
        if not set(data.get("strategy_thesis_refs") or []) <= set(consistency_input.allowed_strategy_thesis_refs or []):
            reasons.append("strategy_thesis_ref_out_of_scope")
        if not set(data.get("risk_assessment_refs") or []) <= set(consistency_input.allowed_risk_assessment_refs or []):
            reasons.append("risk_assessment_ref_out_of_scope")
        if consistency_input.market_context_assessment_ref and consistency_input.market_context_assessment_ref not in set(data.get("market_context_refs") or []):
            reasons.append("missing_market_context_ref")
        if consistency_input.strategy_thesis_ref and consistency_input.strategy_thesis_ref not in set(data.get("strategy_thesis_refs") or []):
            reasons.append("missing_strategy_thesis_ref")
        if consistency_input.risk_assessment_ref and consistency_input.risk_assessment_ref not in set(data.get("risk_assessment_refs") or []):
            reasons.append("missing_risk_assessment_ref")
        if not consistency_input.strategy_thesis_ref:
            reasons.append("missing_strategy_thesis")
        if not consistency_input.risk_assessment_ref:
            reasons.append("missing_risk_assessment")
        if data.get("prohibited_outputs_detected") is True:
            reasons.append("prohibited_output_detected")
        if cls._has_forbidden_field(data):
            reasons.append("forbidden_trading_field")
        if cls._has_forbidden_text(data):
            reasons.append("forbidden_trading_instruction")
        return _ordered_unique(reasons)

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


class StrategyRiskConsistencyAgentRuntime:
    agent_type = "StrategyRiskConsistencyAgent"

    def __init__(self, backend: ConsistencyReasoningBackend | None = None):
        self.backend = backend or DeterministicConsistencyReasoningBackend()

    def execute(self, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> AgentResultEnvelope:
        print(f"[StrategyRiskConsistencyAgent] task_id={task.task_id} status=start")
        started = time.perf_counter()
        consistency_input = ConsistencyInputAssembler.assemble(task, context)
        produced = self.backend.produce(consistency_input)
        raw_reasons = ConsistencyAssessmentValidator.validate(produced, consistency_input)
        assessment = self._coerce(produced)
        reasons = _ordered_unique(raw_reasons + ConsistencyAssessmentValidator.validate(assessment, consistency_input))
        if reasons:
            print(f"[ConsistencyValidation] task_id={task.task_id} status=FAIL reason_codes={reasons}")
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=self.agent_type,
                status=AgentStatus.INVALID_RESULT,
                result_type="consistency_assessment",
                structured_payload=assessment.as_dict(),
                summary="Invalid strategy-risk consistency assessment.",
                evidence_refs=[],
                source_refs=[],
                confidence=0.0,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                failure_code="AGENT_RESULT_INVALID",
                failure_reason=",".join(reasons),
            )
        payload = assessment.as_dict()
        final_confidence = float((payload.get("confidence_reconciliation") or {}).get("final_confidence") or 0.0)
        print(f"[ConsistencyValidation] task_id={task.task_id} status=PASS reason_codes=[]")
        print(
            "[ConsistencyAssessment] "
            f"task_id={task.task_id} consistency_status={payload.get('consistency_status')} "
            f"final_presentation_mode={payload.get('final_presentation_mode')} "
            f"thesis_strength_after_risk={payload.get('thesis_strength_after_risk')} "
            f"final_confidence={final_confidence} "
            f"agreement_points={len(payload.get('agreement_points') or [])} "
            f"contradiction_points={len(payload.get('contradiction_points') or [])} "
            f"payload_chars={len(json.dumps(payload, ensure_ascii=False, default=str))}"
        )
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=self.agent_type,
            status=AgentStatus.SUCCESS,
            result_type="consistency_assessment",
            structured_payload=payload,
            summary=assessment.final_synthesis_guidance,
            evidence_refs=list(assessment.evidence_refs),
            source_refs=list(assessment.source_refs),
            confidence=final_confidence,
            limitations=list(assessment.limitations),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            metadata={"consistency_assessment_is_not_evidence": True},
        )

    @staticmethod
    def _coerce(produced: ConsistencyAssessment | Dict[str, Any]) -> ConsistencyAssessment:
        if isinstance(produced, ConsistencyAssessment):
            return produced
        data = dict(produced or {})
        return ConsistencyAssessment(
            request_id=str(data.get("request_id") or ""),
            task_id=str(data.get("task_id") or ""),
            parent_task_id=str(data.get("parent_task_id") or ""),
            symbol=str(data.get("symbol") or ""),
            as_of=str(data.get("as_of") or ""),
            intent_family=str(data.get("intent_family") or ""),
            assessed_market_context_ref=str(data.get("assessed_market_context_ref") or ""),
            assessed_strategy_thesis_ref=str(data.get("assessed_strategy_thesis_ref") or ""),
            assessed_risk_assessment_ref=str(data.get("assessed_risk_assessment_ref") or ""),
            consistency_status=str(data.get("consistency_status") or ""),
            final_presentation_mode=str(data.get("final_presentation_mode") or ""),
            thesis_strength_after_risk=str(data.get("thesis_strength_after_risk") or ""),
            confidence_reconciliation=dict(data.get("confidence_reconciliation") or {}),
            agreement_points=list(data.get("agreement_points") or []),
            contradiction_points=list(data.get("contradiction_points") or []),
            required_final_answer_emphasis=list(data.get("required_final_answer_emphasis") or []),
            prohibited_final_answer_patterns=list(data.get("prohibited_final_answer_patterns") or []),
            final_synthesis_guidance=str(data.get("final_synthesis_guidance") or ""),
            limitations=list(data.get("limitations") or []),
            evidence_refs=list(data.get("evidence_refs") or []),
            source_refs=list(data.get("source_refs") or []),
            market_context_refs=list(data.get("market_context_refs") or []),
            strategy_thesis_refs=list(data.get("strategy_thesis_refs") or []),
            risk_assessment_refs=list(data.get("risk_assessment_refs") or []),
            prohibited_outputs_detected=bool(data.get("prohibited_outputs_detected") or False),
            consistency_ref=str(data.get("consistency_ref") or ""),
        )


def _ordered_unique(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
