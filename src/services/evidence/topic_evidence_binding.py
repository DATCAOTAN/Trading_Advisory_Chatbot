from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

from src.services.evidence.evidence_pipeline import EvidenceBundle
from src.services.evidence.coverage_requirements import CoverageRequirementSet

@dataclass
class TopicEvidenceBinding:
    task_id: str
    topic_role: str
    required: bool
    topic_description: str
    primary_evidence_ids: List[str]
    supporting_evidence_ids: List[str]
    topic_support_score: float
    binding_confidence: str
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "topic_role": self.topic_role,
            "required": self.required,
            "topic_description": self.topic_description,
            "primary_evidence_ids": list(self.primary_evidence_ids),
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "topic_support_score": self.topic_support_score,
            "binding_confidence": self.binding_confidence,
        }

@dataclass
class SynthesisCoveragePlan:
    task_id: str
    required_topics: List[str]
    supported_topics: List[str] = field(default_factory=list)
    weak_topics: List[str] = field(default_factory=list)
    unsupported_topics: List[str] = field(default_factory=list)
    required_total: int = 0
    required_strong: int = 0
    required_adequate: int = 0
    required_weak: int = 0
    required_unsupported: int = 0
    optional_supported: int = 0
    optional_weak: int = 0
    required_output_order: List[str] = field(default_factory=list)
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "required_topics": list(self.required_topics),
            "supported_topics": list(self.supported_topics),
            "weak_topics": list(self.weak_topics),
            "unsupported_topics": list(self.unsupported_topics),
            "required_total": self.required_total,
            "required_strong": self.required_strong,
            "required_adequate": self.required_adequate,
            "required_weak": self.required_weak,
            "required_unsupported": self.required_unsupported,
            "optional_supported": self.optional_supported,
            "optional_weak": self.optional_weak,
            "required_output_order": list(self.required_output_order),
        }

@dataclass
class TopicEvidenceBindingSet:
    task_id: str
    bindings: List[TopicEvidenceBinding]
    unbound_required_topics: List[str]
    weakly_bound_topics: List[str]
    coverage_ratio: float
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "bindings": [b.as_dict() for b in self.bindings],
            "unbound_required_topics": list(self.unbound_required_topics),
            "weakly_bound_topics": list(self.weakly_bound_topics),
            "coverage_ratio": self.coverage_ratio,
        }

class TopicEvidenceBindingBuilder:
    
    PRIMARY_THRESHOLD = 0.7
    SUPPORTING_THRESHOLD = 0.45

    @staticmethod
    def build(bundle: EvidenceBundle, req_set: CoverageRequirementSet) -> Tuple[TopicEvidenceBindingSet, SynthesisCoveragePlan]:
        bindings = []
        unbound_required = []
        weakly_bound = []
        supported_topics = []
        
        all_reqs = req_set.required_topics + req_set.optional_topics
        required_roles = {req.topic_role for req in req_set.required_topics}
        
        for req in all_reqs:
            topic_role = req.topic_role
            primary_ids = []
            supporting_ids = []
            max_score = 0.0
            
            for item in bundle.all_items:
                score = getattr(item, "topic_scores", {}).get(topic_role, 0.0)
                if score >= TopicEvidenceBindingBuilder.PRIMARY_THRESHOLD:
                    primary_ids.append(item.evidence_id)
                    max_score = max(max_score, score)
                elif score >= TopicEvidenceBindingBuilder.SUPPORTING_THRESHOLD:
                    supporting_ids.append(item.evidence_id)
                    max_score = max(max_score, score)
            
            if primary_ids or supporting_ids:
                confidence = "high" if max_score >= TopicEvidenceBindingBuilder.PRIMARY_THRESHOLD else "medium"
                binding = TopicEvidenceBinding(
                    task_id=bundle.task_id,
                    topic_role=topic_role,
                    required=topic_role in required_roles,
                    topic_description=req.explanation_goal if hasattr(req, "explanation_goal") else topic_role,
                    primary_evidence_ids=primary_ids,
                    supporting_evidence_ids=supporting_ids,
                    topic_support_score=max_score,
                    binding_confidence=confidence
                )
                bindings.append(binding)
                
                print(
                    f"[TopicEvidenceBinding] task_id={bundle.task_id} topic={topic_role} "
                    f"primary={primary_ids} supporting={supporting_ids} "
                    f"support_score={max_score:.2f} confidence={confidence}"
                )
                
                supported_topics.append(topic_role)
                if confidence == "medium":
                    weakly_bound.append(topic_role)
            else:
                if topic_role in required_roles:
                    unbound_required.append(topic_role)
        
        req_roles_list = list(required_roles)
        coverage_ratio = len([t for t in supported_topics if t in required_roles]) / len(required_roles) if required_roles else 1.0
        
        binding_set = TopicEvidenceBindingSet(
            task_id=bundle.task_id,
            bindings=bindings,
            unbound_required_topics=unbound_required,
            weakly_bound_topics=weakly_bound,
            coverage_ratio=coverage_ratio
        )
        
        output_order = [r.topic_role for r in req_set.required_topics]
        for r in req_set.optional_topics:
            if r.topic_role in supported_topics:
                output_order.append(r.topic_role)
                
        # ensure short_conclusion is at the end if it exists
        if "short_conclusion" in output_order:
            output_order.remove("short_conclusion")
            output_order.append("short_conclusion")
            
        req_strong = 0
        req_adequate = 0
        req_weak = 0
        req_unsupported = 0
        opt_supported = 0
        opt_weak = 0
        
        optional_roles = {req.topic_role for req in req_set.optional_topics}
        
        for binding in bindings:
            if binding.required:
                if binding.topic_support_score >= 0.7:
                    req_strong += 1
                elif binding.topic_support_score >= 0.45:
                    req_adequate += 1
                else:
                    req_weak += 1
            else:
                if binding.topic_support_score >= 0.45:
                    opt_supported += 1
                else:
                    opt_weak += 1
                    
        for req in req_set.required_topics:
            if req.topic_role not in supported_topics:
                req_unsupported += 1
                
        synthesis_plan = SynthesisCoveragePlan(
            task_id=bundle.task_id,
            required_topics=req_roles_list,
            supported_topics=[t for t in supported_topics if t in required_roles],
            weak_topics=[t for t in weakly_bound if t in required_roles],
            unsupported_topics=list(unbound_required),
            required_total=len(required_roles),
            required_strong=req_strong,
            required_adequate=req_adequate,
            required_weak=req_weak,
            required_unsupported=req_unsupported,
            optional_supported=opt_supported,
            optional_weak=opt_weak,
            required_output_order=output_order
        )
        
        print(
            f"[SynthesisCoveragePlan] task_id={bundle.task_id} required_total={len(required_roles)} "
            f"required_strong={req_strong} required_adequate={req_adequate} required_weak={req_weak} "
            f"required_unsupported={req_unsupported} optional_supported={opt_supported} optional_weak={opt_weak}"
        )
        return binding_set, synthesis_plan
