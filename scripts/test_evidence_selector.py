import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import (  # noqa: E402
    cpi_report_result,
    event_result,
    knowledge_result,
    market_result,
    query_plan,
    task_view,
)
from src.services.evidence import EvidenceSelector  # noqa: E402


class EvidenceSelectorTests(unittest.TestCase):
    def setUp(self):
        self.selector = EvidenceSelector()

    def test_correct_source_useful_passage_becomes_primary(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        bundle = self.selector.select(plan, task_view(plan), [knowledge_result()], "static_explanation", "task_1")

        self.assertEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(bundle.required_evidence_roles, ["direct_book_passage"])
        self.assertEqual(len(bundle.primary_evidence), 1)
        self.assertIn("trader behavior", bundle.primary_evidence[0].content)

    def test_wrong_author_source_cannot_be_primary_evidence(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        wrong = knowledge_result(
            title="Technical Analysis of the Financial Markets",
            author="John Murphy",
            content="Price patterns and technical analysis are discussed in a broad market framework.",
        )

        bundle = self.selector.select(plan, task_view(plan), [wrong], "static_explanation", "task_1")

        self.assertEqual(bundle.primary_evidence, [])
        self.assertEqual(bundle.sufficiency.status, "INSUFFICIENT")
        self.assertIn("direct_book_passage", bundle.missing_evidence_roles)

    def test_macro_impact_bundle_separates_report_event_and_market_roles(self):
        plan = query_plan(
            primary_intent="macro_market_impact",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            symbols=["XAUUSD"],
            macro_events=["CPI"],
            organizations=["BLS"],
        )

        bundle = self.selector.select(
            plan,
            task_view(plan),
            [cpi_report_result(), event_result(), market_result()],
            "scenario_analysis",
            "task_1",
        )

        self.assertEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(len(bundle.primary_evidence), 1)
        self.assertEqual(len(bundle.event_evidence), 1)
        self.assertEqual(len(bundle.current_market_evidence), 1)
        self.assertIn("official_report", bundle.required_evidence_roles)
        self.assertIn("economic_event", bundle.required_evidence_roles)
        self.assertIn("market_snapshot", bundle.required_evidence_roles)


if __name__ == "__main__":
    unittest.main()
