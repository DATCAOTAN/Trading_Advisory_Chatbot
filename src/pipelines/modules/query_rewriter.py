import time
import re
from typing import List, Dict
from src.config import Config
from src.core.llm_client import LLMClient

class QueryRewriterModule:
    """Mô-đun Tiền Xử Lý Truy Vấn: Chuẩn hóa, làm sạch và mở rộng ý định của User."""
    def __init__(self):
        self.llm_client = LLMClient(provider_override="groq")
        
    def process(self, query: str, chat_history: List[Dict] = None) -> str:
        if not Config.ENABLE_QUERY_REWRITING:
            return query
            
        print(f"\n✏️ [QueryRewriter] Đầu vào gốc: '{query}'")

        history_summary = ""
        if chat_history:
            recent = chat_history[-Config.MEMORY_WINDOW:]
            history_lines = [
                f"  [{m['role'].upper()}]: {m['content'][:200]}"
                for m in recent if m["role"] in ("user", "assistant")
            ]
            if history_lines:
                history_summary = "Lịch sử hội thoại:\n" + "\n".join(history_lines) + "\n\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là AI chuyên gia giao dịch. Nhiệm vụ của bạn là VIẾT LẠI câu hỏi của người dùng "
                    "thành một truy vấn tìm kiếm RAG tối ưu. Không trả lời câu hỏi, CHỈ output câu truy vấn mới.\n"
                    "Lưu ý:\n"
                    "- Dịch mọi từ lóng sang thuật ngữ chuẩn.\n"
                    "- Giữ nguyên các mã tài sản (XAUUSD, DXY).\n"
                    "- Nếu câu hỏi chứa đại từ (nó, điều đó) hoặc BỊ KHUYẾT CHỦ NGỮ (đặc biệt là khuyết tên mã tài sản như Vàng, XAUUSD, BTC...), BẮT BUỘC phải tự động nội suy từ lịch sử hội thoại và điền thẳng tên mã tài sản đó vào câu truy vấn mới.\n"
                    "- KHÔNG tự thêm Trading/Forex/XAUUSD/gold/market impact nếu câu hỏi gốc chỉ hỏi về nội dung báo cáo vĩ mô như FOMC, CPI, NFP, GDP, WEO.\n"
                    "- Chỉ thêm bối cảnh Trading/Forex/XAUUSD khi người dùng hỏi rõ về giao dịch, thị trường, vàng, XAUUSD, DXY, USD, lợi suất, entry/SL/TP hoặc tác động giá.\n"
                    "- Nếu câu hỏi hỏi chung chung về các khái niệm trading như 'quản lý rủi ro', 'quản lý vốn', 'chỉ báo', 'tâm lý giao dịch', có thể thêm cụm từ 'trong giao dịch tài chính (Trading/Forex)'."
                )
            },
            {
                "role": "user",
                "content": f"{history_summary}Câu hỏi gốc: {query}\n\nViết lại thành truy vấn tối ưu:"
            }
        ]

        try:
            start_t = time.time()
            response = self.llm_client.chat(messages, stream=False, temperature=0.1)
            rewritten = response["message"]["content"].strip().strip('"').strip("'")
            if rewritten:
                rewritten = self._apply_scope_guard(query, rewritten)
                print(f"✨ [QueryRewriter] Tối ưu thành ({time.time() - start_t:.2f}s): '{rewritten}'")
                return rewritten
        except Exception as e:
            print(f"⚠️ [QueryRewriter] Bỏ qua vì lỗi API: {e}")
            
        return query

    def _apply_scope_guard(self, original_query: str, rewritten_query: str) -> str:
        """Prevent the LLM rewriter from adding market/trading scope unasked."""
        if self._allows_trading_scope(original_query):
            return rewritten_query.strip()

        guarded = rewritten_query.strip()
        guarded = re.sub(
            r"\s*(?:trong|cho)\s+(?:giao dịch\s+)?tài chính\s*\(?\s*Trading\s*/\s*Forex\s*\)?\s*$",
            "",
            guarded,
            flags=re.IGNORECASE,
        ).strip()
        guarded = re.sub(
            r"\s*\(?\s*Trading\s*/\s*Forex\s*\)?\s*$",
            "",
            guarded,
            flags=re.IGNORECASE,
        ).strip()
        if guarded != rewritten_query.strip():
            print("[QueryRewriter] ScopeGuard removed unrequested Trading/Forex context.")
        return guarded or original_query

    @staticmethod
    def _allows_trading_scope(query: str) -> bool:
        text = QueryRewriterModule._normalize(query)
        trading_terms = (
            "trading",
            "forex",
            "giao dich",
            "thi truong",
            "market",
            "anh huong",
            "impact",
            "xauusd",
            "vang",
            "gold",
            "dxy",
            "usd",
            "yield",
            "loi suat trai phieu",
            "entry",
            "sl",
            "tp",
            "buy",
            "sell",
            "mua",
            "ban",
            "gia",
            "price",
            "xu huong",
            "trend",
        )
        return any(term in text for term in trading_terms)

    @staticmethod
    def _normalize(value: str) -> str:
        import unicodedata

        text = str(value or "").lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
