from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Protocol, Set

from src.services.agents.projection import compact_agent_payload, log_projection
from src.services.agents.runtime import AgentResultEnvelope, AgentRuntimeContext, AgentStatus, AgentTaskEnvelope


THESIS_TYPES = {"conditional_directional", "neutral_observation", "range_or_waiting", "mixed", "unclear"}
THESIS_DIRECTIONS = {"bullish_bias", "bearish_bias", "balanced", "no_clear_bias", "mixed"}
SUPPORT_STRENGTH = {"strong", "adequate", "weak"}
CONFIDENCE_CEILING = {"high": 0.85, "medium": 0.65, "low": 0.4}

FORBIDDEN_FIELDS = {
    "entry_price",
    "stop_loss",
    "take_profit",
    "lot_size",
    "order_type",
    "buy_now",
    "sell_now",
    "open_position",
    "close_position",
    "execute_trade",
    "place_order",
    "mt5_action",
    "account_risk",
    "position_size",
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
        r"\bopen\s+position\b",
        r"\bclose\s+position\b",
        r"\bexecute\s+trade\b",
        r"\bplace\s+order\b",
        r"\bmt5\b",
    ]
]


@dataclass
class StrategyInput:
    request_id: str
    task_id: str
    parent_task_id: str
    intent_family: str
    symbol: str = ""
    as_of: str = ""
    temporal_scope: str = ""
    market_context_assessment_ref: str = ""
    market_context_assessment: Dict[str, Any] = field(default_factory=dict)
    evidence_bundle_ref: str = ""
    topic_binding_refs: List[str] = field(default_factory=list)
    allowed_evidence_refs: List[str] = field(default_factory=list)
    allowed_source_refs: List[str] = field(default_factory=list)
    allowed_market_context_refs: List[str] = field(default_factory=list)
    decision_context_ref: str = "decision_context"
    task_context_ref: str = ""
    confidence_ceiling: str = "high"
    missing_context: List[str] = field(default_factory=list)
    limitations_from_market_context: List[str] = field(default_factory=list)

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
            "evidence_bundle_ref": self.evidence_bundle_ref,
            "topic_binding_refs": list(self.topic_binding_refs),
            "allowed_evidence_refs": list(self.allowed_evidence_refs),
            "allowed_source_refs": list(self.allowed_source_refs),
            "allowed_market_context_refs": list(self.allowed_market_context_refs),
            "decision_context_ref": self.decision_context_ref,
            "task_context_ref": self.task_context_ref,
            "confidence_ceiling": self.confidence_ceiling,
            "missing_context": list(self.missing_context),
            "limitations_from_market_context": list(self.limitations_from_market_context),
        }


@dataclass
class StrategyThesis:
    request_id: str
    task_id: str
    parent_task_id: str
    symbol: str
    as_of: str
    intent_family: str
    thesis_type: str
    thesis_direction: str
    thesis_summary: str
    rationale: List[Dict[str, Any]] = field(default_factory=list)
    supporting_factors: List[Dict[str, Any]] = field(default_factory=list)
    conflicting_factors: List[Dict[str, Any]] = field(default_factory=list)
    activation_conditions: List[Dict[str, Any]] = field(default_factory=list)
    invalidation_conditions: List[Dict[str, Any]] = field(default_factory=list)
    scenario_map: Dict[str, str] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    missing_context: List[str] = field(default_factory=list)
    confidence: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    market_context_refs: List[str] = field(default_factory=list)
    prohibited_outputs_detected: bool = False
    thesis_ref: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "intent_family": self.intent_family,
            "thesis_type": self.thesis_type,
            "thesis_direction": self.thesis_direction,
            "thesis_summary": self.thesis_summary,
            "rationale": [dict(item) for item in self.rationale],
            "supporting_factors": [dict(item) for item in self.supporting_factors],
            "conflicting_factors": [dict(item) for item in self.conflicting_factors],
            "activation_conditions": [dict(item) for item in self.activation_conditions],
            "invalidation_conditions": [dict(item) for item in self.invalidation_conditions],
            "scenario_map": dict(self.scenario_map),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "missing_context": list(self.missing_context),
            "confidence": dict(self.confidence),
            "evidence_refs": list(self.evidence_refs),
            "source_refs": list(self.source_refs),
            "market_context_refs": list(self.market_context_refs),
            "prohibited_outputs_detected": self.prohibited_outputs_detected,
            "thesis_ref": self.thesis_ref or f"strategy_thesis:{self.task_id}",
        }


