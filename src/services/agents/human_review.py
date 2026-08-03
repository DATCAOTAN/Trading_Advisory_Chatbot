from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_persistence import (
    EvaluationDatasetVersion,
    EvaluationPersistenceStore,
    ExportResult,
    ImportResult,
    REGISTRY_SAFETY_PATTERNS,
    SECRET_PATTERNS,
    UNSAFE_FIELD_NAMES,
)
from src.services.agents.evaluation_registry import EvaluationRegistryEntry


ANNOTATION_SCHEMA_VERSION = "human_review_annotation.v1"
ANNOTATED_DATASET_SCHEMA_VERSION = "annotated_review_dataset.v1"
DEFAULT_REVIEW_DIR = Path("data") / "evaluations" / "reviews"
DEFAULT_ANNOTATION_PATH = DEFAULT_REVIEW_DIR / "human_review_annotations.jsonl"
DEFAULT_WORKFLOW_STATE_PATH = DEFAULT_REVIEW_DIR / "review_workflow_states.json"
DEFAULT_ANNOTATED_VERSION_PATH = DEFAULT_REVIEW_DIR / "annotated_dataset_versions.json"
DEFAULT_REVIEW_EXPORT_DIR = DEFAULT_REVIEW_DIR / "exports"

REVIEW_STATUSES = {
    "UNREVIEWED",
    "IN_REVIEW",
    "APPROVED",
    "APPROVED_WITH_NOTES",
    "NEEDS_FIX",
    "REJECTED",
    "NOT_APPLICABLE",
}
QUALITY_DECISIONS = {
    "HIGH_QUALITY",
    "ACCEPTABLE",
    "ACCEPTABLE_WITH_WARNINGS",
    "LOW_QUALITY",
    "INVALID",
    "UNSAFE",
    "NOT_APPLICABLE",
}
CORRECTNESS_LABELS = {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "UNSUPPORTED", "UNCLEAR", "NOT_APPLICABLE"}
GROUNDING_LABELS = {"WELL_GROUNDED", "PARTIALLY_GROUNDED", "POORLY_GROUNDED", "MISSING_SOURCE", "NOT_APPLICABLE"}
SAFETY_LABELS = {"SAFE", "WARNING", "UNSAFE", "NOT_APPLICABLE"}
TASK_SCOPE_LABELS = {"TASK_SCOPE_OK", "POSSIBLE_LEAKAGE", "TASK_SCOPE_FAIL", "NOT_APPLICABLE"}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


@dataclass(frozen=True)
class ReviewReasonCode:
    code: str
    category: str
    description: str
    severity_default: str = "MEDIUM"

    def as_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "category": self.category,
            "description": self.description,
            "severity_default": self.severity_default,
        }


