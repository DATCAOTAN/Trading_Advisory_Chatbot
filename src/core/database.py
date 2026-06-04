import os
import threading
import streamlit as st
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from src.config import Config

# Lock cấp module để bảo vệ việc khởi tạo trong môi trường đa luồng (Streamlit)
_init_lock = threading.Lock()


@st.cache_resource
def _get_qdrant_client() -> QdrantClient:
    """
    Dùng @st.cache_resource để đảm bảo chỉ tạo đúng 1 QdrantClient
    duy nhất trong suốt vòng đời ứng dụng Streamlit (thread-safe).
    """
    os.makedirs(Config.QDRANT_DIR, exist_ok=True)
    print(f"🔌 [Qdrant] Đang kết nối đến kho dữ liệu: {Config.QDRANT_DIR}")
    return QdrantClient(path=str(Config.QDRANT_DIR))


@st.cache_resource
def _get_embedding_model() -> SentenceTransformer:
    """
    Dùng @st.cache_resource để nạp mô hình nhúng vào RAM đúng 1 lần,
    chia sẻ chung cho tất cả các phiên Streamlit (thread-safe).
    """
    print("🧠 [Singleton] Đang nạp mô hình nhúng BAEI/bge-m3 vào RAM...")
    return SentenceTransformer(Config.EMBEDDING_MODEL_NAME)


class QdrantDatabaseProvider:
    """
    Singleton Pattern: Đảm bảo chỉ có một thực thể duy nhất quản lý vòng đời.
    Sử dụng @st.cache_resource bên dưới để xử lý thread-safety trong Streamlit.
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super(QdrantDatabaseProvider, cls).__new__(cls)
        return cls._instance

    @property
    def qdrant_client(self) -> QdrantClient:
        """Trả về QdrantClient duy nhất được cache bởi Streamlit (thread-safe)"""
        return _get_qdrant_client()

    @property
    def embedding_model(self) -> SentenceTransformer:
        """Trả về mô hình nhúng được cache bởi Streamlit (thread-safe)"""
        return _get_embedding_model()