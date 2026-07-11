from scripts.test_macro_answer_repair import _FakeClaimValidator, _FakeLLM, _contract
from src.orchestrator import RAGOrchestrator


class _ExplodingRetrieval:
    def __getattr__(self, name):
        raise AssertionError("repair must not call retrieval, acquisition, or tools")


def test_answer_repair_does_not_call_retrieval_or_acquisition():
    orch = RAGOrchestrator.__new__(RAGOrchestrator)
    orch.llm_service = _FakeLLM("Bao cao cho thay toc do tang cham lai so voi thang truoc.")
    orch.claim_evidence_validator = _FakeClaimValidator(["PASS", "PASS"])
    orch.retrieval_adapter = _ExplodingRetrieval()
    orch.context_acquisition_executor = _ExplodingRetrieval()

    final_answer, _, _, repair_status = orch._validate_and_maybe_repair_answer(
        draft_answer="CPI 3.4%, previous 3.1%.",
        user_query="CPI report noi gi ve inflation?",
        structured_prompt="PRIMARY EVIDENCE: already provided.",
        short_term_history=[],
        evidence_bundles=[],
        answer_contracts=[_contract()],
        runtime_artifacts={},
    )

    assert repair_status == "ATTEMPTED_IMPROVED"
    assert "toc do tang cham lai" in final_answer
    assert orch.llm_service.calls == 1

