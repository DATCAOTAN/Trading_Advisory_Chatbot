import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_evaluation_registry_replay import records  # noqa: E402
from scripts.test_backtest_evaluation import window  # noqa: E402
from scripts.test_paper_trading_evaluation import point  # noqa: E402
from src.services.agents.evaluation_dashboard import (  # noqa: E402
    EvaluationDashboardFilters,
    EvaluationDashboardService,
    replay_view_from_result,
    review_priority,
)
from src.services.agents.evaluation_registry import (  # noqa: E402
    EvaluationRegistry,
    EvaluationReplayCase,
    EvaluationReplayHarness,
)


def dashboard_service(multi=False):
    journal, backtest, paper = records(multi=multi)
    registry = EvaluationRegistry()
    registry.register(journal, "journal_review")
    registry.register(backtest, "backtest_evaluation")
    registry.register(paper, "paper_trading_evaluation")
    return EvaluationDashboardService(registry), journal, backtest, paper


class EvaluationDashboardTests(unittest.TestCase):
    def test_dashboard_summary_from_empty_registry(self):
        service = EvaluationDashboardService(EvaluationRegistry())

        summary, rows = service.load()

        self.assertEqual(summary.total_entries, 0)
        self.assertEqual(rows, [])
        self.assertFalse(summary.execution_allowed)

    def test_dashboard_summary_rows_and_filters(self):
        service, _, _, _ = dashboard_service()

        summary, rows = service.load()
        self.assertEqual(summary.total_entries, 3)
        self.assertEqual(summary.by_record_type["journal_review"], 1)
        self.assertIn("XAUUSD", summary.symbols)
        self.assertFalse(summary.execution_allowed)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.final_answer_sha256 == "abc123" for row in rows))

        self.assertEqual(len(service.load(EvaluationDashboardFilters(request_id="bt_req"))[1]), 3)
        self.assertEqual(len(service.load(EvaluationDashboardFilters(record_type="journal_review"))[1]), 1)
        self.assertGreaterEqual(len(service.load(EvaluationDashboardFilters(symbol="XAUUSD"))[1]), 2)
        self.assertEqual(len(service.load(EvaluationDashboardFilters(status="EVALUATED"))[1]), 2)
        self.assertEqual(len(service.load(EvaluationDashboardFilters(quality_label="useful_for_review"))[1]), 2)

    def test_needs_review_and_priority_filters(self):
        journal, _, _ = records()
        degraded = copy.deepcopy(journal)
        degraded["status"] = "DEGRADED"
        degraded["quality_label"] = "unsafe_or_noncompliant"
        degraded["review_outcome"] = "needs_human_review"
        registry = EvaluationRegistry()
        entry = registry.register(degraded, "journal_review")
        service = EvaluationDashboardService(registry)

        self.assertEqual(review_priority(entry), "HIGH")
        self.assertEqual(len(service.load(EvaluationDashboardFilters(needs_review_only=True))[1]), 1)
        self.assertEqual(len(service.load(EvaluationDashboardFilters(review_priority="HIGH"))[1]), 1)

    def test_row_excludes_raw_prompt_and_full_answer(self):
        service, _, _, _ = dashboard_service()

        _, rows = service.load()
        blob = json.dumps([row.as_dict() for row in rows], ensure_ascii=False)

        self.assertNotIn("full_prompt", blob)
        self.assertNotIn("raw_prompt", blob)
        self.assertNotIn("final_answer_text", blob)

    def test_detail_includes_task_source_safety_evaluation_and_links(self):
        service, _, _, _ = dashboard_service()
        _, rows = service.load()

        detail = service.detail(rows[0].registry_id)

        self.assertIsNotNone(detail)
        self.assertTrue(detail.task_index)
        self.assertIsInstance(detail.safety_index, dict)
        self.assertIsInstance(detail.evaluation_index, dict)
        self.assertIn("abc123", detail.hashes.get("final_answer_sha256", ""))
        self.assertGreaterEqual(len(detail.linked_records), 3)

    def test_chain_view_groups_journal_backtest_paper(self):
        service, _, _, _ = dashboard_service()

        chains = service.chain_view(request_id="bt_req")

        self.assertEqual(len(chains), 1)
        chain = chains[0]
        self.assertTrue(chain.chain_completeness["has_journal"])
        self.assertTrue(chain.chain_completeness["has_backtest"])
        self.assertTrue(chain.chain_completeness["has_paper"])
        self.assertEqual(chain.task_chain[0]["task_id"], "task_1")

    def test_chain_view_handles_missing_backtest_paper_for_static_task(self):
        journal, _, _ = records(multi=True)
        registry = EvaluationRegistry()
        registry.register(journal, "journal_review")
        service = EvaluationDashboardService(registry)

        chains = service.chain_view(request_id="bt_req")
        task_2 = next(task for task in chains[0].task_chain if task["task_id"] == "task_2")

        self.assertEqual(task_2["intent_family"], "book_concept_explanation")
        self.assertEqual(task_2["backtest_status"], "NOT_APPLICABLE")
        self.assertEqual(task_2["paper_status"], "NOT_APPLICABLE")

    def test_multi_intent_task_scope_is_preserved(self):
        service, _, _, _ = dashboard_service(multi=True)
        chain = service.chain_view(request_id="bt_req")[0]
        task_1 = next(task for task in chain.task_chain if task["task_id"] == "task_1")
        task_2 = next(task for task in chain.task_chain if task["task_id"] == "task_2")

        self.assertEqual(task_1["symbol"], "XAUUSD")
        self.assertEqual(task_2["symbol"], "")
        self.assertIn("Reading Price Charts Bar by Bar - Al Brooks", task_2["source_refs"])
        self.assertNotIn("market_snapshot:XAUUSD", task_2["source_refs"])
        self.assertNotIn("XAUUSD", json.dumps(task_2, ensure_ascii=False))

    def test_export_preview_is_review_safe(self):
        service, _, _, _ = dashboard_service()

        preview = service.export_preview({"request_id": "bt_req"})
        blob = preview.to_json().lower()

        self.assertEqual(preview.rows_count, 3)
        self.assertTrue(preview.safe_to_download)
        self.assertNotIn("raw_prompt", blob)
        self.assertNotIn("full_prompt", blob)
        self.assertNotIn("final_answer_text", blob)
        self.assertNotIn("account_balance", blob)
        self.assertNotIn("order_id", blob)
        self.assertNotIn("mt5_credentials", blob)
        self.assertIn("registry_id", preview.to_csv())

    def test_replay_view_displays_mismatches_and_safety(self):
        journal, _, _ = records()
        case = EvaluationReplayCase(
            replay_id="replay:mismatch:dashboard",
            case_type="backtest",
            input_records={"journal_review_record": journal},
            supplied_fixtures={"historical_observation_windows": [window("up", "task_1")]},
            expected_outputs={"expected_status": "SKIPPED"},
        )

        view = replay_view_from_result(EvaluationReplayHarness.replay(case))

        self.assertEqual(view.status, "FAIL")
        self.assertTrue(view.mismatches)
        self.assertTrue(view.safety_summary["no_provider_calls"])
        self.assertTrue(view.safety_summary["no_retrieval"])
        self.assertTrue(view.safety_summary["no_execution"])
        self.assertFalse(view.safety_summary["execution_allowed"])

    def test_dashboard_does_not_mutate_registry_entries_or_create_evidence_items(self):
        service, _, _, _ = dashboard_service()
        before = [entry.as_dict() for entry in service.registry.list_registry_entries({})]

        service.load()
        rows = service.load()[1]
        service.detail(rows[0].registry_id)
        service.chain_view()
        service.export_preview()

        after = [entry.as_dict() for entry in service.registry.list_registry_entries({})]
        self.assertEqual(before, after)
        self.assertNotIn("EvidenceItem", json.dumps(after, ensure_ascii=False))

    def test_ui_tab_import_smoke(self):
        import src.ui.tab_evaluation_dashboard as dashboard_tab

        self.assertTrue(hasattr(dashboard_tab, "render"))

    def test_execution_allowed_false_preserved(self):
        service, _, _, _ = dashboard_service()

        summary, rows = service.load()
        self.assertFalse(summary.execution_allowed)
        self.assertTrue(all(not row.execution_allowed for row in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
