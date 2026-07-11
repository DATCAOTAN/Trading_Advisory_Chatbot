import pytest
from src.core.models import CoverageRefinementRequest
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
    def retrieve_candidates(self, query, top_k=None):
        return self.returned_chunks

def test_previous_chunk_exclusion():
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
        previous_parent_ids=["p1"],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    svc = MockVectorService([
        {"chunk_id": "c1", "parent_id": "p1"},
        {"chunk_id": "c2", "parent_id": "p1"}, # same parent
        {"chunk_id": "c3", "parent_id": "p2"}  # novel parent
    ])
    
    result = executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["topic_a"])
    
    novel_candidates = result["novel_candidates"]
    novel_ids = [doc.get("chunk_id") for doc in novel_candidates]
    
    # c1 MUST be excluded entirely
    assert "c1" not in novel_ids
    # c2 shares parent, it should be tracked but still included as fallback
    assert "c2" in novel_ids
    # c3 is completely novel
    assert "c3" in novel_ids
    
    # check repeated ids tracked
    assert "c1" in result["novelty"].repeated_evidence_ids
