import pytest
from src.services.evidence.topic_evidence_binding import TopicEvidenceBindingBuilder, TopicEvidenceBinding
from src.services.evidence.evidence_pipeline import EvidenceBundle, EvidenceItem
from src.services.evidence.coverage_requirements import CoverageRequirementSet, CoverageRequirement

def test_binding_strong_and_weak():
    req_set = CoverageRequirementSet(
        task_id="task_1",
        required_topics=[CoverageRequirement(topic_role="core_concept", explanation_goal="Explain core concept")],
        optional_topics=[],
        max_missing_critical=0
    )
    
    item1 = EvidenceItem(
        evidence_id="e1", task_id="task_1", evidence_type="book_passage", capability="static",
        topic_scores={"core_concept": 0.8} # Strong
    )
    item2 = EvidenceItem(
        evidence_id="e2", task_id="task_1", evidence_type="book_passage", capability="static",
        topic_scores={"core_concept": 0.5} # Supporting
    )
    item3 = EvidenceItem(
        evidence_id="e3", task_id="task_1", evidence_type="book_passage", capability="static",
        topic_scores={"core_concept": 0.2} # Weak
    )
    
    bundle = EvidenceBundle(
        task_id="task_1", query="query", query_plan={}, answer_type="type",
        primary_evidence=[item1, item2, item3],
        supporting_evidence=[], current_market_evidence=[], event_evidence=[], technical_evidence=[],
        source_requirements=[], required_evidence_roles=[], freshness_summary={},
    )
    # the builder loops over all_items
    bundle.all_items = [item1, item2, item3]
    
    binding_set, plan = TopicEvidenceBindingBuilder.build(bundle, req_set)
    
    assert len(binding_set.bindings) == 1
    binding = binding_set.bindings[0]
    assert binding.topic_role == "core_concept"
    assert "e1" in binding.primary_evidence_ids
    assert "e2" in binding.supporting_evidence_ids
    assert "e3" not in binding.primary_evidence_ids and "e3" not in binding.supporting_evidence_ids
    assert binding.binding_confidence == "high"

def test_unbound_required_topics():
    req_set = CoverageRequirementSet(
        task_id="task_1",
        required_topics=[
            CoverageRequirement(topic_role="core_concept", explanation_goal="Explain core concept"),
            CoverageRequirement(topic_role="context_or_conditions", explanation_goal="Explain conditions")
        ],
        optional_topics=[],
        max_missing_critical=0
    )
    
    item1 = EvidenceItem(
        evidence_id="e1", task_id="task_1", evidence_type="book_passage", capability="static",
        topic_scores={"core_concept": 0.9} 
    )
    
    bundle = EvidenceBundle(
        task_id="task_1", query="query", query_plan={}, answer_type="type",
        primary_evidence=[], supporting_evidence=[], current_market_evidence=[], event_evidence=[], technical_evidence=[],
        source_requirements=[], required_evidence_roles=[], freshness_summary={},
    )
    bundle.all_items = [item1]
    
    binding_set, plan = TopicEvidenceBindingBuilder.build(bundle, req_set)
    
    assert "context_or_conditions" in binding_set.unbound_required_topics
    assert "context_or_conditions" in plan.unsupported_topics
    assert plan.required_output_order == ["core_concept", "context_or_conditions"]

