"""
RAG Orchestrator v2 — Tái cấu trúc triệt để với LLM Gatekeeper.

Pipeline điều phối:
  User Query
    ↓
  [LLM Gatekeeper] ← Qwen 2.5 phân loại ý định (temperature=0.0)
    ├─ GREETING      → quick_reply() tĩnh     ⚡ EARLY EXIT
    ├─ TRASH         → cảnh báo lạc đề        ⚡ EARLY EXIT
    └─ FINANCIAL_RAG → full_rag_pipeline()     🔥 DÂY CHUYỀN HẠNG NẶNG
                          ↓
                       [Query Rewriting] (Qwen)
                          ↓
                       [Hybrid Search + Reranker] (Qdrant + BGE)
                          ↓
                       [Multi-Hop Generation] (Qwen Streaming)
                          ↓ (optional)
                       [Self-Correction] (Qwen)
"""

from typing import Iterator, List, Dict, Tuple, Optional
import time

from src.services.vector_service import VectorService
from src.services.llm_service import LLMService
from src.services.live_data_service import get_live_service
from src.pipelines.intent_router import IntentRouter, IntentType
from src.config import Config


class RAGOrchestrator:
    """
    Facade Pattern: Một đầu mối duy nhất cho toàn bộ hệ thống RAG nâng cấp.

    Cơ chế Early Exit:
    - GREETING / TRASH → trả lời tĩnh ngay lập tức, KHÔNG nạp model nặng
    - CHỈ FINANCIAL_RAG mới kích hoạt: Query Rewrite → Qdrant → Reranker → Qwen Stream
    """

    def __init__(self):
        print("🚀 [Orchestrator] Khởi động các dịch vụ cốt lõi...")
        self.vector_service = VectorService()
        self.llm_service    = LLMService()
        self.live_service   = get_live_service()
        
        # ── In-Memory Caching Layer (TTL: 15 minutes) ──
        self._context_cache = {}
        self._CACHE_TTL = 15 * 60  # 15 phút
        
        print("✅ [Orchestrator] Hệ thống sẵn sàng!")

    # =========================================================================
    # PUBLIC API — Được gọi từ app.py
    # =========================================================================

    def sync_knowledge_base(self, force: bool = False) -> dict:
        """
        Đồng bộ kho tri thức thông minh (Incremental Ingestion).

        Args:
            force: Nếu True, xóa sạch và nạp lại toàn bộ (Force Re-index)

        Returns:
            Dict báo cáo: {added, updated, deleted, unchanged, total_chunks}
        """
        return self.vector_service.sync_documents(force=force)

    def query_financial_advisor(
        self,
        user_query: str,
        chat_history: List[Dict] = None,
        enable_self_correction: bool = False,
        enable_reranker: bool = True,
    ) -> Tuple[Iterator[str], List[Dict], str]:
        """
        Đầu mối xử lý toàn bộ chu trình Hỏi-Đáp.

        Luồng xử lý:
        1. Gatekeeper phân loại intent (Qwen, temperature=0.0)
        2. GREETING / TRASH → Early Exit (trả lời tĩnh, không tốn tài nguyên)
        3. FINANCIAL_RAG → Full pipeline (Rewrite → Search → Rerank → Generate)

        Args:
            user_query:            Câu hỏi thô từ Trader
            chat_history:          Danh sách {role, content} gần nhất
            enable_self_correction: Bật vòng kiểm tra hallucination
            enable_reranker:       Bật BGE Reranker

        Returns:
            (stream_generator, sources_list, intent_type_str)
            - stream_generator: Iterator[str] để st.write_stream()
            - sources_list:     List các nguồn tài liệu đã truy xuất
            - intent_type_str:  Chuỗi intent để hiển thị badge trên UI
        """
        if chat_history is None:
            chat_history = []

        # =====================================================================
        # TẦNG 1: LLM GATEKEEPER — Phân loại ý định trước khi làm bất cứ gì
        # =====================================================================
        intent = IntentRouter.classify(user_query, chat_history)

        # ── EARLY EXIT: Chào hỏi xã giao → Qwen phản hồi linh hoạt, không RAG ──
        if intent == IntentType.GREETING:
            print("⚡ [EarlyExit] GREETING → Qwen sinh phản hồi xã giao")
            return (
                IntentRouter.get_greeting_response(user_query),
                [],       # Không có sources
                "GREETING"
            )

        # ── EARLY EXIT: Vô nghĩa / lạc đề → cảnh báo, không RAG ──
        if intent == IntentType.TRASH:
            print("⚡ [EarlyExit] TRASH → Cảnh báo lạc đề")
            return (
                self._static_stream(IntentRouter.get_trash_response()),
                [],       # Không có sources
                "TRASH"
            )

        # =====================================================================
        # TẦNG 2: FINANCIAL_RAG — Kích hoạt DÂY CHUYỀN HẠNG NẶNG
        # =====================================================================
        print("🔥 [Pipeline] FINANCIAL_RAG → Khởi động full pipeline...")

        # ── Bước 1: Query Rewriting (mở rộng câu hỏi tiếng lóng → chuẩn) ──
        rewritten_query = self.llm_service.rewrite_query(user_query, chat_history)

        # ── Bước 2: In-Memory Caching Layer (Bỏ qua Vector DB nếu trùng cache) ──
        current_time = time.time()
        cached_data = self._find_cache_match(rewritten_query)
        
        if cached_data:
            print("⚡ [Cache] HIT! Lấy context từ bộ nhớ đệm (0s latency).")
            context_str = cached_data["context"]
            sources = cached_data["sources"]
        else:
            print("🔍 [Cache] MISS! Đang thực hiện Hybrid Search & Reranker...")
            # Bước 2.1: Hybrid Search + Reranker (Qdrant + BGE)
            context_str, sources = self.vector_service.retrieve_context(
                rewritten_query,
                enable_reranker=enable_reranker,
            )
            # Lưu vào cache
            self._context_cache[rewritten_query] = {
                "context": context_str,
                "sources": sources,
                "timestamp": current_time
            }

        # ── Bước 3: Multi-Hop Streaming Generation ──
        if enable_self_correction:
            # Non-streaming: thu toàn bộ → self-correct → stream lại
            stream = self._self_correction_pipeline(
                user_query, context_str, chat_history, sources,
            )
        else:
            stream = self.llm_service.generate_multihop_stream(
                user_query, context_str, chat_history
            )

        return stream, sources, "FINANCIAL_RAG"

    # =========================================================================
    # HELPERS NỘI BỘ
    # =========================================================================

    @staticmethod
    def _static_stream(text: str) -> Iterator[str]:
        """
        Giả lập streaming cho câu trả lời tĩnh (GREETING, TRASH).
        Chia nhỏ theo từ để tạo hiệu ứng chữ chạy trên UI.
        """
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def _self_correction_pipeline(
        self,
        query: str,
        context: str,
        history: List[Dict],
        sources: List[Dict],
    ) -> Iterator[str]:
        """
        Stream trực tiếp lên UI (Non-blocking), đồng thời thu thập text.
        Sau khi luồng chính kết thúc mới chạy kiểm tra ngầm và đính chính.
        """
        print("⚡ [Pipeline] Đang stream kết quả trực tiếp...")
        full_answer = ""
        for token in self.llm_service.generate_multihop_stream(query, context, history):
            full_answer += token
            yield token

        print("🔍 [SelfCorrect] Chạy kiểm tra ngầm (Background Task)...")
        correction_note = self.llm_service.self_correct(full_answer, context)

        if correction_note and "[OK]" not in correction_note:
            print("⚠️ [SelfCorrect] Phát hiện sai sót, đang thêm đính chính...")
            yield correction_note

    def _find_cache_match(self, query: str) -> Optional[Dict]:
        """
        Tìm kiếm Cache dựa trên cơ sở So khớp mờ (Fuzzy Keyword Match).
        Tránh Cache Miss cứng nhắc do sai khác một vài từ không quan trọng.
        """
        current_time = time.time()
        
        # Lọc từ khóa: bỏ dấu câu và stop words cơ bản
        def get_keywords(text: str) -> set:
            import re
            clean_text = re.sub(r'[^\w\s]', '', text.lower())
            words = clean_text.split()
            stop_words = {"của", "và", "như", "thế", "nào", "đến", "các", "có", "là", "gì", "cho", "việc", "thì", "sao", "đi", "về", "đâu"}
            return set(w for w in words if w not in stop_words and len(w) > 1)
            
        q_words = get_keywords(query)
        if not q_words:
            return None
            
        for cached_q, data in list(self._context_cache.items()):
            if current_time - data["timestamp"] > self._CACHE_TTL:
                del self._context_cache[cached_q]
                continue
                
            c_words = get_keywords(cached_q)
            if not c_words:
                continue
                
            # Tính tỷ lệ Overlap (trùng khớp)
            intersection = q_words.intersection(c_words)
            overlap_ratio = len(intersection) / max(len(q_words), len(c_words))
            
            if overlap_ratio >= 0.75:  # Trùng > 75% từ khóa
                return data
                
        return None

if __name__ == "__main__":
    print("=== KIỂM THỬ TÍCH HỢP TOÀN PIPELINE ===")
    orch = RAGOrchestrator()

    test_cases = [
        ("Xin chào!",                    "GREETING"),
        ("jdjdjdjddđ",                   "TRASH"),
        ("cách nấu phở",                 "TRASH"),
        ("Lạm phát ảnh hưởng gì đến XAUUSD?", "FINANCIAL_RAG"),
    ]

    for query, expected in test_cases:
        stream, sources, intent = orch.query_financial_advisor(query)
        tokens = list(stream)
        answer_preview = "".join(tokens)[:100]
        status = "✅" if intent == expected else "⚠️"
        print(f"\n{status} [{intent}] '{query}'")
        print(f"   Preview: {answer_preview}...")