class StrategyReasoningBackend(Protocol):
    def produce(self, strategy_input: StrategyInput) -> StrategyThesis | Dict[str, Any]:
        ...


class StrategyInputAssembler:
    @classmethod
    def assemble(cls, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> StrategyInput:
        decision_context = context.decision_context_ref
        query_plan = getattr(decision_context, "query_plan", None) or context.query_plan_ref or {}
        parent_task_id = task.parent_task_id or str(query_plan.get("task_id") or "task_1")
        task_view = cls._task_view(context, parent_task_id)
        market_result = cls._market_context_result(context, parent_task_id)
        raw_market_payload = dict(market_result.structured_payload) if market_result else {}
        market_payload = compact_agent_payload("MarketContextAgent", raw_market_payload)
        if raw_market_payload:
            log_projection(parent_task_id, "market_context_for_strategy", raw_market_payload, market_payload)
        assessment_ref = str(market_payload.get("assessment_ref") or "")
        missing_context = list(task_view.get("missing_required") or task_view.get("missing_context") or [])
        if not assessment_ref:
            missing_context.append("market_context_assessment")
        uncertainty = market_payload.get("uncertainty") if isinstance(market_payload.get("uncertainty"), dict) else {}
        confidence_ceiling = str(task_view.get("confidence_ceiling") or getattr(decision_context, "confidence_ceiling", "") or "high")
        assembled = StrategyInput(
            request_id=str(getattr(decision_context, "request_id", "") or "agent_request"),
            task_id=task.task_id,
            parent_task_id=parent_task_id,
            intent_family=task.intent_family,
            symbol=str(market_payload.get("symbol") or cls._symbol(query_plan)),
            as_of=str(market_payload.get("as_of") or ""),
            temporal_scope=str(cls._child_query_plan(query_plan, parent_task_id).get("temporal_scope") or query_plan.get("temporal_scope") or ""),
            market_context_assessment_ref=assessment_ref,
            market_context_assessment=market_payload,
            evidence_bundle_ref=f"evidence_bundle:{parent_task_id}",
            allowed_evidence_refs=list(task.evidence_refs or []),
            allowed_source_refs=list(task.source_refs or task.metadata.get("allowed_source_refs", []) or []),
            allowed_market_context_refs=[assessment_ref] if assessment_ref else [],
            task_context_ref=f"task_context:{parent_task_id}",
            confidence_ceiling=confidence_ceiling,
            missing_context=_ordered_unique(missing_context),
            limitations_from_market_context=list(uncertainty.get("limitations") or []),
        )
        print(
            "[StrategyInput] "
            f"task_id={assembled.task_id} symbol={assembled.symbol} "
            f"market_context_ref={assembled.market_context_assessment_ref} "
            f"allowed_evidence_refs={assembled.allowed_evidence_refs} "
            f"confidence_ceiling={assembled.confidence_ceiling} "
            f"missing_context={assembled.missing_context} "
            f"serialized_chars={len(json.dumps(assembled.as_dict(), ensure_ascii=False, default=str))}"
        )
        return assembled

    @staticmethod
    def _task_view(context: AgentRuntimeContext, task_id: str) -> Dict[str, Any]:
        item = (context.task_context_refs or {}).get(task_id)
        return dict(item) if isinstance(item, dict) else {}

    @staticmethod
    def _market_context_result(context: AgentRuntimeContext, parent_task_id: str) -> AgentResultEnvelope | None:
        results = (context.metadata or {}).get("agent_results_by_task") or {}
        result = results.get(f"{parent_task_id}:MarketContextAgent")
        if isinstance(result, AgentResultEnvelope) and result.status in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}:
            return result
        return None

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


