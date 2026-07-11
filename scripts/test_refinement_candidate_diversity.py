import pytest
from src.core.models import CoverageRefinementRequest
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
        self.last_top_k = None
        
    def retrieve_candidates(self, query, top_k=None):
        self.last_top_k = top_k
        return self.returned_chunks

def test_candidate_diversity_expanded_pool():
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
        candidate_pool_size=42,  # Distinct value to verify
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    svc = MockVectorService([{"chunk_id": "c2"}])
    executor.execute_refinement(req, svc, before_coverage_ratio=0.5, before_missing_topics=["topic_a"])
    
    # Verify candidate pool size is passed correctly
    assert svc.last_top_k == 42
