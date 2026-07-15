import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator import RAGOrchestrator
from src.services.agents.answer_compliance import AgentAnswerComplianceInputBuilder
from src.services.agents.consistency import ConsistencyInputAssembler
from src.services.agents.projection import compact_agent_payload
from src.services.agents.risk import RiskInputAssembler
from src.services.agents.runtime import AgentExecutionPlan, AgentResultAggregator, AgentResultEnvelope, AgentRuntimeContext, AgentStatus, AgentTaskEnvelope
from src.services.agents.strategy import StrategyInputAssembler


class Decision:
    request_id = "compression_req"
    confidence_ceiling = "high"
    query_plan = {
        "task_id": "task_1",
        "primary_intent": "market_state_analysis",
        "temporal_scope": "current",
        "entities": {"symbols": ["XAUUSD"]},
    }


def market_payload(parent="task_1"):
    return {
        "request_id": "compression_req",
        "task_id": f"{parent}:MarketContextAgent",
        "symbol": "XAUUSD",
        "as_of": "2026-07-12T00:00:00Z",
        "assessment_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "market_state": {
            "directional_bias": "balanced",
            "trend_state": "range",
            "momentum_state": "mixed",
            "volatility_regime": "elevated",
            "structure_state": "range",
        },
        "macro_context": {"active_events": ["macro"], "macro_pressure": "present"},
        "dominant_factors": [
            {"factor": f"factor_{i}", "directional_pressure": "mixed", "support_strength": "adequate", "evidence_refs": [f"evidence_bundle:{parent}"]}
            for i in range(8)
        ],
        "conflicting_signals": [
            {"signal_a": "macro", "signal_b": "momentum", "explanation": "mixed", "evidence_refs": [f"evidence_bundle:{parent}"]}
            for _ in range(5)
        ],
        "confirmation_conditions": {"neutral_or_range_confirmation": "range remains confirmed"},
        "invalidation_conditions": ["new context contradicts range"] * 5,
        "uncertainty": {
            "confidence": 0.65,
            "confidence_ceiling": "high",
            "missing_context": [],
            "limitations": ["limited context"] * 8,
            "conflicting_context": ["mixed macro and momentum"],
        },
        "summary": "Compact market context only.",
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD", "ohlcv:XAUUSD"],
        "market_context_input": {"raw": "x" * 12000},
    }


def strategy_payload(parent="task_1"):
    return {
        "request_id": "compression_req",
        "task_id": f"{parent}:StrategyAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-12T00:00:00Z",
        "intent_family": "market_state_analysis",
        "thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "thesis_type": "mixed",
        "thesis_direction": "mixed",
        "thesis_summary": "Conditional thesis.",
        "supporting_factors": [{"factor": f"support_{i}", "evidence_refs": [f"evidence_bundle:{parent}"]} for i in range(8)],
        "conflicting_factors": [{"factor": "macro", "conflict_with": "momentum", "evidence_refs": [f"evidence_bundle:{parent}"]}],
        "activation_conditions": [{"condition": "confirmation", "context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"]}],
        "invalidation_conditions": [{"condition": "invalidation", "context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"]}],
        "limitations": ["conditional only"] * 8,
        "missing_context": [],
        "confidence": {"value": 0.55, "ceiling": "high"},
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
    }


def risk_payload(parent="task_1"):
    return {
        "request_id": "compression_req",
        "task_id": f"{parent}:RiskAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-12T00:00:00Z",
        "intent_family": "market_state_analysis",
        "risk_ref": f"risk_assessment:{parent}:RiskAgent",
        "assessed_strategy_thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "assessed_market_context_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "overall_risk_level": "elevated",
        "risk_posture": "conflicting_context",
        "confidence_adjustment": {"original_strategy_confidence": 0.55, "adjusted_confidence": 0.5},
        "key_risks": [{"risk_type": f"risk_{i}", "evidence_refs": [f"evidence_bundle:{parent}"]} for i in range(8)],
        "thesis_fragility": {"weak_points": ["mixed context"] * 8},
        "conflicting_factors": [{"factor": "macro", "conflict_with": "momentum"}],
        "confirmation_requirements": [{"requirement": "confirmation"}],
        "invalidation_risks": [{"condition": "invalidation", "severity": "elevated"}],
        "limitations": ["risk critique only"] * 8,
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{parent}:StrategyAgent"],
    }


