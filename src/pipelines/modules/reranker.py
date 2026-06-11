import time
import cohere
from typing import List, Dict, Tuple
from src.config import Config

class RerankerModule:
    """Tái định hạng và lọc tài liệu rác từ hệ thống Vector Search."""
    def __init__(self):
        self.cohere_client = cohere.Client(api_key=Config.COHERE_API_KEY)
        
    def process(self, query: str, raw_documents: List[Dict], top_k: int = 3) -> Tuple[str, List[Dict]]:
        if not Config.ENABLE_RERANKER or not raw_documents:
            context_str = "\n\n".join([d["content"] for d in raw_documents[:top_k]])
            return context_str, raw_documents[:top_k]
            
        print("🎯 [RerankerModule] Bắt đầu chấm điểm Cohere Rerank...")
        start_t = time.time()
        docs_text = [d["content"] for d in raw_documents]
        
        try:
            response = self.cohere_client.rerank(
                model="rerank-multilingual-v3.0",
                query=query,
                documents=docs_text,
                top_n=top_k,
                return_documents=True
            )
            
            best_docs = []
            for r in response.results:
                orig_doc = raw_documents[r.index]
                if r.relevance_score < 0.1:  # Hạ ngưỡng xuống 0.1 cho tìm kiếm đa ngôn ngữ (Việt -> Anh)
                    continue
                best_docs.append({
                    "content": orig_doc["content"],
                    "metadata": orig_doc["metadata"],
                    "score": r.relevance_score
                })
                
            # Nếu bộ lọc quá tay xóa sạch mọi thứ, VỚT VÁT lại chunk có điểm cao nhất
            if not best_docs and response.results:
                r = response.results[0]
                best_docs.append({
                    "content": raw_documents[r.index]["content"],
                    "metadata": raw_documents[r.index]["metadata"],
                    "score": r.relevance_score
                })
                
            print(f"✅ [RerankerModule] Giữ lại {len(best_docs)}/{len(raw_documents)} chunks (Mất {time.time()-start_t:.2f}s)")
            context_str = "\n\n".join([f"ĐỘ TIN CẬY: {d['score']:.2f}\nNỘI DUNG:\n{d['content']}" for d in best_docs])
            return context_str, best_docs
            
        except Exception as e:
            print(f"⚠️ [RerankerModule] Lỗi API: {e} -> Fallback lấy top {top_k} ban đầu.")
            context_str = "\n\n".join([d["content"] for d in raw_documents[:top_k]])
            return context_str, raw_documents[:top_k]
