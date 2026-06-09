"""
Intent Router v3 — LLM Gatekeeper + Few-Shot Prompting + Phản hồi GREETING linh hoạt.

Sử dụng LLM (qua OpenRouter/Ollama) để phân loại ý định
người dùng thành 3 nhóm:

  GREETING      → Chào hỏi, tạm biệt, cảm ơn, chúc tụng  → Qwen trả lời xã giao linh hoạt
  TRASH         → Vô nghĩa, gõ bừa, lạc đề               → cảnh báo tĩnh, KHÔNG RAG
  FINANCIAL_RAG → Câu hỏi tài chính hợp lệ                → kích hoạt FULL pipeline

Cơ chế hoạt động:
  1. Gatekeeper phân loại intent qua Few-Shot System Prompt (temperature=0.0)
  2. Nếu GREETING → gọi thêm 1 lượt Qwen nhẹ để sinh câu trả lời tự nhiên
  3. Nếu TRASH → trả câu cảnh báo tĩnh, không tốn LLM
  4. Nếu FINANCIAL_RAG → trả về để orchestrator kích hoạt pipeline nặng
"""

import json
import re
from enum import Enum
from typing import Dict, Optional, Iterator

from src.config import Config
from src.core.llm_client import LLMClient


# =============================================================================
# ENUM — 3 loại Intent duy nhất
# =============================================================================
class IntentType(str, Enum):
    GREETING      = "GREETING"
    TRASH         = "TRASH"
    FINANCIAL_RAG = "FINANCIAL_RAG"