def consistency_payload(parent="task_1"):
    return {
        "request_id": "compression_req",
        "task_id": f"{parent}:StrategyRiskConsistencyAgent",
        "parent_task_id": parent,
        "symbol": "XAUUSD",
        "as_of": "2026-07-12T00:00:00Z",
        "intent_family": "market_state_analysis",
        "consistency_ref": f"consistency_assessment:{parent}:StrategyRiskConsistencyAgent",
        "assessed_market_context_ref": f"market_context_assessment:{parent}:MarketContextAgent",
        "assessed_strategy_thesis_ref": f"strategy_thesis:{parent}:StrategyAgent",
        "assessed_risk_assessment_ref": f"risk_assessment:{parent}:RiskAgent",
        "consistency_status": "risk_weakened",
        "final_presentation_mode": "mixed_or_uncertain",
        "thesis_strength_after_risk": "weak",
        "confidence_reconciliation": {"strategy_confidence": 0.55, "risk_adjusted_confidence": 0.5, "final_confidence": 0.5},
        "agreement_points": [{"point": "conditional", "evidence_refs": [f"evidence_bundle:{parent}"]}],
        "contradiction_points": [{"strategy_claim": "mixed", "risk_objection": "elevated"}],
        "required_final_answer_emphasis": ["cautious_language", "uncertainty"],
        "prohibited_final_answer_patterns": ["trading_instruction", "entry_sl_tp", "position_sizing"],
        "final_synthesis_guidance": "Use cautious conditional framing.",
        "limitations": ["not evidence"] * 8,
        "evidence_refs": [f"evidence_bundle:{parent}"],
        "source_refs": ["market_snapshot:XAUUSD"],
        "market_context_refs": [f"market_context_assessment:{parent}:MarketContextAgent"],
        "strategy_thesis_refs": [f"strategy_thesis:{parent}:StrategyAgent"],
        "risk_assessment_refs": [f"risk_assessment:{parent}:RiskAgent"],
    }


def result(agent_type, payload, parent="task_1"):
    return AgentResultEnvelope(
        task_id=f"{parent}:{agent_type}",
        parent_task_id=parent,
        agent_type=agent_type,
        status=AgentStatus.SUCCESS,
        structured_payload=payload,
        evidence_refs=[f"evidence_bundle:{parent}"],
        source_refs=["market_snapshot:XAUUSD"],
        confidence=0.5,
    )


def runtime_context(prior_results):
    return AgentRuntimeContext(
        decision_context_ref=Decision(),
        query_plan_ref=Decision.query_plan,
        task_context_refs={"task_1": {"task_id": "task_1", "confidence_ceiling": "high"}},
        metadata={"agent_results_by_task": {item.task_id: item for item in prior_results}},
    )


