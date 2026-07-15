from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from src.services.agents.evaluation_registry import (
    EvaluationRegistry,
    EvaluationRegistryEntry,
    EvaluationRegistryTaskIndex,
    REGISTRY_SAFETY_PATTERNS,
    SECRET_PATTERNS,
)


PERSISTENCE_SCHEMA_VERSION = "evaluation_persistence.v1"
DATASET_MANIFEST_SCHEMA_VERSION = "evaluation_dataset_manifest.v1"
DEFAULT_BASE_DIR = Path("data") / "evaluations"
DEFAULT_REGISTRY_PATH = DEFAULT_BASE_DIR / "registry" / "evaluation_registry.jsonl"
DEFAULT_MANIFEST_PATH = DEFAULT_BASE_DIR / "versions" / "dataset_versions.json"
DEFAULT_EXPORT_DIR = DEFAULT_BASE_DIR / "exports"

REQUIRED_PERSISTED_FIELDS = {
    "schema_version",
    "registry_id",
    "record_type",
    "request_id",
    "task_ids",
    "final_answer_sha256",
    "task_index",
    "safety_index",
    "evaluation_index",
    "hashes",
    "storage_hash",
}

UNSAFE_FIELD_NAMES = {
    "raw_prompt",
    "full_prompt",
    "hidden_prompt",
    "system_prompt",
    "developer_prompt",
    "final_answer_text",
    "raw_final_answer",
    "full_final_answer",
    "account_balance",
    "account_equity",
    "account_number",
    "order_id",
    "order_history",
    "open_position",
    "real_position",
    "entry_price",
    "stop_loss",
    "take_profit",
    "lot_size",
    "position_size",
    "account_risk_percent",
    "mt5_credentials",
    "mt5_password",
    "broker_credentials",
}


@dataclass
class PersistResult:
    status: str
    registry_id: str = ""
    storage_path: str = ""
    storage_hash: str = ""
    redactions: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "registry_id": self.registry_id,
            "storage_path": self.storage_path,
            "storage_hash": self.storage_hash,
            "redactions": self.redactions,
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
        }


@dataclass
class PersistBatchResult:
    status: str
    entries: int = 0
    saved: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    results: List[PersistResult] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "entries": self.entries,
            "saved": self.saved,
            "duplicates": self.duplicates,
            "rejected": self.rejected,
            "failed": self.failed,
            "results": [item.as_dict() for item in self.results],
            "latency_ms": self.latency_ms,
        }


@dataclass
class ValidationResult:
    status: str
    entries_checked: int = 0
    invalid_entries: int = 0
    duplicate_entries: int = 0
    unsafe_entries: int = 0
    schema_versions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "entries_checked": self.entries_checked,
            "invalid_entries": self.invalid_entries,
            "duplicate_entries": self.duplicate_entries,
            "unsafe_entries": self.unsafe_entries,
            "schema_versions": list(self.schema_versions),
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
        }


@dataclass
class CompactResult:
    status: str
    before_entries: int = 0
    after_entries: int = 0
    storage_path: str = ""
    latency_ms: float = 0.0


@dataclass
class ExportResult:
    status: str
    version_id: str = ""
    export_path: str = ""
    format: str = "json"
    payload_chars: int = 0
    redactions: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "version_id": self.version_id,
            "export_path": self.export_path,
            "format": self.format,
            "payload_chars": self.payload_chars,
            "redactions": self.redactions,
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
        }


@dataclass
class ImportResult:
    status: str
    imported_count: int = 0
    skipped_duplicates: int = 0
    rejected_count: int = 0
    warnings: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "imported_count": self.imported_count,
            "skipped_duplicates": self.skipped_duplicates,
            "rejected_count": self.rejected_count,
            "warnings": list(self.warnings),
            "latency_ms": self.latency_ms,
        }


