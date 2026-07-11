import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator import RAGOrchestrator
from src.services.agents import (
    AgentDispatcher,
    AgentExecutionPlanBuilder,
    AgentResultAggregator,
    AgentRuntimeContext,
    AgentRuntimeRegistry,
    AgentTaskEnvelope,
    MarketContextAgentRuntime,
    MarketContextAssessment,
    MarketContextInputAssembler,
)
from src.services.agents.market_context import (
    MarketContextAssessmentValidator,
    MarketContextVocabulary,
    PRESSURE_VALUES,
)
from src.services.agents.runtime import AgentResultValidator
from src.services.agents.runtime import AgentStatus, build_agent_handoff
from src.services.decision_context import DecisionContext, MarketSnapshot
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.semantic.query_plan import QueryPlan, QueryEntities


def result(result_id, capability, target, data, owner="task_1", source="existing_api"):
    return {
        "result_id": result_id,
        "task_id": result_id,
        "capability": capability,
        "target": target,
        "status": "success",
        "required": capability in {"market_snapshot", "official_report", "economic_event"},
        "requested_by_tasks": [owner],
        "task_ids": [owner],
        "data": data,
        "source": source,
        "provenance": {"source": source, "symbol": target, "timestamp": "2026-07-11T00:00:00Z"},
        "fetched_at": "2026-07-11T00:00:00Z",
        "source_timestamp": "2026-07-11T00:00:00Z",
        "freshness_status": "fresh",
    }


def market_results(owner="task_1"):
    return [
        result(
            "market_snapshot:XAUUSD",
            "market_snapshot",
            "XAUUSD",
            {
                "symbol": "XAUUSD",
                "timeframe": "1h",
                "latest_price": 2405.2,
                "ohlcv_summary": {"candles": 12, "first_close": 2390.0, "last_close": 2405.2},
                "recent_trend": "up",
                "volatility_note": "avg_range_pct=0.42",
                "support_resistance": {"recent_support": 2388.0, "recent_resistance": 2412.0},
                "source": "FakeFeed",
                "timestamp": "2026-07-11T00:00:00Z",
            },
            owner,
        ),
        result(
            "ohlcv:XAUUSD",
            "ohlcv",
            "XAUUSD",
            {"candles": 12, "first_close": 2390.0, "last_close": 2405.2},
            owner,
        ),
        result(
            "technical_snapshot:XAUUSD",
            "technical_snapshot",
            "XAUUSD",
            {"trend": "uptrend", "momentum": "bearish weakening", "volatility": "elevated", "source": "derived"},
            owner,
        ),
        result(
            "economic_event:macro",
            "economic_event",
            "macro",
            {"event_name": "Generic macro event", "country": "USD", "status": "available", "source": "existing_api"},
            owner,
        ),
        result(
            "official_report:macro",
            "official_report",
            "macro",
            {"title": "Generic official report", "content": "Inflation pressure context", "source": "official"},
            owner,
            source="official",
        ),
    ]


def decision_context(query_plan=None, acquisition_results=None, confidence_ceiling="medium"):
    query_plan = query_plan or QueryPlan(
        "market state",
        "market state",
        task_id="task_1",
        primary_intent="market_state_analysis",
        temporal_scope="current",
        entities=QueryEntities(symbols=["XAUUSD"]),
    ).as_dict()
    return DecisionContext(
        request_id="market_agent_req",
        user_query="market state",
        normalized_query="market state",
        query_intent={},
        answer_mode={"mode": "MARKET_ANALYSIS"},
        query_plan=query_plan,
        acquisition_results=list(acquisition_results or market_results()),
        task_context_views=[{"task_id": "task_1", "sufficiency_status": "COMPLETE", "confidence_ceiling": confidence_ceiling}],
        evidence_bundles=[{"task_id": "task_1", "items": [{"evidence_id": "e1"}]}],
        sufficiency={"status": "COMPLETE", "confidence_ceiling": confidence_ceiling},
        evidence_sufficiency={"status": "COMPLETE"},
        confidence_ceiling=confidence_ceiling,
        market_data_required=True,
        technical_snapshot_required=True,
    )


def task(source_refs=None, evidence_refs=None, intent="market_state_analysis", parent="task_1", timeout_ms=5000):
    if source_refs is None:
        source_refs = [item["result_id"] for item in market_results(owner=parent)]
    if evidence_refs is None:
        evidence_refs = [f"evidence_bundle:{parent}"]
    return AgentTaskEnvelope(
        task_id=f"{parent}:MarketContextAgent",
        parent_task_id=parent,
        agent_type="MarketContextAgent",
        intent_family=intent,
        required=True,
        source_refs=list(source_refs),
        evidence_refs=list(evidence_refs),
        timeout_ms=timeout_ms,
    )


