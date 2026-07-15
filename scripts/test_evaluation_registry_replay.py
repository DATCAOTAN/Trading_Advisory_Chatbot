import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_backtest_evaluation import (  # noqa: E402
    BacktestEvaluationAgent,
    BacktestEvaluationInputBuilder,
    journal_record,
    window,
)
from scripts.test_paper_trading_evaluation import point  # noqa: E402
from src.services.agents.evaluation_registry import (  # noqa: E402
    EvaluationRegistry,
    EvaluationRegistryEntry,
    EvaluationReplayCase,
    EvaluationReplayHarness,
    register_evaluation_record,
)
from src.services.agents.paper_trading_evaluation import (  # noqa: E402
    PaperTradingEvaluationAgent,
    PaperTradingEvaluationInputBuilder,
)


def records(multi=False):
    journal = journal_record(multi=multi)
    backtest = BacktestEvaluationAgent.evaluate(
        BacktestEvaluationInputBuilder.build(journal, [window("up", "task_1")])
    ).as_dict()
    paper = PaperTradingEvaluationAgent.evaluate(
        PaperTradingEvaluationInputBuilder.build(journal, backtest, [point("obs1", "task_1")])
    ).as_dict()
    return journal, backtest, paper


class EvaluationRegistryReplayTests(unittest.TestCase):
    def test_registry_entry_schema_and_register_all_record_types(self):
        journal, backtest, paper = records()
        registry = EvaluationRegistry()
        journal_entry = registry.register(journal, "journal_review")
        backtest_entry = registry.register(backtest, "backtest_evaluation")
        paper_entry = registry.register(paper, "paper_trading_evaluation")

        self.assertIsInstance(journal_entry, EvaluationRegistryEntry)
        self.assertEqual(len(registry.list_registry_entries()), 3)
        self.assertEqual(journal_entry.final_answer_sha256, "abc123")
        self.assertEqual(backtest_entry.final_answer_sha256, "abc123")
        self.assertEqual(paper_entry.final_answer_sha256, "abc123")
        self.assertEqual(journal_entry.request_id, "bt_req")
        self.assertIn("task_1", paper_entry.task_ids)
        self.assertEqual(paper_entry.safety_index["execution_allowed"], False)

    def test_registry_preserves_task_scope_source_refs_and_static_isolation(self):
        journal, backtest, paper = records(multi=True)
        registry = EvaluationRegistry()
        journal_entry = registry.register(journal, "journal_review")
        paper_entry = registry.register(paper, "paper_trading_evaluation")

        journal_task_1 = next(task for task in journal_entry.task_index if task.task_id == "task_1")
        journal_task_2 = next(task for task in journal_entry.task_index if task.task_id == "task_2")
        task_1 = next(task for task in paper_entry.task_index if task.task_id == "task_1")
        task_2 = next(task for task in paper_entry.task_index if task.task_id == "task_2")

        self.assertIn("market_snapshot:XAUUSD", journal_task_1.source_refs)
        self.assertIn("Reading Price Charts Bar by Bar - Al Brooks", journal_task_2.source_refs)
        self.assertNotIn("market_snapshot:XAUUSD", journal_task_2.source_refs)
        self.assertEqual(task_1.symbol, "XAUUSD")
        self.assertEqual(task_2.intent_family, "book_concept_explanation")
        self.assertEqual(task_2.symbol, "")
        self.assertNotIn("XAUUSD", json.dumps(task_2.as_dict()))

    def test_registry_filters_and_needs_review(self):
        journal, backtest, paper = records()
        degraded = copy.deepcopy(journal)
        degraded["quality_label"] = "failed_validation"
        degraded["status"] = "DEGRADED"
        degraded["review_outcome"] = "needs_human_review"
        registry = EvaluationRegistry()
        registry.register(journal, "journal_review")
        registry.register(backtest, "backtest_evaluation")
        registry.register(paper, "paper_trading_evaluation")
        registry.register(degraded, "journal_review")

        self.assertEqual(len(registry.find_by_request_id("bt_req")), 4)
        self.assertEqual(len(registry.find_by_final_answer_hash("abc123")), 4)
        self.assertGreaterEqual(len(registry.filter_by_symbol("XAUUSD")), 2)
        self.assertEqual(len(registry.filter_by_quality_label("useful_for_review")), 2)
        self.assertEqual(len(registry.filter_by_status("EVALUATED")), 2)
        self.assertTrue(any(entry.review_outcome == "needs_human_review" for entry in registry.filter_needs_review()))

    def test_runtime_artifact_storage_and_source_records_not_mutated(self):
        journal, backtest, paper = records()
        before_journal = copy.deepcopy(journal)
        before_backtest = copy.deepcopy(backtest)
        before_paper = copy.deepcopy(paper)
        artifacts = {"journal_review": journal, "backtest_evaluation": backtest, "paper_trading_evaluation": paper, "evidence_bundles": [{"task_id": "task_1"}]}

        register_evaluation_record(journal, "journal_review", artifacts)
        register_evaluation_record(backtest, "backtest_evaluation", artifacts)
        register_evaluation_record(paper, "paper_trading_evaluation", artifacts)

        self.assertEqual(journal, before_journal)
        self.assertEqual(backtest, before_backtest)
        self.assertEqual(paper, before_paper)
        self.assertEqual(artifacts["evidence_bundles"], [{"task_id": "task_1"}])
        self.assertIn("evaluation_registry", artifacts)
        self.assertEqual(len(artifacts["evaluation_registry"]["entries"]), 3)
        self.assertNotIn("EvidenceItem", str(artifacts["evaluation_registry"]))

    def test_review_dataset_export_is_safe_and_filtered(self):
        journal, backtest, paper = records()
        journal["limitations"] = ["API_KEY=secret-value should be redacted"]
        registry = EvaluationRegistry()
        registry.register(journal, "journal_review")
        registry.register(backtest, "backtest_evaluation")
        registry.register(paper, "paper_trading_evaluation")

        dataset = registry.export_review_dataset({"request_id": "bt_req"})
        blob = json.dumps(dataset.as_dict(), ensure_ascii=False)

        self.assertEqual(dataset.entries_count, 3)
        self.assertGreaterEqual(len(dataset.rows), 3)
        self.assertNotIn("secret-value", blob)
        self.assertNotIn("full_prompt", blob)
        self.assertNotIn("account_balance", blob)
        self.assertNotIn("mt5_password", blob)

    def test_redaction_and_unsafe_source_record_safety_flags(self):
        journal, _, _ = records()
        unsafe = copy.deepcopy(journal)
        unsafe["limitations"] = ["sk-testsecret123456789", "buy now with entry 2400 and MT5 order"]
        registry = EvaluationRegistry()
        entry = registry.register(unsafe, "journal_review")

        self.assertGreater(entry.redactions, 0)
        self.assertTrue(entry.safety_index["prohibited_outputs_detected"])
        self.assertIn("source_record_safety_flag", entry.limitations)

    def test_replay_journal_backtest_paper_and_full_chain_pass(self):
        journal, backtest, _ = records()
        journal_case = EvaluationReplayCase(
            replay_id="replay:journal",
            case_type="journal_only",
            input_records={"journal_review_record": journal},
            expected_outputs={"entries_count": 1},
        )
        backtest_case = EvaluationReplayCase(
            replay_id="replay:backtest",
            case_type="backtest",
            input_records={"journal_review_record": journal},
            supplied_fixtures={"historical_observation_windows": [window("up", "task_1")]},
            expected_outputs={"expected_status": "EVALUATED", "expected_quality_label": "useful_for_review", "expected_task_outcomes": ["aligned"]},
        )
        paper_case = EvaluationReplayCase(
            replay_id="replay:paper",
            case_type="paper_trading",
            input_records={"journal_review_record": journal, "backtest_evaluation_record": backtest},
            supplied_fixtures={"simulated_observation_timeline": [point("obs1", "task_1")]},
            expected_outputs={"expected_status": "EVALUATED", "expected_quality_label": "useful_for_review", "expected_task_outcomes": ["thesis_remained_valid"]},
        )
        full_case = EvaluationReplayCase(
            replay_id="replay:full",
            case_type="full_chain",
            input_records={"journal_review_record": journal},
            supplied_fixtures={
                "historical_observation_windows": [window("up", "task_1")],
                "simulated_observation_timeline": [point("obs1", "task_1")],
            },
            expected_outputs={"entries_count": 3},
        )

        for case in (journal_case, backtest_case, paper_case, full_case):
            result = EvaluationReplayHarness.replay(case)
            self.assertEqual(result.status, "PASS")
            self.assertEqual(result.safety_summary["no_provider_calls"], True)
            self.assertEqual(result.safety_summary["no_retrieval"], True)
            self.assertEqual(result.safety_summary["no_execution"], True)
            self.assertEqual(result.safety_summary["execution_allowed"], False)

    def test_replay_detects_mismatch(self):
        journal, _, _ = records()
        case = EvaluationReplayCase(
            replay_id="replay:mismatch",
            case_type="backtest",
            input_records={"journal_review_record": journal},
            supplied_fixtures={"historical_observation_windows": [window("up", "task_1")]},
            expected_outputs={"expected_status": "SKIPPED"},
        )

        result = EvaluationReplayHarness.replay(case)

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.mismatches[0]["field"], "expected_status")


if __name__ == "__main__":
    unittest.main(verbosity=2)
