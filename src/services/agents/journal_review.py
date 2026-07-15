from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.answer_compliance import (
    TRADING_INSTRUCTION_PATTERNS,
    AgentAnswerComplianceInputBuilder,
)
from src.services.agents.projection import compact_compliance_result


SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b[A-Z0-9_]*(?:API|TOKEN|SECRET|KEY)[A-Z0-9_]*\s*[:=]\s*['\"]?[^'\"\s]+",
        r"\bsk-[A-Za-z0-9_-]{12,}",
        r"\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s]+",
    ]
]

POSITION_SIZING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\blot\s+size\b",
        r"\blot\s*[:=]\s*\d",
        r"\bposition\s+size\b",
        r"\baccount\s+risk\b",
        r"\brisk\s+\d+(\.\d+)?\s*%",
        r"\bentry\s+price\b",
        r"\bstop[-\s]?loss\b",
        r"\btake[-\s]?profit\b",
        r"\bSL\s*[:=]",
        r"\bTP\s*[:=]",
    ]
]

MT5_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bMT5\b",
        r"\bplace\s+order\b",
        r"\bexecute\s+trade\b",
        r"\bopen\s+position\b",
        r"\bclose\s+position\b",
        r"\b[đd][ặa]t\s+l[ệe]nh\b",
    ]
]


@dataclass
class JournalReviewInput:
    request_id: str
    user_query: str
    rewritten_query: str = ""
    parent_intent: str = ""
    answer_type: str = ""
    execution_allowed: bool = False
    final_answer_sha256: str = ""
    final_answer_chars: int = 0
    final_answer_source: str = ""
    delivery_sha256: str = ""
    display_sha256: str = ""
    task_ids: List[str] = field(default_factory=list)
    task_scope_map: Dict[str, str] = field(default_factory=dict)
    query_plan_summary: Dict[str, Any] = field(default_factory=dict)
    context_sufficiency_summary: Dict[str, Any] = field(default_factory=dict)
    evidence_bundle_refs_by_task: Dict[str, str] = field(default_factory=dict)
    source_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    required_source_refs_by_task: Dict[str, List[str]] = field(default_factory=dict)
    agent_runtime_summary: Dict[str, Any] = field(default_factory=dict)
    agent_handoff_summary: Dict[str, Any] = field(default_factory=dict)
    compliance_summary: Dict[str, Any] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    compact_task_analysis_snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    final_answer_text: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_query": self.user_query,
            "rewritten_query": self.rewritten_query,
            "parent_intent": self.parent_intent,
            "answer_type": self.answer_type,
            "execution_allowed": self.execution_allowed,
            "final_answer_sha256": self.final_answer_sha256,
            "final_answer_chars": self.final_answer_chars,
            "final_answer_source": self.final_answer_source,
            "delivery_sha256": self.delivery_sha256,
            "display_sha256": self.display_sha256,
            "task_ids": list(self.task_ids),
            "task_scope_map": dict(self.task_scope_map),
            "query_plan_summary": dict(self.query_plan_summary),
            "context_sufficiency_summary": dict(self.context_sufficiency_summary),
            "evidence_bundle_refs_by_task": dict(self.evidence_bundle_refs_by_task),
            "source_refs_by_task": {key: list(value) for key, value in self.source_refs_by_task.items()},
            "required_source_refs_by_task": {key: list(value) for key, value in self.required_source_refs_by_task.items()},
            "agent_runtime_summary": dict(self.agent_runtime_summary),
            "agent_handoff_summary": dict(self.agent_handoff_summary),
            "compliance_summary": dict(self.compliance_summary),
            "validation_summary": dict(self.validation_summary),
            "compact_task_analysis_snapshots": dict(self.compact_task_analysis_snapshots),
        }


@dataclass
class JournalTaskReview:
    task_id: str
    intent_family: str = ""
    evidence_status: str = "UNKNOWN"
    agent_status: str = "SKIPPED"
    compliance_status: str = "UNKNOWN"
    completeness_status: str = "UNKNOWN"
    source_reference_status: str = "UNKNOWN"
    key_limitations: List[str] = field(default_factory=list)
    review_flags: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent_family": self.intent_family,
            "evidence_status": self.evidence_status,
            "agent_status": self.agent_status,
            "compliance_status": self.compliance_status,
            "completeness_status": self.completeness_status,
            "source_reference_status": self.source_reference_status,
            "key_limitations": list(self.key_limitations),
            "review_flags": list(self.review_flags),
        }


