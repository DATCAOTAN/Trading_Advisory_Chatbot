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


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


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
    GOOGLE_MODEL_NAME      = os.getenv("GOOGLE_MODEL_NAME", "gemini-3.1-flash-lite")
    GOOGLE_FALLBACK_MODEL_NAME = os.getenv("GOOGLE_FALLBACK_MODEL_NAME", "gemini-flash-latest")
    
    
    # ── Cohere API (Reranker) ──
    COHERE_API_KEY         = os.getenv("COHERE_API_KEY", "")
    
    LLM_MODEL_NAME         = "qwen2.5:7b"           # Model Local Ollama
    EMBEDDING_MODEL_NAME   = "BAAI/bge-m3"
    RERANKER_MODEL_NAME    = "BAAI/bge-reranker-v2-m3"
    VECTOR_COLLECTION_NAME = "xauusd_knowledge_v2"
    PDF_PARSER_MODE        = os.getenv("PDF_PARSER_MODE", "pymupdf").strip().lower()
    MINERU_COMMAND         = os.getenv("MINERU_COMMAND", "mineru").strip()
    MINERU_BACKEND         = os.getenv("MINERU_BACKEND", "pipeline").strip()
    MINERU_METHOD          = os.getenv("MINERU_METHOD", "auto").strip()
    MINERU_TIMEOUT_SECONDS = _env_int("MINERU_TIMEOUT_SECONDS", 1800)
    MINERU_PARSE_BOOKS     = _env_bool("MINERU_PARSE_BOOKS", False)
    MINERU_SELECTIVE_BOOK_PAGES_ENABLED = _env_bool("MINERU_SELECTIVE_BOOK_PAGES_ENABLED", True)
    MINERU_SELECTIVE_MAX_PAGES_PER_DOC = _env_int("MINERU_SELECTIVE_MAX_PAGES_PER_DOC", 5)
    MINERU_SELECTIVE_MAX_RANGES_PER_DOC = _env_int("MINERU_SELECTIVE_MAX_RANGES_PER_DOC", 5)
    MINERU_SELECTIVE_LOW_TEXT_CHARS = _env_int("MINERU_SELECTIVE_LOW_TEXT_CHARS", 300)
    MINERU_SELECTIVE_TABLE_LIKE_THRESHOLD = _env_float("MINERU_SELECTIVE_TABLE_LIKE_THRESHOLD", 0.25)
    MINERU_SELECTIVE_IMAGE_AREA_RATIO = _env_float("MINERU_SELECTIVE_IMAGE_AREA_RATIO", 0.20)
    MINERU_FULL_MAX_PAGES_SOFT_LIMIT = _env_int("MINERU_FULL_MAX_PAGES_SOFT_LIMIT", 25)
    MINERU_FULL_COMPLEX_PAGE_RATIO_THRESHOLD = _env_float("MINERU_FULL_COMPLEX_PAGE_RATIO_THRESHOLD", 0.35)
    PARSER_OUTPUT_SCHEMA_VERSION = os.getenv("PARSER_OUTPUT_SCHEMA_VERSION", "adaptive_pdf_parse_v1").strip()
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "cohere").strip().lower()
    EMBEDDING_BATCH_SIZE = _env_int("EMBEDDING_BATCH_SIZE", 32)
    EMBEDDING_REQUEST_TIMEOUT_SECONDS = _env_int("EMBEDDING_REQUEST_TIMEOUT_SECONDS", 90)
    EMBEDDING_MAX_RETRIES = _env_int("EMBEDDING_MAX_RETRIES", 5)
    EMBEDDING_BACKOFF_BASE_SECONDS = _env_int("EMBEDDING_BACKOFF_BASE_SECONDS", 10)
    EMBEDDING_BACKOFF_MAX_SECONDS = _env_int("EMBEDDING_BACKOFF_MAX_SECONDS", 300)
    EMBEDDING_RATE_LIMIT_COOLDOWN_SECONDS = _env_int("EMBEDDING_RATE_LIMIT_COOLDOWN_SECONDS", 600)
    EMBEDDING_CIRCUIT_BREAKER_FAILURES = _env_int("EMBEDDING_CIRCUIT_BREAKER_FAILURES", 3)
    EMBEDDING_FAIL_FAST_ON_AUTH = _env_bool("EMBEDDING_FAIL_FAST_ON_AUTH", True)
    EMBEDDING_RETRY_JITTER = _env_bool("EMBEDDING_RETRY_JITTER", True)
    EMBEDDING_CACHE_ENABLED = _env_bool("EMBEDDING_CACHE_ENABLED", True)
    EMBEDDING_CACHE_BACKEND = os.getenv("EMBEDDING_CACHE_BACKEND", "sqlite").strip().lower()
    EMBEDDING_CACHE_PATH = os.getenv("EMBEDDING_CACHE_PATH", str(DATA_DIR / "cache" / "embedding_cache.sqlite")).strip()
    KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY = _env_bool("KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY", False)
    KNOWLEDGE_UPDATE_MAX_DOCS_PER_RUN = _env_int("KNOWLEDGE_UPDATE_MAX_DOCS_PER_RUN", 0)
    KNOWLEDGE_UPDATE_MAX_VECTORS_PER_RUN = _env_int("KNOWLEDGE_UPDATE_MAX_VECTORS_PER_RUN", 0)
    KNOWLEDGE_UPDATE_STOP_ON_RATE_LIMIT = _env_bool("KNOWLEDGE_UPDATE_STOP_ON_RATE_LIMIT", True)
    KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED = _env_bool("KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED", True)
    KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED = _env_bool("KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED", True)
    KNOWLEDGE_UPDATE_FORCE_REPARSE = _env_bool("KNOWLEDGE_UPDATE_FORCE_REPARSE", False)
    KNOWLEDGE_UPDATE_FORCE_REINDEX = _env_bool("KNOWLEDGE_UPDATE_FORCE_REINDEX", False)
    KNOWLEDGE_UPDATE_LOG_PRECHECK = _env_bool("KNOWLEDGE_UPDATE_LOG_PRECHECK", True)
    SEMANTIC_CONTEXT_EXECUTOR_ENABLED = _env_bool("SEMANTIC_CONTEXT_EXECUTOR_ENABLED", True)
    SEMANTIC_CONTEXT_EXECUTOR_AUTHORITATIVE = _env_bool("SEMANTIC_CONTEXT_EXECUTOR_AUTHORITATIVE", True)
    SEMANTIC_CONTEXT_REUSE_LEGACY_PREFETCH = _env_bool("SEMANTIC_CONTEXT_REUSE_LEGACY_PREFETCH", True)
    SEMANTIC_CONTEXT_BLOCK_DUPLICATE_FETCH = _env_bool("SEMANTIC_CONTEXT_BLOCK_DUPLICATE_FETCH", True)
    SEMANTIC_CONTEXT_TASK_VIEWS_ENABLED = _env_bool("SEMANTIC_CONTEXT_TASK_VIEWS_ENABLED", True)
    SEMANTIC_CONTEXT_KNOWLEDGE_USE_V3 = _env_bool("SEMANTIC_CONTEXT_KNOWLEDGE_USE_V3", True)
    SEMANTIC_CONTEXT_KNOWLEDGE_FALLBACK_TO_LEGACY = _env_bool("SEMANTIC_CONTEXT_KNOWLEDGE_FALLBACK_TO_LEGACY", False)

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
    USE_KNOWLEDGE_V3        = False
    KNOWLEDGE_V3_FALLBACK_TO_LEGACY = True
    KNOWLEDGE_V3_SCORE_THRESHOLD = 0.0

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