REASON_CODE_TAXONOMY: Dict[str, ReviewReasonCode] = {
    "MISSING_SOURCE_REFERENCE": ReviewReasonCode("MISSING_SOURCE_REFERENCE", "Evidence / Grounding", "Required source reference is missing.", "HIGH"),
    "WEAK_SOURCE_SUPPORT": ReviewReasonCode("WEAK_SOURCE_SUPPORT", "Evidence / Grounding", "Source support is weak.", "MEDIUM"),
    "WRONG_SOURCE_USED": ReviewReasonCode("WRONG_SOURCE_USED", "Evidence / Grounding", "Wrong source was used.", "HIGH"),
    "SOURCE_LEAKAGE_BETWEEN_TASKS": ReviewReasonCode("SOURCE_LEAKAGE_BETWEEN_TASKS", "Evidence / Grounding", "Source leaked across task scope.", "HIGH"),
    "CLAIM_NOT_SUPPORTED": ReviewReasonCode("CLAIM_NOT_SUPPORTED", "Evidence / Grounding", "Claim is not supported.", "HIGH"),
    "INCOMPLETE_ANSWER": ReviewReasonCode("INCOMPLETE_ANSWER", "Answer Quality", "Answer is incomplete.", "MEDIUM"),
    "TOO_GENERIC": ReviewReasonCode("TOO_GENERIC", "Answer Quality", "Answer is too generic.", "LOW"),
    "OVERCONFIDENT_LANGUAGE": ReviewReasonCode("OVERCONFIDENT_LANGUAGE", "Answer Quality", "Answer is overconfident.", "MEDIUM"),
    "UNCLEAR_REASONING": ReviewReasonCode("UNCLEAR_REASONING", "Answer Quality", "Reasoning is unclear.", "MEDIUM"),
    "WRONG_INTENT_FOCUS": ReviewReasonCode("WRONG_INTENT_FOCUS", "Answer Quality", "Answer focused on wrong intent.", "HIGH"),
    "TRADING_INSTRUCTION_PRESENT": ReviewReasonCode("TRADING_INSTRUCTION_PRESENT", "Safety / Compliance", "Trading instruction was present.", "CRITICAL"),
    "ENTRY_SL_TP_PRESENT": ReviewReasonCode("ENTRY_SL_TP_PRESENT", "Safety / Compliance", "Entry/SL/TP details were present.", "CRITICAL"),
    "POSITION_SIZING_PRESENT": ReviewReasonCode("POSITION_SIZING_PRESENT", "Safety / Compliance", "Position sizing was present.", "CRITICAL"),
    "ACCOUNT_RISK_PRESENT": ReviewReasonCode("ACCOUNT_RISK_PRESENT", "Safety / Compliance", "Account-risk recommendation was present.", "CRITICAL"),
    "MT5_OR_ORDER_LANGUAGE_PRESENT": ReviewReasonCode("MT5_OR_ORDER_LANGUAGE_PRESENT", "Safety / Compliance", "MT5/order language was present.", "CRITICAL"),
    "UNSUPPORTED_CERTAINTY": ReviewReasonCode("UNSUPPORTED_CERTAINTY", "Safety / Compliance", "Certainty exceeded support.", "HIGH"),
    "MULTI_INTENT_LEAKAGE": ReviewReasonCode("MULTI_INTENT_LEAKAGE", "Task Scope", "Multi-intent leakage detected.", "HIGH"),
    "STATIC_TASK_MARKED_AS_MARKET_TASK": ReviewReasonCode("STATIC_TASK_MARKED_AS_MARKET_TASK", "Task Scope", "Static task was treated as market task.", "HIGH"),
    "MARKET_TASK_MISSING_REQUIRED_CONTEXT": ReviewReasonCode("MARKET_TASK_MISSING_REQUIRED_CONTEXT", "Task Scope", "Market task lacks required context.", "HIGH"),
    "WRONG_TASK_ATTRIBUTION": ReviewReasonCode("WRONG_TASK_ATTRIBUTION", "Task Scope", "Review or record attributed to wrong task.", "HIGH"),
    "BACKTEST_DISAGREES_WITH_THESIS": ReviewReasonCode("BACKTEST_DISAGREES_WITH_THESIS", "Evaluation Consistency", "Backtest disagrees with thesis.", "MEDIUM"),
    "PAPER_EVAL_INVALIDATION_OBSERVED": ReviewReasonCode("PAPER_EVAL_INVALIDATION_OBSERVED", "Evaluation Consistency", "Paper follow-up observed invalidation.", "MEDIUM"),
    "RISK_MATERIALIZED": ReviewReasonCode("RISK_MATERIALIZED", "Evaluation Consistency", "Risk materialized.", "MEDIUM"),
    "CONFIDENCE_CALIBRATION_WEAK": ReviewReasonCode("CONFIDENCE_CALIBRATION_WEAK", "Evaluation Consistency", "Confidence calibration was weak.", "MEDIUM"),
    "MISSING_EVALUATION_RECORD": ReviewReasonCode("MISSING_EVALUATION_RECORD", "System / Data", "Evaluation record is missing.", "MEDIUM"),
    "CORRUPT_PERSISTED_RECORD": ReviewReasonCode("CORRUPT_PERSISTED_RECORD", "System / Data", "Persisted record is corrupt.", "HIGH"),
    "IMPORT_VALIDATION_WARNING": ReviewReasonCode("IMPORT_VALIDATION_WARNING", "System / Data", "Import validation warning.", "MEDIUM"),
    "REPLAY_MISMATCH": ReviewReasonCode("REPLAY_MISMATCH", "System / Data", "Replay mismatch detected.", "HIGH"),
}


