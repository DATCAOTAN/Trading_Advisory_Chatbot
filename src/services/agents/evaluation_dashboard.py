from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_registry import (
    EvaluationRegistry,
    EvaluationRegistryEntry,
    EvaluationReplayCase,
    EvaluationReplayHarness,
    ReplayResult,
)
from src.services.agents.evaluation_persistence import (
    EvaluationPersistenceStore,
    ExportResult,
    ImportResult,
    PersistBatchResult,
    ValidationResult,
)
from src.services.agents.human_review import (
    HumanReviewStore,
    REASON_CODE_TAXONOMY,
    annotation_from_registry_entry,
)
from src.services.agents.review_analytics import (
    QualityMetricsExport,
    QualityMetricsReport,
    ReviewAnalyticsEngine,
    ReviewAnalyticsFilters,
)
from src.services.agents.system_hardening import (
    DiagnosticReport,
    RecoveryPlan,
    SystemHardeningService,
    SystemIntegrityReport,
)


HIGH_REVIEW_STATUSES = {"FAIL", "DEGRADED"}
MEDIUM_REVIEW_STATUSES = {"WARN", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"}
HIGH_QUALITY_FLAGS = {"unsafe_or_noncompliant", "failed_validation", "incomplete", "invalid_input"}
MEDIUM_QUALITY_FLAGS = {"acceptable", "limited_review", "degraded"}


@dataclass
class EvaluationDashboardFilters:
    request_id: str = ""
    final_answer_sha256: str = ""
    symbol: str = ""
    record_type: str = ""
    status: str = ""
    quality_label: str = ""
    review_priority: str = ""
    needs_review_only: bool = False
    task_id: str = ""
    intent_family: str = ""
    safety_flag: str = ""
    review_status: str = ""
    severity: str = ""
    created_after: str = ""
    created_before: str = ""
    limit: int = 100

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "symbol": self.symbol,
            "record_type": self.record_type,
            "status": self.status,
            "quality_label": self.quality_label,
            "review_priority": self.review_priority,
            "needs_review_only": self.needs_review_only,
            "task_id": self.task_id,
            "intent_family": self.intent_family,
            "safety_flag": self.safety_flag,
            "review_status": self.review_status,
            "severity": self.severity,
            "created_after": self.created_after,
            "created_before": self.created_before,
            "limit": self.limit,
        }


@dataclass
class EvaluationDashboardSummary:
    total_entries: int = 0
    by_record_type: Dict[str, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)
    by_quality_label: Dict[str, int] = field(default_factory=dict)
    needs_review_count: int = 0
    safety_flag_count: int = 0
    symbols: List[str] = field(default_factory=list)
    recent_request_ids: List[str] = field(default_factory=list)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "by_record_type": dict(self.by_record_type),
            "by_status": dict(self.by_status),
            "by_quality_label": dict(self.by_quality_label),
            "needs_review_count": self.needs_review_count,
            "safety_flag_count": self.safety_flag_count,
            "symbols": list(self.symbols),
            "recent_request_ids": list(self.recent_request_ids),
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class EvaluationDashboardRow:
    registry_id: str
    created_at: str
    record_type: str
    request_id: str
    task_ids: List[str] = field(default_factory=list)
    symbol: str = ""
    status: str = ""
    quality_label: str = ""
    review_outcome: str = ""
    review_priority: str = "LOW"
    final_answer_sha256: str = ""
    source_refs_count: int = 0
    safety_flags: List[str] = field(default_factory=list)
    has_journal: bool = False
    has_backtest: bool = False
    has_paper: bool = False
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "created_at": self.created_at,
            "record_type": self.record_type,
            "request_id": self.request_id,
            "task_ids": list(self.task_ids),
            "symbol": self.symbol,
            "status": self.status,
            "quality_label": self.quality_label,
            "review_outcome": self.review_outcome,
            "review_priority": self.review_priority,
            "final_answer_sha256": self.final_answer_sha256,
            "source_refs_count": self.source_refs_count,
            "safety_flags": list(self.safety_flags),
            "has_journal": self.has_journal,
            "has_backtest": self.has_backtest,
            "has_paper": self.has_paper,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class EvaluationDashboardDetail:
    registry_id: str
    record_type: str
    request_id: str
    final_answer_sha256: str
    task_index: List[Dict[str, Any]] = field(default_factory=list)
    safety_index: Dict[str, Any] = field(default_factory=dict)
    evaluation_index: Dict[str, Any] = field(default_factory=dict)
    hashes: Dict[str, str] = field(default_factory=dict)
    source_refs: List[str] = field(default_factory=list)
    agent_refs: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    linked_records: List[str] = field(default_factory=list)
    chain_status: Dict[str, bool] = field(default_factory=dict)
    replay_available: bool = False
    export_safe: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "record_type": self.record_type,
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "task_index": list(self.task_index),
            "safety_index": dict(self.safety_index),
            "evaluation_index": dict(self.evaluation_index),
            "hashes": dict(self.hashes),
            "source_refs": list(self.source_refs),
            "agent_refs": list(self.agent_refs),
            "limitations": list(self.limitations),
            "linked_records": list(self.linked_records),
            "chain_status": dict(self.chain_status),
            "replay_available": self.replay_available,
            "export_safe": self.export_safe,
        }


