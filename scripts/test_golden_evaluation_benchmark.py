import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.agents.golden_benchmark import (  # noqa: E402
    DEFAULT_GOLDEN_CASES_PATH,
    GoldenBenchmarkCase,
    GoldenBenchmarkReport,
    GoldenBenchmarkResult,
    GoldenBenchmarkRunner,
)


def load_cases():
    return GoldenBenchmarkRunner.load_cases(DEFAULT_GOLDEN_CASES_PATH)


def case(case_id):
    return copy.deepcopy(next(item for item in load_cases() if item.case_id == case_id))


def result_fields(result):
    return {item["field"] for item in result.mismatches}


class GoldenEvaluationBenchmarkTests(unittest.TestCase):
    def test_case_result_and_report_schema(self):
        benchmark_case = case("golden_static_book_price_action")
        result = GoldenBenchmarkRunner.run_case(benchmark_case)
        report = GoldenBenchmarkRunner.run_all([benchmark_case])

        self.assertIsInstance(benchmark_case, GoldenBenchmarkCase)
        self.assertIsInstance(result, GoldenBenchmarkResult)
        self.assertIsInstance(report, GoldenBenchmarkReport)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.pass_rate, 1.0)
        self.assertFalse(report.execution_allowed)

    def test_load_benchmark_cases_from_json_and_all_canonical_pass(self):
        cases = load_cases()
        report = GoldenBenchmarkRunner.run_all(cases)

        self.assertEqual(len(cases), 10)
        self.assertEqual(report.total_cases, 10)
        self.assertEqual(report.passed, 10)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.pass_rate, 1.0)
        self.assertFalse(report.execution_allowed)
        self.assertIn("static_book", report.coverage_summary["case_family_counts"])
        self.assertIn("analytics_quality", report.coverage_summary["case_family_counts"])

    def test_static_macro_market_multi_controlled_safety_cases_pass(self):
        ids = [
            "golden_static_book_price_action",
            "golden_macro_report_cpi_summary",
            "golden_macro_market_impact_xauusd",
            "golden_market_state_xauusd",
            "golden_multi_intent_macro_static",
            "golden_controlled_failure_missing_source",
            "golden_safety_boundary_no_execution",
        ]

        results = {case_id: GoldenBenchmarkRunner.run_case(case(case_id)) for case_id in ids}

        self.assertTrue(all(result.status == "PASS" for result in results.values()))
        self.assertIn("controlled_failure_expected", results["golden_controlled_failure_missing_source"].passed_checks)
        self.assertIn("safety_boundary", results["golden_safety_boundary_no_execution"].passed_checks)

    def test_dashboard_persistence_human_review_analytics_cases_pass(self):
        ids = [
            "golden_dashboard_evaluation_chain",
            "golden_persistence_reload",
            "golden_human_review_analytics",
        ]

        results = {case_id: GoldenBenchmarkRunner.run_case(case(case_id)) for case_id in ids}

        self.assertTrue(all(result.status == "PASS" for result in results.values()))
        self.assertIn("evaluation_records_expected", results["golden_dashboard_evaluation_chain"].passed_checks)
        self.assertIn("persistence_expected", results["golden_persistence_reload"].passed_checks)
        self.assertIn("analytics_expected", results["golden_human_review_analytics"].passed_checks)

    def test_multi_intent_task_leakage_produces_fail(self):
        benchmark_case = case("golden_multi_intent_macro_static")
        task_2 = benchmark_case.fixtures["runtime_artifacts"]["tasks"][1]
        task_2["symbol"] = "XAUUSD"
        task_2["source_refs"].append("market_snapshot:XAUUSD")

        result = GoldenBenchmarkRunner.run_case(benchmark_case)

        self.assertEqual(result.status, "FAIL")
        self.assertIn("task_scope", result_fields(result))

    def test_static_book_task_with_market_agent_produces_fail(self):
        benchmark_case = case("golden_static_book_price_action")
        benchmark_case.fixtures["runtime_artifacts"]["tasks"][0]["agent_refs"].append("MarketContextAgent")

        result = GoldenBenchmarkRunner.run_case(benchmark_case)

        self.assertEqual(result.status, "FAIL")
        self.assertIn("agents_forbidden", result_fields(result))
        self.assertIn("static_book_market_agents", result_fields(result))

    def test_missing_and_forbidden_source_refs_fail(self):
        missing = case("golden_static_book_price_action")
        missing.fixtures["runtime_artifacts"]["tasks"][0]["source_refs"] = []
        forbidden = case("golden_multi_intent_macro_static")
        forbidden.fixtures["runtime_artifacts"]["tasks"][0]["source_refs"].append("fabricated_source")

        missing_result = GoldenBenchmarkRunner.run_case(missing)
        forbidden_result = GoldenBenchmarkRunner.run_case(forbidden)

        self.assertEqual(missing_result.status, "FAIL")
        self.assertIn("source_refs_required", result_fields(missing_result))
        self.assertEqual(forbidden_result.status, "FAIL")
        self.assertIn("source_refs_forbidden", result_fields(forbidden_result))
        self.assertIn("fabricated_source", result_fields(forbidden_result))

    def test_missing_and_forbidden_agents_fail(self):
        missing = case("golden_market_state_xauusd")
        missing.fixtures["runtime_artifacts"]["tasks"][0]["agent_refs"].remove("RiskAgent")
        forbidden = case("golden_static_book_price_action")
        forbidden.fixtures["runtime_artifacts"]["tasks"][0]["agent_refs"].append("StrategyAgent")

        missing_result = GoldenBenchmarkRunner.run_case(missing)
        forbidden_result = GoldenBenchmarkRunner.run_case(forbidden)

        self.assertEqual(missing_result.status, "FAIL")
        self.assertIn("agents_required", result_fields(missing_result))
        self.assertEqual(forbidden_result.status, "FAIL")
        self.assertIn("agents_forbidden", result_fields(forbidden_result))

    def test_safety_boundary_fails_for_prohibited_output_and_execution_allowed_true(self):
        unsafe = case("golden_safety_boundary_no_execution")
        unsafe.fixtures["final_answer_artifact"]["final_answer_excerpt"] = "buy now with entry marker and send order"
        execution = case("golden_market_state_xauusd")
        execution.fixtures["runtime_artifacts"]["execution_allowed"] = True

        unsafe_result = GoldenBenchmarkRunner.run_case(unsafe)
        execution_result = GoldenBenchmarkRunner.run_case(execution)

        self.assertEqual(unsafe_result.status, "FAIL")
        self.assertTrue({"final_answer_forbidden_markers", "safety_boundary"} & result_fields(unsafe_result))
        self.assertEqual(execution_result.status, "FAIL")
        self.assertIn("execution_allowed", result_fields(execution_result))

    def test_controlled_failure_and_fabricated_source_marker(self):
        controlled = GoldenBenchmarkRunner.run_case(case("golden_controlled_failure_missing_source"))
        fabricated = case("golden_controlled_failure_missing_source")
        fabricated.fixtures["runtime_artifacts"]["tasks"][0]["source_refs"] = ["unknown_source"]

        fabricated_result = GoldenBenchmarkRunner.run_case(fabricated)

        self.assertEqual(controlled.status, "PASS")
        self.assertEqual(fabricated_result.status, "FAIL")
        self.assertIn("source_refs_forbidden", result_fields(fabricated_result))
        self.assertIn("fabricated_source", result_fields(fabricated_result))

    def test_fixture_and_final_answer_are_not_mutated_and_no_evidence_item_created(self):
        benchmark_case = case("golden_market_state_xauusd")
        before = copy.deepcopy(benchmark_case.as_dict())
        final_before = copy.deepcopy(benchmark_case.fixtures["final_answer_artifact"])

        result = GoldenBenchmarkRunner.run_case(benchmark_case)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(benchmark_case.as_dict(), before)
        self.assertEqual(benchmark_case.fixtures["final_answer_artifact"], final_before)
        self.assertNotIn("EvidenceItem", json.dumps(result.as_dict(), ensure_ascii=False))

    def test_no_provider_retrieval_market_mt5_account_calls_in_safety_summary(self):
        result = GoldenBenchmarkRunner.run_case(case("golden_market_state_xauusd"))

        self.assertTrue(result.safety_summary["no_provider_calls"])
        self.assertTrue(result.safety_summary["no_retrieval_calls"])
        self.assertTrue(result.safety_summary["no_market_calls"])
        self.assertTrue(result.safety_summary["no_execution"])
        self.assertTrue(result.safety_summary["no_mt5"])
        self.assertTrue(result.safety_summary["no_account_data"])
        self.assertFalse(result.safety_summary["execution_allowed"])

    def test_json_report_export_is_safe_and_validates(self):
        with tempfile.TemporaryDirectory() as temp:
            report = GoldenBenchmarkRunner.run_all(load_cases())
            out = Path(temp) / "golden_report.json"
            export = GoldenBenchmarkRunner.export_report(report, out)
            validation = GoldenBenchmarkRunner.validate_report(report)
            blob = out.read_text(encoding="utf-8").lower()

        self.assertEqual(export["status"], "EXPORTED")
        self.assertEqual(validation["status"], "PASS")
        self.assertIn("golden_benchmark", blob)
        for forbidden in [
            "raw_prompt",
            "full_final_answer",
            "final_answer_text",
            "api_key",
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

    def test_report_pass_rate_and_case_family_coverage_with_failure(self):
        passing = case("golden_static_book_price_action")
        failing = case("golden_market_state_xauusd")
        failing.fixtures["runtime_artifacts"]["tasks"][0]["agent_refs"] = []

        report = GoldenBenchmarkRunner.run_all([passing, failing])

        self.assertEqual(report.total_cases, 2)
        self.assertEqual(report.passed, 1)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.pass_rate, 0.5)
        self.assertEqual(report.failed_case_ids, ["golden_market_state_xauusd"])
        self.assertEqual(report.coverage_summary["case_family_counts"]["static_book"], 1)
        self.assertEqual(report.coverage_summary["case_family_counts"]["market_state"], 1)

    def test_cli_smoke_runs_without_api_keys_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "cli_report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "run_golden_benchmark.py"),
                    "--cases",
                    str(PROJECT_ROOT / DEFAULT_GOLDEN_CASES_PATH),
                    "--out",
                    str(out),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
            report_exists = out.exists()

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(report_exists)
        self.assertEqual(payload["status"], "EXPORTED")
        self.assertEqual(payload["pass_rate"], 1.0)
        self.assertFalse(payload["execution_allowed"])

    def test_artifact_mode_accepts_runtime_artifacts_without_live_calls(self):
        base = case("golden_macro_market_impact_xauusd")
        artifact_case = GoldenBenchmarkCase(
            case_id="artifact_mode_macro_impact",
            name="Artifact mode macro impact",
            case_family="macro_market_impact",
            expected=copy.deepcopy(base.expected),
            fixtures={
                "runtime_artifacts": copy.deepcopy(base.fixtures["runtime_artifacts"]),
                "final_answer_artifact": copy.deepcopy(base.fixtures["final_answer_artifact"]),
            },
        )

        result = GoldenBenchmarkRunner.run_case(artifact_case)

        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.safety_summary["no_provider_calls"])
        self.assertFalse(result.safety_summary["execution_allowed"])

    def test_execution_allowed_false_preserved_for_all_canonical_cases(self):
        report = GoldenBenchmarkRunner.run_all(load_cases())

        self.assertFalse(report.execution_allowed)
        self.assertTrue(all(not result["safety_summary"]["execution_allowed"] for result in report.results))


if __name__ == "__main__":
    unittest.main(verbosity=2)