# =============================================================================
# SYSTEM PROMPT — Gatekeeper với Few-Shot Prompting (temperature=0.0)
# =============================================================================
_GATEKEEPER_SYSTEM_PROMPT = """\
Bạn là bộ lọc phân loại ý định (Intent Router) cấp cao cho một hệ thống AI Cố vấn Tài chính Forex/SMC.
Nhiệm vụ của bạn là đọc câu hỏi của người dùng và trả về kết quả định dạng JSON chính xác 100%.

Hãy phân loại câu hỏi vào một trong ba nhóm (intent) sau:

1. 'GREETING': Bao gồm TẤT CẢ các trường hợp sau:
   a) Chào hỏi, tạm biệt, cảm ơn, lời chúc xã giao (hello, xin chào, tạm biệt, bye, cảm ơn...).
   b) Hỏi về NĂNG LỰC / CHỨC NĂNG / PHẠM VI TƯ VẤN của Bot mà CHƯA kèm thuật ngữ chuyên ngành cụ thể
      (Ví dụ: "bạn giúp gì được?", "bot biết những gì?", "cho tôi biết khả năng của bạn").
   c) Hỏi về CÁCH SỬ DỤNG / HƯỚNG DẪN VẬN HÀNH / TÍNH NĂNG KỸ THUẬT của chính hệ thống này
      (Ví dụ: "AI Pipeline là gì?", "khi nào nên bật Reranker?", "Hybrid Search hoạt động thế nào?",
       "giải thích các tùy chọn trong cấu hình", "khi nào nên sài các tính năng AI pipeline",
       "Query Rewrite để làm gì?", "Self-Correction là gì?").
      → Đây là câu hỏi hỗ trợ kỹ thuật phần mềm, KHÔNG phải lạc đề, KHÔNG phải TRASH.

2. 'TRASH': Chuỗi ký tự vô nghĩa do đè phím (jdjdjd, asdasd), gõ sai bộ gõ, hoặc câu hỏi lạc đề
   hoàn toàn không liên quan tài chính VÀ không liên quan đến hệ thống (trưa nay ăn gì, cách nấu phở).

3. 'FINANCIAL_RAG': Câu hỏi PHẢI CHỨA ÍT NHẤT MỘT thực thể/thuật ngữ tài chính cụ thể như:
   tên tài sản (XAUUSD, vàng, USD, DXY), thuật ngữ kỹ thuật giao dịch (SMC, Order Block, FVG, ChoCh,
   BOS, Price Action, Entry, SL, TP), hoặc sự kiện kinh tế (Fed, CPI, NFP, lạm phát, lãi suất).
   LƯU Ý: Các từ "AI Pipeline", "Reranker", "Hybrid Search", "Query Rewrite", "cấu hình hệ thống"
   là thuật ngữ CỦA HỆ THỐNG, KHÔNG PHẢI thuật ngữ tài chính → phân loại GREETING, không phải FINANCIAL_RAG.

QUY TẮC BẮT BUỘC:
- CHỈ trả về một chuỗi JSON duy nhất có cấu trúc: {"intent": "TÊN_NHÓM", "reason": "lý do ngắn gọn"}
- Không viết thêm bất kỳ chữ nào ngoài khối JSON.

VÍ DỤ ĐỂ HỌC (FEW-SHOT EXAMPLES):
- "chào bạn" -> {"intent": "GREETING", "reason": "User chào hỏi"}
- "tạm biệt" -> {"intent": "GREETING", "reason": "User chào kết thúc"}
- "cảm ơn nhé" -> {"intent": "GREETING", "reason": "User gửi lời cảm ơn"}
- "bạn có thể giúp gì được cho tôi?" -> {"intent": "GREETING", "reason": "Hỏi năng lực Bot"}
- "bạn là ai" -> {"intent": "GREETING", "reason": "Hỏi danh tính Bot"}
- "khi nào tôi nên sài các tính năng AI pipeline trong cấu hình?" -> {"intent": "GREETING", "reason": "Hỏi hướng dẫn sử dụng tính năng hệ thống"}
- "Hybrid Search là gì?" -> {"intent": "GREETING", "reason": "Hỏi giải thích tính năng kỹ thuật của hệ thống"}
- "Reranker hoạt động thế nào?" -> {"intent": "GREETING", "reason": "Hỏi cơ chế hoạt động của module hệ thống"}
- "giải thích các tùy chọn trong tab cấu hình" -> {"intent": "GREETING", "reason": "Hỏi hướng dẫn sử dụng giao diện"}
- "Query Rewrite để làm gì?" -> {"intent": "GREETING", "reason": "Hỏi chức năng module của hệ thống"}
- "Self-Correction nghĩa là gì?" -> {"intent": "GREETING", "reason": "Hỏi giải thích tính năng hệ thống"}
- "jjdjdj" -> {"intent": "TRASH", "reason": "Chuỗi ký tự vô nghĩa"}
- "trưa nay ăn gì" -> {"intent": "TRASH", "reason": "Lạc đề hoàn toàn"}
- "Quét thanh khoản SMC đánh sao?" -> {"intent": "FINANCIAL_RAG", "reason": "Hỏi kỹ thuật giao dịch SMC"}
- "Vàng xu hướng thế nào em" -> {"intent": "FINANCIAL_RAG", "reason": "Tra cứu xu hướng XAUUSD"}
- "Order Block là gì?" -> {"intent": "FINANCIAL_RAG", "reason": "Thuật ngữ kỹ thuật SMC cụ thể"}
- "Lạm phát ảnh hưởng gì đến giá vàng?" -> {"intent": "FINANCIAL_RAG", "reason": "Thực thể kinh tế + tài sản cụ thể"}
"""