@dataclass
class JournalReviewRecord:
    journal_id: str
    request_id: str
    created_at: str
    final_answer_sha256: str
    status: str
    quality_label: str
    review_outcome: str
    task_reviews: List[JournalTaskReview] = field(default_factory=list)
    agent_summary: Dict[str, Any] = field(default_factory=dict)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    follow_up_review_items: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    prohibited_outputs_detected: bool = False
    input_chars: int = 0
    latency_ms: float = 0.0
    storage_mode: str = "runtime_artifacts"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "journal_id": self.journal_id,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "final_answer_sha256": self.final_answer_sha256,
            "status": self.status,
            "quality_label": self.quality_label,
            "review_outcome": self.review_outcome,
            "task_reviews": [item.as_dict() for item in self.task_reviews],
            "agent_summary": dict(self.agent_summary),
            "safety_summary": dict(self.safety_summary),
            "evidence_summary": dict(self.evidence_summary),
            "validation_summary": dict(self.validation_summary),
            "follow_up_review_items": list(self.follow_up_review_items),
            "limitations": list(self.limitations),
            "prohibited_outputs_detected": self.prohibited_outputs_detected,
            "input_chars": self.input_chars,
            "latency_ms": self.latency_ms,
            "storage_mode": self.storage_mode,
        }


