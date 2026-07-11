import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.evidence.evidence_pipeline import AnswerContractEvaluator, AnswerContract, ContractEvaluationResult
from src.services.evidence.answer_coverage import AnswerCoverageValidationResult
from src.services.evidence.evidence_pipeline import ClaimValidationResult
from src.ui.tab_chatbot import check_answer_completeness

class DummyPlan:
    def __init__(self, req_topics=[], req_un=0, req_weak=0):
        self.required_topics = req_topics
        self.required_unsupported = req_un
        self.required_weak = req_weak

class DummyContract(AnswerContract):
    def __init__(self, plan):
        super().__init__(task_id="t1", answer_type="test")
        self.synthesis_coverage_plan = plan

def test_contract_evaluation_cases():
    print("\n--- Testing Contract Evaluation Cases ---")
    
    # Case 1: claim=PASS, coverage=PASS, req evidence STRONG/ADEQUATE => contract=PASS
    plan1 = DummyPlan(req_un=0, req_weak=0)
    contract1 = DummyContract(plan1)
    res1 = AnswerContractEvaluator.evaluate(
        contract1, 
        AnswerCoverageValidationResult(status="PASS"), 
        ClaimValidationResult(status="PASS", violations=[], warnings=[])
    )
    assert res1.status == "PASS"

    # Case 2: claim=PASS, coverage=WARN (uncertain required topic) => contract=WARN
    res2 = AnswerContractEvaluator.evaluate(
        contract1, 
        AnswerCoverageValidationResult(status="WARN", missing_topics=["t1"]), 
        ClaimValidationResult(status="PASS", violations=[], warnings=[])
    )
    assert res2.status == "WARN"
    assert "answer_coverage_warn" in res2.topic_warnings

    # Case 3: claim=FAIL => contract=FAIL
    res3 = AnswerContractEvaluator.evaluate(
        contract1, 
        AnswerCoverageValidationResult(status="PASS"), 
        ClaimValidationResult(status="FAIL", violations=["viol_1"], warnings=[])
    )
    assert res3.status == "FAIL"
    assert "claim_violation:viol_1" in res3.reason_codes

    # Case 8: required topic WEAK => WARN
    plan_weak = DummyPlan(req_un=0, req_weak=1)
    contract_weak = DummyContract(plan_weak)
    res8 = AnswerContractEvaluator.evaluate(
        contract_weak, 
        AnswerCoverageValidationResult(status="PASS"), 
        ClaimValidationResult(status="PASS", violations=[], warnings=[])
    )
    assert res8.status == "WARN"
    
    # Case 9: required topic UNSUPPORTED => FAIL
    plan_unsupported = DummyPlan(req_un=1, req_weak=0)
    contract_unsupported = DummyContract(plan_unsupported)
    res9 = AnswerContractEvaluator.evaluate(
        contract_unsupported, 
        AnswerCoverageValidationResult(status="PASS"), 
        ClaimValidationResult(status="PASS", violations=[], warnings=[])
    )
    assert res9.status == "FAIL"

    print("All Contract Evaluation Cases PASS")

def test_answer_completeness_early_return():
    print("\n--- Testing AnswerCompleteness Fallbacks ---")
    text = "This is a dummy answer which has a good length but claims fail. " * 20
    
    # claim_validation_failed
    runtime_artifacts = {
        "claim_validation": {"status": "FAIL"},
        "contract_evaluation": {"status": "FAIL", "reason_codes": []}
    }
    result = check_answer_completeness(text, "STOP", 200, "FINANCIAL_RAG", "dummy_query", [], runtime_artifacts)
    print("Result early return:", result)
    assert result["overall_status"] == "FAIL"

    # Contract PASS, Claim PASS, Coverage PASS => overall PASS
    runtime_artifacts_pass = {
        "claim_validation": {"status": "PASS"},
        "contract_evaluation": {"status": "PASS", "reason_codes": []}
    }
    # Create an answer that satisfies structure, source reference, and length
    text_pass = """
- Bullet 1: Here is a properly constructed answer according to the standards. 
- Bullet 2: According to the guidelines, this is well-structured.
Theo bao cao, everything is fine. In conclusion, the system works.
    """ * 5
    
    result_pass = check_answer_completeness(text_pass, "STOP", 200, "FINANCIAL_RAG", "dummy_query", [], runtime_artifacts_pass)
    print("Result pass return:", result_pass)
    assert result_pass["overall_status"] in {"PASS", "WARN"}
    assert result_pass["claim_status"] == "PASS"
    assert result_pass["contract_status"] == "PASS"

    print("AnswerCompleteness Fallbacks PASS")


def _structured_long_answer(include_named_source: bool = False) -> str:
    source_line = "Theo US CPI Report cua BLS, " if include_named_source else ""
    return (
        f"1. Current state: {source_line}the market answer gives a direct state assessment with enough detail "
        "for runtime completeness checks and avoids relying on a report title when the contract does not require one.\n\n"
        "2. Recent behavior: the answer describes the observable movement context in a structured way and remains "
        "grounded in the provided dynamic evidence fields rather than inventing external report provenance.\n\n"
        "3. Risk context: the answer separates current state from possible risk factors and keeps source policy "
        "limited to the provenance required by the active answer contract.\n\n"
        "Ket luan: the response is complete for the selected contract and ends with a clear conclusion."
    )


def test_dynamic_market_state_without_named_source_does_not_fail_source_policy():
    answer = _structured_long_answer(include_named_source=False)
    runtime_artifacts = {
        "claim_validation": {"status": "PASS"},
        "contract_evaluation": {"status": "PASS", "reason_codes": [], "repair_status": "NOT_ATTEMPTED"},
        "evidence_sufficiency": {"status": "COMPLETE", "missing_roles": [], "warnings": []},
        "answer_contracts": [
            {
                "answer_type": "market_analysis",
                "required_sections": [],
                "required_evidence_roles": ["market_snapshot", "ohlcv"],
                "required_source_refs": [],
            }
        ],
    }

    result = check_answer_completeness(
        answer,
        "STOP",
        300,
        "FINANCIAL_RAG",
        "What is currently driving this market?",
        [],
        runtime_artifacts,
    )

    assert result["source_policy"] == "dynamic_provenance"
    assert result["reason"] != "missing_source_reference"
    assert result["overall_status"] in {"PASS", "WARN"}


def test_official_report_without_named_source_still_fails_source_policy():
    answer = _structured_long_answer(include_named_source=False)
    runtime_artifacts = {
        "claim_validation": {"status": "PASS"},
        "contract_evaluation": {"status": "PASS", "reason_codes": [], "repair_status": "NOT_ATTEMPTED"},
        "evidence_sufficiency": {"status": "COMPLETE", "missing_roles": [], "warnings": []},
        "answer_contracts": [
            {
                "answer_type": "report_summary",
                "required_sections": [],
                "required_evidence_roles": ["official_report"],
                "required_source_refs": ["Official Inflation Report - Statistical Agency"],
            }
        ],
    }

    result = check_answer_completeness(
        answer,
        "STOP",
        300,
        "FINANCIAL_RAG",
        "Official inflation report summary",
        [],
        runtime_artifacts,
    )

    assert result["source_policy"] == "named_source_required"
    assert result["overall_status"] == "FAIL"
    assert result["reason"] == "missing_source_reference"

if __name__ == "__main__":
    test_contract_evaluation_cases()
    test_answer_completeness_early_return()
    test_dynamic_market_state_without_named_source_does_not_fail_source_policy()
    test_official_report_without_named_source_still_fails_source_policy()
    print("\nALL TESTS PASSED")
