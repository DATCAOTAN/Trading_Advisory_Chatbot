import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.services.knowledge.answer_mode import AnswerModeClassifier

def _normalize(value: Any) -> str:
    text = str(value or "").lower()
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not str(key).startswith("_")}
    return {}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _result_id(value: Any) -> str:
    if hasattr(value, "result_id"):
        return value.result_id()
    capability = str(_get(value, "capability", ""))
    target = str(_get(value, "target", "default") or "default")
    return f"{capability}:{target}"


def _data_from_result(result: Any) -> Any:
    if isinstance(result, dict):
        return result.get("data")
    return getattr(result, "data", None)


def _metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
    return metadata


def _doc_content(doc: Dict[str, Any]) -> str:
    for key in ("content", "text", "child_text", "parent_text", "page_content"):
        text = str(doc.get(key, "") or "").strip()
        if text:
            return text
    metadata = _metadata(doc)
    for key in ("content", "text", "excerpt", "summary"):
        text = str(metadata.get(key, "") or "").strip()
        if text:
            return text
    return ""


def _shorten(text: str, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    norm = _normalize(text)
    return any(_normalize(term) in norm for term in terms if str(term or "").strip())


@dataclass
class EvidenceItem:
    evidence_id: str
    task_id: str
    evidence_type: str
    capability: str
    target: str = ""
    content: str = ""
    content_summary: str = ""
    source_title: str = ""
    source_author: str = ""
    source_organization: str = ""
    source_type: str = ""
    event_type: str = ""
    period: str = ""
    symbol: str = ""
    timeframe: str = ""
    source_timestamp: str = ""
    fetched_at: str = ""
    freshness_status: str = "unknown"
    semantic_relevance_score: float = 0.0
    passage_usefulness_score: float = 0.0
    directness_score: float = 0.0
    provenance_confidence: float = 0.0
    redundancy_group: str = ""
    is_metadata_only: bool = False
    is_direct_evidence: bool = False
    is_supporting_evidence: bool = False
    is_current_data: bool = False
    claim_topics: List[str] = field(default_factory=list)
    covered_topics: List[str] = field(default_factory=list)
    topic_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "task_id": self.task_id,
            "evidence_type": self.evidence_type,
            "capability": self.capability,
            "target": self.target,
            "content": self.content,
            "content_summary": self.content_summary,
            "source_title": self.source_title,
            "source_author": self.source_author,
            "source_organization": self.source_organization,
            "source_type": self.source_type,
            "event_type": self.event_type,
            "period": self.period,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "source_timestamp": self.source_timestamp,
            "fetched_at": self.fetched_at,
            "freshness_status": self.freshness_status,
            "semantic_relevance_score": self.semantic_relevance_score,
            "passage_usefulness_score": self.passage_usefulness_score,
            "directness_score": self.directness_score,
            "provenance_confidence": self.provenance_confidence,
            "redundancy_group": self.redundancy_group,
            "is_metadata_only": self.is_metadata_only,
            "is_direct_evidence": self.is_direct_evidence,
            "is_supporting_evidence": self.is_supporting_evidence,
            "is_current_data": self.is_current_data,
            "claim_topics": list(self.claim_topics),
            "covered_topics": list(self.covered_topics),
            "warnings": list(self.warnings),
            "raw": dict(self.raw),
        }


@dataclass
class EvidenceSufficiencyResult:
    status: str
    completeness_score: float
    confidence_ceiling: str
    required_roles: List[str] = field(default_factory=list)
    missing_roles: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "completeness_score": self.completeness_score,
            "confidence_ceiling": self.confidence_ceiling,
            "required_roles": list(self.required_roles),
            "missing_roles": list(self.missing_roles),
            "warnings": list(self.warnings),
        }


@dataclass
class EvidenceBundle:
    task_id: str
    query: str
    query_plan: Dict[str, Any]
    answer_type: str
    primary_evidence: List[EvidenceItem] = field(default_factory=list)
    supporting_evidence: List[EvidenceItem] = field(default_factory=list)
    current_market_evidence: List[EvidenceItem] = field(default_factory=list)
    event_evidence: List[EvidenceItem] = field(default_factory=list)
    technical_evidence: List[EvidenceItem] = field(default_factory=list)
    source_requirements: List[str] = field(default_factory=list)
    required_evidence_roles: List[str] = field(default_factory=list)
    missing_evidence_roles: List[str] = field(default_factory=list)
    freshness_summary: Dict[str, str] = field(default_factory=dict)
    sufficiency: Optional[EvidenceSufficiencyResult] = None
    depth_plan: Optional[Any] = None
    coverage_requirements: Optional[Any] = None
    coverage_result: Optional[Any] = None
    evidence_coverage: float = 0.0
    confidence_ceiling: str = "high"
    evidence_quality: str = "UNKNOWN"
    warnings: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    evidence_dispositions: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def all_items(self) -> List[EvidenceItem]:
        output: List[EvidenceItem] = []
        for items in [
            self.primary_evidence,
            self.supporting_evidence,
            self.event_evidence,
            self.current_market_evidence,
            self.technical_evidence,
        ]:
            for item in items:
                if item.evidence_id not in {existing.evidence_id for existing in output}:
                    output.append(item)
        return output

    @all_items.setter
    def all_items(self, value: List[EvidenceItem]) -> None:
        # Backward-compatible test/fixture hook. Runtime code should continue to
        # populate the explicit evidence-role lists.
        self.primary_evidence = list(value or [])

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "query_plan": dict(self.query_plan),
            "answer_type": self.answer_type,
            "primary_evidence": [item.as_dict() for item in self.primary_evidence],
            "supporting_evidence": [item.as_dict() for item in self.supporting_evidence],
            "current_market_evidence": [item.as_dict() for item in self.current_market_evidence],
            "event_evidence": [item.as_dict() for item in self.event_evidence],
            "technical_evidence": [item.as_dict() for item in self.technical_evidence],
            "source_requirements": list(self.source_requirements),
            "required_evidence_roles": list(self.required_evidence_roles),
            "missing_evidence_roles": list(self.missing_evidence_roles),
            "freshness_summary": dict(self.freshness_summary),
            "sufficiency": self.sufficiency.as_dict() if self.sufficiency else None,
            "depth_plan": self.depth_plan.as_dict() if self.depth_plan else None,
            "coverage_requirements": self.coverage_requirements.as_dict() if self.coverage_requirements else None,
            "coverage_result": self.coverage_result.as_dict() if self.coverage_result else None,
            "evidence_coverage": self.evidence_coverage,
            "confidence_ceiling": self.confidence_ceiling,
            "evidence_quality": self.evidence_quality,
            "warnings": list(self.warnings),
            "conflicts": list(self.conflicts),
            "evidence_dispositions": [dict(item) for item in self.evidence_dispositions],
        }


@dataclass
class AnswerContract:
    task_id: str
    answer_type: str
    allowed_claim_types: List[str] = field(default_factory=list)
    required_sections: List[str] = field(default_factory=list)
    required_evidence_roles: List[str] = field(default_factory=list)
    required_source_refs: List[str] = field(default_factory=list)
    optional_sections: List[str] = field(default_factory=list)
    prohibited_claim_types: List[str] = field(default_factory=list)
    confidence_ceiling: str = "low"
    limitations: List[str] = field(default_factory=list)
    topic_bindings: List[Any] = field(default_factory=list)
    synthesis_coverage_plan: Any = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "answer_type": self.answer_type,
            "allowed_claim_types": list(self.allowed_claim_types),
            "required_sections": list(self.required_sections),
            "required_evidence_roles": list(self.required_evidence_roles),
            "required_source_refs": list(self.required_source_refs),
            "optional_sections": list(self.optional_sections),
            "prohibited_claim_types": list(self.prohibited_claim_types),
            "confidence_ceiling": self.confidence_ceiling,
            "limitations": list(self.limitations),
            "topic_bindings": [b.as_dict() if hasattr(b, "as_dict") else b for b in self.topic_bindings],
            "synthesis_coverage_plan": self.synthesis_coverage_plan.as_dict() if self.synthesis_coverage_plan and hasattr(self.synthesis_coverage_plan, "as_dict") else self.synthesis_coverage_plan,
        }

