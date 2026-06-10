from typing import Tuple
from src.core.llm_client import LLMClient

class EvaluatorModule:
    """Đánh giá Hallucination và ép vòng lặp Self-Correction."""
    def __init__(self):
        self.llm_client = LLMClient()
        
    def process(self, answer: str, context: str) -> Tuple[bool, str]:
        """
        Trả về (is_passed, feedback_note)
        Nếu is_passed = False, RAG sẽ bị ép lặp ngược lại.
        """
        if not answer or not context:
            return True, ""
            
        print("🔍 [EvaluatorModule] Kiểm tra chéo lỗi ảo tưởng (Hallucination)...")
        prompt = f"""Bạn là một hệ thống kiểm duyệt tin tức tài chính.
Hãy so sánh CÂU TRẢ LỜI với TÀI LIỆU GỐC.

TÀI LIỆU GỐC:
{context}

CÂU TRẢ LỜI:
{answer}

Nhiệm vụ:
Kiểm tra xem CÂU TRẢ LỜI có chứa thông tin định lượng (giá, mốc thời gian, số liệu, xu hướng) bịa đặt mà không hề xuất hiện trong TÀI LIỆU GỐC hay không.
Nếu phát hiện bịa đặt số liệu hoặc dự đoán sai lệch hoàn toàn so với tài liệu gốc, hãy xuất ra "FAIL: [lý do sai lệch]".
Nếu thông tin hoàn toàn khớp với tài liệu hoặc là suy luận logic từ tài liệu, hãy xuất ra "PASS".
Chỉ xuất ra PASS hoặc FAIL."""

        try:
            response = self.llm_client.chat([{"role": "user", "content": prompt}], stream=False, temperature=0.0)
            result = response.strip().upper()
            if result.startswith("FAIL"):
                reason = response.split(":", 1)[-1].strip() if ":" in response else response
                print(f"⚠️ [EvaluatorModule] Phát hiện ảo tưởng! Đánh rớt: {reason}")
                return False, f"Tôi vừa phát hiện lỗi trong suy luận trước đó: {reason}. Vui lòng thử lại với hướng đi khác."
            print("✅ [EvaluatorModule] Câu trả lời tinh khiết, không ảo tưởng.")
            return True, ""
        except Exception as e:
            print(f"⚠️ [EvaluatorModule] Lỗi module: {e}")
            return True, "" # Fallback an toàn
