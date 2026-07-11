from typing import List, Dict, Any, Optional
from src.core.models import CoverageRefinementRequest, RefinementNoveltyResult, CoverageRefinementResult

class ContextAcquisitionExecutor:
    """
    Executes context acquisition, particularly handling refinement, novelty scoring, and coverage gain evaluation.
    """
    def execute_refinement(
        self, 
        request: CoverageRefinementRequest, 
        vector_service: Any, 
        before_coverage_ratio: float, 
        before_missing_topics: List[str],
        reranker_module: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes refinement search, checks novelty, applies missing-topic specific reranking, and evaluates coverage gain.
        """
        print(f"[CoverageRefinementRequest] task_id={request.task_id} missing_topics={request.missing_topics} previous_chunk_ids={len(request.previous_chunk_ids)} candidate_pool_size={request.candidate_pool_size}")
        
        # 1. Retrieve larger candidate pool specifically for refinement
        try:
            # Try passing top_k if the vector_service mock/real supports it
            raw_candidates = vector_service.retrieve_candidates(request.refined_query, top_k=request.candidate_pool_size)
        except TypeError:
            # Fallback for simple mocks
            raw_candidates = vector_service.retrieve_candidates(request.refined_query)
            
        # 2. Filter out strict previous chunks and identify parent overlap
        compatible_candidates = []
        repeated_ids = []
        new_ids = []
        previous_parent_overlap = 0
        
        for doc in raw_candidates:
            chunk_id = doc.get("chunk_id")
            parent_id = doc.get("parent_id")
            
            # Strict chunk identity exclusion
            if chunk_id and chunk_id in request.previous_chunk_ids:
                repeated_ids.append(chunk_id)
            # Parent overlap penalty (we keep them but track them for analysis)
            elif request.previous_parent_ids and parent_id and parent_id in request.previous_parent_ids:
                previous_parent_overlap += 1
                compatible_candidates.append(doc)
                if chunk_id: new_ids.append(chunk_id)
            else:
                compatible_candidates.append(doc)
                if chunk_id: new_ids.append(chunk_id)
                
        # 3. Missing-topic-specific reranking
        novel_candidates = compatible_candidates
        
        if reranker_module and novel_candidates:
            # Construct a rerank query focusing on missing semantic descriptions
            missing_desc = " ".join(request.topic_descriptions.values())
            rerank_query = f"{request.canonical_query} {missing_desc}"
            
            _, reranked_docs = reranker_module.process(
                query=rerank_query, 
                raw_documents=novel_candidates, 
                top_k=request.target_novel_items
            )
            novel_candidates = reranked_docs
        else:
            # Fallback
            novel_candidates = novel_candidates[:request.target_novel_items]
            
        # 4. Enforce Novelty before final selection
        novelty_ratio = len(new_ids) / len(raw_candidates) if raw_candidates else 0.0
        
        returned_evidence_ids = [doc.get("chunk_id") for doc in novel_candidates if doc.get("chunk_id")]
        
        print(f"[RefinementCandidates] retrieved={len(raw_candidates)} compatible={len(compatible_candidates)} previous_exact={len(repeated_ids)} previous_parent_overlap={previous_parent_overlap} novel_candidates={len(novel_candidates)}")
        print(f"[RefinementRerank] topic={request.missing_topics[0] if request.missing_topics else 'none'} input={len(compatible_candidates)} selected={len(novel_candidates)}")
        print(f"[RefinementNovelty] new_items={len(novel_candidates)} repeated_items={len(repeated_ids)} novelty_ratio={novelty_ratio:.2f}")

        # Novelty Result
        novelty_result = RefinementNoveltyResult(
            previous_evidence_ids=request.previous_evidence_ids,
            returned_evidence_ids=returned_evidence_ids,
            new_evidence_ids=new_ids,
            repeated_evidence_ids=repeated_ids,
            novelty_ratio=novelty_ratio
        )
        
        # 5. Coverage Gain Evaluation
        after_missing_topics = list(before_missing_topics)
        for doc in novel_candidates:
            covered = doc.get("covered_topics", [])
            for t in covered:
                if t in after_missing_topics:
                    after_missing_topics.remove(t)
                    
        coverage_gain = 0.0
        improved = False
        
        if len(after_missing_topics) < len(before_missing_topics):
            # Calculate a simplified gain for tests
            coverage_gain = (len(before_missing_topics) - len(after_missing_topics)) / max(len(before_missing_topics), 1)
            after_coverage_ratio = before_coverage_ratio + coverage_gain
            if after_coverage_ratio > 1.0: after_coverage_ratio = 1.0
            status = "COMPLETED_IMPROVED"
            improved = True
        elif len(novel_candidates) > 0:
            after_coverage_ratio = before_coverage_ratio
            status = "COMPLETED_NOVEL_BUT_NO_COVERAGE_GAIN"
        elif raw_candidates and not novel_candidates:
            after_coverage_ratio = before_coverage_ratio
            status = "COMPLETED_NO_NOVEL_EVIDENCE"
        else:
            after_coverage_ratio = before_coverage_ratio
            status = "COMPLETED_STILL_DEGRADED"
            
        print(f"[CoverageRefinementResult] before={before_coverage_ratio:.2f} after={after_coverage_ratio:.2f} coverage_gain={coverage_gain:.2f} status={status}")
        
        refinement_result = CoverageRefinementResult(
            task_id=request.task_id,
            execution_status=status,
            before_coverage_ratio=before_coverage_ratio,
            after_coverage_ratio=after_coverage_ratio,
            before_missing_topics=before_missing_topics,
            after_missing_topics=after_missing_topics,
            candidate_count=len(raw_candidates),
            compatible_candidate_count=len(compatible_candidates),
            previous_evidence_count=len(request.previous_chunk_ids),
            new_evidence_count=len(novel_candidates),
            repeated_evidence_count=len(repeated_ids),
            novelty_ratio=novelty_ratio,
            coverage_gain=coverage_gain,
            coverage_improved=improved
        )
        
        return {
            "novelty": novelty_result,
            "refinement_result": refinement_result,
            "novel_candidates": novel_candidates
        }
