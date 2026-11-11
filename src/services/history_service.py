import json
import re
import uuid
import datetime
import threading
import hashlib
import os
import socket
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import redis

from src.config import Config

class HistoryService:
    """
    Singleton Pattern: Hybrid Storage (Redis Cache + MongoDB Persistent).
    Quản lý bộ nhớ hội thoại đa phiên (Multi-session).
    """
    _instance = None
    _instance_lock = threading.Lock()
    _research_active = set()
    _research_active_lock = threading.Lock()
    
    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._init_service()
                cls._instance = instance
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
            return None

    def load_history(self, session_id: str, limit: int = None) -> List[Dict]:
        """Load tin nhắn của một phiên. Tốc độ <2ms nhờ ưu tiên Cache. Hỗ trợ cắt Sliding Window."""
        if not session_id:
            return []
        
        messages = None
        # 1. Đọc từ Redis Cache trước
        try:
            cached_data = self.redis_client.get(f"session:{session_id}")
            if cached_data:
                parsed = json.loads(cached_data)
                if isinstance(parsed, list) and len(parsed) > 0:
                    messages = parsed
        except Exception as e:
            print(f"⚠️ [HistoryService] Lỗi Redis Cache: {e}")

        # 2. Cache Miss -> Đọc từ MongoDB -> Nạp ngược lại vào Redis
        if not messages:
            try:
                doc = self.sessions_col.find_one({"_id": session_id})
                if doc and "messages" in doc:
                    messages = doc["messages"]
                    # Chỉ nạp ngược nếu có thực sự có data để nạp
                    if messages:
                        self._cache_session(session_id, messages)
            except Exception as e:
                print(f"❌ [HistoryService] Lỗi lấy lịch sử MongoDB: {e}")
                
        # Nếu MongoDB cũng rỗng hoặc lỗi -> gán mảng rỗng
        if messages is None:
            messages = []
            
        if limit is not None and limit > 0:
            return messages[-limit:]
        return messages

    def append_message(
        self,
        session_id: str,
        message: Dict,
        *,
        include_vector_memory: bool = True,
    ):
        """Lưu tin nhắn song song vào cả Redis, MongoDB và VectorDB (Long-term Memory)."""
        if not session_id:
            return
            
        # Lấy lịch sử hiện tại ra để nạp vào cache Redis
        messages = self.load_history(session_id, limit=None)
        messages.append(message)
        
        # 1. Ghi vào Redis Cache
        self._cache_session(session_id, messages)
        
        # 2. Ghi vĩnh viễn vào MongoDB (dùng $push để tuyệt đối không ghi đè mất data cũ)
        try:
            self.sessions_col.update_one(
                {"_id": session_id},
                {
                    "$push": {
                        "messages": message
                    },
                    "$set": {
                        "updated_at": datetime.datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"❌ [HistoryService] Lỗi cập nhật MongoDB: {e}")
            
        # 3. Ghi vào Long-term Memory (Vector DB)
        if not include_vector_memory:
            return

        content = message.get("content", "").strip()
        # Lọc rác: Bỏ qua tin nhắn quá ngắn
        if len(content) > 15:
            try:
                from src.services.vector_service import VectorService
                from qdrant_client.http.models import PointStruct, VectorParams, Distance
                import uuid
                
                vec_svc = VectorService()
                collection_name = "chat_history_collection"
                
                # Tạo collection nếu chưa tồn tại
                try:
                    vec_svc.client.get_collection(collection_name)
                except Exception:
                    vec_svc.client.create_collection(
                        collection_name=collection_name,
                        vectors_config={
                            vec_svc.DENSE_VECTOR_NAME: VectorParams(size=1024, distance=Distance.COSINE)
                        }
                    )
                
                # Mã hóa tin nhắn
                role_prefix = "USER: " if message["role"] == "user" else "AI: "
                text_to_encode = f"[{session_id}] {role_prefix}{content}"
                dense_vec = vec_svc._encode_dense([text_to_encode], input_type="search_document")[0]
                
                point_id = str(uuid.uuid4())
                vec_svc.client.upsert(
                    collection_name=collection_name,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector={vec_svc.DENSE_VECTOR_NAME: dense_vec},
                            payload={
                                "session_id": session_id,
                                "role": message["role"],
                                "content": content,
                                "quality_status": message.get("quality_status", "PASS"),
                                "timestamp": datetime.datetime.utcnow().isoformat()
                            }
                        )
                    ]
                )
                print(f"🧠 [Memory] Đã lưu tin nhắn vào Long-term Vector Memory.")
            except Exception as e:
                print(f"⚠️ [Memory] Lỗi lưu Vector History: {e}")

    def append_message_if_current(
        self, session_id: str, expected_count: int, expected_tail: Dict, message: Dict,
    ) -> bool:
        """Append a clarification only while its exact review is still the persisted tail."""
        if not session_id or expected_count < 1:
            return False
        try:
            result = self.sessions_col.update_one(
                {
                    "_id": session_id,
                    f"messages.{expected_count - 1}": {"$eq": expected_tail},
                    f"messages.{expected_count}": {"$exists": False},
                },
                {
                    "$push": {"messages": message},
                    "$set": {"updated_at": datetime.datetime.now(datetime.timezone.utc)},
                },
                upsert=False,
            )
            saved = result.modified_count == 1
        except PyMongoError:
            raise RuntimeError("Conversation history is unavailable; the clarification was not confirmed.") from None
        try:
            self.redis_client.delete(f"session:{session_id}")
        except redis.RedisError:
            pass
        return saved

    def load_research_snapshot(self, session_id: str) -> Dict:
        """Research uses persistent conversation state, never a possibly stale Redis view."""
        if not session_id:
            raise ValueError("RESEARCH_CONVERSATION_REQUIRED")
        try:
            document = self.sessions_col.find_one(
                {"_id": session_id}, {"messages": 1, "research_proposals": 1},
            )
        except PyMongoError:
            raise RuntimeError("RESEARCH_STORAGE_UNAVAILABLE") from None
        if document is None:
            raise ValueError("RESEARCH_CONVERSATION_UNAVAILABLE")
        return document

    @staticmethod
    def research_generation_owner() -> str:
        return hashlib.sha256(socket.gethostname().encode()).hexdigest()

    @contextmanager
    def research_generation_lock(self, key):
        """OS ownership releases on crash; Mongo CAS still fences the durable attempt."""
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("RESEARCH_STORAGE_KEY_INVALID")
        with self._research_active_lock:
            if key in self._research_active:
                raise ValueError("RESEARCH_GENERATION_ACTIVE")
            self._research_active.add(key)
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
                kernel.CreateMutexW.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.WaitForSingleObject.restype = wintypes.DWORD
                kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.CreateMutexW(None, False, "Global\\TradingResearch_" + key)
                if not handle:
                    raise RuntimeError("RESEARCH_GENERATION_LOCK_UNAVAILABLE")
                held = False
                try:
                    status = kernel.WaitForSingleObject(handle, 0)
                    if status == 258:
                        raise ValueError("RESEARCH_GENERATION_ACTIVE")
                    if status not in {0, 128}:
                        raise RuntimeError("RESEARCH_GENERATION_LOCK_UNAVAILABLE")
                    held = True
                    yield
                finally:
                    if held:
                        kernel.ReleaseMutex(handle)
                    kernel.CloseHandle(handle)
            else:
                import fcntl
                # Keep the inode: unlinking an advisory lock permits two independent locks.
                path = Path(tempfile.gettempdir()) / ("trading_research_" + key + ".lock")
                fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                try:
                    if os.fstat(fd).st_uid != os.getuid():
                        raise RuntimeError("RESEARCH_GENERATION_LOCK_UNAVAILABLE")
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise ValueError("RESEARCH_GENERATION_ACTIVE") from None
                    yield
                finally:
                    os.close(fd)
        finally:
            with self._research_active_lock:
                self._research_active.discard(key)

    def save_research_state(self, session_id, *, count, tail, key, expected, record) -> bool:
        """CAS protects both the canonical brief and the immutable proposal head."""
        if not re.fullmatch(r"[a-f0-9]{64}", key) or count < 1:
            raise ValueError("RESEARCH_STORAGE_KEY_INVALID")
        path = f"research_proposals.{key}"
        query = {
            "_id": session_id, f"messages.{count - 1}": {"$eq": tail},
            f"messages.{count}": {"$exists": False},
            path: {"$exists": False} if expected is None else {"$eq": expected},
        }
        try:
            result = self.sessions_col.update_one(query, {"$set": {
                path: record, "updated_at": datetime.datetime.now(datetime.timezone.utc),
            }}, upsert=False)
        except PyMongoError:
            raise RuntimeError("RESEARCH_STORAGE_UNAVAILABLE") from None
        return result.modified_count == 1

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
