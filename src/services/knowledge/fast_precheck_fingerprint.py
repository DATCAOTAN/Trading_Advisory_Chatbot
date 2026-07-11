import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import Config
from src.services.knowledge.chunk_policy_resolver import (
    DOCUMENT_TYPE_DEFAULT_POLICY,
    DOMAIN_DEFAULT_POLICY,
    EXACT_POLICY_BY_DOMAIN_SUBDOMAIN,
    KNOWLEDGE_TYPE_DEFAULT_POLICY,
    POLICY_BOUNDS,
    V3_CHUNK_POLICIES,
)
from src.services.knowledge.ingestion_fingerprint import EMBEDDING_DIMENSION, EMBEDDING_MODEL, METADATA_SCHEMA_VERSION


FAST_PRECHECK_VERSION = "fast_precheck_v1"
VECTOR_PAYLOAD_SCHEMA_VERSION = "v3_vector_payload_v1"
INGESTION_SCHEMA_VERSION = "knowledge_v3_ingestion_v1"


@dataclass
class ContentHashResult:
    content_sha256: str
    file_size: int
    mtime_ns: int
    cache_status: str
    latency_ms: float


@dataclass
class FastPrecheckResult:
    fingerprint: str
    payload: Dict[str, Any]
    content_hash: ContentHashResult


@dataclass
class FastPrecheckDecision:
    should_skip: bool
    reason: str


