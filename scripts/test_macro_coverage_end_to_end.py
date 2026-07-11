from src.services.evidence.answer_coverage import AnswerCoverageValidator
from src.services.evidence.evidence_pipeline import AnswerContract, AnswerContractEvaluator, ClaimValidationResult
from src.services.evidence.topic_evidence_binding import TopicEvidenceBinding, SynthesisCoveragePlan


def test_macro_contract_passes_when_answer_roles_are_semantically_covered():
    topics = ["event_state", "confirmation_or_invalidation"]
    answer = (
        "Du lieu moi nhat cong bo CPI thuc te 0.3% so voi ky truoc 0.2%. "
        "Neu gia pha len tren khang cu va loi suat suy yeu, kich ban tang duoc xac nhan; "
        "neu gia pha xuong duoi ho tro va dong USD manh len, kich ban bi vo hieu."
    )
    coverage = AnswerCoverageValidator.evaluate(answer, topics)
    bindings = [
        TopicEvidenceBinding("task_1", topic, True, topic, ["ev1"], [], 0.9, "high")
        for topic in topics
    ]
    plan = SynthesisCoveragePlan(
        task_id="task_1",
        required_topics=topics,
        required_total=2,
        required_strong=2,
    )
    contract = AnswerContract(
        task_id="task_1",
        answer_type="scenario_analysis",
        topic_bindings=bindings,
        synthesis_coverage_plan=plan,
    )
    result = AnswerContractEvaluator.evaluate(contract, coverage, ClaimValidationResult(status="PASS"))

    assert coverage.status == "PASS"
    assert result.status == "PASS"

