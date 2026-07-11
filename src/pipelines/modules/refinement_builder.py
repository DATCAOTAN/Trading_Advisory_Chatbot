from typing import List, Dict
from src.core.models import CoverageRefinementRequest, CoverageRequirement

class CoverageRefinementQueryBuilder:
    """
    Builds refinement queries strictly using semantic descriptions instead of raw ontology labels.
    """
    def build_refinement_request(
        self,
        task_id: str,
        original_query: str,
        missing_topics: List[str],
        topic_registry: Dict[str, dict],
        previous_evidence_ids: List[str],
        previous_chunk_ids: List[str],
        previous_parent_ids: List[str] = None,
        attempt: int = 1
    ) -> CoverageRefinementRequest:
        
        # Build refined query by combining original query with retrieval descriptors
        refined_query_parts = [original_query]
        topic_descriptions = {}
        retrieval_descriptors = []
        
        for topic in missing_topics:
            registry_entry = topic_registry.get(topic, {})
            descriptors = registry_entry.get("retrieval_descriptors", [])
            if descriptors:
                refined_query_parts.extend(descriptors)
                retrieval_descriptors.extend(descriptors)
            
            topic_descriptions[topic] = registry_entry.get("description", "")
            
        refined_query = " ".join(refined_query_parts)
        
        return CoverageRefinementRequest(
            task_id=task_id,
            original_query=original_query,
            canonical_query=original_query,  # Usually the same for refinement context
            refined_query=refined_query,
            missing_topics=missing_topics,
            topic_descriptions=topic_descriptions,
            retrieval_descriptors=retrieval_descriptors,
            previous_evidence_ids=previous_evidence_ids,
            previous_chunk_ids=previous_chunk_ids,
            previous_parent_ids=previous_parent_ids or [],
            provenance_constraints={},  # To be populated if needed
            candidate_pool_size=30,  # Expand candidate pool size specifically for refinement
            target_novel_items=5,
            attempt=attempt,
            reason="Missing required topics"
        )
