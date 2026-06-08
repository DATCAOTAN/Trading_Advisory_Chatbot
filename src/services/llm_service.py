"""
LLM Service — Nâng cấp toàn diện với:
1. Streaming response (stream=True → generator)
2. Query Rewriting: mở rộng câu hỏi tiếng lóng → chuẩn tài chính
3. Multi-Hop Generation: ép Qwen suy luận theo chuỗi logic tài chính
4. Self-Correction: vòng kiểm tra hallucination (tùy chọn)
"""

from typing import Iterator, List, Dict, Optional
import ollama
from src.config import Config


class LLMService:
    """
    Tầng giao tiếp với Ollama Qwen 2.5 7B.
    Tất cả response đều hỗ trợ streaming để hiển thị chữ chạy từng token trên UI.
    """

    SYSTEM_BASE = (
        "Bạn là một Trợ lý Cố vấn Tài chính Cao cấp chuyên sâu về thị trường Vàng (XAUUSD), "
        "hoạt động tại Việt Nam năm 2026.\n\n"

        "QUY TẮC CỐT LÕI:\n"
        "1. CHỈ dùng thông tin trong 'BỐI CẢNH TÀI LIỆU' để trả lời. TUYỆT ĐỐI không bịa số liệu.\n"
        "2. Nếu thiếu thông tin, nói rõ: 'Kho tài liệu chưa có dữ liệu về vấn đề này.'\n"
        "3. Văn phong: Tiếng Việt chuyên ngành tài chính — nghiêm túc, gãy gọn, lập luận logic.\n"
        "4. TỪ CHỐI mọi câu hỏi ngoài phạm vi tài chính, kinh tế, trading.\n\n"

        "NGUYÊN TẮC PHẢN HỒI — NƯƠNG THEO CÂU HỎI (Context-Aware Formatting):\n"
        "Trước khi trả lời, hãy phân tích 'MỤC ĐÍCH CỐT LÕI' của câu hỏi, rồi chọn định dạng PHÙ HỢP NHẤT:\n\n"

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
        self.model = Config.LLM_MODEL_NAME

    def _call(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: float = 0.2,
    ):
        """Gọi Ollama API, hỗ trợ cả stream và non-stream."""
        return ollama.chat(
            model=self.model,
            messages=messages,
            stream=stream,
            options={"temperature": temperature},
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
                    "Bạn là chuyên gia tài chính. Nhiệm vụ: Viết lại câu hỏi của Trader "
                    "thành một câu truy vấn TÌM KIẾM TRONG VĂN BẢN chuẩn, đầy đủ thuật ngữ tài chính.\n\n"

                    "GUARDRAIL BẮT BUỘC:\n"
                    "- CHỈ được mở rộng ngữ nghĩa khi câu hỏi GỐC ĐÃ CHỨA thuật ngữ chuyên ngành "
                    "(tên tài sản, chỉ báo kỹ thuật, sự kiện kinh tế...).\n"
                    "- Nếu câu hỏi gốc là câu hỏi MỞ, CHUNG CHUNG, hoặc CHƯA có thực thể tài chính rõ ràng "
                    "→ GIỮ NGUYÊN nội dung gốc hoặc chỉ sửa lỗi chính tả. "
                    "TUYỆT ĐỐI KHÔNG ĐƯỢC TỰ Ý BỊA THÊM từ khóa tài chính.\n\n"

                    "VÍ DỤ ĐÚNG:\n"
                    '- "vàng lên hay xuống?" → "Xu hướng giá XAUUSD hiện tại?" (✅ gốc đã có "vàng")\n'
                    '- "OB là gì" → "Order Block là gì trong phân tích SMC?" (✅ gốc đã có "OB")\n'
                    '- "Fed tăng lãi suất thì sao" → "Tác động của việc Fed tăng lãi suất đến giá vàng XAUUSD?" (✅ gốc đã có "Fed", "lãi suất")\n\n'

                    "VÍ DỤ SAI (CẤM LÀM):\n"
                    '- "bạn giúp gì được?" → "xu hướng thị trường vàng gần đây?" (❌ BỊA thêm "thị trường vàng")\n'
                    '- "hello" → "phân tích XAUUSD tuần này?" (❌ BỊA hoàn toàn)\n\n'

                    "Chỉ trả về câu truy vấn mới, KHÔNG giải thích."
                )
            },
            {
                "role": "user",
                "content": (
                    f"{history_summary}"
                    f"Câu hỏi gốc: \"{query}\"\n\n"
                    "Hãy viết lại thành câu truy vấn chuẩn tài chính (1-2 câu, tiếng Việt):"
                )
            }
        ]

        try:
            resp = self._call(messages, stream=False, temperature=0.1)
            rewritten = resp["message"]["content"].strip().strip('"').strip("'")
            print(f"✏️ [QueryRewrite] '{query}' → '{rewritten}'")
            return rewritten if rewritten else query
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
            "Hãy phân tích mục đích cốt lõi của câu hỏi trên, "
            "sau đó trả lời DỰA TRÊN TÀI LIỆU với định dạng phù hợp nhất.\n"
            "CÂU TRẢ LỜI:"
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
                token = chunk["message"]["content"]
                if token:
                    yield token
        except Exception as e:
            yield f"\n\n❌ Lỗi kết nối Ollama: {e}"

    # =========================================================================
    # 3. SELF-CORRECTION (NON-STREAMING — Vòng kiểm tra ẩn)
    # =========================================================================
    def self_correct(self, answer: str, context: str) -> str:
        """
        Vòng kiểm tra hallucination: Gửi câu trả lời + context gốc,
        yêu cầu Qwen xác nhận hoặc hiệu chỉnh số liệu không có trong PDF.

        Chạy 1 lần non-stream sau khi đã có full answer.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là kiểm duyệt viên tài chính. Nhiệm vụ: "
                    "So sánh CÂU TRẢ LỜI với TÀI LIỆU GỐC. "
                    "Nếu có số liệu, tỷ lệ % hoặc điểm giá trong câu trả lời KHÔNG xuất hiện trong tài liệu gốc, "
                    "hãy thêm ghi chú '⚠️ [Cảnh báo: Số liệu X có thể không chính xác]' vào câu trả lời. "
                    "Nếu tất cả đều đúng, trả về câu trả lời nguyên bản."
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