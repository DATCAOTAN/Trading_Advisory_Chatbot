import pytest
from src.services.evidence.evidence_pipeline import EvidencePromptAssembler, EvidenceBundle, EvidenceItem, AnswerContract
from src.services.evidence.evidence_coverage import EvidenceCoverageResult

def test_topic_evidence_budget():
    """Test that EvidencePromptAssembler budgets evidence by topic and limits total items."""
    items = []
    # Create 8 items, 3 for topic_A, 5 for topic_B
    for i in range(1, 4):
        items.append(EvidenceItem(evidence_id=f"a{i}", task_id="t1", evidence_type="test", capability="llm", target="", content=f"content a{i}"))
    for i in range(1, 6):
        items.append(EvidenceItem(evidence_id=f"b{i}", task_id="t1", evidence_type="test", capability="llm", target="", content=f"content b{i}"))
        
    bundle = EvidenceBundle(
        task_id="t1",
        query="test",
        query_plan={},
        answer_type="test",
        primary_evidence=items,
        coverage_result=EvidenceCoverageResult(
            task_id="t1",
            status="COMPLETE",
            topic_presence_ratio=1.0,
            evidence_by_topic={
                "topic_A": ["a1", "a2", "a3"],
                "topic_B": ["b1", "b2", "b3", "b4", "b5"]
            }
        )
    )
    
    contract = AnswerContract(
        task_id="t1",
        answer_type="test",
        required_sections=["topic_A", "topic_B"]
    )
    
    assembler = EvidencePromptAssembler()
    lines = assembler._bundle_lines(bundle, contract)
    
    prompt_text = "\n".join(lines)
    
    # It should only include max 2 items for topic A
    assert "Evidence ID: a1" in prompt_text
    assert "Evidence ID: a2" in prompt_text
    assert "Evidence ID: a3" not in prompt_text
    
    # It should only include max 2 items for topic B, or maybe it hits MAX_TOTAL (6).
    # Since 2 + 2 = 4 < 6, it will take 2 items for topic B.
    assert "Evidence ID: b1" in prompt_text
    assert "Evidence ID: b2" in prompt_text
    assert "Evidence ID: b3" not in prompt_text
