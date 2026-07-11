import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import Config
from src.services.knowledge.auto_manifest_service import AutoManifestService
from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.chunk_builder import ChunkBuilder
from src.services.knowledge.document_parser import DocumentParserRegistry
from src.services.knowledge.ingestion_fingerprint import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    METADATA_SCHEMA_VERSION,
    IngestionFingerprintBuilder,
)
from src.services.knowledge.fast_precheck_fingerprint import FastPrecheckFingerprintService
from src.services.knowledge.metadata_resolver import MetadataResolver
from src.services.knowledge.retrieval_smoke import RetrievalSmokeEvaluator, RetrievalSmokeStatus
from src.services.knowledge.validator import Validator


SUPPORTED_EXTENSIONS = {".pdf", ".epub"}
BLOCKED_CHUNK_STATUSES = {"EMPTY_DOCUMENT", "NEEDS_OCR", "FAILED"}
IGNORED_DISCOVERY_NAMES = {".gitkeep", ".ds_store"}
IGNORED_DISCOVERY_SUFFIXES = {".tmp", ".bak"}


class IngestionStatus:
    DISCOVERED = "DISCOVERED"
    INDEXED = "INDEXED"
    SKIPPED_ALREADY_INDEXED = "SKIPPED_ALREADY_INDEXED"
    SKIPPED_UNCHANGED = "SKIPPED_UNCHANGED"
    SKIPPED_UNSUPPORTED_EXTENSION = "SKIPPED_UNSUPPORTED_EXTENSION"
    REINDEXED_CONTENT_CHANGED = "REINDEXED_CONTENT_CHANGED"
    REINDEXED_POLICY_CHANGED = "REINDEXED_POLICY_CHANGED"
    DUPLICATE = "DUPLICATE"
    QUARANTINE = "QUARANTINE"
    NEEDS_OCR = "NEEDS_OCR"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    PENDING_RETRY = "PENDING_RETRY"
    FAILED_NON_RETRYABLE = "FAILED_NON_RETRYABLE"
    FAILED_UPSERT = "FAILED_UPSERT"
    FAILED = "FAILED"
    READY = "READY"


@dataclass
class IngestionResult:
    path: str
    status: str
    reason: str = ""
    doc_id: str = ""
    lifecycle: str = ""
    domain: str = ""
    subdomain: str = ""
    document_type: str = ""
    manifest_path: str = ""
    manifest_created: bool = False
    manifest_updated: bool = False
    checksum: str = ""
    parser_type: str = ""
    extraction_status: str = ""
    chunk_policy_id: str = ""
    parent_chunk_count: int = 0
    chunk_count: int = 0
    ingestion_fingerprint: str = ""
    replaces_doc_id: str = ""
    indexed: bool = False
    retrieval_smoke_status: str = ""
    retrieval_smoke_reason: str = ""
    retrieval_smoke_query: str = ""
    top_source_title: str = ""
    top_source_author: str = ""
    top_source_organization: str = ""
    top_source_domain: str = ""
    top_source_subdomain: str = ""
    top_source_event_type: str = ""
    top_source_period: str = ""
    failure_category: str = ""
    retryable: bool = False
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0
    rate_limit_count: int = 0
    fast_precheck_fingerprint: str = ""
    fast_precheck_payload: Dict[str, Any] = field(default_factory=dict)
    fast_precheck_content_sha256: str = ""
    fast_precheck_file_size: int = 0
    fast_precheck_mtime_ns: int = 0
    precheck_status: str = ""
    precheck_reason: str = ""
    precheck_skipped: bool = False
    fast_precheck_backfilled: bool = False
    fast_precheck_missing: bool = False
    parsed: bool = False
    precheck_duration_ms: float = 0.0
    parse_duration_ms: float = 0.0
    elapsed_ms: float = 0.0
    messages: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


