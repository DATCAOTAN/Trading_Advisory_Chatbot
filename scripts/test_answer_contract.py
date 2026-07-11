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
    ohlcv_result,
    query_plan,
    task_view,
)
from src.services.evidence import AnswerContractBuilder, EvidenceSelector  # noqa: E402


class AnswerContractTests(unittest.TestCase):
    def _contract(self, plan, results, answer_type):
        bundle = EvidenceSelector().select(plan, task_view(plan), results, answer_type, plan["task_id"])
        return AnswerContractBuilder().build(bundle)

    def test_book_contract_prohibits_title_only_author_inference(self):
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        contract = self._contract(plan, [knowledge_result()], "static_explanation")

        self.assertIn("direct_book_passage", contract.required_evidence_roles)
        self.assertIn("title_only_inference", contract.prohibited_claim_types)

    def test_report_contract_requires_official_report_role(self):
        plan = query_plan(
            primary_intent="macro_report_summary",
            query="CPI report noi gi ve inflation?",
            macro_events=["CPI"],
            organizations=["BLS"],
        )
        contract = self._contract(plan, [cpi_report_result()], "report_summary")

        self.assertIn("official_report", contract.required_evidence_roles)

    def test_macro_impact_contract_requires_report_event_and_market(self):
        plan = query_plan(
            primary_intent="macro_market_impact",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            macro_events=["CPI"],
            organizations=["BLS"],
            symbols=["XAUUSD"],
        )
        contract = self._contract(plan, [cpi_report_result(), event_result(), market_result()], "scenario_analysis")

        self.assertEqual(contract.required_evidence_roles, ["official_report", "economic_event", "market_snapshot"])
        self.assertIn("bullish_scenario", contract.required_sections)

    def test_market_analysis_contract_requires_market_and_ohlcv(self):
        plan = query_plan(primary_intent="market_state_analysis", query="XAUUSD hien tai ra sao?", symbols=["XAUUSD"])
        contract = self._contract(plan, [market_result(), ohlcv_result()], "market_analysis")

        self.assertEqual(contract.required_evidence_roles, ["market_snapshot", "ohlcv"])
        self.assertIn("current_claim_without_market_snapshot", contract.prohibited_claim_types)


if __name__ == "__main__":
    unittest.main()