# =============================================================================
# SYSTEM PROMPT — Phản hồi GREETING linh hoạt (Qwen tự viết câu trả lời)
# =============================================================================
_GREETING_RESPONDER_PROMPT = """\
Bạn là AI Cố vấn Tài chính chuyên về thị trường Vàng (XAUUSD) và Forex.
Bạn là một AI Cố vấn Tài chính chuyên về thị trường Vàng (XAUUSD) và Forex. 
Người dùng vừa gửi một câu giao tiếp xã giao, hỏi về khả năng/phạm vi tư vấn, hoặc hỏi về cách sử dụng/tính năng kỹ thuật của hệ thống.
Nhiệm vụ của bạn: Hãy trả lời câu chào của người dùng một cách thân thiện, ngắn gọn và chuyên nghiệp trong vòng 2-3 câu. Giới thiệu nhanh bạn có thể giúp họ phân tích kỹ thuật, SMC hoặc dữ liệu vĩ mô. 
QUY TẮC CHÍ MẠNG: Không dài dòng, không bịa kiến thức khi chưa có tài liệu RAG, nhả chữ ngay lập tức.\
NHIỆM VỤ: Đọc câu nói của người dùng và phản hồi một cách TỰ NHIÊN, LỊCH SỰ, CHUYÊN NGHIỆP.
QUY TẮC:
1. Nếu người dùng CHÀO HỎI → Chào lại và tự giới thiệu ngắn gọn.
2. Nếu người dùng TẠM BIỆT → Chào tạm biệt, chúc giao dịch thuận lợi.
3. Nếu người dùng CẢM ƠN → Đáp lại lịch sự.
4. Nếu người dùng GỬI LỜI CHÚC → Đáp lại bằng lời chúc tương xứng.
5. Nếu người dùng HỎI BẠN LÀ AI → Giới thiệu ngắn: Bạn là AI Cố vấn Tài chính XAUUSD, được vận hành bởi mô hình {model_name} thông qua kiến trúc RAG.
6. Nếu người dùng HỎI NĂNG LỰC / GIÚP GÌ → Liệt kê ngắn gọn phạm vi kiến thức bằng gạch đầu dòng.
7. Nếu người dùng HỎI VỀ TÍNH NĂNG / CẤU HÌNH HỆ THỐNG → Giải thích kỹ thuật dễ hiểu dựa trên kiến thức sau:
   KIẾN THỨC VỀ CÁC TÍNH NĂNG HỆ THỐNG (dùng để trả lời khi user hỏi):
   • **Query Rewriting (Viết lại câu hỏi):**
     Tự động mở rộng câu hỏi ngắn/tiếng lóng của Trader thành câu truy vấn chuẩn tài chính.
     Ví dụ: "vàng lên hay xuống?" → "Xu hướng giá XAUUSD trong bối cảnh DXY và lãi suất Fed?"
     → BẬT khi hỏi nhanh bằng tiếng lóng. TẮT khi câu hỏi đã đầy đủ thuật ngữ chuyên ngành.
   • **Hybrid Search (Tìm kiếm lai):**
     Kết hợp Dense Vector (ngữ nghĩa) + Sparse Vector (từ khóa chính xác) để tìm tài liệu.
     → BẬT để tìm kiếm sâu hơn, đặc biệt với câu hỏi phức tạp có thuật ngữ chuyên ngành.
     → TẮT nếu muốn tiết kiệm thời gian xử lý cho câu hỏi đơn giản.
   • **BGE Reranker (Chấm điểm lại):**
     Sau khi tìm được top 10 đoạn tài liệu, Reranker chấm điểm lại để chọn 3 đoạn chính xác nhất.
     → BẬT khi cần câu trả lời chính xác cao (phân tích chiến lược, mốc giá cụ thể).
     → TẮT khi muốn phản hồi nhanh hơn (~1-2 giây), chấp nhận độ chính xác thấp hơn.
   • **Self-Correction (Tự kiểm tra):**
     Sau khi AI trả lời, hệ thống chạy thêm 1 vòng kiểm tra hallucination — so sánh câu trả lời
     với tài liệu gốc, đánh dấu cảnh báo nếu phát hiện số liệu bịa.
     → BẬT khi cần độ tin cậy tuyệt đối (báo cáo cho khách hàng, ra quyết định giao dịch).
     → TẮT cho chat thông thường vì chậm thêm ~30-50%.
   • **Tổng hợp — Khi nào bật tất cả?**
     Bật đầy đủ AI Pipeline (Query Rewrite + Hybrid Search + Reranker + Self-Correction) khi:
     cần phân tích chiến lược sâu, xác định mốc Entry/SL/TP, hoặc đưa ra quyết định giao dịch.
     Tắt bớt khi chỉ chat xã giao, hỏi khái niệm đơn giản, hoặc muốn tiết kiệm tài nguyên.
PHONG CÁCH:
- Tiếng Việt tự nhiên, thân thiện nhưng chuyên nghiệp.
- Trả lời phù hợp với độ phức tạp của câu hỏi: xã giao → 2-3 câu, hướng dẫn kỹ thuật → chi tiết hơn.
- KHÔNG rập khuôn, mỗi lần trả lời nên khác nhau một chút.
- Có emoji phù hợp.\
"""


