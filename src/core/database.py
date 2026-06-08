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


# =============================================================================
# SINGLETON PROVIDER
# =============================================================================

class QdrantDatabaseProvider:
    """
    Singleton Provider: Cổng truy cập duy nhất đến Qdrant.
    
    Lưu ý:
    - Mô hình AI (Embedding/Reranker) đã được chuyển hoàn toàn lên Cloud (Cohere API).
    - Lớp này giờ đây chỉ có nhiệm vụ duy trì kết nối tới Qdrant Vector DB.
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