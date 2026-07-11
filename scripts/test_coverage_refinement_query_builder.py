import pytest
from src.pipelines.modules.refinement_builder import CoverageRefinementQueryBuilder

def test_query_builder_uses_semantic_descriptions():
    builder = CoverageRefinementQueryBuilder()
    topic_registry = {
        "methodology_or_process": {
            "description": "How the approach is applied in practice",
            "retrieval_descriptors": ["analysis process", "decision process", "practical rules"]
        }
    }
    
    req = builder.build_refinement_request(
        task_id="t1",
        original_query="Al Brooks price action",
        missing_topics=["methodology_or_process"],
        topic_registry=topic_registry,
        previous_evidence_ids=["e1"],
        previous_chunk_ids=["c1"]
    )
    
    assert "methodology_or_process" in req.missing_topics
    assert "analysis process" in req.refined_query
    assert "decision process" in req.refined_query
    assert "Al Brooks price action" in req.refined_query
    assert "methodology_or_process" not in req.refined_query # Raw ontology label is not in query
