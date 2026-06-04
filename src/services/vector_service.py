import os
from qdrant_client.models import Distance, VectorParams, PointStruct
from src.config import Config
from src.core.database import QdrantDatabaseProvider
from src.services.parser_service import PDFParserService

class VectorService:
    def __init__(self):
        # Gọi qua bộ kết nối duy nhất (Singleton Provider)
        db_provider = QdrantDatabaseProvider()
        self.client = db_provider.qdrant_client
        self.embed_model = db_provider.embedding_model
        self._init_collection()

    def _init_collection(self):
        """Khởi tạo kho chứa (Collection) trong Qdrant nếu chưa tồn tại"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if Config.VECTOR_COLLECTION_NAME not in collection_names:
            print(f"📦 [Qdrant] Khởi tạo kho chứa tri thức mới: {Config.VECTOR_COLLECTION_NAME}")
            # Mô hình BGE-M3 sinh ra không gian vector có kích thước 1024 chiều
            self.client.create_collection(
                collection_name=Config.VECTOR_COLLECTION_NAME,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
            )

    def index_documents(self) -> int:
        """Kích hoạt chu trình: Đọc dữ liệu -> Số hóa -> Đẩy vào Vector DB"""
        chunks = PDFParserService.extract_chunks_from_folder()
        if not chunks:
            print("⚠️ Cảnh báo: Không có đoạn văn bản nào để số hóa!")
            return 0

        print(f"🧠 Đang mã hóa toán học và nạp {len(chunks)} đoạn tri thức vào DB. Xin vui lòng đợi...")
        points = []
        
        for idx, chunk in enumerate(chunks):
            # Biến chuỗi văn bản thô thành danh sách số thực (Vector 1024 chiều)
            vector = self.embed_model.encode(chunk["text"]).tolist()
            
            # Đóng gói cấu trúc điểm lưu trữ dữ liệu của Qdrant kèm theo Metadata nguồn file
            points.append(
                PointStruct(
                    id=idx,
                    vector=vector,
                    payload={
                        "text": chunk["text"],
                        "source": chunk["metadata"]["source"]
                    }
                )
            )
            
        # Đẩy dữ liệu hàng loạt xuống ổ cứng
        self.client.upsert(collection_name=Config.VECTOR_COLLECTION_NAME, points=points)
        print("✅ Đã hoàn thành số hóa! Toàn bộ tri thức đã được khóa chặt trong Qdrant DB.")
        return len(points)
    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """
        Biến câu hỏi của Trader thành Vector và tra cứu Top K 
        đoạn văn bản có độ tương đồng cao nhất trong Qdrant DB.
        """
        # 1. Chuyển câu hỏi thô thành dãy số Vector 1024 chiều
        query_vector = self.embed_model.encode(query).tolist()
        
        # 2. Thực hiện tìm kiếm không gian (Vector Search) trong Qdrant Collection
        search_results = self.client.search(
            collection_name=Config.VECTOR_COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k
        )
        
        # 3. Gộp các đoạn văn bản trích xuất được kèm theo nguồn file để làm bằng chứng (Context)
        extracted_contexts = []
        for res in search_results:
            source_file = res.payload.get("source", "Không rõ nguồn")
            text_content = res.payload.get("text", "")
            extracted_contexts.append(f"[Trích nguồn: {source_file}]\n{text_content}")
            
        # Trả về một chuỗi văn bản lớn phân tách bằng các dấu gạch ngang
        return "\n\n---\n\n".join(extracted_contexts)

if __name__ == "__main__":
    # Khung kiểm thử độc lập chu trình nạp dữ liệu
    print("=== TRIỂN KHAI PIPELINE NẠP DỮ LIỆU VÀO VECTOR DB ===")
    service = VectorService()
    service.index_documents()