@dataclass
class TopicRepairDecision:
    task_id: str
    topic_role: str
    answer_status: str
    evidence_strength: str
    repair_allowed: bool
    reason_code: str

    @staticmethod
    def evaluate(task_id: str, topic_role: str, answer_status: str, evidence_strength: str, repair_attempt_count: int = 0) -> 'TopicRepairDecision':
        # Must be UNCERTAIN, PARTIAL, or MISSING
        if answer_status not in {"UNCERTAIN", "PARTIAL", "MISSING"}:
            return TopicRepairDecision(task_id, topic_role, answer_status, evidence_strength, False, "already_covered")
        
        # Evidence must be STRONG or ADEQUATE
        if evidence_strength not in {"STRONG", "ADEQUATE"}:
            return TopicRepairDecision(task_id, topic_role, answer_status, evidence_strength, False, "insufficient_evidence_strength")
        
        # Max 1 attempt
        if repair_attempt_count > 0:
            return TopicRepairDecision(task_id, topic_role, answer_status, evidence_strength, False, "max_attempts_reached")
        
        reason = f"uncertain_answer_with_{evidence_strength.lower()}_evidence" if answer_status == "UNCERTAIN" else f"missing_answer_with_{evidence_strength.lower()}_evidence"
        return TopicRepairDecision(task_id, topic_role, answer_status, evidence_strength, True, reason)

@dataclass
class AnswerCoverageRepairResult:
    attempt: int
    repaired_answer: str
    target_topics: List[str]
    status: str
    failure_reason: str = ""

@dataclass
class ContractEvaluationResult:
    status: str
    task_id: str = ""
    reason_codes: List[str] = field(default_factory=list)
    topic_failures: List[str] = field(default_factory=list)
    topic_warnings: List[str] = field(default_factory=list)
    claim_failures: List[str] = field(default_factory=list)
    claim_warnings: List[str] = field(default_factory=list)
    source_failures: List[str] = field(default_factory=list)
    structural_failures: List[str] = field(default_factory=list)
    confidence_ceiling: str = "high"
    repair_status: str = "NOT_ATTEMPTED"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "task_id": self.task_id,
            "reason_codes": list(self.reason_codes),
            "topic_failures": list(self.topic_failures),
            "topic_warnings": list(self.topic_warnings),
            "claim_failures": list(self.claim_failures),
            "claim_warnings": list(self.claim_warnings),
            "source_failures": list(self.source_failures),
            "structural_failures": list(self.structural_failures),
            "confidence_ceiling": self.confidence_ceiling,
            "repair_status": self.repair_status,
        }

class AnswerContractEvaluator:
    @staticmethod
    def evaluate(
        contract: 'AnswerContract',
        coverage_val: Any,
        claim_val: 'ClaimValidationResult',
        repair_status: str = "NOT_ATTEMPTED",
        task_id: str = "",
    ) -> ContractEvaluationResult:
        task_id = task_id or getattr(contract, "task_id", "")
        reason_codes = []
        topic_failures = []
        topic_warnings = []
        claim_failures = []
        claim_warnings = []
        
        # Check topics
        if contract.synthesis_coverage_plan:
            plan = contract.synthesis_coverage_plan
            if hasattr(plan, 'required_unsupported') and plan.required_unsupported > 0:
                topic_failures.append(f"{plan.required_unsupported}_unsupported_topics")
                reason_codes.append("required_topic_unsupported")
            elif hasattr(plan, 'required_weak') and plan.required_weak > 0:
                topic_warnings.append(f"{plan.required_weak}_weak_topics")
                reason_codes.append("required_topic_weak")

        # Check coverage
        if coverage_val:
            if coverage_val.status == "FAIL":
                topic_failures.append("answer_coverage_failed")
                reason_codes.append("answer_coverage_failed")
            elif coverage_val.status == "WARN":
                topic_warnings.append("answer_coverage_warn")
                reason_codes.append("answer_coverage_partial")

        # Check claims
        if claim_val:
            if claim_val.status == "FAIL":
                claim_failures.extend(claim_val.violations)
                for viol in claim_val.violations:
                    reason_codes.append(f"claim_violation:{viol}")
            if claim_val.warnings:
                for w in claim_val.warnings:
                    if hasattr(w, "severity") and w.severity == "CONTRACT_DEGRADING_WARN":
                        claim_warnings.append(w.warning_code)
                        reason_codes.append(f"claim_warning:{w.warning_code}:{w.claim_id}")
                        
        if repair_status == "ATTEMPTED_NO_IMPROVEMENT":
            topic_warnings.append("repair_attempted_no_improvement")
            reason_codes.append("repair_attempted_no_improvement")
        elif repair_status == "ATTEMPTED_REGRESSED":
            topic_warnings.append("repair_attempted_regressed")
            reason_codes.append("repair_attempted_regressed")

        status = "PASS"
        if topic_failures or claim_failures:
            status = "FAIL"
        elif topic_warnings or claim_warnings:
            status = "WARN"

        task_log = f"task_id={task_id} " if task_id else ""
        print(f"[ContractEvaluation] {task_log}status={status} reason_codes={reason_codes} repair_status={repair_status}")
        return ContractEvaluationResult(
            status=status,
            task_id=task_id,
            reason_codes=reason_codes,
            topic_failures=topic_failures,
            topic_warnings=topic_warnings,
            claim_failures=claim_failures,
            claim_warnings=claim_warnings,
            repair_status=repair_status
        )


@dataclass
class ClaimValidationWarning:
    warning_code: str
    reason: str
    severity: str
    claim_id: str = "unknown"
    evidence_ids: List[str] = field(default_factory=list)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.warning_code == other
        return super().__eq__(other)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "warning_code": self.warning_code,
            "reason": self.reason,
            "severity": self.severity,
            "claim_id": self.claim_id,
            "evidence_ids": self.evidence_ids,
        }


@dataclass
class ClaimValidationResult:
    status: str
    violations: List[str] = field(default_factory=list)
    warnings: List[ClaimValidationWarning] = field(default_factory=list)
    validated_claim_groups: List[str] = field(default_factory=list)
    unsupported_claim_groups: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "violations": list(self.violations),
            "warnings": [w.as_dict() for w in self.warnings],
            "validated_claim_groups": list(self.validated_claim_groups),
            "unsupported_claim_groups": list(self.unsupported_claim_groups),
        }


class EvidenceUsefulnessEvaluator:
    METADATA_TERMS = (
        "copyright",
        "isbn",
        "library of congress",
        "all rights reserved",
        "publisher",
        "published by",
        "table of contents",
        "contents",
        "bibliography",
        "index",
        "dedication",
        "acknowledgments",
    )
    DIRECT_DISCUSSION_TERMS = (
        "means",
        "because",
        "therefore",
        "trader",
        "market",
        "price",
        "trend",
        "risk",
        "inflation",
        "employment",
        "rate",
        "gold",
        "xauusd",
        "support",
        "resistance",
        "discipline",
        "volume",
        "position",
        "report",
        "component",
        "components",
        "category",
        "categories",
        "sector",
        "sectors",
    )

    @classmethod
    def evaluate(cls, content: str, metadata: Optional[Dict[str, Any]] = None, query_terms: Optional[List[str]] = None) -> Tuple[float, bool, List[str]]:
        text = str(content or "").strip()
        norm = _normalize(text)
        warnings: List[str] = []
        if not text:
            return 0.0, True, ["empty_content"]
        word_count = len(re.findall(r"\w+", text))
        metadata_hits = sum(1 for term in cls.METADATA_TERMS if cls._metadata_term_present(term, norm))
        direct_hits = sum(1 for term in cls.DIRECT_DISCUSSION_TERMS if term in norm)
        query_hits = sum(1 for term in query_terms or [] if _normalize(term) and _normalize(term) in norm)
        metadata_only = False
        if metadata_hits >= 2 and direct_hits == 0:
            metadata_only = True
        if word_count < 28 and metadata_hits:
            metadata_only = True
        section = _normalize((metadata or {}).get("section") or (metadata or {}).get("section_title") or "")
        if any(term in section for term in ("copyright", "contents", "bibliography", "index")):
            metadata_only = True
        score = 0.25
        score += min(word_count / 220.0, 0.35)
        score += min(direct_hits * 0.06, 0.24)
        score += min(query_hits * 0.08, 0.24)
        score -= min(metadata_hits * 0.16, 0.45)
        if metadata_only:
            score = min(score, 0.35)
            warnings.append("metadata_only")
        score = max(0.0, min(score, 1.0))
        return score, metadata_only, warnings

    @staticmethod
    def _metadata_term_present(term: str, norm: str) -> bool:
        if term == "index":
            return bool(re.search(r"\bindex\b", norm))
        if term == "contents":
            return bool(re.search(r"\bcontents\b", norm))
        return term in norm