@dataclass
class KnowledgeUpdateReport:
    repository_path: str
    job_id: str
    discovered: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    pending_retry: int = 0
    failed_non_retryable: int = 0
    failed_upsert: int = 0
    needs_ocr: int = 0
    quarantined: int = 0
    duplicates: int = 0
    unsupported: int = 0
    smoke_pass: int = 0
    smoke_skipped: int = 0
    smoke_fail: int = 0
    rate_limit_count: int = 0
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0
    precheck_skipped: int = 0
    fast_precheck_backfilled: int = 0
    fast_precheck_missing: int = 0
    parsed: int = 0
    skipped_after_parse: int = 0
    total_duration_ms: float = 0.0
    precheck_duration_ms: float = 0.0
    parse_duration_ms: float = 0.0
    results: List[IngestionResult] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)

    def add_result(self, result: IngestionResult) -> None:
        self.results.append(result)
        if result.status in {
            IngestionStatus.INDEXED,
            IngestionStatus.REINDEXED_CONTENT_CHANGED,
            IngestionStatus.REINDEXED_POLICY_CHANGED,
        }:
            self.indexed += 1
        elif result.status == IngestionStatus.NEEDS_OCR:
            self.needs_ocr += 1
            self.skipped += 1
        elif result.status == IngestionStatus.QUARANTINE:
            self.quarantined += 1
            self.skipped += 1
        elif result.status == IngestionStatus.DUPLICATE:
            self.duplicates += 1
            self.skipped += 1
        elif result.status == IngestionStatus.SKIPPED_UNSUPPORTED_EXTENSION:
            self.unsupported += 1
            self.skipped += 1
        elif result.status == IngestionStatus.FAILED:
            self.failed += 1
        elif result.status == IngestionStatus.PENDING_RETRY:
            self.pending_retry += 1
        elif result.status == IngestionStatus.FAILED_NON_RETRYABLE:
            self.failed_non_retryable += 1
            self.failed += 1
        elif result.status == IngestionStatus.FAILED_UPSERT:
            self.failed_upsert += 1
            self.failed += 1
        elif result.status == IngestionStatus.SKIPPED_ALREADY_INDEXED:
            self.skipped += 1
            if result.precheck_skipped:
                self.precheck_skipped += 1
            else:
                self.skipped_after_parse += 1
        elif result.status == IngestionStatus.DISCOVERED:
            return
        else:
            self.skipped += 1
        if result.fast_precheck_backfilled:
            self.fast_precheck_backfilled += 1
        if result.fast_precheck_missing:
            self.fast_precheck_missing += 1
        if result.retrieval_smoke_status == RetrievalSmokeStatus.PASS:
            self.smoke_pass += 1
        elif result.retrieval_smoke_status == RetrievalSmokeStatus.SKIPPED:
            self.smoke_skipped += 1
        elif result.retrieval_smoke_status == RetrievalSmokeStatus.FAIL:
            self.smoke_fail += 1
        self.rate_limit_count += int(result.rate_limit_count or 0)
        self.embedding_cache_hits += int(result.embedding_cache_hits or 0)
        self.embedding_cache_misses += int(result.embedding_cache_misses or 0)
        if result.parsed:
            self.parsed += 1
        self.precheck_duration_ms += float(result.precheck_duration_ms or 0.0)
        self.parse_duration_ms += float(result.parse_duration_ms or 0.0)

    def summary(self) -> Dict[str, int]:
        return {
            "discovered": self.discovered,
            "indexed": self.indexed,
            "skipped": self.skipped,
            "failed": self.failed,
            "pending_retry": self.pending_retry,
            "failed_non_retryable": self.failed_non_retryable,
            "failed_upsert": self.failed_upsert,
            "needs_ocr": self.needs_ocr,
            "quarantined": self.quarantined,
            "duplicates": self.duplicates,
            "unsupported": self.unsupported,
            "smoke_pass": self.smoke_pass,
            "smoke_skipped": self.smoke_skipped,
            "smoke_fail": self.smoke_fail,
            "rate_limit_count": self.rate_limit_count,
            "embedding_cache_hits": self.embedding_cache_hits,
            "embedding_cache_misses": self.embedding_cache_misses,
            "precheck_skipped": self.precheck_skipped,
            "fast_precheck_backfilled": self.fast_precheck_backfilled,
            "fast_precheck_missing": self.fast_precheck_missing,
            "parsed": self.parsed,
            "skipped_after_parse": self.skipped_after_parse,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "precheck_duration_ms": round(self.precheck_duration_ms, 2),
            "parse_duration_ms": round(self.parse_duration_ms, 2),
        }


class DocumentDiscoveryService:
    def __init__(self, supported_extensions: Optional[set[str]] = None):
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS

    def discover(self, repository_path: str, include_unsupported: bool = True) -> List[Path]:
        root = Path(repository_path)
        if not root.exists():
            return []
        files = [
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.name.endswith(".manifest.yaml")
            and not self._should_ignore(path)
        ]
        if include_unsupported:
            return sorted(files)
        return sorted(path for path in files if path.suffix.lower() in self.supported_extensions)

    def _should_ignore(self, path: Path) -> bool:
        name = path.name.lower()
        suffix = path.suffix.lower()
        return (
            name in IGNORED_DISCOVERY_NAMES
            or suffix in IGNORED_DISCOVERY_SUFFIXES
            or "__pycache__" in [part.lower() for part in path.parts]
        )


