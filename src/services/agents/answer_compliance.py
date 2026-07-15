from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Set

from src.services.agents.projection import (
    TaskAnalysisSnapshot,
    compact_agent_payload,
    compact_compliance_result,
    log_projection,
)

COMPLIANCE_STATUSES = {"PASS", "WARN", "FAIL"}
FINAL_ACTIONS = {"accept", "accept_with_warning", "repair_required", "bounded_response_required"}

TRADING_INSTRUCTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bbuy\s+now\b",
        r"\bsell\s+now\b",
        r"\benter\s+(at|now)\b",
        r"\bentry\s+price\s*[:=]?\s*\d",
        r"\b(set|use|place)\s+(a\s+)?stop[-\s]?loss\b",
        r"\bstop[-\s]?loss\s*[:=]?\s*\d",
        r"\bsl\s*[:=]\s*\d",
        r"\b(set|use|place)\s+(a\s+)?take[-\s]?profit\b",
        r"\btake[-\s]?profit\s*[:=]?\s*\d",
        r"\btp\s*[:=]\s*\d",
        r"\blot\s+size\s*[:=]?\s*\d",
        r"\bposition\s+size\s*[:=]?\s*\d",
        r"\brisk\s+\d+(\.\d+)?\s*%",
        r"\baccount\s+risk\s*[:=]?\s*\d",
        r"\bplace\s+order\b",
        r"\bexecute\s+trade\b",
        r"\bmt5\s+order\b",
        r"\bopen\s+position\b",
        r"\bclose\s+position\b",
        r"\b(n[eê]n|h[aã]y|c[aầ]n|ph[aả]i)\s+mua\s+ngay\b",
        r"\b(n[eê]n|h[aã]y|c[aầ]n|ph[aả]i)\s+b[aá]n\s+ngay\b",
        r"\b(n[eê]n|h[aã]y|c[aầ]n|ph[aả]i)\s+v[aà]o\s+l[eệ]nh\b",
        r"\bv[aà]o\s+l[eệ]nh\s+(mua|b[aá]n)\b",
        r"\b[iđ]i[eể]m\s+v[aà]o\s*[:=]?\s*\d",
        r"\b(i[eê]m|m[uư]c|gi[aá])\s+v[aà]o\s+l[eệ]nh\s*[:=]?\s*\d",
        r"\b([đd][ặa]t|d[uù]ng|s[uử]\s+d[uụ]ng)\s+c[aắ]t\s+l[oỗ]\b",
        r"\bc[aắ]t\s+l[oỗ]\s+(t[aạ]i|[oở]\s+m[uư]c|:|=)\s*\d",
        r"\b([đd][ặa]t|d[uù]ng|s[uử]\s+d[uụ]ng)\s+ch[oố]t\s+l[ờo]i\b",
        r"\bch[oố]t\s+l[ờo]i\s+(t[aạ]i|[oở]\s+m[uư]c|:|=)\s*\d",
        r"\bkh[oố]i\s+l[uư][ợo]ng\s+l[eệ]nh\s*[:=]?\s*\d",
        r"\blot\s*[:=]?\s*\d",
        r"\b\d+(\.\d+)?\s*%\s+(t[aà]i\s+kho[aả]n|account)\b",
        r"\b[đd][ặa]t\s+l[eệ]nh\s+(mua|b[aá]n)\b",
    ]
]

MARKET_ANALYSIS_EXECUTION_TERM_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bv[aà]o\s+l[eệ]nh\b",
        r"\b[iđ]i[eể]m\s+v[aà]o\b",
        r"\bc[aắ]t\s+l[oỗ]\b",
        r"\bch[oố]t\s+l[ờo]i\b",
        r"\bkh[oố]i\s+l[uư][ợo]ng\s+l[eệ]nh\b",
        r"\bph[aầ]n\s+tr[aă]m\s+t[aà]i\s+kho[aả]n\b",
        r"\b[đd][ặa]t\s+l[eệ]nh\b",
    ]
]

UNSUPPORTED_CERTAINTY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"ch[aắ]c\s+ch[aắ]n\s+(s[eẽ]\s+)?(t[aă]ng|gi[aả]m)",
        r"xu\s+h[uư][ớo]ng\s+r[oõ]\s+r[aà]ng\s+s[eẽ]",
        r"t[ií]n\s+hi[eệ]u\s+mua",
        r"t[ií]n\s+hi[eệ]u\s+b[aá]n",
        r"\bguaranteed\b",
        r"\bdefinitely\b",
        r"\bwill\s+certainly\b",
        r"\bclear\s+(buy|sell)\b",
        r"\bmust\s+(rise|fall)\b",
    ]
]

