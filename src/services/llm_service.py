import ollama
from src.config import Config

class LLMService:
    def __init__(self):
        # Lấy tên mô hình qwen2.5:7b từ file cấu hình tập trung
        self.model_name = Config.LLM_MODEL_NAME

    def generate_response(self, query: str, context: str) -> str:
        """
        Đóng gói System Prompt cấu trúc cao + Ngữ cảnh RAG + Câu hỏi 
        để ép mô hình Qwen 2.5 7B suy luận logic.
        """
        system_prompt = (
            "Bạn là một Trợ lý Cố vấn Tài chính Cao cấp chuyên sâu về thị trường Vàng (XAUUSD).\n"
            "Nhiệm vụ của bạn là đưa ra các phân tích xu hướng và tư vấn kỹ thuật dựa trên tài liệu được cung cấp.\n\n"
            "QUY TẮC SUY LUẬN TỐI CAO:\n"
            "1. CHỈ sử dụng thông tin được cung cấp trong phần 'BỐI CẢNH TÀI LIỆU' để trả lời.\n"
            "2. Nếu thông tin không có trong tài liệu, hãy trả lời: 'Tôi không tìm thấy dữ liệu này trong kho chiến lược của tôi.' Tuyệt đối không tự bịa ra số liệu hoặc xu hướng.\n"
            "3. Nếu tài liệu chứa các con số toán học, điểm Entry, SL, TP hoặc dữ liệu lạm phát, hãy trích xuất chính xác và trình bày rõ ràng bằng bảng biểu hoặc gạch đầu dòng.\n"
            "4. Văn phong trả lời phải là tiếng Việt chuyên ngành tài chính, nghiêm túc, gãy gọn, có tính lập luận cao.\n"
            "5. TUYỆT ĐỐI từ chối trả lời các câu hỏi nằm ngoài phạm vi tài chính, kinh tế và trading."
        )

        # Cấu trúc hóa nội dung đẩy vào mô hình
        user_content = (
            f"BỐI CẢNH TÀI LIỆU ĐƯỢC TRÍCH XUẤT TỪ DB:\n{context}\n\n"
            f"CÂU HỎI CỦA TRADER: {query}\n"
            f"CÂU TRẢ LỜI CỦA CHUYÊN GIA TÀI CHÍNH:"
        )

        try:
            # Gọi API cục bộ của Ollama chạy dưới nền máy tính
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                options={
                    "temperature": 0.2  # Đặt temp thấp để AI trả lời thực tế, bám sát tài liệu, không "sáng tạo" bừa
                }
            )
            return response['message']['content']
        except Exception as e:
            return f"❌ Lỗi kết nối đến dịch vụ Ollama (Qwen 2.5): {str(e)}"

if __name__ == "__main__":
    # Khung kiểm thử độc lập xem bộ não Ollama đã thức dậy chưa
    print("=== KIỂM THỬ KẾT NỐI BỘ NÃO LLM LOCAL ===")
    llm = LLMService()
    
    test_query = "Kiểm tra kết nối. Bạn tên là gì và chuyên môn của bạn là gì?"
    test_context = "Tài liệu mẫu: Hệ thống AI tư vấn tài chính đang hoạt động ổn định."
    
    print(f"💬 Đang gửi câu hỏi thử nghiệm tới {Config.LLM_MODEL_NAME}...")
    reply = llm.generate_response(test_query, test_context)
    print("\n🤖 AI PHẢN HỒI:")
    print(reply)