import pytest
from src.services.evidence.evidence_pipeline import EvidencePromptAssembler, AnswerContract, EvidenceBundle, EvidenceItem
from src.services.evidence.topic_evidence_binding import TopicEvidenceBinding, SynthesisCoveragePlan

def test_prompt_assembly_with_bindings():
    item1 = EvidenceItem(
        evidence_id="e1", task_id="task_1", evidence_type="book_passage", capability="static",
        content="This is core content", source_title="Source A"
    )
    bundle = EvidenceBundle(
        task_id="task_1", query="query", query_plan={}, answer_type="type",
        primary_evidence=[item1],
        supporting_evidence=[], current_market_evidence=[], event_evidence=[], technical_evidence=[],
        source_requirements=[], required_evidence_roles=[], freshness_summary={},
    )
    bundle.all_items = [item1]
    
    contract = AnswerContract(
        task_id="task_1", answer_type="type", required_sections=[], required_evidence_roles=[], required_source_refs=[]
    )
    contract.topic_bindings = [
        TopicEvidenceBinding(
            task_id="task_1", topic_role="core_concept", required=True, topic_description="Explain core concept",
            primary_evidence_ids=["e1"], supporting_evidence_ids=[], topic_support_score=0.9, binding_confidence="high"
        )
    ]
    contract.synthesis_coverage_plan = SynthesisCoveragePlan(
        task_id="task_1", required_topics=["core_concept"], supported_topics=["core_concept"], weak_topics=[], unsupported_topics=[],
        required_output_order=["core_concept"]
    )
    
    assembler = EvidencePromptAssembler()
    prompt = assembler.assemble([bundle], [contract], "What is SMC?")
    
    assert "EVIDENCE REPOSITORY" in prompt
    assert "TOPIC-SPECIFIC INSTRUCTIONS" in prompt
    assert "TOPIC: core_concept" in prompt
    assert "Primary evidence IDs: e1" in prompt