class JournalReviewInputBuilder:
    @classmethod
    def build(
        cls,
        final_answer_text: str,
        runtime_artifacts: Mapping[str, Any] | None,
        completion_result: Mapping[str, Any] | None = None,
        memory_policy_action: str = "pending",
        user_query: str = "",
        answer_contracts: Sequence[Any] | None = None,
    ) -> JournalReviewInput:
        artifacts = dict(runtime_artifacts or {})
        final_artifact = artifacts.get("final_answer_artifact") if isinstance(artifacts.get("final_answer_artifact"), Mapping) else {}
        delivery_artifact = artifacts.get("answer_delivery_artifact") if isinstance(artifacts.get("answer_delivery_artifact"), Mapping) else {}
        agent_runtime = artifacts.get("agent_runtime") if isinstance(artifacts.get("agent_runtime"), Mapping) else {}
        execution_plan = agent_runtime.get("execution_plan") if isinstance(agent_runtime.get("execution_plan"), Mapping) else {}
        aggregated = agent_runtime.get("aggregated_result") if isinstance(agent_runtime.get("aggregated_result"), Mapping) else {}
        handoff = agent_runtime.get("handoff") if isinstance(agent_runtime.get("handoff"), Mapping) else {}
        contracts = list(answer_contracts or artifacts.get("answer_contracts") or [])
        compliance_input = AgentAnswerComplianceInputBuilder.build(final_answer_text, artifacts, contracts)
        completion = dict(completion_result or {})
        claim = artifacts.get("claim_validation") if isinstance(artifacts.get("claim_validation"), Mapping) else {}
        contract_eval = artifacts.get("contract_evaluation") if isinstance(artifacts.get("contract_evaluation"), Mapping) else {}
        compliance = artifacts.get("agent_answer_compliance") if isinstance(artifacts.get("agent_answer_compliance"), Mapping) else {}
        evidence_suff = artifacts.get("evidence_sufficiency") if isinstance(artifacts.get("evidence_sufficiency"), Mapping) else {}
        request_id = str(
            handoff.get("request_id")
            or execution_plan.get("request_id")
            or compliance.get("request_id")
            or completion.get("request_id")
            or ""
        )
        selected_hash = str(final_artifact.get("sha256") or _answer_sha256(final_answer_text))
        return JournalReviewInput(
            request_id=request_id,
            user_query=_redact_text(user_query),
            rewritten_query=_redact_text(str(artifacts.get("rewritten_query") or "")),
            parent_intent=str(execution_plan.get("parent_intent") or ""),
            answer_type=str(compliance_input.answer_type or ""),
            execution_allowed=bool(execution_plan.get("execution_allowed") or False),
            final_answer_sha256=selected_hash,
            final_answer_chars=int(final_artifact.get("chars") or len(final_answer_text or "")),
            final_answer_source=str(final_artifact.get("source") or ""),
            delivery_sha256=str(delivery_artifact.get("canonical_sha256") or delivery_artifact.get("sha256") or ""),
            display_sha256=str(delivery_artifact.get("display_sha256") or ""),
            task_ids=list(compliance_input.task_ids),
            task_scope_map=dict(compliance_input.task_scope_map),
            query_plan_summary=cls._query_plan_summary(artifacts),
            context_sufficiency_summary=dict(evidence_suff),
            evidence_bundle_refs_by_task=dict(compliance_input.evidence_bundle_refs_by_task),
            source_refs_by_task=cls._source_refs_by_task(artifacts),
            required_source_refs_by_task=cls._required_source_refs_by_task(contracts),
            agent_runtime_summary={
                "aggregate_status": aggregated.get("status", "SKIPPED" if not execution_plan.get("tasks") else "UNKNOWN"),
                "task_results": cls._task_result_summary(agent_runtime.get("results") or []),
                "unavailable_agents": list(execution_plan.get("unavailable_agents") or []),
                "blocked_agents": list(aggregated.get("blocked_tasks") or []),
                "warnings": list(aggregated.get("warnings") or handoff.get("warnings") or []),
            },
            agent_handoff_summary=cls._handoff_summary(handoff),
            compliance_summary=compact_compliance_result(compliance),
            validation_summary={
                "claim_validation_status": str(claim.get("status") or "UNKNOWN"),
                "contract_status": str(contract_eval.get("status") or "UNKNOWN"),
                "agent_answer_compliance": str(compliance.get("status") or "UNKNOWN"),
                "answer_completeness_status": str(completion.get("overall_status") or completion.get("level") or "UNKNOWN"),
                "answer_completeness_reason": str(completion.get("reason") or ""),
                "source_reference_present": bool(completion.get("has_source_reference") or False),
                "source_policy": str(completion.get("source_policy") or "unknown"),
                "memory_policy_action": memory_policy_action,
            },
            compact_task_analysis_snapshots=dict(compliance_input.task_analysis_snapshots_by_task),
            final_answer_text=str(final_answer_text or ""),
        )

    @staticmethod
    def _query_plan_summary(artifacts: Mapping[str, Any]) -> Dict[str, Any]:
        for bundle in artifacts.get("evidence_bundles", []) or []:
            if isinstance(bundle, Mapping) and isinstance(bundle.get("query_plan"), Mapping):
                plan = bundle.get("query_plan") or {}
                return {
                    "task_id": plan.get("task_id", ""),
                    "primary_intent": plan.get("primary_intent", ""),
                    "temporal_scope": plan.get("temporal_scope", ""),
                    "requires_execution": bool(plan.get("requires_execution") or False),
                }
        return {}

    @staticmethod
    def _source_refs_by_task(artifacts: Mapping[str, Any]) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = {}
        for bundle in artifacts.get("evidence_bundles", []) or []:
            if not isinstance(bundle, Mapping):
                continue
            task_id = str(bundle.get("task_id") or "")
            refs: List[str] = []
            for item in bundle.get("primary_evidence", []) or []:
                if not isinstance(item, Mapping):
                    continue
                title = str(item.get("source_title") or item.get("source_organization") or item.get("symbol") or "")
                owner = str(item.get("source_author") or item.get("source_organization") or "")
                ref = f"{title} - {owner}" if title and owner and owner not in title else title
                if ref:
                    refs.append(ref)
            if task_id:
                output[task_id] = _ordered_unique(refs)
        return output

    @staticmethod
    def _required_source_refs_by_task(contracts: Sequence[Any]) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = {}
        for contract in contracts or []:
            task_id = str(contract.get("task_id") if isinstance(contract, Mapping) else getattr(contract, "task_id", "") or "")
            refs = contract.get("required_source_refs", []) if isinstance(contract, Mapping) else getattr(contract, "required_source_refs", [])
            if task_id:
                output[task_id] = [str(ref) for ref in refs or [] if str(ref or "").strip()]
        return output

    @staticmethod
    def _task_result_summary(results: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": item.get("task_id", ""),
                "parent_task_id": item.get("parent_task_id", ""),
                "agent_type": item.get("agent_type", ""),
                "status": item.get("status", ""),
                "failure_code": item.get("failure_code", ""),
            }
            for item in results or []
            if isinstance(item, Mapping)
        ]

    @staticmethod
    def _handoff_summary(handoff: Mapping[str, Any]) -> Dict[str, Any]:
        results = handoff.get("agent_results") if isinstance(handoff.get("agent_results"), list) else []
        summary = {
            "market_context_refs": [],
            "strategy_thesis_refs": [],
            "risk_assessment_refs": [],
            "consistency_assessment_refs": [],
        }
        for result in results:
            if not isinstance(result, Mapping) or result.get("status") not in {"SUCCESS", "PARTIAL"}:
                continue
            payload = result.get("structured_payload") if isinstance(result.get("structured_payload"), Mapping) else {}
            agent_type = result.get("agent_type")
            if agent_type == "MarketContextAgent" and payload.get("assessment_ref"):
                summary["market_context_refs"].append(payload.get("assessment_ref"))
            elif agent_type == "StrategyAgent" and payload.get("thesis_ref"):
                summary["strategy_thesis_refs"].append(payload.get("thesis_ref"))
            elif agent_type == "RiskAgent" and payload.get("risk_ref"):
                summary["risk_assessment_refs"].append(payload.get("risk_ref"))
            elif agent_type == "StrategyRiskConsistencyAgent" and payload.get("consistency_ref"):
                summary["consistency_assessment_refs"].append(payload.get("consistency_ref"))
        return {key: _ordered_unique([str(item) for item in value]) for key, value in summary.items()}