class KnowledgeUpdateService:
    """UI/CLI-safe controller for Knowledge Platform V3 repository updates."""

    def __init__(
        self,
        repository_path: Optional[str] = None,
        discovery_service: Optional[DocumentDiscoveryService] = None,
        auto_manifest_service: Optional[AutoManifestService] = None,
        parser_registry: Optional[DocumentParserRegistry] = None,
        resolver: Optional[Any] = None,
        validator: Optional[Any] = None,
        chunk_builder: Optional[Any] = None,
        catalog: Optional[Any] = None,
        vector_service: Optional[Any] = None,
        fingerprint_builder: Optional[IngestionFingerprintBuilder] = None,
        retrieval_smoke_evaluator: Optional[Any] = None,
        fast_precheck_service: Optional[Any] = None,
    ):
        self.repository_path = repository_path or str(Config.DATA_DIR / "knowledge_repository")
        self.discovery_service = discovery_service or DocumentDiscoveryService()
        self.auto_manifest_service = auto_manifest_service or AutoManifestService()
        self.parser_registry = parser_registry or DocumentParserRegistry()
        self.catalog = catalog or KnowledgeCatalog()

        if resolver is None:
            from src.services.knowledge.registry_loader import RegistryLoader

            resolver = MetadataResolver.__new__(MetadataResolver)
            resolver.registry = RegistryLoader()
            resolver.catalog = self.catalog
        self.resolver = resolver

        self.validator = validator or Validator()
        self.chunk_builder = chunk_builder or ChunkBuilder(parser_registry=self.parser_registry)
        self.vector_service = vector_service
        self.fingerprint_builder = fingerprint_builder or IngestionFingerprintBuilder()
        self.retrieval_smoke_evaluator = retrieval_smoke_evaluator
        self.fast_precheck_service = fast_precheck_service

    def scan_repository(self, repository_path: Optional[str] = None) -> KnowledgeUpdateReport:
        repo = repository_path or self.repository_path
        job_id = f"kp_scan_{uuid.uuid4().hex}"
        files = self.discovery_service.discover(repo, include_unsupported=True)
        report = KnowledgeUpdateReport(repository_path=repo, job_id=job_id, discovered=len(files))
        self._log_report(report, f"job_id={job_id} stage=discover discovered={len(files)}")

        for file_path in files:
            extension = file_path.suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                result = IngestionResult(
                    path=str(file_path),
                    status=IngestionStatus.SKIPPED_UNSUPPORTED_EXTENSION,
                    reason=f"Unsupported extension: {extension}",
                    document_type=extension.lstrip("."),
                )
            else:
                result = IngestionResult(
                    path=str(file_path),
                    status=IngestionStatus.DISCOVERED,
                    document_type=extension.lstrip("."),
                )
            report.add_result(result)
        return report

    def update_repository(self, repository_path: Optional[str] = None) -> KnowledgeUpdateReport:
        repo = repository_path or self.repository_path
        job_id = f"kp_update_{uuid.uuid4().hex}"
        report_start = time.perf_counter()
        if Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY:
            retry_docs = self.catalog.get_retryable_documents() if hasattr(self.catalog, "get_retryable_documents") else []
            files = [Path(row["source_path"]) for row in retry_docs if row.get("source_path")]
            self._log_retry_mode(job_id, len(files))
        else:
            files = self.discovery_service.discover(repo, include_unsupported=True)
        if Config.KNOWLEDGE_UPDATE_MAX_DOCS_PER_RUN and Config.KNOWLEDGE_UPDATE_MAX_DOCS_PER_RUN > 0:
            files = files[: Config.KNOWLEDGE_UPDATE_MAX_DOCS_PER_RUN]
        report = KnowledgeUpdateReport(repository_path=repo, job_id=job_id, discovered=len(files))
        self._log_report(report, f"job_id={job_id} stage=discover discovered={len(files)}")

        for file_path in files:
            result = self.update_file(str(file_path), job_id=job_id)
            report.add_result(result)

        report.total_duration_ms = round((time.perf_counter() - report_start) * 1000, 2)
        self._log_report(
            report,
            "final "
            f"discovered={report.discovered} precheck_skipped={report.precheck_skipped} "
            f"parsed={report.parsed} indexed={report.indexed} skipped_after_parse={report.skipped_after_parse} "
            f"fast_precheck_backfilled={report.fast_precheck_backfilled} "
            f"fast_precheck_missing={report.fast_precheck_missing} "
            f"pending_retry={report.pending_retry} failed_upsert={report.failed_upsert} "
            f"needs_ocr={report.needs_ocr} quarantined={report.quarantined} failed={report.failed}",
        )
        return report

    def update_file(self, file_path: str, job_id: Optional[str] = None) -> IngestionResult:
        start = time.perf_counter()
        path = Path(file_path)
        job_id = job_id or f"kp_update_{uuid.uuid4().hex}"
        result = IngestionResult(path=str(path), status=IngestionStatus.READY, document_type=path.suffix.lower().lstrip("."))

        try:
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                result.status = IngestionStatus.SKIPPED_UNSUPPORTED_EXTENSION
                result.reason = f"Unsupported extension: {path.suffix.lower()}"
                self._log_result(result, f"job_id={job_id} file={path} stage=skip reason={result.reason}")
                return self._finish(result, start)

            path_error = self._validate_repository_path(path)
            if path_error:
                result.status = IngestionStatus.QUARANTINE
                result.reason = path_error
                result.messages.append(path_error)
                self._log_result(result, f"job_id={job_id} file={path} stage=metadata status=QUARANTINE reason={path_error}")
                return self._finish(result, start)

            content_hash = None
            if Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED:
                precheck_start = time.perf_counter()
                self._log_fast_precheck(str(path), "status=start")
                content_hash = self._get_fast_precheck_service().compute_content_hash(str(path))
                result.precheck_duration_ms += round((time.perf_counter() - precheck_start) * 1000, 2)

            manifest_hints = {"checksum": content_hash.content_sha256} if content_hash else None
            manifest_result = self.auto_manifest_service.ensure_manifest(
                str(path),
                mutate=True,
                update_checksum=True,
                metadata_hints=manifest_hints,
            )
            result.manifest_path = manifest_result.manifest_path
            result.manifest_created = manifest_result.created
            result.manifest_updated = manifest_result.updated
            result.checksum = manifest_result.data.get("checksum", "")
            self._log_result(
                result,
                f"job_id={job_id} file={path} stage=manifest "
                f"status={'created' if manifest_result.created else 'updated' if manifest_result.updated else 'ok'}",
            )

            metadata = self.resolver.resolve(str(path))
            if metadata.get("lifecycle") == "QUARANTINE":
                result.status = self._quarantine_status(metadata)
                result.reason = metadata.get("error", "QUARANTINE")
                result.messages.append(result.reason)
                self._log_result(result, f"job_id={job_id} file={path} stage=metadata status={result.status} reason={result.reason}")
                return self._finish(result, start)

            self._apply_metadata(result, metadata)
            result.replaces_doc_id = metadata.get("replaces_doc_id", "")
            self._log_result(
                result,
                f"job_id={job_id} file={path} stage=metadata "
                f"domain={result.domain} subdomain={result.subdomain} owner={manifest_result.data.get('author_slug', '')} "
                f"replaces_doc_id={result.replaces_doc_id}",
            )
            if metadata.get("routing_metadata", {}).get("knowledge_type") == "report":
                document_metadata = metadata.get("document_metadata", {}) or {}
                report_line = (
                    f"[ReportMetadata] job_id={job_id} file={path} "
                    f"organization={document_metadata.get('organization', '')} "
                    f"event_type={document_metadata.get('event_type', '')} "
                    f"period={document_metadata.get('period', '')}"
                )
                result.logs.append(report_line)
                print(report_line)

            validation = self.validator.validate(str(path), metadata)
            result.messages.extend(getattr(validation, "messages", []))
            if not validation.is_valid or validation.level in {"ERROR", "FATAL"}:
                result.status = IngestionStatus.FAILED
                result.reason = self._validation_reason(validation)
                self._mark_catalog_failure(result, result.reason)
                self._log_result(result, f"job_id={job_id} file={path} stage=validate status=FAILED errors={result.reason}")
                return self._finish(result, start)

            if Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED:
                precheck_start = time.perf_counter()
                fast_precheck = self._get_fast_precheck_service().build(
                    str(path),
                    manifest_result.data,
                    metadata,
                    content_hash=content_hash,
                )
                result.fast_precheck_fingerprint = fast_precheck.fingerprint
                result.fast_precheck_payload = fast_precheck.payload
                result.fast_precheck_content_sha256 = fast_precheck.content_hash.content_sha256
                result.fast_precheck_file_size = fast_precheck.content_hash.file_size
                result.fast_precheck_mtime_ns = fast_precheck.content_hash.mtime_ns
                existing_precheck = self.catalog.get_document(result.doc_id) if result.doc_id else None
                decision = self._get_fast_precheck_service().decide(
                    fast_precheck.fingerprint,
                    existing_precheck,
                    retry_failed_only=bool(Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY),
                )
                result.fast_precheck_missing = decision.reason == "NO_PREVIOUS_FAST_FINGERPRINT"
                result.precheck_duration_ms += round((time.perf_counter() - precheck_start) * 1000, 2)
                previous_fp = (existing_precheck or {}).get("fast_precheck_fingerprint", "")
                if decision.should_skip:
                    result.status = IngestionStatus.SKIPPED_ALREADY_INDEXED
                    result.reason = decision.reason
                    result.precheck_status = "SKIP_BEFORE_PARSE"
                    result.precheck_reason = decision.reason
                    result.precheck_skipped = True
                    result.ingestion_fingerprint = (existing_precheck or {}).get("ingestion_fingerprint", "")
                    result.parser_type = (existing_precheck or {}).get("parser_type", "")
                    result.chunk_count = int((existing_precheck or {}).get("chunk_count") or 0)
                    self._log_fast_precheck(
                        str(path),
                        f"fingerprint={fast_precheck.fingerprint} previous={previous_fp} status=matched",
                    )
                    self.catalog.upsert_document(
                        result.doc_id,
                        {
                            "fast_precheck_fingerprint": fast_precheck.fingerprint,
                            "fast_precheck_fingerprint_version": fast_precheck.payload.get("fast_precheck_version", ""),
                            "fast_precheck_payload": self._json_for_catalog(fast_precheck.payload),
                            "fast_precheck_ingestion_fingerprint": result.ingestion_fingerprint,
                            "fast_precheck_content_sha256": result.fast_precheck_content_sha256,
                            "fast_precheck_file_size": result.fast_precheck_file_size,
                            "fast_precheck_mtime_ns": result.fast_precheck_mtime_ns,
                            "last_precheck_at": time.time(),
                            "last_successful_status": IngestionStatus.SKIPPED_UNCHANGED,
                        },
                    )
                    self._log_result(
                        result,
                        f"job_id={job_id} file={path} stage=precheck "
                        "status=SKIP_BEFORE_PARSE reason=FAST_FINGERPRINT_UNCHANGED",
                    )
                    return self._finish(result, start)
                result.precheck_status = "CONTINUE_PARSE"
                result.precheck_reason = decision.reason
                status_word = "changed" if previous_fp else "continue"
                self._log_fast_precheck(
                    str(path),
                    f"fingerprint={fast_precheck.fingerprint} previous={previous_fp} "
                    f"status={status_word} reason={decision.reason}",
                )
                self._log_result(
                    result,
                    f"job_id={job_id} file={path} stage=precheck "
                    f"status=CONTINUE_PARSE reason={decision.reason}",
                )

            parse_start = time.perf_counter()
            parsed_document = self.parser_registry.parse(str(path))
            result.parse_duration_ms = round((time.perf_counter() - parse_start) * 1000, 2)
            result.parsed = True
            result.parser_type = parsed_document.parser_type
            result.extraction_status = parsed_document.extraction_status
            self._log_result(
                result,
                f"job_id={job_id} file={path} stage=parse parser={parsed_document.parser_type} "
                f"status={parsed_document.extraction_status} chars={parsed_document.extracted_char_count} "
                f"words={parsed_document.extracted_word_count}",
            )

            chunk_result = self.chunk_builder.build_chunks_from_parsed(parsed_document, metadata)
            result.extraction_status = chunk_result.get("status", "")
            chunk_stats = chunk_result.get("chunk_stats", {}) or {}
            result.chunk_policy_id = chunk_stats.get("selected_chunk_policy", "")
            result.parent_chunk_count = int(chunk_stats.get("parent_chunk_count", 0) or 0)
            result.chunk_count = len(chunk_result.get("chunks", []))
            fingerprint = self.fingerprint_builder.build(result.checksum, parsed_document, chunk_result)
            result.ingestion_fingerprint = fingerprint["fingerprint"]
            for warning in chunk_stats.get("policy_warnings", []) or []:
                result.messages.append(f"[WARNING] {warning}")
            self._log_result(
                result,
                f"job_id={job_id} file={path} stage=chunk policy={result.chunk_policy_id} "
                f"parents={result.parent_chunk_count} children={result.chunk_count} "
                f"child_target_tokens={chunk_stats.get('child_target_tokens', '')}",
            )

            if result.extraction_status in BLOCKED_CHUNK_STATUSES:
                result.status = result.extraction_status
                result.reason = chunk_result.get("error") or result.extraction_status
                self._mark_catalog_failure(result, result.reason)
                self._log_result(result, f"job_id={job_id} file={path} stage=skip reason={result.reason}")
                return self._finish(result, start)

            if result.extraction_status == "PARTIAL_TEXT":
                result.messages.append("[WARNING] PARTIAL_TEXT detected; indexing with caution.")

            if Config.KNOWLEDGE_UPDATE_MAX_VECTORS_PER_RUN and result.chunk_count > Config.KNOWLEDGE_UPDATE_MAX_VECTORS_PER_RUN:
                result.status = IngestionStatus.PENDING_RETRY
                result.reason = f"MAX_VECTORS_PER_RUN exceeded: chunks={result.chunk_count}"
                result.retryable = True
                self._mark_catalog_pending_retry(result, "index", "max_vectors_per_run", result.reason, True)
                self._log_result(result, f"job_id={job_id} file={path} stage=index status=PENDING_RETRY reason={result.reason}")
                return self._finish(result, start)

            existing = self.catalog.get_document(result.doc_id) if result.doc_id else None
            reindex_reason = self._determine_reindex_reason(existing, result.checksum, result.ingestion_fingerprint)
            if reindex_reason == "UNCHANGED_ALREADY_INDEXED":
                result.status = IngestionStatus.SKIPPED_ALREADY_INDEXED
                result.reason = reindex_reason
                self._store_fast_precheck_success(result, "SKIPPED_UNCHANGED_AFTER_PARSE")
                self._log_result(
                    result,
                    f"job_id={job_id} file={path} stage=skip reason={result.reason} "
                    f"fingerprint={result.ingestion_fingerprint}",
                )
                return self._finish(result, start)

            if reindex_reason != "NEW_DOCUMENT":
                result.reason = reindex_reason
                result.messages.append(f"[INFO] {reindex_reason}")
                self._log_result(
                    result,
                    f"job_id={job_id} file={path} stage=reindex_required reason={reindex_reason} "
                    f"fingerprint={result.ingestion_fingerprint}",
                )

            self.catalog.upsert_document(result.doc_id, {
                "source_path": str(path),
                "manifest_path": result.manifest_path,
                "checksum": result.checksum,
                "lifecycle": result.lifecycle,
                "index_status": "PENDING",
                "parser_version": parsed_document.parser_version,
                "chunker_version": chunk_result.get("operational_metadata", {}).get("chunker_version", ""),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_version": EMBEDDING_VERSION,
                "index_version": "v3",
                "metadata_schema_version": METADATA_SCHEMA_VERSION,
                "chunks_count": result.chunk_count,
                "vectors_expected": result.chunk_count,
                "parser_type": parsed_document.parser_type,
                "embedding_provider": Config.EMBEDDING_PROVIDER,
            })

            index_job_id = f"{job_id}_{uuid.uuid4().hex}"
            if not self.catalog.acquire_index_lock(result.doc_id, index_job_id, worker_id="knowledge_update"):
                result.status = IngestionStatus.FAILED
                result.reason = "Could not acquire index lock."
                self._mark_catalog_failure(result, result.reason)
                self._log_result(result, f"job_id={job_id} file={path} stage=index status=FAILED reason=lock")
                return self._finish(result, start)

            vector_service = self._get_vector_service()
            ok = self._vector_upsert_document(
                vector_service,
                result.doc_id,
                chunk_result["chunks"],
                index_job_id,
                result.ingestion_fingerprint,
                parsed_document.parser_type,
            )
            if not ok:
                self._apply_vector_failure(result, getattr(vector_service, "last_index_result", {}) or {})
                self._log_result(
                    result,
                    f"job_id={job_id} file={path} stage=index status={result.status} "
                    f"reason={result.reason} category={result.failure_category}",
                )
                return self._finish(result, start)

            if result.replaces_doc_id and result.replaces_doc_id != result.doc_id:
                self._cleanup_replaced_doc(result.replaces_doc_id, result.doc_id)

            self.catalog.upsert_document(result.doc_id, {
                "source_path": str(path),
                "manifest_path": result.manifest_path,
                "checksum": result.checksum,
                "lifecycle": result.lifecycle,
                "index_status": "INDEXED",
                "parser_version": parsed_document.parser_version,
                "chunker_version": chunk_result.get("operational_metadata", {}).get("chunker_version", ""),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_version": EMBEDDING_VERSION,
                "index_version": "v3",
                "chunk_count": result.chunk_count,
                "ingestion_fingerprint": result.ingestion_fingerprint,
                "ingestion_fingerprint_version": fingerprint["fingerprint_version"],
                "ingestion_fingerprint_payload": self._fingerprint_payload_json(fingerprint),
                "metadata_schema_version": METADATA_SCHEMA_VERSION,
                "fast_precheck_fingerprint": result.fast_precheck_fingerprint,
                "fast_precheck_fingerprint_version": "fast_precheck_v1" if result.fast_precheck_fingerprint else "",
                "fast_precheck_payload": self._json_for_catalog(result.fast_precheck_payload),
                "fast_precheck_ingestion_fingerprint": result.ingestion_fingerprint,
                "fast_precheck_content_sha256": result.fast_precheck_content_sha256,
                "fast_precheck_file_size": result.fast_precheck_file_size,
                "fast_precheck_mtime_ns": result.fast_precheck_mtime_ns,
                "last_precheck_at": time.time(),
                "last_validated_at": time.time(),
                "last_successful_status": "INDEXED",
                "vector_count": result.chunk_count,
            })
            if reindex_reason == "CONTENT_CHANGED":
                result.status = IngestionStatus.REINDEXED_CONTENT_CHANGED
            elif reindex_reason in {"INGESTION_FINGERPRINT_CHANGED", "FORCE_REINDEX"}:
                result.status = IngestionStatus.REINDEXED_POLICY_CHANGED
            else:
                result.status = IngestionStatus.INDEXED
            result.indexed = True
            self._apply_vector_stats(result, getattr(vector_service, "last_index_result", {}) or {})
            self._mark_fast_precheck_backfilled(result, "INDEXED_SUCCESS")
            self._log_result(result, f"job_id={job_id} file={path} stage=index status={result.status} vectors={result.chunk_count}")
            self._run_retrieval_smoke(result, metadata, job_id, path)
            return self._finish(result, start)
        except Exception as exc:
            result.status = IngestionStatus.FAILED
            result.reason = str(exc)
            result.messages.append(f"[ERROR] {exc}")
            self._mark_catalog_failure(result, result.reason)
            self._log_result(result, f"job_id={job_id} file={path} stage=failed reason={result.reason}")
            return self._finish(result, start)

    def _apply_metadata(self, result: IngestionResult, metadata: Dict[str, Any]) -> None:
        routing = metadata.get("routing_metadata", {}) or {}
        document = metadata.get("document_metadata", {}) or {}
        result.doc_id = metadata.get("doc_id", "")
        result.lifecycle = metadata.get("lifecycle", "")
        result.domain = routing.get("domain", "")
        result.subdomain = routing.get("subdomain", "")
        result.checksum = document.get("checksum", result.checksum)
        result.document_type = document.get("document_type", result.document_type)

    def _validate_repository_path(self, path: Path) -> str:
        parts = list(path.parts)
        try:
            repo_idx = parts.index("knowledge_repository")
        except ValueError:
            return "FATAL: Path does not contain 'knowledge_repository'"

        if len(parts) < repo_idx + 6:
            return "FATAL: Path convention violation"
        return ""

    def _quarantine_status(self, metadata: Dict[str, Any]) -> str:
        error = metadata.get("error", "")
        if "POSSIBLE_DUPLICATE" in error:
            return IngestionStatus.DUPLICATE
        return IngestionStatus.QUARANTINE

    def _mark_catalog_failure(self, result: IngestionResult, error_message: str) -> None:
        if not result.doc_id:
            return
        self.catalog.upsert_document(result.doc_id, {
            "source_path": result.path,
            "manifest_path": result.manifest_path,
            "checksum": result.checksum,
            "lifecycle": result.lifecycle,
            "index_status": "FAILED",
            "error_message": error_message,
            "failed_stage": "index",
            "failure_reason": error_message,
        })

    def _mark_catalog_pending_retry(
        self,
        result: IngestionResult,
        failed_stage: str,
        category: str,
        reason: str,
        retryable: bool,
    ) -> None:
        if not result.doc_id:
            return
        if result.fast_precheck_fingerprint:
            not_backfilled_reason = result.status or category or failed_stage
            self._log_fast_precheck(result.path, f"status=not_backfilled reason={not_backfilled_reason}")
        now = time.time()
        next_retry_after = now + Config.EMBEDDING_RATE_LIMIT_COOLDOWN_SECONDS if category in {"rate_limited", "quota_exceeded"} else now
        self.catalog.upsert_document(
            result.doc_id,
            {
                "source_path": result.path,
                "manifest_path": result.manifest_path,
                "checksum": result.checksum,
                "lifecycle": result.lifecycle,
                "index_status": result.status,
                "error_message": reason,
                "failed_stage": failed_stage,
                "failure_category": category,
                "failure_reason": reason,
                "retryable": 1 if retryable else 0,
                "attempts": 1,
                "last_attempt_at": now,
                "next_retry_after": next_retry_after,
                "chunks_count": result.chunk_count,
                "vectors_expected": result.chunk_count,
                "parser_type": result.parser_type,
                "embedding_provider": Config.EMBEDDING_PROVIDER,
            },
        )

    def _determine_reindex_reason(
        self,
        existing: Optional[Dict[str, Any]],
        checksum: str,
        ingestion_fingerprint: str,
    ) -> str:
        if Config.KNOWLEDGE_UPDATE_FORCE_REINDEX:
            return "FORCE_REINDEX"
        if not existing or existing.get("index_status") != "INDEXED":
            return "NEW_DOCUMENT"
        if existing.get("checksum") != checksum:
            return "CONTENT_CHANGED"
        if existing.get("ingestion_fingerprint") != ingestion_fingerprint:
            return "INGESTION_FINGERPRINT_CHANGED"
        return "UNCHANGED_ALREADY_INDEXED"

    def _fingerprint_payload_json(self, fingerprint: Dict[str, Any]) -> str:
        return json.dumps(fingerprint.get("payload", {}), sort_keys=True, ensure_ascii=False)

    def _json_for_catalog(self, value: Dict[str, Any]) -> str:
        return json.dumps(value or {}, sort_keys=True, ensure_ascii=False)

    def _store_fast_precheck_success(self, result: IngestionResult, reason: str) -> None:
        if not result.doc_id or not result.fast_precheck_fingerprint:
            self._log_fast_precheck(result.path, "status=not_backfilled reason=MISSING_DOC_ID_OR_FINGERPRINT")
            return
        if not result.ingestion_fingerprint:
            self._log_fast_precheck(result.path, "status=not_backfilled reason=MISSING_INGESTION_FINGERPRINT")
            return
        now = time.time()
        last_successful_status = (
            IngestionStatus.SKIPPED_UNCHANGED
            if reason == "SKIPPED_UNCHANGED_AFTER_PARSE"
            else result.status
        )
        self.catalog.upsert_document(
            result.doc_id,
            {
                "source_path": result.path,
                "checksum": result.checksum,
                "parser_type": result.parser_type,
                "chunk_count": result.chunk_count,
                "fast_precheck_fingerprint": result.fast_precheck_fingerprint,
                "fast_precheck_fingerprint_version": "fast_precheck_v1",
                "fast_precheck_payload": self._json_for_catalog(result.fast_precheck_payload),
                "fast_precheck_ingestion_fingerprint": result.ingestion_fingerprint,
                "fast_precheck_content_sha256": result.fast_precheck_content_sha256,
                "fast_precheck_file_size": result.fast_precheck_file_size,
                "fast_precheck_mtime_ns": result.fast_precheck_mtime_ns,
                "last_successful_status": last_successful_status,
                "last_precheck_at": now,
                "last_validated_at": now,
                "vector_count": result.chunk_count,
            },
        )
        self._mark_fast_precheck_backfilled(result, reason)

    def _mark_fast_precheck_backfilled(self, result: IngestionResult, reason: str) -> None:
        if not result.fast_precheck_fingerprint or result.fast_precheck_backfilled:
            return
        result.fast_precheck_backfilled = True
        self._log_fast_precheck(
            result.path,
            f"status=backfilled reason={reason} fingerprint={result.fast_precheck_fingerprint}",
        )

    def _validation_reason(self, validation: Any) -> str:
        messages = getattr(validation, "messages", []) or []
        errors = [message for message in messages if message.startswith("[ERROR]") or message.startswith("[FATAL]")]
        return "; ".join(errors or messages or ["Validation failed."])

    def _cleanup_replaced_doc(self, old_doc_id: str, new_doc_id: str) -> None:
        try:
            vector_service = self._get_vector_service()
            if hasattr(vector_service, "delete_by_doc_id"):
                vector_service.delete_by_doc_id(old_doc_id)
        except Exception as exc:
            print(f"[KnowledgeUpdate] stage=replace_cleanup status=WARNING old_doc_id={old_doc_id} reason={exc}")
        self.catalog.upsert_document(old_doc_id, {
            "lifecycle": "ARCHIVED",
            "index_status": "REPLACED",
            "error_message": f"Replaced by canonical doc_id {new_doc_id}",
        })

    def _vector_upsert_document(
        self,
        vector_service: Any,
        doc_id: str,
        chunks: List[Dict[str, Any]],
        index_job_id: str,
        ingestion_fingerprint: str,
        parser_type: str,
    ) -> bool:
        try:
            return bool(
                vector_service.upsert_document(
                    doc_id,
                    chunks,
                    index_job_id,
                    ingestion_fingerprint=ingestion_fingerprint,
                    parser_type=parser_type,
                )
            )
        except TypeError:
            return bool(vector_service.upsert_document(doc_id, chunks, index_job_id))

    def _apply_vector_failure(self, result: IngestionResult, index_result: Dict[str, Any]) -> None:
        status = str(index_result.get("status") or "").strip()
        category = str(index_result.get("category") or "unknown_error").strip()
        retryable = bool(index_result.get("retryable", False))
        reason = str(index_result.get("reason") or "vector_upsert_false")
        if status == "FAILED_UPSERT":
            result.status = IngestionStatus.FAILED_UPSERT
            result.retryable = True
        elif status == "PENDING_RETRY" or retryable:
            result.status = IngestionStatus.PENDING_RETRY
            result.retryable = True
        elif status == "FAILED_NON_RETRYABLE":
            result.status = IngestionStatus.FAILED_NON_RETRYABLE
            result.retryable = False
        else:
            result.status = IngestionStatus.FAILED
            result.retryable = False
        result.reason = reason
        result.failure_category = category
        self._apply_vector_stats(result, index_result)
        if result.status == IngestionStatus.PENDING_RETRY:
            self._mark_catalog_pending_retry(result, "embedding", category, reason, result.retryable)
        elif result.status == IngestionStatus.FAILED_UPSERT:
            self._mark_catalog_pending_retry(result, "upsert", category or "upsert_failed", reason, True)
        else:
            self._mark_catalog_pending_retry(result, "embedding", category, reason, False)

    def _apply_vector_stats(self, result: IngestionResult, index_result: Dict[str, Any]) -> None:
        result.embedding_cache_hits = int(index_result.get("cache_hits", 0) or 0)
        result.embedding_cache_misses = int(index_result.get("cache_misses", 0) or 0)
        result.rate_limit_count = int(index_result.get("rate_limit_count", 0) or 0)

    def _run_retrieval_smoke(
        self,
        result: IngestionResult,
        metadata: Dict[str, Any],
        job_id: str,
        path: Path,
    ) -> None:
        smoke = self._get_retrieval_smoke_evaluator().evaluate_document(result.doc_id, metadata)
        result.retrieval_smoke_status = smoke.status
        result.retrieval_smoke_reason = smoke.reason
        result.retrieval_smoke_query = smoke.query
        result.top_source_title = smoke.top_source_title
        result.top_source_author = smoke.top_source_author
        result.top_source_organization = smoke.top_source_organization
        result.top_source_domain = smoke.top_source_domain
        result.top_source_subdomain = smoke.top_source_subdomain
        result.top_source_event_type = smoke.top_source_event_type
        result.top_source_period = smoke.top_source_period
        if smoke.status != RetrievalSmokeStatus.PASS and smoke.reason:
            result.messages.append(f"[WARNING] {smoke.status}: {smoke.reason}")
        self._log_result(
            result,
            f"job_id={job_id} file={path} stage=retrieval_smoke status={smoke.status} "
            f"query={smoke.query!r} reason={smoke.reason}",
        )

    def _get_vector_service(self):
        if self.vector_service is None:
            from src.services.knowledge.vector_service import VectorServiceV3

            self.vector_service = VectorServiceV3()
        return self.vector_service

    def _get_retrieval_smoke_evaluator(self):
        if self.retrieval_smoke_evaluator is not None:
            return self.retrieval_smoke_evaluator

        vector_service = self._get_vector_service()
        if not hasattr(vector_service, "search"):
            self.retrieval_smoke_evaluator = RetrievalSmokeEvaluator(enabled=False)
            return self.retrieval_smoke_evaluator

        from src.services.knowledge.knowledge_service import KnowledgeService

        self.retrieval_smoke_evaluator = RetrievalSmokeEvaluator(
            search_service=KnowledgeService(vector_service=vector_service)
        )
        return self.retrieval_smoke_evaluator

    def _get_fast_precheck_service(self):
        if self.fast_precheck_service is None:
            self.fast_precheck_service = FastPrecheckFingerprintService(
                catalog=self.catalog,
                repository_path=self.repository_path,
            )
        return self.fast_precheck_service

    def _log_fast_precheck(self, file_path: str, message: str) -> None:
        if Config.KNOWLEDGE_UPDATE_LOG_PRECHECK:
            print(f"[FastPrecheck] file={file_path} {message}")

    def _log_retry_mode(self, job_id: str, candidates: int) -> None:
        print(f"[KnowledgeUpdate] job_id={job_id} mode=retry_failed_only candidates={candidates}")

    def _log_report(self, report: KnowledgeUpdateReport, message: str) -> None:
        line = f"[KnowledgeUpdate] {message}"
        report.logs.append(line)
        print(line)

    def _log_result(self, result: IngestionResult, message: str) -> None:
        line = f"[KnowledgeUpdate] {message}"
        result.logs.append(line)
        print(line)

    def _finish(self, result: IngestionResult, start: float) -> IngestionResult:
        result.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return result
