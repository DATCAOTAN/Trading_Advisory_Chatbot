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
from src.services.evidence import EvidenceRefinementPlanner, EvidenceSelector  # noqa: E402


class EvidenceRefinementTests(unittest.TestCase):
    def test_metadata_only_correct_source_triggers_bounded_refinement_need(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        result = knowledge_result(content="Copyright 2009. ISBN 978-0-000. Library of Congress data.")

        bundle = EvidenceSelector().select(plan, task_view(plan), [result], "static_explanation", "task_1")

        self.assertNotEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertTrue(EvidenceRefinementPlanner.should_refine(bundle))

    def test_useful_direct_evidence_does_not_trigger_refinement(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        
        # Must provide enough coverage to satisfy topics for book_concept_explanation
        content = "Price action is about trade entry setup and method process rules context condition environment"
        bundle = EvidenceSelector().select(plan, task_view(plan), [knowledge_result(content=content)], "static_explanation", "task_1")

        self.assertEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertFalse(EvidenceRefinementPlanner.should_refine(bundle))


if __name__ == "__main__":
    unittest.main()
