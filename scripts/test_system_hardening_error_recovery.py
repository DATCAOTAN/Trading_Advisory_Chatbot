import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents.evaluation_dashboard import EvaluationDashboardService  # noqa: E402
from src.services.agents.evaluation_persistence import EvaluationPersistenceStore  # noqa: E402
from src.services.agents.evaluation_registry import (  # noqa: E402
    EvaluationRegistry,
    EvaluationRegistryEntry,
    EvaluationRegistryTaskIndex,
)
from src.services.agents.human_review import HumanReviewStore, annotation_from_registry_entry  # noqa: E402
from src.services.agents.review_analytics import ReviewAnalyticsEngine  # noqa: E402
from src.services.agents.system_hardening import (  # noqa: E402
    DiagnosticReport,
    QuarantineRecord,
    RecoveryPlan,
    SafeErrorEnvelope,
    SystemHardeningService,
    SystemIntegrityIssue,
    SystemIntegrityReport,
)


def registry_entry(task_id="task_1", intent="market_state_analysis", symbol="XAUUSD"):
    return EvaluationRegistryEntry(
        registry_id=f"registry:{task_id}",
        created_at="2026-01-01T00:00:00+00:00",
        record_type="journal_review",
        request_id="req_1",
        task_ids=[task_id],
        symbol=symbol,
        final_answer_sha256="abc123",
        quality_label="high_quality",
        status="PASS",
        execution_allowed=False,
        task_index=[
            EvaluationRegistryTaskIndex(
                task_id=task_id,
                intent_family=intent,
                symbol=symbol,
                status="PASS",
                quality_label="high_quality",
                source_refs=["market_snapshot:XAUUSD"] if symbol else ["Reading Price Charts Bar by Bar - Al Brooks"],
                agent_refs=["MarketContextAgent"] if symbol else [],
            )
        ],
        safety_index={"prohibited_outputs_detected": False},
        evaluation_index={},
        hashes={"final_answer_sha256": "abc123"},
    )


def persisted_payload(registry_id="registry:1", **updates):
    payload = {
        "schema_version": "evaluation_persistence.v1",
        "persisted_at": "2026-01-01T00:00:00+00:00",
        "registry_id": registry_id,
        "record_type": "journal_review",
        "request_id": "req_1",
        "task_ids": ["task_1"],
        "symbol": "XAUUSD",
        "final_answer_sha256": "abc123",
        "source_record_id": {"journal_id": "journal:1"},
        "quality_label": "high_quality",
        "status": "PASS",
        "review_outcome": "accepted",
        "review_priority": "LOW",
        "execution_allowed": False,
        "task_index": [
            {
                "task_id": "task_1",
                "intent_family": "market_state_analysis",
                "symbol": "XAUUSD",
                "status": "PASS",
                "quality_label": "high_quality",
                "review_flags": [],
                "source_refs": ["market_snapshot:XAUUSD"],
                "agent_refs": ["MarketContextAgent"],
            }
        ],
        "safety_index": {"prohibited_outputs_detected": False},
        "evaluation_index": {},
        "hashes": {"final_answer_sha256": "abc123"},
        "tags": [],
        "limitations": [],
        "storage_hash": "hash",
    }
    payload.update(updates)
    return payload


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) if not isinstance(row, str) else row for row in rows), encoding="utf-8")


