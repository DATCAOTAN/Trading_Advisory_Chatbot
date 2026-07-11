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
from src.services.evidence import EvidenceSelector  # noqa: E402


class EvidenceBundleTests(unittest.TestCase):
    def test_bundle_as_dict_preserves_content_provenance_and_freshness(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        bundle = EvidenceSelector().select(plan, task_view(plan), [knowledge_result()], "static_explanation", "task_1")
        payload = bundle.as_dict()

        primary = payload["primary_evidence"][0]
        self.assertIn("trader behavior", primary["content"])
        self.assertEqual(primary["source_title"], "Reading Price Charts Bar by Bar")
        self.assertEqual(primary["source_author"], "Al Brooks")
        self.assertEqual(primary["freshness_status"], "acceptable")

    def test_duplicate_chunks_are_redundancy_grouped(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        first = knowledge_result()
        duplicate = knowledge_result()

        bundle = EvidenceSelector().select(plan, task_view(plan), [first, duplicate], "static_explanation", "task_1")

        self.assertEqual(len(bundle.primary_evidence), 1)
        self.assertEqual(bundle.sufficiency.status, "COMPLETE")


if __name__ == "__main__":
    unittest.main()