class AboveCeilingBackend:
    def produce(self, market_input):
        assessment = MarketContextAssessment(
            request_id=market_input.request_id,
            task_id=market_input.task_id,
            symbol=market_input.symbol,
            as_of=market_input.as_of,
            market_state={
                "directional_bias": "bullish_pressure",
                "trend_state": "uptrend",
                "momentum_state": "strengthening",
                "volatility_regime": "elevated",
                "structure_state": "trend_continuation",
            },
            uncertainty={"confidence": 0.95, "confidence_ceiling": market_input.confidence_ceiling},
            summary="structured context only",
            evidence_refs=list(market_input.allowed_evidence_refs),
            source_refs=list(market_input.allowed_source_refs),
        )
        return assessment


class ForeignRefBackend:
    def __init__(self, source=False, evidence=False, execution=False):
        self.source = source
        self.evidence = evidence
        self.execution = execution

    def produce(self, market_input):
        return {
            "request_id": market_input.request_id,
            "task_id": market_input.task_id,
            "symbol": market_input.symbol,
            "as_of": market_input.as_of,
            "market_state": {
                "directional_bias": "bullish_pressure",
                "trend_state": "uptrend",
                "momentum_state": "strengthening",
                "volatility_regime": "elevated",
                "structure_state": "trend_continuation",
            },
            "macro_context": {},
            "technical_context": {},
            "dominant_factors": [],
            "conflicting_signals": [],
            "confirmation_conditions": {},
            "invalidation_conditions": [],
            "uncertainty": {"confidence": 0.6, "confidence_ceiling": market_input.confidence_ceiling},
            "summary": "place_order now" if self.execution else "structured context only",
            "evidence_refs": ["evidence_bundle:sibling"] if self.evidence else list(market_input.allowed_evidence_refs),
            "source_refs": ["official_report:sibling"] if self.source else list(market_input.allowed_source_refs),
            "assessment_ref": f"market_context_assessment:{market_input.task_id}",
        }


class UnsupportedPressureBackend:
    def __init__(self, pressure="unsupported_random_value"):
        self.pressure = pressure

    def produce(self, market_input):
        return {
            "request_id": market_input.request_id,
            "task_id": market_input.task_id,
            "symbol": market_input.symbol,
            "as_of": market_input.as_of,
            "market_state": {
                "directional_bias": "balanced",
                "trend_state": "range",
                "momentum_state": "neutral",
                "volatility_regime": "mixed",
                "structure_state": "range",
            },
            "macro_context": {},
            "technical_context": {},
            "dominant_factors": [
                {
                    "factor": "test factor",
                    "category": "market",
                    "directional_pressure": self.pressure,
                    "support_strength": "adequate",
                    "confidence": 0.5,
                    "evidence_refs": list(market_input.allowed_evidence_refs),
                    "source_refs": list(market_input.allowed_source_refs),
                }
            ],
            "conflicting_signals": [],
            "confirmation_conditions": {},
            "invalidation_conditions": [],
            "uncertainty": {"confidence": 0.5, "confidence_ceiling": market_input.confidence_ceiling},
            "summary": "structured context only",
            "evidence_refs": list(market_input.allowed_evidence_refs),
            "source_refs": list(market_input.allowed_source_refs),
            "assessment_ref": f"market_context_assessment:{market_input.task_id}",
        }


class SlowRuntime:
    def execute(self, task, context):
        time.sleep(0.2)
        return MarketContextAgentRuntime().execute(task, context)


