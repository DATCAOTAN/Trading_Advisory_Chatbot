import pytest
from src.core.models import CoverageRefinementRequest
from src.pipelines.modules.context_acquisition import ContextAcquisitionExecutor

class MockVectorService:
    def __init__(self, returned_chunks):
        self.returned_chunks = returned_chunks
    def retrieve_candidates(self, query, top_k=None):
        return self.returned_chunks

def test_outcome_semantics_improved():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1", original_query="", canonical_query="", refined_query="", missing_topics=["topic_a"],
        topic_descriptions={}, retrieval_descriptors=[], previous_evidence_ids=["e1"], previous_chunk_ids=["c1"], previous_parent_ids=[], provenance_constraints={}, candidate_pool_size=30, target_novel_items=5, attempt=1, reason="Missing"
    )
    svc = MockVectorService([{"chunk_id": "c2", "covered_topics": ["topic_a"]}])
    res = executor.execute_refinement(req, svc, 0.5, ["topic_a"])
    assert res["refinement_result"].execution_status == "COMPLETED_IMPROVED"
    assert res["refinement_result"].coverage_gain > 0

def test_outcome_semantics_novel_but_irrelevant():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1", original_query="", canonical_query="", refined_query="", missing_topics=["topic_a"],
        topic_descriptions={}, retrieval_descriptors=[], previous_evidence_ids=["e1"], previous_chunk_ids=["c1"], previous_parent_ids=[], provenance_constraints={}, candidate_pool_size=30, target_novel_items=5, attempt=1, reason="Missing"
    )
    # c2 is novel, but doesn't cover topic_a
    svc = MockVectorService([{"chunk_id": "c2", "covered_topics": ["topic_b"]}])
    res = executor.execute_refinement(req, svc, 0.5, ["topic_a"])
    assert res["refinement_result"].execution_status == "COMPLETED_NOVEL_BUT_NO_COVERAGE_GAIN"
    assert res["refinement_result"].coverage_gain == 0.0

def test_outcome_semantics_no_novel_evidence():
    executor = ContextAcquisitionExecutor()
    req = CoverageRefinementRequest(
        task_id="t1", original_query="", canonical_query="", refined_query="", missing_topics=["topic_a"],
        topic_descriptions={}, retrieval_descriptors=[], previous_evidence_ids=["e1"], previous_chunk_ids=["c1"], previous_parent_ids=[], provenance_constraints={}, candidate_pool_size=30, target_novel_items=5, attempt=1, reason="Missing"
    )
    # only returns c1, which is excluded
    svc = MockVectorService([{"chunk_id": "c1", "covered_topics": ["topic_a"]}])
    res = executor.execute_refinement(req, svc, 0.5, ["topic_a"])
    assert res["refinement_result"].execution_status == "COMPLETED_NO_NOVEL_EVIDENCE"
    assert res["refinement_result"].coverage_gain == 0.0