CAUTION_TERMS = [
    "rủi ro",
    "rui ro",
    "thận trọng",
    "than trong",
    "không chắc",
    "khong chac",
    "không rõ",
    "khong ro",
    "điều kiện",
    "dieu kien",
    "xác nhận",
    "xac nhan",
    "vô hiệu",
    "vo hieu",
    "uncertain",
    "uncertainty",
    "caution",
    "risk",
    "conditional",
    "confirmation",
    "invalidation",
    "mixed",
]

AGENT_AS_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"according\s+to\s+(the\s+)?(riskagent|strategyagent|riskassessment|strategythesis|consistencyassessment)\s+as\s+(source\s+)?evidence",
        r"(riskagent|strategyagent|riskassessment|strategythesis|consistencyassessment)\s+proves\b",
        r"(riskassessment|strategythesis|consistencyassessment)\s+evidence\s+shows\b",
        r"b[aằ]ng\s+ch[uứ]ng\s+t[uừ]\s+(riskagent|strategyagent|riskassessment|strategythesis|consistencyassessment)",
    ]
]


@dataclass
class AgentAnswerComplianceInput:
    request_id: str
    final_answer_text: str
    final_answer_sha256: str
    answer_type: str = ""
    parent_intent: str = ""
    task_ids: List[str] = field(default_factory=list)
    answer_contracts_by_task: Dict[str, Any] = field(default_factory=dict)
    contract_evaluations_by_task: Dict[str, Any] = field(default_factory=dict)
    answer_coverage_by_task: Dict[str, Any] = field(default_factory=dict)
    claim_validation_result: Dict[str, Any] = field(default_factory=dict)
    evidence_bundle_refs_by_task: Dict[str, str] = field(default_factory=dict)
    agent_handoff_ref: str = "agent_handoff"
    market_context_assessments_by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    strategy_theses_by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    risk_assessments_by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    consistency_assessments_by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    task_analysis_snapshots_by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    confidence_ceiling_by_task: Dict[str, str] = field(default_factory=dict)
    task_scope_map: Dict[str, str] = field(default_factory=dict)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "answer_type": self.answer_type,
            "parent_intent": self.parent_intent,
            "task_ids": list(self.task_ids),
            "answer_contracts_by_task": dict(self.answer_contracts_by_task),
            "contract_evaluations_by_task": dict(self.contract_evaluations_by_task),
            "answer_coverage_by_task": dict(self.answer_coverage_by_task),
            "claim_validation_result": dict(self.claim_validation_result),
            "evidence_bundle_refs_by_task": dict(self.evidence_bundle_refs_by_task),
            "agent_handoff_ref": self.agent_handoff_ref,
            "market_context_assessments_by_task": dict(self.market_context_assessments_by_task),
            "strategy_theses_by_task": dict(self.strategy_theses_by_task),
            "risk_assessments_by_task": dict(self.risk_assessments_by_task),
            "consistency_assessments_by_task": dict(self.consistency_assessments_by_task),
            "confidence_ceiling_by_task": dict(self.confidence_ceiling_by_task),
            "task_scope_map": dict(self.task_scope_map),
            "execution_allowed": self.execution_allowed,
            "answer_chars": len(self.final_answer_text or ""),
        }


@dataclass
class AgentAnswerComplianceTaskResult:
    task_id: str
    status: str = "PASS"
    reason_codes: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    required_repairs: List[str] = field(default_factory=list)
    overstatement_detected: bool = False
    risk_omission_detected: bool = False
    consistency_violation_detected: bool = False
    unsupported_certainty_detected: bool = False
    trading_instruction_detected: bool = False
    sibling_scope_violation_detected: bool = False
    agent_output_as_evidence_detected: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "required_repairs": list(self.required_repairs),
            "overstatement_detected": self.overstatement_detected,
            "risk_omission_detected": self.risk_omission_detected,
            "consistency_violation_detected": self.consistency_violation_detected,
            "unsupported_certainty_detected": self.unsupported_certainty_detected,
            "trading_instruction_detected": self.trading_instruction_detected,
            "sibling_scope_violation_detected": self.sibling_scope_violation_detected,
            "agent_output_as_evidence_detected": self.agent_output_as_evidence_detected,
        }