class MarketContextAgentTests(unittest.TestCase):
    def test_market_context_input_construction_is_task_scoped(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
            evidence_refs={"task_1": ctx.evidence_bundles[0]},
        )

        market_input = MarketContextInputAssembler.assemble(task(), runtime_context)

        self.assertEqual(market_input.task_id, "task_1:MarketContextAgent")
        self.assertEqual(market_input.symbol, "XAUUSD")
        self.assertEqual(market_input.market_snapshot_ref, "market_snapshot:XAUUSD")
        self.assertEqual(market_input.ohlcv_ref, "ohlcv:XAUUSD")
        self.assertEqual(market_input.technical_snapshot_ref, "technical_snapshot:XAUUSD")
        self.assertIn("economic_event:macro", market_input.economic_event_refs)
        self.assertEqual(market_input.confidence_ceiling, "medium")

    def test_production_backend_emits_canonical_factor_pressure_values_for_balanced_context(self):
        range_results = market_results()
        for item in range_results:
            if item["capability"] == "market_snapshot":
                item["data"]["recent_trend"] = "flat"
                item["data"]["ohlcv_summary"] = {"candles": 12, "first_close": 2400.0, "last_close": 2400.0}
            if item["capability"] == "ohlcv":
                item["data"] = {"candles": 12, "first_close": 2400.0, "last_close": 2400.0}
            if item["capability"] == "technical_snapshot":
                item["data"] = {"trend": "range", "momentum": "neutral", "volatility": "mixed"}
        ctx = decision_context(acquisition_results=range_results)
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in range_results},
        )

        envelope = MarketContextAgentRuntime().execute(
            task(source_refs=[item["result_id"] for item in range_results]),
            runtime_context,
        )

        pressures = {
            factor["directional_pressure"]
            for factor in envelope.structured_payload["dominant_factors"]
        }
        self.assertEqual(envelope.status, AgentStatus.SUCCESS)
        self.assertEqual(envelope.structured_payload["market_state"]["directional_bias"], "balanced")
        self.assertIn("neutral", pressures)
        self.assertTrue(pressures <= PRESSURE_VALUES)

    def test_canonical_factor_pressure_values_pass_validation(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )
        market_input = MarketContextInputAssembler.assemble(task(), runtime_context)
        assessment = MarketContextAssessment(
            request_id=market_input.request_id,
            task_id=market_input.task_id,
            symbol=market_input.symbol,
            as_of=market_input.as_of,
            market_state={
                "directional_bias": "balanced",
                "trend_state": "range",
                "momentum_state": "neutral",
                "volatility_regime": "mixed",
                "structure_state": "range",
            },
            dominant_factors=[
                {
                    "factor": f"{pressure} factor",
                    "category": "market",
                    "directional_pressure": pressure,
                    "support_strength": "adequate",
                    "confidence": 0.5,
                    "evidence_refs": list(market_input.allowed_evidence_refs),
                    "source_refs": list(market_input.allowed_source_refs),
                }
                for pressure in sorted(PRESSURE_VALUES)
            ],
            uncertainty={"confidence": 0.5, "confidence_ceiling": market_input.confidence_ceiling},
            summary="structured context only",
            evidence_refs=list(market_input.allowed_evidence_refs),
            source_refs=list(market_input.allowed_source_refs),
        )

        self.assertEqual(MarketContextAssessmentValidator.validate(assessment, market_input), [])

    def test_unknown_and_malformed_factor_pressure_remain_invalid(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        unsupported = MarketContextAgentRuntime(UnsupportedPressureBackend()).execute(task(), runtime_context)
        malformed = MarketContextAgentRuntime(UnsupportedPressureBackend(pressure=None)).execute(task(), runtime_context)

        self.assertEqual(unsupported.status, AgentStatus.INVALID_RESULT)
        self.assertIn("invalid_factor_pressure", unsupported.failure_reason)
        self.assertEqual(malformed.status, AgentStatus.INVALID_RESULT)
        self.assertIn("invalid_factor_pressure", malformed.failure_reason)

    def test_producer_and_validator_share_canonical_pressure_vocabulary(self):
        self.assertIs(PRESSURE_VALUES, MarketContextVocabulary.FACTOR_PRESSURE)
        self.assertEqual(
            MarketContextVocabulary.factor_pressure_from_directional_bias("balanced"),
            "neutral",
        )
        self.assertEqual(
            MarketContextVocabulary.factor_pressure_from_directional_bias("bullish_pressure"),
            "bullish_pressure",
        )

    def test_serialization_round_trip_preserves_factor_pressure_identity(self):
        assessment = MarketContextAssessment(
            request_id="req",
            task_id="task_1:MarketContextAgent",
            symbol="GENERIC",
            as_of="2026-07-11T00:00:00Z",
            market_state={
                "directional_bias": "balanced",
                "trend_state": "range",
                "momentum_state": "neutral",
                "volatility_regime": "mixed",
                "structure_state": "range",
            },
            dominant_factors=[{"directional_pressure": "neutral", "support_strength": "adequate"}],
            uncertainty={"confidence": 0.5, "confidence_ceiling": "medium"},
        )

        round_trip = MarketContextAssessment(**assessment.as_dict())

        self.assertEqual(round_trip.dominant_factors[0]["directional_pressure"], "neutral")

    def test_valid_production_runtime_result_is_structured(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
            evidence_refs={"task_1": ctx.evidence_bundles[0]},
        )

        envelope = MarketContextAgentRuntime().execute(task(), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.SUCCESS)
        self.assertEqual(envelope.result_type, "market_context_assessment")
        self.assertEqual(envelope.structured_payload["symbol"], "XAUUSD")
        self.assertEqual(envelope.structured_payload["market_state"]["trend_state"], "uptrend")
        self.assertLessEqual(envelope.confidence, 0.65)
        self.assertIn("market_context_assessment:", envelope.structured_payload["assessment_ref"])
        self.assertNotIn("BUY", envelope.summary.upper())

    def test_invalid_semantic_assessment_returns_invalid_envelope_but_outer_structure_valid(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )
        agent_task = task()

        envelope = MarketContextAgentRuntime(UnsupportedPressureBackend()).execute(agent_task, runtime_context)
        outer = AgentResultValidator.validate(agent_task, envelope, known_task_ids=[agent_task.task_id])

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertEqual(outer.status, AgentStatus.INVALID_RESULT)
        self.assertEqual(outer.failure_code, "AGENT_RESULT_INVALID")
        self.assertIn("invalid_factor_pressure", outer.failure_reason)

    def test_invalid_structured_output_confidence_above_ceiling(self):
        ctx = decision_context(confidence_ceiling="medium")
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        envelope = MarketContextAgentRuntime(AboveCeilingBackend()).execute(task(), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("confidence_above_ceiling", envelope.failure_reason)

    def test_out_of_scope_source_ref_is_invalid(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        envelope = MarketContextAgentRuntime(ForeignRefBackend(source=True)).execute(task(), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("source_ref_out_of_scope", envelope.failure_reason)

    def test_out_of_scope_evidence_ref_is_invalid(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        envelope = MarketContextAgentRuntime(ForeignRefBackend(evidence=True)).execute(task(), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("evidence_ref_out_of_scope", envelope.failure_reason)

    def test_execution_instruction_is_invalid(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        envelope = MarketContextAgentRuntime(ForeignRefBackend(execution=True)).execute(task(), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.INVALID_RESULT)
        self.assertIn("trading_instruction_not_allowed", envelope.failure_reason)

    def test_missing_optional_context_is_explicit_limitation(self):
        limited_results = [item for item in market_results() if item["capability"] != "technical_snapshot"]
        ctx = decision_context(acquisition_results=limited_results)
        source_refs = [item["result_id"] for item in limited_results]
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in limited_results},
        )

        envelope = MarketContextAgentRuntime().execute(task(source_refs=source_refs), runtime_context)

        self.assertIn(envelope.status, {AgentStatus.SUCCESS, AgentStatus.PARTIAL})
        self.assertIn("technical snapshot unavailable", envelope.limitations)

    def test_missing_required_input_is_partial_not_fabricated(self):
        ctx = decision_context(acquisition_results=[])
        runtime_context = AgentRuntimeContext(decision_context_ref=ctx, query_plan_ref=ctx.query_plan)

        envelope = MarketContextAgentRuntime().execute(task(source_refs=[]), runtime_context)

        self.assertEqual(envelope.status, AgentStatus.PARTIAL)
        self.assertEqual(envelope.failure_code, "AGENT_PARTIAL")
        self.assertEqual(envelope.evidence_refs, [])

    def test_temporal_metadata_and_conflicting_signals_are_preserved(self):
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )

        envelope = MarketContextAgentRuntime().execute(task(), runtime_context)

        self.assertEqual(envelope.structured_payload["as_of"], "2026-07-11T00:00:00Z")
        self.assertTrue(envelope.structured_payload["conflicting_signals"])

    def test_market_state_and_macro_impact_select_and_register_market_context_agent(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        for intent in ["market_state_analysis", "macro_market_impact"]:
            plan_dict = QueryPlan(
                "q",
                "q",
                task_id="task_1",
                primary_intent=intent,
                entities=QueryEntities(symbols=["XAUUSD"], macro_events=["GENERIC_EVENT"]),
            ).as_dict()
            ctx = decision_context(query_plan=plan_dict)
            contract = OrchestratorContractBuilder().build(
                OrchestratorInput(ctx, available_agents=["MarketContextAgent"])
            )
            plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
            self.assertIn("MarketContextAgent", contract.selected_agents)
            self.assertEqual([item.agent_type for item in plan.tasks], ["MarketContextAgent"])

    def test_unrelated_static_query_excludes_market_context_agent(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        ctx = DecisionContext(
            request_id="static_req",
            user_query="book concept",
            normalized_query="book concept",
            query_intent={},
            answer_mode={"mode": "BOOK_CONCEPT_EXPLANATION"},
            query_plan=QueryPlan("q", "q", task_id="task_1", primary_intent="book_concept_explanation").as_dict(),
            sufficiency={"status": "COMPLETE"},
            static_knowledge_required=True,
        )
        contract = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketContextAgent"])
        )
        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)

        self.assertNotIn("MarketContextAgent", contract.selected_agents)
        self.assertEqual(plan.tasks, [])

    def test_multi_intent_market_context_agent_is_child_scoped(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        parent = QueryPlan(
            "parent",
            "parent",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("market", "market", task_id="task_1", primary_intent="market_state_analysis", entities=QueryEntities(symbols=["XAUUSD"])),
                QueryPlan("book", "book", task_id="task_2", primary_intent="book_concept_explanation"),
            ],
        ).as_dict()
        sibling = result("static_knowledge:book", "static_knowledge", "book", {"title": "Book"}, owner="task_2")
        ctx = decision_context(query_plan=parent, acquisition_results=market_results(owner="task_1") + [sibling])
        contract = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["MarketContextAgent"])
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        market_task = plan.tasks[0]
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": {"task_id": "task_1"}},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )
        market_input = MarketContextInputAssembler.assemble(market_task, runtime_context)

        self.assertEqual(market_task.parent_task_id, "task_1")
        self.assertNotIn("static_knowledge:book", market_task.source_refs)
        self.assertNotIn("static_knowledge:book", market_input.allowed_source_refs)

    def test_multi_intent_macro_child_gets_market_context_handoff_and_static_child_does_not(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        parent = QueryPlan(
            "parent",
            "parent",
            primary_intent="multi_intent",
            child_plans=[
                QueryPlan("macro impact", "macro impact", task_id="task_1", primary_intent="macro_market_impact", entities=QueryEntities(symbols=["XAUUSD"], macro_events=["GENERIC_EVENT"])),
                QueryPlan("book concept", "book concept", task_id="task_2", primary_intent="book_concept_explanation"),
            ],
        ).as_dict()
        sibling = result("static_knowledge:book", "static_knowledge", "book", {"title": "Book"}, owner="task_2")
        ctx = decision_context(
            query_plan=parent,
            acquisition_results=market_results(owner="task_1") + [sibling],
        )
        ctx.task_context_views = [
            {"task_id": "task_1", "sufficiency_status": "COMPLETE", "confidence_ceiling": "medium"},
            {"task_id": "task_2", "sufficiency_status": "COMPLETE", "confidence_ceiling": "high"},
        ]
        ctx.evidence_bundles = [
            {"task_id": "task_1", "items": [{"evidence_id": "market_evidence"}]},
            {"task_id": "task_2", "items": [{"evidence_id": "book_evidence"}]},
        ]
        contract = OrchestratorContractBuilder().build(
            OrchestratorInput(ctx, available_agents=["StaticKnowledgeAgent", "MarketDataAgent", "CalendarAgent"])
        )

        plan = AgentExecutionPlanBuilder(registry).build(contract, ctx)
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={item["task_id"]: item for item in ctx.task_context_views},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
            evidence_refs={item["task_id"]: item for item in ctx.evidence_bundles},
        )
        results = AgentDispatcher(registry).execute(plan, runtime_context)
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", {"handoff": handoff.as_dict()})

        self.assertEqual([item.task_id for item in plan.tasks], ["task_1:MarketContextAgent"])
        self.assertEqual(plan.tasks[0].parent_task_id, "task_1")
        self.assertEqual(plan.tasks[0].intent_family, "macro_market_impact")
        self.assertNotIn("static_knowledge:book", plan.tasks[0].source_refs)
        self.assertEqual(results[0].status, AgentStatus.SUCCESS)
        self.assertEqual(aggregate.status, "PASS")
        self.assertEqual(handoff.market_context_assessments_by_task, {"task_1": "market_context_assessment:task_1:MarketContextAgent"})
        self.assertIn("task_id=task_1", prompt)
        self.assertNotIn("task_id=task_2", prompt)
        self.assertIn("analysis only; not evidence", prompt)
        self.assertNotIn("EvidenceItem", prompt)
        self.assertFalse(plan.execution_allowed)

    def test_dispatch_aggregation_and_handoff_include_assessment_ref(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime())
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )
        agent_task = task()
        plan = type("Plan", (), {
            "request_id": "handoff_req",
            "tasks": [agent_task],
            "parallel_groups": [[agent_task.task_id]],
            "parent_plan_id": "parent",
            "parent_intent": "market_state_analysis",
            "unavailable_agents": [],
        })()

        results = AgentDispatcher(registry).execute(plan, runtime_context)
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)

        self.assertEqual(aggregate.status, "PASS")
        self.assertTrue(handoff.market_context_assessment_refs)
        self.assertIn("market_context_assessment:", handoff.market_context_assessment_refs[0])
        self.assertNotIn("EvidenceItem", str(handoff.as_dict()))

    def test_invalid_assessment_does_not_enter_handoff_or_prompt_enrichment(self):
        registry = AgentRuntimeRegistry()
        registry.register("MarketContextAgent", MarketContextAgentRuntime(UnsupportedPressureBackend()))
        ctx = decision_context()
        runtime_context = AgentRuntimeContext(
            decision_context_ref=ctx,
            query_plan_ref=ctx.query_plan,
            task_context_refs={"task_1": ctx.task_context_views[0]},
            acquisition_result_refs={item["result_id"]: item for item in ctx.acquisition_results},
        )
        agent_task = task()
        plan = type("Plan", (), {
            "request_id": "invalid_handoff_req",
            "tasks": [agent_task],
            "parallel_groups": [[agent_task.task_id]],
            "parent_plan_id": "parent",
            "parent_intent": "market_state_analysis",
            "unavailable_agents": [],
        })()

        results = AgentDispatcher(registry).execute(plan, runtime_context)
        aggregate = AgentResultAggregator.aggregate(plan, results)
        handoff = build_agent_handoff(plan, aggregate)
        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", {"handoff": handoff.as_dict()})

        self.assertEqual(results[0].status, AgentStatus.INVALID_RESULT)
        self.assertEqual(handoff.market_context_assessment_refs, [])
        self.assertEqual(prompt, "BASE")

    def test_timeout_and_unavailable_runtime_behavior(self):
        slow_registry = AgentRuntimeRegistry()
        slow_registry.register("MarketContextAgent", SlowRuntime())
        agent_task = task(timeout_ms=1)
        plan = type("Plan", (), {
            "request_id": "timeout_req",
            "tasks": [agent_task],
            "parallel_groups": [[agent_task.task_id]],
            "parent_plan_id": "parent",
            "parent_intent": "market_state_analysis",
            "unavailable_agents": [],
        })()
        result = AgentDispatcher(slow_registry).execute(plan, AgentRuntimeContext(decision_context_ref=decision_context()))[0]
        self.assertEqual(result.status, AgentStatus.TIMEOUT)

        ctx = decision_context()
        contract = OrchestratorContractBuilder().build(OrchestratorInput(ctx, available_agents=["MarketContextAgent"]))
        unavailable_plan = AgentExecutionPlanBuilder(AgentRuntimeRegistry()).build(contract, ctx)
        self.assertEqual(unavailable_plan.tasks, [])
        self.assertEqual(unavailable_plan.unavailable_agents, ["MarketContextAgent"])

    def test_downstream_enrichment_boundary_appends_compact_non_evidence_block(self):
        payload = {
            "handoff": {
                "agent_results": [
                    {
                        "agent_type": "MarketContextAgent",
                        "status": "SUCCESS",
                        "parent_task_id": "task_1",
                        "structured_payload": {
                            "assessment_ref": "market_context_assessment:task_1",
                            "symbol": "XAUUSD",
                            "as_of": "2026-07-11T00:00:00Z",
                            "market_state": {"directional_bias": "balanced"},
                            "dominant_factors": [{"factor": "recent price behavior"}],
                            "conflicting_signals": [],
                            "uncertainty": {"confidence": 0.6, "missing_context": [], "limitations": []},
                        },
                        "source_refs": ["market_snapshot:XAUUSD"],
                        "evidence_refs": ["evidence_bundle:task_1"],
                    }
                ]
            }
        }

        prompt = RAGOrchestrator._append_agent_handoff_to_prompt("BASE", payload)

        self.assertIn("AGENT HANDOFF CONTEXT", prompt)
        self.assertIn("not evidence", prompt)
        self.assertIn("Factual claims still require", prompt)
        self.assertNotIn("EvidenceItem", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