class FastPrecheckFingerprintService:
    """Cheap pre-parse fingerprint for Knowledge V3 update skips."""

    def __init__(self, catalog: Optional[Any] = None, repository_path: Optional[str] = None):
        self.catalog = catalog
        self.repository_path = Path(repository_path or Config.DATA_DIR / "knowledge_repository")

    def compute_content_hash(self, file_path: str) -> ContentHashResult:
        path = Path(file_path)
        stat = path.stat()
        file_size = int(stat.st_size)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        started = time.perf_counter()

        cached = None
        if Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED and self.catalog is not None:
            cached = self.catalog.get_file_hash_cache(str(path)) if hasattr(self.catalog, "get_file_hash_cache") else None
        if (
            cached
            and int(cached.get("file_size") or -1) == file_size
            and int(cached.get("mtime_ns") or -1) == mtime_ns
            and cached.get("content_sha256")
        ):
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            print(
                f"[FastPrecheck] file={path} content_hash_status=cache_hit "
                f"size={file_size} mtime_ns={mtime_ns}"
            )
            return ContentHashResult(str(cached["content_sha256"]), file_size, mtime_ns, "cache_hit", latency_ms)

        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        content_sha256 = digest.hexdigest()
        if Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED and self.catalog is not None:
            if hasattr(self.catalog, "upsert_file_hash_cache"):
                self.catalog.upsert_file_hash_cache(str(path), file_size, mtime_ns, content_sha256)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        print(
            f"[FastPrecheck] file={path} content_hash_status=computed "
            f"size={file_size} latency_ms={latency_ms}"
        )
        return ContentHashResult(content_sha256, file_size, mtime_ns, "computed", latency_ms)

    def build(
        self,
        file_path: str,
        manifest_data: Dict[str, Any],
        metadata: Dict[str, Any],
        content_hash: Optional[ContentHashResult] = None,
    ) -> FastPrecheckResult:
        path = Path(file_path)
        content = content_hash or self.compute_content_hash(file_path)
        payload = self._payload(path, manifest_data or {}, metadata or {}, content)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        return FastPrecheckResult(fingerprint=fingerprint, payload=payload, content_hash=content)

    def decide(
        self,
        fast_fingerprint: str,
        previous: Optional[Dict[str, Any]],
        *,
        retry_failed_only: bool = False,
    ) -> FastPrecheckDecision:
        if not Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED:
            return FastPrecheckDecision(False, "FAST_PRECHECK_DISABLED")
        if Config.KNOWLEDGE_UPDATE_FORCE_REPARSE:
            return FastPrecheckDecision(False, "FORCE_REPARSE")
        if Config.KNOWLEDGE_UPDATE_FORCE_REINDEX:
            return FastPrecheckDecision(False, "FORCE_REINDEX")
        if retry_failed_only:
            return FastPrecheckDecision(False, "RETRY_FAILED_ONLY")
        if not previous:
            return FastPrecheckDecision(False, "NO_PREVIOUS_SUCCESS_STATE")

        status = str(previous.get("index_status") or "")
        retryable = bool(previous.get("retryable"))
        failure_category = str(previous.get("failure_category") or "")
        if status == "PENDING_RETRY":
            return FastPrecheckDecision(False, "PENDING_RETRY")
        if status == "FAILED_UPSERT" and retryable:
            return FastPrecheckDecision(False, "FAILED_UPSERT_RETRYABLE")
        if status == "FAILED_NON_RETRYABLE":
            return FastPrecheckDecision(False, "FAILED_NON_RETRYABLE")
        if failure_category and failure_category != "retrieval_smoke" and status != "INDEXED":
            return FastPrecheckDecision(False, "PREVIOUS_FAILURE_STATE")
        if status not in {"INDEXED", "SKIPPED_ALREADY_INDEXED", "SKIPPED_UNCHANGED"}:
            return FastPrecheckDecision(False, "NO_PREVIOUS_SUCCESS_STATE")

        previous_fast = str(previous.get("fast_precheck_fingerprint") or "")
        if not previous_fast:
            return FastPrecheckDecision(False, "NO_PREVIOUS_FAST_FINGERPRINT")
        if previous_fast == fast_fingerprint:
            paired_ingestion = str(previous.get("fast_precheck_ingestion_fingerprint") or "")
            current_ingestion = str(previous.get("ingestion_fingerprint") or "")
            if paired_ingestion and current_ingestion and paired_ingestion != current_ingestion:
                return FastPrecheckDecision(False, "INGESTION_FINGERPRINT_MISMATCH")
            return FastPrecheckDecision(True, "FAST_FINGERPRINT_UNCHANGED")
        return FastPrecheckDecision(False, "FAST_FINGERPRINT_CHANGED")

    def _payload(
        self,
        path: Path,
        manifest_data: Dict[str, Any],
        metadata: Dict[str, Any],
        content: ContentHashResult,
    ) -> Dict[str, Any]:
        routing = metadata.get("routing_metadata", {}) or {}
        document = metadata.get("document_metadata", {}) or {}
        doc_id = metadata.get("doc_id") or document.get("doc_id") or ""
        owner = (
            manifest_data.get("author_slug")
            or manifest_data.get("organization_slug")
            or document.get("author_slug")
            or document.get("organization_slug")
            or ""
        )
        payload = {
            "fast_precheck_version": FAST_PRECHECK_VERSION,
            "repository_relative_file_path": self._relative_path(path),
            "document_type": document.get("document_type") or manifest_data.get("document_type") or path.suffix.lower().lstrip("."),
            "file_extension": path.suffix.lower(),
            "file_size": content.file_size,
            "content_sha256": content.content_sha256,
            "manifest_hash": self._stable_hash(self._manifest_projection(manifest_data)),
            "metadata_hash": self._stable_hash(self._metadata_projection(metadata)),
            "doc_id": doc_id,
            "domain": routing.get("domain") or manifest_data.get("domain", ""),
            "subdomain": routing.get("subdomain") or manifest_data.get("subdomain", ""),
            "owner": owner,
            "author": document.get("author") or manifest_data.get("author", ""),
            "organization": document.get("organization") or manifest_data.get("organization", ""),
            "lifecycle": metadata.get("lifecycle") or manifest_data.get("lifecycle", ""),
            "source_tier": routing.get("source_tier") or manifest_data.get("source_tier", ""),
            "language": routing.get("language") or manifest_data.get("language", ""),
            "parser_config_version": "adaptive_pdf_parse_config_v1",
            "pdf_parser_mode": Config.PDF_PARSER_MODE,
            "mineru_backend": Config.MINERU_BACKEND,
            "mineru_method": Config.MINERU_METHOD,
            "mineru_parse_books": Config.MINERU_PARSE_BOOKS,
            "mineru_selective_book_pages_enabled": Config.MINERU_SELECTIVE_BOOK_PAGES_ENABLED,
            "mineru_selective_max_pages_per_doc": Config.MINERU_SELECTIVE_MAX_PAGES_PER_DOC,
            "mineru_selective_max_ranges_per_doc": Config.MINERU_SELECTIVE_MAX_RANGES_PER_DOC,
            "mineru_full_max_pages_soft_limit": Config.MINERU_FULL_MAX_PAGES_SOFT_LIMIT,
            "mineru_full_complex_page_ratio_threshold": Config.MINERU_FULL_COMPLEX_PAGE_RATIO_THRESHOLD,
            "mineru_selective_low_text_chars": Config.MINERU_SELECTIVE_LOW_TEXT_CHARS,
            "mineru_selective_table_like_threshold": Config.MINERU_SELECTIVE_TABLE_LIKE_THRESHOLD,
            "mineru_selective_image_area_ratio": Config.MINERU_SELECTIVE_IMAGE_AREA_RATIO,
            "parser_output_schema_version": Config.PARSER_OUTPUT_SCHEMA_VERSION,
            "chunk_policy_version": "chunk_policy_v1",
            "chunk_policy_config_hash": self.chunk_policy_config_hash(),
            "metadata_schema_version": METADATA_SCHEMA_VERSION,
            "registry_manifest_schema_version": "registry_manifest_v1",
            "registry_hash": self.registry_hash(),
            "embedding_provider": Config.EMBEDDING_PROVIDER,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_input_type": "search_document",
            "embedding_dimension": EMBEDDING_DIMENSION,
            "vector_payload_schema_version": VECTOR_PAYLOAD_SCHEMA_VERSION,
            "ingestion_schema_version": INGESTION_SCHEMA_VERSION,
        }
        return payload

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repository_path.resolve())).replace("\\", "/")
        except Exception:
            return str(path).replace("\\", "/")

    @staticmethod
    def _stable_hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _manifest_projection(data: Dict[str, Any]) -> Dict[str, Any]:
        keys = [
            "title",
            "title_slug",
            "author",
            "author_slug",
            "organization",
            "organization_slug",
            "knowledge_type",
            "domain",
            "subdomain",
            "document_type",
            "version",
            "lifecycle",
            "language",
            "source_tier",
            "publisher",
            "edition",
            "publish_year",
            "country",
            "event_type",
            "published_date",
            "period",
            "release_time",
            "revision",
            "asset_focus",
            "tags",
            "chunk_policy",
            "chunking_override",
        ]
        return {key: data.get(key) for key in keys if key in data}

    @staticmethod
    def _metadata_projection(metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "doc_id": metadata.get("doc_id", ""),
            "lifecycle": metadata.get("lifecycle", ""),
            "routing_metadata": metadata.get("routing_metadata", {}) or {},
            "document_metadata": {
                key: value
                for key, value in (metadata.get("document_metadata", {}) or {}).items()
                if key
                in {
                    "title",
                    "author",
                    "organization",
                    "document_type",
                    "checksum",
                    "event_type",
                    "period",
                    "published_date",
                    "source_tier",
                    "language",
                    "country",
                    "asset_focus",
                }
            },
            "chunking_override": metadata.get("chunking_override") or metadata.get("chunk_policy") or {},
        }

    @staticmethod
    def chunk_policy_config_hash() -> str:
        value = {
            "policies": {key: policy.__dict__ for key, policy in V3_CHUNK_POLICIES.items()},
            "exact": {"/".join(key): value for key, value in EXACT_POLICY_BY_DOMAIN_SUBDOMAIN.items()},
            "domain_defaults": DOMAIN_DEFAULT_POLICY,
            "knowledge_type_defaults": KNOWLEDGE_TYPE_DEFAULT_POLICY,
            "document_type_defaults": {"/".join(key): value for key, value in DOCUMENT_TYPE_DEFAULT_POLICY.items()},
            "bounds": POLICY_BOUNDS,
        }
        return FastPrecheckFingerprintService._stable_hash(value)

    @staticmethod
    def registry_hash() -> str:
        metadata_dir = Config.BASE_DIR / "src" / "metadata"
        if not metadata_dir.exists():
            return ""
        digest = hashlib.sha256()
        for path in sorted(metadata_dir.glob("*.yaml")):
            digest.update(path.name.encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except Exception:
                pass
        return digest.hexdigest()