class DeterministicStrategyReasoningBackend:
    def produce(self, strategy_input: StrategyInput) -> StrategyThesis:
        assessment = strategy_input.market_context_assessment or {}
        market_state = assessment.get("market_state") if isinstance(assessment.get("market_state"), dict) else {}
        dominant = assessment.get("dominant_factors") if isinstance(assessment.get("dominant_factors"), list) else []
        conflicts = assessment.get("conflicting_signals") if isinstance(assessment.get("conflicting_signals"), list) else []
        direction = self._direction(str(market_state.get("directional_bias") or "unclear"), bool(conflicts))
        thesis_type = self._thesis_type(direction, bool(conflicts))
        confidence = self._confidence(strategy_input, assessment, bool(conflicts))
        support = [self._supporting_factor(item, strategy_input) for item in dominant[:4] if isinstance(item, dict)]
        conflict_items = [self._conflict(item, strategy_input) for item in conflicts[:3] if isinstance(item, dict)]
        activation = self._activation_conditions(assessment, strategy_input)
        invalidation = self._invalidation_conditions(assessment, strategy_input)
        summary = self._summary(direction, thesis_type, bool(conflicts))
        return StrategyThesis(
            request_id=strategy_input.request_id,
            task_id=strategy_input.task_id,
            parent_task_id=strategy_input.parent_task_id,
            symbol=strategy_input.symbol,
            as_of=strategy_input.as_of,
            intent_family=strategy_input.intent_family,
            thesis_type=thesis_type,
            thesis_direction=direction,
            thesis_summary=summary,
            rationale=[
                {
                    "statement": "Thesis is conditional on the supplied market context and evidence references.",
                    "evidence_refs": list(strategy_input.allowed_evidence_refs),
                    "market_context_refs": [strategy_input.market_context_assessment_ref],
                    "support_strength": "adequate" if strategy_input.allowed_evidence_refs else "weak",
                }
            ],
            supporting_factors=support,
            conflicting_factors=conflict_items,
            activation_conditions=activation,
            invalidation_conditions=invalidation,
            scenario_map={
                "bullish_case": "Bullish thesis only if supplied confirmations strengthen.",
                "bearish_case": "Bearish thesis only if supplied invalidations or risk conditions dominate.",
                "neutral_case": "Neutral thesis if mixed signals persist.",
            },
            assumptions=["No execution decision is made by StrategyAgent."],
            limitations=list(strategy_input.limitations_from_market_context or []),
            missing_context=list(strategy_input.missing_context or []),
            confidence={
                "value": confidence,
                "ceiling": strategy_input.confidence_ceiling,
                "rationale": "Bounded by upstream context confidence and market-context uncertainty.",
            },
            evidence_refs=list(strategy_input.allowed_evidence_refs),
            source_refs=list(strategy_input.allowed_source_refs),
            market_context_refs=[strategy_input.market_context_assessment_ref] if strategy_input.market_context_assessment_ref else [],
            prohibited_outputs_detected=False,
            thesis_ref=f"strategy_thesis:{strategy_input.task_id}",
        )

    @staticmethod
    def _direction(bias: str, has_conflicts: bool) -> str:
        if has_conflicts:
            return "mixed"
        if bias == "bullish_pressure":
            return "bullish_bias"
        if bias == "bearish_pressure":
            return "bearish_bias"
        if bias == "balanced":
            return "balanced"
        return "no_clear_bias"

    @staticmethod
    def _thesis_type(direction: str, has_conflicts: bool) -> str:
        if has_conflicts:
            return "mixed"
        if direction in {"bullish_bias", "bearish_bias"}:
            return "conditional_directional"
        if direction == "balanced":
            return "range_or_waiting"
        return "unclear"

    @staticmethod
    def _confidence(strategy_input: StrategyInput, assessment: Mapping[str, Any], has_conflicts: bool) -> float:
        ceiling = CONFIDENCE_CEILING.get(strategy_input.confidence_ceiling, 0.65)
        uncertainty = assessment.get("uncertainty") if isinstance(assessment.get("uncertainty"), dict) else {}
        market_confidence = float(uncertainty.get("confidence") or ceiling)
        value = min(ceiling, market_confidence)
        if has_conflicts:
            value = min(value, 0.65)
        if strategy_input.missing_context:
            value = min(value, 0.5)
        return round(max(0.0, min(value, 1.0)), 2)

    @staticmethod
    def _supporting_factor(item: Mapping[str, Any], strategy_input: StrategyInput) -> Dict[str, Any]:
        return {
            "factor": str(item.get("factor") or "market context factor"),
            "category": str(item.get("category") or "market_context"),
            "direction": str(item.get("directional_pressure") or "unclear"),
            "support_strength": str(item.get("support_strength") or "adequate"),
            "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(strategy_input.allowed_evidence_refs)],
            "market_context_refs": [strategy_input.market_context_assessment_ref],
        }

    @staticmethod
    def _conflict(item: Mapping[str, Any], strategy_input: StrategyInput) -> Dict[str, Any]:
        return {
            "factor": str(item.get("signal_a") or "market context signal"),
            "conflict_with": str(item.get("signal_b") or "opposing signal"),
            "explanation": str(item.get("explanation") or "Signals conflict within supplied context."),
            "evidence_refs": [ref for ref in item.get("evidence_refs", []) if ref in set(strategy_input.allowed_evidence_refs)],
            "market_context_refs": [strategy_input.market_context_assessment_ref],
        }

    @staticmethod
    def _activation_conditions(assessment: Mapping[str, Any], strategy_input: StrategyInput) -> List[Dict[str, Any]]:
        conditions = assessment.get("confirmation_conditions") if isinstance(assessment.get("confirmation_conditions"), dict) else {}
        output = []
        for key, value in list(conditions.items())[:3]:
            if value:
                output.append({
                    "condition": str(value),
                    "reason": f"Confirmation condition from market context: {key}",
                    "evidence_refs": list(strategy_input.allowed_evidence_refs),
                    "context_refs": [strategy_input.market_context_assessment_ref],
                })
        return output or [{
            "condition": "Wait for clearer confirmation from supplied evidence context.",
            "reason": "No specific confirmation condition was supplied.",
            "evidence_refs": list(strategy_input.allowed_evidence_refs),
            "context_refs": [strategy_input.market_context_assessment_ref] if strategy_input.market_context_assessment_ref else [],
        }]

    @staticmethod
    def _invalidation_conditions(assessment: Mapping[str, Any], strategy_input: StrategyInput) -> List[Dict[str, Any]]:
        conditions = assessment.get("invalidation_conditions") if isinstance(assessment.get("invalidation_conditions"), list) else []
        return [
            {
                "condition": str(item),
                "reason": "Invalidation condition from market context.",
                "evidence_refs": list(strategy_input.allowed_evidence_refs),
                "context_refs": [strategy_input.market_context_assessment_ref],
            }
            for item in conditions[:3]
            if item
        ] or [{
            "condition": "Thesis weakens if supplied evidence no longer supports the current context.",
            "reason": "Generic context invalidation.",
            "evidence_refs": list(strategy_input.allowed_evidence_refs),
            "context_refs": [strategy_input.market_context_assessment_ref] if strategy_input.market_context_assessment_ref else [],
        }]

    @staticmethod
    def _summary(direction: str, thesis_type: str, has_conflicts: bool) -> str:
        if has_conflicts:
            return "Market thesis remains conditional because supplied context contains conflicting signals."
        if direction in {"bullish_bias", "bearish_bias"}:
            return "Directional thesis is conditional and requires confirmation from supplied context."
        if thesis_type == "range_or_waiting":
            return "Thesis favors observation while context remains balanced."
        return "No clear strategy thesis is supported by the supplied context."


