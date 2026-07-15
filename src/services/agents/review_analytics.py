from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_persistence import (
    EvaluationDatasetVersion,
    REGISTRY_SAFETY_PATTERNS,
    SECRET_PATTERNS,
    UNSAFE_FIELD_NAMES,
)
from src.services.agents.evaluation_registry import EvaluationRegistryEntry
from src.services.agents.human_review import (
    AnnotatedDatasetVersion,
    HumanReviewAnnotation,
    REASON_CODE_TAXONOMY,
    ReviewWorkflowState,
)


QUALITY_ANALYTICS_SCHEMA_VERSION = "review_analytics.v1"
DEFAULT_ANALYTICS_EXPORT_DIR = Path("data") / "evaluations" / "analytics"

QUALITY_SCORES = {
    "HIGH_QUALITY": 1.0,
    "ACCEPTABLE": 0.8,
    "ACCEPTABLE_WITH_WARNINGS": 0.6,
    "LOW_QUALITY": 0.3,
    "INVALID": 0.0,
    "UNSAFE": 0.0,
}
CORRECTNESS_SCORES = {
    "CORRECT": 1.0,
    "PARTIALLY_CORRECT": 0.5,
    "INCORRECT": 0.0,
    "UNSUPPORTED": 0.0,
    "UNCLEAR": 0.25,
}
GROUNDING_ISSUES = {"POORLY_GROUNDED", "MISSING_SOURCE"}
SAFETY_ISSUES = {"WARNING", "UNSAFE"}
TASK_SCOPE_ISSUES = {"POSSIBLE_LEAKAGE", "TASK_SCOPE_FAIL"}
STATIC_INTENTS = {"book_concept_explanation", "static_explanation", "static_knowledge"}
EVALUATION_REASON_CODES = {
    "BACKTEST_DISAGREES_WITH_THESIS",
    "PAPER_EVAL_INVALIDATION_OBSERVED",
    "RISK_MATERIALIZED",
    "CONFIDENCE_CALIBRATION_WEAK",
    "REPLAY_MISMATCH",
}
SYSTEM_QUALITY_RECOMMENDATIONS = {
    "grounding": "Review source grounding for tasks with MISSING_SOURCE_REFERENCE or weak support.",
    "task_scope": "Inspect multi-intent routing because task leakage was detected.",
    "safety": "Review compliance prompts because trading-instruction or execution-language issues were annotated.",
    "coverage": "Increase human review coverage before using this dataset for evaluation.",
    "evaluation": "Review evaluation consistency records where backtest or paper follow-up disagrees with the original thesis.",
}


@dataclass
class ReviewAnalyticsFilters:
    request_id: str = ""
    final_answer_sha256: str = ""
    registry_id: str = ""
    task_id: str = ""
    record_type: str = ""
    intent_family: str = ""
    symbol: str = ""
    reviewer_id: str = ""
    review_status: str = ""
    quality_decision: str = ""
    correctness_label: str = ""
    grounding_label: str = ""
    safety_label: str = ""
    task_scope_label: str = ""
    reason_code: str = ""
    severity: str = ""
    created_after: str = ""
    created_before: str = ""
    dataset_version_id: str = ""
    annotated_dataset_version_id: str = ""
    limit: int = 1000

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "registry_id": self.registry_id,
            "task_id": self.task_id,
            "record_type": self.record_type,
            "intent_family": self.intent_family,
            "symbol": self.symbol,
            "reviewer_id": self.reviewer_id,
            "review_status": self.review_status,
            "quality_decision": self.quality_decision,
            "correctness_label": self.correctness_label,
            "grounding_label": self.grounding_label,
            "safety_label": self.safety_label,
            "task_scope_label": self.task_scope_label,
            "reason_code": self.reason_code,
            "severity": self.severity,
            "created_after": self.created_after,
            "created_before": self.created_before,
            "dataset_version_id": self.dataset_version_id,
            "annotated_dataset_version_id": self.annotated_dataset_version_id,
            "limit": self.limit,
        }


