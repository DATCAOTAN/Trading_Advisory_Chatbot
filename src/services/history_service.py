import json
import os
import threading
from pathlib import Path
from typing import List, Dict

from src.config import Config

class HistoryService:
    """
    Singleton Pattern: Quản lý bộ nhớ hội thoại toàn cục (Global Session Memory).
    Đảm bảo tính nhất quán dữ liệu khi đọc/ghi file chat_history.json.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_service()
            return cls._instance

    def _init_service(self):
        self.history_file = Path(Config.BASE_DIR) / "data" / "chat_history.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Tạo file rỗng nếu chưa tồn tại
        if not self.history_file.exists():
            self._save_to_disk([])

    def _save_to_disk(self, messages: List[Dict]):
        """Lưu toàn bộ lịch sử xuống ổ cứng (Persistent Storage)."""
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    def load_history(self) -> List[Dict]:
        """Tải toàn bộ lịch sử từ file (Dùng khi F5 hoặc khởi động lại app)."""
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def append_message(self, message: Dict):
        """Thêm một tin nhắn mới và lưu trực tiếp xuống file."""
        with self._lock:
            messages = self.load_history()
            messages.append(message)
            self._save_to_disk(messages)

    def clear_history(self):
        """Xóa trắng lịch sử hội thoại."""
        with self._lock:
            self._save_to_disk([])
