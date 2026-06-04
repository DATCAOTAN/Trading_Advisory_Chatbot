from src.services.vector_service import VectorService
from src.services.llm_service import LLMService

class RAGOrchestrator:
    """
    Facade Design Pattern: Bao bọc sự phức tạp của các dịch vụ tầng dưới (Vector DB, LLM)
    để cung cấp một đầu mối xử lý duy nhất cho tầng giao diện người dùng (UI).
    """
    def __init__(self):
        # Khởi tạo các dịch vụ cốt lõi
        self.vector_service = VectorService()
        self.llm_service = LLMService()

    def sync_knowledge_base(self) -> int:
        """Đầu mối kích hoạt chu trình nạp dữ liệu tĩnh từ PDF vào Qdrant"""
        return self.vector_service.index_documents()

    def query_financial_advisor(self, user_query: str) -> tuple[str, str]:
        """
        Đầu mối xử lý chu trình Hỏi - Đáp động (Inference Pipeline)
        Trả về một tuple gồm: (Câu trả lời của AI, Đoạn ngữ cảnh gốc trích từ PDF)
        """
        # Bước 1: Sang kho Qdrant DB tìm các đoạn văn bản liên quan nhất đến câu hỏi
        context = self.vector_service.retrieve_context(user_query, top_k=3)
        
        # Bước 2: Đẩy câu hỏi và đống tài liệu vừa tìm được sang cho Qwen 2.5 7B suy luận
        ai_response = self.llm_service.generate_response(user_query, context)
        
        return ai_response, context

if __name__ == "__main__":
    # Khung kiểm thử tích hợp (Integration Test) toàn bộ hệ thống RAG dạng đóng
    print("=== KIỂM THỬ TÍCH HỢP TOÀN DIỆN (END-TO-END RAG) ===")
    orchestrator = RAGOrchestrator()
    
    # Thử đặt một câu hỏi thực tế về vàng hoặc chiến lược giao dịch có trong tài liệu của anh
    test_query = "Lạm phát ảnh hưởng như thế nào đến giá vàng?"
    print(f"🤔 Câu hỏi thử nghiệm: '{test_query}'")
    print("⏳ Hệ thống đang truy vấn DB và bắt AI suy luận...")
    
    answer, source_used = orchestrator.query_financial_advisor(test_query)
    
    print("\n" + "="*30 + " KẾT QUẢ TRẢ LỜI " + "="*30)
    print(answer)
    print("\n" + "="*30 + " TÀI LIỆU PHÁP LÝ ĐỐI CHIẾU " + "="*30)
    print(source_used)