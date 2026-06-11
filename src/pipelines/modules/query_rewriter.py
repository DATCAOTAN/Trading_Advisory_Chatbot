import time
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
                    "- Nếu câu hỏi chứa đại từ (nó, điều đó), hãy dùng ngữ cảnh từ lịch sử để thay thế.\n"
                    "- QUAN TRỌNG: Nếu câu hỏi hỏi chung chung về các khái niệm như 'quản lý rủi ro', 'quản lý vốn', 'chỉ báo', 'tâm lý', hãy TỰ ĐỘNG THÊM cụm từ 'trong giao dịch tài chính (Trading/Forex)' vào cuối truy vấn."
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
                print(f"✨ [QueryRewriter] Tối ưu thành ({time.time() - start_t:.2f}s): '{rewritten}'")
                return rewritten
        except Exception as e:
            print(f"⚠️ [QueryRewriter] Bỏ qua vì lỗi API: {e}")
            
        return query