class AgentStackCompressionTests(unittest.TestCase):
    def test_compact_projection_preserves_refs_identity_confidence_and_limits_size(self):
        raw = market_payload()
        compact = compact_agent_payload("MarketContextAgent", raw)

        self.assertEqual(compact["assessment_ref"], raw["assessment_ref"])
        self.assertEqual(compact["task_id"], raw["task_id"])
        self.assertEqual(compact["uncertainty"]["confidence"], 0.65)
        self.assertIn("evidence_bundle:task_1", compact["evidence_refs"])
        self.assertNotIn("market_context_input", compact)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(raw)) * 0.8)

    def test_strategy_input_uses_compact_market_context(self):
        ctx = runtime_context([result("MarketContextAgent", market_payload())])
        task = AgentTaskEnvelope("task_1:StrategyAgent", "StrategyAgent", parent_task_id="task_1", intent_family="market_state_analysis", evidence_refs=["evidence_bundle:task_1"])

        strategy_input = StrategyInputAssembler.assemble(task, ctx)

        self.assertNotIn("market_context_input", strategy_input.market_context_assessment)
        self.assertEqual(strategy_input.market_context_assessment_ref, "market_context_assessment:task_1:MarketContextAgent")
        self.assertLessEqual(len(strategy_input.market_context_assessment["dominant_factors"]), 3)

    def test_risk_input_uses_compact_market_and_strategy_payloads(self):
        ctx = runtime_context([
            result("MarketContextAgent", market_payload()),
            result("StrategyAgent", strategy_payload()),
        ])
        task = AgentTaskEnvelope("task_1:RiskAgent", "RiskAgent", parent_task_id="task_1", intent_family="market_state_analysis", evidence_refs=["evidence_bundle:task_1"])

        risk_input = RiskInputAssembler.assemble(task, ctx)

        self.assertNotIn("market_context_input", risk_input.market_context_assessment)
        self.assertEqual(risk_input.strategy_thesis_ref, "strategy_thesis:task_1:StrategyAgent")
        self.assertLessEqual(len(risk_input.strategy_thesis["supporting_factors"]), 3)

    def test_consistency_input_uses_compact_agent_payloads(self):
        ctx = runtime_context([
            result("MarketContextAgent", market_payload()),
            result("StrategyAgent", strategy_payload()),
            result("RiskAgent", risk_payload()),
        ])
        task = AgentTaskEnvelope("task_1:StrategyRiskConsistencyAgent", "StrategyRiskConsistencyAgent", parent_task_id="task_1", intent_family="market_state_analysis", evidence_refs=["evidence_bundle:task_1"])

        consistency_input = ConsistencyInputAssembler.assemble(task, ctx)

        self.assertEqual(consistency_input.strategy_thesis_ref, "strategy_thesis:task_1:StrategyAgent")
        self.assertEqual(consistency_input.risk_assessment_ref, "risk_assessment:task_1:RiskAgent")
        self.assertLessEqual(len(consistency_input.risk_assessment["key_risks"]), 3)

    def test_compliance_input_uses_task_analysis_snapshot_and_compact_payloads(self):
        runtime_artifacts = {
            "agent_runtime": {
                "execution_plan": {
                    "request_id": "compression_req",
                    "parent_intent": "market_state_analysis",
                    "execution_allowed": False,
                    "tasks": [{"parent_task_id": "task_1", "intent_family": "market_state_analysis", "source_refs": ["market_snapshot:XAUUSD"]}],
                },
                "handoff": {
                    "request_id": "compression_req",
                    "agent_results": [
                        result("MarketContextAgent", market_payload()).as_dict(),
                        result("StrategyAgent", strategy_payload()).as_dict(),
                        result("RiskAgent", risk_payload()).as_dict(),
                        result("StrategyRiskConsistencyAgent", consistency_payload()).as_dict(),
                    ],
                },
            },
            "evidence_bundles": [{"task_id": "task_1"}],
        }

        built = AgentAnswerComplianceInputBuilder.build("Cautious conditional answer with risk and uncertainty.", runtime_artifacts, [])

        self.assertIn("task_1", built.task_analysis_snapshots_by_task)
        self.assertNotIn("market_context_input", built.market_context_assessments_by_task["task_1"])
        self.assertEqual(built.consistency_assessments_by_task["task_1"]["final_presentation_mode"], "mixed_or_uncertain")
        self.assertLess(len(json.dumps(built.as_dict())), 20000)

    def test_prompt_enrichment_preserves_analysis_marker_refs_and_constraints(self):
        artifacts = {
            "handoff": {
                "agent_results": [
                    result("MarketContextAgent", market_payload()).as_dict(),
                    result("StrategyAgent", strategy_payload()).as_dict(),
                    result("RiskAgent", risk_payload()).as_dict(),
                    result("StrategyRiskConsistencyAgent", consistency_payload()).as_dict(),
                ]
            }
        }

        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", artifacts)

        self.assertIn("not evidence", prompt.lower())
        self.assertIn("task_1", prompt)
        self.assertIn("market_context_assessment:task_1:MarketContextAgent", prompt)
        self.assertIn("risk_posture", prompt)
        self.assertIn("final_presentation_mode", prompt)
        self.assertNotIn("entry_price", prompt)

    def test_static_book_task_does_not_gain_market_context(self):
        runtime_artifacts = {
            "agent_runtime": {
                "execution_plan": {"request_id": "compression_req", "parent_intent": "book_concept_explanation", "execution_allowed": False, "tasks": []},
                "handoff": {"request_id": "compression_req", "agent_results": []},
            },
            "evidence_bundles": [{"task_id": "task_1"}],
        }
        built = AgentAnswerComplianceInputBuilder.build("Static explanation.", runtime_artifacts, [])

        self.assertEqual(built.market_context_assessments_by_task, {})
        self.assertFalse(built.execution_allowed)

    def test_static_no_agent_plan_aggregation_remains_skipped(self):
        plan = AgentExecutionPlan(
            request_id="compression_req",
            parent_plan_id="plan_static",
            parent_intent="book_concept_explanation",
            execution_allowed=False,
        )

        aggregate = AgentResultAggregator.aggregate(plan, [])

        self.assertEqual(aggregate.status, "SKIPPED")
        self.assertEqual(aggregate.task_results, [])

    def test_static_no_agent_prompt_has_no_market_agent_enrichment(self):
        artifacts = {"handoff": {"agent_results": []}}

        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", artifacts)

        self.assertEqual(prompt, "BASE")
        self.assertNotIn("MarketContextAssessment", prompt)
        self.assertNotIn("StrategyThesis", prompt)
        self.assertNotIn("RiskAssessment", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
