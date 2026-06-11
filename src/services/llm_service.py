"""
LLM Service — Nâng cấp toàn diện với:
1. Streaming response (stream=True → generator)
2. Query Rewriting: mở rộng câu hỏi tiếng lóng → chuẩn tài chính
3. Multi-Hop Generation: ép LLM suy luận theo chuỗi logic tài chính
4. Self-Correction: vòng kiểm tra hallucination (tùy chọn)
"""

from typing import Iterator, List, Dict, Optional
from src.config import Config
from src.core.llm_client import LLMClient


class LLMService:
    """
    Tầng giao tiếp với Cloud LLM (OpenRouter) và Local Fallback.
    Tất cả response đều hỗ trợ streaming để hiển thị chữ chạy từng token trên UI.
    """

    SYSTEM_BASE = (
        "Bạn là một Trợ lý Cố vấn Tài chính Cao cấp chuyên sâu về thị trường Vàng (XAUUSD) và Ngoại hối (Forex), "
        "hoạt động tại Việt Nam năm 2026.\n\n"

        "QUY TẮC CỐT LÕI:\n"
        "1. KHÓA NGÔN NGỮ (LANGUAGE LOCK - BẮT BUỘC): Bất kể tài liệu ngữ cảnh trích xuất chứa ngôn ngữ gì (Tiếng Anh, Tiếng Trung...), BẠN PHẢI DỊCH và TỔNG HỢP toàn bộ thành TIẾNG VIỆT 100% chuẩn ngữ pháp. TUYỆT ĐỐI KHÔNG để lọt bất kỳ ký tự tiếng nước ngoài nào chưa được dịch vào câu trả lời (trừ mã tài sản viết tắt như XAUUSD, DXY, SMC, FVG).\n"
        "2. CHỈ dùng thông tin trong 'BỐI CẢNH TÀI LIỆU' để trả lời. TUYỆT ĐỐI không bịa số liệu.\n"
        "3. TRÍ NHỚ DÀI HẠN: Nếu trong bối cảnh có chứa mục 【KÝ ỨC LỊCH SỬ DÀI HẠN】, đó CHÍNH LÀ những gì bạn và người dùng đã nói với nhau trước đây. Hãy đọc nó để trả lời! TUYỆT ĐỐI KHÔNG được từ chối bằng các câu như 'Là một AI, tôi không lưu lịch sử' - vì hệ thống đã trang bị bộ nhớ Vector cho bạn rồi.\n"
        "4. Văn phong: Tiếng Việt chuyên ngành tài chính — nghiêm túc, gãy gọn, lập luận logic.\n"
        "5. TỪ CHỐI mọi câu hỏi ngoài phạm vi tài chính, kinh tế, trading.\n\n"

        "CÔ LẬP KẾT QUẢ ĐẦU RA (OUTPUT ISOLATION - RẤT QUAN TRỌNG):\n"
        "- TUYỆT ĐỐI KHÔNG in ra quá trình suy nghĩ, phân tích ý định, hay các tiêu đề nội bộ (như 'Phân tích mục đích...', 'Trả lời dựa trên tài liệu...', 'Định dạng phù hợp...').\n"
        "- TUYỆT ĐỐI KHÔNG lặp lại câu hỏi thô hoặc câu hỏi đã được làm sạch của người dùng trong bài làm.\n"
        "- Trả về kết quả SẠCH SẼ, đi THẲNG VÀO TRỌNG TÂM câu hỏi. Bắt đầu ngay bằng nội dung phân tích.\n\n"

        "NGUYÊN TẮC PHẢN HỒI — NƯƠNG THEO CÂU HỎI (Context-Aware Formatting):\n"
        "Hãy chọn định dạng PHÙ HỢP NHẤT dựa trên mục đích câu hỏi:\n\n"

        "• Nếu người dùng hỏi về KHÁI NIỆM / ĐỊNH NGHĨA (vd: 'Order Block là gì?', 'FVG hoạt động thế nào?'):\n"
        "  → Tập trung giải thích bản chất lý thuyết, cơ chế hoạt động, kèm ví dụ minh họa từ tài liệu.\n"
        "  → KHÔNG ép vào khuôn phân tích vĩ mô hay đưa Entry/SL/TP.\n\n"

        "• Nếu người dùng yêu cầu PHÂN TÍCH XU HƯỚNG / CHIẾN LƯỢC giao dịch cụ thể (vd: 'vàng nên mua hay bán?', 'xu hướng XAUUSD tuần này?'):\n"
        "  → Tổng hợp dữ liệu từ vĩ mô (Fed, DXY, lạm phát) đến kỹ thuật (SMC, Price Action) trong tài liệu.\n"
        "  → Đưa ra mốc Entry / SL / TP rõ ràng nếu tài liệu có đủ dữ liệu.\n\n"

        "• Nếu người dùng hỏi về NĂNG LỰC / CHỨC NĂNG của hệ thống (vd: 'bạn có thể giúp gì?', 'bot biết những gì?'):\n"
        "  → Liệt kê ngắn gọn các phạm vi kiến thức (SMC, Price Action, Vĩ mô, Dòng tiền) bằng gạch đầu dòng.\n\n"

        "• Với MỌI loại câu hỏi khác: Tự do chọn định dạng tối ưu nhất (bảng biểu, gạch đầu dòng, đoạn văn ngắn).\n"
        "  TUYỆT ĐỐI KHÔNG áp dụng một khuôn mẫu cố định cho mọi lượt chat."
    )

    def __init__(self):
        self.llm_client = LLMClient(provider_override="google")

    def _call(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: float = 0.2,
    ):
        """Gọi LLM Router (OpenRouter/Ollama) hỗ trợ cả stream và non-stream."""
        return self.llm_client.chat(
            messages=messages,
            stream=stream,
            temperature=temperature,
        )

    # =========================================================================
    # 1. QUERY REWRITING
    # =========================================================================
    def rewrite_query(self, query: str, chat_history: List[Dict] = None) -> str:
        """
        Mở rộng và làm rõ câu hỏi ngắn/tiếng lóng của Trader thành
        câu truy vấn chuẩn khoa học để tối ưu Hybrid Search.

        Ví dụ:
          "vàng lên hay xuống?" → "Xu hướng giá XAUUSD trong bối cảnh DXY và lãi suất Fed hiện tại?"
        """
        if not Config.ENABLE_QUERY_REWRITING:
            return query
            
        print(f"\n✏️ [QueryRewrite] Đầu vào gốc nhận được: '{query}'")

        history_summary = ""
        if chat_history:
            recent = chat_history[-Config.MEMORY_WINDOW:]
            history_lines = [
                f"  [{m['role'].upper()}]: {m['content'][:200]}"
                for m in recent
                if m["role"] in ("user", "assistant")
            ]
            if history_lines:
                history_summary = "Lịch sử hội thoại gần đây:\n" + "\n".join(history_lines) + "\n\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là một Kỹ sư Cấu trúc Dữ liệu chuyên trách tối ưu hóa câu lệnh tìm kiếm (Query Expansion Expert) "
                    "cho Vector Database (Qdrant) trong hệ thống RAG tài chính chuyên sâu về Vàng (XAUUSD) và Forex.\n"
                    "Nhiệm vụ của bạn: Đọc câu hỏi hoặc câu thoại của người dùng, phân tích ý định ngầm (Intent) của họ. "
                    "Sau đó, hãy tạo ra một chuỗi các từ khóa mở rộng mang tính chất định hướng tri thức (Semantic Search Terms) "
                    "để hệ thống đi quét các tài liệu kỹ thuật liên quan.\n\n"

                    "HƯỚNG DẪN TƯ DUY EXPANSION:\n"
                    "- Nếu người dùng hỏi chung chung về thị trường, hãy tự động bổ sung các cụm từ khóa nền tảng: "
                    "'Cấu trúc thị trường (Market Structure), Mô hình nến, Xu hướng giá vĩ mô, Quản lý vốn, Tâm lý giao dịch Forex, Phân tích kỹ thuật XAUUSD'.\n"
                    "- Nếu người dùng hỏi về chiến lược cụ thể, hãy bổ sung các từ khóa chuyên sâu: "
                    "'Phương pháp SMC (Smart Money Concept), Vùng thanh khoản (Liquidity Pool), Khối lệnh (Order Block), "
                    "Vùng mất cân bằng cung cầu (Fair Value Gap - FVG), Quét thanh khoản (Liquidity Sweep)'.\n\n"

                    "QUY TẮC ĐẦU RA BẮT BUỘC:\n"
                    "- KHÔNG giải thích dòng vo, KHÔNG chào hỏi, KHÔNG bọc thẻ mã code block (```).\n"
                    "- Chỉ trả về DUY NHẤT chuỗi văn bản chứa các từ khóa ngữ nghĩa đã được mở rộng.\n"
                    "- Chuỗi trả về bắt buộc phải có nghĩa, độ dài tối thiểu trên 10 ký tự, tuyệt đối không trả về ký tự đơn rác rưởi hoặc chỉ chứa dấu câu."
                )
            },
            {
                "role": "user",
                "content": (
                    f"{history_summary}"
                    f"Câu hỏi gốc: \"{query}\"\n\n"
                    "Tạo chuỗi từ khóa Semantic Search:"
                )
            }
        ]

        try:
            # Thực hiện gọi đồng bộ (Sync) lên OpenRouter
            response = self.llm_client.openrouter_client.chat.completions.create(
                model=self.llm_client.openrouter_model,
                messages=messages,
                temperature=0.5,
                stream=False
            )
            raw_rewritten = response.choices[0].message.content.strip()
            rewritten = raw_rewritten.strip('"').strip("'")
            
            # --- VALIDATION CHECK (FALLBACK TO ORIGINAL QUERY) ---
            # 1. Chống Rỗng & Ngắn
            if len(rewritten) < 5 or not any(c.isalnum() for c in rewritten):
                print(f"⚠️ [QueryRewrite] VALIDATION FAILED!")
                print(f"   -> Câu hỏi gốc của User: '{query}'")
                print(f"   -> Chuỗi LLM viết lại lỗi: '{rewritten}'")
                print(f"   -> Quyết định: HỦY BỎ chuỗi lỗi, tự động bốc câu gốc chuyển sang Qdrant.")
                return query
                
            # 2. Chống Mất Thực Thể (Entity Validation Guardrail)
            query_lower = query.lower()
            rewritten_lower = rewritten.lower()
            core_entities = ["vàng", "gold", "xauusd", "dxy", "forex", "smc", "fvg", "lãi suất", "fed"]
            
            # Xác định các thực thể trọng tâm có trong câu hỏi gốc
            found_entities = [ent for ent in core_entities if ent in query_lower]
            if found_entities:
                # Nếu câu rewrite KHÔNG bảo toàn được ít nhất một thực thể liên quan -> Hủy bỏ
                # (Vì bộ não LLM gọt quá tay)
                if not any(ent in rewritten_lower for ent in found_entities):
                    print(f"⚠️ [QueryRewrite] VALIDATION FAILED! (Mất từ khóa {found_entities})")
                    print(f"   -> Câu hỏi gốc của User: '{query}'")
                    print(f"   -> Chuỗi LLM viết lại lỗi: '{rewritten}'")
                    print(f"   -> Quyết định: HỦY BỎ chuỗi lỗi, tự động bốc câu gốc chuyển sang Qdrant.")
                    return query

            print(f"✏️ [QueryRewrite] Viết lại thành công: '{rewritten}'")
            return rewritten

        except Exception as e:
            print(f"⚠️ [QueryRewrite] Lỗi: {e}")
            return query

    # =========================================================================
    # 2. MULTI-HOP GENERATION (STREAMING)
    # =========================================================================
    def generate_multihop_stream(
        self,
        query: str,
        context: str,
        chat_history: List[Dict] = None,
        defense_preamble: str = "",
    ) -> Iterator[str]:
        """
        Sinh câu trả lời linh hoạt dựa trên mục đích câu hỏi.
        LLM tự phân tích intent rồi chọn định dạng phù hợp nhất.

        Yields: Từng token/chunk text để streaming lên Streamlit.
        """
        # Xây dựng lịch sử chat gần nhất
        history_messages = []
        if chat_history:
            recent = chat_history[-(Config.MEMORY_WINDOW):]
            for m in recent:
                if m["role"] in ("user", "assistant"):
                    history_messages.append({
                        "role": m["role"],
                        "content": m["content"][:1500]  # Truncate để tiết kiệm token
                    })

        user_content = (
            f"BỐI CẢNH TÀI LIỆU TRÍCH XUẤT TỪ QDRANT DB:\n{context}\n\n"
            "─" * 40 + "\n\n"
            f"CÂU HỎI CỦA TRADER: {query}\n\n"
            "Hãy trả lời CÂU HỎI CỦA TRADER trực tiếp, đi thẳng vào trọng tâm DỰA TRÊN TÀI LIỆU.\n"
            "LƯU Ý: BẮT BUỘC TRẢ LỜI 100% BẰNG TIẾNG VIỆT, BẤT KỂ TÀI LIỆU LÀ TIẾNG GÌ.\n"
            "KHÔNG nhắc lại câu hỏi, KHÔNG giải thích quá trình suy nghĩ. BẮT ĐẦU TRẢ LỜI NGAY:\n"
        )

        messages = [
            {"role": "system", "content": self.SYSTEM_BASE},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        try:
            stream = self._call(messages, stream=True, temperature=0.2)
            if defense_preamble:
                yield defense_preamble
            for chunk in stream:
                if chunk:
                    yield chunk
        except Exception as e:
            yield f"\n\n❌ Lỗi kết nối AI: {e}"

    # =========================================================================
    # 3. SELF-CORRECTION (NON-STREAMING — Vòng kiểm tra ẩn)
    # =========================================================================
    def self_correct(self, answer: str, context: str) -> str:
        """
        Vòng kiểm tra hallucination: Gửi câu trả lời + context gốc,
        yêu cầu LLM xác nhận hoặc hiệu chỉnh số liệu không có trong PDF.

        Chạy 1 lần non-stream sau khi đã có full answer.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là kiểm duyệt viên tài chính. Nhiệm vụ: "
                    "So sánh CÂU TRẢ LỜI với TÀI LIỆU GỐC. "
                    "Nếu có số liệu, tỷ lệ % hoặc điểm giá trong câu trả lời KHÔNG xuất hiện trong tài liệu gốc, "
                    "hãy trả về CHỈ MỘT DÒNG DUY NHẤT: '\n\n⚠️ **Đính chính tự động:** Số liệu [X] không có trong tài liệu.' "
                    "Nếu tất cả đều đúng, trả về chính xác chữ: '[OK]'."
                )
            },
            {
                "role": "user",
                "content": (
                    f"TÀI LIỆU GỐC:\n{context[:3000]}\n\n"
                    f"CÂU TRẢ LỜI CẦN KIỂM TRA:\n{answer}\n\n"
                    "Hãy kiểm tra và trả về câu trả lời đã xác nhận:"
                )
            }
        ]

        try:
            resp = self._call(messages, stream=False, temperature=0.0)
            corrected = resp["message"]["content"].strip()
            return corrected if corrected else answer
        except Exception as e:
            print(f"⚠️ [SelfCorrect] Lỗi: {e}")
            return answer

    # =========================================================================
    # 4. BACKWARD COMPAT — Non-streaming cho test scripts cũ
    # =========================================================================
    def generate_response(self, query: str, context: str) -> str:
        """Non-streaming: Gom toàn bộ stream thành 1 string."""
        tokens = list(self.generate_multihop_stream(query, context))
        return "".join(tokens)


if __name__ == "__main__":
    print("=== SMOKE TEST: LLM SERVICE ===")
    svc = LLMService()

    test_query = "Lạm phát cao ảnh hưởng đến XAUUSD như thế nào?"
    test_ctx   = "[Nguồn: test_doc.pdf]\nKhi lạm phát tăng, Fed thường tăng lãi suất..."

    print("✏️ Test Query Rewriting...")
    rewritten = svc.rewrite_query(test_query)
    print(f"   → {rewritten}")

    print("\n🌊 Test Streaming Generation...")
    for token in svc.generate_multihop_stream(rewritten, test_ctx):
        print(token, end="", flush=True)
    print("\n✅ Done!")