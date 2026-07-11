import pytest
from src.services.evidence.evidence_coverage import EvidenceTopicAttributor, EvidenceCoverageEvaluator
from src.services.evidence.answer_coverage import AnswerCoverageValidator
from src.services.evidence.coverage_requirements import CoverageRequirementPlanner
from src.services.evidence.evidence_pipeline import EvidenceItem, EvidenceBundle
from src.services.semantic.query_plan import QueryPlan
from src.services.evidence.answer_depth import AnswerDepthPlan

class DummyQueryPlan:
    task_id = "t1"

def create_req_set(answer_type="static_explanation"):
    qp = DummyQueryPlan()
    dp = AnswerDepthPlan(task_id="t1", detail_level="detailed", expected_explanation_depth="deep", expected_topic_count_range=(2, 4), practical_interpretation_required=True, limitations_required=True)
    return CoverageRequirementPlanner.plan(qp, dp, answer_type)

def test_evidence_topic_attribution():
    """Test EvidenceTopicAttributor with semantic signals rather than literal keywords."""
    req_set = create_req_set()
    
    # 1. Procedural evidence without the literal word "methodology"
    item = EvidenceItem(
        evidence_id="e1",
        task_id="t1",
        evidence_type="book_passage",
        capability="knowledge_v3",
        target="al_brooks_book",
        content="The trader identifies the signal bar, places an order at the entry bar, entering on stops.",
        content_summary=""
    )
    
    result = EvidenceTopicAttributor.attribute(item, req_set)
    assert "methodology_or_process" in result.covered_topics, "Should detect methodology via semantic signals like 'signal bar', 'entry bar'"
    assert "practical_application" in result.covered_topics, "Should detect practical application via 'entering on stops'"
    
def test_multilingual_answer_coverage():
    """Test AnswerCoverageValidator with Vietnamese text against English ontology roles."""
    reqs = ["methodology_or_process", "practical_application", "short_conclusion", "core_concept"]
    
    # Vietnamese answer containing semantic methodology explanation
    vietnamese_text = "Trong hành động giá, nhà giao dịch xác định thanh tín hiệu, sau đó dùng thanh vào lệnh để đặt cắt lỗ. Tóm lại, đây là chiến lược cốt lõi."
    
    result = AnswerCoverageValidator.evaluate(vietnamese_text, reqs)
    
    assert "methodology_or_process" in result.covered_topics, "Vietnamese methodology should be recognized"
    assert "practical_application" in result.covered_topics, "Vietnamese practical application should be recognized"
    assert "short_conclusion" in result.covered_topics, "Structural short conclusion 'Tóm lại' should be recognized"

def test_structural_contract_topic_detection():
    """Test structural topics like short_conclusion."""
    reqs = ["short_conclusion"]
    
    # Test positive
    res_pos = AnswerCoverageValidator.evaluate("Kết luận ngắn: đây là chiến lược tốt.", reqs)
    assert "short_conclusion" in res_pos.covered_topics
    
    # Test negative
    res_neg = AnswerCoverageValidator.evaluate("Chiến lược này rất phức tạp.", reqs)
    assert "short_conclusion" not in res_neg.covered_topics

def test_post_refinement_coverage_recompute():
    """Test post-refinement coverage evaluates merged bundle and logs actual item count."""
    req_set = create_req_set()
    
    item1 = EvidenceItem("e1", "t1", "book_passage", "kb", "tg", content="This refers to price action.")
    
    bundle_before = EvidenceBundle(task_id="t1", query="test", query_plan={}, answer_type="static_explanation", primary_evidence=[item1])
    res_before = EvidenceCoverageEvaluator.evaluate(bundle_before, req_set, phase="pre_refinement")
    
    assert res_before.coverage_ratio < 1.0
    assert "methodology_or_process" in res_before.missing_required_topics
    
    # Simulate refinement
    item2 = EvidenceItem("e2", "t1", "book_passage", "kb", "tg", content="You must enter on stops above the signal bar.")
    bundle_after = EvidenceBundle(task_id="t1", query="test", query_plan={}, answer_type="static_explanation", primary_evidence=[item1, item2])
    
    res_after = EvidenceCoverageEvaluator.evaluate(bundle_after, req_set, phase="post_refinement")
    
    assert res_after.coverage_ratio > res_before.coverage_ratio
    assert "methodology_or_process" not in res_after.missing_required_topics

def test_coverage_false_negative_regressions():
    """Test regressions related to missing topics falsely identified."""
    reqs = ["limitations"]
    
    text = "Tuy nhiên, rủi ro lớn nhất là thanh khoản thấp."
    res = AnswerCoverageValidator.evaluate(text, reqs)
    assert "limitations" in res.covered_topics, "Vietnamese 'rủi ro' / 'tuy nhiên' should satisfy limitations"

    reqs2 = ["headline_findings"]
    text2 = "Báo cáo cho thấy lạm phát tăng mạnh."
    res2 = AnswerCoverageValidator.evaluate(text2, reqs2)
    assert "headline_findings" in res2.covered_topics
