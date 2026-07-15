import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_evaluation_registry_replay import records  # noqa: E402
from src.services.agents.evaluation_dashboard import EvaluationDashboardFilters, EvaluationDashboardService  # noqa: E402
from src.services.agents.evaluation_persistence import EvaluationPersistenceStore  # noqa: E402
from src.services.agents.evaluation_registry import EvaluationRegistry  # noqa: E402
from src.services.agents.human_review import HumanReviewStore, annotation_from_registry_entry  # noqa: E402
from src.services.agents.review_analytics import (  # noqa: E402
    QualityMetricsReport,
    ReviewAnalyticsEngine,
    ReviewAnalyticsFilters,
)


def build_registry(multi=False):
    journal, backtest, paper = records(multi=multi)
    registry = EvaluationRegistry()
    for record, record_type in (
        (journal, "journal_review"),
        (backtest, "backtest_evaluation"),
        (paper, "paper_trading_evaluation"),
    ):
        registry.register(record, record_type)
    return registry


class ReviewAnalyticsQualityMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.persistence = EvaluationPersistenceStore(root / "registry.jsonl", root / "manifest.json", root / "exports")
        self.review = HumanReviewStore(
            root / "annotations.jsonl",
            root / "states.json",
            root / "annotated_versions.json",
            root / "review_exports",
            self.persistence,
        )
        self.registry = build_registry()
        self.entries = self.registry.list_registry_entries({})
        self.persistence.save_entries(self.entries)

    def tearDown(self):
        self.temp.cleanup()

    def annotation(self, entry=None, task_id="task_1", reviewer_id="alice", **overrides):
        entry = entry or self.entries[0]
        defaults = {
            "reviewer_id": reviewer_id,
            "review_status": "APPROVED",
            "quality_decision": "HIGH_QUALITY",
            "correctness_label": "CORRECT",
            "grounding_label": "WELL_GROUNDED",
            "safety_label": "SAFE",
            "task_scope_label": "TASK_SCOPE_OK",
            "reason_codes": [],
            "reviewer_note": "Safe review note.",
            "suggested_fix_summary": "No system-quality follow-up needed.",
            "severity": "LOW",
        }
        defaults.update(overrides)
        return annotation_from_registry_entry(entry, task_id=task_id, **defaults)

    def report(self, filters=None):
        states = self.review.list_workflow_states()
        engine = ReviewAnalyticsEngine(
            self.registry.list_registry_entries({}),
            self.review.load_annotations(),
            states,
            self.persistence.list_dataset_versions(),
            self.review.list_annotated_dataset_versions(),
        )
        return engine.compute(filters)

    def test_filters_and_empty_report_schema(self):
        filters = ReviewAnalyticsFilters(request_id="missing")
        report = self.report(filters)

        self.assertIsInstance(report, QualityMetricsReport)
        self.assertEqual(report.filters_used["request_id"], "missing")
        self.assertEqual(report.coverage.total_registry_entries, 0)
        self.assertEqual(report.coverage.annotation_coverage_rate, 0.0)
        self.assertFalse(report.execution_allowed)

    def test_coverage_and_quality_scores_from_reviewed_annotations(self):
        self.review.save_annotation(self.annotation(self.entries[0], quality_decision="HIGH_QUALITY"))
        self.review.save_annotation(self.annotation(self.entries[1], quality_decision="ACCEPTABLE", correctness_label="PARTIALLY_CORRECT"))

        report = self.report()

        self.assertEqual(report.coverage.total_registry_entries, 3)
        self.assertEqual(report.coverage.annotated_entries, 2)
        self.assertEqual(report.coverage.unreviewed_entries, 1)
        self.assertEqual(report.coverage.annotation_coverage_rate, 0.6667)
        self.assertEqual(report.quality.quality_score, 0.9)
        self.assertEqual(report.correctness.correctness_score, 0.75)
        self.assertEqual(report.quality.high_quality_count, 1)
        self.assertEqual(report.quality.acceptable_count, 1)

    def test_grounding_safety_task_scope_and_reason_code_metrics(self):
        self.review.save_annotation(
            self.annotation(
                self.entries[0],
                review_status="NEEDS_FIX",
                quality_decision="ACCEPTABLE_WITH_WARNINGS",
                grounding_label="MISSING_SOURCE",
                safety_label="WARNING",
                task_scope_label="POSSIBLE_LEAKAGE",
                reason_codes=[
                    "MISSING_SOURCE_REFERENCE",
                    "MULTI_INTENT_LEAKAGE",
                    "BACKTEST_DISAGREES_WITH_THESIS",
                    "PAPER_EVAL_INVALIDATION_OBSERVED",
                    "RISK_MATERIALIZED",
                    "CONFIDENCE_CALIBRATION_WEAK",
                    "REPLAY_MISMATCH",
                ],
                severity="HIGH",
            )
        )

        report = self.report()

        self.assertEqual(report.grounding.missing_source_count, 1)
        self.assertEqual(report.grounding.grounding_issue_rate, 1.0)
        self.assertEqual(report.safety.warning_count, 1)
        self.assertEqual(report.safety.safety_issue_rate, 1.0)
        self.assertEqual(report.task_scope.possible_leakage_count, 1)
        self.assertEqual(report.task_scope.task_leakage_rate, 1.0)
        self.assertEqual(report.reason_codes.reason_code_counts["MISSING_SOURCE_REFERENCE"], 1)
        self.assertEqual(report.reason_codes.reason_category_counts["Evidence / Grounding"], 1)
        self.assertEqual(report.evaluation_consistency.backtest_disagreement_count, 1)
        self.assertEqual(report.evaluation_consistency.paper_invalidation_count, 1)
        self.assertEqual(report.evaluation_consistency.risk_materialized_count, 1)
        self.assertEqual(report.evaluation_consistency.confidence_calibration_weak_count, 1)
        self.assertEqual(report.evaluation_consistency.replay_mismatch_count, 1)
        self.assertTrue(report.recommendations)

    def test_dataset_health_labels(self):
        self.review.save_annotation(self.annotation(quality_decision="HIGH_QUALITY"))
        self.assertEqual(self.report().dataset_quality.dataset_health_label, "EXCELLENT")

        self.temp.cleanup()
        self.setUp()
        self.review.save_annotation(self.annotation(quality_decision="ACCEPTABLE"))
        self.assertEqual(self.report().dataset_quality.dataset_health_label, "GOOD")

        self.temp.cleanup()
        self.setUp()
        self.review.save_annotation(self.annotation(quality_decision="ACCEPTABLE_WITH_WARNINGS"))
        self.assertEqual(self.report().dataset_quality.dataset_health_label, "NEEDS_REVIEW")

        self.temp.cleanup()
        self.setUp()
        self.review.save_annotation(self.annotation(quality_decision="LOW_QUALITY"))
        self.assertEqual(self.report().dataset_quality.dataset_health_label, "DEGRADED")

        self.temp.cleanup()
        self.setUp()
        self.review.save_annotation(self.annotation(quality_decision="UNSAFE", safety_label="UNSAFE", reason_codes=["TRADING_INSTRUCTION_PRESENT"], severity="CRITICAL"))
        report = self.report()
        self.assertEqual(report.dataset_quality.dataset_health_label, "UNSAFE")
        self.assertEqual(report.safety.trading_instruction_issue_count, 1)

    def test_reviewer_activity_and_disagreement_detection(self):
        entry = self.entries[0]
        self.review.save_annotation(self.annotation(entry, reviewer_id="alice", quality_decision="HIGH_QUALITY", safety_label="SAFE", task_scope_label="TASK_SCOPE_OK"))
        self.review.save_annotation(self.annotation(entry, reviewer_id="bob", quality_decision="INVALID", safety_label="UNSAFE", task_scope_label="TASK_SCOPE_FAIL", severity="CRITICAL"))

        report = self.report()

        self.assertEqual(report.reviewer_activity.reviewer_count, 2)
        self.assertEqual(report.reviewer_activity.annotations_by_reviewer["alice"], 1)
        self.assertEqual(report.reviewer_activity.annotations_by_reviewer["bob"], 1)
        self.assertGreaterEqual(report.reviewer_activity.reviewer_disagreement_count, 3)
        self.assertTrue(any(item["severity"] == "HIGH" for item in report.reviewer_activity.disagreements))

    def test_task_intent_symbol_breakdowns_and_static_book_isolation(self):
        self.registry = build_registry(multi=True)
        self.entries = self.registry.list_registry_entries({})
        self.persistence.save_entries(self.entries)
        journal = next(entry for entry in self.entries if entry.record_type == "journal_review")
        self.review.save_annotation(self.annotation(journal, task_id="task_1", reviewer_id="alice"))
        self.review.save_annotation(self.annotation(journal, task_id="task_2", reviewer_id="bob", grounding_label="WELL_GROUNDED"))

        report = self.report()
        task_1 = report.task_breakdown["task_1"]
        task_2 = report.task_breakdown["task_2"]

        self.assertIn("macro_market_impact", report.intent_family_breakdown)
        self.assertIn("book_concept_explanation", report.intent_family_breakdown)
        self.assertIn("XAUUSD", report.symbol_breakdown)
        self.assertEqual(task_1["annotations"], 1)
        self.assertEqual(task_2["annotations"], 1)
        self.assertNotIn("XAUUSD", json.dumps(task_2, ensure_ascii=False))
        self.assertEqual(report.task_scope.static_task_market_leakage_count, 0)

    def test_filters_by_labels_dataset_and_annotated_dataset(self):
        self.review.save_annotation(self.annotation(self.entries[0], reviewer_id="alice", review_status="APPROVED", severity="LOW"))
        self.review.save_annotation(self.annotation(self.entries[1], reviewer_id="bob", review_status="NEEDS_FIX", severity="HIGH", reason_codes=["WEAK_SOURCE_SUPPORT"]))
        dataset = self.persistence.create_dataset_version("filtered", filters={"record_type": "journal_review"})
        annotated = self.review.create_annotated_dataset_version("annotated")

        needs_fix = self.report(ReviewAnalyticsFilters(review_status="NEEDS_FIX"))
        by_reviewer = self.report(ReviewAnalyticsFilters(reviewer_id="bob"))
        by_dataset = self.report(ReviewAnalyticsFilters(dataset_version_id=dataset.version_id))
        by_annotated = self.report(ReviewAnalyticsFilters(annotated_dataset_version_id=annotated.version_id))

        self.assertEqual(needs_fix.coverage.annotated_entries, 1)
        self.assertEqual(by_reviewer.coverage.reviewed_by_reviewer["bob"], 1)
        self.assertEqual(by_dataset.coverage.total_registry_entries, 1)
        self.assertEqual(by_annotated.coverage.annotated_entries, 2)
        self.assertEqual(by_annotated.dataset_quality.dataset_id, annotated.version_id)
        self.assertEqual(by_annotated.dataset_quality.annotation_hash, annotated.annotation_hash)

    def test_metrics_export_json_is_safe(self):
        self.review.save_annotation(self.annotation(reason_codes=["MISSING_SOURCE_REFERENCE"]))
        report = self.report()
        export = ReviewAnalyticsEngine().export_report(report, export_dir=Path(self.temp.name) / "analytics")
        blob = Path(export.export_path).read_text(encoding="utf-8").lower()

        self.assertEqual(export.status, "EXPORTED")
        self.assertGreater(export.payload_chars, 0)
        self.assertIn("quality_score", blob)
        for forbidden in [
            "raw_prompt",
            "full_prompt",
            "final_answer_text",
            "account_balance",
            "order_id",
            "mt5_credentials",
            "entry_price",
            "stop_loss",
            "take_profit",
            "lot_size",
            "account_risk_percent",
        ]:
            self.assertNotIn(forbidden, blob)
        self.assertFalse(export.execution_allowed)

    def test_recommendations_are_system_quality_only(self):
        self.review.save_annotation(
            self.annotation(
                quality_decision="UNSAFE",
                safety_label="UNSAFE",
                reason_codes=["TRADING_INSTRUCTION_PRESENT"],
                severity="CRITICAL",
            )
        )

        report = self.report()
        text = " ".join(report.recommendations).lower()

        self.assertIn("review compliance", text)
        for forbidden in ["buy", "sell", "entry", "stop-loss", "take-profit", "lot size", "account risk", "mt5"]:
            self.assertNotIn(forbidden, text)

    def test_analytics_does_not_mutate_registry_annotations_or_create_evidence_items(self):
        self.review.save_annotation(self.annotation())
        before_entries = [copy.deepcopy(entry.as_dict()) for entry in self.registry.list_registry_entries({})]
        before_annotations = [copy.deepcopy(item.as_dict()) for item in self.review.load_annotations()]

        report = self.report()

        after_entries = [entry.as_dict() for entry in self.registry.list_registry_entries({})]
        after_annotations = [item.as_dict() for item in self.review.load_annotations()]
        blob = json.dumps(report.as_dict(), ensure_ascii=False)
        self.assertEqual(before_entries, after_entries)
        self.assertEqual(before_annotations, after_annotations)
        self.assertNotIn("EvidenceItem", blob)

    def test_dashboard_analytics_view_model_and_empty_state(self):
        empty = EvaluationDashboardService(EvaluationRegistry())
        empty_report = empty.analytics_report()
        self.assertEqual(empty_report.coverage.total_registry_entries, 0)

        self.review.save_annotation(self.annotation())
        service = EvaluationDashboardService(self.registry, self.persistence, self.review)
        report = service.analytics_report(EvaluationDashboardFilters(request_id="bt_req"))

        self.assertEqual(report.coverage.total_registry_entries, 3)
        self.assertFalse(report.execution_allowed)
        self.assertIn("task_1", report.task_breakdown)

    def test_execution_allowed_false_preserved(self):
        self.review.save_annotation(self.annotation())
        report = self.report()

        self.assertFalse(report.coverage.execution_allowed)
        self.assertFalse(report.execution_allowed)
        self.assertTrue(all(not entry.execution_allowed for entry in self.registry.list_registry_entries({})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
