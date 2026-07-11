import pytest
from src.core.models import CoverageRefinementRequest
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
    def retrieve_candidates(self, query, top_k=None):
        return self.returned_chunks

def test_novelty_scoring():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="query",
        refined_query="query refined",
        missing_topics=["topic_a"],
        topic_descriptions={},
        retrieval_descriptors=[],
        previous_evidence_ids=["e1", "e2"],
        previous_chunk_ids=["c1", "c2"],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    # Simulate returning same chunks
    svc = MockVectorService([{"chunk_id": "c1"}, {"chunk_id": "c2"}])
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["topic_a"])
    
    novelty = result["novelty"]
    assert novelty.novelty_ratio == 0.0
    assert "c1" in novelty.repeated_evidence_ids
    assert len(novelty.new_evidence_ids) == 0
    assert result["refinement_result"].execution_status == "COMPLETED_NO_NOVEL_EVIDENCE"

def test_novelty_improvement():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="query",
        refined_query="query refined",
        missing_topics=["topic_a"],
        topic_descriptions={},
        retrieval_descriptors=[],
        previous_evidence_ids=["e1"],
        previous_chunk_ids=["c1"],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    # Simulate returning new chunks that cover topic_a
    svc = MockVectorService([{"chunk_id": "c2", "covered_topics": ["topic_a"]}])
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["topic_a"])
    
    novelty = result["novelty"]
    assert novelty.novelty_ratio == 1.0
    assert "c2" in novelty.new_evidence_ids
    assert result["refinement_result"].execution_status == "COMPLETED_IMPROVED"
    assert result["refinement_result"].coverage_improved is True
    assert result["refinement_result"].after_coverage_ratio > 0.5