@dataclass
class EvaluationChainView:
    request_id: str
    final_answer_sha256: str
    journal_records: List[str] = field(default_factory=list)
    backtest_records: List[str] = field(default_factory=list)
    paper_records: List[str] = field(default_factory=list)
    chain_completeness: Dict[str, bool] = field(default_factory=dict)
    task_chain: List[Dict[str, Any]] = field(default_factory=list)
    review_priority: str = "LOW"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "journal_records": list(self.journal_records),
            "backtest_records": list(self.backtest_records),
            "paper_records": list(self.paper_records),
            "chain_completeness": dict(self.chain_completeness),
            "task_chain": list(self.task_chain),
            "review_priority": self.review_priority,
        }


@dataclass
class EvaluationReplayView:
    replay_id: str
    status: str
    compared_fields: List[str] = field(default_factory=list)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    generated_records_summary: List[Dict[str, Any]] = field(default_factory=list)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "status": self.status,
            "compared_fields": list(self.compared_fields),
            "mismatches": list(self.mismatches),
            "generated_records_summary": list(self.generated_records_summary),
            "safety_summary": dict(self.safety_summary),
            "latency_ms": self.latency_ms,
        }


@dataclass
class EvaluationExportPreview:
    export_id: str
    rows_count: int
    filters_used: Dict[str, Any] = field(default_factory=dict)
    redactions: int = 0
    payload_chars: int = 0
    safe_to_download: bool = True
    rows: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "export_id": self.export_id,
            "rows_count": self.rows_count,
            "filters_used": dict(self.filters_used),
            "redactions": self.redactions,
            "payload_chars": self.payload_chars,
            "safe_to_download": self.safe_to_download,
            "rows": list(self.rows),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, default=str)

    def to_csv(self) -> str:
        if not self.rows:
            return ""
        output = io.StringIO()
        fieldnames = sorted({key for row in self.rows for key in row.keys()})
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in self.rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
        return output.getvalue()


