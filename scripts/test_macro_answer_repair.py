from src.orchestrator import RAGOrchestrator
from src.services.evidence.evidence_pipeline import AnswerContract, ClaimValidationResult
from src.services.evidence.topic_evidence_binding import TopicEvidenceBinding, SynthesisCoveragePlan


class _FakeLLM:
    def __init__(self, repaired_answer):
        self.repaired_answer = repaired_answer
        self.calls = 0

    def generate_evidence_contract_stream(self, query, structured_prompt, history):
        self.calls += 1
        yield self.repaired_answer


class _FakeClaimValidator:
    def __init__(self, statuses):
        self.statuses = list(statuses)

    def validate(self, answer, evidence_bundles, answer_contracts):
        status = self.statuses.pop(0) if self.statuses else "PASS"
        return ClaimValidationResult(status=status, violations=["unsupported_numeric"] if status == "FAIL" else [])


def _contract(topic="short_interpretation", score=0.9):
    binding = TopicEvidenceBinding(
        task_id="task_1",
        topic_role=topic,
        required=True,
        topic_description=topic,
        primary_evidence_ids=["ev1"],
        supporting_evidence_ids=[],
        topic_support_score=score,
        binding_confidence="high",
    )
    plan = SynthesisCoveragePlan(
        task_id="task_1",
        required_topics=[topic],
        required_total=1,
        required_strong=1,
    )
    return AnswerContract(
        task_id="task_1",
        answer_type="report_summary",
        topic_bindings=[binding],
        synthesis_coverage_plan=plan,
    )


def test_repair_improves_semantic_coverage_and_is_accepted():
    orch = RAGOrchestrator.__new__(RAGOrchestrator)
    orch.llm_service = _FakeLLM("Bao cao cho thay toc do tang cham lai so voi thang truoc va ap luc gia ha nhiet.")
    orch.claim_evidence_validator = _FakeClaimValidator(["PASS", "PASS"])
    artifacts = {}

    final_answer, claim_val, coverage_val, repair_status = orch._validate_and_maybe_repair_answer(
        draft_answer="CPI 3.4%, previous 3.1%, core CPI 3.2%.",
        user_query="CPI report noi gi ve inflation?",
        structured_prompt="PRIMARY EVIDENCE: CPI report content.",
        short_term_history=[],
        evidence_bundles=[],
        answer_contracts=[_contract()],
        runtime_artifacts=artifacts,
    )

    assert repair_status == "ATTEMPTED_IMPROVED"
    assert "toc do tang cham lai" in final_answer
    assert coverage_val.topic_statuses["short_interpretation"] == "COVERED"
    assert claim_val.status == "PASS"
    assert artifacts["contract_evaluation"]["repair_status"] == "ATTEMPTED_IMPROVED"


def test_regressed_repair_is_rejected_and_original_answer_retained():
    orch = RAGOrchestrator.__new__(RAGOrchestrator)
    orch.llm_service = _FakeLLM("Bao cao cho thay toc do tang cham lai va them so 99.9% khong co trong evidence.")
    orch.claim_evidence_validator = _FakeClaimValidator(["PASS", "FAIL"])

    original = "CPI 3.4%, previous 3.1%, core CPI 3.2%."
    final_answer, claim_val, _, repair_status = orch._validate_and_maybe_repair_answer(
        draft_answer=original,
        user_query="CPI report noi gi ve inflation?",
        structured_prompt="PRIMARY EVIDENCE: CPI report content.",
        short_term_history=[],
        evidence_bundles=[],
        answer_contracts=[_contract()],
        runtime_artifacts={},
    )

    assert repair_status == "ATTEMPTED_REGRESSED"
    assert final_answer == original
    assert claim_val.status == "PASS"