@dataclass
class EvaluationDatasetVersion:
    version_id: str
    created_at: str
    name: str
    description: str = ""
    source: Dict[str, Any] = field(default_factory=dict)
    entries_count: int = 0
    request_ids: List[str] = field(default_factory=list)
    final_answer_hashes: List[str] = field(default_factory=list)
    record_type_counts: Dict[str, int] = field(default_factory=dict)
    quality_counts: Dict[str, int] = field(default_factory=dict)
    status_counts: Dict[str, int] = field(default_factory=dict)
    safety_flag_count: int = 0
    review_priority_counts: Dict[str, int] = field(default_factory=dict)
    dataset_hash: str = ""
    export_paths: Dict[str, str] = field(default_factory=dict)
    schema_version: str = DATASET_MANIFEST_SCHEMA_VERSION
    limitations: List[str] = field(default_factory=list)
    registry_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "created_at": self.created_at,
            "name": self.name,
            "description": self.description,
            "source": dict(self.source),
            "entries_count": self.entries_count,
            "request_ids": list(self.request_ids),
            "final_answer_hashes": list(self.final_answer_hashes),
            "record_type_counts": dict(self.record_type_counts),
            "quality_counts": dict(self.quality_counts),
            "status_counts": dict(self.status_counts),
            "safety_flag_count": self.safety_flag_count,
            "review_priority_counts": dict(self.review_priority_counts),
            "dataset_hash": self.dataset_hash,
            "export_paths": dict(self.export_paths),
            "schema_version": self.schema_version,
            "limitations": list(self.limitations),
            "registry_ids": list(self.registry_ids),
        }


@dataclass
class EvaluationDatasetManifest:
    schema_version: str = DATASET_MANIFEST_SCHEMA_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    versions: List[EvaluationDatasetVersion] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "versions": [version.as_dict() for version in self.versions],
        }


