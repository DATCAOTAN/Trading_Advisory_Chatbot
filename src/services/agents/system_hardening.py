from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_persistence import (
    DATASET_MANIFEST_SCHEMA_VERSION,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_REGISTRY_PATH,
    PERSISTENCE_SCHEMA_VERSION,
    UNSAFE_FIELD_NAMES,
)
from src.services.agents.evaluation_registry import (
    EvaluationRegistryEntry,
    REGISTRY_SAFETY_PATTERNS,
    SECRET_PATTERNS,
)
from src.services.agents.golden_benchmark import (
    DEFAULT_GOLDEN_CASES_PATH,
    GOLDEN_BENCHMARK_VERSION,
)
from src.services.agents.human_review import (
    ANNOTATED_DATASET_SCHEMA_VERSION,
    ANNOTATION_SCHEMA_VERSION,
    DEFAULT_ANNOTATED_VERSION_PATH,
    DEFAULT_ANNOTATION_PATH,
    DEFAULT_WORKFLOW_STATE_PATH,
)


DEFAULT_EVALUATION_BASE_DIR = Path("data") / "evaluations"
DEFAULT_QUARANTINE_DIR = DEFAULT_EVALUATION_BASE_DIR / "quarantine"
DEFAULT_DIAGNOSTICS_DIR = DEFAULT_EVALUATION_BASE_DIR / "diagnostics"

ISSUE_SEVERITIES = {"INFO", "WARN", "ERROR", "CRITICAL"}
ISSUE_CATEGORIES = {
    "RUNTIME_ARTIFACT",
    "PERSISTENCE_STORE",
    "DASHBOARD_STATE",
    "BENCHMARK_CASE",
    "BENCHMARK_REPORT",
    "HUMAN_REVIEW",
    "ANALYTICS",
    "REPLAY",
    "STREAMING",
    "PROVIDER_ERROR_ARTIFACT",
    "SAFETY_BOUNDARY",
    "UNKNOWN",
}
REPORT_STATUSES = {"PASS", "WARN", "FAIL", "CRITICAL"}
RECOVERY_ACTION_TYPES = {
    "NOOP",
    "WARN_ONLY",
    "QUARANTINE_RECORD",
    "SKIP_RECORD",
    "REBUILD_INDEX_FROM_SAFE_RECORDS",
    "RELOAD_FROM_DISK",
    "FALLBACK_EMPTY_STATE",
    "MARK_NOT_APPLICABLE",
    "MARK_INCOMPLETE_CHAIN",
    "VALIDATE_ONLY",
    "EXPORT_DIAGNOSTIC_REPORT",
}

REQUIRED_REGISTRY_FIELDS = {
    "registry_id",
    "record_type",
    "request_id",
    "final_answer_sha256",
    "execution_allowed",
}
REQUIRED_ANNOTATION_FIELDS = {
    "annotation_id",
    "registry_id",
    "request_id",
    "final_answer_sha256",
    "task_id",
    "record_type",
    "execution_allowed",
}
RAW_TEXT_FIELD_NAMES = {
    "raw_prompt",
    "full_prompt",
    "hidden_prompt",
    "system_prompt",
    "developer_prompt",
    "raw_answer",
    "final_answer_text",
    "raw_final_answer",
    "full_final_answer",
    "document_text",
    "raw_document",
    "full_document",
}
ACCOUNT_EXECUTION_FIELD_NAMES = {
    "account_balance",
    "account_equity",
    "account_number",
    "order_id",
    "order_history",
    "open_position",
    "real_position",
    "mt5_credentials",
    "mt5_password",
    "broker_credentials",
    "broker_password",
}
TRADING_FIELD_NAMES = {
    "entry",
    "entry_price",
    "stop_loss",
    "sl",
    "take_profit",
    "tp",
    "lot",
    "lot_size",
    "position_size",
    "account_risk",
    "account_risk_percent",
}
UNSAFE_KEYS = {key.lower() for key in UNSAFE_FIELD_NAMES | RAW_TEXT_FIELD_NAMES | ACCOUNT_EXECUTION_FIELD_NAMES | TRADING_FIELD_NAMES}
STATIC_INTENTS = {"book_concept_explanation", "static_explanation", "static_knowledge"}
MARKET_AGENT_TYPES = {"MarketContextAgent", "StrategyAgent", "RiskAgent", "StrategyRiskConsistencyAgent"}
UNSAFE_ASSIGNMENT_PATTERNS = [
    re.compile(rf"\b{re.escape(key)}\s*[:=]\s*['\"]?[^'\"\s,;]+", re.IGNORECASE)
    for key in sorted(UNSAFE_KEYS, key=len, reverse=True)
]


