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
from src.services.decision_context import DecisionContext  # noqa: E402
from src.services.evidence import AnswerContractBuilder, EvidencePromptAssembler, EvidenceSelector  # noqa: E402
from src.services.orchestrator_contract import OrchestratorOutput  # noqa: E402
from src.services.response_gate import ResponseGate  # noqa: E402


class EvidenceAnswerEndToEndTests(unittest.TestCase):
    def _context(self, plan, evidence_status):
        return DecisionContext(
            request_id="test",
            user_query=plan["original_query"],
            normalized_query=plan["normalized_query"],
            query_intent={},
            answer_mode={},
            query_plan=plan,
            sufficiency={"status": "COMPLETE", "confidence_ceiling": "high"},
            evidence_sufficiency=evidence_status,
            confidence_ceiling=evidence_status.get("confidence_ceiling", "low"),
        )

    def test_complete_context_but_insufficient_evidence_blocks_normal_synthesis(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        metadata_only = knowledge_result(content="Copyright 2009. ISBN 978-0-000. Library of Congress data.")
        bundle = EvidenceSelector().select(plan, task_view(plan), [metadata_only], "static_explanation", "task_1")
        ctx = self._context(plan, bundle.sufficiency.as_dict())

        gate = ResponseGate.evaluate(ctx, OrchestratorOutput(answer_type="static_explanation", execution_allowed=False))

        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertEqual(gate.answer_type, "insufficient_context")
        self.assertIn("bang chung truc tiep", gate.message)

    def test_useful_evidence_allows_structured_prompt_synthesis(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        bundle = EvidenceSelector().select(plan, task_view(plan), [knowledge_result()], "static_explanation", "task_1")
        contract = AnswerContractBuilder().build(bundle)
        prompt = EvidencePromptAssembler().assemble([bundle], [contract], plan["original_query"], "COMPLETE")
        ctx = self._context(plan, bundle.sufficiency.as_dict())

        gate = ResponseGate.evaluate(ctx, OrchestratorOutput(answer_type="static_explanation", execution_allowed=False))

        self.assertTrue(gate.normal_synthesis_allowed)
        self.assertIn("SYSTEM RESPONSE CONTRACT", prompt)
        self.assertIn("PRIMARY EVIDENCE", prompt)
        self.assertIn("trader behavior", prompt)


if __name__ == "__main__":
    unittest.main()
