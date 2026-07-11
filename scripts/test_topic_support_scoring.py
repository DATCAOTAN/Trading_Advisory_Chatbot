import pytest
from src.services.evidence.evidence_coverage import EvidenceTopicAttributor, EvidenceCoverageResult
from src.services.evidence.coverage_requirements import CoverageRequirementSet, CoverageRequirement
from src.services.evidence.evidence_pipeline import EvidenceItem

def test_attributor_scores():
    req_set = CoverageRequirementSet(
        task_id="task_1",
        required_topics=[CoverageRequirement(topic_role="core_concept", explanation_goal="Explain core concept")],
        optional_topics=[],
        max_missing_critical=0
    )
    
    item1 = EvidenceItem(
        evidence_id="e1", task_id="task_1", evidence_type="book_passage", capability="static",
        content="This passage directly defines the core concept as xyz.", source_title="Source A"
    )
    
    res = EvidenceTopicAttributor.attribute(item1, req_set)
    assert "core_concept" in res.covered_topics
    assert "core_concept" in res.topic_scores
    assert res.topic_scores["core_concept"] > 0
