import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import DecisionContext, RetrievedKnowledgeContext
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput


def make_context(**overrides):
    base = {
        "request_id": "req123",
        "user_query": "query",
        "normalized_query": "query",
        "query_intent": {"intent_type": "unknown"},
        "answer_mode": {"mode": "REPORT_SUMMARY"},
        "retrieved_sources": RetrievedKnowledgeContext(primary_sources=["Source A"], source_coverage_score=1.0),
    }
    base.update(overrides)
    return DecisionContext(**base)


class OrchestratorContractTests(unittest.TestCase):
    def test_static_context_returns_static_explanation_and_execution_false(self):
        ctx = make_context(static_knowledge_required=True)
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx))

        self.assertEqual(output.answer_type, "static_explanation")
        self.assertIn("StaticKnowledgeAgent", output.selected_agents)
        self.assertFalse(output.execution_allowed)

    def test_market_context_selects_market_agent(self):
        ctx = make_context(
            answer_mode={"mode": "MARKET_IMPACT"},
            market_data_required=True,
            static_knowledge_required=True,
        )
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx))

        self.assertEqual(output.answer_type, "scenario_analysis")
        self.assertIn("MarketDataAgent", output.selected_agents)
        self.assertIn("StaticKnowledgeAgent", output.selected_agents)
        self.assertFalse(output.execution_allowed)

    def test_trade_plan_missing_risk_context_has_no_position_size(self):
        ctx = make_context(
            answer_mode={"mode": "MARKET_IMPACT"},
            market_data_required=True,
            technical_snapshot_required=True,
            risk_context_required=True,
            execution_gate_required=True,
            missing_context=["risk_context"],
        )
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx, permissions={"execution": True}))

        self.assertEqual(output.answer_type, "trade_plan_draft_without_position_size")
        self.assertFalse(output.execution_allowed)
        self.assertTrue(any("position size" in warning.lower() for warning in output.risk_warnings))
        self.assertIn("collect_account_risk_constraints", output.next_actions)

    def test_missing_market_data_returns_insufficient_context_warning(self):
        ctx = make_context(
            answer_mode={"mode": "MARKET_IMPACT"},
            market_data_required=True,
            missing_context=["market_data"],
        )
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx))

        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(output.execution_allowed)
        self.assertTrue(any("market data" in warning.lower() for warning in output.risk_warnings))

    def test_available_agents_filter_is_respected(self):
        ctx = make_context(static_knowledge_required=True, market_data_required=True)
        output = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["MarketDataAgent"])
        )

        self.assertEqual(output.selected_agents, ["MarketDataAgent"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
