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
from src.orchestrator import RAGOrchestrator  # noqa: E402
from src.services.evidence.answer_coverage import AnswerCoverageValidationResult  # noqa: E402
from src.services.evidence.evidence_pipeline import AnswerContract, AnswerContractEvaluator, ClaimValidationResult  # noqa: E402
from src.services.semantic.context_execution import ContextExecutionPlanner  # noqa: E402
from src.services.semantic.context_requirements import ContextRequirementPlanner  # noqa: E402
from src.services.semantic.query_plan import QueryEntities, QueryPlan  # noqa: E402


class MultiIntentEvidenceIsolationTests(unittest.TestCase):
    def test_book_and_macro_tasks_get_separate_evidence_bundles(self):
        book_plan = query_plan(
            task_id="task_1",
            authors=["Al Brooks"],
            books=["Reading Price Charts Bar by Bar"],
            concepts=["price_action"],
        )
        macro_plan = query_plan(
            primary_intent="macro_market_impact",
            task_id="task_2",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            macro_events=["CPI"],
            organizations=["BLS"],
            symbols=["XAUUSD"],
        )
        shared_results = [
            knowledge_result(task_ids=["task_1"]),
            cpi_report_result(task_ids=["task_2"]),
            event_result(task_ids=["task_2"]),
            market_result(task_ids=["task_2"]),
        ]
        selector = EvidenceSelector()

        book_bundle = selector.select(book_plan, task_view(book_plan), shared_results, "static_explanation", "task_1")
        macro_bundle = selector.select(macro_plan, task_view(macro_plan), shared_results, "scenario_analysis", "task_2")

        self.assertEqual(book_bundle.sufficiency.status, "COMPLETE")
        self.assertEqual(macro_bundle.sufficiency.status, "COMPLETE")
        self.assertTrue(all(item.capability == "static_knowledge" for item in book_bundle.all_items))
        self.assertFalse(any(item.source_organization == "BLS" for item in book_bundle.all_items))
        self.assertFalse(any(item.source_author == "Al Brooks" for item in macro_bundle.all_items))
        self.assertTrue(any(item.evidence_type == "economic_event_record" for item in macro_bundle.event_evidence))

    def test_macro_and_market_tasks_share_acquisition_without_evidence_leakage(self):
        macro_plan = query_plan(
            primary_intent="macro_market_impact",
            task_id="task_1",
            query="CPI moi nhat anh huong XAUUSD the nao?",
            macro_events=["CPI"],
            organizations=["BLS"],
            symbols=["XAUUSD"],
        )
        market_plan = query_plan(
            primary_intent="market_state_analysis",
            task_id="task_2",
            query="XAUUSD hien tai dang chiu tac dong boi yeu to nao?",
            symbols=["XAUUSD"],
        )
        shared_market = market_result(task_ids=["task_1", "task_2"])
        results = [cpi_report_result(task_ids=["task_1"]), event_result(task_ids=["task_1"]), shared_market]
        selector = EvidenceSelector()

        macro_bundle = selector.select(macro_plan, task_view(macro_plan), results, "scenario_analysis", "task_1")
        market_bundle = selector.select(market_plan, task_view(market_plan), results, "market_analysis", "task_2")

        self.assertTrue(macro_bundle.current_market_evidence)
        self.assertTrue(market_bundle.current_market_evidence)
        self.assertFalse(market_bundle.event_evidence)
        self.assertFalse(market_bundle.primary_evidence)

    def _heterogeneous_parent_plan(self):
        macro = QueryPlan(
            original_query="Macro event affects asset how?",
            normalized_query="macro event affects asset how",
            task_id="task_1",
            primary_intent="macro_market_impact",
            entities=QueryEntities(symbols=["XAUUSD"], macro_events=["CPI"], organizations=["BLS"]),
            temporal_scope="latest",
            user_action_intent="analysis",
        )
        book = QueryPlan(
            original_query="Author explains concept how?",
            normalized_query="author explains concept how",
            task_id="task_2",
            primary_intent="book_concept_explanation",
            entities=QueryEntities(authors=["Al Brooks"], books=["Reading Price Charts Bar by Bar"], concepts=["price_action"]),
            temporal_scope="timeless",
            user_action_intent="explanation",
        )
        return QueryPlan(
            original_query="Macro event affects asset how?\nAuthor explains concept how?",
            normalized_query="macro and book",
            task_id="parent",
            primary_intent="multi_intent",
            child_plans=[macro, book],
            requires_execution=False,
        )

    def test_child_refinement_scope_excludes_sibling_capabilities(self):
        parent = self._heterogeneous_parent_plan()
        requirements = ContextRequirementPlanner().plan(parent)
        execution_plan = ContextExecutionPlanner().plan(requirements)

        task_1_requirements = RAGOrchestrator._requirements_for_task(requirements, "task_1")
        task_1_plan, task_1_scope = RAGOrchestrator._refinement_plan_for_task(
            execution_plan,
            task_1_requirements,
            "task_1",
        )
        self.assertIn("official_report:CPI", task_1_scope["scheduled_capabilities"])
        self.assertIn("market_knowledge:gold", task_1_scope["scheduled_capabilities"])
        self.assertNotIn("static_knowledge:price_action", task_1_scope["scheduled_capabilities"])
        self.assertIn("static_knowledge:price_action", task_1_scope["rejected_sibling_capabilities"])
        self.assertTrue(all(task.capability != "static_knowledge" for task in task_1_plan.parallel_tasks + task_1_plan.dependent_tasks))

        task_2_requirements = RAGOrchestrator._requirements_for_task(requirements, "task_2")
        task_2_plan, task_2_scope = RAGOrchestrator._refinement_plan_for_task(
            execution_plan,
            task_2_requirements,
            "task_2",
        )
        self.assertEqual(task_2_scope["scheduled_capabilities"], ["static_knowledge:price_action"])
        self.assertIn("official_report:CPI", task_2_scope["rejected_sibling_capabilities"])
        self.assertIn("market_knowledge:gold", task_2_scope["rejected_sibling_capabilities"])
        self.assertTrue(all(task.capability == "static_knowledge" for task in task_2_plan.parallel_tasks + task_2_plan.dependent_tasks))

    def test_child_query_plan_and_results_are_task_scoped(self):
        parent = self._heterogeneous_parent_plan()
        task_1_plan = RAGOrchestrator._query_plan_for_task(parent, "task_1")
        task_2_plan = RAGOrchestrator._query_plan_for_task(parent, "task_2")
        self.assertEqual(task_1_plan.primary_intent, "macro_market_impact")
        self.assertEqual(task_2_plan.primary_intent, "book_concept_explanation")

        results = [
            cpi_report_result(task_ids=["task_1"]),
            event_result(task_ids=["task_1"]),
            market_result(task_ids=["task_1"]),
            knowledge_result(task_ids=["task_2"]),
        ]
        task_1_results = RAGOrchestrator._results_for_task(results, "task_1")
        task_2_results = RAGOrchestrator._results_for_task(results, "task_2")
        self.assertFalse(any(result.capability == "static_knowledge" for result in task_1_results))
        self.assertTrue(all(result.capability == "static_knowledge" for result in task_2_results))

    def test_single_intent_report_result_routes_to_task_evidence_and_refinement_merge(self):
        plan = QueryPlan(
            original_query="Summarize the macro report.",
            normalized_query="summarize the macro report",
            task_id="task_1",
            primary_intent="macro_report_summary",
            entities=QueryEntities(macro_events=["CPI"], organizations=["BLS"]),
            temporal_scope="latest",
            user_action_intent="explanation",
        )
        requirements = ContextRequirementPlanner().plan(plan)
        execution_plan = ContextExecutionPlanner().plan(requirements)
        scoped_requirements = RAGOrchestrator._requirements_for_task(requirements, "task_1")
        scoped_plan, scope = RAGOrchestrator._refinement_plan_for_task(
            execution_plan,
            scoped_requirements,
            "task_1",
        )

        self.assertEqual(requirements.task_id, "task_1")
        self.assertEqual(scope["scheduled_capabilities"], ["official_report:CPI"])
        self.assertEqual(scope["rejected_sibling_capabilities"], [])
        self.assertEqual([task.task_id() for task in scoped_plan.parallel_tasks], ["official_report:CPI"])

        result = cpi_report_result(task_ids=["task_1"])
        foreign = knowledge_result(task_ids=["task_2"])
        task_results = RAGOrchestrator._results_for_task([result, foreign], "task_1")
        self.assertEqual([RAGOrchestrator._result_id(item) for item in task_results], ["official_report:CPI"])

        selector = EvidenceSelector()
        bundle = selector.select(plan, task_view(plan.as_dict()), task_results, "report_summary", "task_1")
        self.assertTrue(bundle.all_items)
        self.assertEqual(bundle.sufficiency.status, "COMPLETE")
        self.assertTrue(any(item.capability == "official_report" for item in bundle.all_items))

    def test_contract_evaluation_keeps_task_identity_and_parent_aggregation(self):
        contract_1 = AnswerContract(task_id="task_1", answer_type="scenario_analysis")
        contract_2 = AnswerContract(task_id="task_2", answer_type="static_explanation")
        coverage = AnswerCoverageValidationResult(status="PASS", coverage_ratio=1.0)
        claim = ClaimValidationResult(status="PASS")

        eval_1 = AnswerContractEvaluator.evaluate(contract_1, coverage, claim, task_id="task_1").as_dict()
        eval_2 = AnswerContractEvaluator.evaluate(contract_2, coverage, claim, task_id="task_2").as_dict()

        self.assertEqual(eval_1["task_id"], "task_1")
        self.assertEqual(eval_2["task_id"], "task_2")
        self.assertEqual(RAGOrchestrator._aggregate_contract_status([eval_1, eval_2]), "PASS")
        eval_2["status"] = "WARN"
        self.assertEqual(RAGOrchestrator._aggregate_contract_status([eval_1, eval_2]), "WARN")


if __name__ == "__main__":
    unittest.main()