@dataclass
class HumanReviewAnnotation:
    annotation_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    registry_id: str = ""
    request_id: str = ""
    final_answer_sha256: str = ""
    task_id: str = ""
    record_type: str = ""
    reviewer_id: str = ""
    review_status: str = "UNREVIEWED"
    quality_decision: str = "NOT_APPLICABLE"
    correctness_label: str = "NOT_APPLICABLE"
    grounding_label: str = "NOT_APPLICABLE"
    safety_label: str = "NOT_APPLICABLE"
    task_scope_label: str = "NOT_APPLICABLE"
    reason_codes: List[str] = field(default_factory=list)
    reviewer_note: str = ""
    suggested_fix_summary: str = ""
    severity: str = "LOW"
    locked: bool = False
    locked_at: str = ""
    source_refs_snapshot: List[str] = field(default_factory=list)
    hashes_snapshot: Dict[str, str] = field(default_factory=dict)
    execution_allowed: bool = False
    schema_version: str = ANNOTATION_SCHEMA_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "annotation_id": self.annotation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "registry_id": self.registry_id,
            "request_id": self.request_id,
            "final_answer_sha256": self.final_answer_sha256,
            "task_id": self.task_id,
            "record_type": self.record_type,
            "reviewer_id": self.reviewer_id,
            "review_status": self.review_status,
            "quality_decision": self.quality_decision,
            "correctness_label": self.correctness_label,
            "grounding_label": self.grounding_label,
            "safety_label": self.safety_label,
            "task_scope_label": self.task_scope_label,
            "reason_codes": list(self.reason_codes),
            "reviewer_note": self.reviewer_note,
            "suggested_fix_summary": self.suggested_fix_summary,
            "severity": self.severity,
            "locked": self.locked,
            "locked_at": self.locked_at,
            "source_refs_snapshot": list(self.source_refs_snapshot),
            "hashes_snapshot": dict(self.hashes_snapshot),
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class ReviewWorkflowState:
    registry_id: str
    current_status: str = "UNREVIEWED"
    latest_annotation_id: str = ""
    annotation_count: int = 0
    reviewer_ids: List[str] = field(default_factory=list)
    has_open_issue: bool = False
    highest_severity: str = "LOW"
    needs_followup: bool = False
    locked: bool = False
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "current_status": self.current_status,
            "latest_annotation_id": self.latest_annotation_id,
            "annotation_count": self.annotation_count,
            "reviewer_ids": list(self.reviewer_ids),
            "has_open_issue": self.has_open_issue,
            "highest_severity": self.highest_severity,
            "needs_followup": self.needs_followup,
            "locked": self.locked,
            "updated_at": self.updated_at,
        }


@dataclass
class ReviewBatchSummary:
    total_records: int = 0
    reviewed_count: int = 0
    approved_count: int = 0
    needs_fix_count: int = 0
    rejected_count: int = 0
    unsafe_count: int = 0
    not_applicable_count: int = 0
    high_severity_count: int = 0
    locked_count: int = 0
    by_reviewer: Dict[str, int] = field(default_factory=dict)
    by_reason_code: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "reviewed_count": self.reviewed_count,
            "approved_count": self.approved_count,
            "needs_fix_count": self.needs_fix_count,
            "rejected_count": self.rejected_count,
            "unsafe_count": self.unsafe_count,
            "not_applicable_count": self.not_applicable_count,
            "high_severity_count": self.high_severity_count,
            "locked_count": self.locked_count,
            "by_reviewer": dict(self.by_reviewer),
            "by_reason_code": dict(self.by_reason_code),
        }


@dataclass
class AnnotatedDatasetVersion:
    version_id: str
    created_at: str
    source_dataset_version_id: str = ""
    annotation_ids: List[str] = field(default_factory=list)
    entries_count: int = 0
    reviewed_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    unsafe_count: int = 0
    dataset_hash: str = ""
    annotation_hash: str = ""
    locked: bool = False
    limitations: List[str] = field(default_factory=list)
    export_paths: Dict[str, str] = field(default_factory=dict)
    schema_version: str = ANNOTATED_DATASET_SCHEMA_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version_id": self.version_id,
            "created_at": self.created_at,
            "source_dataset_version_id": self.source_dataset_version_id,
            "annotation_ids": list(self.annotation_ids),
            "entries_count": self.entries_count,
            "reviewed_count": self.reviewed_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "unsafe_count": self.unsafe_count,
            "dataset_hash": self.dataset_hash,
            "annotation_hash": self.annotation_hash,
            "locked": self.locked,
            "limitations": list(self.limitations),
            "export_paths": dict(self.export_paths),
        }


@dataclass
class ReviewPersistResult:
    status: str
    annotation_id: str = ""
    registry_id: str = ""
    storage_path: str = ""
    redactions: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "annotation_id": self.annotation_id,
            "registry_id": self.registry_id,
            "storage_path": self.storage_path,
            "redactions": self.redactions,
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
        }


@dataclass
class LockResult:
    status: str
    annotation_id: str = ""
    registry_id: str = ""
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class ReviewValidationResult:
    status: str
    annotations_checked: int = 0
    invalid_annotations: int = 0
    unsafe_annotations: int = 0
    duplicate_annotations: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0


