import pytest
from src.core.models import CoverageRefinementRequest, CoverageRequirement
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
    def retrieve_candidates(self, query, top_k=None):
        return self.returned_chunks

def test_effectiveness_when_same_evidence_returned():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="query",
        refined_query="query refined",
        missing_topics=["methodology_or_process"],
        topic_descriptions={},
        retrieval_descriptors=[],
        previous_evidence_ids=["c1"],
        previous_chunk_ids=["c1"],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    # Simulate returning same chunk
    svc = MockVectorService([{"chunk_id": "c1", "covered_topics": ["core_concept"]}])
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["methodology_or_process"])
    
    assert result["refinement_result"].coverage_improved is False
    assert result["refinement_result"].execution_status == "COMPLETED_NO_NOVEL_EVIDENCE"
    assert result["novelty"].novelty_ratio == 0.0

def test_effectiveness_when_new_evidence_improves_coverage():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="query",
        refined_query="query refined",
        missing_topics=["methodology_or_process"],
        topic_descriptions={},
        retrieval_descriptors=[],
        previous_evidence_ids=["c1"],
        previous_chunk_ids=["c1"],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    # Simulate returning new chunk that actually covers the missing topic
    svc = MockVectorService([{"chunk_id": "c2", "covered_topics": ["methodology_or_process"]}])
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["methodology_or_process"])
    
    assert result["refinement_result"].coverage_improved is True
    assert result["refinement_result"].execution_status == "COMPLETED_IMPROVED"
    assert result["novelty"].novelty_ratio == 1.0

def test_effectiveness_when_new_evidence_does_not_improve_coverage():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="query",
        refined_query="query refined",
        missing_topics=["methodology_or_process"],
        topic_descriptions={},
        retrieval_descriptors=[],
        previous_evidence_ids=["c1"],
        previous_chunk_ids=["c1"],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    # Simulate returning new chunk but it covers something else entirely, not what's missing
    svc = MockVectorService([{"chunk_id": "c2", "covered_topics": ["practical_application"]}])
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["methodology_or_process"])
    
    assert result["refinement_result"].coverage_improved is False
    assert result["refinement_result"].execution_status == "COMPLETED_NOVEL_BUT_NO_COVERAGE_GAIN"
    assert result["novelty"].novelty_ratio == 1.0