class SystemHardeningErrorRecoveryTests(unittest.TestCase):
    def test_schema_dataclasses(self):
        service = SystemHardeningService()
        issue = service._issue("WARN", "PERSISTENCE_STORE", "store", "message")
        report = service._report(["component"], [issue], 0.0)
        plan = service.plan_recovery(report)
        envelope = service.normalize_error("provider", "stream", TimeoutError("timeout"))

        self.assertIsInstance(issue, SystemIntegrityIssue)
        self.assertIsInstance(report, SystemIntegrityReport)
        self.assertIsInstance(plan, RecoveryPlan)
        self.assertIsInstance(envelope, SafeErrorEnvelope)
        self.assertFalse(report.execution_allowed)
        self.assertFalse(plan.execution_allowed)
        self.assertFalse(envelope.execution_allowed)

    def test_missing_and_empty_registry_jsonl_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            service = SystemHardeningService(Path(temp) / "q", Path(temp) / "d")
            missing = service.validate_jsonl(Path(temp) / "missing.jsonl")
            empty_path = Path(temp) / "empty.jsonl"
            empty_path.write_text("", encoding="utf-8")
            empty = service.validate_jsonl(empty_path)

        self.assertEqual(missing.status, "WARN")
        self.assertEqual(missing.missing_artifacts_count, 1)
        self.assertEqual(empty.status, "PASS")
        self.assertFalse(missing.execution_allowed)
        self.assertFalse(empty.execution_allowed)

    def test_corrupt_jsonl_line_detected_and_quarantined(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.jsonl"
            write_jsonl(path, [persisted_payload(), "{bad json"])
            service = SystemHardeningService(Path(temp) / "quarantine", Path(temp) / "diagnostics")
            report = service.validate_jsonl(path, required_fields={"registry_id"}, expected_schema_versions={"evaluation_persistence.v1"})
            quarantined = service.quarantine_jsonl_records(path, [2], reason="corrupt JSONL line")
            quarantine_exists = Path(quarantined[0].quarantine_path).exists()

        self.assertEqual(report.status, "FAIL")
        self.assertEqual(report.corrupt_records_count, 1)
        self.assertEqual(len(quarantined), 1)
        self.assertIsInstance(quarantined[0], QuarantineRecord)
        self.assertTrue(quarantine_exists)
        self.assertTrue(quarantined[0].original_hash)
        self.assertFalse(quarantined[0].execution_allowed)

    def test_duplicate_and_missing_required_fields_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.jsonl"
            missing = persisted_payload("registry:missing")
            missing.pop("final_answer_sha256")
            write_jsonl(path, [persisted_payload("registry:dup"), persisted_payload("registry:dup"), missing])
            report = SystemHardeningService().validate_jsonl(path, required_fields={"registry_id", "final_answer_sha256"})

        messages = " ".join(issue.message for issue in report.issues)
        self.assertIn("duplicate", messages)
        self.assertIn("missing required fields", messages)
        self.assertIn(report.status, {"WARN", "FAIL"})

    def test_unsafe_raw_prompt_secret_account_mt5_and_trading_fields_detected_and_redacted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.jsonl"
            unsafe = persisted_payload(
                raw_prompt="do not store",
                api_key="sk-secretsecretsecret",
                account_balance="100000",
                mt5_credentials="mt5_password=secret",
                entry_price="unsafe",
                stop_loss="unsafe",
                take_profit="unsafe",
                lot_size="unsafe",
                account_risk_percent="unsafe",
            )
            write_jsonl(path, [unsafe])
            service = SystemHardeningService(Path(temp) / "q", Path(temp) / "d")
            report = service.validate_jsonl(path, required_fields={"registry_id"})
            plan = service.plan_recovery(report)
            diagnostic = service.export_diagnostic_report(report, plan)
            blob = Path(diagnostic.diagnostics_path).read_text(encoding="utf-8").lower()

        self.assertIn(report.status, {"FAIL", "CRITICAL"})
        self.assertGreaterEqual(report.unsafe_artifacts_count, 1)
        self.assertIsInstance(diagnostic, DiagnosticReport)
        self.assertNotIn("sk-secretsecretsecret", blob)
        self.assertNotIn("100000", blob)
        self.assertFalse(diagnostic.execution_allowed)

    def test_execution_allowed_true_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.jsonl"
            write_jsonl(path, [persisted_payload(execution_allowed=True)])
            report = SystemHardeningService().validate_jsonl(path, required_fields={"registry_id"})

        self.assertEqual(report.status, "CRITICAL")
        self.assertTrue(report.execution_allowed)
        self.assertTrue(any(issue.category == "SAFETY_BOUNDARY" for issue in report.issues))

    def test_invalid_manifest_and_missing_versions_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "invalid.json"
            invalid.write_text("{bad", encoding="utf-8")
            missing_versions = Path(temp) / "manifest.json"
            missing_versions.write_text(json.dumps({"schema_version": "evaluation_dataset_manifest.v1"}), encoding="utf-8")
            service = SystemHardeningService()
            invalid_report = service.validate_manifest(invalid)
            missing_report = service.validate_manifest(missing_versions)

        self.assertEqual(invalid_report.status, "FAIL")
        self.assertEqual(missing_report.status, "FAIL")

    def test_dashboard_empty_missing_selected_and_partial_chain_do_not_crash(self):
        service = EvaluationDashboardService(EvaluationRegistry())
        report, plan = service.system_health_report(selected_registry_id="missing")

        self.assertIn(report.status, {"WARN", "FAIL"})
        self.assertTrue(plan.actions)
        self.assertFalse(report.execution_allowed)

    def test_static_task_missing_backtest_paper_not_failure_but_market_task_warns(self):
        hardening = SystemHardeningService()
        static_report = hardening.validate_runtime_artifacts(
            {
                "final_answer_artifact": {"final_answer_sha256": "abc"},
                "tasks": [{"task_id": "task_2", "intent_family": "book_concept_explanation", "source_refs": ["Al Brooks"]}],
            }
        )
        market_report = hardening.validate_runtime_artifacts(
            {
                "final_answer_artifact": {"final_answer_sha256": "abc"},
                "tasks": [{"task_id": "task_1", "intent_family": "market_state_analysis", "symbol": "XAUUSD"}],
            }
        )

        self.assertFalse(any("market task is missing" in issue.message for issue in static_report.issues))
        self.assertTrue(any("market task is missing" in issue.message for issue in market_report.issues))

    def test_task_2_static_does_not_inherit_task_1_symbol(self):
        clean = registry_entry("task_2", "book_concept_explanation", "")
        leaked = registry_entry("task_2", "book_concept_explanation", "XAUUSD")
        hardening = SystemHardeningService()

        clean_report = hardening.validate_dashboard_state([clean])
        leaked_report = hardening.validate_dashboard_state([leaked])

        self.assertFalse(any("inherited" in issue.message for issue in clean_report.issues))
        self.assertTrue(any("inherited" in issue.message for issue in leaked_report.issues))

    def test_runtime_missing_compliance_and_final_hash_warns(self):
        report = SystemHardeningService().validate_runtime_artifacts({"final_answer_artifact": {}})
        messages = " ".join(issue.message for issue in report.issues)

        self.assertIn("final answer hash is missing", messages)
        self.assertIn("compliance result is missing", messages)
        self.assertIn(report.status, {"WARN", "FAIL"})

    def test_benchmark_missing_invalid_unsafe_and_bad_report_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            service = SystemHardeningService(Path(temp) / "q", Path(temp) / "d")
            missing = service.validate_benchmark_cases(Path(temp) / "missing.json")
            invalid = Path(temp) / "bad.json"
            invalid.write_text("{bad", encoding="utf-8")
            invalid_report = service.validate_benchmark_cases(invalid)
            unsafe = Path(temp) / "unsafe.json"
            unsafe.write_text(
                json.dumps({"cases": [{"case_id": "case_1", "expected": {"execution_allowed": False}, "fixtures": {"account_balance": "1000"}, "safety_policy": {"no_execution": True}}]}),
                encoding="utf-8",
            )
            unsafe_report = service.validate_benchmark_cases(unsafe)
            bad_counts = service.validate_benchmark_report({"total_cases": 2, "passed": 2, "warned": 1, "failed": 0, "skipped": 0, "pass_rate": 0.5, "execution_allowed": False})

        self.assertEqual(missing.status, "WARN")
        self.assertEqual(invalid_report.status, "FAIL")
        self.assertIn(unsafe_report.status, {"FAIL", "CRITICAL"})
        self.assertEqual(bad_counts.status, "FAIL")

    def test_replay_missing_fixture_and_policy_execution_safe(self):
        missing = SystemHardeningService().validate_replay_case({"replay_id": "r1", "replay_policy": {"no_execution": True}})
        unsafe = SystemHardeningService().validate_replay_case({"replay_id": "r2", "replay_policy": {"no_execution": False}})

        self.assertEqual(missing.status, "WARN")
        self.assertEqual(unsafe.status, "CRITICAL")
        self.assertTrue(unsafe.execution_allowed)

    def test_analytics_zero_annotations_no_division_error(self):
        report = ReviewAnalyticsEngine(registry_entries=[registry_entry()], annotations=[]).compute()

        self.assertEqual(report.coverage.annotation_coverage_rate, 0.0)
        self.assertEqual(report.safety.safety_issue_rate, 0.0)
        self.assertFalse(report.execution_allowed)

    def test_human_review_corrupt_annotation_line_quarantined_and_locked_append_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            annotation_path = Path(temp) / "annotations.jsonl"
            write_jsonl(annotation_path, ["{bad json"])
            service = SystemHardeningService(Path(temp) / "q", Path(temp) / "d")
            report = service.validate_jsonl(annotation_path, component="HUMAN_REVIEW", required_fields={"annotation_id"}, id_field="annotation_id")
            quarantined = service.quarantine_jsonl_records(annotation_path, [1], reason="corrupt annotation")
            store = HumanReviewStore(
                annotation_path=Path(temp) / "clean_annotations.jsonl",
                workflow_state_path=Path(temp) / "states.json",
                annotated_version_path=Path(temp) / "versions.json",
                export_dir=Path(temp) / "exports",
                persistence_store=EvaluationPersistenceStore(Path(temp) / "registry.jsonl", Path(temp) / "manifest.json", Path(temp) / "exports"),
            )
            entry = registry_entry()
            annotation = annotation_from_registry_entry(entry, reviewer_id="r", task_id="task_1", locked=True)
            saved = store.save_annotation(annotation)
            duplicate = store.save_annotation(annotation)

        self.assertEqual(report.status, "FAIL")
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(saved.status, "SAVED")
        self.assertIn(duplicate.status, {"LOCKED", "SKIPPED_DUPLICATE"})

    def test_safe_error_envelope_for_provider_and_streaming(self):
        provider = SystemHardeningService().normalize_error("provider", "request", TimeoutError("provider timeout api_key=secret"), retryable=True, fallback_used="safe_error_artifact")
        streaming = SystemHardeningService().normalize_error("streaming", "read", RuntimeError("stream interrupted"))

        self.assertEqual(provider.error_type, "TimeoutError")
        self.assertTrue(provider.retryable)
        self.assertNotIn("secret", provider.technical_summary.lower())
        self.assertFalse(streaming.execution_allowed)

    def test_recovery_plan_is_non_destructive_by_default_and_apply_skips_quarantine_without_permission(self):
        service = SystemHardeningService()
        report = service._report(["x"], [service._issue("ERROR", "PERSISTENCE_STORE", "x:1", "corrupt JSONL line detected")], 0.0)
        plan = service.plan_recovery(report)
        result = service.apply_recovery(plan)

        self.assertTrue(plan.actions)
        self.assertEqual(plan.destructive_actions_count, 0)
        self.assertFalse(plan.requires_confirmation)
        self.assertTrue(all(not action.destructive for action in plan.actions))
        self.assertEqual(result.status, "SKIPPED")

    def test_diagnostic_export_excludes_raw_full_answer_secrets_account_order_mt5_and_trade_fields(self):
        service = SystemHardeningService()
        report = service._report(
            ["x"],
            [
                service._issue(
                    "ERROR",
                    "PERSISTENCE_STORE",
                    "raw_prompt",
                    "api_key=sk-secretsecretsecret account_balance=100 order_id=1 mt5_password=abc entry_price=1 stop_loss=2 take_profit=3 lot_size=4 account_risk_percent=5 final_answer_text",
                    safety_relevant=True,
                )
            ],
            0.0,
        )
        with tempfile.TemporaryDirectory() as temp:
            diagnostic = service.export_diagnostic_report(report, out_dir=Path(temp))
            blob = Path(diagnostic.diagnostics_path).read_text(encoding="utf-8").lower()

        for forbidden in [
            "sk-secretsecretsecret",
            "account_balance=100",
            "order_id=1",
            "mt5_password=abc",
            "entry_price=1",
            "stop_loss=2",
            "take_profit=3",
            "lot_size=4",
            "account_risk_percent=5",
            "final_answer_text",
        ]:
            self.assertNotIn(forbidden, blob)

    def test_hardening_does_not_mutate_valid_registry_or_final_answer_or_create_evidence_item(self):
        entry = registry_entry()
        before = copy.deepcopy(entry.as_dict())
        final_answer = {"final_answer_sha256": "abc123", "excerpt": "safe advisory summary"}
        final_before = copy.deepcopy(final_answer)
        service = SystemHardeningService()

        report = service.validate_dashboard_state([entry], runtime_artifacts={"final_answer_artifact": final_answer, "compliance_result": {"status": "PASS"}, "answer_completeness": {"status": "PASS"}})
        blob = json.dumps(report.as_dict(), ensure_ascii=False)

        self.assertEqual(entry.as_dict(), before)
        self.assertEqual(final_answer, final_before)
        self.assertNotIn("EvidenceItem", blob)
        self.assertFalse(report.execution_allowed)

    def test_dashboard_health_view_model_works_with_temp_stores(self):
        with tempfile.TemporaryDirectory() as temp:
            registry = EvaluationRegistry([registry_entry()])
            persistence = EvaluationPersistenceStore(Path(temp) / "registry.jsonl", Path(temp) / "versions.json", Path(temp) / "exports")
            human = HumanReviewStore(
                annotation_path=Path(temp) / "reviews.jsonl",
                workflow_state_path=Path(temp) / "states.json",
                annotated_version_path=Path(temp) / "annotated_versions.json",
                export_dir=Path(temp) / "review_exports",
                persistence_store=persistence,
            )
            service = EvaluationDashboardService(registry, persistence, human)
            report, plan = service.system_health_report()

        self.assertIsInstance(report, SystemIntegrityReport)
        self.assertIsInstance(plan, RecoveryPlan)
        self.assertFalse(report.execution_allowed)
        self.assertFalse(plan.execution_allowed)


if __name__ == "__main__":
    unittest.main()