@dataclass
class AgentAnswerComplianceResult:
    request_id: str
    status: str
    task_results: List[AgentAnswerComplianceTaskResult] = field(default_factory=list)
    aggregate_status: str = "PASS"
    reason_codes: List[str] = field(default_factory=list)
    overstatement_detected: bool = False
    risk_omission_detected: bool = False
    consistency_violation_detected: bool = False
    unsupported_certainty_detected: bool = False
    trading_instruction_detected: bool = False
    sibling_scope_violation_detected: bool = False
    agent_output_as_evidence_detected: bool = False
    confidence_alignment: List[Dict[str, Any]] = field(default_factory=list)
    final_answer_action: str = "accept"
    repair_guidance: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "task_results": [item.as_dict() for item in self.task_results],
            "aggregate_status": self.aggregate_status,
            "reason_codes": list(self.reason_codes),
            "overstatement_detected": self.overstatement_detected,
            "risk_omission_detected": self.risk_omission_detected,
            "consistency_violation_detected": self.consistency_violation_detected,
            "unsupported_certainty_detected": self.unsupported_certainty_detected,
            "trading_instruction_detected": self.trading_instruction_detected,
            "sibling_scope_violation_detected": self.sibling_scope_violation_detected,
            "agent_output_as_evidence_detected": self.agent_output_as_evidence_detected,
            "confidence_alignment": [dict(item) for item in self.confidence_alignment],
            "final_answer_action": self.final_answer_action,
            "repair_guidance": list(self.repair_guidance),
            "latency_ms": self.latency_ms,
        }


