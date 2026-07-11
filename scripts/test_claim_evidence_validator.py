import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import cpi_report_result, knowledge_result, query_plan, task_view  # noqa: E402
from src.services.evidence import AnswerContractBuilder, ClaimEvidenceValidator, EvidenceSelector  # noqa: E402


class ClaimEvidenceValidatorTests(unittest.TestCase):
    def test_book_author_claim_without_direct_passage_fails(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        metadata_only = knowledge_result(content="Copyright 2009. ISBN 978-0-000. Library of Congress data.")
        bundle = EvidenceSelector().select(plan, task_view(plan), [metadata_only], "static_explanation", "task_1")
        contract = AnswerContractBuilder().build(bundle)

        result = ClaimEvidenceValidator().validate("Theo Al Brooks, price action la...", [bundle], [contract])

        self.assertEqual(result.status, "FAIL")
        self.assertIn("author_attribution_without_direct_book_evidence", result.violations)

    def test_market_price_claim_without_market_snapshot_fails_when_required(self):
        plan = query_plan(
            primary_intent="macro_market_impact",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            macro_events=["CPI"],
            organizations=["BLS"],
            symbols=["XAUUSD"],
        )
        bundle = EvidenceSelector().select(plan, task_view(plan), [cpi_report_result()], "scenario_analysis", "task_1")
        contract = AnswerContractBuilder().build(bundle)

        result = ClaimEvidenceValidator().validate("XAUUSD dang o 2345 va phan ung manh.", [bundle], [contract])

        self.assertEqual(result.status, "FAIL")
        self.assertIn("current_market_claim_without_market_snapshot", result.violations)

    def test_numeric_claim_without_numeric_evidence_warns(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        bundle = EvidenceSelector().select(plan, task_view(plan), [knowledge_result()], "static_explanation", "task_1")
        contract = AnswerContractBuilder().build(bundle)

        result = ClaimEvidenceValidator().validate("Setup nay co 3 diem can luu y.", [bundle], [contract])

        self.assertEqual(result.status, "WARN")
        self.assertIn("numeric_claim_without_numeric_evidence", result.warnings)


if __name__ == "__main__":
    unittest.main()
