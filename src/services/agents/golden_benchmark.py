from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_persistence import UNSAFE_FIELD_NAMES
from src.services.agents.evaluation_registry import REGISTRY_SAFETY_PATTERNS, SECRET_PATTERNS


GOLDEN_BENCHMARK_VERSION = "golden_benchmark.v1"
DEFAULT_GOLDEN_CASES_PATH = Path("data") / "evaluations" / "benchmarks" / "golden_cases.v1.json"
DEFAULT_GOLDEN_REPORT_DIR = Path("data") / "evaluations" / "benchmarks" / "reports"
BENCHMARK_CASE_FAMILIES = {
    "static_book",
    "macro_report",
    "macro_market_impact",
    "market_state",
    "multi_intent",
    "controlled_failure",
    "safety_boundary",
    "dashboard_evaluation",
    "persistence_review",
    "analytics_quality",
}
BENCHMARK_RESULT_STATUSES = {"PASS", "WARN", "FAIL", "SKIPPED"}
MARKET_AGENT_TYPES = {"MarketContextAgent", "StrategyAgent", "RiskAgent", "StrategyRiskConsistencyAgent"}
STATIC_INTENT_FAMILIES = {"book_concept_explanation", "static_explanation", "static_knowledge"}
ABSTRACT_FORBIDDEN_MARKERS = {"prohibited_trading_output", "execution_language", "position_sizing_output"}


@dataclass
class GoldenBenchmarkCase:
    case_id: str
    name: str
    description: str = ""
    query: str = ""
    case_family: str = ""
    expected: Dict[str, Any] = field(default_factory=dict)
    fixtures: Dict[str, Any] = field(default_factory=dict)
    safety_policy: Dict[str, bool] = field(
        default_factory=lambda: {
            "no_provider_calls": True,
            "no_retrieval_calls": True,
            "no_market_calls": True,
            "no_execution": True,
            "no_mt5": True,
            "no_account_data": True,
        }
    )

    def as_dict(self, include_fixtures: bool = True) -> Dict[str, Any]:
        data = {
            "case_id": self.case_id,
            "name": self.name,
            "description": self.description,
            "query": self.query,
            "case_family": self.case_family,
            "expected": copy.deepcopy(self.expected),
            "safety_policy": dict(self.safety_policy),
        }
        if include_fixtures:
            data["fixtures"] = copy.deepcopy(self.fixtures)
        return data


@dataclass
class GoldenBenchmarkResult:
    case_id: str
    status: str = "PASS"
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "mismatches": list(self.mismatches),
            "passed_checks": list(self.passed_checks),
            "failed_checks": list(self.failed_checks),
            "warnings": list(self.warnings),
            "safety_summary": dict(self.safety_summary),
            "latency_ms": self.latency_ms,
        }


@dataclass
class GoldenBenchmarkReport:
    report_id: str
    created_at: str
    benchmark_version: str = GOLDEN_BENCHMARK_VERSION
    total_cases: int = 0
    passed: int = 0
    warned: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    failed_case_ids: List[str] = field(default_factory=list)
    warning_case_ids: List[str] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    coverage_summary: Dict[str, Any] = field(default_factory=dict)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    regression_summary: Dict[str, Any] = field(default_factory=dict)
    execution_allowed: bool = False
    payload_chars: int = 0
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "benchmark_version": self.benchmark_version,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate": self.pass_rate,
            "failed_case_ids": list(self.failed_case_ids),
            "warning_case_ids": list(self.warning_case_ids),
            "results": list(self.results),
            "coverage_summary": dict(self.coverage_summary),
            "safety_summary": dict(self.safety_summary),
            "regression_summary": dict(self.regression_summary),
            "execution_allowed": self.execution_allowed,
            "payload_chars": self.payload_chars,
            "latency_ms": self.latency_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True, default=str)


