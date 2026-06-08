import os
import threading
import streamlit as st
from qdrant_client import QdrantClient
from src.config import Config


# =============================================================================
# SINGLETON RESOURCES — @st.cache_resource đảm bảo thread-safe, chỉ load 1 lần
# =============================================================================

@st.cache_resource
def _get_qdrant_client() -> QdrantClient:
    """Kết nối Qdrant Local duy nhất."""
    os.makedirs(Config.QDRANT_DIR, exist_ok=True)
    print(f"🔌 [Qdrant] Kết nối kho dữ liệu: {Config.QDRANT_DIR}")
    return QdrantClient(path=str(Config.QDRANT_DIR))


@st.cache_resource
def _get_embedding_model():
    """
    Nạp BGE-M3 qua SentenceTransformer — ổn định, đã kiểm chứng.
    Import bên trong function để không block quá trình khởi động.
    """
    print(f"🧠 [Embedding] Đang nạp mô hình {Config.EMBEDDING_MODEL_NAME}...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(Config.EMBEDDING_MODEL_NAME)
        print(f"✅ [Embedding] Đã nạp xong {Config.EMBEDDING_MODEL_NAME}")
        return model
    except Exception as e:
        print(f"❌ [Embedding] Lỗi nghiêm trọng: {e}")
        raise


@st.cache_resource
def _get_bgem3_model():
    """
    BGEM3FlagModel cho Hybrid Search (Dense + Sparse cùng lúc).
    Trả về None nếu FlagEmbedding chưa cài — app vẫn chạy bình thường.
    """
    try:
        from FlagEmbedding import BGEM3FlagModel
        print(f"⚡ [BGEM3] Nạp FlagEmbedding model cho Hybrid Search...")
        return BGEM3FlagModel(Config.EMBEDDING_MODEL_NAME, use_fp16=True)
    except ImportError:
        print("ℹ️ [BGEM3] FlagEmbedding chưa cài → Hybrid Search dùng Dense-only")
        return None
    except Exception as e:
        print(f"⚠️ [BGEM3] Lỗi: {e} → Hybrid Search dùng Dense-only")
        return None


@st.cache_resource
def _get_reranker_model():
    """
    BGE-Reranker — CHỈ nạp khi được gọi tường minh.
    Trả về None nếu FlagEmbedding chưa cài.
    """
    try:
        from FlagEmbedding import FlagReranker
        print(f"🎯 [Reranker] Nạp mô hình: {Config.RERANKER_MODEL_NAME}")
        return FlagReranker(Config.RERANKER_MODEL_NAME, use_fp16=True)
    except ImportError:
        print("ℹ️ [Reranker] FlagEmbedding chưa cài → Reranker tắt")
        return None
    except Exception as e:
        print(f"⚠️ [Reranker] Lỗi: {e} → Reranker tắt")
        return None


# =============================================================================
# SINGLETON PROVIDER
# =============================================================================

class QdrantDatabaseProvider:
    """
    Singleton Provider: Cổng truy cập duy nhất đến tất cả AI resources.
    
    Thứ tự nạp (tuần tự, KHÔNG đồng thời):
    1. qdrant_client    → Nhẹ, nạp ngay
    2. embedding_model  → BGE-M3 ~1.5GB, nạp khi cần
    3. bgem3_model      → Chỉ khi FlagEmbedding đã cài
    4. reranker_model   → Chỉ khi user dùng tính năng reranker
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def qdrant_client(self) -> QdrantClient:
        return _get_qdrant_client()

    @property
    def embedding_model(self):
        """Dense embedding — luôn khả dụng."""
        return _get_embedding_model()

    @property
    def bgem3_model(self):
        """Hybrid model — None nếu FlagEmbedding chưa cài."""
        return _get_bgem3_model()

    @property
    def reranker_model(self):
        """Reranker — None nếu FlagEmbedding chưa cài."""
        return _get_reranker_model()