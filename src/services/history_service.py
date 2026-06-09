import json
import uuid
import datetime
from typing import List, Dict, Optional
from pymongo import MongoClient
import redis

from src.config import Config

class HistoryService:
    """
    Singleton Pattern: Hybrid Storage (Redis Cache + MongoDB Persistent).
    Quản lý bộ nhớ hội thoại đa phiên (Multi-session).
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_service()
        return cls._instance

    def _init_service(self):
        # Khởi tạo MongoDB (Persistent Storage)
        self.mongo_client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=2000)
        self.db = self.mongo_client["trading_bot_db"]
        self.sessions_col = self.db["sessions"]
        
        # Khởi tạo Redis (Cache siêu tốc)
        self.redis_client = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)
        self.cache_ttl = 3600 * 24 # Giữ cache trong 24 giờ

    def create_session(self, title: str = "New Chat") -> str:
        session_id = str(uuid.uuid4())
        session_doc = {
            "_id": session_id,
            "title": title,
            "updated_at": datetime.datetime.utcnow(),
            "messages": []
        }
        try:
            self.sessions_col.insert_one(session_doc)
            self._cache_session(session_id, [])
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi tạo session MongoDB: {e}")
            # Fallback lưu vào cache tạm thời nếu Mongo chết
            self._cache_session(session_id, [])
        return session_id

    def get_all_sessions(self) -> List[Dict]:
        """Lấy danh sách tất cả các phiên chat để hiển thị ở Sidebar."""
        try:
            cursor = self.sessions_col.find({}, {"messages": 0}).sort("updated_at", -1)
            return list(cursor)
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi lấy danh sách session: {e}")
            return []

    def load_history(self, session_id: str) -> List[Dict]:
        """Load tin nhắn của một phiên. Tốc độ <2ms nhờ ưu tiên Cache."""
        if not session_id:
            return []
        
        # 1. Đọc từ Redis Cache trước
        try:
            cached_data = self.redis_client.get(f"session:{session_id}")
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"⚠️ [HistoryService] Lỗi Redis Cache: {e}")

        # 2. Cache Miss -> Đọc từ MongoDB -> Nạp ngược lại vào Redis
        try:
            doc = self.sessions_col.find_one({"_id": session_id})
            if doc and "messages" in doc:
                messages = doc["messages"]
                self._cache_session(session_id, messages)
                return messages
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi lấy lịch sử MongoDB: {e}")
            
        return []

    def append_message(self, session_id: str, message: Dict):
        """Lưu tin nhắn song song vào cả Redis và MongoDB."""
        if not session_id:
            return
            
        messages = self.load_history(session_id)
        messages.append(message)
        
        # 1. Ghi vào Redis Cache
        self._cache_session(session_id, messages)
        
        # 2. Ghi vĩnh viễn vào MongoDB
        try:
            self.sessions_col.update_one(
                {"_id": session_id},
                {
                    "$set": {
                        "messages": messages,
                        "updated_at": datetime.datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi cập nhật MongoDB: {e}")

    def delete_session(self, session_id: str):
        """Xóa vĩnh viễn một phiên chat."""
        if not session_id:
            return
        # 1. Xóa khỏi Redis
        try:
            self.redis_client.delete(f"session:{session_id}")
        except Exception:
            pass
            
        # 2. Xóa khỏi MongoDB
        try:
            self.sessions_col.delete_one({"_id": session_id})
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi xóa session MongoDB: {e}")

    def rename_session(self, session_id: str, new_title: str):
        """Đổi tên phiên chat."""
        if not session_id or not new_title:
            return
        try:
            self.sessions_col.update_one(
                {"_id": session_id},
                {
                    "$set": {
                        "title": new_title,
                        "updated_at": datetime.datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi đổi tên session MongoDB: {e}")

    def _cache_session(self, session_id: str, messages: List[Dict]):
        """Hàm nội bộ: Cập nhật dữ liệu vào Redis."""
        try:
            self.redis_client.setex(
                f"session:{session_id}",
                self.cache_ttl,
                json.dumps(messages, ensure_ascii=False)
            )
        except Exception:
            pass