class GoldenBenchmarkRunner:
    @classmethod
    def load_cases(cls, path: str | Path | None = None) -> List[GoldenBenchmarkCase]:
        case_path = Path(path or DEFAULT_GOLDEN_CASES_PATH)
        data = json.loads(case_path.read_text(encoding="utf-8"))
        items = data.get("cases") if isinstance(data, Mapping) else data
        return [case_from_mapping(item) for item in items or []]

    @classmethod
    def run_case(cls, case: GoldenBenchmarkCase | Mapping[str, Any]) -> GoldenBenchmarkResult:
        started = time.perf_counter()
        original = copy.deepcopy(case.as_dict() if isinstance(case, GoldenBenchmarkCase) else dict(case))
        benchmark_case = case if isinstance(case, GoldenBenchmarkCase) else case_from_mapping(case)
        mismatches: List[Dict[str, Any]] = []
        passed: List[str] = []
        warnings: List[str] = []
        context = _context(benchmark_case.fixtures)

        if benchmark_case.case_family not in BENCHMARK_CASE_FAMILIES:
            _mismatch(mismatches, "case_family", "known_family", "unknown_family")
        else:
            passed.append("case_family")

        cls._validate_intent_tasks(benchmark_case, context, mismatches, passed)
        cls._validate_sources(benchmark_case, context, mismatches, passed)
        cls._validate_agents(benchmark_case, context, mismatches, passed)
        cls._validate_safety(benchmark_case, context, mismatches, passed)
        cls._validate_answer_artifact(benchmark_case, context, mismatches, passed)
        cls._validate_evaluation_artifacts(benchmark_case, context, mismatches, passed)
        cls._validate_persistence_review_analytics(benchmark_case, context, mismatches, passed)
        cls._validate_no_mutation_no_evidence_item(benchmark_case, original, mismatches, passed)

        safety_summary = _safety_summary(benchmark_case, context)
        if not all(safety_summary.get(key) for key in ("no_provider_calls", "no_retrieval_calls", "no_market_calls", "no_execution", "no_mt5", "no_account_data")):
            _mismatch(mismatches, "safety_policy", "all_disabled", "unsafe_policy")
        if safety_summary.get("execution_allowed"):
            _mismatch(mismatches, "execution_allowed", False, True)

        status = "FAIL" if mismatches else ("WARN" if warnings else "PASS")
        failed_checks = _ordered_unique(str(item.get("field") or "unknown") for item in mismatches)
        result = GoldenBenchmarkResult(
            case_id=benchmark_case.case_id,
            status=status,
            mismatches=mismatches,
            passed_checks=_ordered_unique(passed),
            failed_checks=failed_checks,
            warnings=warnings,
            safety_summary=safety_summary,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        print(
            "[GoldenBenchmark] "
            f"action=run_case case_id={result.case_id} status={result.status} "
            f"checks={len(result.passed_checks) + len(result.failed_checks)} mismatches={len(result.mismatches)} "
            f"latency_ms={result.latency_ms}"
        )
        return result

    @classmethod
    def run_all(cls, cases: Sequence[GoldenBenchmarkCase | Mapping[str, Any]]) -> GoldenBenchmarkReport:
        started = time.perf_counter()
        normalized = [case if isinstance(case, GoldenBenchmarkCase) else case_from_mapping(case) for case in cases]
        results = [cls.run_case(case) for case in normalized]
        passed = sum(1 for item in results if item.status == "PASS")
        warned = sum(1 for item in results if item.status == "WARN")
        failed = sum(1 for item in results if item.status == "FAIL")
        skipped = sum(1 for item in results if item.status == "SKIPPED")
        coverage = _coverage_summary(normalized, results)
        safety = _aggregate_safety(results)
        report_id = f"golden_benchmark:{_hash_payload([[case.case_id for case in normalized], [item.status for item in results]])[:16]}"
        report = GoldenBenchmarkReport(
            report_id=report_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            total_cases=len(results),
            passed=passed,
            warned=warned,
            failed=failed,
            skipped=skipped,
            pass_rate=_rate(passed, len(results)),
            failed_case_ids=[item.case_id for item in results if item.status == "FAIL"],
            warning_case_ids=[item.case_id for item in results if item.status == "WARN"],
            results=[item.as_dict() for item in results],
            coverage_summary=coverage,
            safety_summary=safety,
            regression_summary={
                "task_leakage_failures": sum(1 for item in results for mismatch in item.mismatches if mismatch.get("field") == "task_scope"),
                "source_failures": sum(1 for item in results for mismatch in item.mismatches if "source" in str(mismatch.get("field"))),
                "agent_failures": sum(1 for item in results for mismatch in item.mismatches if "agent" in str(mismatch.get("field"))),
                "safety_failures": sum(1 for item in results for mismatch in item.mismatches if mismatch.get("field") in {"execution_allowed", "safety_boundary", "final_answer_forbidden_markers"}),
            },
            execution_allowed=bool(safety.get("execution_allowed")),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        report.payload_chars = len(report.to_json())
        print(
            "[GoldenBenchmark] "
            f"action=run_all cases={report.total_cases} passed={report.passed} failed={report.failed} "
            f"warnings={report.warned} latency_ms={report.latency_ms}"
        )
        return report

    @classmethod
    def export_report(cls, report: GoldenBenchmarkReport | Mapping[str, Any], out_path: str | Path | None = None, format: str = "json") -> Dict[str, Any]:
        started = time.perf_counter()
        data = report.as_dict() if isinstance(report, GoldenBenchmarkReport) else dict(report)
        if format.lower() != "json":
            return {"status": "FAILED", "warnings": ["unsupported_format"], "latency_ms": _elapsed(started)}
        if _unsafe_warnings(data):
            return {"status": "REJECTED_UNSAFE", "warnings": _unsafe_warnings(data), "latency_ms": _elapsed(started)}
        target = Path(out_path) if out_path else DEFAULT_GOLDEN_REPORT_DIR / "latest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        target.write_text(text, encoding="utf-8")
        result = {"status": "EXPORTED", "export_path": str(target), "payload_chars": len(text), "latency_ms": _elapsed(started)}
        print(
            "[GoldenBenchmark] "
            f"action=export_report report_id={data.get('report_id', '')} payload_chars={result['payload_chars']} status={result['status']}"
        )
        return result

    @classmethod
    def validate_report(cls, report: GoldenBenchmarkReport | Mapping[str, Any]) -> Dict[str, Any]:
        data = report.as_dict() if isinstance(report, GoldenBenchmarkReport) else dict(report)
        warnings = _unsafe_warnings(data)
        status = "PASS" if not warnings and data.get("execution_allowed") is False else "FAIL"
        return {
            "status": status,
            "total_cases": int(data.get("total_cases") or 0),
            "failed": int(data.get("failed") or 0),
            "warnings": warnings,
            "execution_allowed": bool(data.get("execution_allowed")),
        }

    @staticmethod
    def _validate_intent_tasks(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        task_ids = sorted(context["tasks"])
        if "task_count" in expected:
            _check_equal(mismatches, passed, "task_count", expected["task_count"], len(task_ids))
        if expected.get("task_ids"):
            _check_set_contains(mismatches, passed, "task_ids", expected["task_ids"], task_ids)
        if expected.get("intent_families"):
            actual = _ordered_unique(task.get("intent_family", "") for task in context["tasks"].values())
            _check_set_contains(mismatches, passed, "intent_families", expected["intent_families"], actual)
        if int(expected.get("task_count") or 0) > 1:
            static_tasks = [task for task in context["tasks"].values() if task.get("intent_family") in STATIC_INTENT_FAMILIES]
            for task in static_tasks:
                leakage = _static_task_leakage(task)
                if leakage:
                    _mismatch(mismatches, "task_scope", "isolated_static_task", leakage)
                else:
                    passed.append(f"task_scope:{task.get('task_id')}")

    @staticmethod
    def _validate_sources(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        refs = context["source_refs"]
        if expected.get("source_refs_required"):
            for ref in expected["source_refs_required"]:
                if not _contains(refs, ref):
                    _mismatch(mismatches, "source_refs_required", "present", "missing")
                else:
                    passed.append("source_refs_required")
        if expected.get("source_refs_forbidden"):
            for ref in expected["source_refs_forbidden"]:
                if _contains(refs, ref):
                    _mismatch(mismatches, "source_refs_forbidden", "absent", "present")
                else:
                    passed.append("source_refs_forbidden")
        if any("fabricated" in ref.lower() or "unknown_source" in ref.lower() for ref in refs):
            _mismatch(mismatches, "fabricated_source", "absent", "present")
        else:
            passed.append("fabricated_source_absent")

    @staticmethod
    def _validate_agents(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        agents = context["agent_refs"]
        for agent in expected.get("agents_required") or []:
            if not _agent_present(agent, agents):
                _mismatch(mismatches, "agents_required", "present", "missing")
            else:
                passed.append("agents_required")
        for agent in expected.get("agents_forbidden") or []:
            if _agent_present(agent, agents):
                _mismatch(mismatches, "agents_forbidden", "absent", "present")
            else:
                passed.append("agents_forbidden")
        for task in context["tasks"].values():
            if task.get("intent_family") in STATIC_INTENT_FAMILIES:
                forbidden = sorted(set(task.get("agent_refs") or []) & MARKET_AGENT_TYPES)
                if forbidden:
                    _mismatch(mismatches, "static_book_market_agents", "absent", "present")
                else:
                    passed.append(f"static_book_agents:{task.get('task_id')}")

    @staticmethod
    def _validate_safety(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        execution_expected = expected.get("execution_allowed")
        if execution_expected is not None:
            _check_equal(mismatches, passed, "execution_allowed", bool(execution_expected), context["execution_allowed"])
        output_text = context["final_answer_text"]
        if expected.get("final_answer_forbidden_markers"):
            if _forbidden_output_present(output_text, expected["final_answer_forbidden_markers"]):
                _mismatch(mismatches, "final_answer_forbidden_markers", "absent", "present")
            else:
                passed.append("final_answer_forbidden_markers")
        if _forbidden_output_present(output_text, ABSTRACT_FORBIDDEN_MARKERS):
            _mismatch(mismatches, "safety_boundary", "safe_output", "prohibited_output")
        else:
            passed.append("safety_boundary")
        if expected.get("compliance_status"):
            _check_equal(mismatches, passed, "compliance_status", expected["compliance_status"], context["compliance_status"])

    @staticmethod
    def _validate_answer_artifact(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        if expected.get("final_answer_hash_required", True):
            if not context["final_answer_sha256"]:
                _mismatch(mismatches, "final_answer_sha256", "present", "missing")
            else:
                passed.append("final_answer_sha256")
        if expected.get("answer_completeness_status"):
            _check_equal(mismatches, passed, "answer_completeness_status", expected["answer_completeness_status"], context["answer_completeness_status"])
        for marker in expected.get("final_answer_required_markers") or []:
            if marker and marker.lower() not in context["final_answer_text"].lower():
                _mismatch(mismatches, "final_answer_required_markers", "present", "missing")
            else:
                passed.append("final_answer_required_markers")
        for key in expected.get("runtime_artifact_required_keys") or []:
            if key not in context["runtime_artifacts"]:
                _mismatch(mismatches, "runtime_artifact_required_keys", "present", "missing")
            else:
                passed.append("runtime_artifact_required_keys")
        for key in expected.get("runtime_artifact_forbidden_keys") or []:
            if key in context["runtime_artifacts"]:
                _mismatch(mismatches, "runtime_artifact_forbidden_keys", "absent", "present")
            else:
                passed.append("runtime_artifact_forbidden_keys")
        if expected.get("controlled_failure_expected") is not None:
            _check_equal(mismatches, passed, "controlled_failure_expected", bool(expected["controlled_failure_expected"]), context["controlled_failure"])

    @staticmethod
    def _validate_evaluation_artifacts(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        if "evaluation_records_expected" in expected:
            _check_equal(mismatches, passed, "evaluation_records_expected", bool(expected["evaluation_records_expected"]), bool(context["evaluation_records"]))
        if "dashboard_records_expected" in expected:
            _check_equal(mismatches, passed, "dashboard_records_expected", bool(expected["dashboard_records_expected"]), bool(context["registry_entries"]))
        for record_type in expected.get("record_types_required") or []:
            if record_type not in context["record_types"]:
                _mismatch(mismatches, "record_types_required", "present", "missing")
            else:
                passed.append("record_types_required")

    @staticmethod
    def _validate_persistence_review_analytics(case: GoldenBenchmarkCase, context: Dict[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        expected = case.expected
        if "persistence_expected" in expected:
            _check_equal(mismatches, passed, "persistence_expected", bool(expected["persistence_expected"]), bool(context["persisted_entries"]))
        if "human_review_expected" in expected:
            _check_equal(mismatches, passed, "human_review_expected", bool(expected["human_review_expected"]), bool(context["annotations"]))
        if "analytics_expected" in expected:
            _check_equal(mismatches, passed, "analytics_expected", bool(expected["analytics_expected"]), bool(context["analytics_report"]))
        if context["annotations"]:
            for annotation in context["annotations"]:
                if not annotation.get("registry_id") or not annotation.get("task_id") or not annotation.get("final_answer_sha256"):
                    _mismatch(mismatches, "human_review_binding", "registry_task_hash", "missing_binding")
                else:
                    passed.append("human_review_binding")
        if context["analytics_report"] and context["analytics_report"].get("execution_allowed"):
            _mismatch(mismatches, "analytics_execution_allowed", False, True)
        elif context["analytics_report"]:
            passed.append("analytics_execution_allowed")

    @staticmethod
    def _validate_no_mutation_no_evidence_item(case: GoldenBenchmarkCase, original: Mapping[str, Any], mismatches: List[Dict[str, Any]], passed: List[str]) -> None:
        current = case.as_dict()
        if current != original:
            _mismatch(mismatches, "fixture_mutation", "unchanged", "mutated")
        else:
            passed.append("fixture_not_mutated")
        if "EvidenceItem" in json.dumps(current, ensure_ascii=False, default=str):
            _mismatch(mismatches, "evidence_item_creation", "absent", "present")
        else:
            passed.append("no_evidence_item")


def case_from_mapping(data: Mapping[str, Any]) -> GoldenBenchmarkCase:
    return GoldenBenchmarkCase(
        case_id=str(data.get("case_id") or ""),
        name=str(data.get("name") or data.get("case_id") or ""),
        description=str(data.get("description") or ""),
        query=str(data.get("query") or ""),
        case_family=str(data.get("case_family") or ""),
        expected=copy.deepcopy(dict(data.get("expected") or {})),
        fixtures=copy.deepcopy(dict(data.get("fixtures") or {})),
        safety_policy=dict(data.get("safety_policy") or GoldenBenchmarkCase("", "").safety_policy),
    )


def _context(fixtures: Mapping[str, Any]) -> Dict[str, Any]:
    runtime = dict(fixtures.get("runtime_artifacts") or {})
    final = dict(fixtures.get("final_answer_artifact") or runtime.get("final_answer_artifact") or {})
    registry_entries = [dict(item) for item in fixtures.get("registry_entries") or []]
    journal_records = [dict(item) for item in fixtures.get("journal_records") or []]
    backtest_records = [dict(item) for item in fixtures.get("backtest_records") or []]
    paper_records = [dict(item) for item in fixtures.get("paper_records") or []]
    annotations = [dict(item) for item in fixtures.get("annotations") or []]
    persisted_entries = [dict(item) for item in fixtures.get("persisted_entries") or []]
    analytics_report = dict(fixtures.get("analytics_report") or {})
    tasks = _collect_tasks(runtime, registry_entries, journal_records)
    source_refs = _ordered_unique(ref for task in tasks.values() for ref in task.get("source_refs", []))
    agent_refs = _ordered_unique(ref for task in tasks.values() for ref in task.get("agent_refs", []))
    final_text = str(final.get("final_answer_excerpt") or final.get("answer_excerpt") or final.get("text") or "")
    execution_allowed = _any_execution_allowed([runtime, final, *registry_entries, *journal_records, *backtest_records, *paper_records, analytics_report])
    compliance = _first(
        [
            runtime.get("agent_answer_compliance", {}).get("status") if isinstance(runtime.get("agent_answer_compliance"), Mapping) else "",
            runtime.get("compliance_status"),
            final.get("compliance_status"),
            _first(record.get("validation_summary", {}).get("agent_answer_compliance") for record in journal_records if isinstance(record.get("validation_summary"), Mapping)),
        ]
    )
    completeness = _first(
        [
            runtime.get("answer_completeness", {}).get("status") if isinstance(runtime.get("answer_completeness"), Mapping) else "",
            runtime.get("answer_completeness_status"),
            final.get("answer_completeness_status"),
            _first(record.get("validation_summary", {}).get("answer_completeness_status") for record in journal_records if isinstance(record.get("validation_summary"), Mapping)),
        ]
    )
    controlled = bool(runtime.get("controlled_failure") or runtime.get("response_gate", {}).get("status") in {"CONTROLLED_FAILURE", "INSUFFICIENT_EVIDENCE"})
    evaluation_records = [*journal_records, *backtest_records, *paper_records]
    record_types = _ordered_unique(entry.get("record_type", "") for entry in registry_entries)
    return {
        "runtime_artifacts": runtime,
        "final_answer_artifact": final,
        "registry_entries": registry_entries,
        "journal_records": journal_records,
        "backtest_records": backtest_records,
        "paper_records": paper_records,
        "evaluation_records": evaluation_records,
        "record_types": record_types,
        "annotations": annotations,
        "persisted_entries": persisted_entries,
        "analytics_report": analytics_report,
        "tasks": tasks,
        "source_refs": source_refs,
        "agent_refs": agent_refs,
        "final_answer_text": final_text,
        "final_answer_sha256": str(final.get("sha256") or final.get("final_answer_sha256") or runtime.get("final_answer_sha256") or ""),
        "execution_allowed": execution_allowed,
        "compliance_status": str(compliance or ""),
        "answer_completeness_status": str(completeness or ""),
        "controlled_failure": controlled,
    }


def _collect_tasks(runtime: Mapping[str, Any], registry_entries: Sequence[Mapping[str, Any]], journal_records: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    tasks: Dict[str, Dict[str, Any]] = {}

    def ensure(task_id: str) -> Dict[str, Any]:
        task = tasks.setdefault(task_id, {"task_id": task_id, "intent_family": "", "symbol": "", "source_refs": [], "agent_refs": []})
        return task

    for item in runtime.get("tasks") or []:
        if isinstance(item, Mapping):
            task = ensure(str(item.get("task_id") or ""))
            task["intent_family"] = str(item.get("intent_family") or task["intent_family"])
            task["symbol"] = str(item.get("symbol") or task["symbol"])
            task["source_refs"] = _ordered_unique([*task["source_refs"], *[str(ref) for ref in item.get("source_refs") or []]])
            task["agent_refs"] = _ordered_unique([*task["agent_refs"], *[str(ref) for ref in item.get("agent_refs") or []]])
    for result in runtime.get("agent_runtime", {}).get("handoff", {}).get("agent_results", []) if isinstance(runtime.get("agent_runtime"), Mapping) else []:
        if isinstance(result, Mapping):
            task_id = str(result.get("parent_task_id") or result.get("task_id") or "")
            agent_type = str(result.get("agent_type") or "")
            if task_id and agent_type:
                task = ensure(task_id)
                task["agent_refs"] = _ordered_unique([*task["agent_refs"], agent_type])
    for entry in registry_entries:
        for item in entry.get("task_index") or []:
            if isinstance(item, Mapping):
                task = ensure(str(item.get("task_id") or ""))
                task["intent_family"] = str(item.get("intent_family") or task["intent_family"])
                task["symbol"] = str(item.get("symbol") or task["symbol"])
                task["source_refs"] = _ordered_unique([*task["source_refs"], *[str(ref) for ref in item.get("source_refs") or []]])
                task["agent_refs"] = _ordered_unique([*task["agent_refs"], *[str(ref) for ref in item.get("agent_refs") or []]])
    for record in journal_records:
        for review in record.get("task_reviews") or []:
            if isinstance(review, Mapping):
                task = ensure(str(review.get("task_id") or ""))
                task["intent_family"] = str(review.get("intent_family") or task["intent_family"])
        snapshots = record.get("compact_task_analysis_snapshots") if isinstance(record.get("compact_task_analysis_snapshots"), Mapping) else {}
        for task_id, snapshot in snapshots.items():
            if isinstance(snapshot, Mapping):
                task = ensure(str(task_id))
                task["intent_family"] = str(snapshot.get("intent_family") or task["intent_family"])
                task["symbol"] = str(snapshot.get("symbol") or task["symbol"])
                task["source_refs"] = _ordered_unique([*task["source_refs"], *[str(ref) for ref in snapshot.get("allowed_source_refs") or []]])
                for agent_key, agent_name in (("market_context", "MarketContextAgent"), ("strategy", "StrategyAgent"), ("risk", "RiskAgent"), ("consistency", "StrategyRiskConsistencyAgent")):
                    if snapshot.get(agent_key):
                        task["agent_refs"] = _ordered_unique([*task["agent_refs"], agent_name])
    return {key: value for key, value in tasks.items() if key}


def _safety_summary(case: GoldenBenchmarkCase, context: Mapping[str, Any]) -> Dict[str, Any]:
    policy = case.safety_policy
    return {
        "no_provider_calls": bool(policy.get("no_provider_calls", True)),
        "no_retrieval_calls": bool(policy.get("no_retrieval_calls", True)),
        "no_market_calls": bool(policy.get("no_market_calls", True)),
        "no_execution": bool(policy.get("no_execution", True)),
        "no_mt5": bool(policy.get("no_mt5", True)),
        "no_account_data": bool(policy.get("no_account_data", True)),
        "execution_allowed": bool(context.get("execution_allowed")),
    }


def _static_task_leakage(task: Mapping[str, Any]) -> str:
    symbol = str(task.get("symbol") or "")
    refs = " ".join(str(ref) for ref in task.get("source_refs") or [])
    agents = set(str(agent) for agent in task.get("agent_refs") or [])
    if symbol:
        return "static_task_symbol_leakage"
    if any(marker in refs for marker in ("XAUUSD", "market_snapshot", "ohlcv:")):
        return "static_task_source_leakage"
    if agents & MARKET_AGENT_TYPES:
        return "static_task_agent_leakage"
    return ""


def _agent_present(agent: Any, agents: Sequence[str]) -> bool:
    if isinstance(agent, Mapping):
        agent_type = str(agent.get("agent_type") or agent.get("name") or "")
    else:
        agent_type = str(agent)
    return any(agent_type == value or agent_type in value for value in agents)


def _forbidden_output_present(text: str, markers: Iterable[str]) -> bool:
    lowered = text.lower()
    for marker in markers:
        marker_text = str(marker)
        if marker_text in ABSTRACT_FORBIDDEN_MARKERS:
            if any(pattern.search(text) for pattern in REGISTRY_SAFETY_PATTERNS):
                return True
        elif marker_text and marker_text.lower() in lowered:
            return True
    return False


def _any_execution_allowed(values: Sequence[Any]) -> bool:
    for value in values:
        if isinstance(value, Mapping):
            if value.get("execution_allowed") is True:
                return True
            safety = value.get("safety_summary") if isinstance(value.get("safety_summary"), Mapping) else value.get("safety_index")
            if isinstance(safety, Mapping) and safety.get("execution_allowed") is True:
                return True
            if _any_execution_allowed(list(value.values())):
                return True
        elif isinstance(value, list):
            if _any_execution_allowed(value):
                return True
    return False


def _check_equal(mismatches: List[Dict[str, Any]], passed: List[str], field: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        _mismatch(mismatches, field, expected, actual)
    else:
        passed.append(field)


def _check_set_contains(mismatches: List[Dict[str, Any]], passed: List[str], field: str, expected: Iterable[str], actual: Iterable[str]) -> None:
    missing = [str(item) for item in expected if str(item) not in set(str(value) for value in actual)]
    if missing:
        _mismatch(mismatches, field, "present", "missing")
    else:
        passed.append(field)


def _mismatch(mismatches: List[Dict[str, Any]], field: str, expected: Any, actual: Any) -> None:
    mismatches.append({"field": field, "expected": _safe_mismatch_value(expected), "actual": _safe_mismatch_value(actual)})


def _safe_mismatch_value(value: Any) -> Any:
    if isinstance(value, str) and _forbidden_output_present(value, ABSTRACT_FORBIDDEN_MARKERS):
        return "[REDACTED_UNSAFE_DETAIL]"
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            value = pattern.sub("[REDACTED_SECRET]", value)
        return value
    return value


def _contains(values: Iterable[str], needle: str) -> bool:
    return any(str(needle).lower() in str(value).lower() for value in values)


def _coverage_summary(cases: Sequence[GoldenBenchmarkCase], results: Sequence[GoldenBenchmarkResult]) -> Dict[str, Any]:
    by_family: Dict[str, Dict[str, int]] = {}
    status_by_id = {result.case_id: result.status for result in results}
    for case in cases:
        bucket = by_family.setdefault(case.case_family, {"total": 0, "passed": 0, "failed": 0, "warned": 0, "skipped": 0})
        bucket["total"] += 1
        status = status_by_id.get(case.case_id, "SKIPPED").lower()
        key = "warned" if status == "warn" else f"{status}ed" if status in {"pass", "fail", "skip"} else status
        if key == "passed":
            bucket["passed"] += 1
        elif key == "failed":
            bucket["failed"] += 1
        elif key == "skipped":
            bucket["skipped"] += 1
        elif key == "warned":
            bucket["warned"] += 1
    return {"case_family_counts": {family: data["total"] for family, data in by_family.items()}, "by_family": by_family}


def _aggregate_safety(results: Sequence[GoldenBenchmarkResult]) -> Dict[str, Any]:
    return {
        "no_provider_calls": all(result.safety_summary.get("no_provider_calls") for result in results),
        "no_retrieval_calls": all(result.safety_summary.get("no_retrieval_calls") for result in results),
        "no_market_calls": all(result.safety_summary.get("no_market_calls") for result in results),
        "no_execution": all(result.safety_summary.get("no_execution") for result in results),
        "no_mt5": all(result.safety_summary.get("no_mt5") for result in results),
        "no_account_data": all(result.safety_summary.get("no_account_data") for result in results),
        "execution_allowed": any(result.safety_summary.get("execution_allowed") for result in results),
    }


def _unsafe_warnings(value: Any) -> List[str]:
    warnings: List[str] = []
    keys = {key.lower() for key in _mapping_keys(value)}
    if keys & UNSAFE_FIELD_NAMES:
        warnings.append("unsafe_field")
    text = " ".join(_string_values(value))
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        warnings.append("secret_like_value")
    if any(pattern.search(text) for pattern in REGISTRY_SAFETY_PATTERNS):
        warnings.append("prohibited_trading_or_execution_text")
    return _ordered_unique(warnings)


def _mapping_keys(value: Any) -> List[str]:
    if isinstance(value, Mapping):
        output = [str(key) for key in value.keys()]
        for item in value.values():
            output.extend(_mapping_keys(item))
        return output
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            output.extend(_mapping_keys(item))
        return output
    return []


def _string_values(value: Any) -> List[str]:
    if isinstance(value, Mapping):
        output: List[str] = []
        for item in value.values():
            output.extend(_string_values(item))
        return output
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            output.extend(_string_values(item))
        return output
    if isinstance(value, str):
        return [value]
    return []


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _first(values: Iterable[Any]) -> Any:
    for value in values:
        if value:
            return value
    return ""


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic golden evaluation benchmark fixtures.")
    parser.add_argument("--cases", default=str(DEFAULT_GOLDEN_CASES_PATH))
    parser.add_argument("--out", default=str(DEFAULT_GOLDEN_REPORT_DIR / "latest.json"))
    args = parser.parse_args(argv)
    cases = GoldenBenchmarkRunner.load_cases(args.cases)
    report = GoldenBenchmarkRunner.run_all(cases)
    export = GoldenBenchmarkRunner.export_report(report, args.out)
    print(
        json.dumps(
            {
                "status": export["status"],
                "report_id": report.report_id,
                "total_cases": report.total_cases,
                "passed": report.passed,
                "warned": report.warned,
                "failed": report.failed,
                "skipped": report.skipped,
                "pass_rate": report.pass_rate,
                "execution_allowed": report.execution_allowed,
                "export_path": export.get("export_path", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.failed == 0 and export["status"] == "EXPORTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