class EvaluationPersistenceStore:
    def __init__(
        self,
        registry_path: str | Path | None = None,
        manifest_path: str | Path | None = None,
        export_dir: str | Path | None = None,
    ):
        self.registry_path = Path(registry_path or DEFAULT_REGISTRY_PATH)
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST_PATH)
        self.export_dir = Path(export_dir or DEFAULT_EXPORT_DIR)

    def save_entry(self, entry: EvaluationRegistryEntry | Mapping[str, Any]) -> PersistResult:
        started = time.perf_counter()
        registry_entry = EvaluationRegistry._entry(entry) if isinstance(entry, Mapping) else entry
        self._ensure_dirs()
        payload, warnings = _persisted_payload(registry_entry)
        if warnings:
            return self._persist_result("REJECTED_UNSAFE", registry_entry, "", 0, warnings, started)
        if self.exists(registry_entry.registry_id):
            return self._persist_result("SKIPPED_DUPLICATE", registry_entry, "", 0, [], started)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        try:
            with self.registry_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            result = self._persist_result("SAVED", registry_entry, payload["storage_hash"], 0, [], started)
        except OSError as exc:
            result = self._persist_result("FAILED", registry_entry, "", 0, [exc.__class__.__name__], started)
        print(
            "[EvaluationPersistence] "
            f"action=save entries=1 saved={1 if result.status == 'SAVED' else 0} "
            f"duplicates={1 if result.status == 'SKIPPED_DUPLICATE' else 0} "
            f"rejected={1 if result.status == 'REJECTED_UNSAFE' else 0} latency_ms={result.latency_ms}"
        )
        return result

    def save_entries(self, entries: Sequence[EvaluationRegistryEntry | Mapping[str, Any]]) -> PersistBatchResult:
        started = time.perf_counter()
        results = [self.save_entry(entry) for entry in entries]
        batch = PersistBatchResult(
            status="PASS" if all(result.status in {"SAVED", "SKIPPED_DUPLICATE"} for result in results) else "WARN",
            entries=len(entries),
            saved=sum(1 for result in results if result.status == "SAVED"),
            duplicates=sum(1 for result in results if result.status == "SKIPPED_DUPLICATE"),
            rejected=sum(1 for result in results if result.status == "REJECTED_UNSAFE"),
            failed=sum(1 for result in results if result.status == "FAILED"),
            results=results,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        print(
            "[EvaluationPersistence] "
            f"action=save entries={batch.entries} saved={batch.saved} duplicates={batch.duplicates} "
            f"rejected={batch.rejected} latency_ms={batch.latency_ms}"
        )
        return batch

    def load_entries(self, filters: Mapping[str, Any] | None = None) -> List[EvaluationRegistryEntry]:
        started = time.perf_counter()
        entries = [entry for _, entry in self._iter_valid_entries()]
        registry = EvaluationRegistry(entries)
        results = registry.list_registry_entries(filters or {})
        print(
            "[EvaluationPersistence] "
            f"action=load entries={len(results)} filters={dict(filters or {})} "
            f"latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return results

    def load_latest(self, limit: int | None = None) -> List[EvaluationRegistryEntry]:
        entries = sorted(self.load_entries(), key=lambda entry: entry.created_at, reverse=True)
        return entries[:limit] if limit else entries

    def exists(self, registry_id: str) -> bool:
        return any(entry.registry_id == registry_id for entry in self.load_entries())

    def deduplicate(self, entries: Sequence[EvaluationRegistryEntry]) -> List[EvaluationRegistryEntry]:
        seen: Set[str] = set()
        output: List[EvaluationRegistryEntry] = []
        for entry in entries:
            if entry.registry_id and entry.registry_id not in seen:
                seen.add(entry.registry_id)
                output.append(entry)
        return output

    def compact_store(self) -> CompactResult:
        started = time.perf_counter()
        entries = self.load_entries()
        compacted = self.deduplicate(entries)
        self._ensure_dirs()
        tmp = self.registry_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for entry in compacted:
                payload, warnings = _persisted_payload(entry)
                if not warnings:
                    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        tmp.replace(self.registry_path)
        return CompactResult("PASS", len(entries), len(compacted), str(self.registry_path), round((time.perf_counter() - started) * 1000, 3))

    def validate_store(self) -> ValidationResult:
        started = time.perf_counter()
        seen: Set[str] = set()
        versions: Set[str] = set()
        checked = invalid = duplicates = unsafe = 0
        warnings: List[str] = []
        if not self.registry_path.exists():
            return ValidationResult("PASS", 0, latency_ms=round((time.perf_counter() - started) * 1000, 3))
        for line in self.registry_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            checked += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            versions.add(str(payload.get("schema_version") or ""))
            if not REQUIRED_PERSISTED_FIELDS.issubset(payload):
                invalid += 1
                continue
            if payload.get("storage_hash") != _storage_hash({k: v for k, v in payload.items() if k not in {"persisted_at", "storage_hash"}}):
                invalid += 1
            if payload.get("registry_id") in seen:
                duplicates += 1
            seen.add(str(payload.get("registry_id") or ""))
            if _unsafe_warnings(payload):
                unsafe += 1
        if invalid:
            warnings.append("invalid_entries")
        if duplicates:
            warnings.append("duplicate_entries")
        if unsafe:
            warnings.append("unsafe_entries")
        status = "FAIL" if invalid or unsafe else ("WARN" if duplicates else "PASS")
        result = ValidationResult(status, checked, invalid, duplicates, unsafe, sorted(versions), warnings, round((time.perf_counter() - started) * 1000, 3))
        print(
            "[EvaluationPersistence] "
            f"action=validate entries_checked={result.entries_checked} status={result.status} "
            f"unsafe={result.unsafe_entries} duplicates={result.duplicate_entries}"
        )
        return result

    def create_dataset_version(
        self,
        name: str,
        description: str = "",
        filters: Mapping[str, Any] | None = None,
    ) -> EvaluationDatasetVersion:
        started = time.perf_counter()
        filters = dict(filters or {})
        entries = self.load_entries(filters)
        version = _dataset_version(name, description, filters, entries, self.registry_path)
        manifest = self._load_manifest()
        manifest.versions = [item for item in manifest.versions if item.version_id != version.version_id] + [version]
        manifest.updated_at = _utc_now()
        self._write_manifest(manifest)
        print(
            "[EvaluationDatasetVersion] "
            f"action=create version_id={version.version_id} entries={version.entries_count} "
            f"dataset_hash={version.dataset_hash} latency_ms={round((time.perf_counter() - started) * 1000, 3)}"
        )
        return version

    def list_dataset_versions(self) -> List[EvaluationDatasetVersion]:
        return list(self._load_manifest().versions)

    def get_dataset_version(self, version_id: str) -> EvaluationDatasetVersion | None:
        return next((version for version in self.list_dataset_versions() if version.version_id == version_id), None)

    def export_dataset_version(self, version_id: str, format: str = "json") -> ExportResult:
        started = time.perf_counter()
        version = self.get_dataset_version(version_id)
        if not version:
            return ExportResult("FAILED", version_id=version_id, format=format, warnings=["missing_version"], latency_ms=round((time.perf_counter() - started) * 1000, 3))
        self._ensure_dirs()
        entries = [entry for entry in self.load_entries() if entry.registry_id in set(version.registry_ids)]
        dataset = EvaluationRegistry(entries).export_review_dataset({})
        export_format = format.lower()
        path = self.export_dir / f"{_safe_filename(version.version_id)}.{export_format}"
        if export_format == "json":
            persisted = [_persisted_payload(entry)[0] for entry in entries]
            payload = {
                "schema_version": PERSISTENCE_SCHEMA_VERSION,
                "dataset_version": version.as_dict(),
                "review_dataset": dataset.as_dict(),
                "entries": persisted,
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        elif export_format == "csv":
            text = _dataset_csv(dataset.rows)
        else:
            return ExportResult("FAILED", version_id=version_id, format=format, warnings=["unsupported_format"], latency_ms=round((time.perf_counter() - started) * 1000, 3))
        _atomic_write_text(path, text)
        version.export_paths[export_format] = str(path)
        self._upsert_version(version)
        result = ExportResult("EXPORTED", version.version_id, str(path), export_format, len(text), dataset.redactions, latency_ms=round((time.perf_counter() - started) * 1000, 3))
        print(
            "[EvaluationDatasetVersion] "
            f"action=export version_id={version.version_id} format={export_format} "
            f"payload_chars={result.payload_chars} redactions={result.redactions} status={result.status}"
        )
        return result

    def import_dataset_export(self, path: str | Path, validate_only: bool = False) -> ImportResult:
        started = time.perf_counter()
        warnings: List[str] = []
        imported = duplicates = rejected = 0
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ImportResult("FAILED", warnings=[exc.__class__.__name__], latency_ms=round((time.perf_counter() - started) * 1000, 3))
        entries = data.get("entries") if isinstance(data, Mapping) else None
        if not isinstance(entries, list):
            return ImportResult("REJECTED", rejected_count=1, warnings=["missing_entries"], latency_ms=round((time.perf_counter() - started) * 1000, 3))
        for item in entries:
            if not isinstance(item, Mapping) or not REQUIRED_PERSISTED_FIELDS.issubset(item) or _unsafe_warnings(item):
                rejected += 1
                continue
            if self.exists(str(item.get("registry_id") or "")):
                duplicates += 1
                continue
            if not validate_only:
                entry = _entry_from_persisted(item)
                result = self.save_entry(entry)
                if result.status == "SAVED":
                    imported += 1
                elif result.status == "SKIPPED_DUPLICATE":
                    duplicates += 1
                else:
                    rejected += 1
            else:
                imported += 1
        if rejected:
            status = "REJECTED" if validate_only or (imported == 0 and duplicates == 0) else "PARTIAL"
        else:
            status = "VALIDATED" if validate_only else "IMPORTED"
        return ImportResult(status, imported, duplicates, rejected, warnings, round((time.perf_counter() - started) * 1000, 3))

    def _persist_result(self, status: str, entry: EvaluationRegistryEntry, storage_hash: str, redactions: int, warnings: List[str], started: float) -> PersistResult:
        return PersistResult(status, entry.registry_id, str(self.registry_path), storage_hash, redactions, warnings, round((time.perf_counter() - started) * 1000, 3))

    def _iter_valid_entries(self) -> Iterable[tuple[Mapping[str, Any], EvaluationRegistryEntry]]:
        if not self.registry_path.exists():
            return []
        output: List[tuple[Mapping[str, Any], EvaluationRegistryEntry]] = []
        for line in self.registry_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if REQUIRED_PERSISTED_FIELDS.issubset(payload) and not _unsafe_warnings(payload):
                output.append((payload, _entry_from_persisted(payload)))
        return output

    def _ensure_dirs(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> EvaluationDatasetManifest:
        if not self.manifest_path.exists():
            return EvaluationDatasetManifest()
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return EvaluationDatasetManifest()
        return EvaluationDatasetManifest(
            schema_version=str(data.get("schema_version") or DATASET_MANIFEST_SCHEMA_VERSION),
            created_at=str(data.get("created_at") or _utc_now()),
            updated_at=str(data.get("updated_at") or _utc_now()),
            versions=[_version_from_mapping(item) for item in data.get("versions") or [] if isinstance(item, Mapping)],
        )

    def _write_manifest(self, manifest: EvaluationDatasetManifest) -> None:
        self._ensure_dirs()
        _atomic_write_text(self.manifest_path, json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2, sort_keys=True, default=str))

    def _upsert_version(self, version: EvaluationDatasetVersion) -> None:
        manifest = self._load_manifest()
        manifest.versions = [item for item in manifest.versions if item.version_id != version.version_id] + [version]
        manifest.updated_at = _utc_now()
        self._write_manifest(manifest)


def _persisted_payload(entry: EvaluationRegistryEntry) -> tuple[Dict[str, Any], List[str]]:
    safe = {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "registry_id": entry.registry_id,
        "record_type": entry.record_type,
        "request_id": entry.request_id,
        "task_ids": list(entry.task_ids),
        "symbol": entry.symbol,
        "final_answer_sha256": entry.final_answer_sha256,
        "source_record_id": dict(entry.source_record_id),
        "quality_label": entry.quality_label,
        "status": entry.status,
        "review_outcome": entry.review_outcome,
        "review_priority": _review_priority(entry),
        "execution_allowed": bool(entry.execution_allowed),
        "task_index": [task.as_dict() for task in entry.task_index],
        "safety_index": dict(entry.safety_index),
        "evaluation_index": dict(entry.evaluation_index),
        "hashes": dict(entry.hashes),
        "tags": list(entry.tags),
        "limitations": list(entry.limitations),
    }
    warnings = _unsafe_warnings(safe)
    canonical = dict(safe)
    safe["persisted_at"] = _utc_now()
    safe["storage_hash"] = _storage_hash(canonical)
    return safe, warnings


def _entry_from_persisted(data: Mapping[str, Any]) -> EvaluationRegistryEntry:
    return EvaluationRegistryEntry(
        registry_id=str(data.get("registry_id") or ""),
        created_at=str(data.get("persisted_at") or data.get("created_at") or ""),
        record_type=str(data.get("record_type") or ""),
        request_id=str(data.get("request_id") or ""),
        task_ids=[str(value) for value in data.get("task_ids") or []],
        symbol=str(data.get("symbol") or ""),
        final_answer_sha256=str(data.get("final_answer_sha256") or ""),
        source_record_id=dict(data.get("source_record_id") or {}),
        quality_label=str(data.get("quality_label") or ""),
        status=str(data.get("status") or ""),
        review_outcome=str(data.get("review_outcome") or ""),
        execution_allowed=bool(data.get("execution_allowed") or False),
        task_index=[
            EvaluationRegistryTaskIndex(**task)
            for task in data.get("task_index") or []
            if isinstance(task, Mapping)
        ],
        safety_index=dict(data.get("safety_index") or {}),
        evaluation_index=dict(data.get("evaluation_index") or {}),
        hashes=dict(data.get("hashes") or {}),
        tags=[str(value) for value in data.get("tags") or []],
        limitations=[str(value) for value in data.get("limitations") or []],
    )


def _dataset_version(name: str, description: str, filters: Mapping[str, Any], entries: Sequence[EvaluationRegistryEntry], store_path: Path) -> EvaluationDatasetVersion:
    persisted = [_persisted_payload(entry)[0] for entry in entries]
    dataset_hash = _storage_hash({"entries": [{k: v for k, v in item.items() if k != "persisted_at"} for item in persisted]})
    version_id = f"dataset_version:{_safe_filename(name) or 'dataset'}:{dataset_hash[:12]}"
    return EvaluationDatasetVersion(
        version_id=version_id,
        created_at=_utc_now(),
        name=name,
        description=description,
        source={"registry_store_path": str(store_path), "filters_used": dict(filters)},
        entries_count=len(entries),
        request_ids=_ordered_unique(entry.request_id for entry in entries),
        final_answer_hashes=_ordered_unique(entry.final_answer_sha256 for entry in entries),
        record_type_counts=_counts(entry.record_type for entry in entries),
        quality_counts=_counts(entry.quality_label for entry in entries),
        status_counts=_counts(entry.status for entry in entries),
        safety_flag_count=sum(1 for entry in entries if _safety_flags(entry.safety_index)),
        review_priority_counts=_counts(_review_priority(entry) for entry in entries),
        dataset_hash=dataset_hash,
        registry_ids=[entry.registry_id for entry in entries],
    )


def _version_from_mapping(data: Mapping[str, Any]) -> EvaluationDatasetVersion:
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
        schema_version=str(data.get("schema_version") or DATASET_MANIFEST_SCHEMA_VERSION),
        limitations=[str(value) for value in data.get("limitations") or []],
        registry_ids=[str(value) for value in data.get("registry_ids") or []],
    )


def _unsafe_warnings(value: Any) -> List[str]:
    warnings: List[str] = []
    field_names = {key.lower() for key in _mapping_keys(value)}
    if field_names & UNSAFE_FIELD_NAMES:
        warnings.append("unsafe_field")
    text = " ".join(_string_values(value))
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        warnings.append("secret_like_value")
    if any(pattern.search(text) for pattern in REGISTRY_SAFETY_PATTERNS):
        warnings.append("prohibited_trading_or_execution_text")
    if isinstance(value, Mapping):
        safety = value.get("safety_index") if isinstance(value.get("safety_index"), Mapping) else value.get("safety_summary")
        if isinstance(safety, Mapping) and (safety.get("prohibited_outputs_detected") or safety.get("execution_allowed")):
            warnings.append("unsafe_safety_index")
        if value.get("execution_allowed") is True:
            warnings.append("execution_allowed_true")
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


def _review_priority(entry: EvaluationRegistryEntry) -> str:
    if entry.execution_allowed or _safety_flags(entry.safety_index) or entry.status in {"FAIL", "DEGRADED"} or entry.quality_label in {"unsafe_or_noncompliant", "failed_validation", "incomplete", "invalid_input"}:
        return "HIGH"
    if entry.status in {"WARN", "EVALUATED_WITH_WARNINGS", "INSUFFICIENT_DATA", "SKIPPED"} or entry.quality_label in {"acceptable", "limited_review", "degraded"}:
        return "MEDIUM"
    return str(entry.evaluation_index.get("review_priority") or "LOW").upper()


def _safety_flags(index: Mapping[str, Any]) -> List[str]:
    return [key for key, value in index.items() if value and (key.endswith("_detected") or key in {"prohibited_outputs_detected", "execution_allowed"})]


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


def _storage_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _dataset_csv(rows: Sequence[Mapping[str, Any]]) -> str:
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
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(value).strip().lower()).strip("-")[:80]


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
