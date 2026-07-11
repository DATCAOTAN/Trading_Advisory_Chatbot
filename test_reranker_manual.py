import sys
import os

from src.pipelines.modules.reranker import RerankerModule

def run_test():
    reranker = RerankerModule()
    
    # Mock raw documents
    raw_docs = []
    for i in range(10):
        raw_docs.append({
            "content": f"Mock content {i}",
            "metadata": {"source": "mock_source", "parent_id": f"p{i}"},
            "score": 0.9 - (i * 0.05)
        })
        
    print("\n--- Running STANDARD (top_k=3) ---")
    _, best_docs = reranker.process("test query", raw_docs, top_k=3, is_refinement=False, enabled=False)
    print(f"Returned docs: {len(best_docs)}")
    
    print("\n--- Running REFINEMENT (top_k=3, is_refinement=True) ---")
    _, best_docs_refine = reranker.process("test query", raw_docs, top_k=3, is_refinement=True, enabled=False)
    print(f"Returned docs: {len(best_docs_refine)}")

if __name__ == "__main__":
    run_test()
