import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import knowledge_result, query_plan, task_view  # noqa: E402
from src.services.evidence import AnswerContractBuilder, EvidencePromptAssembler, EvidenceSelector  # noqa: E402
from src.services.semantic.context_execution import ContextAcquisitionResult  # noqa: E402


class PromptAssemblerEvidenceHandoffTests(unittest.TestCase):
    def test_acquisition_result_as_dict_preserves_retrieved_content(self):
        result = knowledge_result()
        payload = result.as_dict()

        self.assertIn("data", payload)
        self.assertIn("trader behavior", payload["data"][0]["content"])

    def test_content_survives_to_structured_prompt_with_provenance_separate(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        result = knowledge_result()
        round_trip = ContextAcquisitionResult(**{key: value for key, value in result.as_dict().items() if key in ContextAcquisitionResult.__dataclass_fields__})
        bundle = EvidenceSelector().select(plan, task_view(plan), [round_trip], "static_explanation", "task_1")
        contract = AnswerContractBuilder().build(bundle)
        prompt = EvidencePromptAssembler().assemble([bundle], [contract], plan["original_query"], "COMPLETE")

        self.assertIn("PRIMARY EVIDENCE", prompt)
        self.assertIn("Content:", prompt)
        self.assertIn("trader behavior", prompt)
        self.assertIn("Source: Reading Price Charts Bar by Bar", prompt)
        self.assertIn("Author/Organization: Al Brooks", prompt)


if __name__ == "__main__":
    unittest.main()