class StrategyThesisValidator:
    @classmethod
    def validate(cls, thesis: StrategyThesis | Dict[str, Any], strategy_input: StrategyInput) -> List[str]:
        data = thesis.as_dict() if isinstance(thesis, StrategyThesis) else dict(thesis or {})
        reasons: List[str] = []
        if data.get("task_id") != strategy_input.task_id:
            reasons.append("task_id_mismatch")
        if data.get("parent_task_id") != strategy_input.parent_task_id:
            reasons.append("parent_task_id_mismatch")
        if data.get("thesis_type") not in THESIS_TYPES:
            reasons.append("invalid_thesis_type")
        if data.get("thesis_direction") not in THESIS_DIRECTIONS:
            reasons.append("invalid_thesis_direction")
        confidence = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
        value = float(confidence.get("value") or 0.0)
        ceiling = CONFIDENCE_CEILING.get(strategy_input.confidence_ceiling, 0.65)
        if not 0.0 <= value <= 1.0 or value > ceiling:
            reasons.append("confidence_ceiling_exceeded")
        if not set(data.get("evidence_refs") or []) <= set(strategy_input.allowed_evidence_refs or []):
            reasons.append("evidence_ref_out_of_scope")
        if not set(data.get("source_refs") or []) <= set(strategy_input.allowed_source_refs or []):
            reasons.append("source_ref_out_of_scope")
        if not set(data.get("market_context_refs") or []) <= set(strategy_input.allowed_market_context_refs or []):
            reasons.append("market_context_ref_out_of_scope")
        if data.get("prohibited_outputs_detected") is True:
            reasons.append("prohibited_output_detected")
        if cls._has_forbidden_field(data):
            reasons.append("forbidden_trading_field")
        if cls._has_forbidden_text(data):
            reasons.append("forbidden_trading_instruction")
        if strategy_input.market_context_assessment_ref and strategy_input.market_context_assessment_ref not in set(data.get("market_context_refs") or []):
            reasons.append("missing_market_context_ref")
        if not strategy_input.market_context_assessment_ref:
            reasons.append("missing_market_context_assessment")
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


