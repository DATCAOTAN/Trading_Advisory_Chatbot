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
        intent = IntentRouter.classify(user_query)

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

        # ── Bước 2: Hybrid Search + Reranker (Qdrant + BGE) ──
        context_str, sources = self.vector_service.retrieve_context(
            rewritten_query,
            enable_reranker=enable_reranker,
        )

        # ── Bước 3: Multi-Hop Streaming Generation (Qwen 2.5) ──
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
        Thu toàn bộ answer → kiểm tra hallucination → stream lại kết quả.
        """
        print("🔍 [SelfCorrect] Thu thập câu trả lời để kiểm tra...")
        full_answer = "".join(
            self.llm_service.generate_multihop_stream(query, context, history)
        )

        print("🔍 [SelfCorrect] Đang kiểm tra hallucination...")
        corrected = self.llm_service.self_correct(full_answer, context)

        corrected_with_note = corrected + "\n\n*🔍 Đã qua vòng kiểm tra Self-Correction.*"
        yield from self._static_stream(corrected_with_note)


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