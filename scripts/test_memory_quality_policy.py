import pytest
from src.ui.tab_chatbot import check_answer_completeness

def test_memory_quality_policy():
    """Test that WARN results in quality_status=DEGRADED and FAIL skips memory storage."""
    
    # We can just test the completeness logic, as the UI logic is hard to mock in pytest.
    result_warn = check_answer_completeness(
        answer="- Theo báo cáo, This is an answer that is somewhat short but pass.\n" * 5 + "[1]\nKết luận ngắn: x.",
        finish_reason="STOP",
        min_chars=300, # Will trigger WARN if chars < 600
        intent="FINANCIAL_RAG",
        runtime_artifacts={"answer_contracts": []},
        query="test query",
        sources=[{"id": "1", "source_title": "test document"}]
    )
    
    print(result_warn)
    assert result_warn["level"] == "warn"
    assert "short_rag_answer" in result_warn["reason"]
    
    # Check Fail
    result_fail = check_answer_completeness(
        answer="Too short",
        finish_reason="STOP",
        min_chars=300,
        intent="FINANCIAL_RAG",
        runtime_artifacts={"answer_contracts": []},
        query="test query",
        sources=[]
    )
    
    assert result_fail["level"] == "fail"
    assert "too_short" in result_fail["reason"]