@dataclass
class ReviewCoverageMetrics:
    total_registry_entries: int = 0
    annotated_entries: int = 0
    unreviewed_entries: int = 0
    annotation_coverage_rate: float = 0.0
    locked_reviews: int = 0
    locked_rate: float = 0.0
    reviewed_by_status: Dict[str, int] = field(default_factory=dict)
    reviewed_by_reviewer: Dict[str, int] = field(default_factory=dict)
    execution_allowed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class QualityDecisionMetrics:
    high_quality_count: int = 0
    acceptable_count: int = 0
    acceptable_with_warnings_count: int = 0
    low_quality_count: int = 0
    invalid_count: int = 0
    unsafe_count: int = 0
    not_applicable_count: int = 0
    quality_score: float = 0.0
    quality_distribution: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class CorrectnessMetrics:
    correct_count: int = 0
    partially_correct_count: int = 0
    incorrect_count: int = 0
    unsupported_count: int = 0
    unclear_count: int = 0
    not_applicable_count: int = 0
    correctness_score: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class GroundingMetrics:
    well_grounded_count: int = 0
    partially_grounded_count: int = 0
    poorly_grounded_count: int = 0
    missing_source_count: int = 0
    grounding_issue_rate: float = 0.0
    source_issue_rate: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class SafetyMetrics:
    safe_count: int = 0
    warning_count: int = 0
    unsafe_count: int = 0
    safety_issue_rate: float = 0.0
    trading_instruction_issue_count: int = 0
    entry_sl_tp_issue_count: int = 0
    position_sizing_issue_count: int = 0
    account_risk_issue_count: int = 0
    mt5_order_language_issue_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class TaskScopeMetrics:
    task_scope_ok_count: int = 0
    possible_leakage_count: int = 0
    task_scope_fail_count: int = 0
    task_leakage_rate: float = 0.0
    static_task_market_leakage_count: int = 0
    multi_intent_leakage_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class ReasonCodeMetrics:
    total_reason_codes: int = 0
    reason_code_counts: Dict[str, int] = field(default_factory=dict)
    reason_category_counts: Dict[str, int] = field(default_factory=dict)
    top_reason_codes: List[Dict[str, Any]] = field(default_factory=list)
    high_severity_reason_codes: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class EvaluationConsistencyMetrics:
    backtest_disagreement_count: int = 0
    paper_invalidation_count: int = 0
    risk_materialized_count: int = 0
    confidence_calibration_weak_count: int = 0
    replay_mismatch_count: int = 0
    evaluation_issue_rate: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class DatasetQualityMetrics:
    dataset_id: str = ""
    entries_count: int = 0
    reviewed_count: int = 0
    coverage_rate: float = 0.0
    quality_score: float = 0.0
    grounding_issue_rate: float = 0.0
    safety_issue_rate: float = 0.0
    task_leakage_rate: float = 0.0
    high_severity_rate: float = 0.0
    dataset_health_label: str = "NEEDS_REVIEW"
    dataset_hash: str = ""
    annotation_hash: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class ReviewerDisagreement:
    registry_id: str
    task_id: str
    label_field: str
    reviewer_values: Dict[str, str] = field(default_factory=dict)
    severity: str = "LOW"

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class ReviewerActivityMetrics:
    reviewer_count: int = 0
    annotations_by_reviewer: Dict[str, int] = field(default_factory=dict)
    approval_rate_by_reviewer: Dict[str, float] = field(default_factory=dict)
    rejection_rate_by_reviewer: Dict[str, float] = field(default_factory=dict)
    high_severity_by_reviewer: Dict[str, int] = field(default_factory=dict)
    reviewer_disagreement_count: int = 0
    reviewer_disagreement_rate: float = 0.0
    disagreements: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class QualityMetricsReport:
    report_id: str
    created_at: str
    filters_used: Dict[str, Any] = field(default_factory=dict)
    coverage: ReviewCoverageMetrics = field(default_factory=ReviewCoverageMetrics)
    quality: QualityDecisionMetrics = field(default_factory=QualityDecisionMetrics)
    correctness: CorrectnessMetrics = field(default_factory=CorrectnessMetrics)
    grounding: GroundingMetrics = field(default_factory=GroundingMetrics)
    safety: SafetyMetrics = field(default_factory=SafetyMetrics)
    task_scope: TaskScopeMetrics = field(default_factory=TaskScopeMetrics)
    reason_codes: ReasonCodeMetrics = field(default_factory=ReasonCodeMetrics)
    evaluation_consistency: EvaluationConsistencyMetrics = field(default_factory=EvaluationConsistencyMetrics)
    dataset_quality: DatasetQualityMetrics = field(default_factory=DatasetQualityMetrics)
    reviewer_activity: ReviewerActivityMetrics = field(default_factory=ReviewerActivityMetrics)
    task_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    intent_family_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    symbol_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_allowed: bool = False
    latency_ms: float = 0.0
    schema_version: str = QUALITY_ANALYTICS_SCHEMA_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "created_at": self.created_at,
            "filters_used": dict(self.filters_used),
            "coverage": self.coverage.as_dict(),
            "quality": self.quality.as_dict(),
            "correctness": self.correctness.as_dict(),
            "grounding": self.grounding.as_dict(),
            "safety": self.safety.as_dict(),
            "task_scope": self.task_scope.as_dict(),
            "reason_codes": self.reason_codes.as_dict(),
            "evaluation_consistency": self.evaluation_consistency.as_dict(),
            "dataset_quality": self.dataset_quality.as_dict(),
            "reviewer_activity": self.reviewer_activity.as_dict(),
            "task_breakdown": dict(self.task_breakdown),
            "intent_family_breakdown": dict(self.intent_family_breakdown),
            "symbol_breakdown": dict(self.symbol_breakdown),
            "recommendations": list(self.recommendations),
            "warnings": list(self.warnings),
            "execution_allowed": self.execution_allowed,
            "latency_ms": self.latency_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True, default=str)


@dataclass
class QualityMetricsExport:
    export_id: str
    created_at: str
    report_id: str
    filters_used: Dict[str, Any] = field(default_factory=dict)
    dataset_version_id: str = ""
    annotated_dataset_version_id: str = ""
    metrics_summary: Dict[str, Any] = field(default_factory=dict)
    breakdowns: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    execution_allowed: bool = False
    payload_chars: int = 0
    export_path: str = ""
    format: str = "json"
    status: str = "EXPORTED"

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


