import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.evidence.evidence_pipeline import TopicRepairDecision
from src.services.evidence.answer_coverage import AnswerCoverageValidationResult
from src.services.evidence.evidence_pipeline import AnswerContractEvaluator, AnswerContract, ContractEvaluationResult
from src.services.evidence.evidence_pipeline import ClaimValidationResult

def test_topic_repair_decision():
    print("\n--- Testing TopicRepairDecision ---")
    
    # 1. Answer topic COVERED + STRONG evidence. (repair_allowed=false)
    dec1 = TopicRepairDecision.evaluate("t1", "core_concept", "COVERED", "STRONG")
    assert not dec1.repair_allowed
    assert dec1.reason_code == "already_covered"
    
    # 2. Answer topic UNCERTAIN + ADEQUATE evidence. (repair_allowed=true)
    dec2 = TopicRepairDecision.evaluate("t2", "context_or_conditions", "UNCERTAIN", "ADEQUATE")
    assert dec2.repair_allowed
    assert dec2.reason_code == "uncertain_answer_with_adequate_evidence"
    
    # 3. Answer topic PARTIAL + STRONG evidence. (repair_allowed=true)
    dec3 = TopicRepairDecision.evaluate("t3", "methodology_or_process", "PARTIAL", "STRONG")
    assert dec3.repair_allowed
    assert dec3.reason_code == "missing_answer_with_strong_evidence"
    
    # 4. Answer topic MISSING + WEAK evidence. (repair_allowed=false)
    dec4 = TopicRepairDecision.evaluate("t4", "examples", "MISSING", "WEAK")
    assert not dec4.repair_allowed
    assert dec4.reason_code == "insufficient_evidence_strength"
    
    # 5. Maximum one repair attempt
    dec5 = TopicRepairDecision.evaluate("t5", "core_concept", "MISSING", "STRONG", repair_attempt_count=1)
    assert not dec5.repair_allowed
    assert dec5.reason_code == "max_attempts_reached"

    print("test_topic_repair_decision: PASS")

def test_contract_evaluation_with_repair_status():
    print("\n--- Testing ContractEvaluation with Repair Status ---")
    
    contract = AnswerContract(task_id="t1", answer_type="concept")
    
    cov_val_warn = AnswerCoverageValidationResult(status="WARN")
    claim_val_pass = ClaimValidationResult(status="PASS", violations=[], warnings=[])
    
    # Repair ATTEMPTED_NO_IMPROVEMENT should result in a WARN
    res1 = AnswerContractEvaluator.evaluate(contract, cov_val_warn, claim_val_pass, repair_status="ATTEMPTED_NO_IMPROVEMENT")
    assert res1.status == "WARN"
    assert "repair_attempted_no_improvement" in res1.reason_codes
    
    # Repair ATTEMPTED_REGRESSED should also result in a WARN
    res2 = AnswerContractEvaluator.evaluate(contract, cov_val_warn, claim_val_pass, repair_status="ATTEMPTED_REGRESSED")
    assert res2.status == "WARN"
    assert "repair_attempted_regressed" in res2.reason_codes
    
    # Repair ATTEMPTED_IMPROVED and coverage is PASS => Contract should be PASS
    cov_val_pass = AnswerCoverageValidationResult(status="PASS")
    res3 = AnswerContractEvaluator.evaluate(contract, cov_val_pass, claim_val_pass, repair_status="ATTEMPTED_IMPROVED")
    assert res3.status == "PASS"
    assert "repair_attempted_no_improvement" not in res3.reason_codes
    assert "repair_attempted_regressed" not in res3.reason_codes
    assert res3.repair_status == "ATTEMPTED_IMPROVED"
    
    print("test_contract_evaluation_with_repair_status: PASS")

if __name__ == "__main__":
    test_topic_repair_decision()
    test_contract_evaluation_with_repair_status()
    print("\nALL TESTS PASSED")