class AgentAnswerComplianceInputBuilder:
    @classmethod
    def build(
        cls,
        final_answer_text: str,
        runtime_artifacts: Mapping[str, Any] | None,
        answer_contracts: Sequence[Any] | None = None,
    ) -> AgentAnswerComplianceInput:
        artifacts = dict(runtime_artifacts or {})
        agent_runtime = artifacts.get("agent_runtime") or {}
        handoff = agent_runtime.get("handoff") or {}
        execution_plan = agent_runtime.get("execution_plan") or {}
        results = handoff.get("agent_results") or []
        task_ids = cls._task_ids(artifacts, answer_contracts, results)
        market_payloads = cls._payloads_by_task(results, "MarketContextAgent")
        strategy_payloads = cls._payloads_by_task(results, "StrategyAgent")
        risk_payloads = cls._payloads_by_task(results, "RiskAgent")
        consistency_payloads = cls._payloads_by_task(results, "StrategyRiskConsistencyAgent")
        confidence_by_task = cls._confidence_by_task(artifacts, results)
        evidence_refs_by_task = cls._evidence_refs_by_task(artifacts)
        task_scope_map = cls._task_scope_map(task_ids, answer_contracts)
        return AgentAnswerComplianceInput(
            request_id=str(handoff.get("request_id") or execution_plan.get("request_id") or ""),
            final_answer_text=str(final_answer_text or ""),
            final_answer_sha256=_answer_sha256(final_answer_text),
            answer_type=cls._answer_type(artifacts, answer_contracts),
            parent_intent=str(execution_plan.get("parent_intent") or ""),
            task_ids=task_ids,
            answer_contracts_by_task=cls._contracts_by_task(answer_contracts),
            contract_evaluations_by_task=cls._contract_evaluations_by_task(artifacts),
            answer_coverage_by_task=dict(artifacts.get("answer_coverage_by_task") or {}),
            claim_validation_result=dict(artifacts.get("claim_validation") or {}),
            evidence_bundle_refs_by_task=evidence_refs_by_task,
            agent_handoff_ref="agent_handoff",
            market_context_assessments_by_task=market_payloads,
            strategy_theses_by_task=strategy_payloads,
            risk_assessments_by_task=risk_payloads,
            consistency_assessments_by_task=consistency_payloads,
            task_analysis_snapshots_by_task=cls._snapshots_by_task(
                task_ids,
                execution_plan,
                evidence_refs_by_task,
                market_payloads,
                strategy_payloads,
                risk_payloads,
                consistency_payloads,
                confidence_by_task,
                task_scope_map,
            ),
            confidence_ceiling_by_task=confidence_by_task,
            task_scope_map=task_scope_map,
            execution_allowed=bool(execution_plan.get("execution_allowed") or False),
        )

    @staticmethod
    def _payloads_by_task(results: Sequence[Mapping[str, Any]], agent_type: str) -> Dict[str, Dict[str, Any]]:
        output: Dict[str, Dict[str, Any]] = {}
        for result in results or []:
            if not isinstance(result, Mapping):
                continue
            if result.get("agent_type") != agent_type or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            task_id = str(result.get("parent_task_id") or result.get("task_id") or "")
            payload = result.get("structured_payload") if isinstance(result.get("structured_payload"), Mapping) else {}
            if task_id and payload:
                compact = compact_agent_payload(agent_type, payload)
                log_projection(task_id, f"{agent_type}_for_compliance", payload, compact)
                output[task_id] = compact
        return output

    @staticmethod
    def _snapshots_by_task(
        task_ids: Sequence[str],
        execution_plan: Mapping[str, Any],
        evidence_refs_by_task: Mapping[str, str],
        market_payloads: Mapping[str, Dict[str, Any]],
        strategy_payloads: Mapping[str, Dict[str, Any]],
        risk_payloads: Mapping[str, Dict[str, Any]],
        consistency_payloads: Mapping[str, Dict[str, Any]],
        confidence_by_task: Mapping[str, str],
        task_scope_map: Mapping[str, str],
    ) -> Dict[str, Dict[str, Any]]:
        tasks = execution_plan.get("tasks") if isinstance(execution_plan.get("tasks"), list) else []
        task_meta = {
            str(item.get("parent_task_id") or item.get("task_id") or ""): item
            for item in tasks
            if isinstance(item, Mapping)
        }
        output: Dict[str, Dict[str, Any]] = {}
        for task_id in task_ids:
            meta = task_meta.get(task_id, {})
            market = dict(market_payloads.get(task_id) or {})
            strategy = dict(strategy_payloads.get(task_id) or {})
            risk = dict(risk_payloads.get(task_id) or {})
            consistency = dict(consistency_payloads.get(task_id) or {})
            snapshot = TaskAnalysisSnapshot(
                request_id=str(execution_plan.get("request_id") or ""),
                task_id=task_id,
                parent_task_id=task_id,
                intent_family=str(meta.get("intent_family") or task_scope_map.get(task_id) or ""),
                symbol=str(
                    market.get("symbol")
                    or strategy.get("symbol")
                    or risk.get("symbol")
                    or consistency.get("symbol")
                    or ""
                ),
                temporal_scope=str(meta.get("metadata", {}).get("temporal_scope") if isinstance(meta.get("metadata"), Mapping) else ""),
                as_of=str(market.get("as_of") or strategy.get("as_of") or risk.get("as_of") or consistency.get("as_of") or ""),
                evidence_bundle_ref=str(evidence_refs_by_task.get(task_id) or f"evidence_bundle:{task_id}"),
                allowed_evidence_refs=[str(evidence_refs_by_task.get(task_id) or f"evidence_bundle:{task_id}")],
                allowed_source_refs=list(meta.get("source_refs") or []),
                market_context=market,
                strategy=strategy,
                risk=risk,
                consistency=consistency,
                execution_allowed=bool(execution_plan.get("execution_allowed") or False),
            )
            data = snapshot.as_dict()
            data["compliance"] = {
                "confidence_ceiling": confidence_by_task.get(task_id, "high"),
                "task_scope": task_scope_map.get(task_id, "task"),
            }
            output[task_id] = data
        return output

    @staticmethod
    def _task_ids(artifacts: Mapping[str, Any], answer_contracts: Sequence[Any] | None, results: Sequence[Mapping[str, Any]]) -> List[str]:
        values: List[str] = []
        for contract in answer_contracts or []:
            task_id = getattr(contract, "task_id", "") if not isinstance(contract, Mapping) else contract.get("task_id", "")
            if task_id:
                values.append(str(task_id))
        for bundle in artifacts.get("evidence_bundles", []) or []:
            task_id = bundle.get("task_id", "") if isinstance(bundle, Mapping) else getattr(bundle, "task_id", "")
            if task_id:
                values.append(str(task_id))
        for result in results or []:
            if isinstance(result, Mapping):
                task_id = str(result.get("parent_task_id") or result.get("task_id") or "")
                if task_id:
                    values.append(task_id)
        return _ordered_unique(values) or ["task_1"]

    @staticmethod
    def _contracts_by_task(answer_contracts: Sequence[Any] | None) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for contract in answer_contracts or []:
            task_id = getattr(contract, "task_id", "") if not isinstance(contract, Mapping) else contract.get("task_id", "")
            if task_id:
                output[str(task_id)] = contract.as_dict() if hasattr(contract, "as_dict") else dict(contract)
        return output

    @staticmethod
    def _contract_evaluations_by_task(artifacts: Mapping[str, Any]) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for item in artifacts.get("contract_evaluations", []) or []:
            if isinstance(item, Mapping) and item.get("task_id"):
                output[str(item.get("task_id"))] = dict(item)
        ce = artifacts.get("contract_evaluation")
        if isinstance(ce, Mapping) and ce.get("task_id") and ce.get("task_id") not in output:
            output[str(ce.get("task_id"))] = dict(ce)
        return output

    @staticmethod
    def _evidence_refs_by_task(artifacts: Mapping[str, Any]) -> Dict[str, str]:
        output: Dict[str, str] = {}
        for bundle in artifacts.get("evidence_bundles", []) or []:
            task_id = bundle.get("task_id", "") if isinstance(bundle, Mapping) else getattr(bundle, "task_id", "")
            if task_id:
                output[str(task_id)] = f"evidence_bundle:{task_id}"
        return output

    @staticmethod
    def _confidence_by_task(artifacts: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
        output: Dict[str, str] = {}
        suff = artifacts.get("evidence_sufficiency") if isinstance(artifacts.get("evidence_sufficiency"), Mapping) else {}
        default = str(suff.get("confidence_ceiling") or "high")
        for result in results or []:
            if isinstance(result, Mapping):
                task_id = str(result.get("parent_task_id") or result.get("task_id") or "")
                if task_id:
                    output.setdefault(task_id, default)
        for task_id in AgentAnswerComplianceInputBuilder._evidence_refs_by_task(artifacts):
            output.setdefault(task_id, default)
        return output

    @staticmethod
    def _task_scope_map(task_ids: Sequence[str], answer_contracts: Sequence[Any] | None) -> Dict[str, str]:
        output: Dict[str, str] = {}
        for contract in answer_contracts or []:
            task_id = getattr(contract, "task_id", "") if not isinstance(contract, Mapping) else contract.get("task_id", "")
            answer_type = getattr(contract, "answer_type", "") if not isinstance(contract, Mapping) else contract.get("answer_type", "")
            if task_id:
                output[str(task_id)] = str(answer_type or "task")
        for task_id in task_ids:
            output.setdefault(task_id, "task")
        return output

    @staticmethod
    def _answer_type(artifacts: Mapping[str, Any], answer_contracts: Sequence[Any] | None) -> str:
        for contract in answer_contracts or []:
            value = getattr(contract, "answer_type", "") if not isinstance(contract, Mapping) else contract.get("answer_type", "")
            if value:
                return str(value)
        return ""


class AgentAnswerComplianceGate:
    @classmethod
    def evaluate(cls, compliance_input: AgentAnswerComplianceInput) -> AgentAnswerComplianceResult:
        started = time.perf_counter()
        task_results = [cls._evaluate_task(compliance_input, task_id) for task_id in compliance_input.task_ids]
        status = cls._aggregate_status(task_results)
        reason_codes = _ordered_unique([code for task in task_results for code in task.reason_codes])
        result = AgentAnswerComplianceResult(
            request_id=compliance_input.request_id,
            status=status,
            aggregate_status=status,
            task_results=task_results,
            reason_codes=reason_codes,
            overstatement_detected=any(task.overstatement_detected for task in task_results),
            risk_omission_detected=any(task.risk_omission_detected for task in task_results),
            consistency_violation_detected=any(task.consistency_violation_detected for task in task_results),
            unsupported_certainty_detected=any(task.unsupported_certainty_detected for task in task_results),
            trading_instruction_detected=any(task.trading_instruction_detected for task in task_results),
            sibling_scope_violation_detected=any(task.sibling_scope_violation_detected for task in task_results),
            agent_output_as_evidence_detected=any(task.agent_output_as_evidence_detected for task in task_results),
            confidence_alignment=cls._confidence_alignment(compliance_input, task_results),
            final_answer_action=cls._action(status),
            repair_guidance=cls._repair_guidance(task_results),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        cls._log(compliance_input, result)
        return result

    @classmethod
    def _evaluate_task(cls, compliance_input: AgentAnswerComplianceInput, task_id: str) -> AgentAnswerComplianceTaskResult:
        text = compliance_input.final_answer_text or ""
        lower_text = text.lower()
        consistency = compliance_input.consistency_assessments_by_task.get(task_id) or {}
        risk = compliance_input.risk_assessments_by_task.get(task_id) or {}
        strategy = compliance_input.strategy_theses_by_task.get(task_id) or {}
        has_agents = bool(consistency or risk or strategy or compliance_input.market_context_assessments_by_task.get(task_id))
        task_result = AgentAnswerComplianceTaskResult(task_id=task_id)

        if cls._has_trading_instruction(text, include_market_terms=has_agents):
            cls._fail(task_result, "trading_instruction", "Remove executable trading instructions.")
            task_result.trading_instruction_detected = True

        if cls._agent_output_as_evidence(text):
            cls._fail(task_result, "agent_output_as_evidence", "Do not cite agent outputs as factual evidence.")
            task_result.agent_output_as_evidence_detected = True

        if has_agents:
            mode = str(consistency.get("final_presentation_mode") or "")
            consistency_status = str(consistency.get("consistency_status") or "")
            strength = str(consistency.get("thesis_strength_after_risk") or "")
            if mode in {"cautious_conditional", "mixed_or_uncertain", "risk_first", "insufficient_context"}:
                if cls._has_unsupported_certainty(text):
                    cls._fail(task_result, "unsupported_certainty", "Soften certainty to match consistency guidance.")
                    task_result.unsupported_certainty_detected = True
                    task_result.consistency_violation_detected = True
            if consistency_status in {"risk_weakened", "contradicted", "insufficient_context", "unclear"} and cls._has_strong_directional_thesis(text):
                cls._fail(task_result, "consistency_violation", "Do not overstate a weakened or unclear thesis.")
                task_result.consistency_violation_detected = True
                task_result.overstatement_detected = True
            if strength in {"weak", "very_weak", "unclear"} and cls._has_strong_directional_thesis(text):
                cls._fail(task_result, "overstatement", "Present weak thesis as conditional or uncertain.")
                task_result.overstatement_detected = True

            risk_level = str(risk.get("overall_risk_level") or "")
            risk_posture = str(risk.get("risk_posture") or "")
            if risk_level in {"elevated", "high"} or risk_posture in {"conflicting_context", "thesis_fragile", "insufficient_context"}:
                if not cls._mentions_caution(text):
                    cls._fail(task_result, "risk_omission", "Mention elevated risk, uncertainty, confirmation, or invalidation.")
                    task_result.risk_omission_detected = True

            thesis_type = str(strategy.get("thesis_type") or "")
            thesis_direction = str(strategy.get("thesis_direction") or "")
            if thesis_type in {"mixed", "unclear", "range_or_waiting", "neutral_observation"} or thesis_direction in {"mixed", "no_clear_bias", "balanced"}:
                if cls._has_strong_directional_thesis(text):
                    cls._fail(task_result, "overstatement", "Do not convert mixed or neutral thesis into one-sided certainty.")
                    task_result.overstatement_detected = True

        else:
            section = cls._task_section(text, task_id, compliance_input)
            if cls._static_section_has_market_agent_leakage(section):
                cls._fail(task_result, "sibling_scope_violation", "Remove market-agent analysis from non-market task section.")
                task_result.sibling_scope_violation_detected = True

        if not task_result.reason_codes:
            task_result.status = "PASS"
        return task_result

    @staticmethod
    def _fail(task_result: AgentAnswerComplianceTaskResult, code: str, repair: str) -> None:
        task_result.status = "FAIL"
        if code not in task_result.reason_codes:
            task_result.reason_codes.append(code)
        if code not in task_result.violations:
            task_result.violations.append(code)
        if repair not in task_result.required_repairs:
            task_result.required_repairs.append(repair)

    @staticmethod
    def _aggregate_status(task_results: Sequence[AgentAnswerComplianceTaskResult]) -> str:
        if any(item.status == "FAIL" for item in task_results):
            return "FAIL"
        if any(item.status == "WARN" for item in task_results):
            return "WARN"
        return "PASS"

    @staticmethod
    def _action(status: str) -> str:
        if status == "PASS":
            return "accept"
        if status == "WARN":
            return "accept_with_warning"
        return "repair_required"

    @staticmethod
    def _repair_guidance(task_results: Sequence[AgentAnswerComplianceTaskResult]) -> List[str]:
        return _ordered_unique([repair for task in task_results for repair in task.required_repairs])

    @staticmethod
    def _confidence_alignment(
        compliance_input: AgentAnswerComplianceInput,
        task_results: Sequence[AgentAnswerComplianceTaskResult],
    ) -> List[Dict[str, Any]]:
        output = []
        for task in task_results:
            detected = "strong" if task.unsupported_certainty_detected or task.overstatement_detected else "conditional"
            allowed = compliance_input.confidence_ceiling_by_task.get(task.task_id, "high")
            output.append({
                "task_id": task.task_id,
                "allowed_confidence": allowed,
                "detected_answer_strength": detected,
                "status": "FAIL" if task.unsupported_certainty_detected or task.overstatement_detected else "PASS",
            })
        return output

    @staticmethod
    def _has_trading_instruction(text: str, include_market_terms: bool = False) -> bool:
        if any(pattern.search(text or "") for pattern in TRADING_INSTRUCTION_PATTERNS):
            return True
        if include_market_terms:
            return any(pattern.search(text or "") for pattern in MARKET_ANALYSIS_EXECUTION_TERM_PATTERNS)
        return False

    @staticmethod
    def _has_unsupported_certainty(text: str) -> bool:
        return any(pattern.search(text or "") for pattern in UNSUPPORTED_CERTAINTY_PATTERNS)

    @staticmethod
    def _has_strong_directional_thesis(text: str) -> bool:
        return AgentAnswerComplianceGate._has_unsupported_certainty(text)

    @staticmethod
    def _mentions_caution(text: str) -> bool:
        lower = str(text or "").lower()
        return any(term in lower for term in CAUTION_TERMS)

    @staticmethod
    def _agent_output_as_evidence(text: str) -> bool:
        return any(pattern.search(text or "") for pattern in AGENT_AS_EVIDENCE_PATTERNS)

    @staticmethod
    def _static_section_has_market_agent_leakage(section: str) -> bool:
        lower = str(section or "").lower()
        agent_terms = [
            "riskassessment",
            "risk assessment",
            "strategythesis",
            "strategy thesis",
            "marketcontextassessment",
            "market context assessment",
            "consistencyassessment",
            "consistency assessment",
            "riskagent",
            "strategyagent",
        ]
        market_terms = ["xauusd", "market thesis", "risk posture", "strategy thesis"]
        return any(term in lower for term in agent_terms) and any(term in lower for term in market_terms)

    @staticmethod
    def _task_section(text: str, task_id: str, compliance_input: AgentAnswerComplianceInput) -> str:
        task_kind = compliance_input.task_scope_map.get(task_id, "")
        if task_kind in {"static_explanation", "book_concept_explanation"}:
            patterns = [
                r"(al\s+brooks|price\s+action|reading\s+price\s+charts)",
                r"(ph[ầa]n\s*2|task_2|nhi[eệ]m\s+v[uụ]\s*2)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return text[match.start():]
        return text

    @staticmethod
    def _log(compliance_input: AgentAnswerComplianceInput, result: AgentAnswerComplianceResult) -> None:
        print(
            "[AgentAnswerCompliance] "
            f"request_id={result.request_id} status={result.status} "
            f"aggregate_status={result.aggregate_status} reason_codes={result.reason_codes} "
            f"serialized_chars={len(json.dumps(compliance_input.as_dict(), ensure_ascii=False, default=str))} "
            f"payload_chars={len(json.dumps(result.as_dict(), ensure_ascii=False, default=str))} "
            f"latency_ms={result.latency_ms}"
        )
        for task in result.task_results:
            print(
                "[AgentAnswerComplianceTask] "
                f"task_id={task.task_id} status={task.status} reason_codes={task.reason_codes} "
                f"overstatement={str(task.overstatement_detected).lower()} "
                f"risk_omission={str(task.risk_omission_detected).lower()} "
                f"trading_instruction={str(task.trading_instruction_detected).lower()} "
                f"scope_violation={str(task.sibling_scope_violation_detected).lower()}"
            )
        print(f"[AgentAnswerComplianceAction] action={result.final_answer_action}")


def _answer_sha256(answer: str) -> str:
    return hashlib.sha256(str(answer or "").encode("utf-8", errors="ignore")).hexdigest()


def _ordered_unique(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
