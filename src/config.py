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
    # 2. CẤU HÌNH MÔ HÌNH AI
    # =========================================================================
    LLM_MODEL_NAME         = "qwen2.5:7b"
    EMBEDDING_MODEL_NAME   = "BAAI/bge-m3"
    RERANKER_MODEL_NAME    = "BAAI/bge-reranker-v2-m3"
    VECTOR_COLLECTION_NAME = "xauusd_knowledge_v2"

    # =========================================================================
    # 3. CHUNKING — PARENT-CHILD
    # =========================================================================
    PARENT_CHUNK_SIZE    = 2000
    PARENT_CHUNK_OVERLAP = 200
    CHILD_CHUNK_SIZE     = 400
    CHILD_CHUNK_OVERLAP  = 80
    # Backward compat
    CHUNK_SIZE    = CHILD_CHUNK_SIZE
    CHUNK_OVERLAP = CHILD_CHUNK_OVERLAP

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