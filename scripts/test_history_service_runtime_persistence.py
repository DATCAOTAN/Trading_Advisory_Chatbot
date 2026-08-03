import threading
from unittest.mock import MagicMock

from src.services.history_service import HistoryService


def test_singleton_is_not_published_before_initialization(monkeypatch):
    original = HistoryService._instance
    entered = threading.Event()
    release = threading.Event()

    def initialize(instance):
        entered.set()
        assert release.wait(timeout=2)
        instance.sessions_col = object()

    monkeypatch.setattr(HistoryService, "_instance", None)
    monkeypatch.setattr(HistoryService, "_init_service", initialize)
    instances = []
    first = threading.Thread(target=lambda: instances.append(HistoryService()))
    second = threading.Thread(target=lambda: instances.append(HistoryService()))

    first.start()
    assert entered.wait(timeout=2)
    second.start()
    assert instances == []
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len(instances) == 2
    assert instances[0] is instances[1]
    assert hasattr(instances[0], "sessions_col")
    HistoryService._instance = original


def test_chat_history_persists_when_vector_memory_is_skipped():
    service = object.__new__(HistoryService)
    service.load_history = MagicMock(return_value=[])
    service._cache_session = MagicMock()
    service.sessions_col = MagicMock()
    message = {"role": "assistant", "content": "Incomplete answer remains visible."}

    service.append_message("session-1", message, include_vector_memory=False)

    service._cache_session.assert_called_once_with("session-1", [message])
    service.sessions_col.update_one.assert_called_once()
