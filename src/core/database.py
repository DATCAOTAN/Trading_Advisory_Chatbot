import os
import threading
import streamlit as st
from qdrant_client import QdrantClient
from src.config import Config

class QdrantDatabaseProvider:
    """
    Singleton Provider: Cổng truy cập duy nhất đến Qdrant.
    """
    _instance = None
    _instance_lock = threading.Lock()
    _client = None

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def qdrant_client(self) -> QdrantClient:
        with self._instance_lock:
            if self._client is None:
                os.makedirs(Config.QDRANT_DIR, exist_ok=True)
                print(f"🔌 [Qdrant] Kết nối kho dữ liệu: {Config.QDRANT_DIR}")
                self._client = QdrantClient(path=str(Config.QDRANT_DIR))
            return self._client