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

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Iterator, List, Dict, Tuple, Optional
import time

from src.services.vector_service import VectorService
from src.services.llm_service import LLMService
from src.services.live_data_service import get_live_service
from src.config import Config

# Nhập các Mô-đun Modular RAG
from src.pipelines.modules.query_rewriter import QueryRewriterModule
from src.pipelines.modules.router import RouterModule, RouteAction
from src.pipelines.modules.reranker import RerankerModule
from src.pipelines.modules.evaluator import EvaluatorModule


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
        # ── Modular Components ──
        self.rewriter_module = QueryRewriterModule()
        self.router_module = RouterModule()
        self.reranker_module = RerankerModule()
        self.evaluator_module = EvaluatorModule()
        
        # ── In-Memory Caching Layer (TTL: 15 minutes) ──
        self._context_cache = {}
        self._CACHE_TTL = 15 * 60  # 15 phút
        
        print("✅ [Orchestrator] Hệ thống Modular RAG đã sẵn sàng!")

    # =========================================================================
    # PUBLIC API — Được gọi từ app.py
    # =========================================================================

    def sync_knowledge_base(self, force: bool = False) -> dict:
        return self.vector_service.sync_documents(force=force)

    def query_financial_advisor(
        self,
        user_query: str,
        chat_history: List[Dict] = None,
        session_id: str = "",
        enable_self_correction: bool = False,
        enable_reranker: bool = True,
    ) -> Tuple[Iterator[str], List[Dict], str]:
        if chat_history is None:
            chat_history = []

        # =====================================================================
        # TẦNG 1: ROUTING TĨNH (Early Exit Gatekeeper)
        # =====================================================================
        route_action, static_response = self.router_module.process(user_query, chat_history)

        if route_action == RouteAction.EARLY_EXIT:
            print("⚡ [Agent] EARLY_EXIT kích hoạt. Trả lời ngay lập tức.")
            if isinstance(static_response, str):
                stream = self._static_stream(static_response)
            else:
                stream = static_response
            return stream, [], "EARLY_EXIT"

        # =====================================================================
        # TẦNG 2: AGENTIC RAG CONTROLLER (ReAct Loop)
        # =====================================================================
        print("🤖 [Agent] Khởi động Agentic RAG Controller...")

        max_loops = 3 if enable_self_correction else 1
        current_loop = 0
        final_stream = None
        final_sources = []
        feedback_note = ""
        
        # Tiền xử lý bằng Rewriter để có Query cơ sở tốt nhất
        current_query = self.rewriter_module.process(user_query, chat_history)

        # Lấy thời gian hiện tại một lần cho toàn bộ phiên
        vn_tz = timezone(timedelta(hours=7))
        weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        now = datetime.now(vn_tz)
        weekday_str = weekdays[now.weekday()]
        now_str = f"{weekday_str}, ngày {now.strftime('%d/%m/%Y %H:%M:%S')} (Giờ VN)"

        while current_loop < max_loops:
            current_loop += 1
            print(f"\n🔄 [Agent Loop {current_loop}/{max_loops}] Truy vấn hiện tại: {current_query}")

            # ── BƯỚC 1: THOUGHT & ACTION (Tool Selection) ──
            tools_to_run = self._agent_tool_selector(current_query, now_str)
            print(f"🛠️ [Agent Action] LLM tự quyết định gọi công cụ: {tools_to_run}")

            # ── BƯỚC 2: OBSERVATION (Tổng hợp Context từ Tools) ──
            combined_context = f"【THỜI GIAN HỆ THỐNG HIỆN TẠI】\nHôm nay là: {now_str}\n\n"
            current_sources = []

            # Trích xuất danh sách tên công cụ để kiểm tra logic
            tool_names = [t.get("tool") if isinstance(t, dict) else t for t in tools_to_run]

            if "Live_API" in tool_names:
                # Tìm tham số của Live_API
                live_args = next((t.get("args", {}) for t in tools_to_run if isinstance(t, dict) and t.get("tool") == "Live_API"), {})
                symbol = live_args.get("symbol", "XAUUSD")
                timeframe = live_args.get("timeframe", "1m")
                limit = live_args.get("limit", 100)
                
                print(f"📡 [Observation] Lấy dữ liệu Live API cho {symbol} ({timeframe}, {limit} nến)...")
                live_price = self.live_service.get_live_price(symbol)
                live_cal = self.live_service.get_economic_calendar()
                
                # Bổ sung lấy nến quá khứ (OHLCV)
                candles = self.live_service.get_historical_candles(symbol=symbol, timeframe=timeframe, limit=limit)
                candles_str = json.dumps(candles) if candles else "Không có dữ liệu nến"
                
                combined_context += f"【DỮ LIỆU THỜI GIAN THỰC】\nGiá hiện tại:\n{live_price}\n\nLịch kinh tế tuần này:\n{live_cal}\n\nDữ liệu nến quá khứ ({timeframe}, {limit} nến):\n{candles_str}\n\n"

            if "Search_Chat_History" in tool_names:
                print("⏳ [Observation] Trích xuất Long-term Memory...")
                history_context = self.vector_service.search_chat_history(session_id, current_query)
                combined_context += f"【KÝ ỨC LỊCH SỬ DÀI HẠN】\n{history_context}\n\n"

            if "VectorDB_Search" in tool_names:
                print("📚 [Observation] Bới tìm VectorDB...")
                raw_candidates = self.vector_service.retrieve_candidates(current_query)
                if raw_candidates and not isinstance(raw_candidates, str):
                    db_context, best_docs = self.reranker_module.process(current_query, raw_candidates)
                    combined_context += f"【DỮ LIỆU KHO TRI THỨC】\n{db_context}\n\n"
                    current_sources = best_docs

            if not combined_context.strip():
                combined_context = "Không tìm thấy dữ liệu liên quan. Bạn phải trả lời dựa trên suy luận logic."

            # Giới hạn Short-term memory (RAM) gửi cho LLM (chỉ nạp 10 tin nhắn)
            short_term_history = chat_history[-10:] if chat_history else []

            # ── BƯỚC 3: GENERATION ──
            if not enable_self_correction:
                print("🚀 [Agent] Bỏ qua Reflection, trả thẳng kết quả stream ra UI.")
                final_stream = self.llm_service.generate_multihop_stream(user_query, combined_context, short_term_history)
                return final_stream, current_sources, "FINANCIAL_RAG"

            print(f"🧠 [Agent Reasoning] Sinh câu trả lời ngầm để Evaluator kiểm duyệt (Chưa hiện ra UI)...")
            draft_answer = ""
            for token in self.llm_service.generate_multihop_stream(user_query, combined_context, short_term_history):
                draft_answer += token

            # ── BƯỚC 4: EVALUATION & REFLECTION ──
            is_passed, new_feedback = self.evaluator_module.process(draft_answer, combined_context)
            
            if is_passed:
                print("✅ [Agent Reflection] Evaluator phê duyệt. Bắt đầu đẩy kết quả ra Streamlit UI...")
                final_stream = self._static_stream(draft_answer)
                return final_stream, current_sources, "FINANCIAL_RAG"
            else:
                feedback_note = new_feedback
                print(f"⚠️ [Agent Reflection] Evaluator bắt lỗi Hallucination: {feedback_note}")
                
                if current_loop < max_loops:
                    print("💡 [Agent Reflection] Đang tự đọc Feedback và sửa sai, tạo Query mới...")
                    current_query = self._agent_reflector(user_query, feedback_note, current_query)
                else:
                    print("🚨 [Agent] Đã thử hết giới hạn vòng lặp mà vẫn ảo tưởng. Ép in cảnh báo.")
                    warning = (
                        "⚠️ **CẢNH BÁO TỰ ĐỘNG:** Hệ thống không thể xác thực 100% "
                        "số liệu dưới đây do thiếu hụt tài liệu gốc. Vui lòng tham khảo có chọn lọc.\n\n"
                    )
                    final_stream = self._static_stream(warning + draft_answer)
                    return final_stream, current_sources, "FINANCIAL_RAG"

    # =========================================================================
    # AGENTIC INTERNAL HELPERS
    # =========================================================================

    def _agent_tool_selector(self, query: str, current_time_str: str) -> List[Dict]:
        """Sử dụng LLM để tự quyết định công cụ cần gọi dựa trên câu hỏi."""
        prompt = f"""Bạn là một AI Controller. Bạn có 3 công cụ trong tay:
1. "VectorDB_Search": Dùng khi câu hỏi cần tìm lý thuyết (SMC, FVG), phân tích vĩ mô tĩnh trong quá khứ, báo cáo cũ.
2. "Live_API": Dùng khi câu hỏi nhắc đến GIÁ HIỆN TẠI, GIÁ ĐÓNG CỬA, HOẶC XU HƯỚNG HIỆN TẠI. Hỗ trợ truyền tham số: symbol (ví dụ: XAUUSD, BTCUSDT), timeframe (ví dụ: 1m, 5m, 15m, 1h, 4h, 1d), limit (số lượng nến cần lấy, mặc định 100).
3. "Search_Chat_History": Dùng khi người dùng chủ động hỏi vặn, nhắc lại hoặc hồi tưởng về một chi tiết cụ thể nằm trong cuộc trò chuyện ở quá khứ. TUYỆT ĐỐI KHÔNG GỌI công cụ này nếu câu hỏi không mang tính chất lục lọi quá khứ.

THÔNG TIN BỐI CẢNH QUAN TRỌNG:
Thời gian hiện tại của hệ thống: {current_time_str}
Hãy dùng thời gian này để tính toán nếu người dùng hỏi những câu như "10 phút trước", "hôm qua", "tuần trước" để truyền limit và timeframe cho phù hợp.

Nhiệm vụ: CÂU HỎI dưới đây cần gọi công cụ nào? Bạn có thể gọi 1 công cụ hoặc kết hợp nhiều công cụ cùng lúc. Trả về mảng rỗng [] nếu câu hỏi chỉ là chào hỏi xã giao hoặc không cần gọi công cụ.
Output BẮT BUỘC phải là mảng JSON hợp lệ chứa các object. Mỗi object gồm trường "tool" (tên công cụ) và "args" (các tham số cần thiết, nếu không cần tham số thì để trống). Không xuất thêm bất cứ text nào khác.
Ví dụ:
[
  {{"tool": "Live_API", "args": {{"symbol": "XAUUSD", "timeframe": "1d", "limit": 1}}}},
  {{"tool": "VectorDB_Search", "args": {{}}}}
]
hoặc []

CÂU HỎI: {query}"""
        try:
            from src.core.llm_client import LLMClient
            openrouter_client = LLMClient(provider_override="groq")
            resp = openrouter_client.chat([{"role": "user", "content": prompt}], stream=False, temperature=0.0)
            clean_resp = resp["message"]["content"].replace("```json", "").replace("```", "").strip()
            tools = json.loads(clean_resp)
            if isinstance(tools, list):
                return tools
        except Exception as e:
            print(f"⚠️ [Agent Tool Selector] Lỗi parse JSON: {e} -> Fallback dùng VectorDB_Search.")
        return [{"tool": "VectorDB_Search", "args": {}}]

    def _agent_reflector(self, original_query: str, feedback: str, previous_query: str) -> str:
        """LLM đọc Feedback từ Evaluator và tự sinh Query mới để tìm bù thông tin."""
        prompt = f"""Hệ thống vừa bị từ chối kết quả với LÝ DO: {feedback}
CÂU HỎI GỐC CỦA NGƯỜI DÙNG: {original_query}
CÂU TRUY VẤN LẦN TRƯỚC BẠN DÙNG: {previous_query}

Nhiệm vụ: Hãy đọc LÝ DO bị từ chối, và viết ra MỘT câu truy vấn TỪ KHÓA MỚI để tìm đúng đoạn kiến thức còn thiếu đó. 
CHỈ output câu truy vấn mới, tuyệt đối không giải thích."""
        try:
            from src.core.llm_client import LLMClient
            openrouter_client = LLMClient(provider_override="groq")
            new_q = openrouter_client.chat([{"role": "user", "content": prompt}], stream=False, temperature=0.3)
            return new_q["message"]["content"].strip('"').strip()
        except Exception:
            return f"{previous_query} {feedback}"

    @staticmethod
    def _static_stream(text: str) -> Iterator[str]:
        """Giả lập streaming cho câu trả lời đã tạo sẵn, giúp giao diện UI mượt mà."""
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