class EvaluationDashboardService:
    def __init__(
        self,
        registry: EvaluationRegistry | None = None,
        persistence_store: EvaluationPersistenceStore | None = None,
        human_review_store: HumanReviewStore | None = None,
    ):
        self.registry = registry or EvaluationRegistry()
        self.persistence_store = persistence_store or EvaluationPersistenceStore()
        self.human_review_store = human_review_store or HumanReviewStore(persistence_store=self.persistence_store)

    @classmethod
    def from_runtime_artifacts(cls, runtime_artifacts: Mapping[str, Any] | None) -> "EvaluationDashboardService":
        artifacts = dict(runtime_artifacts or {})
        stored = artifacts.get("evaluation_registry") if isinstance(artifacts.get("evaluation_registry"), Mapping) else {}
        return cls(EvaluationRegistry(stored.get("entries") or []))

    @classmethod
    def from_persistence_store(cls, persistence_store: EvaluationPersistenceStore) -> "EvaluationDashboardService":
        return cls(EvaluationRegistry(persistence_store.load_entries()), persistence_store)

    def load(self, filters: EvaluationDashboardFilters | Mapping[str, Any] | None = None) -> tuple[EvaluationDashboardSummary, List[EvaluationDashboardRow]]:
        started = time.perf_counter()
        dashboard_filters = _filters(filters)
        entries = self._filtered_entries(dashboard_filters)
        rows = [self._row(entry) for entry in entries[: max(0, dashboard_filters.limit or 100)]]
        summary = self._summary(entries)
        print(
            "[EvaluationDashboard] "
            f"action=load entries={len(entries)} filters={dashboard_filters.as_dict()} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return summary, rows

    def detail(self, registry_id: str) -> EvaluationDashboardDetail | None:
        started = time.perf_counter()
        entry = self.registry.get_registry_entry(registry_id)
        if not entry:
            return None
        related = self.registry.list_registry_entries(
            {"request_id": entry.request_id, "final_answer_sha256": entry.final_answer_sha256}
        )
        detail = EvaluationDashboardDetail(
            registry_id=entry.registry_id,
            record_type=entry.record_type,
            request_id=entry.request_id,
            final_answer_sha256=entry.final_answer_sha256,
            task_index=[task.as_dict() for task in entry.task_index],
            safety_index=dict(entry.safety_index),
            evaluation_index=dict(entry.evaluation_index),
            hashes=dict(entry.hashes),
            source_refs=_ordered_unique(ref for task in entry.task_index for ref in task.source_refs),
            agent_refs=_ordered_unique(ref for task in entry.task_index for ref in task.agent_refs),
            limitations=list(entry.limitations),
            linked_records=[item.registry_id for item in related],
            chain_status=_chain_status(related),
            replay_available=bool(entry.request_id and entry.final_answer_sha256),
            export_safe=not bool(entry.safety_index.get("prohibited_outputs_detected")),
        )
        print(
            "[EvaluationDashboard] "
            f"action=detail registry_id={registry_id} status=PASS "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return detail

    def chain_view(self, request_id: str = "", final_answer_sha256: str = "") -> List[EvaluationChainView]:
        started = time.perf_counter()
        entries = self.registry.list_registry_entries({})
        if request_id:
            entries = [entry for entry in entries if entry.request_id == request_id]
        if final_answer_sha256:
            entries = [entry for entry in entries if entry.final_answer_sha256 == final_answer_sha256]
        groups: Dict[tuple[str, str], List[EvaluationRegistryEntry]] = {}
        for entry in entries:
            groups.setdefault((entry.request_id, entry.final_answer_sha256), []).append(entry)
        chains = [self._chain(key[0], key[1], group) for key, group in sorted(groups.items())]
        print(
            "[EvaluationDashboard] "
            f"action=chain_view request_id={request_id} records={len(entries)} "
            f"chain_status=PASS latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return chains

    def replay_view(self, replay_case: EvaluationReplayCase | Mapping[str, Any]) -> EvaluationReplayView:
        result = EvaluationReplayHarness.replay(replay_case)
        return replay_view_from_result(result)

    def export_preview(self, filters: EvaluationDashboardFilters | Mapping[str, Any] | None = None) -> EvaluationExportPreview:
        started = time.perf_counter()
        dashboard_filters = _filters(filters)
        registry_filters = _registry_filters(dashboard_filters)
        dataset = self.registry.export_review_dataset(registry_filters)
        rows = [_safe_row(row) for row in dataset.rows]
        preview = EvaluationExportPreview(
            export_id=dataset.export_id,
            rows_count=len(rows),
            filters_used=dashboard_filters.as_dict(),
            redactions=dataset.redactions,
            payload_chars=dataset.payload_chars,
            safe_to_download=not _contains_forbidden_export_fields(rows),
            rows=rows,
        )
        print(
            "[EvaluationDashboard] "
            f"action=export rows={preview.rows_count} redactions={preview.redactions} "
            f"payload_chars={preview.payload_chars} status={'PASS' if preview.safe_to_download else 'WARN'} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return preview

    def save_current_records(self) -> PersistBatchResult:
        return self.persistence_store.save_entries(self.registry.list_registry_entries({}))

    def load_persisted_records(self, filters: Mapping[str, Any] | None = None) -> tuple[EvaluationDashboardSummary, List[EvaluationDashboardRow]]:
        self.registry = EvaluationRegistry(self.persistence_store.load_entries(filters or {}))
        return self.load()

    def validate_persistence_store(self) -> ValidationResult:
        return self.persistence_store.validate_store()

    def create_dataset_version(self, name: str, description: str = "", filters: EvaluationDashboardFilters | Mapping[str, Any] | None = None):
        dashboard_filters = _filters(filters)
        return self.persistence_store.create_dataset_version(name, description, _registry_filters(dashboard_filters))

    def list_dataset_versions(self):
        return self.persistence_store.list_dataset_versions()

    def export_dataset_version(self, version_id: str, format: str = "json") -> ExportResult:
        return self.persistence_store.export_dataset_version(version_id, format)

    def import_dataset_export(self, path: str, validate_only: bool = False) -> ImportResult:
        result = self.persistence_store.import_dataset_export(path, validate_only=validate_only)
        if result.status == "IMPORTED":
            self.registry = EvaluationRegistry(self.persistence_store.load_entries())
        return result

    def review_history(self, registry_id: str):
        return self.human_review_store.get_annotations_for_registry_id(registry_id)

    def workflow_state(self, registry_id: str):
        return self.human_review_store.get_workflow_state(registry_id)

    def review_batch_summary(self):
        return self.human_review_store.batch_summary()

    def reason_codes(self):
        return [reason.as_dict() for reason in REASON_CODE_TAXONOMY.values()]

    def save_review_annotation(self, registry_id: str, task_id: str, reviewer_id: str, **kwargs):
        entry = self.registry.get_registry_entry(registry_id)
        if not entry:
            raise ValueError(f"missing registry entry: {registry_id}")
        annotation = annotation_from_registry_entry(entry, task_id=task_id, reviewer_id=reviewer_id, **kwargs)
        return self.human_review_store.save_annotation(annotation)

    def lock_registry_review(self, registry_id: str):
        return self.human_review_store.lock_registry_review(registry_id)

    def create_annotated_dataset_version(self, name: str, filters: Mapping[str, Any] | None = None, locked: bool = False):
        return self.human_review_store.create_annotated_dataset_version(name, filters=filters or {}, locked=locked)

    def list_annotated_dataset_versions(self):
        return self.human_review_store.list_annotated_dataset_versions()

    def export_annotated_dataset(self, version_id: str, format: str = "json") -> ExportResult:
        return self.human_review_store.export_annotated_dataset(version_id, format)

    def import_annotations(self, path: str, validate_only: bool = False) -> ImportResult:
        return self.human_review_store.import_annotations(path, validate_only)

    def analytics_report(self, filters: EvaluationDashboardFilters | Mapping[str, Any] | ReviewAnalyticsFilters | None = None) -> QualityMetricsReport:
        started = time.perf_counter()
        analytics_filters = _analytics_filters(filters)
        entries = self.registry.list_registry_entries(_registry_filters(_filters(filters if not isinstance(filters, ReviewAnalyticsFilters) else {})))
        engine = ReviewAnalyticsEngine(
            registry_entries=entries,
            annotations=self.human_review_store.load_annotations(),
            workflow_states=self.human_review_store.list_workflow_states(),
            dataset_versions=self.persistence_store.list_dataset_versions(),
            annotated_dataset_versions=self.human_review_store.list_annotated_dataset_versions(),
        )
        report = engine.compute(analytics_filters)
        print(
            "[EvaluationDashboard] "
            f"action=analytics_load report_id={report.report_id} health={report.dataset_quality.dataset_health_label} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return report

    def export_analytics_report(self, report: QualityMetricsReport, format: str = "json") -> QualityMetricsExport:
        return ReviewAnalyticsEngine().export_report(report, format=format)

    def system_health_report(
        self,
        selected_registry_id: str = "",
        runtime_artifacts: Mapping[str, Any] | None = None,
    ) -> tuple[SystemIntegrityReport, RecoveryPlan]:
        started = time.perf_counter()
        hardening = SystemHardeningService()
        persistence_report = hardening.validate_persistence_stores(
            registry_path=self.persistence_store.registry_path,
            dataset_manifest_path=self.persistence_store.manifest_path,
            annotation_path=self.human_review_store.annotation_path,
            workflow_state_path=self.human_review_store.workflow_state_path,
            annotated_version_path=self.human_review_store.annotated_version_path,
        )
        dashboard_report = hardening.validate_dashboard_state(
            registry_entries=self.registry.list_registry_entries({}),
            selected_registry_id=selected_registry_id,
            runtime_artifacts=runtime_artifacts,
        )
        report = hardening._combine_reports([persistence_report, dashboard_report], started, "evaluation_dashboard_health")
        plan = hardening.plan_recovery(report)
        print(
            "[EvaluationDashboard] "
            f"action=system_health status={report.status} issues={len(report.issues)} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return report, plan

    def export_system_diagnostic(
        self,
        integrity_report: SystemIntegrityReport | Mapping[str, Any],
        recovery_plan: RecoveryPlan | Mapping[str, Any] | None = None,
    ) -> DiagnosticReport:
        return SystemHardeningService().export_diagnostic_report(integrity_report, recovery_plan)

    def _filtered_entries(self, filters: EvaluationDashboardFilters) -> List[EvaluationRegistryEntry]:
        entries = self.registry.list_registry_entries(_registry_filters(filters))
        if filters.needs_review_only:
            needs = {entry.registry_id for entry in self.registry.filter_needs_review()}
            entries = [entry for entry in entries if entry.registry_id in needs]
        if filters.review_priority:
            entries = [entry for entry in entries if review_priority(entry) == filters.review_priority.upper()]
        if filters.task_id:
            entries = [entry for entry in entries if filters.task_id in entry.task_ids]
        if filters.intent_family:
            entries = [entry for entry in entries if any(task.intent_family == filters.intent_family for task in entry.task_index)]
        if filters.safety_flag:
            entries = [entry for entry in entries if entry.safety_index.get(filters.safety_flag)]
        if filters.review_status:
            states = {state.registry_id: state for state in self.human_review_store.list_workflow_states()}
            entries = [entry for entry in entries if states.get(entry.registry_id) and states[entry.registry_id].current_status == filters.review_status]
        if filters.severity:
            states = {state.registry_id: state for state in self.human_review_store.list_workflow_states()}
            entries = [entry for entry in entries if states.get(entry.registry_id) and states[entry.registry_id].highest_severity == filters.severity]
        if filters.created_after:
            entries = [entry for entry in entries if _date_gte(entry.created_at, filters.created_after)]
        if filters.created_before:
            entries = [entry for entry in entries if _date_lte(entry.created_at, filters.created_before)]
        return entries

    def _summary(self, entries: Sequence[EvaluationRegistryEntry]) -> EvaluationDashboardSummary:
        symbols: List[str] = []
        for entry in entries:
            if entry.symbol:
                symbols.append(entry.symbol)
            symbols.extend(task.symbol for task in entry.task_index if task.symbol)
        return EvaluationDashboardSummary(
            total_entries=len(entries),
            by_record_type=_counts(entry.record_type for entry in entries),
            by_status=_counts(entry.status for entry in entries),
            by_quality_label=_counts(entry.quality_label for entry in entries),
            needs_review_count=sum(1 for entry in entries if review_priority(entry) in {"HIGH", "MEDIUM"}),
            safety_flag_count=sum(1 for entry in entries if _safety_flags(entry.safety_index)),
            symbols=sorted(_ordered_unique(symbols)),
            recent_request_ids=_ordered_unique(entry.request_id for entry in sorted(entries, key=lambda item: item.created_at, reverse=True))[:5],
            execution_allowed=any(entry.execution_allowed for entry in entries),
        )

    def _row(self, entry: EvaluationRegistryEntry) -> EvaluationDashboardRow:
        chain = self.registry.list_registry_entries({"request_id": entry.request_id, "final_answer_sha256": entry.final_answer_sha256})
        record_types = {item.record_type for item in chain}
        return EvaluationDashboardRow(
            registry_id=entry.registry_id,
            created_at=entry.created_at,
            record_type=entry.record_type,
            request_id=entry.request_id,
            task_ids=list(entry.task_ids),
            symbol=entry.symbol or _first(task.symbol for task in entry.task_index),
            status=entry.status,
            quality_label=entry.quality_label,
            review_outcome=entry.review_outcome,
            review_priority=review_priority(entry),
            final_answer_sha256=entry.final_answer_sha256,
            source_refs_count=len(_ordered_unique(ref for task in entry.task_index for ref in task.source_refs)),
            safety_flags=_safety_flags(entry.safety_index),
            has_journal="journal_review" in record_types,
            has_backtest="backtest_evaluation" in record_types,
            has_paper="paper_trading_evaluation" in record_types,
            execution_allowed=entry.execution_allowed,
        )

    def _chain(self, request_id: str, final_hash: str, entries: Sequence[EvaluationRegistryEntry]) -> EvaluationChainView:
        task_ids = _ordered_unique(task_id for entry in entries for task_id in entry.task_ids)
        task_chain = []
        for task_id in task_ids:
            task_entries = [(entry, task) for entry in entries for task in entry.task_index if task.task_id == task_id]
            intent = _first(task.intent_family for _, task in task_entries)
            symbol = _first(task.symbol for _, task in task_entries)
            safety = _ordered_unique(flag for entry, _ in task_entries for flag in _safety_flags(entry.safety_index))
            source_refs = _ordered_unique(ref for _, task in task_entries for ref in task.source_refs)
            statuses = {entry.record_type: task.status or entry.status for entry, task in task_entries}
            qualities = [task.quality_label or entry.quality_label for entry, task in task_entries]
            task_chain.append(
                {
                    "task_id": task_id,
                    "intent_family": intent,
                    "symbol": symbol,
                    "journal_status": statuses.get("journal_review", "MISSING"),
                    "backtest_status": statuses.get("backtest_evaluation", "NOT_APPLICABLE" if intent in {"book_concept_explanation", "static_explanation"} else "MISSING"),
                    "paper_status": statuses.get("paper_trading_evaluation", "NOT_APPLICABLE" if intent in {"book_concept_explanation", "static_explanation"} else "MISSING"),
                    "quality_label": _first(qualities),
                    "needs_review": any(review_priority(entry) in {"HIGH", "MEDIUM"} for entry, _ in task_entries),
                    "safety_flags": safety,
                    "source_refs": source_refs,
                }
            )
        return EvaluationChainView(
            request_id=request_id,
            final_answer_sha256=final_hash,
            journal_records=[entry.registry_id for entry in entries if entry.record_type == "journal_review"],
            backtest_records=[entry.registry_id for entry in entries if entry.record_type == "backtest_evaluation"],
            paper_records=[entry.registry_id for entry in entries if entry.record_type == "paper_trading_evaluation"],
            chain_completeness=_chain_status(entries),
            task_chain=task_chain,
            review_priority=_max_priority(review_priority(entry) for entry in entries),
        )


def replay_view_from_result(result: ReplayResult | Mapping[str, Any]) -> EvaluationReplayView:
    data = result.as_dict() if hasattr(result, "as_dict") else dict(result or {})
    return EvaluationReplayView(
        replay_id=str(data.get("replay_id") or ""),
        status=str(data.get("status") or ""),
        compared_fields=[str(value) for value in data.get("compared_fields") or []],
        mismatches=[dict(value) for value in data.get("mismatches") or [] if isinstance(value, Mapping)],
        generated_records_summary=[
            {
                "record_type": record.get("record_type") or record.get("evaluation_type") or "",
                "status": record.get("status", ""),
                "quality_label": record.get("quality_label", ""),
                "request_id": record.get("request_id", ""),
            }
            for record in data.get("generated_records") or []
            if isinstance(record, Mapping)
        ],
        safety_summary=dict(data.get("safety_summary") or {}),
        latency_ms=float(data.get("latency_ms") or 0.0),
    )


def review_priority(entry: EvaluationRegistryEntry) -> str:
    flags = _safety_flags(entry.safety_index)
    if (
        entry.execution_allowed
        or flags
        or entry.status in HIGH_REVIEW_STATUSES
        or entry.quality_label in HIGH_QUALITY_FLAGS
        or "missing_source_reference" in entry.limitations
        or entry.evaluation_index.get("review_priority") == "high"
    ):
        return "HIGH"
    if (
        entry.status in MEDIUM_REVIEW_STATUSES
        or entry.quality_label in MEDIUM_QUALITY_FLAGS
        or entry.evaluation_index.get("review_priority") == "medium"
        or entry.evaluation_index.get("risk_materialization") in {"materialized", "partially_materialized"}
        or entry.evaluation_index.get("confidence_calibration") in {"overconfident", "underconfident"}
    ):
        return "MEDIUM"
    return "LOW"


def _filters(filters: EvaluationDashboardFilters | Mapping[str, Any] | None) -> EvaluationDashboardFilters:
    if isinstance(filters, EvaluationDashboardFilters):
        return filters
    return EvaluationDashboardFilters(**{key: value for key, value in dict(filters or {}).items() if key in EvaluationDashboardFilters.__dataclass_fields__})


def _registry_filters(filters: EvaluationDashboardFilters) -> Dict[str, Any]:
    return {
        key: value
        for key, value in {
            "request_id": filters.request_id,
            "final_answer_sha256": filters.final_answer_sha256,
            "symbol": filters.symbol,
            "record_type": filters.record_type,
            "status": filters.status,
            "quality_label": filters.quality_label,
        }.items()
        if value
    }


def _analytics_filters(filters: EvaluationDashboardFilters | Mapping[str, Any] | ReviewAnalyticsFilters | None) -> ReviewAnalyticsFilters:
    if isinstance(filters, ReviewAnalyticsFilters):
        return filters
    dashboard_filters = _filters(filters)
    return ReviewAnalyticsFilters(
        request_id=dashboard_filters.request_id,
        final_answer_sha256=dashboard_filters.final_answer_sha256,
        task_id=dashboard_filters.task_id,
        record_type=dashboard_filters.record_type,
        intent_family=dashboard_filters.intent_family,
        symbol=dashboard_filters.symbol,
        review_status=dashboard_filters.review_status,
        quality_decision=dashboard_filters.quality_label,
        safety_label="UNSAFE" if dashboard_filters.safety_flag == "unsafe" else "",
        severity=dashboard_filters.severity,
        limit=dashboard_filters.limit,
    )


def _chain_status(entries: Sequence[EvaluationRegistryEntry]) -> Dict[str, bool]:
    types = {entry.record_type for entry in entries}
    return {
        "has_journal": "journal_review" in types,
        "has_backtest": "backtest_evaluation" in types,
        "has_paper": "paper_trading_evaluation" in types,
    }


def _safety_flags(index: Mapping[str, Any]) -> List[str]:
    return [key for key, value in index.items() if value and (key.endswith("_detected") or key in {"execution_allowed", "prohibited_outputs_detected"})]


def _counts(values: Iterable[str]) -> Dict[str, int]:
    output: Dict[str, int] = {}
    for value in values:
        if value:
            output[value] = output.get(value, 0) + 1
    return output


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _first(values: Iterable[Any]) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _date_gte(value: str, threshold: str) -> bool:
    return _parse_dt(value) >= _parse_dt(threshold)


def _date_lte(value: str, threshold: str) -> bool:
    return _parse_dt(value) <= _parse_dt(threshold)


def _parse_dt(value: str) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def _max_priority(values: Iterable[str]) -> str:
    priorities = list(values)
    if "HIGH" in priorities:
        return "HIGH"
    if "MEDIUM" in priorities:
        return "MEDIUM"
    return "LOW"


def _safe_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    banned = {"raw_prompt", "full_prompt", "hidden_prompt", "final_answer_text", "raw_final_answer", "account_balance", "order_id", "mt5_credentials"}
    return {key: value for key, value in dict(row).items() if key not in banned}


def _contains_forbidden_export_fields(rows: Sequence[Mapping[str, Any]]) -> bool:
    forbidden = {"raw_prompt", "full_prompt", "hidden_prompt", "final_answer_text", "account_balance", "order_id", "mt5_credentials"}
    blob = json.dumps(rows, ensure_ascii=False, default=str).lower()
    return any(item in blob for item in forbidden)


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return "" if value is None else str(value)
