"""
Config Settings — Trung tâm cấu hình duy nhất của toàn hệ thống.

Nguyên lý SOLID (Single Responsibility):
  - File này CHỈ chứa thông số cấu hình, KHÔNG chứa logic nghiệp vụ.

Defensive Programming:
  - Tất cả đường dẫn dùng Path.resolve() — định vị động tuyệt đối.
  - Không bao giờ gãy khi di chuyển dự án sang máy khác, Docker, hay Linux.
  - Tự động tạo thư mục cần thiết khi import.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load biến môi trường từ file .env (nếu có)
load_dotenv()


class Config:
    # =========================================================================
    # 1. ĐƯỜNG DẪN HỆ THỐNG (Defensive Programming — Path.resolve())
    # =========================================================================
    # Gốc dự án: src/ -> lùi 1 cấp = project root
    BASE_DIR = Path(__file__).resolve().parent.parent

    # ── Phân vùng DỮ LIỆU ──────────────────────────────────────────────────
    DATA_DIR        = BASE_DIR / "data"
    STATIC_PDF_DIR  = DATA_DIR / "raw_pdfs" / "static"    # Sách, phương pháp luận cứng
    DYNAMIC_PDF_DIR = DATA_DIR / "raw_pdfs" / "dynamic"   # Báo cáo vĩ mô cập nhật
    RAW_PDF_DIR     = DATA_DIR / "raw_pdfs"                # Gốc (backward compat)
    QDRANT_DIR      = DATA_DIR / "qdrant_db"               # Vector database

    # ── Phân vùng TRẠNG THÁI ────────────────────────────────────────────────
    INGESTION_STATE_FILE = DATA_DIR / "ingestion_state.json"  # SHA-256 tracking

    # ── Phân vùng LOG ───────────────────────────────────────────────────────
    LOGS_DIR = BASE_DIR / "logs"

    # =========================================================================
    # 2. CẤU HÌNH DATABASE / CACHE (HYBRID STORAGE)
    # =========================================================================
    REDIS_URL              = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MONGO_URI              = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

    # =========================================================================
    # 3. CẤU HÌNH MÔ HÌNH AI & PROVIDER
    # =========================================================================
    LLM_PROVIDER           = os.getenv("LLM_PROVIDER", "openrouter").lower()
    
    # ── OpenRouter API ──
    OPENROUTER_API_KEY     = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL_NAME  = os.getenv("OPENROUTER_MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b:free")
    
    # ── Groq API (Fallback hoặc Tùy chọn) ──
    GROQ_API_KEY           = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL_NAME        = os.getenv("GROQ_MODEL_NAME", "qwen-3-32b")
    
    # ── Google AI Studio API (OpenAI Compatible) ──
    GOOGLE_API_KEY         = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL_NAME      = os.getenv("GOOGLE_MODEL_NAME", "gemini-2.5-flash")
    
    
    # ── Cohere API (Reranker) ──
    COHERE_API_KEY         = os.getenv("COHERE_API_KEY", "")
    
    LLM_MODEL_NAME         = "qwen2.5:7b"           # Model Local Ollama
    EMBEDDING_MODEL_NAME   = "BAAI/bge-m3"
    RERANKER_MODEL_NAME    = "BAAI/bge-reranker-v2-m3"
    VECTOR_COLLECTION_NAME = "xauusd_knowledge_v2"

    # ── Live Data APIs ──
    OANDA_API_KEY          = os.getenv("OANDA_API_KEY", "")
    OANDA_ACCOUNT_ID       = os.getenv("OANDA_ACCOUNT_ID", "")
    TWELVE_DATA_API_KEY    = os.getenv("TWELVE_DATA_API_KEY", "")
    BINANCE_API_KEY        = os.getenv("BINANCE_API_KEY", "")

    # =========================================================================
    # 4. CHUNKING — PARENT-CHILD
    # =========================================================================
    PARENT_CHUNK_SIZE    = 2000
    PARENT_CHUNK_OVERLAP = 200
    CHILD_CHUNK_SIZE     = 400
    CHILD_CHUNK_OVERLAP  = 80
    # Backward compat
    CHUNK_SIZE    = CHILD_CHUNK_SIZE
    CHUNK_OVERLAP = CHILD_CHUNK_OVERLAP

    # Tùy chỉnh Chunk theo ngữ cảnh thư mục (Adaptive Chunking)
    ADAPTIVE_CHUNK_CONFIG = {
        "indicators": {
            "parent_size": 1500, "parent_overlap": 150,
            "child_size": 300, "child_overlap": 50
        },
        "price_action": {
            "parent_size": 1500, "parent_overlap": 150,
            "child_size": 300, "child_overlap": 50
        },
        "smc": {
            "parent_size": 2000, "parent_overlap": 200,
            "child_size": 400, "child_overlap": 80
        },
        "macro_reports": {
            "parent_size": 3000, "parent_overlap": 300,
            "child_size": 600, "child_overlap": 100
        },
        "risk_management": {
            "parent_size": 3000, "parent_overlap": 300,
            "child_size": 800, "child_overlap": 150
        },
        "default": {
            "parent_size": PARENT_CHUNK_SIZE, "parent_overlap": PARENT_CHUNK_OVERLAP,
            "child_size": CHILD_CHUNK_SIZE, "child_overlap": CHILD_CHUNK_OVERLAP
        }
    }

    # =========================================================================
    # 4. PIPELINE RETRIEVAL
    # =========================================================================
    # ── HYBRID SEARCH & RERANK ──
    RETRIEVAL_TOP_K = 10     # Số tài liệu thô lấy ra từ Vector DB
    RERANK_TOP_N    = 3      # Số tài liệu chất lượng nhất giữ lại sau khi Rerank (Context Trimming)

    # =========================================================================
    # 5. FEATURE FLAGS — Bật/tắt qua Sidebar hoặc đây
    # =========================================================================
    ENABLE_HYBRID_SEARCH    = True
    ENABLE_RERANKER         = True
    ENABLE_SELF_CORRECTION  = False
    ENABLE_QUERY_REWRITING  = True

    # =========================================================================
    # 6. BỘ NHỚ HỘI THOẠI
    # =========================================================================
    MEMORY_WINDOW = 6


# =============================================================================
# AUTO-INIT: Tự động tạo tất cả thư mục cần thiết khi import
# =============================================================================
for _dir in [
    Config.STATIC_PDF_DIR,
    Config.DYNAMIC_PDF_DIR,
    Config.QDRANT_DIR,
    Config.LOGS_DIR,
]:
    os.makedirs(_dir, exist_ok=True)