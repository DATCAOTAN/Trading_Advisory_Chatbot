import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evidence_test_fixtures import market_result, ohlcv_result, query_plan, task_view  # noqa: E402
from src.services.evidence import AnswerContractBuilder, EvidenceSelector  # noqa: E402


class MarketStateFamilyAlignmentTests(unittest.TestCase):
    def test_market_state_required_topics_match_required_capabilities(self):
        plan = query_plan(
            primary_intent="market_state_analysis",
            query="XAUUSD hien tai dang chiu tac dong boi yeu to nao?",
            symbols=["XAUUSD"],
        )

        bundle = EvidenceSelector().select(
            plan,
            task_view(plan),
            [market_result(), ohlcv_result()],
            "market_analysis",
            "task_1",
        )
        contract = AnswerContractBuilder().build(bundle)
        required_topics = [topic.topic_role for topic in bundle.coverage_requirements.required_topics]
        optional_topics = [topic.topic_role for topic in bundle.coverage_requirements.optional_topics]

        self.assertEqual(required_topics, ["current_state", "recent_market_behavior"])
        self.assertIn("main_drivers", optional_topics)
        self.assertIn("confirmation_or_risk_factors", optional_topics)
        self.assertEqual(contract.required_evidence_roles, ["market_snapshot", "ohlcv"])
        self.assertNotIn("main_drivers", contract.required_sections)
        self.assertNotIn("confirmation_or_risk_factors", contract.required_sections)
        self.assertIn(bundle.coverage_result.status, {"COMPLETE", "DEGRADED"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

