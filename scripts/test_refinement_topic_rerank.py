import pytest
from src.core.models import CoverageRefinementRequest
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
    def retrieve_candidates(self, query, top_k=None):
        return self.returned_chunks

class MockRerankerModule:
    def __init__(self):
        self.last_query = None
        
    def process(self, query, raw_documents, top_k):
        self.last_query = query
        # Just return docs in same order
        return "", raw_documents[:top_k]

def test_missing_topic_rerank():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1",
        original_query="query",
        canonical_query="canonical_X",
        refined_query="refined_X",
        missing_topics=["topic_a"],
        topic_descriptions={"topic_a": "missing description for topic A"},
        retrieval_descriptors=[],
        previous_evidence_ids=[],
        previous_chunk_ids=[],
        previous_parent_ids=[],
        provenance_constraints={},
        candidate_pool_size=30,
        target_novel_items=5,
        attempt=1,
        reason="Missing"
    )
    
    svc = MockVectorService([{"chunk_id": "c1"}])
    reranker = MockRerankerModule()
    
    executor.execute_refinement(
        req, 
        svc, 
        before_coverage_ratio=0.5, 
        before_missing_topics=["topic_a"],
        reranker_module=reranker
    )
    
    # Verify reranker receives semantic description, NOT just the raw label
    assert "canonical_X" in reranker.last_query
    assert "missing description for topic A" in reranker.last_query
    assert "topic_a" not in reranker.last_query # Ensure raw label isn't just dumped
