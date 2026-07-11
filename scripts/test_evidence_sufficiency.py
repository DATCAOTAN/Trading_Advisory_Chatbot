import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import knowledge_result, market_result, ohlcv_result, query_plan, task_view  # noqa: E402
from src.services.evidence import EvidenceSelector  # noqa: E402


class EvidenceSufficiencyTests(unittest.TestCase):
    def setUp(self):
        self.selector = EvidenceSelector()

    def test_required_direct_book_evidence_complete(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        bundle = self.selector.select(plan, task_view(plan), [knowledge_result()], "static_explanation", "task_1")

        self.assertEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(bundle.confidence_ceiling, "high")

    def test_metadata_only_book_evidence_is_insufficient(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        metadata_doc = knowledge_result(
            content="Copyright 2009. ISBN 978-0-000. Library of Congress data. All rights reserved.",
        )

        bundle = self.selector.select(plan, task_view(plan), [metadata_doc], "static_explanation", "task_1")

        self.assertEqual(bundle.sufficiency.status, "INSUFFICIENT")
        self.assertIn("metadata_only_evidence_rejected", bundle.warnings)

    def test_stale_market_snapshot_does_not_satisfy_current_market_role(self):
        plan = query_plan(primary_intent="market_state_analysis", query="XAUUSD hien tai ra sao?", symbols=["XAUUSD"])
        bundle = self.selector.select(
            plan,
            task_view(plan),
            [market_result(freshness="stale"), ohlcv_result()],
            "market_analysis",
            "task_1",
        )

        self.assertEqual(bundle.sufficiency.status, "INSUFFICIENT")
        self.assertIn("market_snapshot", bundle.missing_evidence_roles)


if __name__ == "__main__":
    unittest.main()