class HumanReviewStore:
    def __init__(
        self,
        annotation_path: str | Path | None = None,
        workflow_state_path: str | Path | None = None,
        annotated_version_path: str | Path | None = None,
        export_dir: str | Path | None = None,
        persistence_store: EvaluationPersistenceStore | None = None,
    ):
        self.annotation_path = Path(annotation_path or DEFAULT_ANNOTATION_PATH)
        self.workflow_state_path = Path(workflow_state_path or DEFAULT_WORKFLOW_STATE_PATH)
        self.annotated_version_path = Path(annotated_version_path or DEFAULT_ANNOTATED_VERSION_PATH)
        self.export_dir = Path(export_dir or DEFAULT_REVIEW_EXPORT_DIR)
        self.persistence_store = persistence_store or EvaluationPersistenceStore()

    def save_annotation(
        self,
        annotation: HumanReviewAnnotation | Mapping[str, Any],
        allow_append_after_lock: bool = False,
    ) -> ReviewPersistResult:
        started = time.perf_counter()
        self._ensure_dirs()
        item = annotation if isinstance(annotation, HumanReviewAnnotation) else annotation_from_mapping(annotation)
        validation = _validate_annotation(item)
        if validation:
            return ReviewPersistResult("REJECTED", item.annotation_id, item.registry_id, str(self.annotation_path), warnings=validation, latency_ms=_elapsed(started))
        locked_state = self.get_workflow_state(item.registry_id)
        if locked_state.locked and not allow_append_after_lock:
            return ReviewPersistResult("LOCKED", item.annotation_id, item.registry_id, str(self.annotation_path), warnings=["registry_review_locked"], latency_ms=_elapsed(started))
        existing = self.get_annotation(item.annotation_id) if item.annotation_id else None
        if existing and existing.locked:
            return ReviewPersistResult("LOCKED", item.annotation_id, item.registry_id, str(self.annotation_path), warnings=["annotation_locked"], latency_ms=_elapsed(started))
        if existing:
            return ReviewPersistResult("SKIPPED_DUPLICATE", item.annotation_id, item.registry_id, str(self.annotation_path), latency_ms=_elapsed(started))
        sanitized, redactions = _sanitize_annotation(item)
        if not sanitized.annotation_id:
            sanitized.annotation_id = _annotation_id(sanitized)
        sanitized.updated_at = _utc_now()
        with self.annotation_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitized.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        self._write_workflow_states()
        result = ReviewPersistResult("SAVED", sanitized.annotation_id, sanitized.registry_id, str(self.annotation_path), redactions, latency_ms=_elapsed(started))
        print(
            "[HumanReview] "
            f"action=save_annotation annotation_id={result.annotation_id} registry_id={result.registry_id} "
            f"status={sanitized.review_status} severity={sanitized.severity} redactions={result.redactions} latency_ms={result.latency_ms}"
        )
        return result

    def load_annotations(self, filters: Mapping[str, Any] | None = None) -> List[HumanReviewAnnotation]:
        annotations = self._read_annotations()
        filters = dict(filters or {})
        return [item for item in annotations if _annotation_matches(item, filters)]

    def get_annotation(self, annotation_id: str) -> HumanReviewAnnotation | None:
        return next((item for item in self._read_annotations() if item.annotation_id == annotation_id), None)

    def get_annotations_for_registry_id(self, registry_id: str) -> List[HumanReviewAnnotation]:
        return self.load_annotations({"registry_id": registry_id})

    def get_workflow_state(self, registry_id: str) -> ReviewWorkflowState:
        annotations = self.get_annotations_for_registry_id(registry_id)
        state = workflow_state_for(registry_id, annotations)
        print(
            "[HumanReview] "
            f"action=workflow_state registry_id={registry_id} status={state.current_status} "
            f"annotation_count={state.annotation_count} locked={state.locked}"
        )
        return state

    def list_workflow_states(self, filters: Mapping[str, Any] | None = None) -> List[ReviewWorkflowState]:
        registry_ids = _ordered_unique(item.registry_id for item in self._read_annotations())
        states = [self.get_workflow_state(registry_id) for registry_id in registry_ids]
        filters = dict(filters or {})
        return [state for state in states if _state_matches(state, filters)]

    def lock_annotation(self, annotation_id: str) -> LockResult:
        started = time.perf_counter()
        annotations = self._read_annotations()
        found = False
        for item in annotations:
            if item.annotation_id == annotation_id:
                item.locked = True
                item.locked_at = item.locked_at or _utc_now()
                item.updated_at = _utc_now()
                found = True
        if not found:
            return LockResult("NOT_FOUND", annotation_id=annotation_id, latency_ms=_elapsed(started))
        self._rewrite_annotations(annotations)
        self._write_workflow_states()
        return LockResult("LOCKED", annotation_id=annotation_id, latency_ms=_elapsed(started))

    def lock_registry_review(self, registry_id: str) -> LockResult:
        started = time.perf_counter()
        annotations = self.get_annotations_for_registry_id(registry_id)
        if not annotations:
            return LockResult("NOT_FOUND", registry_id=registry_id, latency_ms=_elapsed(started))
        for item in annotations:
            item.locked = True
            item.locked_at = item.locked_at or _utc_now()
            item.updated_at = _utc_now()
        all_annotations = [item for item in self._read_annotations() if item.registry_id != registry_id] + annotations
        self._rewrite_annotations(all_annotations)
        self._write_workflow_states()
        return LockResult("LOCKED", registry_id=registry_id, latency_ms=_elapsed(started))

    def batch_summary(self, filters: Mapping[str, Any] | None = None) -> ReviewBatchSummary:
        annotations = self.load_annotations(filters or {})
        latest_by_registry = {state.registry_id: state for state in self.list_workflow_states()}
        return ReviewBatchSummary(
            total_records=len(latest_by_registry),
            reviewed_count=sum(1 for state in latest_by_registry.values() if state.current_status != "UNREVIEWED"),
            approved_count=sum(1 for state in latest_by_registry.values() if state.current_status in {"APPROVED", "APPROVED_WITH_NOTES"}),
            needs_fix_count=sum(1 for state in latest_by_registry.values() if state.current_status == "NEEDS_FIX"),
            rejected_count=sum(1 for state in latest_by_registry.values() if state.current_status == "REJECTED"),
            unsafe_count=sum(1 for item in annotations if item.safety_label == "UNSAFE" or item.quality_decision == "UNSAFE"),
            not_applicable_count=sum(1 for state in latest_by_registry.values() if state.current_status == "NOT_APPLICABLE"),
            high_severity_count=sum(1 for item in annotations if item.severity in {"HIGH", "CRITICAL"}),
            locked_count=sum(1 for state in latest_by_registry.values() if state.locked),
            by_reviewer=_counts(item.reviewer_id for item in annotations),
            by_reason_code=_counts(code for item in annotations for code in item.reason_codes),
        )

    def create_annotated_dataset_version(
        self,
        name: str,
        source_dataset_version: EvaluationDatasetVersion | None = None,
        filters: Mapping[str, Any] | None = None,
        locked: bool = False,
    ) -> AnnotatedDatasetVersion:
        started = time.perf_counter()
        annotations = self.load_annotations(filters or {})
        rows = self._annotated_rows(annotations)
        annotation_hash = _hash_payload([item.as_dict() for item in annotations])
        dataset_hash = _hash_payload(rows)
        version = AnnotatedDatasetVersion(
            version_id=f"annotated_dataset:{_safe_filename(name) or 'review'}:{annotation_hash[:12]}",
            created_at=_utc_now(),
            source_dataset_version_id=source_dataset_version.version_id if source_dataset_version else "",
            annotation_ids=[item.annotation_id for item in annotations],
            entries_count=len(rows),
            reviewed_count=sum(1 for item in annotations if item.review_status != "UNREVIEWED"),
            approved_count=sum(1 for item in annotations if item.review_status in {"APPROVED", "APPROVED_WITH_NOTES"}),
            rejected_count=sum(1 for item in annotations if item.review_status == "REJECTED"),
            unsafe_count=sum(1 for item in annotations if item.safety_label == "UNSAFE" or item.quality_decision == "UNSAFE"),
            dataset_hash=dataset_hash,
            annotation_hash=annotation_hash,
            locked=locked,
        )
        versions = [item for item in self._load_versions() if item.version_id != version.version_id] + [version]
        self._write_versions(versions)
        print(
            "[HumanReview] "
            f"action=create_annotated_dataset version_id={version.version_id} entries={version.entries_count} "
            f"annotations={len(version.annotation_ids)} dataset_hash={version.dataset_hash} latency_ms={_elapsed(started)}"
        )
        return version

    def list_annotated_dataset_versions(self) -> List[AnnotatedDatasetVersion]:
        return self._load_versions()

    def export_annotated_dataset(self, version_id: str, format: str = "json") -> ExportResult:
        started = time.perf_counter()
        version = next((item for item in self._load_versions() if item.version_id == version_id), None)
        if not version:
            return ExportResult("FAILED", version_id=version_id, format=format, warnings=["missing_version"], latency_ms=_elapsed(started))
        annotations = [item for item in self._read_annotations() if item.annotation_id in set(version.annotation_ids)]
        rows = self._annotated_rows(annotations)
        export_format = format.lower()
        path = self.export_dir / f"{_safe_filename(version.version_id)}.{export_format}"
        if export_format == "json":
            payload = {
                "schema_version": ANNOTATED_DATASET_SCHEMA_VERSION,
                "version": version.as_dict(),
                "rows": rows,
                "annotations": [item.as_dict() for item in annotations],
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        elif export_format == "csv":
            text = _csv(rows)
        else:
            return ExportResult("FAILED", version_id=version_id, format=format, warnings=["unsupported_format"], latency_ms=_elapsed(started))
        _atomic_write_text(path, text)
        version.export_paths[export_format] = str(path)
        self._write_versions([item for item in self._load_versions() if item.version_id != version.version_id] + [version])
        result = ExportResult("EXPORTED", version_id, str(path), export_format, len(text), latency_ms=_elapsed(started))
        print(
            "[HumanReview] "
            f"action=export version_id={version_id} format={export_format} payload_chars={result.payload_chars} "
            f"redactions={result.redactions} status={result.status}"
        )
        return result

    def import_annotations(self, path: str | Path, validate_only: bool = False) -> ImportResult:
        started = time.perf_counter()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ImportResult("FAILED", warnings=[exc.__class__.__name__], latency_ms=_elapsed(started))
        items = data.get("annotations") if isinstance(data, Mapping) else None
        if not isinstance(items, list):
            return ImportResult("REJECTED", rejected_count=1, warnings=["missing_annotations"], latency_ms=_elapsed(started))
        imported = duplicates = rejected = 0
        for raw in items:
            annotation = annotation_from_mapping(raw) if isinstance(raw, Mapping) else HumanReviewAnnotation()
            if _validate_annotation(annotation) or _unsafe_mapping(raw):
                rejected += 1
                continue
            if self.get_annotation(annotation.annotation_id):
                duplicates += 1
                continue
            if validate_only:
                imported += 1
            else:
                result = self.save_annotation(annotation)
                if result.status == "SAVED":
                    imported += 1
                elif result.status == "SKIPPED_DUPLICATE":
                    duplicates += 1
                else:
                    rejected += 1
        status = "REJECTED" if rejected and validate_only else ("PARTIAL" if rejected else ("VALIDATED" if validate_only else "IMPORTED"))
        return ImportResult(status, imported, duplicates, rejected, latency_ms=_elapsed(started))

    def validate_annotations(self) -> ReviewValidationResult:
        started = time.perf_counter()
        seen: Set[str] = set()
        invalid = unsafe = duplicate = checked = 0
        for item in self._read_raw_annotation_lines():
            checked += 1
            if not isinstance(item, Mapping):
                invalid += 1
                continue
            annotation = annotation_from_mapping(item)
            if _validate_annotation(annotation):
                invalid += 1
            if _unsafe_mapping(item):
                unsafe += 1
            if annotation.annotation_id in seen:
                duplicate += 1
            seen.add(annotation.annotation_id)
        status = "FAIL" if invalid or unsafe else ("WARN" if duplicate else "PASS")
        return ReviewValidationResult(status, checked, invalid, unsafe, duplicate, latency_ms=_elapsed(started))

    def _annotated_rows(self, annotations: Sequence[HumanReviewAnnotation]) -> List[Dict[str, Any]]:
        registry_entries = {entry.registry_id: entry for entry in self.persistence_store.load_entries()}
        rows: List[Dict[str, Any]] = []
        for annotation in annotations:
            entry = registry_entries.get(annotation.registry_id)
            task = _task_for_annotation(entry, annotation.task_id) if entry else None
            rows.append(
                {
                    "registry_id": annotation.registry_id,
                    "annotation_id": annotation.annotation_id,
                    "request_id": annotation.request_id,
                    "final_answer_sha256": annotation.final_answer_sha256,
                    "task_id": annotation.task_id,
                    "record_type": annotation.record_type,
                    "intent_family": task.intent_family if task else "",
                    "symbol": task.symbol if task else "",
                    "source_refs": list(annotation.source_refs_snapshot),
                    "registry_status": entry.status if entry else "",
                    "registry_quality_label": entry.quality_label if entry else "",
                    "review_status": annotation.review_status,
                    "quality_decision": annotation.quality_decision,
                    "correctness_label": annotation.correctness_label,
                    "grounding_label": annotation.grounding_label,
                    "safety_label": annotation.safety_label,
                    "task_scope_label": annotation.task_scope_label,
                    "reason_codes": list(annotation.reason_codes),
                    "severity": annotation.severity,
                    "reviewer_note_redacted": annotation.reviewer_note,
                    "suggested_fix_summary_redacted": annotation.suggested_fix_summary,
                    "hashes": dict(annotation.hashes_snapshot),
                    "execution_allowed": annotation.execution_allowed,
                }
            )
        return rows

    def _read_annotations(self) -> List[HumanReviewAnnotation]:
        return [annotation_from_mapping(item) for item in self._read_raw_annotation_lines() if isinstance(item, Mapping)]

    def _read_raw_annotation_lines(self) -> List[Any]:
        if not self.annotation_path.exists():
            return []
        output: List[Any] = []
        for line in self.annotation_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                output.append(json.loads(line))
            except json.JSONDecodeError:
                output.append(None)
        return output

    def _rewrite_annotations(self, annotations: Sequence[HumanReviewAnnotation]) -> None:
        self._ensure_dirs()
        text = "\n".join(json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True) for item in annotations)
        _atomic_write_text(self.annotation_path, text + ("\n" if text else ""))

    def _write_workflow_states(self) -> None:
        states = [state.as_dict() for state in self.list_workflow_states({})]
        _atomic_write_text(self.workflow_state_path, json.dumps({"schema_version": "human_review_workflow_state.v1", "updated_at": _utc_now(), "states": states}, ensure_ascii=False, indent=2, sort_keys=True))

    def _load_versions(self) -> List[AnnotatedDatasetVersion]:
        if not self.annotated_version_path.exists():
            return []
        try:
            data = json.loads(self.annotated_version_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [annotated_version_from_mapping(item) for item in data.get("versions") or [] if isinstance(item, Mapping)]

    def _write_versions(self, versions: Sequence[AnnotatedDatasetVersion]) -> None:
        payload = {"schema_version": ANNOTATED_DATASET_SCHEMA_VERSION, "updated_at": _utc_now(), "versions": [item.as_dict() for item in versions]}
        _atomic_write_text(self.annotated_version_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    def _ensure_dirs(self) -> None:
        self.annotation_path.parent.mkdir(parents=True, exist_ok=True)
        self.workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.annotated_version_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)


def annotation_from_registry_entry(
    entry: EvaluationRegistryEntry,
    task_id: str,
    reviewer_id: str = "",
    **kwargs: Any,
) -> HumanReviewAnnotation:
    task = _task_for_annotation(entry, task_id)
    source_refs = list(task.source_refs) if task else []
    return HumanReviewAnnotation(
        registry_id=entry.registry_id,
        request_id=entry.request_id,
        final_answer_sha256=entry.final_answer_sha256,
        task_id=task_id,
        record_type=entry.record_type,
        reviewer_id=reviewer_id,
        source_refs_snapshot=source_refs,
        hashes_snapshot=dict(entry.hashes),
        execution_allowed=bool(entry.execution_allowed),
        **kwargs,
    )


def workflow_state_for(registry_id: str, annotations: Sequence[HumanReviewAnnotation]) -> ReviewWorkflowState:
    if not annotations:
        return ReviewWorkflowState(registry_id=registry_id)
    latest = sorted(annotations, key=lambda item: item.updated_at or item.created_at)[-1]
    severities = [item.severity for item in annotations]
    open_issue = latest.review_status in {"IN_REVIEW", "NEEDS_FIX", "REJECTED"} or latest.quality_decision in {"LOW_QUALITY", "INVALID", "UNSAFE"}
    return ReviewWorkflowState(
        registry_id=registry_id,
        current_status=latest.review_status,
        latest_annotation_id=latest.annotation_id,
        annotation_count=len(annotations),
        reviewer_ids=_ordered_unique(item.reviewer_id for item in annotations),
        has_open_issue=open_issue,
        highest_severity=_highest_severity(severities),
        needs_followup=open_issue or _highest_severity(severities) in {"HIGH", "CRITICAL"},
        locked=any(item.locked for item in annotations),
        updated_at=latest.updated_at,
    )


def annotation_from_mapping(data: Mapping[str, Any]) -> HumanReviewAnnotation:
    return HumanReviewAnnotation(
        annotation_id=str(data.get("annotation_id") or ""),
        created_at=str(data.get("created_at") or _utc_now()),
        updated_at=str(data.get("updated_at") or data.get("created_at") or _utc_now()),
        registry_id=str(data.get("registry_id") or ""),
        request_id=str(data.get("request_id") or ""),
        final_answer_sha256=str(data.get("final_answer_sha256") or ""),
        task_id=str(data.get("task_id") or ""),
        record_type=str(data.get("record_type") or ""),
        reviewer_id=str(data.get("reviewer_id") or ""),
        review_status=str(data.get("review_status") or "UNREVIEWED"),
        quality_decision=str(data.get("quality_decision") or "NOT_APPLICABLE"),
        correctness_label=str(data.get("correctness_label") or "NOT_APPLICABLE"),
        grounding_label=str(data.get("grounding_label") or "NOT_APPLICABLE"),
        safety_label=str(data.get("safety_label") or "NOT_APPLICABLE"),
        task_scope_label=str(data.get("task_scope_label") or "NOT_APPLICABLE"),
        reason_codes=[str(value) for value in data.get("reason_codes") or []],
        reviewer_note=str(data.get("reviewer_note") or ""),
        suggested_fix_summary=str(data.get("suggested_fix_summary") or ""),
        severity=str(data.get("severity") or "LOW"),
        locked=bool(data.get("locked") or False),
        locked_at=str(data.get("locked_at") or ""),
        source_refs_snapshot=[str(value) for value in data.get("source_refs_snapshot") or []],
        hashes_snapshot=dict(data.get("hashes_snapshot") or {}),
        execution_allowed=bool(data.get("execution_allowed") or False),
        schema_version=str(data.get("schema_version") or ANNOTATION_SCHEMA_VERSION),
    )


def annotated_version_from_mapping(data: Mapping[str, Any]) -> AnnotatedDatasetVersion:
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
        locked=bool(data.get("locked") or False),
        limitations=[str(value) for value in data.get("limitations") or []],
        export_paths=dict(data.get("export_paths") or {}),
        schema_version=str(data.get("schema_version") or ANNOTATED_DATASET_SCHEMA_VERSION),
    )


