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
from src.services.agents.human_review import (  # noqa: E402
    HumanReviewAnnotation,
    HumanReviewStore,
    REASON_CODE_TAXONOMY,
    annotation_from_registry_entry,
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


class HumanReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.persistence = EvaluationPersistenceStore(root / "registry.jsonl", root / "manifest.json", root / "exports")
        self.review = HumanReviewStore(
            root / "human_review_annotations.jsonl",
            root / "review_workflow_states.json",
            root / "annotated_dataset_versions.json",
            root / "review_exports",
            self.persistence,
        )
        self.registry = build_registry()
        self.entries = self.registry.list_registry_entries({})
        self.persistence.save_entries(self.entries)

    def tearDown(self):
        self.temp.cleanup()

    def annotation(self, entry=None, task_id="task_1", **overrides):
        entry = entry or self.entries[0]
        defaults = {
            "reviewer_id": "alice",
            "review_status": "APPROVED_WITH_NOTES",
            "quality_decision": "ACCEPTABLE",
            "correctness_label": "PARTIALLY_CORRECT",
            "grounding_label": "WELL_GROUNDED",
            "safety_label": "SAFE",
            "task_scope_label": "TASK_SCOPE_OK",
            "reason_codes": [],
            "reviewer_note": "Safe short note.",
            "suggested_fix_summary": "No user-facing change required.",
            "severity": "LOW",
        }
        defaults.update(overrides)
        return annotation_from_registry_entry(entry, task_id=task_id, **defaults)

    def test_annotation_schema_save_load_by_id_and_registry(self):
        annotation = self.annotation()
        result = self.review.save_annotation(annotation)

        loaded = self.review.get_annotation(result.annotation_id)
        by_registry = self.review.get_annotations_for_registry_id(annotation.registry_id)

        self.assertEqual(result.status, "SAVED")
        self.assertIsInstance(loaded, HumanReviewAnnotation)
        self.assertEqual(loaded.registry_id, annotation.registry_id)
        self.assertEqual(len(by_registry), 1)
        self.assertEqual(loaded.execution_allowed, False)

    def test_workflow_state_unreviewed_updates_and_latest_wins(self):
        entry = self.entries[0]
        self.assertEqual(self.review.get_workflow_state(entry.registry_id).current_status, "UNREVIEWED")
        first = self.annotation(entry, review_status="IN_REVIEW", severity="MEDIUM")
        second = self.annotation(entry, review_status="NEEDS_FIX", severity="HIGH", reason_codes=["UNCLEAR_REASONING"])

        self.review.save_annotation(first)
        self.review.save_annotation(second)
        state = self.review.get_workflow_state(entry.registry_id)

        self.assertEqual(state.current_status, "NEEDS_FIX")
        self.assertEqual(state.annotation_count, 2)
        self.assertEqual(state.highest_severity, "HIGH")
        self.assertTrue(state.has_open_issue)

    def test_lock_annotation_and_registry_review(self):
        annotation = self.annotation()
        result = self.review.save_annotation(annotation)
        locked = self.review.lock_annotation(result.annotation_id)
        duplicate = self.review.save_annotation(self.review.get_annotation(result.annotation_id))
        registry_lock = self.review.lock_registry_review(annotation.registry_id)
        after_lock = self.review.save_annotation(self.annotation(review_status="APPROVED"))

        self.assertEqual(locked.status, "LOCKED")
        self.assertEqual(duplicate.status, "LOCKED")
        self.assertEqual(registry_lock.status, "LOCKED")
        self.assertEqual(after_lock.status, "LOCKED")
        self.assertTrue(self.review.get_workflow_state(annotation.registry_id).locked)

    def test_reason_codes_are_bounded_and_unknown_rejected(self):
        self.assertIn("MISSING_SOURCE_REFERENCE", REASON_CODE_TAXONOMY)
        valid = self.review.save_annotation(self.annotation(reason_codes=["MISSING_SOURCE_REFERENCE"]))
        invalid = self.review.save_annotation(self.annotation(reason_codes=["MADE_UP_REASON"]))

        self.assertEqual(valid.status, "SAVED")
        self.assertEqual(invalid.status, "REJECTED")
        self.assertIn("unknown_reason_code", invalid.warnings)

    def test_reviewer_note_and_fix_summary_redact_secrets_and_execution_details(self):
        annotation = self.annotation(
            reviewer_note="API_KEY=secret-value. Buy now at entry price 2400 and send MT5 order.",
            suggested_fix_summary="Remove stop loss 2390, take profit 2420, lot size 1, account risk 2%.",
        )

        result = self.review.save_annotation(annotation)
        loaded = self.review.get_annotation(result.annotation_id)
        blob = json.dumps(loaded.as_dict(), ensure_ascii=False).lower()

        self.assertEqual(result.status, "SAVED")
        self.assertGreater(result.redactions, 0)
        self.assertNotIn("secret-value", blob)
        self.assertNotIn("2400", blob)
        self.assertNotIn("mt5 order", blob)

    def test_annotation_preserves_binding_and_task_scope(self):
        annotation = self.annotation()
        self.review.save_annotation(annotation)
        loaded = self.review.load_annotations()[0]

        self.assertEqual(loaded.registry_id, annotation.registry_id)
        self.assertEqual(loaded.request_id, "bt_req")
        self.assertEqual(loaded.final_answer_sha256, "abc123")
        self.assertEqual(loaded.task_id, "task_1")
        self.assertEqual(loaded.record_type, annotation.record_type)
        self.assertTrue(loaded.source_refs_snapshot)

    def test_multi_intent_task_annotations_remain_isolated(self):
        registry = build_registry(multi=True)
        entries = registry.list_registry_entries({})
        self.persistence.save_entries(entries)
        journal_entry = next(entry for entry in entries if entry.record_type == "journal_review")
        task_1 = self.annotation(journal_entry, "task_1")
        task_2 = self.annotation(journal_entry, "task_2", review_status="APPROVED")

        self.review.save_annotation(task_1)
        self.review.save_annotation(task_2)
        annotations = self.review.get_annotations_for_registry_id(journal_entry.registry_id)
        a1 = next(item for item in annotations if item.task_id == "task_1")
        a2 = next(item for item in annotations if item.task_id == "task_2")

        self.assertIn("market_snapshot:XAUUSD", a1.source_refs_snapshot)
        self.assertIn("Reading Price Charts Bar by Bar - Al Brooks", a2.source_refs_snapshot)
        self.assertNotIn("market_snapshot:XAUUSD", a2.source_refs_snapshot)
        self.assertNotIn("XAUUSD", json.dumps(a2.as_dict(), ensure_ascii=False))

    def test_review_batch_summary_counts_statuses_and_high_severity(self):
        self.review.save_annotation(self.annotation(review_status="APPROVED", severity="LOW"))
        self.review.save_annotation(self.annotation(self.entries[1], review_status="NEEDS_FIX", severity="HIGH", safety_label="WARNING", reason_codes=["BACKTEST_DISAGREES_WITH_THESIS"]))
        self.review.save_annotation(self.annotation(self.entries[2], review_status="REJECTED", quality_decision="UNSAFE", safety_label="UNSAFE", severity="CRITICAL", reason_codes=["MT5_OR_ORDER_LANGUAGE_PRESENT"]))

        summary = self.review.batch_summary()

        self.assertEqual(summary.reviewed_count, 3)
        self.assertEqual(summary.approved_count, 1)
        self.assertEqual(summary.needs_fix_count, 1)
        self.assertEqual(summary.rejected_count, 1)
        self.assertEqual(summary.unsafe_count, 1)
        self.assertEqual(summary.high_severity_count, 2)
        self.assertEqual(summary.by_reviewer["alice"], 3)

    def test_create_annotated_dataset_version_and_deterministic_hash(self):
        self.review.save_annotation(self.annotation(review_status="APPROVED"))
        first = self.review.create_annotated_dataset_version("supervised", locked=True)
        second = self.review.create_annotated_dataset_version("supervised", locked=True)

        self.assertEqual(first.entries_count, 1)
        self.assertEqual(first.annotation_hash, second.annotation_hash)
        self.assertEqual(first.dataset_hash, second.dataset_hash)
        self.assertTrue(first.locked)

    def test_export_annotated_dataset_json_csv_is_safe(self):
        self.review.save_annotation(self.annotation(review_status="APPROVED", reviewer_note="Reviewed safely."))
        version = self.review.create_annotated_dataset_version("exportable")
        json_export = self.review.export_annotated_dataset(version.version_id, "json")
        csv_export = self.review.export_annotated_dataset(version.version_id, "csv")
        blob = Path(json_export.export_path).read_text(encoding="utf-8").lower()

        self.assertEqual(json_export.status, "EXPORTED")
        self.assertEqual(csv_export.status, "EXPORTED")
        for forbidden in ["raw_prompt", "full_prompt", "final_answer_text", "secret-value", "account_balance", "order_id", "mt5_credentials", "entry_price", "stop_loss", "take_profit", "lot_size", "account_risk_percent"]:
            self.assertNotIn(forbidden, blob)
        self.assertIn("annotation_id", Path(csv_export.export_path).read_text(encoding="utf-8"))

    def test_import_validate_clean_export_rejects_unsafe_and_deduplicates(self):
        self.review.save_annotation(self.annotation(review_status="APPROVED"))
        version = self.review.create_annotated_dataset_version("importable")
        export = self.review.export_annotated_dataset(version.version_id, "json")
        other_root = Path(self.temp.name) / "other"
        other_persistence = EvaluationPersistenceStore(other_root / "registry.jsonl", other_root / "manifest.json", other_root / "exports")
        other = HumanReviewStore(other_root / "annotations.jsonl", other_root / "states.json", other_root / "versions.json", other_root / "exports", other_persistence)

        validate = other.import_annotations(export.export_path, validate_only=True)
        imported = other.import_annotations(export.export_path, validate_only=False)
        duplicate = other.import_annotations(export.export_path, validate_only=False)

        unsafe_path = Path(export.export_path).with_name("unsafe_annotations.json")
        data = json.loads(Path(export.export_path).read_text(encoding="utf-8"))
        data["annotations"][0]["raw_prompt"] = "hidden"
        unsafe_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        unsafe = other.import_annotations(unsafe_path, validate_only=True)

        self.assertEqual(validate.status, "VALIDATED")
        self.assertEqual(imported.status, "IMPORTED")
        self.assertEqual(duplicate.skipped_duplicates, 1)
        self.assertEqual(unsafe.status, "REJECTED")

    def test_dashboard_service_saves_annotation_filters_and_history(self):
        service = EvaluationDashboardService(self.registry, self.persistence, self.review)
        entry = self.entries[0]

        result = service.save_review_annotation(
            entry.registry_id,
            "task_1",
            "reviewer-ui",
            review_status="NEEDS_FIX",
            quality_decision="ACCEPTABLE_WITH_WARNINGS",
            correctness_label="PARTIALLY_CORRECT",
            grounding_label="PARTIALLY_GROUNDED",
            safety_label="WARNING",
            task_scope_label="TASK_SCOPE_OK",
            reason_codes=["OVERCONFIDENT_LANGUAGE"],
            reviewer_note="Needs a softer conclusion.",
            suggested_fix_summary="Use conditional wording.",
            severity="MEDIUM",
        )
        filtered = service.load(EvaluationDashboardFilters(review_status="NEEDS_FIX"))[1]
        severity_filtered = service.load(EvaluationDashboardFilters(severity="MEDIUM"))[1]

        self.assertEqual(result.status, "SAVED")
        self.assertEqual(len(service.review_history(entry.registry_id)), 1)
        self.assertEqual(service.workflow_state(entry.registry_id).current_status, "NEEDS_FIX")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(len(severity_filtered), 1)

    def test_human_review_does_not_mutate_registry_or_final_answer_or_create_evidence(self):
        before = [entry.as_dict() for entry in self.entries]
        self.review.save_annotation(self.annotation())
        after = [entry.as_dict() for entry in self.entries]
        blob = self.review.annotation_path.read_text(encoding="utf-8")

        self.assertEqual(before, after)
        self.assertNotIn("EvidenceItem", blob)
        self.assertIn("abc123", blob)

    def test_no_provider_retrieval_market_mt5_account_calls_and_execution_false(self):
        self.review.save_annotation(self.annotation())
        blob = self.review.annotation_path.read_text(encoding="utf-8").lower()

        self.assertNotIn("provider_response", blob)
        self.assertNotIn("retrieval_payload", blob)
        self.assertNotIn("account_balance", blob)
        self.assertNotIn("mt5_credentials", blob)
        self.assertTrue(all(not item.execution_allowed for item in self.review.load_annotations()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
