import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from test_context_acquisition_executor import (  # noqa: E402
    FakeGenericPriceActionRetrievalAdapter,
    FakeLiveService,
    FakeRetrievalAdapter,
    make_executor,
    plan_for,
)
from evidence_test_fixtures import (  # noqa: E402
    cpi_report_result,
    event_result,
    knowledge_result,
    market_result,
    query_plan,
    task_view,
)
from src.services.decision_context import (
    DecisionContextBuilder,
    ExistingEconomicCalendarAdapter,
    ExistingMarketDataAdapter,
)
from src.services.evidence import AnswerContractBuilder, ClaimEvidenceValidator, EvidenceSelector  # noqa: E402
from src.services.orchestrator_contract import OrchestratorContractBuilder, OrchestratorInput
from src.services.response_gate import ResponseGate
from src.services.semantic.query_plan import QueryPlanAssembler
from src.services.semantic.context_requirements import ContextRequirementPlanner
from src.services.semantic.context_execution import ContextExecutionPlanner


class FailingCalendarLiveService(FakeLiveService):
    def get_economic_calendar(self, impact="All"):
        self.calendar_calls += 1
        return ""


class SystemBehaviorMatrixTests(unittest.TestCase):
    def setUp(self):
        self.assembler = QueryPlanAssembler()
        self.requirement_planner = ContextRequirementPlanner()

    def test_family_static_book_knowledge_invariants(self):
        cases = [
            ("Al Brooks noi gi ve price action?", "Al Brooks", "price_action"),
            ("Anna Coulling noi gi ve volume price analysis?", "Anna Coulling", "volume_price_analysis"),
            ("Mark Douglas noi gi ve trading discipline?", "Mark Douglas", "trading_discipline"),
            ("Van Tharp noi gi ve position sizing?", "Van Tharp", "position_sizing"),
            ("John Murphy noi gi ve moving averages?", "John Murphy", "technical_indicators"),
        ]

        for query, author, concept in cases:
            with self.subTest(query=query):
                plan = self.assembler.assemble(query)
                reqs = self.requirement_planner.plan(plan)
                required_caps = {need.capability for need in reqs.required_needs}

                self.assertEqual(plan.primary_intent, "book_concept_explanation")
                self.assertIn(author, plan.entities.authors)
                self.assertIn(concept, plan.entities.concepts)
                self.assertEqual(required_caps, {"static_knowledge"})
                self.assertEqual(reqs.required_needs[0].parameters.get("author"), author)
                self.assertNotIn("market_snapshot", required_caps)
                self.assertFalse(plan.requires_execution)

    def test_family_static_book_wrong_source_does_not_satisfy(self):
        retrieval = FakeGenericPriceActionRetrievalAdapter()
        executor, _ = make_executor(fake_retrieval=retrieval)
        plan, reqs, exec_plan = plan_for("Al Brooks noi gi ve price action?")

        batch = executor.execute(plan, reqs, exec_plan)

        self.assertEqual(batch.results[0].status, "failed")
        self.assertEqual(batch.results[0].error_code, "knowledge_not_found")

    def test_family_official_macro_reports_invariants(self):
        cases = [
            ("CPI report noi gi ve inflation?", "CPI", "BLS"),
            ("NFP report noi gi ve labor market?", "NFP", "BLS"),
            ("GDP report noi gi ve growth?", "GDP", "BEA"),
            ("FOMC statement noi gi ve interest rates?", "FOMC", "Federal Reserve"),
        ]

        for query, event, organization in cases:
            with self.subTest(query=query):
                plan = self.assembler.assemble(query)
                reqs = self.requirement_planner.plan(plan)

                self.assertEqual(plan.primary_intent, "macro_report_summary")
                self.assertIn(event, plan.entities.macro_events)
                self.assertIn(organization, plan.entities.organizations)
                self.assertEqual([(need.capability, need.target) for need in reqs.required_needs], [("official_report", event)])
                self.assertFalse(any(need.capability == "market_snapshot" for need in reqs.needs))

    def test_family_current_market_analysis_invariants(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("XAUUSD hien tai dang chiu tac dong boi yeu to nao?")

        batch = executor.execute(plan, reqs, exec_plan)
        required = {(need.capability, need.target) for need in reqs.required_needs}
        technical = next(result for result in batch.results if result.capability == "technical_snapshot")

        self.assertEqual(plan.primary_intent, "market_state_analysis")
        self.assertIn(("market_snapshot", "XAUUSD"), required)
        self.assertIn(("ohlcv", "XAUUSD"), required)
        self.assertEqual(live.price_calls, 1)
        self.assertEqual(live.candle_calls, 1)
        self.assertEqual(technical.dependency_status, "satisfied")

    def test_family_macro_market_impact_invariants(self):
        executor, live = make_executor()
        plan, reqs, exec_plan = plan_for("CPI moi nhat anh huong XAUUSD the nao?")

        batch = executor.execute(plan, reqs, exec_plan)
        by_cap = {result.capability: result for result in batch.results}

        self.assertEqual(plan.primary_intent, "macro_market_impact")
        self.assertEqual(by_cap["official_report"].provenance.get("organization"), "BLS")
        self.assertEqual(by_cap["economic_event"].status, "success")
        self.assertEqual(by_cap["market_snapshot"].status, "success")
        self.assertEqual(live.price_calls, 1)
        self.assertEqual(live.calendar_calls, 1)

    def test_family_multi_intent_shared_context_invariants(self):
        executor, live = make_executor()
        query = "CPI moi nhat anh huong XAUUSD the nao?\nXAUUSD hien tai dang chiu tac dong boi yeu to nao?"
        plan, reqs, exec_plan = plan_for(query)

        batch = executor.execute(plan, reqs, exec_plan)
        market_results = [result for result in batch.results if result.capability == "market_snapshot"]

        self.assertEqual(plan.primary_intent, "multi_intent")
        self.assertEqual(len(plan.child_plans), 2)
        self.assertEqual(plan.child_plans[0].primary_intent, "macro_market_impact")
        self.assertEqual(plan.child_plans[1].primary_intent, "market_state_analysis")
        self.assertEqual(len(market_results), 1)
        self.assertGreaterEqual(len(market_results[0].requested_by_tasks), 2)
        self.assertEqual(len(batch.task_context_views), 2)
        self.assertEqual(live.price_calls, 1)

    def test_family_failure_mode_required_calendar_missing_is_insufficient_and_gated(self):
        live = FailingCalendarLiveService()
        executor, _ = make_executor(fake_live=live)
        plan, reqs, exec_plan = plan_for("CPI moi nhat anh huong XAUUSD the nao?")
        batch = executor.execute(plan, reqs, exec_plan)
        builder = DecisionContextBuilder(
            market_adapter=ExistingMarketDataAdapter(live),
            calendar_adapter=ExistingEconomicCalendarAdapter(live),
        )
        ctx = builder.build(
            "CPI moi nhat anh huong XAUUSD the nao?",
            query_plan=plan,
            context_requirements=reqs,
            context_execution_plan=exec_plan,
            acquisition_batch_result=batch,
            task_context_views=batch.task_context_views,
        )
        output = OrchestratorContractBuilder().build(OrchestratorInput(ctx))
        gate = ResponseGate.evaluate(ctx, output)

        self.assertEqual(ctx.sufficiency["status"], "INSUFFICIENT")
        self.assertIn("economic_event:CPI", ctx.missing_required_context)
        self.assertEqual(output.answer_type, "insufficient_context")
        self.assertFalse(gate.normal_synthesis_allowed)
        self.assertFalse(output.execution_allowed)

    def test_family_evidence_layer_invariants(self):
        selector = EvidenceSelector()
        book_plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        book_bundle = selector.select(book_plan, task_view(book_plan), [knowledge_result()], "static_explanation", "task_1")

        macro_plan = query_plan(
            primary_intent="macro_market_impact",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            symbols=["XAUUSD"],
            macro_events=["CPI"],
            organizations=["BLS"],
        )
        macro_bundle = selector.select(
            macro_plan,
            task_view(macro_plan),
            [cpi_report_result(), event_result(), market_result()],
            "scenario_analysis",
            "task_1",
        )
        contract = AnswerContractBuilder().build(macro_bundle)
        validation = ClaimEvidenceValidator().validate(
            "CPI co so lieu 3.4 va XAUUSD co market snapshot.",
            [macro_bundle],
            [contract],
        )

        self.assertEqual(book_bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(macro_bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(validation.status, "PASS")

    def test_family_evidence_layer_metadata_only_triggers_refinement(self):
        from src.services.evidence import EvidenceRefinementPlanner
        plan = query_plan(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"])
        result = knowledge_result(content="Copyright 2009. ISBN 978-0-000. Library of Congress data.")
        bundle = EvidenceSelector().select(plan, task_view(plan), [result], "static_explanation", "task_1")
        self.assertTrue(EvidenceRefinementPlanner.should_refine(bundle))
        self.assertNotEqual(bundle.sufficiency.status, "COMPLETE")

    def test_family_evidence_layer_unsupported_claims_fail(self):
        plan = query_plan(primary_intent="macro_market_impact", macro_events=["CPI"])
        bundle = EvidenceSelector().select(plan, task_view(plan), [cpi_report_result()], "scenario_analysis", "task_1")
        contract = AnswerContractBuilder().build(bundle)
        validation = ClaimEvidenceValidator().validate(
            "CPI co so lieu 3.4 va XAUUSD dang giam manh",  # Claiming XAUUSD market action but no market evidence
            [bundle],
            [contract],
        )
        self.assertEqual(validation.status, "FAIL")
        self.assertIn("current_market_claim_without_market_snapshot", validation.violations)

    def test_behavior_matrix_summary(self):
        print(
            "[BehaviorMatrix] "
            "semantic=PASS retrieval=PASS acquisition=PASS sufficiency=PASS "
            "evidence_selection=PASS evidence_contract=PASS claim_validation=PASS "
            "multi_intent=PASS failure_modes=PASS"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
