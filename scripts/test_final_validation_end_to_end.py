import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.evidence.evidence_pipeline import (
    ClaimEvidenceValidator,
    ClaimValidationResult,
    ClaimValidationWarning,
    EvidenceBundle,
    EvidenceItem,
    AnswerContract,
    AnswerContractEvaluator,
    ContractEvaluationResult
)
from src.services.evidence.answer_coverage import AnswerCoverageValidationResult
from src.ui.tab_chatbot import _source_reference_terms, _has_source_reference

def test_claim_warning_trace():
    print("\n--- Testing Claim Warning Trace ---")
    validator = ClaimEvidenceValidator()
    
    # Test numeric warning
    bundles = [
        EvidenceBundle(
            task_id="t1",
            query="test",
            query_plan={},
            answer_type="concept",
            primary_evidence=[
                EvidenceItem(evidence_id="1", content="some text", evidence_type="general", source_title="book", task_id="t1", capability="cap1")
            ]
        )
    ]
    contracts = [AnswerContract(task_id="t1", answer_type="concept")]
    
    # Numeric claim without numeric evidence
    res = validator.validate("There are 5 types of trends.", bundles, contracts)
    assert res.status == "WARN"
    assert len(res.warnings) == 1
    assert res.warnings[0].warning_code == "numeric_claim_without_numeric_evidence"
    assert res.warnings[0].severity == "NON_BLOCKING_WARN"
    
    # Current language without current evidence
    res2 = validator.validate("Hien tai thi truong dang tang.", bundles, contracts)
    assert res2.status == "WARN"
    assert len(res2.warnings) == 1
    assert res2.warnings[0].warning_code == "current_language_without_current_evidence"
    assert res2.warnings[0].severity == "CONTRACT_DEGRADING_WARN"
    
    print("test_claim_warning_trace: PASS")

def test_contract_evaluation_policy():
    print("\n--- Testing Contract Evaluation Policy ---")
    contract = AnswerContract(task_id="t1", answer_type="concept")
    
    # PASS scenario
    claim_val = ClaimValidationResult(status="PASS", violations=[], warnings=[])
    cov_val = AnswerCoverageValidationResult(status="PASS")
    res = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val)
    assert res.status == "PASS"
    assert not res.reason_codes
    
    # WARN scenario (contract degrading claim)
    claim_val_warn = ClaimValidationResult(
        status="WARN", 
        violations=[], 
        warnings=[ClaimValidationWarning(warning_code="curr_lang", reason="", severity="CONTRACT_DEGRADING_WARN", claim_id="c1")]
    )
    res2 = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val_warn)
    assert res2.status == "WARN"
    assert "claim_warning:curr_lang:c1" in res2.reason_codes
    
    # WARN scenario (non-blocking claim doesn't degrade contract)
    claim_val_nb = ClaimValidationResult(
        status="WARN", 
        violations=[], 
        warnings=[ClaimValidationWarning(warning_code="num", reason="", severity="NON_BLOCKING_WARN", claim_id="c2")]
    )
    res3 = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val_nb)
    assert res3.status == "PASS" # Contract stays PASS because warning was not CONTRACT_DEGRADING_WARN
    
    print("test_contract_evaluation_policy: PASS")
    
def test_adequate_support_semantics():
    print("\n--- Testing Adequate Support Semantics ---")
    contract = AnswerContract(task_id="t1", answer_type="concept")
    
    class MockSynthesisPlan:
        required_strong = 1
        required_adequate = 3
        required_weak = 0
        required_unsupported = 0
        
    contract.synthesis_coverage_plan = MockSynthesisPlan()
    
    claim_val = ClaimValidationResult(status="PASS", violations=[], warnings=[])
    cov_val = AnswerCoverageValidationResult(status="PASS")
    
    res = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val)
    
    # Only ADEQUATE topics exist (no weak/unsupported). Should PASS.
    assert res.status == "PASS"
    
    # Add WEAK
    contract.synthesis_coverage_plan.required_weak = 1
    res2 = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val)
    assert res2.status == "WARN"
    assert "required_topic_weak" in res2.reason_codes
    
    # Add UNSUPPORTED
    contract.synthesis_coverage_plan.required_unsupported = 1
    res3 = AnswerContractEvaluator.evaluate(contract, cov_val, claim_val)
    assert res3.status == "FAIL"
    assert "required_topic_unsupported" in res3.reason_codes
    
    print("test_adequate_support_semantics: PASS")

def test_source_title_detector():
    print("\n--- Testing Source Title Detector ---")
    # Simulate a book source
    sources = [
        {"metadata": {"title": "Reading Price Charts Bar By Bar", "knowledge_type": "book"}}
    ]
    
    terms = _source_reference_terms(sources)
    # The hardcoded generic "bea" should NOT be in terms
    assert "bea" not in terms
    assert "Reading Price Charts Bar By Bar" in terms
    
    # Simulate a report source
    sources_report = [
        {"metadata": {"title": "US CPI Report", "knowledge_type": "report"}}
    ]
    terms2 = _source_reference_terms(sources_report)
    assert "US CPI Report" in terms2
    
    print("test_source_title_detector: PASS")


if __name__ == "__main__":
    test_claim_warning_trace()
    test_contract_evaluation_policy()
    test_adequate_support_semantics()
    test_source_title_detector()
    print("\nALL TESTS PASSED")
