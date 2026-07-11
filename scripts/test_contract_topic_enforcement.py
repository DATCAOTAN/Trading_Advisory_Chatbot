import pytest
from src.ui.tab_chatbot import check_answer_completeness
from src.services.evidence.evidence_pipeline import AnswerContract

def test_contract_topic_enforcement():
    """Test that missing required topics enforce WARN contract_status."""
    
    contract = AnswerContract(
        task_id="t1",
        answer_type="test",
        required_sections=["core_concept", "methodology_or_process"]
    )
    
    runtime_artifacts = {
        "answer_contracts": [contract]
    }
    # Missing methodology_or_process
    answer = "- Theo báo cáo, This is a concept about price action. [1]\n\n" * 15 + "Kết luận ngắn: test."
    
    result = check_answer_completeness(
        answer=answer,
        finish_reason="STOP",
        min_chars=10, # Keep it low so format_status=PASS
        intent="FINANCIAL_RAG",
        runtime_artifacts=runtime_artifacts,
        query="test query",
        sources=[{"id": "1", "source_title": "test document"}]
    )
    
    # Check that contract_status was degraded to WARN
    assert result["contract_status"] == "WARN"
    assert result["coverage_status"] == "WARN"
    assert "methodology_or_process" in result.get("reason", "")
    assert result["overall_status"] == "WARN"