# =============================================================================
# CLASS CHÍNH
# =============================================================================
class IntentRouter:
    """
    LLM Gatekeeper v3 — Few-Shot Prompting + Phản hồi GREETING linh hoạt.

    Thay đổi so với v2:
    - System Prompt dùng Few-Shot Examples để Qwen học từ ví dụ cụ thể
    - GREETING response do Qwen sinh linh hoạt (không rập khuôn if/elif)
    - Loại bỏ hoàn toàn logic Python rẽ nhánh thủ công cho GREETING
    """

    @staticmethod
    def classify(query: str, chat_history: list = None) -> IntentType:
        """
        Gửi câu hỏi tới LLM Gatekeeper (temperature=0.0) để phân loại ý định.

        Args:
            query: Câu hỏi thô từ người dùng
            chat_history: Lịch sử hội thoại để kế thừa bối cảnh

        Returns:
            IntentType enum (GREETING | TRASH | FINANCIAL_RAG)
        """
        print(f"🚪 [Gatekeeper] Phân loại: '{query}'")

        try:
            # ── Bổ sung lịch sử để kế thừa bối cảnh ──
            history_text = ""
            if chat_history:
                recent = chat_history[-4:] # Lấy 4 tin nhắn gần nhất
                lines = [f"[{m['role'].upper()}]: {m['content'][:100]}" for m in recent]
                history_text = "LỊCH SỬ GẦN ĐÂY:\n" + "\n".join(lines) + "\n\n"

            prompt_content = f"{history_text}CÂU HỎI MỚI CỦA NGƯỜI DÙNG: {query}"

            # ── Gọi LLM Router (temperature=0.0) ──
            client = LLMClient()
            response = client.chat(
                messages=[
                    {"role": "system", "content": _GATEKEEPER_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt_content},
                ],
                stream=False,
                temperature=0.0,
            )

            raw_output = response["message"]["content"].strip()
            print(f"🚪 [Gatekeeper] Raw LLM output: {raw_output}")

            # ── Bóc tách JSON an toàn ──
            result = _parse_gatekeeper_json(raw_output)

            if result is None:
                print("⚠️ [Gatekeeper] Không parse được JSON → fallback FINANCIAL_RAG")
                return IntentType.FINANCIAL_RAG

            intent_str = result.get("intent", "").upper().strip()
            reason     = result.get("reason", "không rõ")

            # ── Map chuỗi → enum, chỉ chấp nhận 3 giá trị hợp lệ ──
            intent_map = {
                "GREETING":      IntentType.GREETING,
                "TRASH":         IntentType.TRASH,
                "FINANCIAL_RAG": IntentType.FINANCIAL_RAG,
            }

            intent = intent_map.get(intent_str, IntentType.FINANCIAL_RAG)
            print(f"🚪 [Gatekeeper] → {intent.value} | Lý do: {reason}")
            return intent

        except Exception as e:
            print(f"❌ [Gatekeeper] Lỗi API: {e} → fallback FINANCIAL_RAG")
            return IntentType.FINANCIAL_RAG

    # =========================================================================
    # PHẢN HỒI GREETING — Qwen tự sinh câu trả lời linh hoạt, tự nhiên
    # =========================================================================
    @staticmethod
    def get_greeting_response(query: str) -> Iterator[str]:
        """
        Gọi LLM để sinh câu phản hồi xã giao TỰ NHIÊN dựa trên
        nội dung câu nói của người dùng (chào/biệt/cảm ơn/chúc).

        Không dùng if/elif rẽ nhánh thủ công — hoàn toàn do LLM quyết định
        cách trả lời phù hợp với ngữ cảnh.

        Args:
            query: Câu nói xã giao gốc từ người dùng

        Yields:
            Từng token/chunk text để streaming lên Streamlit
        """
        print(f"👋 [Greeting] LLM sinh phản hồi cho: '{query}'")

        try:
            # Xác định tên model đang chạy thực tế
            if Config.LLM_PROVIDER == "openrouter":
                active_model = Config.OPENROUTER_MODEL_NAME
            elif Config.LLM_PROVIDER == "google":
                active_model = Config.GOOGLE_MODEL_NAME
            elif Config.LLM_PROVIDER == "groq":
                active_model = Config.GROQ_MODEL_NAME
            else:
                active_model = Config.LLM_MODEL_NAME

            dynamic_prompt = _GREETING_RESPONDER_PROMPT.format(model_name=active_model)

            client = LLMClient()
            stream = client.chat(
                messages=[
                    {"role": "system", "content": dynamic_prompt},
                    {"role": "user",   "content": query},
                ],
                stream=True,
                temperature=0.7,
            )

            for chunk in stream:
                if chunk:
                    yield chunk

        except Exception as e:
            # Fallback tĩnh nếu Ollama lỗi
            print(f"⚠️ [Greeting] Lỗi Ollama: {e} → dùng câu trả lời mặc định")
            yield (
                "Xin chào! Tôi là AI Cố vấn Tài chính XAUUSD. "
                "Hãy đặt câu hỏi về thị trường để tôi hỗ trợ bạn! 📈"
            )

    # =========================================================================
    # CÂU TRẢ LỜI TĨNH — TRASH (cảnh báo ngay, tiết kiệm tài nguyên)
    # =========================================================================
    @staticmethod
    def get_trash_response() -> str:
        """Thông báo cảnh báo khi input vô nghĩa hoặc lạc đề."""
        return (
            "⚠️ **Yêu cầu không rõ ràng hoặc nằm ngoài phạm vi tư vấn.**\n\n"
            "Tôi là Trợ lý chuyên về thị trường Vàng (XAUUSD). "
            "Vui lòng nhập câu hỏi cụ thể về thị trường, ví dụ:\n\n"
            "- *\"Cấu trúc SMC hiện tại của XAUUSD?\"*\n"
            "- *\"Lạm phát ảnh hưởng đến giá vàng như thế nào?\"*\n"
            "- *\"Chiến lược Entry/SL/TP cho tuần này?\"*\n"
            "- *\"Báo cáo NFP tác động gì đến DXY?\"*"
        )


# =============================================================================
# HÀM TIỆN ÍCH NỘI BỘ — Bóc tách JSON từ output LLM
# =============================================================================
def _parse_gatekeeper_json(raw: str) -> Optional[Dict]:
    """
    Parse JSON từ output của Gatekeeper LLM.

    LLM đôi khi trả về JSON kèm markdown (```json ... ```) hoặc text thừa.
    Hàm này cố gắng trích xuất JSON bằng nhiều cách:
    1. json.loads() trực tiếp
    2. Tìm khối {...} bằng regex rồi parse
    3. Trả về None nếu hoàn toàn không parse được

    Args:
        raw: Chuỗi thô từ LLM

    Returns:
        Dict chứa {"intent": ..., "reason": ...} hoặc None
    """
    # Cách 1: Parse trực tiếp
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Cách 2: Trích xuất khối JSON đầu tiên trong chuỗi
    json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except (json.JSONDecodeError, TypeError):
            pass

    # Cách 3: Thất bại hoàn toàn
    return None