class ReviewAnalyticsEngine:
    def __init__(
        self,
        registry_entries: Sequence[EvaluationRegistryEntry | Mapping[str, Any]] | None = None,
        annotations: Sequence[HumanReviewAnnotation | Mapping[str, Any]] | None = None,
        workflow_states: Sequence[ReviewWorkflowState | Mapping[str, Any]] | None = None,
        dataset_versions: Sequence[EvaluationDatasetVersion | Mapping[str, Any]] | None = None,
        annotated_dataset_versions: Sequence[AnnotatedDatasetVersion | Mapping[str, Any]] | None = None,
    ):
        self.registry_entries = [_entry(item) for item in registry_entries or []]
        self.annotations = [_annotation(item) for item in annotations or []]
        self.workflow_states = [_state(item) for item in workflow_states or []]
        self.dataset_versions = [_dataset_version(item) for item in dataset_versions or []]
        self.annotated_dataset_versions = [_annotated_version(item) for item in annotated_dataset_versions or []]

    def compute(self, filters: ReviewAnalyticsFilters | Mapping[str, Any] | None = None) -> QualityMetricsReport:
        started = time.perf_counter()
        analytics_filters = _filters(filters)
        entries = _filter_entries(self.registry_entries, analytics_filters, self.dataset_versions)
        annotations = _filter_annotations(self.annotations, analytics_filters, entries, self.annotated_dataset_versions)
        states = _filter_states(self.workflow_states, entries)

        coverage = _coverage_metrics(entries, annotations, states)
        quality = _quality_metrics(annotations)
        correctness = _correctness_metrics(annotations)
        grounding = _grounding_metrics(annotations)
        safety = _safety_metrics(annotations)
        task_scope = _task_scope_metrics(annotations, entries)
        reason_codes = _reason_code_metrics(annotations)
        evaluation_consistency = _evaluation_consistency_metrics(annotations)
        reviewer_activity = _reviewer_activity_metrics(annotations)
        task_breakdown = _breakdown(entries, annotations, "task_id")
        intent_breakdown = _intent_breakdown(entries, annotations)
        symbol_breakdown = _symbol_breakdown(entries, annotations)
        dataset_quality = _dataset_quality_metrics(
            analytics_filters,
            entries,
            annotations,
            coverage,
            quality,
            grounding,
            safety,
            task_scope,
            self.dataset_versions,
            self.annotated_dataset_versions,
        )
        recommendations = _recommendations(coverage, grounding, safety, task_scope, evaluation_consistency)
        warnings = _warnings(entries, annotations, reason_codes)
        created_at = datetime.now(timezone.utc).isoformat()
        report_id = f"quality_metrics:{_hash_payload([analytics_filters.as_dict(), [entry.registry_id for entry in entries], [item.annotation_id for item in annotations]])[:16]}"
        report = QualityMetricsReport(
            report_id=report_id,
            created_at=created_at,
            filters_used=analytics_filters.as_dict(),
            coverage=coverage,
            quality=quality,
            correctness=correctness,
            grounding=grounding,
            safety=safety,
            task_scope=task_scope,
            reason_codes=reason_codes,
            evaluation_consistency=evaluation_consistency,
            dataset_quality=dataset_quality,
            reviewer_activity=reviewer_activity,
            task_breakdown=task_breakdown,
            intent_family_breakdown=intent_breakdown,
            symbol_breakdown=symbol_breakdown,
            recommendations=recommendations,
            warnings=warnings,
            execution_allowed=coverage.execution_allowed,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        print(
            "[ReviewAnalytics] "
            f"action=compute entries={len(entries)} annotations={len(annotations)} "
            f"filters={analytics_filters.as_dict()} health={report.dataset_quality.dataset_health_label} "
            f"latency_ms={report.latency_ms}"
        )
        return report

    def export_report(self, report: QualityMetricsReport, export_dir: str | Path | None = None, format: str = "json") -> QualityMetricsExport:
        started = time.perf_counter()
        export_format = format.lower()
        if export_format != "json":
            return QualityMetricsExport(
                export_id=f"quality_metrics_export:{report.report_id}:failed",
                created_at=datetime.now(timezone.utc).isoformat(),
                report_id=report.report_id,
                filters_used=report.filters_used,
                warnings=["unsupported_format"],
                execution_allowed=report.execution_allowed,
                status="FAILED",
                format=export_format,
            )
        payload = _safe_report_payload(report)
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        unsafe = _unsafe_warnings(payload)
        status = "EXPORTED" if not unsafe else "REJECTED_UNSAFE"
        path = ""
        if status == "EXPORTED":
            output_dir = Path(export_dir or DEFAULT_ANALYTICS_EXPORT_DIR)
            output_dir.mkdir(parents=True, exist_ok=True)
            path_obj = output_dir / f"{_safe_filename(report.report_id)}.json"
            path_obj.write_text(text, encoding="utf-8")
            path = str(path_obj)
        result = QualityMetricsExport(
            export_id=f"quality_metrics_export:{report.report_id}",
            created_at=datetime.now(timezone.utc).isoformat(),
            report_id=report.report_id,
            filters_used=dict(report.filters_used),
            dataset_version_id=str(report.filters_used.get("dataset_version_id") or ""),
            annotated_dataset_version_id=str(report.filters_used.get("annotated_dataset_version_id") or ""),
            metrics_summary={
                "dataset_health_label": report.dataset_quality.dataset_health_label,
                "quality_score": report.quality.quality_score,
                "annotation_coverage_rate": report.coverage.annotation_coverage_rate,
                "safety_issue_rate": report.safety.safety_issue_rate,
                "grounding_issue_rate": report.grounding.grounding_issue_rate,
                "task_leakage_rate": report.task_scope.task_leakage_rate,
            },
            breakdowns={
                "task_breakdown": dict(report.task_breakdown),
                "intent_family_breakdown": dict(report.intent_family_breakdown),
                "symbol_breakdown": dict(report.symbol_breakdown),
                "reason_codes": report.reason_codes.as_dict(),
            },
            warnings=list(report.warnings) + unsafe,
            execution_allowed=report.execution_allowed,
            payload_chars=len(text),
            export_path=path,
            format=export_format,
            status=status,
        )
        print(
            "[ReviewAnalytics] "
            f"action=export report_id={report.report_id} format={export_format} "
            f"payload_chars={result.payload_chars} status={result.status} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return result


def _coverage_metrics(
    entries: Sequence[EvaluationRegistryEntry],
    annotations: Sequence[HumanReviewAnnotation],
    states: Sequence[ReviewWorkflowState],
) -> ReviewCoverageMetrics:
    annotated_registry_ids = {item.registry_id for item in annotations}
    state_by_id = {state.registry_id: state for state in states}
    reviewed_states = [state for state in state_by_id.values() if state.current_status != "UNREVIEWED"]
    return ReviewCoverageMetrics(
        total_registry_entries=len(entries),
        annotated_entries=sum(1 for entry in entries if entry.registry_id in annotated_registry_ids),
        unreviewed_entries=sum(1 for entry in entries if entry.registry_id not in annotated_registry_ids),
        annotation_coverage_rate=_rate(sum(1 for entry in entries if entry.registry_id in annotated_registry_ids), len(entries)),
        locked_reviews=sum(1 for state in state_by_id.values() if state.locked),
        locked_rate=_rate(sum(1 for state in state_by_id.values() if state.locked), len(entries)),
        reviewed_by_status=_counts(state.current_status for state in reviewed_states),
        reviewed_by_reviewer=_counts(item.reviewer_id for item in annotations),
        execution_allowed=any(entry.execution_allowed for entry in entries) or any(item.execution_allowed for item in annotations),
    )


def _quality_metrics(annotations: Sequence[HumanReviewAnnotation]) -> QualityDecisionMetrics:
    counts = _counts(item.quality_decision for item in annotations)
    return QualityDecisionMetrics(
        high_quality_count=counts.get("HIGH_QUALITY", 0),
        acceptable_count=counts.get("ACCEPTABLE", 0),
        acceptable_with_warnings_count=counts.get("ACCEPTABLE_WITH_WARNINGS", 0),
        low_quality_count=counts.get("LOW_QUALITY", 0),
        invalid_count=counts.get("INVALID", 0),
        unsafe_count=counts.get("UNSAFE", 0),
        not_applicable_count=counts.get("NOT_APPLICABLE", 0),
        quality_score=_score_average((item.quality_decision for item in annotations), QUALITY_SCORES),
        quality_distribution=counts,
    )


def _correctness_metrics(annotations: Sequence[HumanReviewAnnotation]) -> CorrectnessMetrics:
    counts = _counts(item.correctness_label for item in annotations)
    return CorrectnessMetrics(
        correct_count=counts.get("CORRECT", 0),
        partially_correct_count=counts.get("PARTIALLY_CORRECT", 0),
        incorrect_count=counts.get("INCORRECT", 0),
        unsupported_count=counts.get("UNSUPPORTED", 0),
        unclear_count=counts.get("UNCLEAR", 0),
        not_applicable_count=counts.get("NOT_APPLICABLE", 0),
        correctness_score=_score_average((item.correctness_label for item in annotations), CORRECTNESS_SCORES),
    )


def _grounding_metrics(annotations: Sequence[HumanReviewAnnotation]) -> GroundingMetrics:
    counts = _counts(item.grounding_label for item in annotations)
    denominator = sum(count for label, count in counts.items() if label != "NOT_APPLICABLE")
    source_issues = sum(1 for item in annotations if any(code in {"MISSING_SOURCE_REFERENCE", "WEAK_SOURCE_SUPPORT", "WRONG_SOURCE_USED", "CLAIM_NOT_SUPPORTED"} for code in item.reason_codes))
    return GroundingMetrics(
        well_grounded_count=counts.get("WELL_GROUNDED", 0),
        partially_grounded_count=counts.get("PARTIALLY_GROUNDED", 0),
        poorly_grounded_count=counts.get("POORLY_GROUNDED", 0),
        missing_source_count=counts.get("MISSING_SOURCE", 0),
        grounding_issue_rate=_rate(sum(counts.get(label, 0) for label in GROUNDING_ISSUES), denominator),
        source_issue_rate=_rate(source_issues, len(annotations)),
    )


def _safety_metrics(annotations: Sequence[HumanReviewAnnotation]) -> SafetyMetrics:
    counts = _counts(item.safety_label for item in annotations)
    denominator = sum(count for label, count in counts.items() if label != "NOT_APPLICABLE")
    code_counts = _counts(code for item in annotations for code in item.reason_codes)
    return SafetyMetrics(
        safe_count=counts.get("SAFE", 0),
        warning_count=counts.get("WARNING", 0),
        unsafe_count=counts.get("UNSAFE", 0),
        safety_issue_rate=_rate(sum(counts.get(label, 0) for label in SAFETY_ISSUES), denominator),
        trading_instruction_issue_count=code_counts.get("TRADING_INSTRUCTION_PRESENT", 0),
        entry_sl_tp_issue_count=code_counts.get("ENTRY_SL_TP_PRESENT", 0),
        position_sizing_issue_count=code_counts.get("POSITION_SIZING_PRESENT", 0),
        account_risk_issue_count=code_counts.get("ACCOUNT_RISK_PRESENT", 0),
        mt5_order_language_issue_count=code_counts.get("MT5_OR_ORDER_LANGUAGE_PRESENT", 0),
    )


def _task_scope_metrics(annotations: Sequence[HumanReviewAnnotation], entries: Sequence[EvaluationRegistryEntry]) -> TaskScopeMetrics:
    counts = _counts(item.task_scope_label for item in annotations)
    denominator = sum(count for label, count in counts.items() if label != "NOT_APPLICABLE")
    entry_task_map = _entry_task_map(entries)
    return TaskScopeMetrics(
        task_scope_ok_count=counts.get("TASK_SCOPE_OK", 0),
        possible_leakage_count=counts.get("POSSIBLE_LEAKAGE", 0),
        task_scope_fail_count=counts.get("TASK_SCOPE_FAIL", 0),
        task_leakage_rate=_rate(sum(counts.get(label, 0) for label in TASK_SCOPE_ISSUES), denominator),
        static_task_market_leakage_count=sum(1 for item in annotations if _static_market_leakage(item, entry_task_map)),
        multi_intent_leakage_count=sum(1 for item in annotations if "MULTI_INTENT_LEAKAGE" in item.reason_codes or item.task_scope_label in TASK_SCOPE_ISSUES),
    )


def _reason_code_metrics(annotations: Sequence[HumanReviewAnnotation]) -> ReasonCodeMetrics:
    counts = _counts(code for item in annotations for code in item.reason_codes)
    category_counts: Dict[str, int] = {}
    high: Dict[str, int] = {}
    for code, count in counts.items():
        reason = REASON_CODE_TAXONOMY.get(code)
        category = reason.category if reason else "Unknown"
        category_counts[category] = category_counts.get(category, 0) + count
        if reason and reason.severity_default in {"HIGH", "CRITICAL"}:
            high[code] = count
    top = [{"code": code, "count": count} for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]]
    return ReasonCodeMetrics(
        total_reason_codes=sum(counts.values()),
        reason_code_counts=counts,
        reason_category_counts=category_counts,
        top_reason_codes=top,
        high_severity_reason_codes=high,
    )


def _evaluation_consistency_metrics(annotations: Sequence[HumanReviewAnnotation]) -> EvaluationConsistencyMetrics:
    counts = _counts(code for item in annotations for code in item.reason_codes)
    issue_total = sum(counts.get(code, 0) for code in EVALUATION_REASON_CODES)
    return EvaluationConsistencyMetrics(
        backtest_disagreement_count=counts.get("BACKTEST_DISAGREES_WITH_THESIS", 0),
        paper_invalidation_count=counts.get("PAPER_EVAL_INVALIDATION_OBSERVED", 0),
        risk_materialized_count=counts.get("RISK_MATERIALIZED", 0),
        confidence_calibration_weak_count=counts.get("CONFIDENCE_CALIBRATION_WEAK", 0),
        replay_mismatch_count=counts.get("REPLAY_MISMATCH", 0),
        evaluation_issue_rate=_rate(issue_total, len(annotations)),
    )


def _dataset_quality_metrics(
    filters: ReviewAnalyticsFilters,
    entries: Sequence[EvaluationRegistryEntry],
    annotations: Sequence[HumanReviewAnnotation],
    coverage: ReviewCoverageMetrics,
    quality: QualityDecisionMetrics,
    grounding: GroundingMetrics,
    safety: SafetyMetrics,
    task_scope: TaskScopeMetrics,
    dataset_versions: Sequence[EvaluationDatasetVersion],
    annotated_versions: Sequence[AnnotatedDatasetVersion],
) -> DatasetQualityMetrics:
    high_severity = sum(1 for item in annotations if item.severity in {"HIGH", "CRITICAL"})
    health = _dataset_health(quality, grounding, safety, task_scope)
    dataset_hash = _hash_payload([entry.registry_id for entry in entries])
    annotation_hash = _hash_payload([item.as_dict() for item in annotations])
    if filters.dataset_version_id:
        version = next((item for item in dataset_versions if item.version_id == filters.dataset_version_id), None)
        if version and version.dataset_hash:
            dataset_hash = version.dataset_hash
    if filters.annotated_dataset_version_id:
        version = next((item for item in annotated_versions if item.version_id == filters.annotated_dataset_version_id), None)
        if version:
            dataset_hash = version.dataset_hash or dataset_hash
            annotation_hash = version.annotation_hash or annotation_hash
    return DatasetQualityMetrics(
        dataset_id=filters.annotated_dataset_version_id or filters.dataset_version_id or "current",
        entries_count=len(entries),
        reviewed_count=coverage.annotated_entries,
        coverage_rate=coverage.annotation_coverage_rate,
        quality_score=quality.quality_score,
        grounding_issue_rate=grounding.grounding_issue_rate,
        safety_issue_rate=safety.safety_issue_rate,
        task_leakage_rate=task_scope.task_leakage_rate,
        high_severity_rate=_rate(high_severity, len(annotations)),
        dataset_health_label=health,
        dataset_hash=dataset_hash,
        annotation_hash=annotation_hash,
    )


def _dataset_health(
    quality: QualityDecisionMetrics,
    grounding: GroundingMetrics,
    safety: SafetyMetrics,
    task_scope: TaskScopeMetrics,
) -> str:
    if safety.safety_issue_rate > 0.05 or safety.unsafe_count > 0 or safety.trading_instruction_issue_count > 0:
        return "UNSAFE"
    if quality.quality_score >= 0.90 and safety.safety_issue_rate == 0 and task_scope.task_leakage_rate == 0 and grounding.grounding_issue_rate <= 0.05:
        return "EXCELLENT"
    if quality.quality_score >= 0.75 and safety.safety_issue_rate <= 0.02 and task_scope.task_leakage_rate <= 0.02 and grounding.grounding_issue_rate <= 0.15:
        return "GOOD"
    if quality.quality_score >= 0.50 and safety.safety_issue_rate <= 0.05:
        return "NEEDS_REVIEW"
    return "DEGRADED"


def _reviewer_activity_metrics(annotations: Sequence[HumanReviewAnnotation]) -> ReviewerActivityMetrics:
    by_reviewer = _counts(item.reviewer_id for item in annotations)
    approvals: Dict[str, int] = {}
    rejections: Dict[str, int] = {}
    high_severity: Dict[str, int] = {}
    for item in annotations:
        if item.review_status in {"APPROVED", "APPROVED_WITH_NOTES"}:
            approvals[item.reviewer_id] = approvals.get(item.reviewer_id, 0) + 1
        if item.review_status in {"REJECTED", "NEEDS_FIX"}:
            rejections[item.reviewer_id] = rejections.get(item.reviewer_id, 0) + 1
        if item.severity in {"HIGH", "CRITICAL"}:
            high_severity[item.reviewer_id] = high_severity.get(item.reviewer_id, 0) + 1
    disagreements = _reviewer_disagreements(annotations)
    groups = _group_annotations(annotations, ("registry_id", "task_id"))
    return ReviewerActivityMetrics(
        reviewer_count=len([reviewer for reviewer in by_reviewer if reviewer]),
        annotations_by_reviewer=by_reviewer,
        approval_rate_by_reviewer={reviewer: _rate(approvals.get(reviewer, 0), total) for reviewer, total in by_reviewer.items()},
        rejection_rate_by_reviewer={reviewer: _rate(rejections.get(reviewer, 0), total) for reviewer, total in by_reviewer.items()},
        high_severity_by_reviewer=high_severity,
        reviewer_disagreement_count=len(disagreements),
        reviewer_disagreement_rate=_rate(len(disagreements), len(groups)),
        disagreements=[item.as_dict() for item in disagreements],
    )


def _reviewer_disagreements(annotations: Sequence[HumanReviewAnnotation]) -> List[ReviewerDisagreement]:
    disagreements: List[ReviewerDisagreement] = []
    labels = ("quality_decision", "correctness_label", "grounding_label", "safety_label", "task_scope_label")
    for (registry_id, task_id), group in _group_annotations(annotations, ("registry_id", "task_id")).items():
        reviewers = {item.reviewer_id for item in group if item.reviewer_id}
        if len(reviewers) < 2:
            continue
        for label in labels:
            values = {item.reviewer_id: str(getattr(item, label)) for item in group if item.reviewer_id}
            if len(set(values.values())) <= 1:
                continue
            disagreements.append(
                ReviewerDisagreement(
                    registry_id=registry_id,
                    task_id=task_id,
                    label_field=label,
                    reviewer_values=values,
                    severity=_disagreement_severity(label, set(values.values())),
                )
            )
    return disagreements


def _disagreement_severity(label: str, values: Set[str]) -> str:
    if label == "safety_label" and {"SAFE", "UNSAFE"}.issubset(values):
        return "HIGH"
    if label == "quality_decision" and ({"HIGH_QUALITY", "INVALID"}.issubset(values) or {"HIGH_QUALITY", "UNSAFE"}.issubset(values)):
        return "HIGH"
    if label == "task_scope_label" and {"TASK_SCOPE_OK", "TASK_SCOPE_FAIL"}.issubset(values):
        return "HIGH"
    if any(value in {"UNSAFE", "INVALID", "TASK_SCOPE_FAIL", "MISSING_SOURCE"} for value in values):
        return "MEDIUM"
    return "LOW"


def _breakdown(entries: Sequence[EvaluationRegistryEntry], annotations: Sequence[HumanReviewAnnotation], field: str) -> Dict[str, Dict[str, Any]]:
    values = sorted({getattr(item, field) for item in annotations if getattr(item, field)})
    output: Dict[str, Dict[str, Any]] = {}
    for value in values:
        subset = [item for item in annotations if getattr(item, field) == value]
        output[value] = _breakdown_metrics(subset)
    for entry in entries:
        for task in entry.task_index:
            if field == "task_id" and task.task_id and task.task_id not in output:
                output[task.task_id] = _breakdown_metrics([])
    return output


def _intent_breakdown(entries: Sequence[EvaluationRegistryEntry], annotations: Sequence[HumanReviewAnnotation]) -> Dict[str, Dict[str, Any]]:
    task_map = _entry_task_map(entries)
    grouped: Dict[str, List[HumanReviewAnnotation]] = {}
    for item in annotations:
        intent = task_map.get((item.registry_id, item.task_id), {}).get("intent_family") or ""
        if intent:
            grouped.setdefault(intent, []).append(item)
    for entry in entries:
        for task in entry.task_index:
            if task.intent_family:
                grouped.setdefault(task.intent_family, [])
    return {key: _breakdown_metrics(value) for key, value in sorted(grouped.items())}


def _symbol_breakdown(entries: Sequence[EvaluationRegistryEntry], annotations: Sequence[HumanReviewAnnotation]) -> Dict[str, Dict[str, Any]]:
    task_map = _entry_task_map(entries)
    grouped: Dict[str, List[HumanReviewAnnotation]] = {}
    for item in annotations:
        symbol = task_map.get((item.registry_id, item.task_id), {}).get("symbol") or ""
        if symbol:
            grouped.setdefault(symbol, []).append(item)
    for entry in entries:
        for task in entry.task_index:
            if task.symbol:
                grouped.setdefault(task.symbol, [])
    return {key: _breakdown_metrics(value) for key, value in sorted(grouped.items())}


def _breakdown_metrics(annotations: Sequence[HumanReviewAnnotation]) -> Dict[str, Any]:
    quality = _quality_metrics(annotations)
    safety = _safety_metrics(annotations)
    grounding = _grounding_metrics(annotations)
    return {
        "annotations": len(annotations),
        "quality_score": quality.quality_score,
        "quality_distribution": quality.quality_distribution,
        "safety_issue_rate": safety.safety_issue_rate,
        "grounding_issue_rate": grounding.grounding_issue_rate,
        "reason_code_counts": _counts(code for item in annotations for code in item.reason_codes),
    }


def _recommendations(
    coverage: ReviewCoverageMetrics,
    grounding: GroundingMetrics,
    safety: SafetyMetrics,
    task_scope: TaskScopeMetrics,
    evaluation: EvaluationConsistencyMetrics,
) -> List[str]:
    recommendations: List[str] = []
    if coverage.annotation_coverage_rate < 0.8:
        recommendations.append(SYSTEM_QUALITY_RECOMMENDATIONS["coverage"])
    if grounding.grounding_issue_rate > 0 or grounding.source_issue_rate > 0:
        recommendations.append(SYSTEM_QUALITY_RECOMMENDATIONS["grounding"])
    if task_scope.task_leakage_rate > 0 or task_scope.static_task_market_leakage_count > 0:
        recommendations.append(SYSTEM_QUALITY_RECOMMENDATIONS["task_scope"])
    if safety.safety_issue_rate > 0 or safety.trading_instruction_issue_count > 0:
        recommendations.append(SYSTEM_QUALITY_RECOMMENDATIONS["safety"])
    if evaluation.evaluation_issue_rate > 0:
        recommendations.append(SYSTEM_QUALITY_RECOMMENDATIONS["evaluation"])
    return _ordered_unique(recommendations)


def _warnings(
    entries: Sequence[EvaluationRegistryEntry],
    annotations: Sequence[HumanReviewAnnotation],
    reason_codes: ReasonCodeMetrics,
) -> List[str]:
    warnings: List[str] = []
    if any(entry.execution_allowed for entry in entries) or any(item.execution_allowed for item in annotations):
        warnings.append("execution_allowed_true")
    if reason_codes.reason_code_counts.get("TRADING_INSTRUCTION_PRESENT"):
        warnings.append("trading_instruction_issue_present")
    if any(item.safety_label == "UNSAFE" or item.quality_decision == "UNSAFE" for item in annotations):
        warnings.append("unsafe_annotation_present")
    if _unsafe_warnings([entry.as_dict() for entry in entries]) or _unsafe_warnings([item.as_dict() for item in annotations]):
        warnings.append("unsafe_text_or_field_detected")
    return _ordered_unique(warnings)


def _safe_report_payload(report: QualityMetricsReport) -> Dict[str, Any]:
    payload = report.as_dict()
    payload.pop("raw_prompt", None)
    payload.pop("final_answer_text", None)
    return payload


def _filter_entries(
    entries: Sequence[EvaluationRegistryEntry],
    filters: ReviewAnalyticsFilters,
    dataset_versions: Sequence[EvaluationDatasetVersion],
) -> List[EvaluationRegistryEntry]:
    selected_ids: Set[str] | None = None
    if filters.dataset_version_id:
        version = next((item for item in dataset_versions if item.version_id == filters.dataset_version_id), None)
        selected_ids = set(version.registry_ids) if version else set()
    output: List[EvaluationRegistryEntry] = []
    for entry in entries:
        if selected_ids is not None and entry.registry_id not in selected_ids:
            continue
        if filters.registry_id and entry.registry_id != filters.registry_id:
            continue
        if filters.request_id and entry.request_id != filters.request_id:
            continue
        if filters.final_answer_sha256 and entry.final_answer_sha256 != filters.final_answer_sha256:
            continue
        if filters.record_type and entry.record_type != filters.record_type:
            continue
        if filters.symbol and not (entry.symbol == filters.symbol or any(task.symbol == filters.symbol for task in entry.task_index)):
            continue
        if filters.task_id and filters.task_id not in entry.task_ids:
            continue
        if filters.intent_family and not any(task.intent_family == filters.intent_family for task in entry.task_index):
            continue
        if filters.created_after and not _date_gte(entry.created_at, filters.created_after):
            continue
        if filters.created_before and not _date_lte(entry.created_at, filters.created_before):
            continue
        output.append(entry)
    return output[: max(0, filters.limit or 1000)]


def _filter_annotations(
    annotations: Sequence[HumanReviewAnnotation],
    filters: ReviewAnalyticsFilters,
    entries: Sequence[EvaluationRegistryEntry],
    annotated_versions: Sequence[AnnotatedDatasetVersion],
) -> List[HumanReviewAnnotation]:
    selected_registry_ids = {entry.registry_id for entry in entries}
    selected_annotation_ids: Set[str] | None = None
    if filters.annotated_dataset_version_id:
        version = next((item for item in annotated_versions if item.version_id == filters.annotated_dataset_version_id), None)
        selected_annotation_ids = set(version.annotation_ids) if version else set()
    output: List[HumanReviewAnnotation] = []
    for item in annotations:
        if selected_annotation_ids is not None and item.annotation_id not in selected_annotation_ids:
            continue
        if selected_registry_ids and item.registry_id not in selected_registry_ids:
            continue
        if filters.registry_id and item.registry_id != filters.registry_id:
            continue
        if filters.request_id and item.request_id != filters.request_id:
            continue
        if filters.final_answer_sha256 and item.final_answer_sha256 != filters.final_answer_sha256:
            continue
        if filters.task_id and item.task_id != filters.task_id:
            continue
        if filters.record_type and item.record_type != filters.record_type:
            continue
        if filters.reviewer_id and item.reviewer_id != filters.reviewer_id:
            continue
        if filters.review_status and item.review_status != filters.review_status:
            continue
        if filters.quality_decision and item.quality_decision != filters.quality_decision:
            continue
        if filters.correctness_label and item.correctness_label != filters.correctness_label:
            continue
        if filters.grounding_label and item.grounding_label != filters.grounding_label:
            continue
        if filters.safety_label and item.safety_label != filters.safety_label:
            continue
        if filters.task_scope_label and item.task_scope_label != filters.task_scope_label:
            continue
        if filters.reason_code and filters.reason_code not in item.reason_codes:
            continue
        if filters.severity and item.severity != filters.severity:
            continue
        if filters.created_after and not _date_gte(item.created_at, filters.created_after):
            continue
        if filters.created_before and not _date_lte(item.created_at, filters.created_before):
            continue
        output.append(item)
    return output


def _filter_states(states: Sequence[ReviewWorkflowState], entries: Sequence[EvaluationRegistryEntry]) -> List[ReviewWorkflowState]:
    selected = {entry.registry_id for entry in entries}
    return [state for state in states if state.registry_id in selected]


def _entry_task_map(entries: Sequence[EvaluationRegistryEntry]) -> Dict[tuple[str, str], Dict[str, str]]:
    output: Dict[tuple[str, str], Dict[str, str]] = {}
    for entry in entries:
        for task in entry.task_index:
            output[(entry.registry_id, task.task_id)] = {
                "intent_family": task.intent_family,
                "symbol": task.symbol,
                "status": task.status,
                "quality_label": task.quality_label,
            }
    return output


def _static_market_leakage(item: HumanReviewAnnotation, task_map: Mapping[tuple[str, str], Mapping[str, str]]) -> bool:
    task = task_map.get((item.registry_id, item.task_id), {})
    intent = task.get("intent_family") or ""
    symbol = task.get("symbol") or ""
    return intent in STATIC_INTENTS and (bool(symbol) or "STATIC_TASK_MARKED_AS_MARKET_TASK" in item.reason_codes)


def _group_annotations(annotations: Sequence[HumanReviewAnnotation], fields: Sequence[str]) -> Dict[tuple[str, ...], List[HumanReviewAnnotation]]:
    output: Dict[tuple[str, ...], List[HumanReviewAnnotation]] = {}
    for item in annotations:
        key = tuple(str(getattr(item, field, "")) for field in fields)
        output.setdefault(key, []).append(item)
    return output


def _entry(item: EvaluationRegistryEntry | Mapping[str, Any]) -> EvaluationRegistryEntry:
    if isinstance(item, EvaluationRegistryEntry):
        return item
    from src.services.agents.evaluation_registry import EvaluationRegistry

    return EvaluationRegistry([item]).list_registry_entries({})[0]


def _annotation(item: HumanReviewAnnotation | Mapping[str, Any]) -> HumanReviewAnnotation:
    if isinstance(item, HumanReviewAnnotation):
        return item
    from src.services.agents.human_review import annotation_from_mapping

    return annotation_from_mapping(dict(item))


def _state(item: ReviewWorkflowState | Mapping[str, Any]) -> ReviewWorkflowState:
    if isinstance(item, ReviewWorkflowState):
        return item
    data = dict(item)
    return ReviewWorkflowState(
        registry_id=str(data.get("registry_id") or ""),
        current_status=str(data.get("current_status") or "UNREVIEWED"),
        latest_annotation_id=str(data.get("latest_annotation_id") or ""),
        annotation_count=int(data.get("annotation_count") or 0),
        reviewer_ids=[str(value) for value in data.get("reviewer_ids") or []],
        has_open_issue=bool(data.get("has_open_issue")),
        highest_severity=str(data.get("highest_severity") or "LOW"),
        needs_followup=bool(data.get("needs_followup")),
        locked=bool(data.get("locked")),
        updated_at=str(data.get("updated_at") or ""),
    )


def _dataset_version(item: EvaluationDatasetVersion | Mapping[str, Any]) -> EvaluationDatasetVersion:
    if isinstance(item, EvaluationDatasetVersion):
        return item
    data = dict(item)
    return EvaluationDatasetVersion(
        version_id=str(data.get("version_id") or ""),
        created_at=str(data.get("created_at") or ""),
        name=str(data.get("name") or ""),
        description=str(data.get("description") or ""),
        source=dict(data.get("source") or {}),
        entries_count=int(data.get("entries_count") or 0),
        request_ids=[str(value) for value in data.get("request_ids") or []],
        final_answer_hashes=[str(value) for value in data.get("final_answer_hashes") or []],
        record_type_counts=dict(data.get("record_type_counts") or {}),
        quality_counts=dict(data.get("quality_counts") or {}),
        status_counts=dict(data.get("status_counts") or {}),
        safety_flag_count=int(data.get("safety_flag_count") or 0),
        review_priority_counts=dict(data.get("review_priority_counts") or {}),
        dataset_hash=str(data.get("dataset_hash") or ""),
        export_paths=dict(data.get("export_paths") or {}),
        schema_version=str(data.get("schema_version") or ""),
        limitations=[str(value) for value in data.get("limitations") or []],
        registry_ids=[str(value) for value in data.get("registry_ids") or []],
    )


def _annotated_version(item: AnnotatedDatasetVersion | Mapping[str, Any]) -> AnnotatedDatasetVersion:
    if isinstance(item, AnnotatedDatasetVersion):
        return item
    data = dict(item)
    return AnnotatedDatasetVersion(
        version_id=str(data.get("version_id") or ""),
        created_at=str(data.get("created_at") or ""),
        source_dataset_version_id=str(data.get("source_dataset_version_id") or ""),
        annotation_ids=[str(value) for value in data.get("annotation_ids") or []],
        entries_count=int(data.get("entries_count") or 0),
        reviewed_count=int(data.get("reviewed_count") or 0),
        approved_count=int(data.get("approved_count") or 0),
        rejected_count=int(data.get("rejected_count") or 0),
        unsafe_count=int(data.get("unsafe_count") or 0),
        dataset_hash=str(data.get("dataset_hash") or ""),
        annotation_hash=str(data.get("annotation_hash") or ""),
        locked=bool(data.get("locked")),
        limitations=[str(value) for value in data.get("limitations") or []],
        export_paths=dict(data.get("export_paths") or {}),
        schema_version=str(data.get("schema_version") or ""),
    )


def _filters(filters: ReviewAnalyticsFilters | Mapping[str, Any] | None) -> ReviewAnalyticsFilters:
    if isinstance(filters, ReviewAnalyticsFilters):
        return filters
    data = dict(filters or {})
    return ReviewAnalyticsFilters(**{key: value for key, value in data.items() if key in ReviewAnalyticsFilters.__dataclass_fields__})


def _score_average(labels: Iterable[str], score_map: Mapping[str, float]) -> float:
    values = [score_map[label] for label in labels if label in score_map]
    return round(sum(values) / len(values), 4) if values else 0.0


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _counts(values: Iterable[str]) -> Dict[str, int]:
    output: Dict[str, int] = {}
    for value in values:
        if value:
            output[str(value)] = output.get(str(value), 0) + 1
    return output


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.lower())
    return "-".join(part for part in cleaned.split("-") if part)[:160] or "quality-metrics"


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


def _asdict(value: Any) -> Dict[str, Any]:
    return {key: _asdict_item(item) for key, item in value.__dict__.items()}


def _asdict_item(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, dict):
        return {key: _asdict_item(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_asdict_item(item) for item in value]
    return value