class JournalReviewAgent:
    @classmethod
    def review(cls, review_input: JournalReviewInput) -> JournalReviewRecord:
        started = time.perf_counter()
        input_chars = len(json.dumps(review_input.as_dict(), ensure_ascii=False, default=str))
        safety = cls._safety_summary(review_input)
        validation = dict(review_input.validation_summary)
        task_reviews = [cls._task_review(review_input, task_id) for task_id in review_input.task_ids]
        flags = _ordered_unique([flag for task in task_reviews for flag in task.review_flags])
        if safety["safety_status"] == "FAIL":
            flags.append("safety_failure")
        if cls._hash_mismatch(review_input):
            flags.append("artifact_hash_mismatch")
        quality_label, review_outcome, status = cls._quality(validation, safety, flags)
        agent_summary = cls._agent_summary(review_input)
        evidence_summary = cls._evidence_summary(review_input, validation)
        limitations = _ordered_unique(
            list(review_input.agent_runtime_summary.get("warnings") or [])
            + [flag for flag in flags if flag in {"missing_source_reference", "artifact_hash_mismatch"}]
        )
        record = JournalReviewRecord(
            journal_id=f"journal_review:{review_input.request_id or review_input.final_answer_sha256[:12]}",
            request_id=review_input.request_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            final_answer_sha256=review_input.final_answer_sha256,
            status=status,
            quality_label=quality_label,
            review_outcome=review_outcome,
            task_reviews=task_reviews,
            agent_summary=agent_summary,
            safety_summary=safety,
            evidence_summary=evidence_summary,
            validation_summary=validation,
            follow_up_review_items=cls._follow_ups(flags, validation),
            limitations=limitations,
            prohibited_outputs_detected=bool(
                safety["trading_instruction_detected"]
                or safety["position_sizing_detected"]
                or safety["account_risk_detected"]
                or safety["mt5_execution_detected"]
            ),
            input_chars=input_chars,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        cls._log(record)
        return record

    @staticmethod
    def _task_review(review_input: JournalReviewInput, task_id: str) -> JournalTaskReview:
        scope = review_input.task_scope_map.get(task_id, "")
        evidence_status = str(review_input.context_sufficiency_summary.get("status") or "UNKNOWN")
        aggregate_status = str(review_input.agent_runtime_summary.get("aggregate_status") or "SKIPPED")
        has_agent_refs = any(
            task_id in str(ref)
            for refs in review_input.agent_handoff_summary.values()
            for ref in (refs if isinstance(refs, list) else [])
        )
        if has_agent_refs:
            agent_status = aggregate_status if aggregate_status != "UNKNOWN" else "PASS"
        elif scope in {"static_explanation", "book_concept_explanation"}:
            agent_status = "NOT_REQUIRED"
        else:
            agent_status = aggregate_status
        compliance_status = str(review_input.compliance_summary.get("status") or "UNKNOWN")
        completeness_status = str(review_input.validation_summary.get("answer_completeness_status") or "UNKNOWN")
        source_present = bool(review_input.validation_summary.get("source_reference_present") or False)
        required_sources = review_input.required_source_refs_by_task.get(task_id) or []
        source_status = "PRESENT" if source_present else ("MISSING" if required_sources else "NOT_REQUIRED")
        flags: List[str] = []
        if source_status == "MISSING":
            flags.append("missing_source_reference")
        if compliance_status == "FAIL":
            flags.append("compliance_failed")
        if str(completeness_status).upper() == "FAIL" or str(completeness_status).lower() == "fail":
            flags.append("answer_incomplete")
        if agent_status in {"FAIL", "FAILED", "TIMEOUT", "DEPENDENCY_BLOCKED"}:
            flags.append("agent_chain_incomplete")
        limitations = []
        snapshot = review_input.compact_task_analysis_snapshots.get(task_id) or {}
        for section in ("market_context", "strategy", "risk", "consistency"):
            payload = snapshot.get(section) if isinstance(snapshot.get(section), Mapping) else {}
            limitations.extend([str(item) for item in payload.get("limitations", []) or []])
        return JournalTaskReview(
            task_id=task_id,
            intent_family=str(scope or snapshot.get("intent_family") or ""),
            evidence_status=evidence_status,
            agent_status=agent_status,
            compliance_status=compliance_status,
            completeness_status=str(completeness_status),
            source_reference_status=source_status,
            key_limitations=_ordered_unique(limitations)[:5],
            review_flags=_ordered_unique(flags),
        )

    @staticmethod
    def _safety_summary(review_input: JournalReviewInput) -> Dict[str, Any]:
        text = review_input.final_answer_text or ""
        trading = any(pattern.search(text) for pattern in TRADING_INSTRUCTION_PATTERNS)
        position = any(pattern.search(text) for pattern in POSITION_SIZING_PATTERNS)
        account = bool(re.search(r"\b(account\s+risk|risk\s+\d+(\.\d+)?\s*%)\b", text, re.IGNORECASE))
        mt5 = any(pattern.search(text) for pattern in MT5_PATTERNS)
        execution_allowed = bool(review_input.execution_allowed)
        status = "FAIL" if execution_allowed or trading or position or account or mt5 else "PASS"
        return {
            "execution_allowed": execution_allowed,
            "trading_instruction_detected": trading,
            "position_sizing_detected": position,
            "account_risk_detected": account,
            "mt5_execution_detected": mt5,
            "safety_status": status,
        }

    @staticmethod
    def _hash_mismatch(review_input: JournalReviewInput) -> bool:
        selected = review_input.final_answer_sha256
        if not selected:
            return True
        delivery = review_input.delivery_sha256
        if delivery and delivery != selected:
            return True
        actual = _answer_sha256(review_input.final_answer_text)
        return actual != selected

    @staticmethod
    def _quality(validation: Mapping[str, Any], safety: Mapping[str, Any], flags: Sequence[str]) -> tuple[str, str, str]:
        compliance = str(validation.get("agent_answer_compliance", "") or validation.get("agent_answer_compliance_status", "") or "")
        if not compliance:
            compliance = str(validation.get("compliance_status", "") or "")
        completeness = str(validation.get("answer_completeness_status") or "").upper()
        claim = str(validation.get("claim_validation_status") or "").upper()
        if safety.get("safety_status") == "FAIL" or compliance.upper() == "FAIL":
            return "unsafe_or_noncompliant", "needs_human_review", "DEGRADED"
        if completeness == "FAIL" or str(validation.get("answer_completeness_status")).lower() == "fail":
            return "incomplete", "needs_human_review", "DEGRADED"
        if claim == "FAIL":
            return "failed_validation", "exclude_from_learning", "DEGRADED"
        if "artifact_hash_mismatch" in flags:
            return "failed_validation", "needs_human_review", "DEGRADED"
        if compliance.upper() == "WARN" or flags:
            return "acceptable", "suitable_for_later_review", "RECORDED_WITH_WARNINGS"
        if completeness == "PASS" and claim == "PASS" and compliance.upper() in {"PASS", ""}:
            return "high_quality", "suitable_for_memory", "RECORDED"
        return "acceptable", "suitable_for_later_review", "RECORDED_WITH_WARNINGS"

    @staticmethod
    def _agent_summary(review_input: JournalReviewInput) -> Dict[str, Any]:
        handoff = review_input.agent_handoff_summary
        return {
            "market_context_present": bool(handoff.get("market_context_refs")),
            "strategy_thesis_present": bool(handoff.get("strategy_thesis_refs")),
            "risk_assessment_present": bool(handoff.get("risk_assessment_refs")),
            "consistency_assessment_present": bool(handoff.get("consistency_assessment_refs")),
            "agent_chain_status": review_input.agent_runtime_summary.get("aggregate_status", "SKIPPED"),
        }

    @staticmethod
    def _evidence_summary(review_input: JournalReviewInput, validation: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "evidence_bundle_refs": list(review_input.evidence_bundle_refs_by_task.values()),
            "source_refs": _ordered_unique([ref for refs in review_input.source_refs_by_task.values() for ref in refs]),
            "required_source_refs": _ordered_unique([ref for refs in review_input.required_source_refs_by_task.values() for ref in refs]),
            "source_reference_present": bool(validation.get("source_reference_present") or False),
        }

    @staticmethod
    def _follow_ups(flags: Sequence[str], validation: Mapping[str, Any]) -> List[str]:
        items = []
        if "missing_source_reference" in flags:
            items.append("review_source_reference_format")
        if str(validation.get("agent_answer_compliance", "")).upper() in {"WARN", "FAIL"}:
            items.append("review_agent_compliance_alignment")
        if "artifact_hash_mismatch" in flags:
            items.append("review_artifact_identity_chain")
        if "safety_failure" in flags:
            items.append("review_safety_language")
        return _ordered_unique(items)

    @staticmethod
    def _log(record: JournalReviewRecord) -> None:
        flags = _ordered_unique([flag for task in record.task_reviews for flag in task.review_flags])
        print(
            "[JournalReview] "
            f"request_id={record.request_id} status={record.status} "
            f"quality_label={record.quality_label} review_outcome={record.review_outcome} "
            f"tasks={len(record.task_reviews)} flags={flags} "
            f"input_chars={record.input_chars} payload_chars={len(json.dumps(record.as_dict(), ensure_ascii=False, default=str))} "
            f"latency_ms={record.latency_ms}"
        )
        for task in record.task_reviews:
            print(
                "[JournalReviewTask] "
                f"task_id={task.task_id} intent_family={task.intent_family} "
                f"evidence_status={task.evidence_status} agent_status={task.agent_status} "
                f"compliance_status={task.compliance_status} completeness_status={task.completeness_status} "
                f"source_reference_status={task.source_reference_status} flags={task.review_flags}"
            )
        print(
            "[JournalReviewSafety] "
            f"execution_allowed={str(record.safety_summary.get('execution_allowed')).lower()} "
            f"trading_instruction_detected={str(record.safety_summary.get('trading_instruction_detected')).lower()} "
            f"position_sizing_detected={str(record.safety_summary.get('position_sizing_detected')).lower()} "
            f"mt5_execution_detected={str(record.safety_summary.get('mt5_execution_detected')).lower()} "
            f"status={record.safety_summary.get('safety_status')}"
        )
        print("[JournalReviewStorage] mode=runtime_artifacts status=PASS")


def record_journal_review(
    final_answer_text: str,
    runtime_artifacts: Dict[str, Any] | None,
    completion_result: Mapping[str, Any] | None,
    memory_policy_action: str = "pending",
    user_query: str = "",
    answer_contracts: Sequence[Any] | None = None,
) -> JournalReviewRecord | None:
    if runtime_artifacts is None:
        return None
    review_input = JournalReviewInputBuilder.build(
        final_answer_text=final_answer_text,
        runtime_artifacts=runtime_artifacts,
        completion_result=completion_result,
        memory_policy_action=memory_policy_action,
        user_query=user_query,
        answer_contracts=answer_contracts,
    )
    record = JournalReviewAgent.review(review_input)
    runtime_artifacts["journal_review"] = record.as_dict()
    return record


def _answer_sha256(answer: str) -> str:
    return hashlib.sha256(str(answer or "").encode("utf-8", errors="ignore")).hexdigest()


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _redact_text(value: str) -> str:
    text = str(value or "")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