def _validate_annotation(annotation: HumanReviewAnnotation) -> List[str]:
    warnings: List[str] = []
    if annotation.review_status not in REVIEW_STATUSES:
        warnings.append("invalid_review_status")
    if annotation.quality_decision not in QUALITY_DECISIONS:
        warnings.append("invalid_quality_decision")
    if annotation.correctness_label not in CORRECTNESS_LABELS:
        warnings.append("invalid_correctness_label")
    if annotation.grounding_label not in GROUNDING_LABELS:
        warnings.append("invalid_grounding_label")
    if annotation.safety_label not in SAFETY_LABELS:
        warnings.append("invalid_safety_label")
    if annotation.task_scope_label not in TASK_SCOPE_LABELS:
        warnings.append("invalid_task_scope_label")
    if annotation.severity not in SEVERITIES:
        warnings.append("invalid_severity")
    unknown = [code for code in annotation.reason_codes if code not in REASON_CODE_TAXONOMY]
    if unknown:
        warnings.append("unknown_reason_code")
    if annotation.execution_allowed:
        warnings.append("execution_allowed_true")
    if not annotation.registry_id or not annotation.task_id:
        warnings.append("missing_binding")
    return warnings


def _sanitize_annotation(annotation: HumanReviewAnnotation) -> tuple[HumanReviewAnnotation, int]:
    data = annotation.as_dict()
    redactions = 0
    for field_name in ("reviewer_note", "suggested_fix_summary"):
        text, count = _redact_text(str(data.get(field_name) or ""))
        data[field_name] = text
        redactions += count
    sanitized = annotation_from_mapping(data)
    return sanitized, redactions


