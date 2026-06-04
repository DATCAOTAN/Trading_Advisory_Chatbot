import os
from pathlib import Path

class Config:
    # 1. Quản lý các đường dẫn hệ thống (Tự động định vị từ thư mục gốc)
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_PDF_DIR = BASE_DIR / "data" / "raw_pdfs"
    QDRANT_DIR = BASE_DIR / "data" / "qdrant_db"
    
    # 2. Cấu hình các mô hình AI (Đã chốt bản Qwen 7B siêu khôn)
    LLM_MODEL_NAME = "qwen2.5:7b"
    EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
    VECTOR_COLLECTION_NAME = "xauusd_knowledge"
    
    # 3. Tham số kỹ thuật thuật toán RAG (Cắt nhỏ văn bản)
    CHUNK_SIZE = 800       # Độ dài mỗi đoạn văn bản (800 ký tự)
    CHUNK_OVERLAP = 150    # Đoạn gối đầu giữa các chunk để giữ ngữ cảnh không bị ngắt quãng

# Tự động tạo các thư mục vật lý nếu chúng chưa tồn tại trên máy tính
os.makedirs(Config.RAW_PDF_DIR, exist_ok=True)
os.makedirs(Config.QDRANT_DIR, exist_ok=True)