class EvidenceSelector:
    KNOWLEDGE_CAPABILITIES = {"official_report", "static_knowledge", "market_knowledge"}

    def select(
        self,
        query_plan: Any,
        task_view: Any,
        acquisition_results: List[Any],
        answer_type: str,
        task_id: str = "",
        phase: str = "pre_refinement"
    ) -> EvidenceBundle:
        task_dict = _as_dict(task_view)
        plan_dict = self._task_plan_dict(query_plan, task_dict, task_id)
        effective_task_id = task_id or task_dict.get("task_id") or plan_dict.get("task_id") or getattr(query_plan, "task_id", "") or "task_1"
        query = task_dict.get("subquery") or plan_dict.get("original_query") or getattr(query_plan, "original_query", "")
        relevant_results = self._relevant_results(effective_task_id, acquisition_results, task_dict)
        query_terms = self._query_terms(plan_dict, query)
        raw_items = self._items_from_results(effective_task_id, relevant_results, query_terms)
        self._apply_plan_provenance_constraints(raw_items, plan_dict)
        deduped_items, dispositions = self._dedupe_with_dispositions(raw_items)
        all_items = [
            item
            for item in deduped_items
            if self._effective_item_usable(item)
        ]
        
        # Planners
        from src.services.evidence.answer_depth import AnswerDepthPlanner
        from src.services.evidence.coverage_requirements import CoverageRequirementPlanner
        from src.services.evidence.evidence_coverage import EvidenceCoverageEvaluator
        from src.services.semantic.query_plan import QueryPlan
        
        qp_obj = query_plan if hasattr(query_plan, "primary_intent") else QueryPlan(**plan_dict)
        depth_plan = AnswerDepthPlanner.plan(qp_obj, answer_type, effective_task_id, is_multi_intent=len(getattr(qp_obj, "child_plans", [])) > 0)
        coverage_requirements = CoverageRequirementPlanner.plan(qp_obj, depth_plan, answer_type)

        primary = [
            item
            for item in all_items
            if item.capability in self.KNOWLEDGE_CAPABILITIES
            and item.is_direct_evidence
            and not item.is_metadata_only
        ]
        supporting = [
            item
            for item in all_items
            if item.capability in self.KNOWLEDGE_CAPABILITIES
            and item.evidence_id not in {primary_item.evidence_id for primary_item in primary}
            and not item.is_metadata_only
        ]
        market = [item for item in all_items if item.evidence_type == "market_snapshot"]
        events = [item for item in all_items if item.evidence_type == "economic_event_record"]
        technical = [item for item in all_items if item.evidence_type in {"ohlcv_summary", "technical_snapshot"}]

        required_roles = self.required_roles(plan_dict.get("primary_intent", ""), answer_type)
        bundle = EvidenceBundle(
            task_id=effective_task_id,
            query=query,
            query_plan=plan_dict,
            answer_type=answer_type,
            primary_evidence=primary,
            supporting_evidence=supporting,
            current_market_evidence=market,
            event_evidence=events,
            technical_evidence=technical,
            source_requirements=self._source_requirements(plan_dict),
            required_evidence_roles=required_roles,
            freshness_summary={item.evidence_id: item.freshness_status for item in all_items},
            depth_plan=depth_plan,
            coverage_requirements=coverage_requirements,
            evidence_dispositions=dispositions,
        )
        metadata_rejected = len([item for item in raw_items if item.is_metadata_only])
        redundant_rejected = len([item for item in dispositions if item.get("status") == "DEDUPLICATED_WITH_REASON"])
        
        # Evaluate Sufficiency and Coverage
        bundle.sufficiency = EvidenceSufficiencyEvaluator.evaluate(bundle)
        bundle.coverage_result = EvidenceCoverageEvaluator.evaluate(bundle, coverage_requirements, phase)
        
        if metadata_rejected:
            warning = "metadata_only_evidence_rejected"
            if warning not in bundle.warnings:
                bundle.warnings.append(warning)
            if bundle.sufficiency and warning not in bundle.sufficiency.warnings:
                bundle.sufficiency.warnings.append(warning)
        bundle.missing_evidence_roles = list(bundle.sufficiency.missing_roles)
        bundle.evidence_coverage = bundle.coverage_result.coverage_ratio
        bundle.confidence_ceiling = bundle.sufficiency.confidence_ceiling
        bundle.evidence_quality = bundle.sufficiency.status
        bundle.warnings.extend(bundle.sufficiency.warnings)
        bundle.warnings.extend(bundle.coverage_result.warnings)
        print(
            "[EvidenceSelection] "
            f"task_id={effective_task_id} input_items={len(all_items)} "
            f"selected_primary={len(bundle.primary_evidence)} "
            f"selected_supporting={len(bundle.supporting_evidence)} "
            f"metadata_only_rejected={metadata_rejected} "
            f"redundant_rejected={redundant_rejected}"
        )
        for disposition in dispositions[:12]:
            print(
                "[EvidenceDisposition] "
                f"task_id={effective_task_id} evidence_id={disposition.get('evidence_id')} "
                f"status={disposition.get('status')} reason={disposition.get('reason')} "
                f"source={disposition.get('source_title')}"
            )
        for item in bundle.all_items[:8]:
            print(
                "[EvidenceItem] "
                f"evidence_id={item.evidence_id} type={item.evidence_type} "
                f"source={item.source_title or item.source_organization or item.symbol} "
                f"directness={item.directness_score:.2f} "
                f"usefulness={item.passage_usefulness_score:.2f} "
                f"metadata_only={str(item.is_metadata_only).lower()}"
            )
        print(f"[EvidenceBundle] task_id={effective_task_id} items={len(bundle.all_items)}")
        return bundle

    @classmethod
    def required_roles(cls, primary_intent: str, answer_type: str) -> List[str]:
        if primary_intent == "book_concept_explanation" or answer_type == "static_explanation":
            return ["direct_book_passage"]
        if primary_intent == "macro_report_summary" or answer_type == "report_summary":
            return ["official_report"]
        if primary_intent == "macro_market_impact" or answer_type == "scenario_analysis":
            return ["official_report", "economic_event", "market_snapshot"]
        if primary_intent == "market_state_analysis" or answer_type == "market_analysis":
            return ["market_snapshot", "ohlcv"]
        return ["knowledge_or_data"]

    def _items_from_results(self, task_id: str, results: List[Any], query_terms: List[str]) -> List[EvidenceItem]:
        output: List[EvidenceItem] = []
        for result in results:
            capability = str(_get(result, "capability", ""))
            if capability in self.KNOWLEDGE_CAPABILITIES:
                output.extend(self._knowledge_items(task_id, result, query_terms))
            elif capability == "economic_event":
                output.append(self._event_item(task_id, result))
            elif capability == "market_snapshot":
                output.append(self._market_item(task_id, result))
            elif capability == "ohlcv":
                output.append(self._ohlcv_item(task_id, result))
            elif capability == "technical_snapshot":
                output.append(self._technical_item(task_id, result))
        return output

    def _knowledge_items(self, task_id: str, result: Any, query_terms: List[str]) -> List[EvidenceItem]:
        data = _data_from_result(result)
        docs = data if isinstance(data, list) else [data]
        output: List[EvidenceItem] = []
        for index, doc in enumerate([item for item in docs if isinstance(item, dict)]):
            metadata = _metadata(doc)
            content = _doc_content(doc)
            usefulness, metadata_only, warnings = EvidenceUsefulnessEvaluator.evaluate(content, metadata, query_terms)
            evidence_type = self._knowledge_evidence_type(str(_get(result, "capability", "")), metadata)
            title = metadata.get("title") or metadata.get("source") or doc.get("source") or _get(result, "source", "")
            author = metadata.get("author") or (_get(result, "provenance", {}) or {}).get("author", "")
            organization = metadata.get("organization") or (_get(result, "provenance", {}) or {}).get("organization", "")
            source_type = metadata.get("knowledge_type") or metadata.get("doc_type") or ("report" if evidence_type != "book_passage" else "book")
            semantic_relevance = self._semantic_relevance(content, query_terms)
            directness = max(usefulness, semantic_relevance)
            direct_threshold = 0.35 if evidence_type == "official_report_passage" else 0.55
            item = EvidenceItem(
                evidence_id=self._evidence_id(task_id, result, index, content),
                task_id=task_id,
                evidence_type=evidence_type,
                capability=str(_get(result, "capability", "")),
                target=str(_get(result, "target", "")),
                content=content,
                content_summary=_shorten(content),
                source_title=str(title or ""),
                source_author=str(author or ""),
                source_organization=str(organization or ""),
                source_type=str(source_type or ""),
                event_type=str(metadata.get("event_type") or ""),
                period=str(metadata.get("period") or metadata.get("published_date") or ""),
                source_timestamp=str(_get(result, "source_timestamp", "")),
                fetched_at=str(_get(result, "fetched_at", "")),
                freshness_status=str(_get(result, "freshness_status", "unknown")),
                semantic_relevance_score=semantic_relevance,
                passage_usefulness_score=usefulness,
                directness_score=directness,
                provenance_confidence=0.95 if title and (author or organization or metadata.get("event_type")) else 0.75,
                redundancy_group=str(metadata.get("parent_chunk_id") or metadata.get("chunk_id") or hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:12]),
                is_metadata_only=metadata_only,
                is_direct_evidence=usefulness >= direct_threshold and not metadata_only,
                is_supporting_evidence=usefulness >= 0.35 and not metadata_only,
                claim_topics=list(query_terms[:8]),
                warnings=warnings,
                raw=doc,
            )
            output.append(item)
        return output

    @staticmethod
    def _knowledge_evidence_type(capability: str, metadata: Dict[str, Any]) -> str:
        knowledge_type = _normalize(metadata.get("knowledge_type") or metadata.get("doc_type") or "")
        if capability == "official_report" or "report" in knowledge_type:
            return "official_report_passage"
        if capability == "market_knowledge":
            return "market_commentary_passage"
        return "book_passage"

    def _event_item(self, task_id: str, result: Any) -> EvidenceItem:
        data = _as_dict(_data_from_result(result))
        content = (
            f"event_name={data.get('event_name') or _get(result, 'target', '')}; "
            f"country={data.get('country', '')}; actual={data.get('actual')}; "
            f"forecast={data.get('forecast')}; previous={data.get('previous')}; "
            f"surprise={data.get('surprise')}; release_time={data.get('release_time', '')}; "
            f"status={data.get('status', '')}"
        )
        return EvidenceItem(
            evidence_id=self._evidence_id(task_id, result, 0, content),
            task_id=task_id,
            evidence_type="economic_event_record",
            capability="economic_event",
            target=str(_get(result, "target", "")),
            content=content,
            content_summary=content,
            source_organization=str(data.get("source") or _get(result, "source", "existing_api")),
            event_type=str(_get(result, "target", "")),
            source_timestamp=str(data.get("release_time") or _get(result, "source_timestamp", "")),
            fetched_at=str(_get(result, "fetched_at", "")),
            freshness_status=str(_get(result, "freshness_status", "unknown")),
            semantic_relevance_score=0.9,
            passage_usefulness_score=0.85,
            directness_score=0.9,
            provenance_confidence=0.85,
            is_direct_evidence=True,
            is_current_data=True,
            claim_topics=["economic_event", str(_get(result, "target", ""))],
            raw=data,
        )

    def _market_item(self, task_id: str, result: Any) -> EvidenceItem:
        data = _as_dict(_data_from_result(result))
        symbol = str(data.get("symbol") or _get(result, "target", ""))
        content = (
            f"MarketSnapshot {symbol}: "
            f"symbol={symbol}; "
            f"price={data.get('latest_price')}; timeframe={data.get('timeframe', '')}; "
            f"trend={data.get('recent_trend', '')}; volatility={data.get('volatility_note', '')}; "
            f"timestamp={data.get('timestamp') or _get(result, 'source_timestamp', '')}; "
            f"source={data.get('source') or _get(result, 'source', 'existing_api')}"
        )
        freshness = str(_get(result, "freshness_status", "unknown"))
        return EvidenceItem(
            evidence_id=self._evidence_id(task_id, result, 0, content),
            task_id=task_id,
            evidence_type="market_snapshot",
            capability="market_snapshot",
            target=str(_get(result, "target", "")),
            content=content,
            content_summary=content,
            symbol=symbol,
            timeframe=str(data.get("timeframe") or ""),
            source_timestamp=str(data.get("timestamp") or _get(result, "source_timestamp", "")),
            fetched_at=str(_get(result, "fetched_at", "")),
            freshness_status=freshness,
            semantic_relevance_score=0.9,
            passage_usefulness_score=0.8 if freshness != "stale" else 0.25,
            directness_score=0.9 if freshness != "stale" else 0.3,
            provenance_confidence=0.85,
            is_direct_evidence=freshness != "stale",
            is_current_data=True,
            claim_topics=["market_price", str(_get(result, "target", ""))],
            raw=data,
            warnings=["stale_market_snapshot"] if freshness == "stale" else [],
        )

    def _ohlcv_item(self, task_id: str, result: Any) -> EvidenceItem:
        data = _data_from_result(result)
        candles = data if isinstance(data, list) else []
        latest = candles[-1] if candles and isinstance(candles[-1], dict) else {}
        symbol = str(_get(result, "target", ""))
        behavior = self._ohlcv_behavior_summary(candles)
        behavior_text = ""
        if behavior:
            behavior_text = (
                f"; first_close={behavior.get('first_close', '')}; "
                f"last_close={behavior.get('last_close', '')}; "
                f"direction={behavior.get('direction', '')}; "
                f"change_pct={behavior.get('change_pct', '')}; "
                f"range_pct={behavior.get('range_pct', '')}"
            )
        content = (
            f"OHLCV {symbol}: "
            f"symbol={symbol}; candles={len(candles)}; "
            f"latest_timestamp={latest.get('timestamp', '')}; "
            f"latest_close={latest.get('close', '')}; timeframe={(_get(result, 'normalized_parameters', {}) or {}).get('timeframe', '')}"
            f"{behavior_text}"
        )
        freshness = str(_get(result, "freshness_status", "unknown"))
        usefulness = 0.75 if freshness != "stale" and candles else 0.25
        directness = 0.8 if freshness != "stale" and candles else 0.25
        if not behavior and len(candles) <= 1:
            usefulness = min(usefulness, 0.45)
            directness = min(directness, 0.45)
        return EvidenceItem(
            evidence_id=self._evidence_id(task_id, result, 0, content),
            task_id=task_id,
            evidence_type="ohlcv_summary",
            capability="ohlcv",
            target=str(_get(result, "target", "")),
            content=content,
            content_summary=content,
            symbol=symbol,
            timeframe=str((_get(result, "normalized_parameters", {}) or {}).get("timeframe", "")),
            source_timestamp=str(latest.get("timestamp", "") or _get(result, "source_timestamp", "")),
            fetched_at=str(_get(result, "fetched_at", "")),
            freshness_status=freshness,
            semantic_relevance_score=0.8,
            passage_usefulness_score=usefulness,
            directness_score=directness,
            provenance_confidence=0.8,
            is_direct_evidence=bool(candles) and freshness != "stale",
            is_current_data=True,
            claim_topics=["ohlcv", str(_get(result, "target", ""))],
            raw={"candles": candles[:3], "count": len(candles), "behavior": behavior},
        )

    def _technical_item(self, task_id: str, result: Any) -> EvidenceItem:
        data = _as_dict(_data_from_result(result))
        content = f"technical_snapshot={data}"
        return EvidenceItem(
            evidence_id=self._evidence_id(task_id, result, 0, content),
            task_id=task_id,
            evidence_type="technical_snapshot",
            capability="technical_snapshot",
            target=str(_get(result, "target", "")),
            content=content,
            content_summary=_shorten(content),
            symbol=str(_get(result, "target", "")),
            source_timestamp=str(_get(result, "source_timestamp", "")),
            fetched_at=str(_get(result, "fetched_at", "")),
            freshness_status=str(_get(result, "freshness_status", "unknown")),
            semantic_relevance_score=0.75,
            passage_usefulness_score=0.7,
            directness_score=0.75,
            provenance_confidence=0.75,
            is_direct_evidence=True,
            is_current_data=True,
            claim_topics=["technical_snapshot"],
            raw=data,
        )

    @staticmethod
    def _ohlcv_behavior_summary(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(candles, list) or len(candles) < 2:
            return {}
        first = candles[0] if isinstance(candles[0], dict) else {}
        latest = candles[-1] if isinstance(candles[-1], dict) else {}
        try:
            first_close = float(first.get("close"))
            last_close = float(latest.get("close"))
        except (TypeError, ValueError):
            first_close = last_close = None
        highs = []
        lows = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            try:
                highs.append(float(candle.get("high")))
                lows.append(float(candle.get("low")))
            except (TypeError, ValueError):
                continue
        summary: Dict[str, Any] = {
            "count": len(candles),
            "first_timestamp": first.get("timestamp", ""),
            "last_timestamp": latest.get("timestamp", ""),
        }
        if first_close is not None and last_close is not None:
            change_pct = ((last_close - first_close) / first_close * 100.0) if first_close else 0.0
            direction = "up" if change_pct > 0.05 else ("down" if change_pct < -0.05 else "flat")
            summary.update(
                {
                    "first_close": round(first_close, 5),
                    "last_close": round(last_close, 5),
                    "change_pct": round(change_pct, 3),
                    "direction": direction,
                }
            )
        if highs and lows:
            high = max(highs)
            low = min(lows)
            reference = last_close or high or 1.0
            range_pct = ((high - low) / reference * 100.0) if reference else 0.0
            summary.update({"high": round(high, 5), "low": round(low, 5), "range_pct": round(range_pct, 3)})
        return summary

    @staticmethod
    def _semantic_relevance(content: str, query_terms: List[str]) -> float:
        if not query_terms:
            return 0.5
        hits = sum(1 for term in query_terms if _normalize(term) and _normalize(term) in _normalize(content))
        return min(1.0, 0.35 + hits * 0.12)

    @staticmethod
    def _dedupe(items: List[EvidenceItem]) -> List[EvidenceItem]:
        best_by_group: Dict[str, EvidenceItem] = {}
        order: List[str] = []
        for item in items:
            key = item.redundancy_group or item.evidence_id
            existing = best_by_group.get(key)
            if existing is None:
                best_by_group[key] = item
                order.append(key)
            elif item.directness_score > existing.directness_score:
                best_by_group[key] = item
        return [best_by_group[key] for key in order]

    @classmethod
    def _dedupe_with_dispositions(cls, items: List[EvidenceItem]) -> Tuple[List[EvidenceItem], List[Dict[str, Any]]]:
        best_by_group: Dict[str, EvidenceItem] = {}
        order: List[str] = []
        for item in items:
            key = item.redundancy_group or item.evidence_id
            existing = best_by_group.get(key)
            if existing is None:
                best_by_group[key] = item
                order.append(key)
            elif item.directness_score > existing.directness_score:
                best_by_group[key] = item

        dispositions: List[Dict[str, Any]] = []
        for item in items:
            key = item.redundancy_group or item.evidence_id
            kept = best_by_group.get(key)
            if kept and kept.evidence_id != item.evidence_id:
                status = "DEDUPLICATED_WITH_REASON"
                reason = f"redundancy_group:{key}; kept={kept.evidence_id}"
            elif item.is_metadata_only:
                status = "REJECTED_WITH_REASON"
                reason = "metadata_only"
            elif not cls._effective_item_usable(item):
                status = "REJECTED_WITH_REASON"
                reason = ";".join(item.warnings or ["not_direct_or_supporting_evidence"])
            else:
                status = "USED"
                reason = "effective_evidence"

            metadata = item.raw.get("metadata", {}) if isinstance(item.raw, dict) else {}
            dispositions.append(
                {
                    "evidence_id": item.evidence_id,
                    "status": status,
                    "reason": reason,
                    "redundancy_group": key,
                    "kept_evidence_id": kept.evidence_id if kept else "",
                    "chunk_id": metadata.get("chunk_id") or item.raw.get("chunk_id", "") if isinstance(item.raw, dict) else "",
                    "parent_chunk_id": metadata.get("parent_chunk_id", "") if isinstance(metadata, dict) else "",
                    "source_title": item.source_title or item.source_organization or item.symbol,
                    "evidence_type": item.evidence_type,
                }
            )

        return [best_by_group[key] for key in order], dispositions

    @classmethod
    def _effective_item_usable(cls, item: EvidenceItem) -> bool:
        if item.is_metadata_only:
            return False
        if item.capability in cls.KNOWLEDGE_CAPABILITIES:
            return bool(item.is_direct_evidence or item.is_supporting_evidence)
        return True

    @staticmethod
    def _evidence_id(task_id: str, result: Any, index: int, content: str) -> str:
        seed = f"{task_id}|{_result_id(result)}|{index}|{content[:80]}"
        return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:12]

    @staticmethod
    def _query_terms(plan_dict: Dict[str, Any], query: str) -> List[str]:
        entities = plan_dict.get("entities") or {}
        terms: List[str] = []
        for key in ("symbols", "macro_events", "organizations", "authors", "books", "concepts", "strategies"):
            value = entities.get(key, [])
            terms.extend([str(item).replace("_", " ") for item in value or []])
        terms.extend([word for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", str(query or ""))[:8]])
        output: List[str] = []
        for term in terms:
            if term and _normalize(term) not in {_normalize(item) for item in output}:
                output.append(term)
        return output

    @staticmethod
    def _source_requirements(plan_dict: Dict[str, Any]) -> List[str]:
        entities = plan_dict.get("entities") or {}
        requirements = []
        for key in ("authors", "books", "organizations", "macro_events"):
            for value in entities.get(key, []) or []:
                requirements.append(str(value))
        return requirements

    @staticmethod
    def _apply_plan_provenance_constraints(items: List[EvidenceItem], plan_dict: Dict[str, Any]) -> None:
        entities = plan_dict.get("entities") or {}
        author_terms = [str(item) for item in entities.get("authors", []) or []]
        book_terms = [str(item) for item in entities.get("books", []) or []]
        org_terms = [str(item) for item in entities.get("organizations", []) or []]
        event_terms = [str(item) for item in entities.get("macro_events", []) or []]
        for item in items:
            if item.capability not in EvidenceSelector.KNOWLEDGE_CAPABILITIES:
                continue
            haystack = " ".join(
                [
                    item.source_title,
                    item.source_author,
                    item.source_organization,
                    item.event_type,
                    item.content[:500],
                ]
            )
            if author_terms or book_terms:
                if not (_contains_any(haystack, author_terms) or _contains_any(haystack, book_terms)):
                    item.is_direct_evidence = False
                    item.is_supporting_evidence = False
                    item.provenance_confidence = min(item.provenance_confidence, 0.2)
                    item.warnings.append("plan_provenance_mismatch")
            if org_terms and item.evidence_type == "official_report_passage":
                if not _contains_any(haystack, org_terms):
                    item.is_direct_evidence = False
                    item.is_supporting_evidence = False
                    item.provenance_confidence = min(item.provenance_confidence, 0.2)
                    item.warnings.append("organization_mismatch")
            if event_terms and item.evidence_type == "official_report_passage":
                if not (_contains_any(haystack, event_terms) or _contains_any(item.event_type, event_terms)):
                    item.is_direct_evidence = False
                    item.is_supporting_evidence = False
                    item.provenance_confidence = min(item.provenance_confidence, 0.2)
                    item.warnings.append("event_type_mismatch")

    @staticmethod
    def _task_plan_dict(query_plan: Any, task_dict: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        if task_dict.get("query_plan"):
            return dict(task_dict["query_plan"])
        plan_dict = query_plan.as_dict() if hasattr(query_plan, "as_dict") else _as_dict(query_plan)
        if task_id and plan_dict.get("child_plans"):
            for child in plan_dict.get("child_plans", []):
                if isinstance(child, dict) and child.get("task_id") == task_id:
                    return dict(child)
        return plan_dict

    @staticmethod
    def _relevant_results(task_id: str, results: List[Any], task_dict: Dict[str, Any]) -> List[Any]:
        if task_id:
            relevant = [
                result
                for result in results or []
                if task_id in (_get(result, "requested_by_tasks", []) or _get(result, "task_ids", []) or [])
            ]
            if relevant:
                return relevant
        if task_dict:
            by_id = {
                str(item.get("result_id") or f"{item.get('capability')}:{item.get('target')}")
                for item in list(task_dict.get("required_context_results") or []) + list(task_dict.get("optional_context_results") or [])
                if isinstance(item, dict)
            }
            if by_id:
                return [result for result in results or [] if _result_id(result) in by_id]
        return list(results or [])


class EvidenceSufficiencyEvaluator:
    @classmethod
    def evaluate(cls, bundle: EvidenceBundle) -> EvidenceSufficiencyResult:
        roles = list(bundle.required_evidence_roles)
        missing = [role for role in roles if not cls._role_satisfied(role, bundle)]
        warnings = []
        if any(item.is_metadata_only for item in bundle.all_items):
            warnings.append("metadata_only_evidence_rejected")
        if missing:
            status = "INSUFFICIENT" if any(role in cls._hard_required_roles(bundle) for role in missing) else "DEGRADED"
            score = max(0.0, (len(roles) - len(missing)) / max(len(roles), 1))
            confidence = "low" if status == "INSUFFICIENT" else "medium"
        elif warnings:
            status = "DEGRADED"
            score = 0.75
            confidence = "medium"
        else:
            status = "COMPLETE"
            score = 1.0
            confidence = "high"
        print(
            "[EvidenceSufficiency] "
            f"task_id={bundle.task_id} status={status} "
            f"required_roles={roles} missing_roles={missing}"
        )
        return EvidenceSufficiencyResult(status, score, confidence, roles, missing, warnings)

    @staticmethod
    def _hard_required_roles(bundle: EvidenceBundle) -> List[str]:
        return list(bundle.required_evidence_roles)

    @staticmethod
    def _role_satisfied(role: str, bundle: EvidenceBundle) -> bool:
        if role == "direct_book_passage":
            return any(item.evidence_type == "book_passage" and item.is_direct_evidence and not item.is_metadata_only for item in bundle.primary_evidence)
        if role == "official_report":
            return any(item.evidence_type == "official_report_passage" and item.is_direct_evidence and not item.is_metadata_only for item in bundle.primary_evidence + bundle.supporting_evidence)
        if role == "economic_event":
            return any(item.evidence_type == "economic_event_record" and item.is_direct_evidence for item in bundle.event_evidence)
        if role == "market_snapshot":
            return any(item.evidence_type == "market_snapshot" and item.is_direct_evidence and item.freshness_status != "stale" for item in bundle.current_market_evidence)
        if role == "ohlcv":
            return any(item.evidence_type == "ohlcv_summary" and item.is_direct_evidence and item.freshness_status != "stale" for item in bundle.technical_evidence)
        if role == "knowledge_or_data":
            return bool(bundle.primary_evidence or bundle.current_market_evidence or bundle.event_evidence)
        return False


class AnswerContractBuilder:
    def build(self, bundle: EvidenceBundle, context_sufficiency: str = "COMPLETE") -> AnswerContract:
        primary_intent = str((bundle.query_plan or {}).get("primary_intent") or "")
        answer_type = bundle.answer_type
        
        req_sections = ["source_used"]
        limitations = list(bundle.missing_evidence_roles)
        if bundle.coverage_result and bundle.coverage_result.missing_required_topics:
            limitations.extend(bundle.coverage_result.missing_required_topics)
            
        if bundle.coverage_requirements:
            req_sections.extend([r.topic_role for r in bundle.coverage_requirements.required_topics])
        req_sections.append("short_conclusion")
        
        # Deduplicate while preserving order
        seen = set()
        req_sections = [x for x in req_sections if not (x in seen or seen.add(x))]

        if primary_intent == "book_concept_explanation" or answer_type == "static_explanation":
            contract = AnswerContract(
                task_id=bundle.task_id,
                answer_type=answer_type,
                allowed_claim_types=["source_backed_concept_summary", "careful_interpretation"],
                required_sections=req_sections,
                required_evidence_roles=["direct_book_passage"],
                required_source_refs=self._source_refs(bundle),
                prohibited_claim_types=["title_only_inference", "unsupported_author_attribution", "market_call", "generic_filler", "repeated_paraphrase", "claims_beyond_evidence_coverage"],
                confidence_ceiling=bundle.confidence_ceiling,
                limitations=limitations,
            )
        elif primary_intent == "macro_market_impact" or answer_type == "scenario_analysis":
            contract = AnswerContract(
                task_id=bundle.task_id,
                answer_type=answer_type,
                allowed_claim_types=["report_summary", "event_data_summary", "market_state", "scenario"],
                required_sections=req_sections,
                required_evidence_roles=["official_report", "economic_event", "market_snapshot"],
                required_source_refs=self._source_refs(bundle),
                prohibited_claim_types=["guaranteed_profit", "current_claim_without_market_snapshot", "event_number_without_event_evidence", "generic_filler", "claims_beyond_evidence_coverage"],
                confidence_ceiling=bundle.confidence_ceiling,
                limitations=limitations,
            )
        elif primary_intent == "market_state_analysis" or answer_type == "market_analysis":
            contract = AnswerContract(
                task_id=bundle.task_id,
                answer_type=answer_type,
                allowed_claim_types=["market_snapshot_summary", "ohlcv_summary", "technical_summary"],
                required_sections=req_sections,
                required_evidence_roles=["market_snapshot", "ohlcv"],
                required_source_refs=self._source_refs(bundle),
                prohibited_claim_types=["current_claim_without_market_snapshot", "guaranteed_profit", "generic_filler"],
                confidence_ceiling=bundle.confidence_ceiling,
                limitations=limitations,
            )
        else:
            contract = AnswerContract(
                task_id=bundle.task_id,
                answer_type=answer_type,
                allowed_claim_types=["supported_summary"],
                required_sections=req_sections,
                required_evidence_roles=list(bundle.required_evidence_roles),
                required_source_refs=self._source_refs(bundle),
                prohibited_claim_types=["unsupported_claim", "generic_filler", "claims_beyond_evidence_coverage"],
                confidence_ceiling=bundle.confidence_ceiling,
                limitations=limitations,
            )
            
        if bundle.coverage_requirements:
            from src.services.evidence.topic_evidence_binding import TopicEvidenceBindingBuilder
            binding_set, synthesis_plan = TopicEvidenceBindingBuilder.build(bundle, bundle.coverage_requirements)
            contract.topic_bindings = binding_set.bindings
            contract.synthesis_coverage_plan = synthesis_plan
            
        print(f"[AnswerContract] task_id={contract.task_id} answer_type={contract.answer_type} required_sections={contract.required_sections} required_sources={contract.required_source_refs} confidence_ceiling={contract.confidence_ceiling}")
        return contract

    @staticmethod
    def _source_refs(bundle: EvidenceBundle) -> List[str]:
        refs = []
        for item in bundle.primary_evidence + bundle.supporting_evidence:
            title = item.source_title
            owner = item.source_author or item.source_organization
            ref = f"{title} - {owner}" if title and owner else title
            if ref and ref not in refs:
                refs.append(ref)
        return refs


class EvidencePromptAssembler:
    MAX_EVIDENCE_ITEMS_PER_TOPIC = 2
    MAX_TOTAL_EVIDENCE_ITEMS = 6

    def assemble(self, bundles: List[EvidenceBundle], contracts: List[AnswerContract], user_query: str, context_sufficiency: str = "COMPLETE") -> str:
        lines = [
            "SYSTEM RESPONSE CONTRACT",
            "- Use only the structured evidence below for source-attributed claims.",
            "- Do not infer an author's view from title or metadata alone.",
            "- Distinguish source metadata from source content.",
            "- If evidence is degraded, surface the limitation.",
            "",
            f"TASK: {user_query}",
            f"CONTEXT QUALITY: context_sufficiency={context_sufficiency}",
            "",
        ]
        for bundle, contract in zip(bundles, contracts):
            lines.extend(self._bundle_lines(bundle, contract))
        lines.extend(
            [
                "REQUIRED RESPONSE STRUCTURE",
                "- Answer directly in Vietnamese.",
                "- Attribute claims to compatible evidence IDs/sources naturally.",
                "- End with 'Ket luan ngan:' or 'Kết luận ngắn:'.",
                "",
                "PROHIBITED CLAIMS",
                "- No guaranteed profit.",
                "- No current price/event numeric claim without corresponding structured evidence.",
                "- No source title-only inference.",
            ]
        )
        prompt = "\n".join(lines)
        print(
            "[PromptAssembler] "
            f"bundles={len(bundles)} chars={len(prompt)} "
            f"primary_items={sum(len(bundle.primary_evidence) for bundle in bundles)}"
        )
        return prompt

    def _bundle_lines(self, bundle: EvidenceBundle, contract: AnswerContract) -> List[str]:
        lines = [
            f"TASK_CONTEXT task_id={bundle.task_id}",
            f"QUESTION: {bundle.query}",
            f"ANSWER TYPE: {bundle.answer_type}",
            f"DETAIL LEVEL: {bundle.depth_plan.detail_level if bundle.depth_plan else 'standard'}",
            f"COVERAGE STATUS: {bundle.coverage_result.status if bundle.coverage_result else 'UNKNOWN'}",
            f"MISSING TOPICS: {', '.join(bundle.coverage_result.missing_required_topics) if bundle.coverage_result and bundle.coverage_result.missing_required_topics else 'none'}",
            f"EVIDENCE QUALITY: {bundle.evidence_quality} coverage={bundle.evidence_coverage:.2f} confidence_ceiling={bundle.confidence_ceiling}",
            f"REQUIRED EVIDENCE ROLES: {', '.join(bundle.required_evidence_roles)}",
            f"MISSING OR DEGRADED EVIDENCE: {', '.join(bundle.missing_evidence_roles or bundle.warnings) or 'none'}",
            f"REQUIRED SECTIONS: {', '.join(contract.required_sections)}",
            f"PROHIBITED CLAIM TYPES: {', '.join(contract.prohibited_claim_types)}",
            "",
        ]
        # New Topic-Bound Assembly logic
        if getattr(contract, "topic_bindings", None) and getattr(contract, "synthesis_coverage_plan", None):
            lines.append("PRIMARY EVIDENCE")
            lines.append("EVIDENCE REPOSITORY")
            # De-duplicate evidence items to preserve prompt budget
            unique_items = []
            seen_ids = set()
            for item in bundle.all_items:
                if item.evidence_id not in seen_ids:
                    unique_items.append(item)
                    seen_ids.add(item.evidence_id)
            lines.extend(self._items_lines(self._budget_items_by_topic(bundle, contract, unique_items)))
            
            lines.append("")
            lines.append("TOPIC-SPECIFIC INSTRUCTIONS")
            plan = contract.synthesis_coverage_plan
            bindings_by_topic = {b.topic_role: b for b in contract.topic_bindings}
            
            for topic in getattr(plan, "required_output_order", []):
                lines.append(f"TOPIC: {topic}")
                binding = bindings_by_topic.get(topic)
                if binding:
                    lines.append(f"Goal: {binding.topic_description}")
                    if binding.primary_evidence_ids:
                        lines.append(f"Primary evidence IDs: {', '.join(binding.primary_evidence_ids)}")
                    if binding.supporting_evidence_ids:
                        lines.append(f"Supporting evidence IDs: {', '.join(binding.supporting_evidence_ids)}")
                    
                    if binding.binding_confidence == "high":
                        lines.append("Instruction: Provide a clear direct explanation using the bound evidence.")
                    else:
                        if binding.topic_support_score >= 0.45:
                            lines.append("Instruction: Provide a standard explanation using the provided evidence.")
                        else:
                            lines.append("Instruction: Explain only the contextual conditions directly supported by these passages. If the passages do not establish broader rules, state that limitation explicitly. Do not infer unless supported.")
                else:
                    lines.append("Goal: Explain this topic.")
                    lines.append("Instruction: No direct evidence is available for this topic. Be concise or surface as a limitation. Do not invent facts.")
                lines.append("")
        else:
            # Fallback for old tests or lack of bindings
            lines.append("PRIMARY EVIDENCE")
            lines.extend(self._items_lines(self._budget_items_by_topic(bundle, contract, bundle.primary_evidence)))
            lines.append("SUPPORTING EVIDENCE")
            lines.extend(self._items_lines(self._budget_items_by_topic(bundle, contract, bundle.supporting_evidence)))
            lines.append("CURRENT EVENT DATA")
            lines.extend(self._items_lines(bundle.event_evidence))
            lines.append("CURRENT MARKET DATA")
            lines.extend(self._items_lines(bundle.current_market_evidence))
            lines.append("TECHNICAL EVIDENCE")
            lines.extend(self._items_lines(bundle.technical_evidence))
            
        lines.append("")
        return lines

    def _budget_items_by_topic(
        self,
        bundle: EvidenceBundle,
        contract: AnswerContract,
        items: List[EvidenceItem],
    ) -> List[EvidenceItem]:
        unique_items: List[EvidenceItem] = []
        seen_ids = set()
        for item in items or []:
            if item.evidence_id in seen_ids:
                continue
            unique_items.append(item)
            seen_ids.add(item.evidence_id)

        coverage = getattr(bundle, "coverage_result", None)
        evidence_by_topic = getattr(coverage, "evidence_by_topic", None) or {}
        if not evidence_by_topic:
            return unique_items[: self.MAX_TOTAL_EVIDENCE_ITEMS]

        by_id = {item.evidence_id: item for item in unique_items}
        mapped_ids = {
            evidence_id
            for evidence_ids in evidence_by_topic.values()
            for evidence_id in (evidence_ids or [])
        }
        selected: List[EvidenceItem] = []
        selected_ids = set()
        topic_order = list(contract.required_sections or [])
        topic_order.extend(topic for topic in evidence_by_topic if topic not in topic_order)

        for topic in topic_order:
            topic_count = 0
            for evidence_id in evidence_by_topic.get(topic, []) or []:
                item = by_id.get(evidence_id)
                if item is None or evidence_id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(evidence_id)
                topic_count += 1
                if len(selected) >= self.MAX_TOTAL_EVIDENCE_ITEMS:
                    return selected
                if topic_count >= self.MAX_EVIDENCE_ITEMS_PER_TOPIC:
                    break

        for item in unique_items:
            if item.evidence_id in selected_ids or item.evidence_id in mapped_ids:
                continue
            selected.append(item)
            if len(selected) >= self.MAX_TOTAL_EVIDENCE_ITEMS:
                break
        return selected

    @staticmethod
    def _items_lines(items: List[EvidenceItem]) -> List[str]:
        if not items:
            return ["- none"]
        lines = []
        for item in items:
            owner = item.source_author or item.source_organization
            topics = getattr(item, "covered_topics", [])
            lines.extend(
                [
                    f"- Evidence ID: {item.evidence_id}",
                    f"  Role: {item.evidence_type}",
                    f"  Source: {item.source_title or item.symbol or item.target}",
                    f"  Author/Organization: {owner}",
                    f"  Event/Period/Timestamp: {item.event_type or item.period or item.source_timestamp}",
                    f"  Freshness: {item.freshness_status}",
                    f"  Metadata only: {str(item.is_metadata_only).lower()}",
                    f"  Topics: {', '.join(topics)}",
                    f"  Content: {item.content_summary}",
                ]
            )
        return lines


class ClaimEvidenceValidator:
    def validate(self, answer: str, bundles: List[EvidenceBundle], contracts: List[AnswerContract]) -> ClaimValidationResult:
        text = str(answer or "")
        violations: List[str] = []
        warnings: List[ClaimValidationWarning] = []
        groups: List[str] = []
        unsupported: List[str] = []
        all_items = [item for bundle in bundles for item in bundle.all_items]
        source_text = " ".join(
            " ".join([item.source_title, item.source_author, item.source_organization, item.content])
            for item in all_items
        )
        for contract in contracts:
            if "direct_book_passage" in contract.required_evidence_roles:
                if not any(item.evidence_type == "book_passage" and item.is_direct_evidence for item in all_items):
                    violations.append("author_attribution_without_direct_book_evidence")
                    unsupported.append("book_author_claims")
            if "official_report" in contract.required_evidence_roles:
                if not any(item.evidence_type == "official_report_passage" and item.is_direct_evidence for item in all_items):
                    violations.append("report_attribution_without_report_evidence")
                    unsupported.append("official_report_claims")
            if "market_snapshot" in contract.required_evidence_roles:
                if not any(item.evidence_type == "market_snapshot" and item.is_direct_evidence for item in all_items):
                    violations.append("current_market_claim_without_market_snapshot")
                    unsupported.append("current_market_claims")
        
        if re.search(r"\b\d+(?:\.\d+)?\b", text) and not any(item.evidence_type in {"economic_event_record", "market_snapshot", "official_report_passage"} for item in all_items):
            warnings.append(ClaimValidationWarning(
                warning_code="numeric_claim_without_numeric_evidence",
                reason="numeric claim without numeric evidence",
                severity="NON_BLOCKING_WARN"
            ))
        if _contains_any(text, ["hien tai", "current", "luc nay", "bay gio"]) and not any(item.is_current_data and item.freshness_status != "stale" for item in all_items):
            warnings.append(ClaimValidationWarning(
                warning_code="current_language_without_current_evidence",
                reason="current language without current evidence",
                severity="CONTRACT_DEGRADING_WARN"
            ))
        if source_text and any((item.source_title and _normalize(item.source_title) in _normalize(text)) for item in all_items):
            groups.append("source_reference")
            
        status = "FAIL" if violations else ("WARN" if warnings else "PASS")
        
        warning_codes = [w.warning_code for w in warnings]
        print(
            "[ClaimEvidenceValidation] "
            f"status={status} violations={len(violations)} warnings={len(warnings)} warning_codes={warning_codes}"
        )
        for w in warnings:
            print(f"[ClaimEvidenceWarning] claim_id={w.claim_id} code={w.warning_code} severity={w.severity} reason={w.reason} evidence_ids={w.evidence_ids}")
            
        return ClaimValidationResult(status, violations, warnings, groups, unsupported)


@dataclass
class EvidenceRefinementRequest:
    task_id: str
    original_query: str
    refined_query: str
    reason: str
    missing_topics: List[str] = field(default_factory=list)
    topic_descriptions: List[str] = field(default_factory=list)
    previous_evidence_ids: List[str] = field(default_factory=list)
    previous_chunk_ids: List[str] = field(default_factory=list)
    attempt: int = 1

class EvidenceRefinementPlanner:
    @staticmethod
    def should_refine(bundle: EvidenceBundle, attempt: int = 1) -> Optional[EvidenceRefinementRequest]:
        reason = ""
        missing_topics = []
        topic_descriptions = []
        
        # Check sufficiency issues first
        if bundle.sufficiency and bundle.sufficiency.status == "INSUFFICIENT":
            metadata_items = [item for item in bundle.all_items if item.is_metadata_only]
            metadata_rejected = "metadata_only_evidence_rejected" in set(bundle.warnings)
            no_primary = not bundle.primary_evidence
            missing_direct = any("passage" in str(r) or "official_report" in str(r) for r in bundle.sufficiency.missing_roles)
            low_usefulness = any(item.passage_usefulness_score is not None and item.passage_usefulness_score < 0.5 for item in bundle.all_items)
            
            if metadata_items or metadata_rejected:
                reason = "metadata_only_passages"
            elif low_usefulness:
                reason = "low_usefulness"
            elif no_primary:
                reason = "no_primary_evidence"
            elif missing_direct:
                reason = "missing_direct_evidence"
                
        # Check coverage issues next
        if not reason and bundle.coverage_result and bundle.coverage_result.refinement_recommended:
            reason = "missing_topic_coverage"
            missing_topics = list(bundle.coverage_result.missing_required_topics)
            if bundle.coverage_requirements:
                # Find the corresponding CoverageRequirement objects to extract retrieval_descriptors
                for topic in missing_topics:
                    for req in bundle.coverage_requirements.required_topics + bundle.coverage_requirements.optional_topics:
                        if req.topic_role == topic and hasattr(req, "retrieval_descriptors") and req.retrieval_descriptors:
                            topic_descriptions.extend(req.retrieval_descriptors)
            
        if not reason:
            return None
            
        # Build query override if needed using semantic topic descriptions instead of raw ontology labels
        original_query = bundle.query or ""
        refined_query = original_query
        
        # Hardcode semantic map to guarantee descriptors are found even if bundle.coverage_requirements is mangled
        semantic_map = {
            "methodology_or_process": ["how the method is applied", "analysis process", "decision sequence", "practical rules"],
            "core_concept": ["core concept", "definition", "how it works"],
            "context_or_conditions": ["market environment", "context", "conditions", "when the approach applies"],
            "practical_application": ["practical application", "trading setup", "entry rules"],
            "limitations": ["risks", "limitations"],
            "main_ideas": ["main ideas", "core concepts"],
            "supporting_details": ["supporting details", "context"]
        }
        
        if missing_topics:
            for topic in missing_topics:
                if topic in semantic_map:
                    # Only append if not already in topic_descriptions to avoid duplication
                    for desc in semantic_map[topic]:
                        if desc not in topic_descriptions:
                            topic_descriptions.append(desc)
        
        if topic_descriptions:
            refined_query = f"{original_query} {' '.join(topic_descriptions)}"
        elif missing_topics:
            # Fallback if no descriptions are found
            refined_query = f"{original_query} {' '.join(missing_topics).replace('_', ' ')}"
            
        # Gather previous IDs to penalize or exclude in the next retrieval round
        previous_evidence_ids = [item.evidence_id for item in bundle.all_items]
        previous_chunk_ids = []
        for item in bundle.all_items:
            chunk_id = item.raw.get("metadata", {}).get("chunk_id") if isinstance(item.raw, dict) else None
            if chunk_id:
                previous_chunk_ids.append(chunk_id)
            elif hasattr(item, "redundancy_group") and item.redundancy_group:
                previous_chunk_ids.append(item.redundancy_group)
            
        return EvidenceRefinementRequest(
            task_id=bundle.task_id,
            original_query=original_query,
            refined_query=refined_query,
            reason=reason,
            missing_topics=missing_topics,
            topic_descriptions=topic_descriptions,
            previous_evidence_ids=previous_evidence_ids,
            previous_chunk_ids=previous_chunk_ids,
            attempt=attempt
        )

    @staticmethod
    def log_refinement(request: EvidenceRefinementRequest, status: str) -> None:
        missing_str = f" missing_topics={request.missing_topics}" if request.missing_topics else ""
        query_str = ""
        if status == "start":
            query_str = f" original_query={request.original_query!r} refined_query={request.refined_query!r}"
        print(
            "[EvidenceRefinement] "
            f"task_id={request.task_id} reason={request.reason}{missing_str} "
            f"attempt={request.attempt} status={status}{query_str}"
        )