@dataclass
class SystemIntegrityIssue:
    issue_id: str
    created_at: str
    severity: str
    category: str
    location: str = ""
    message: str = ""
    affected_ids: List[str] = field(default_factory=list)
    recoverable: bool = True
    safety_relevant: bool = False
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "created_at": self.created_at,
            "severity": self.severity,
            "category": self.category,
            "location": self.location,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "recoverable": self.recoverable,
            "safety_relevant": self.safety_relevant,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class SystemIntegrityReport:
    report_id: str
    created_at: str
    status: str = "PASS"
    checked_components: List[str] = field(default_factory=list)
    issues: List[SystemIntegrityIssue] = field(default_factory=list)
    issue_counts_by_severity: Dict[str, int] = field(default_factory=dict)
    issue_counts_by_category: Dict[str, int] = field(default_factory=dict)
    corrupt_records_count: int = 0
    quarantined_records_count: int = 0
    missing_artifacts_count: int = 0
    unsafe_artifacts_count: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "status": self.status,
            "checked_components": list(self.checked_components),
            "issues": [issue.as_dict() for issue in self.issues],
            "issue_counts_by_severity": dict(self.issue_counts_by_severity),
            "issue_counts_by_category": dict(self.issue_counts_by_category),
            "corrupt_records_count": self.corrupt_records_count,
            "quarantined_records_count": self.quarantined_records_count,
            "missing_artifacts_count": self.missing_artifacts_count,
            "unsafe_artifacts_count": self.unsafe_artifacts_count,
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class RecoveryAction:
    action_id: str
    action_type: str
    target: str = ""
    reason: str = ""
    safe_to_apply: bool = True
    destructive: bool = False
    requires_confirmation: bool = False
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target": self.target,
            "reason": self.reason,
            "safe_to_apply": self.safe_to_apply,
            "destructive": self.destructive,
            "requires_confirmation": self.requires_confirmation,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class RecoveryPlan:
    plan_id: str
    created_at: str
    source_report_id: str
    actions: List[RecoveryAction] = field(default_factory=list)
    safe_actions_count: int = 0
    destructive_actions_count: int = 0
    requires_confirmation: bool = False
    can_auto_apply: bool = False
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "source_report_id": self.source_report_id,
            "actions": [action.as_dict() for action in self.actions],
            "safe_actions_count": self.safe_actions_count,
            "destructive_actions_count": self.destructive_actions_count,
            "requires_confirmation": self.requires_confirmation,
            "can_auto_apply": self.can_auto_apply,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class RecoveryResult:
    result_id: str
    created_at: str
    plan_id: str
    status: str = "SKIPPED"
    applied_actions: List[str] = field(default_factory=list)
    skipped_actions: List[str] = field(default_factory=list)
    failed_actions: List[str] = field(default_factory=list)
    diagnostics_path: str = ""
    warnings: List[str] = field(default_factory=list)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "created_at": self.created_at,
            "plan_id": self.plan_id,
            "status": self.status,
            "applied_actions": list(self.applied_actions),
            "skipped_actions": list(self.skipped_actions),
            "failed_actions": list(self.failed_actions),
            "diagnostics_path": self.diagnostics_path,
            "warnings": list(self.warnings),
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class SafeErrorEnvelope:
    error_id: str
    created_at: str
    component: str
    operation: str
    error_type: str
    safe_message: str
    technical_summary: str = ""
    retryable: bool = False
    fallback_used: str = ""
    affected_artifact_ids: List[str] = field(default_factory=list)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "created_at": self.created_at,
            "component": self.component,
            "operation": self.operation,
            "error_type": self.error_type,
            "safe_message": self.safe_message,
            "technical_summary": self.technical_summary,
            "retryable": self.retryable,
            "fallback_used": self.fallback_used,
            "affected_artifact_ids": list(self.affected_artifact_ids),
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class QuarantineRecord:
    quarantine_id: str
    created_at: str
    source_path: str
    line_number: int = 0
    reason: str = ""
    severity: str = "WARN"
    safe_excerpt: str = ""
    original_hash: str = ""
    quarantine_path: str = ""
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "created_at": self.created_at,
            "source_path": self.source_path,
            "line_number": self.line_number,
            "reason": self.reason,
            "severity": self.severity,
            "safe_excerpt": self.safe_excerpt,
            "original_hash": self.original_hash,
            "quarantine_path": self.quarantine_path,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class DiagnosticReport:
    report_id: str
    created_at: str
    integrity_report: Dict[str, Any]
    recovery_plan: Dict[str, Any] = field(default_factory=dict)
    recovery_result: Dict[str, Any] = field(default_factory=dict)
    file_stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    diagnostics_path: str = ""
    payload_chars: int = 0
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "integrity_report": dict(self.integrity_report),
            "recovery_plan": dict(self.recovery_plan),
            "recovery_result": dict(self.recovery_result),
            "file_stats": dict(self.file_stats),
            "warnings": list(self.warnings),
            "diagnostics_path": self.diagnostics_path,
            "payload_chars": self.payload_chars,
            "execution_allowed": self.execution_allowed,
        }


