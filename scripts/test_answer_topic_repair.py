from src.orchestrator import RAGOrchestrator
from src.services.evidence.evidence_pipeline import AnswerContract, ClaimValidationResult
from src.services.evidence.topic_evidence_binding import TopicEvidenceBinding, SynthesisCoveragePlan


class _FakeLLM:
    def generate_evidence_contract_stream(self, query, structured_prompt, history):
        yield "The report suggests mixed conditions and the context depends on observable market conditions."


class _FakeClaimValidator:
    def validate(self, answer, evidence_bundles, answer_contracts):
        return ClaimValidationResult(status="PASS")


def test_topic_repair_path_uses_current_orchestrator_api():
    orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
    orchestrator.llm_service = _FakeLLM()
    orchestrator.claim_evidence_validator = _FakeClaimValidator()

    contract = AnswerContract(
        task_id="t1",
        answer_type="report_summary",
        topic_bindings=[
            TopicEvidenceBinding(
                task_id="t1",
                topic_role="short_interpretation",
                required=True,
                topic_description="",
                primary_evidence_ids=["e1"],
                supporting_evidence_ids=[],
                topic_support_score=0.9,
                binding_confidence="high",
            )
        ],
        synthesis_coverage_plan=SynthesisCoveragePlan(
            task_id="t1",
            required_topics=["short_interpretation"],
            required_total=1,
            required_strong=1,
            required_output_order=["short_interpretation"],
        ),
    )

    artifacts = {}
    final_answer, claim_validation, coverage, repair_status = orchestrator._validate_and_maybe_repair_answer(
        draft_answer="CPI 3.4%, previous 3.1%.",
        user_query="CPI report noi gi ve inflation?",
        structured_prompt="PRIMARY EVIDENCE: CPI report.",
        short_term_history=[],
        evidence_bundles=[],
        answer_contracts=[contract],
        runtime_artifacts=artifacts,
    )

    assert claim_validation.status == "PASS"
    assert repair_status in {"ATTEMPTED_IMPROVED", "ATTEMPTED_NO_IMPROVEMENT"}
    assert coverage.status in {"PASS", "WARN"}
    assert "contract_evaluation" in artifacts
    assert final_answer
