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
from src.services.agents.evaluation_dashboard import EvaluationDashboardService  # noqa: E402
from src.services.agents.evaluation_persistence import (  # noqa: E402
    EvaluationDatasetVersion,
    EvaluationPersistenceStore,
    PERSISTENCE_SCHEMA_VERSION,
    _storage_hash,
)
from src.services.agents.evaluation_registry import EvaluationRegistry  # noqa: E402


def make_registry(multi=False):
    journal, backtest, paper = records(multi=multi)
    registry = EvaluationRegistry()
    registry.register(journal, "journal_review")
    registry.register(backtest, "backtest_evaluation")
    registry.register(paper, "paper_trading_evaluation")
    return registry, journal, backtest, paper


class EvaluationPersistenceVersioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EvaluationPersistenceStore(root / "registry" / "evaluation_registry.jsonl", root / "versions" / "dataset_versions.json", root / "exports")

    def tearDown(self):
        self.temp.cleanup()

    def save_clean_entries(self, multi=False):
        registry, journal, backtest, paper = make_registry(multi=multi)
        entries = registry.list_registry_entries({})
        result = self.store.save_entries(entries)
        self.assertEqual(result.status, "PASS")
        return entries, journal, backtest, paper

    def test_persisted_entry_schema_save_one_and_duplicate_skip(self):
        entries, _, _, _ = self.save_clean_entries()
        line = json.loads(self.store.registry_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(line["schema_version"], PERSISTENCE_SCHEMA_VERSION)
        self.assertIn("storage_hash", line)
        self.assertIn("task_index", line)
        self.assertEqual(line["execution_allowed"], False)
        duplicate = self.store.save_entry(entries[0])
        self.assertEqual(duplicate.status, "SKIPPED_DUPLICATE")

    def test_save_journal_backtest_paper_and_load_after_new_store_instance(self):
        self.save_clean_entries()
        reloaded = EvaluationPersistenceStore(self.store.registry_path, self.store.manifest_path, self.store.export_dir)

        loaded = reloaded.load_entries()

        self.assertEqual(len(loaded), 3)
        self.assertEqual({entry.record_type for entry in loaded}, {"journal_review", "backtest_evaluation", "paper_trading_evaluation"})
        self.assertTrue(all(entry.final_answer_sha256 == "abc123" for entry in loaded))

    def test_load_latest_and_filters(self):
        self.save_clean_entries()

        self.assertEqual(len(self.store.load_latest(limit=2)), 2)
        self.assertEqual(len(self.store.load_entries({"request_id": "bt_req"})), 3)
        self.assertEqual(len(self.store.load_entries({"final_answer_sha256": "abc123"})), 3)
        self.assertGreaterEqual(len(self.store.load_entries({"symbol": "XAUUSD"})), 2)
        self.assertEqual(len(self.store.load_entries({"status": "EVALUATED"})), 2)
        self.assertEqual(len(self.store.load_entries({"quality_label": "useful_for_review"})), 2)

    def test_validate_store_pass_and_duplicate_warn(self):
        entries, _, _, _ = self.save_clean_entries()
        self.assertEqual(self.store.validate_store().status, "PASS")

        payload = json.loads(self.store.registry_path.read_text(encoding="utf-8").splitlines()[0])
        with self.store.registry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        validation = self.store.validate_store()

        self.assertEqual(validation.status, "WARN")
        self.assertEqual(validation.duplicate_entries, 1)
        self.assertEqual(entries[0].registry_id, payload["registry_id"])

    def test_validate_store_fail_for_unsafe_record(self):
        self.save_clean_entries()
        payload = json.loads(self.store.registry_path.read_text(encoding="utf-8").splitlines()[0])
        payload["limitations"] = ["buy now with entry price and MT5 order"]
        payload["storage_hash"] = _storage_hash({k: v for k, v in payload.items() if k not in {"persisted_at", "storage_hash"}})
        with self.store.registry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

        validation = self.store.validate_store()

        self.assertEqual(validation.status, "FAIL")
        self.assertGreaterEqual(validation.unsafe_entries, 1)

    def test_persistence_excludes_raw_prompt_full_answer_secrets_account_order_mt5(self):
        self.save_clean_entries()
        blob = self.store.registry_path.read_text(encoding="utf-8").lower()

        for forbidden in ["raw_prompt", "full_prompt", "final_answer_text", "secret-value", "account_balance", "order_id", "mt5_credentials"]:
            self.assertNotIn(forbidden, blob)

    def test_rejects_trading_instruction_and_position_fields(self):
        entries, _, _, _ = self.save_clean_entries()
        unsafe = copy.deepcopy(entries[0].as_dict())
        unsafe["limitations"] = ["SELL now, entry price 2400, stop loss 2390, take profit 2420, lot size 1, account risk 2%, MT5 order"]
        unsafe_entry = EvaluationRegistry._entry(unsafe)

        result = self.store.save_entry(unsafe_entry)

        self.assertEqual(result.status, "REJECTED_UNSAFE")
        self.assertTrue(result.warnings)

    def test_preserves_source_refs_task_ids_and_multi_intent_isolation(self):
        self.save_clean_entries(multi=True)
        loaded = self.store.load_entries({"record_type": "journal_review"})[0]
        task_1 = next(task for task in loaded.task_index if task.task_id == "task_1")
        task_2 = next(task for task in loaded.task_index if task.task_id == "task_2")

        self.assertIn("task_1", loaded.task_ids)
        self.assertIn("task_2", loaded.task_ids)
        self.assertIn("market_snapshot:XAUUSD", task_1.source_refs)
        self.assertIn("Reading Price Charts Bar by Bar - Al Brooks", task_2.source_refs)
        self.assertEqual(task_2.symbol, "")
        self.assertNotIn("market_snapshot:XAUUSD", task_2.source_refs)
        self.assertNotIn("XAUUSD", json.dumps(task_2.as_dict(), ensure_ascii=False))

    def test_does_not_mutate_registry_entries_final_answer_or_create_evidence_item(self):
        registry, _, _, _ = make_registry()
        before = [entry.as_dict() for entry in registry.list_registry_entries({})]

        self.store.save_entries(registry.list_registry_entries({}))

        after = [entry.as_dict() for entry in registry.list_registry_entries({})]
        self.assertEqual(before, after)
        self.assertNotIn("EvidenceItem", self.store.registry_path.read_text(encoding="utf-8"))
        self.assertIn("abc123", self.store.registry_path.read_text(encoding="utf-8"))

    def test_dataset_version_created_from_filtered_records_and_hash_deterministic(self):
        self.save_clean_entries()
        first = self.store.create_dataset_version("journal-only", "filtered", {"record_type": "journal_review"})
        second = self.store.create_dataset_version("journal-only", "filtered", {"record_type": "journal_review"})

        self.assertIsInstance(first, EvaluationDatasetVersion)
        self.assertEqual(first.entries_count, 1)
        self.assertEqual(first.dataset_hash, second.dataset_hash)
        self.assertEqual(first.record_type_counts["journal_review"], 1)
        self.assertIn("bt_req", first.request_ids)

    def test_dataset_manifest_list_get_export_json_and_csv(self):
        self.save_clean_entries()
        version = self.store.create_dataset_version("all-records", "all", {})

        versions = self.store.list_dataset_versions()
        self.assertEqual(len(versions), 1)
        self.assertEqual(self.store.get_dataset_version(version.version_id).dataset_hash, version.dataset_hash)
        json_export = self.store.export_dataset_version(version.version_id, "json")
        csv_export = self.store.export_dataset_version(version.version_id, "csv")

        self.assertEqual(json_export.status, "EXPORTED")
        self.assertEqual(csv_export.status, "EXPORTED")
        self.assertTrue(Path(json_export.export_path).exists())
        self.assertTrue(Path(csv_export.export_path).exists())

    def test_export_excludes_unsafe_fields_and_import_validate_clean_export(self):
        self.save_clean_entries()
        version = self.store.create_dataset_version("clean", "", {})
        export = self.store.export_dataset_version(version.version_id, "json")
        blob = Path(export.export_path).read_text(encoding="utf-8").lower()

        for forbidden in ["raw_prompt", "full_prompt", "final_answer_text", "secret-value", "account_balance", "order_id", "mt5_credentials"]:
            self.assertNotIn(forbidden, blob)

        with tempfile.TemporaryDirectory() as temp:
            other = EvaluationPersistenceStore(Path(temp) / "registry.jsonl", Path(temp) / "manifest.json", Path(temp) / "exports")
            validation = other.import_dataset_export(export.export_path, validate_only=True)
            imported = other.import_dataset_export(export.export_path, validate_only=False)

        self.assertEqual(validation.status, "VALIDATED")
        self.assertEqual(imported.status, "IMPORTED")
        self.assertEqual(imported.imported_count, 3)

    def test_import_rejects_unsafe_export_and_deduplicates_existing_ids(self):
        self.save_clean_entries()
        version = self.store.create_dataset_version("clean", "", {})
        export = self.store.export_dataset_version(version.version_id, "json")
        duplicate = self.store.import_dataset_export(export.export_path, validate_only=False)

        unsafe_path = Path(export.export_path).with_name("unsafe_export.json")
        data = json.loads(Path(export.export_path).read_text(encoding="utf-8"))
        data["entries"][0]["raw_prompt"] = "hidden"
        unsafe_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        unsafe = self.store.import_dataset_export(unsafe_path, validate_only=True)

        self.assertEqual(duplicate.status, "IMPORTED")
        self.assertEqual(duplicate.skipped_duplicates, 3)
        self.assertEqual(unsafe.status, "REJECTED")
        self.assertGreaterEqual(unsafe.rejected_count, 1)

    def test_dashboard_service_loads_persisted_entries_summary_chain_export(self):
        self.save_clean_entries(multi=True)
        service = EvaluationDashboardService.from_persistence_store(self.store)

        summary, rows = service.load()
        chains = service.chain_view()
        preview = service.export_preview()

        self.assertEqual(summary.total_entries, 3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(chains), 1)
        self.assertTrue(preview.safe_to_download)
        task_2 = next(task for task in chains[0].task_chain if task["task_id"] == "task_2")
        self.assertEqual(task_2["backtest_status"], "SKIPPED")
        self.assertEqual(task_2["paper_status"], "SKIPPED")

    def test_dashboard_manual_save_load_and_store_validation(self):
        registry, _, _, _ = make_registry()
        service = EvaluationDashboardService(registry, self.store)

        saved = service.save_current_records()
        summary, rows = service.load_persisted_records()
        validation = service.validate_persistence_store()

        self.assertEqual(saved.saved, 3)
        self.assertEqual(summary.total_entries, 3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(validation.status, "PASS")

    def test_no_provider_retrieval_market_mt5_account_calls_and_execution_false(self):
        self.save_clean_entries()
        loaded = self.store.load_entries()
        blob = self.store.registry_path.read_text(encoding="utf-8").lower()

        self.assertTrue(all(not entry.execution_allowed for entry in loaded))
        self.assertNotIn("provider_response", blob)
        self.assertNotIn("retrieval_payload", blob)
        self.assertNotIn("account_balance", blob)
        self.assertNotIn("mt5_credentials", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