class StrategyAgentRuntime:
    agent_type = "StrategyAgent"

    def __init__(self, backend: StrategyReasoningBackend | None = None):
        self.backend = backend or DeterministicStrategyReasoningBackend()

    def execute(self, task: AgentTaskEnvelope, context: AgentRuntimeContext) -> AgentResultEnvelope:
        print(f"[StrategyAgent] task_id={task.task_id} status=start")
        started = time.perf_counter()
        strategy_input = StrategyInputAssembler.assemble(task, context)
        produced = self.backend.produce(strategy_input)
        raw_reasons = StrategyThesisValidator.validate(produced, strategy_input)
        thesis = self._coerce(produced)
        reasons = _ordered_unique(raw_reasons + StrategyThesisValidator.validate(thesis, strategy_input))
        if reasons:
            print(f"[StrategyValidation] task_id={task.task_id} status=FAIL reason_codes={reasons}")
            return AgentResultEnvelope(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_type=self.agent_type,
                status=AgentStatus.INVALID_RESULT,
                result_type="strategy_thesis",
                structured_payload=thesis.as_dict(),
                summary="Invalid strategy thesis.",
                evidence_refs=[],
                source_refs=[],
                confidence=0.0,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                failure_code="AGENT_RESULT_INVALID",
                failure_reason=",".join(reasons),
            )
        payload = thesis.as_dict()
        print(f"[StrategyValidation] task_id={task.task_id} status=PASS reason_codes=[]")
        print(
            "[StrategyThesis] "
            f"task_id={task.task_id} thesis_type={payload.get('thesis_type')} "
            f"thesis_direction={payload.get('thesis_direction')} "
            f"confidence={(payload.get('confidence') or {}).get('value')} "
            f"supporting_factors={len(payload.get('supporting_factors') or [])} "
            f"conflicting_factors={len(payload.get('conflicting_factors') or [])} "
            f"activation_conditions={len(payload.get('activation_conditions') or [])} "
            f"invalidation_conditions={len(payload.get('invalidation_conditions') or [])} "
            f"payload_chars={len(json.dumps(payload, ensure_ascii=False, default=str))}"
        )
        return AgentResultEnvelope(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_type=self.agent_type,
            status=AgentStatus.SUCCESS,
            result_type="strategy_thesis",
            structured_payload=payload,
            summary=thesis.thesis_summary,
            evidence_refs=list(thesis.evidence_refs),
            source_refs=list(thesis.source_refs),
            confidence=float((thesis.confidence or {}).get("value") or 0.0),
            limitations=list(thesis.limitations),
            warnings=[],
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            metadata={"strategy_thesis_is_not_evidence": True},
        )

    @staticmethod
    def _coerce(produced: StrategyThesis | Dict[str, Any]) -> StrategyThesis:
        if isinstance(produced, StrategyThesis):
            return produced
        data = dict(produced or {})
        return StrategyThesis(
            request_id=str(data.get("request_id") or ""),
            task_id=str(data.get("task_id") or ""),
            parent_task_id=str(data.get("parent_task_id") or ""),
            symbol=str(data.get("symbol") or ""),
            as_of=str(data.get("as_of") or ""),
            intent_family=str(data.get("intent_family") or ""),
            thesis_type=str(data.get("thesis_type") or ""),
            thesis_direction=str(data.get("thesis_direction") or ""),
            thesis_summary=str(data.get("thesis_summary") or ""),
            rationale=list(data.get("rationale") or []),
            supporting_factors=list(data.get("supporting_factors") or []),
            conflicting_factors=list(data.get("conflicting_factors") or []),
            activation_conditions=list(data.get("activation_conditions") or []),
            invalidation_conditions=list(data.get("invalidation_conditions") or []),
            scenario_map=dict(data.get("scenario_map") or {}),
            assumptions=list(data.get("assumptions") or []),
            limitations=list(data.get("limitations") or []),
            missing_context=list(data.get("missing_context") or []),
            confidence=dict(data.get("confidence") or {}),
            evidence_refs=list(data.get("evidence_refs") or []),
            source_refs=list(data.get("source_refs") or []),
            market_context_refs=list(data.get("market_context_refs") or []),
            prohibited_outputs_detected=bool(data.get("prohibited_outputs_detected") or False),
            thesis_ref=str(data.get("thesis_ref") or ""),
        )


def _ordered_unique(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
