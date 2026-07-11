import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.decision_context import DecisionContext
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.response_gate import ResponseGate


def make_context(primary_intent, sufficiency_status="COMPLETE", missing_required=None, **overrides):
    base = {
        "request_id": "resp",
        "user_query": "query",
        "normalized_query": "query",
        "query_intent": {},
        "answer_mode": {},
        "query_plan": {"primary_intent": primary_intent},
        "sufficiency": {
            "status": sufficiency_status,
            "confidence_ceiling": "high" if sufficiency_status == "COMPLETE" else "low",
            "missing_required": list(missing_required or []),
            "missing_optional": [],
        },
        "missing_required_context": list(missing_required or []),
    }
    base.update(overrides)
    return DecisionContext(**base)


class ResponseContractInvariantTests(unittest.TestCase):
    def build_and_gate(self, ctx):
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx))
        return output, ResponseGate.evaluate(ctx, output)

    def test_complete_static_explanation_allows_normal_synthesis(self):
        ctx = make_context("book_concept_explanation", static_knowledge_required=True)

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "static_explanation")
        self.assertTrue(gate.normal_synthesis_allowed)
        self.assertFalse(output.execution_allowed)

    def test_complete_scenario_analysis_allows_normal_synthesis(self):
        ctx = make_context(
            "macro_market_impact",
            static_knowledge_required=True,
            market_data_required=True,
            economic_calendar_required=True,
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "scenario_analysis")
        self.assertTrue(gate.normal_synthesis_allowed)
        self.assertFalse(output.execution_allowed)

    def test_degraded_allows_synthesis_with_medium_confidence(self):
        ctx = make_context(
            "market_state_analysis",
            "DEGRADED",
            market_data_required=True,
            missing_optional_context=["technical_snapshot:XAUUSD"],
            sufficiency={
                "status": "DEGRADED",
                "confidence_ceiling": "medium",
                "missing_required": [],
                "missing_optional": ["technical_snapshot:XAUUSD"],
            },
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "market_analysis")
        self.assertTrue(gate.normal_synthesis_allowed)
        self.assertEqual(gate.confidence_ceiling, "medium")

    def test_insufficient_blocks_normal_synthesis(self):
        ctx = make_context(
            "book_concept_explanation",
            "INSUFFICIENT",
            missing_required=["static_knowledge:price_action"],
            static_knowledge_required=True,
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertIn("static_knowledge:price_action", gate.missing_context)
        self.assertIn("khong the", gate.message.lower())

    def test_wrong_author_source_cannot_get_author_attributed_contract(self):
        ctx = make_context(
            "book_concept_explanation",
            "INSUFFICIENT",
            missing_required=["static_knowledge:price_action"],
            acquisition_results=[
                {
                    "capability": "static_knowledge",
                    "target": "price_action",
                    "status": "failed",
                    "provenance": {"title": "Price-Action-Trading-Guide.pdf"},
                }
            ],
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertEqual(output.source_refs, [])

    def test_wrong_organization_source_cannot_get_official_report_contract(self):
        ctx = make_context(
            "macro_report_summary",
            "INSUFFICIENT",
            missing_required=["official_report:CPI"],
            acquisition_results=[
                {
                    "capability": "official_report",
                    "target": "CPI",
                    "status": "failed",
                    "provenance": {"title": "Gold Market Commentary", "organization": "World Gold Council"},
                }
            ],
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertEqual(output.source_refs, [])

    def test_multi_intent_one_task_insufficient_blocks_normal_synthesis(self):
        ctx = make_context(
            "multi_intent",
            "INSUFFICIENT",
            missing_required=["official_report:CPI"],
            query_plan={
                "primary_intent": "multi_intent",
                "child_plans": [
                    {"task_id": "task_1", "primary_intent": "macro_market_impact"},
                    {"task_id": "task_2", "primary_intent": "market_state_analysis"},
                ],
            },
            sufficiency={
                "status": "INSUFFICIENT",
                "confidence_ceiling": "low",
                "missing_required": ["official_report:CPI"],
                "task_statuses": {
                    "task_1": {"status": "INSUFFICIENT"},
                    "task_2": {"status": "COMPLETE"},
                },
            },
        )

        output, gate = self.build_and_gate(ctx)

        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertFalse(output.execution_allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
