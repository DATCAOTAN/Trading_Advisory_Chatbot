import os
import sys

# add parent dir so we can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.history_service import HistoryService
from src.services.vector_service import VectorService
from unittest.mock import MagicMock
import uuid

def test_memory_policy():
    """Verify that DEGRADED memory correctly persists in VectorDB and gets the warning prefix."""
    vec_svc = object.__new__(VectorService)
    vec_svc.client = MagicMock()
    vec_svc._encode_dense = MagicMock(return_value=[[0.0] * 1024])
    
    # Fake search results
    class MockPayload:
        def __init__(self, p):
            self.payload = p
            
    hit1 = MockPayload({
        "session_id": "test_session",
        "role": "user",
        "content": "What about CPI?",
        "quality_status": "PASS",
        "timestamp": "2023-01-01T12:00:00"
    })
    
    hit2 = MockPayload({
        "session_id": "test_session",
        "role": "assistant",
        "content": "CPI is 5%.",
        "quality_status": "DEGRADED",
        "timestamp": "2023-01-01T12:01:00"
    })
    
    vec_svc.client.search.return_value = [hit1, hit2]
    vec_svc.client.get_collection.return_value = True
    
    result = vec_svc.search_chat_history(session_id="test_session", query="CPI")
    
    # Assert DEGRADED prefix is injected
    assert "[WARNING: NON-AUTHORITATIVE DEGRADED MEMORY]" in result
    assert "[2023-01-01T12:01:00] ASSISTANT: [WARNING: NON-AUTHORITATIVE DEGRADED MEMORY] CPI is 5%." in result
    print("Memory policy test passed!")

if __name__ == "__main__":
    test_memory_policy()