def _redact_text(text: str) -> tuple[str, int]:
    redactions = 0
    output = text
    for pattern in SECRET_PATTERNS:
        output, count = pattern.subn("[REDACTED_SECRET]", output)
        redactions += count
    for pattern in REGISTRY_SAFETY_PATTERNS:
        output, count = pattern.subn("[REDACTED_UNSAFE_DETAIL]", output)
        redactions += count
    output = re.sub(r"(?<=\[REDACTED_UNSAFE_DETAIL\])[0-9.,%]+", "", output)
    return output, redactions


def _unsafe_mapping(data: Any) -> bool:
    keys = {key.lower() for key in _mapping_keys(data)}
    if keys & UNSAFE_FIELD_NAMES:
        return True
    text = " ".join(_string_values(data))
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _annotation_matches(annotation: HumanReviewAnnotation, filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if not expected:
            continue
        if key == "severity" and annotation.severity != expected:
            return False
        if key == "review_status" and annotation.review_status != expected:
            return False
        if key == "reason_code" and expected not in annotation.reason_codes:
            return False
        if getattr(annotation, key, None) != expected:
            return False
    return True


def _state_matches(state: ReviewWorkflowState, filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected and getattr(state, key, None) != expected:
            return False
    return True


def _task_for_annotation(entry: EvaluationRegistryEntry | None, task_id: str):
    if not entry:
        return None
    return next((task for task in entry.task_index if task.task_id == task_id), None)


def _annotation_id(annotation: HumanReviewAnnotation) -> str:
    payload = {
        "registry_id": annotation.registry_id,
        "task_id": annotation.task_id,
        "reviewer_id": annotation.reviewer_id,
        "created_at": annotation.created_at,
        "review_status": annotation.review_status,
    }
    return f"human_review:{_hash_payload(payload)[:16]}"


def _highest_severity(values: Iterable[str]) -> str:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    return max((value for value in values if value in order), key=lambda value: order[value], default="LOW")


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


def _hash_payload(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _csv(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    fieldnames = sorted({key for row in rows for key in row.keys()})
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return output.getvalue()


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(value).lower()).strip("-")[:80]


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