class SystemHardeningService:
    def __init__(
        self,
        quarantine_dir: str | Path | None = None,
        diagnostics_dir: str | Path | None = None,
    ):
        self.quarantine_dir = Path(quarantine_dir or DEFAULT_QUARANTINE_DIR)
        self.diagnostics_dir = Path(diagnostics_dir or DEFAULT_DIAGNOSTICS_DIR)

    def validate_jsonl(
        self,
        path: str | Path,
        component: str = "PERSISTENCE_STORE",
        required_fields: Set[str] | None = None,
        id_field: str = "registry_id",
        expected_schema_versions: Set[str] | None = None,
        missing_is_warn: bool = True,
    ) -> SystemIntegrityReport:
        started = time.perf_counter()
        target = Path(path)
        issues: List[SystemIntegrityIssue] = []
        checked = [component, str(target)]
        seen_ids: Set[str] = set()
        corrupt = 0
        unsafe = 0
        missing = 0
        entries_checked = 0
        required = set(required_fields or set())

        if not target.exists():
            missing = 1
            issues.append(
                self._issue(
                    severity="WARN" if missing_is_warn else "ERROR",
                    category=component,
                    location=str(target),
                    message="store file is missing; using safe empty state",
                    recoverable=True,
                )
            )
            return self._report(checked, issues, started, missing_artifacts=missing, corrupt_records=corrupt, unsafe_artifacts=unsafe)

        text = target.read_text(encoding="utf-8")
        if not text.strip():
            issues.append(
                self._issue(
                    severity="INFO",
                    category=component,
                    location=str(target),
                    message="store file is empty; no records to load",
                    recoverable=True,
                )
            )
            return self._report(checked, issues, started, corrupt_records=0, unsafe_artifacts=0)

        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                corrupt += 1
                issues.append(
                    self._issue(
                        severity="ERROR",
                        category=component,
                        location=f"{target}:{line_number}",
                        message="corrupt JSONL line detected",
                        recoverable=True,
                    )
                )
                continue
            entries_checked += 1
            if not isinstance(item, Mapping):
                corrupt += 1
                issues.append(
                    self._issue(
                        severity="ERROR",
                        category=component,
                        location=f"{target}:{line_number}",
                        message="JSONL record is not an object",
                        recoverable=True,
                    )
                )
                continue
            missing_fields = sorted(field for field in required if field not in item)
            if missing_fields:
                issues.append(
                    self._issue(
                        severity="ERROR",
                        category=component,
                        location=f"{target}:{line_number}",
                        message=f"record missing required fields: {', '.join(missing_fields)}",
                        affected_ids=[str(item.get(id_field, ""))] if item.get(id_field) else [],
                        recoverable=True,
                    )
                )
            record_id = str(item.get(id_field) or "")
            if record_id:
                if record_id in seen_ids:
                    issues.append(
                        self._issue(
                            severity="WARN",
                            category=component,
                            location=f"{target}:{line_number}",
                            message=f"duplicate {id_field} detected; first safe record should be kept",
                            affected_ids=[record_id],
                            recoverable=True,
                        )
                    )
                seen_ids.add(record_id)
            schema_version = str(item.get("schema_version") or "")
            if expected_schema_versions is not None and schema_version and schema_version not in expected_schema_versions:
                issues.append(
                    self._issue(
                        severity="WARN",
                        category=component,
                        location=f"{target}:{line_number}",
                        message=f"unexpected schema_version: {schema_version}",
                        affected_ids=[record_id] if record_id else [],
                        recoverable=True,
                    )
                )
            unsafe_warnings = _unsafe_warnings(item)
            if unsafe_warnings:
                unsafe += 1
                issues.append(
                    self._issue(
                        severity="CRITICAL" if _account_or_execution_warning(unsafe_warnings) else "ERROR",
                        category=component,
                        location=f"{target}:{line_number}",
                        message=f"unsafe fields or values detected: {', '.join(sorted(set(unsafe_warnings)))}",
                        affected_ids=[record_id] if record_id else [],
                        recoverable=True,
                        safety_relevant=True,
                    )
                )
            if bool(item.get("execution_allowed")):
                unsafe += 1
                issues.append(
                    self._issue(
                        severity="CRITICAL",
                        category="SAFETY_BOUNDARY",
                        location=f"{target}:{line_number}",
                        message="execution_allowed=true is not permitted",
                        affected_ids=[record_id] if record_id else [],
                        recoverable=True,
                        safety_relevant=True,
                        execution_allowed=True,
                    )
                )

        report = self._report(checked, issues, started, corrupt_records=corrupt, unsafe_artifacts=unsafe)
        report.warnings.append(f"entries_checked={entries_checked}")
        print(
            "[SystemHardening] "
            f"action=validate components={checked} status={report.status} issues={len(report.issues)} "
            f"latency_ms={report.latency_ms}"
        )
        return report

    def validate_manifest(
        self,
        path: str | Path,
        component: str = "PERSISTENCE_STORE",
        required_list_key: str = "versions",
        expected_schema_versions: Set[str] | None = None,
    ) -> SystemIntegrityReport:
        started = time.perf_counter()
        target = Path(path)
        checked = [component, str(target)]
        issues: List[SystemIntegrityIssue] = []
        missing = 0
        unsafe = 0
        if not target.exists():
            missing = 1
            issues.append(self._issue("WARN", component, str(target), "manifest is missing; using safe empty state"))
            return self._report(checked, issues, started, missing_artifacts=missing)
        try:
            data = json.loads(target.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            issues.append(self._issue("ERROR", component, str(target), "manifest contains invalid JSON", recoverable=True))
            return self._report(checked, issues, started, corrupt_records=1)
        if not isinstance(data, Mapping):
            issues.append(self._issue("ERROR", component, str(target), "manifest root is not an object", recoverable=True))
            return self._report(checked, issues, started, corrupt_records=1)
        if required_list_key not in data or not isinstance(data.get(required_list_key), list):
            issues.append(self._issue("ERROR", component, str(target), f"manifest missing list field: {required_list_key}", recoverable=True))
        schema_version = str(data.get("schema_version") or "")
        if expected_schema_versions is not None and schema_version and schema_version not in expected_schema_versions:
            issues.append(self._issue("WARN", component, str(target), f"unexpected schema_version: {schema_version}"))
        unsafe_warnings = _unsafe_warnings(data)
        if unsafe_warnings:
            unsafe = 1
            issues.append(
                self._issue(
                    "CRITICAL" if _account_or_execution_warning(unsafe_warnings) else "ERROR",
                    component,
                    str(target),
                    f"unsafe manifest fields or values detected: {', '.join(sorted(set(unsafe_warnings)))}",
                    safety_relevant=True,
                )
            )
        return self._report(checked, issues, started, unsafe_artifacts=unsafe)

    def validate_persistence_stores(
        self,
        registry_path: str | Path = DEFAULT_REGISTRY_PATH,
        dataset_manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
        annotation_path: str | Path = DEFAULT_ANNOTATION_PATH,
        workflow_state_path: str | Path = DEFAULT_WORKFLOW_STATE_PATH,
        annotated_version_path: str | Path = DEFAULT_ANNOTATED_VERSION_PATH,
        golden_cases_path: str | Path = DEFAULT_GOLDEN_CASES_PATH,
    ) -> SystemIntegrityReport:
        started = time.perf_counter()
        reports = [
            self.validate_jsonl(
                registry_path,
                component="PERSISTENCE_STORE",
                required_fields=REQUIRED_REGISTRY_FIELDS,
                expected_schema_versions={PERSISTENCE_SCHEMA_VERSION},
            ),
            self.validate_manifest(
                dataset_manifest_path,
                component="PERSISTENCE_STORE",
                expected_schema_versions={DATASET_MANIFEST_SCHEMA_VERSION},
            ),
            self.validate_jsonl(
                annotation_path,
                component="HUMAN_REVIEW",
                required_fields=REQUIRED_ANNOTATION_FIELDS,
                id_field="annotation_id",
                expected_schema_versions={ANNOTATION_SCHEMA_VERSION},
            ),
            self.validate_manifest(
                workflow_state_path,
                component="HUMAN_REVIEW",
                required_list_key="states",
                expected_schema_versions={"human_review_workflow_state.v1"},
            ),
            self.validate_manifest(
                annotated_version_path,
                component="HUMAN_REVIEW",
                expected_schema_versions={ANNOTATED_DATASET_SCHEMA_VERSION},
            ),
            self.validate_benchmark_cases(golden_cases_path),
        ]
        report = self._combine_reports(reports, started, checked_component="system_persistence")
        print(
            "[SystemHardening] "
            f"action=validate components=persistence status={report.status} issues={len(report.issues)} "
            f"latency_ms={report.latency_ms}"
        )
        return report

    def validate_dashboard_state(
        self,
        registry_entries: Sequence[EvaluationRegistryEntry | Mapping[str, Any]] | None = None,
        selected_registry_id: str = "",
        runtime_artifacts: Mapping[str, Any] | None = None,
    ) -> SystemIntegrityReport:
        started = time.perf_counter()
        entries = [_entry_dict(item) for item in registry_entries or []]
        issues: List[SystemIntegrityIssue] = []
        if not entries:
            issues.append(
                self._issue(
                    "INFO",
                    "DASHBOARD_STATE",
                    "evaluation_dashboard",
                    "registry is empty; dashboard should show safe empty state",
                    recoverable=True,
                )
            )
        if selected_registry_id and selected_registry_id not in {str(entry.get("registry_id") or "") for entry in entries}:
            issues.append(
                self._issue(
                    "WARN",
                    "DASHBOARD_STATE",
                    "selected_registry_id",
                    "selected registry_id is no longer available; detail panel should fall back safely",
                    affected_ids=[selected_registry_id],
                )
            )
        for entry in entries:
            registry_id = str(entry.get("registry_id") or "")
            if not isinstance(entry.get("task_index", []), list):
                issues.append(self._issue("ERROR", "DASHBOARD_STATE", registry_id, "task_index is malformed", [registry_id]))
                continue
            if not isinstance(entry.get("safety_index", {}), Mapping):
                issues.append(self._issue("WARN", "DASHBOARD_STATE", registry_id, "safety_index missing or malformed", [registry_id]))
            if not isinstance(entry.get("evaluation_index", {}), Mapping):
                issues.append(self._issue("WARN", "DASHBOARD_STATE", registry_id, "evaluation_index missing or malformed", [registry_id]))
            for task in entry.get("task_index", []) or []:
                if not isinstance(task, Mapping):
                    issues.append(self._issue("ERROR", "DASHBOARD_STATE", registry_id, "task_index item is malformed", [registry_id]))
                    continue
                issues.extend(self._task_scope_issues(task, registry_id))
        if runtime_artifacts is not None:
            runtime_report = self.validate_runtime_artifacts(runtime_artifacts)
            issues.extend(runtime_report.issues)
        return self._report(["dashboard_state"], issues, started, unsafe_artifacts=sum(1 for issue in issues if issue.safety_relevant))

    def validate_runtime_artifacts(self, runtime_artifacts: Mapping[str, Any] | None) -> SystemIntegrityReport:
        started = time.perf_counter()
        issues: List[SystemIntegrityIssue] = []
        if not isinstance(runtime_artifacts, Mapping):
            issues.append(self._issue("ERROR", "RUNTIME_ARTIFACT", "runtime_artifacts", "runtime_artifacts is not dict-like"))
            return self._report(["runtime_artifacts"], issues, started, missing_artifacts=1)
        final_artifact = runtime_artifacts.get("final_answer_artifact")
        final_hash = runtime_artifacts.get("final_answer_sha256")
        if final_artifact is None:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "final_answer_artifact", "final answer artifact is missing"))
        elif isinstance(final_artifact, Mapping) and not (final_artifact.get("final_answer_sha256") or final_artifact.get("hashes", {}).get("final_answer_sha256")):
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "final_answer_artifact", "final answer hash is missing"))
        if final_artifact is None and not final_hash:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "final_answer_sha256", "final answer sha256 is missing"))
        if "compliance_result" not in runtime_artifacts and "agent_answer_compliance" not in runtime_artifacts:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "compliance_result", "compliance result is missing"))
        if "answer_completeness" not in runtime_artifacts:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "answer_completeness", "answer completeness result is missing"))
        if "journal_review" not in runtime_artifacts and final_artifact is not None:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "journal_review", "journal review is missing after final answer"))
        if "evaluation_registry" not in runtime_artifacts:
            issues.append(self._issue("WARN", "RUNTIME_ARTIFACT", "evaluation_registry", "evaluation registry artifact is missing"))
        tasks = _runtime_tasks(runtime_artifacts)
        for task in tasks:
            issues.extend(self._task_scope_issues(task, str(task.get("task_id") or "runtime_task")))
            intent = str(task.get("intent_family") or "")
            missing_backtest = not task.get("backtest_status") and not task.get("backtest_record_id")
            missing_paper = not task.get("paper_status") and not task.get("paper_record_id")
            if intent in STATIC_INTENTS and (missing_backtest or missing_paper):
                continue
            if _is_market_intent(intent) and (missing_backtest or missing_paper):
                issues.append(
                    self._issue(
                        "WARN",
                        "RUNTIME_ARTIFACT",
                        str(task.get("task_id") or ""),
                        "market task is missing backtest or paper evaluation artifact",
                        affected_ids=[str(task.get("task_id") or "")],
                    )
                )
        if bool(runtime_artifacts.get("execution_allowed")):
            issues.append(
                self._issue(
                    "CRITICAL",
                    "SAFETY_BOUNDARY",
                    "runtime_artifacts.execution_allowed",
                    "execution_allowed=true is not permitted",
                    recoverable=True,
                    safety_relevant=True,
                    execution_allowed=True,
                )
            )
        unsafe = _unsafe_warnings(runtime_artifacts)
        if unsafe:
            issues.append(self._issue("ERROR", "RUNTIME_ARTIFACT", "runtime_artifacts", "unsafe runtime artifact fields detected", safety_relevant=True))
        return self._report(["runtime_artifacts"], issues, started, unsafe_artifacts=sum(1 for issue in issues if issue.safety_relevant))

    def validate_benchmark_cases(self, path: str | Path = DEFAULT_GOLDEN_CASES_PATH) -> SystemIntegrityReport:
        started = time.perf_counter()
        target = Path(path)
        issues: List[SystemIntegrityIssue] = []
        if not target.exists():
            issues.append(self._issue("WARN", "BENCHMARK_CASE", str(target), "benchmark cases file is missing"))
            return self._report(["benchmark_cases"], issues, started, missing_artifacts=1)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append(self._issue("ERROR", "BENCHMARK_CASE", str(target), "benchmark cases file contains invalid JSON"))
            return self._report(["benchmark_cases"], issues, started, corrupt_records=1)
        items = data.get("cases") if isinstance(data, Mapping) else data
        if not isinstance(items, list) or not items:
            issues.append(self._issue("ERROR", "BENCHMARK_CASE", str(target), "benchmark cases list is missing or empty"))
            return self._report(["benchmark_cases"], issues, started)
        seen: Set[str] = set()
        unsafe = 0
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                issues.append(self._issue("ERROR", "BENCHMARK_CASE", f"{target}:{index}", "benchmark case is not an object"))
                continue
            case_id = str(item.get("case_id") or "")
            if not case_id:
                issues.append(self._issue("ERROR", "BENCHMARK_CASE", f"{target}:{index}", "benchmark case missing case_id"))
            if case_id in seen:
                issues.append(self._issue("WARN", "BENCHMARK_CASE", f"{target}:{index}", "duplicate benchmark case_id", [case_id]))
            seen.add(case_id)
            if not isinstance(item.get("expected", {}), Mapping):
                issues.append(self._issue("ERROR", "BENCHMARK_CASE", f"{target}:{case_id}", "expected block is malformed", [case_id]))
            policy = item.get("safety_policy", {})
            if not isinstance(policy, Mapping) or not policy:
                issues.append(self._issue("WARN", "BENCHMARK_CASE", f"{target}:{case_id}", "safety policy is missing", [case_id]))
            if bool(item.get("expected", {}).get("execution_allowed")):
                unsafe += 1
                issues.append(self._issue("CRITICAL", "SAFETY_BOUNDARY", f"{target}:{case_id}", "benchmark expects execution_allowed=true", [case_id], safety_relevant=True, execution_allowed=True))
            fixture_warnings = _unsafe_warnings(item.get("fixtures", {}), allow_unsafe_query=True)
            if fixture_warnings:
                unsafe += 1
                issues.append(
                    self._issue(
                        "CRITICAL" if _account_or_execution_warning(fixture_warnings) else "ERROR",
                        "BENCHMARK_CASE",
                        f"{target}:{case_id}",
                        f"unsafe benchmark fixture fields detected: {', '.join(sorted(set(fixture_warnings)))}",
                        [case_id],
                        safety_relevant=True,
                    )
                )
        return self._report(["benchmark_cases"], issues, started, unsafe_artifacts=unsafe)

    def validate_benchmark_report(self, report: Mapping[str, Any] | str | Path) -> SystemIntegrityReport:
        started = time.perf_counter()
        issues: List[SystemIntegrityIssue] = []
        location = "benchmark_report"
        if isinstance(report, (str, Path)):
            location = str(report)
            try:
                data = json.loads(Path(report).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                issues.append(self._issue("ERROR", "BENCHMARK_REPORT", location, "benchmark report cannot be read as JSON"))
                return self._report(["benchmark_report"], issues, started, corrupt_records=1)
        else:
            data = dict(report)
        total = int(data.get("total_cases") or 0)
        passed = int(data.get("passed") or 0)
        warned = int(data.get("warned") or 0)
        failed = int(data.get("failed") or 0)
        skipped = int(data.get("skipped") or 0)
        if total != passed + warned + failed + skipped:
            issues.append(self._issue("ERROR", "BENCHMARK_REPORT", location, "benchmark report counts do not add up"))
        expected_rate = _rate(passed, total)
        if abs(float(data.get("pass_rate") or 0.0) - expected_rate) > 0.0001:
            issues.append(self._issue("ERROR", "BENCHMARK_REPORT", location, "benchmark report pass_rate does not match counts"))
        if data.get("benchmark_version") and data.get("benchmark_version") != GOLDEN_BENCHMARK_VERSION:
            issues.append(self._issue("WARN", "BENCHMARK_REPORT", location, "unexpected benchmark version"))
        if bool(data.get("execution_allowed")):
            issues.append(self._issue("CRITICAL", "SAFETY_BOUNDARY", location, "benchmark report has execution_allowed=true", safety_relevant=True, execution_allowed=True))
        if _unsafe_warnings(data):
            issues.append(self._issue("ERROR", "BENCHMARK_REPORT", location, "unsafe benchmark report fields detected", safety_relevant=True))
        return self._report(["benchmark_report"], issues, started, unsafe_artifacts=sum(1 for issue in issues if issue.safety_relevant))

    def validate_replay_case(self, replay_case: Mapping[str, Any] | None) -> SystemIntegrityReport:
        started = time.perf_counter()
        issues: List[SystemIntegrityIssue] = []
        if not isinstance(replay_case, Mapping):
            issues.append(self._issue("ERROR", "REPLAY", "replay_case", "replay case is missing or malformed"))
            return self._report(["replay"], issues, started)
        if not replay_case.get("input_records") and not replay_case.get("supplied_fixtures"):
            issues.append(self._issue("WARN", "REPLAY", str(replay_case.get("replay_id") or ""), "replay fixture is missing; replay should be skipped or fail safely"))
        policy = replay_case.get("replay_policy", {})
        if isinstance(policy, Mapping) and not bool(policy.get("no_execution", True)):
            issues.append(self._issue("CRITICAL", "SAFETY_BOUNDARY", str(replay_case.get("replay_id") or ""), "replay policy permits execution", safety_relevant=True, execution_allowed=True))
        return self._report(["replay"], issues, started)

    def normalize_error(
        self,
        component: str,
        operation: str,
        error: BaseException | str,
        retryable: bool = False,
        fallback_used: str = "",
        affected_artifact_ids: Sequence[str] | None = None,
    ) -> SafeErrorEnvelope:
        error_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
        summary = _safe_excerpt(str(error), 220)
        return SafeErrorEnvelope(
            error_id=f"safe_error:{_hash_payload([component, operation, error_type, summary])[:16]}",
            created_at=_utc_now(),
            component=component,
            operation=operation,
            error_type=error_type,
            safe_message=f"{component} {operation} failed safely",
            technical_summary=summary,
            retryable=retryable,
            fallback_used=fallback_used,
            affected_artifact_ids=list(affected_artifact_ids or []),
            execution_allowed=False,
        )

    def plan_recovery(self, report: SystemIntegrityReport | Mapping[str, Any]) -> RecoveryPlan:
        started = time.perf_counter()
        data = report.as_dict() if isinstance(report, SystemIntegrityReport) else dict(report)
        actions: List[RecoveryAction] = []
        for index, issue in enumerate(data.get("issues", []) or []):
            category = issue.get("category", "UNKNOWN")
            location = issue.get("location", "")
            message = issue.get("message", "")
            if "missing" in message and category in {"PERSISTENCE_STORE", "HUMAN_REVIEW", "BENCHMARK_CASE", "DASHBOARD_STATE"}:
                action_type = "FALLBACK_EMPTY_STATE"
            elif "corrupt JSONL" in message or "invalid JSON" in message:
                action_type = "QUARANTINE_RECORD"
            elif "duplicate" in message:
                action_type = "SKIP_RECORD"
            elif "unsafe" in message or issue.get("safety_relevant"):
                action_type = "WARN_ONLY"
            elif "market task is missing" in message:
                action_type = "MARK_INCOMPLETE_CHAIN"
            elif "static" in message or "not applicable" in message:
                action_type = "MARK_NOT_APPLICABLE"
            else:
                action_type = "VALIDATE_ONLY"
            actions.append(
                RecoveryAction(
                    action_id=f"recovery_action:{_hash_payload([data.get('report_id'), index, action_type, location])[:12]}",
                    action_type=action_type,
                    target=location,
                    reason=message,
                    safe_to_apply=True,
                    destructive=False,
                    requires_confirmation=False,
                    execution_allowed=False,
                )
            )
        if not actions:
            actions.append(
                RecoveryAction(
                    action_id=f"recovery_action:{_hash_payload([data.get('report_id'), 'noop'])[:12]}",
                    action_type="NOOP",
                    target=str(data.get("report_id") or ""),
                    reason="no recovery action required",
                )
            )
        plan = RecoveryPlan(
            plan_id=f"recovery_plan:{_hash_payload([data.get('report_id'), [action.as_dict() for action in actions]])[:16]}",
            created_at=_utc_now(),
            source_report_id=str(data.get("report_id") or ""),
            actions=actions,
            safe_actions_count=sum(1 for action in actions if action.safe_to_apply),
            destructive_actions_count=sum(1 for action in actions if action.destructive),
            requires_confirmation=any(action.requires_confirmation for action in actions),
            can_auto_apply=all(action.safe_to_apply and not action.destructive and not action.requires_confirmation for action in actions),
            execution_allowed=False,
        )
        print(
            "[SystemHardening] "
            f"action=plan_recovery report_id={plan.source_report_id} actions={len(plan.actions)} "
            f"requires_confirmation={plan.requires_confirmation} latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return plan

    def quarantine_jsonl_records(
        self,
        source_path: str | Path,
        line_numbers: Sequence[int] | None = None,
        reason: str = "corrupt_or_unsafe_record",
        severity: str = "ERROR",
    ) -> List[QuarantineRecord]:
        source = Path(source_path)
        if not source.exists():
            return []
        requested = set(line_numbers or [])
        records: List[QuarantineRecord] = []
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if requested and line_number not in requested:
                continue
            original_hash = _hash_text(line)
            quarantine_id = f"quarantine:{_hash_payload([str(source), line_number, original_hash])[:16]}"
            target = self.quarantine_dir / f"{_safe_filename(source.name)}.{line_number}.{original_hash[:12]}.json"
            payload = {
                "quarantine_id": quarantine_id,
                "created_at": _utc_now(),
                "source_path": str(source),
                "line_number": line_number,
                "reason": reason,
                "severity": severity,
                "safe_excerpt": _safe_excerpt(line),
                "original_hash": original_hash,
                "execution_allowed": False,
            }
            self.quarantine_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            records.append(
                QuarantineRecord(
                    quarantine_id=quarantine_id,
                    created_at=payload["created_at"],
                    source_path=str(source),
                    line_number=line_number,
                    reason=reason,
                    severity=severity,
                    safe_excerpt=payload["safe_excerpt"],
                    original_hash=original_hash,
                    quarantine_path=str(target),
                    execution_allowed=False,
                )
            )
        print(
            "[SystemHardening] "
            f"action=quarantine source={source} records={len(records)} status={'PASS' if records else 'SKIPPED'}"
        )
        return records

    def apply_recovery(
        self,
        plan: RecoveryPlan | Mapping[str, Any],
        allow_quarantine: bool = False,
        allow_destructive: bool = False,
    ) -> RecoveryResult:
        started = time.perf_counter()
        data = plan.as_dict() if isinstance(plan, RecoveryPlan) else dict(plan)
        applied: List[str] = []
        skipped: List[str] = []
        failed: List[str] = []
        for action in data.get("actions", []) or []:
            action_id = str(action.get("action_id") or "")
            if action.get("destructive") and not allow_destructive:
                skipped.append(action_id)
            elif action.get("action_type") == "QUARANTINE_RECORD" and not allow_quarantine:
                skipped.append(action_id)
            else:
                applied.append(action_id)
        status = "APPLIED" if applied and not failed and not skipped else ("PARTIAL" if applied else "SKIPPED")
        result = RecoveryResult(
            result_id=f"recovery_result:{_hash_payload([data.get('plan_id'), applied, skipped, failed])[:16]}",
            created_at=_utc_now(),
            plan_id=str(data.get("plan_id") or ""),
            status=status,
            applied_actions=applied,
            skipped_actions=skipped,
            failed_actions=failed,
            warnings=["quarantine requires explicit allow_quarantine"] if skipped and not allow_quarantine else [],
            execution_allowed=False,
        )
        print(
            "[SystemHardening] "
            f"action=apply_recovery plan_id={result.plan_id} status={result.status} "
            f"applied={len(applied)} failed={len(failed)} latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return result

    def export_diagnostic_report(
        self,
        integrity_report: SystemIntegrityReport | Mapping[str, Any],
        recovery_plan: RecoveryPlan | Mapping[str, Any] | None = None,
        recovery_result: RecoveryResult | Mapping[str, Any] | None = None,
        file_stats: Mapping[str, Any] | None = None,
        out_dir: str | Path | None = None,
    ) -> DiagnosticReport:
        started = time.perf_counter()
        report_data = integrity_report.as_dict() if isinstance(integrity_report, SystemIntegrityReport) else dict(integrity_report)
        plan_data = recovery_plan.as_dict() if isinstance(recovery_plan, RecoveryPlan) else dict(recovery_plan or {})
        result_data = recovery_result.as_dict() if isinstance(recovery_result, RecoveryResult) else dict(recovery_result or {})
        payload = {
            "report_id": f"diagnostic:{_hash_payload([report_data.get('report_id'), plan_data.get('plan_id'), result_data.get('result_id')])[:16]}",
            "created_at": _utc_now(),
            "integrity_report": report_data,
            "recovery_plan": plan_data,
            "recovery_result": result_data,
            "file_stats": dict(file_stats or {}),
            "warnings": [],
            "execution_allowed": False,
        }
        redacted_payload = _redact_payload(payload)
        text = json.dumps(redacted_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        target_dir = Path(out_dir or self.diagnostics_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{redacted_payload['report_id'].replace(':', '_')}.json"
        target.write_text(text, encoding="utf-8")
        diagnostic = DiagnosticReport(
            report_id=redacted_payload["report_id"],
            created_at=redacted_payload["created_at"],
            integrity_report=redacted_payload["integrity_report"],
            recovery_plan=redacted_payload["recovery_plan"],
            recovery_result=redacted_payload["recovery_result"],
            file_stats=redacted_payload["file_stats"],
            warnings=redacted_payload["warnings"],
            diagnostics_path=str(target),
            payload_chars=len(text),
            execution_allowed=False,
        )
        print(
            "[SystemHardening] "
            f"action=diagnostic_export report_id={diagnostic.report_id} payload_chars={diagnostic.payload_chars} "
            f"status=PASS latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return diagnostic

    def _task_scope_issues(self, task: Mapping[str, Any], registry_id: str) -> List[SystemIntegrityIssue]:
        issues: List[SystemIntegrityIssue] = []
        task_id = str(task.get("task_id") or "")
        intent = str(task.get("intent_family") or "")
        symbol = str(task.get("symbol") or "")
        source_refs = [str(ref) for ref in task.get("source_refs", []) or []]
        agent_refs = [str(ref) for ref in task.get("agent_refs", []) or []]
        if intent in STATIC_INTENTS:
            if symbol:
                issues.append(
                    self._issue(
                        "ERROR",
                        "RUNTIME_ARTIFACT",
                        registry_id,
                        "static/book task inherited a market symbol",
                        affected_ids=[task_id or registry_id],
                        safety_relevant=True,
                    )
                )
            leaked_sources = [ref for ref in source_refs if "market" in ref.lower() or "xauusd" in ref.lower()]
            if leaked_sources:
                issues.append(
                    self._issue(
                        "ERROR",
                        "RUNTIME_ARTIFACT",
                        registry_id,
                        "static/book task inherited market source refs",
                        affected_ids=[task_id or registry_id],
                        safety_relevant=True,
                    )
                )
            leaked_agents = [agent for agent in agent_refs if agent in MARKET_AGENT_TYPES]
            if leaked_agents:
                issues.append(
                    self._issue(
                        "ERROR",
                        "RUNTIME_ARTIFACT",
                        registry_id,
                        "static/book task inherited market agent refs",
                        affected_ids=[task_id or registry_id],
                        safety_relevant=True,
                    )
                )
        return issues

    def _issue(
        self,
        severity: str,
        category: str,
        location: str,
        message: str,
        affected_ids: Sequence[str] | None = None,
        recoverable: bool = True,
        safety_relevant: bool = False,
        execution_allowed: bool = False,
    ) -> SystemIntegrityIssue:
        safe_message = _safe_excerpt(message, 260)
        safe_location = _safe_excerpt(location, 260)
        issue_id = f"integrity_issue:{_hash_payload([severity, category, safe_location, safe_message, affected_ids or []])[:16]}"
        return SystemIntegrityIssue(
            issue_id=issue_id,
            created_at=_utc_now(),
            severity=severity if severity in ISSUE_SEVERITIES else "WARN",
            category=category if category in ISSUE_CATEGORIES else "UNKNOWN",
            location=safe_location,
            message=safe_message,
            affected_ids=[_safe_excerpt(item, 80) for item in affected_ids or []],
            recoverable=recoverable,
            safety_relevant=safety_relevant,
            execution_allowed=execution_allowed,
        )

    def _report(
        self,
        checked_components: Sequence[str],
        issues: Sequence[SystemIntegrityIssue],
        started: float,
        corrupt_records: int = 0,
        quarantined_records: int = 0,
        missing_artifacts: int = 0,
        unsafe_artifacts: int = 0,
    ) -> SystemIntegrityReport:
        status = _report_status(issues)
        report = SystemIntegrityReport(
            report_id=f"integrity_report:{_hash_payload([checked_components, [issue.as_dict() for issue in issues]])[:16]}",
            created_at=_utc_now(),
            status=status,
            checked_components=list(checked_components),
            issues=list(issues),
            issue_counts_by_severity=_counts(issue.severity for issue in issues),
            issue_counts_by_category=_counts(issue.category for issue in issues),
            corrupt_records_count=corrupt_records,
            quarantined_records_count=quarantined_records,
            missing_artifacts_count=missing_artifacts,
            unsafe_artifacts_count=unsafe_artifacts,
            warnings=[issue.message for issue in issues if issue.severity in {"WARN", "ERROR", "CRITICAL"}],
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            execution_allowed=any(issue.execution_allowed for issue in issues),
        )
        return report

    def _combine_reports(
        self,
        reports: Sequence[SystemIntegrityReport],
        started: float,
        checked_component: str,
    ) -> SystemIntegrityReport:
        issues = [issue for report in reports for issue in report.issues]
        checked = [checked_component]
        for report in reports:
            checked.extend(report.checked_components)
        return self._report(
            checked,
            issues,
            started,
            corrupt_records=sum(report.corrupt_records_count for report in reports),
            quarantined_records=sum(report.quarantined_records_count for report in reports),
            missing_artifacts=sum(report.missing_artifacts_count for report in reports),
            unsafe_artifacts=sum(report.unsafe_artifacts_count for report in reports),
        )


def _runtime_tasks(runtime_artifacts: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    tasks = runtime_artifacts.get("tasks")
    if isinstance(tasks, list):
        return [task for task in tasks if isinstance(task, Mapping)]
    registry = runtime_artifacts.get("evaluation_registry")
    if isinstance(registry, Mapping):
        entries = registry.get("entries")
        if isinstance(entries, list):
            return [task for entry in entries if isinstance(entry, Mapping) for task in entry.get("task_index", []) if isinstance(task, Mapping)]
    return []


def _entry_dict(entry: EvaluationRegistryEntry | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(entry, EvaluationRegistryEntry):
        return entry.as_dict()
    return dict(entry)


def _report_status(issues: Sequence[SystemIntegrityIssue]) -> str:
    severities = {issue.severity for issue in issues}
    if "CRITICAL" in severities:
        return "CRITICAL"
    if "ERROR" in severities:
        return "FAIL"
    if "WARN" in severities:
        return "WARN"
    return "PASS"


def _unsafe_warnings(value: Any, allow_unsafe_query: bool = False) -> List[str]:
    warnings: List[str] = []
    for key in _mapping_keys(value):
        lowered = key.lower()
        if lowered == "query" and allow_unsafe_query:
            continue
        if lowered in UNSAFE_KEYS or any(token in lowered for token in ("password", "secret", "api_key", "token")):
            warnings.append(f"unsafe_field:{lowered}")
    for text in _string_values(value):
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                warnings.append("secret_like_value")
        for pattern in REGISTRY_SAFETY_PATTERNS:
            if pattern.search(text):
                warnings.append("prohibited_trading_or_execution_text")
    return sorted(set(warnings))


def _account_or_execution_warning(warnings: Sequence[str]) -> bool:
    return any("account" in warning or "mt5" in warning or "order" in warning or "execution" in warning for warning in warnings)


def _mapping_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key)
            yield from _mapping_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _mapping_keys(item)


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _string_values(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def _redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        redacted: Dict[str, Any] = {}
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in UNSAFE_KEYS:
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact_payload(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _redact_text(text: str) -> str:
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    for pattern in REGISTRY_SAFETY_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    for pattern in UNSAFE_ASSIGNMENT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    for key in sorted(UNSAFE_KEYS, key=len, reverse=True):
        redacted = re.sub(rf"\b{re.escape(key)}\b", "[REDACTED_FIELD]", redacted, flags=re.IGNORECASE)
    return redacted


def _safe_excerpt(text: str, limit: int = 180) -> str:
    redacted = _redact_text(str(text)).replace("\n", " ").replace("\r", " ")
    return redacted[:limit]


def _safe_filename(text: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)[:120] or "record"


def _is_market_intent(intent: str) -> bool:
    lowered = intent.lower()
    return any(token in lowered for token in ("market", "macro", "strategy", "risk"))


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _counts(values: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        key = str(value or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
