import argparse
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


BLOCKED_CHUNK_STATUSES = {"EMPTY_DOCUMENT", "NEEDS_OCR", "FAILED"}
SUPPORTED_EXTENSIONS = {".pdf", ".epub"}


@dataclass
class IngestResult:
    path: str
    action: str
    status: str
    doc_id: str = ""
    lifecycle: str = ""
    domain: str = ""
    subdomain: str = ""
    chunk_count: int = 0
    ocr_status: str = ""
    messages: List[str] = field(default_factory=list)
    indexed: bool = False


@dataclass
class RepoSummary:
    discovered: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    needs_ocr: int = 0
    quarantined: int = 0
    results: List[IngestResult] = field(default_factory=list)


class KnowledgePlatformIngestor:
    def __init__(
        self,
        resolver: Optional[Any] = None,
        validator: Optional[Any] = None,
        chunk_builder: Optional[Any] = None,
        catalog: Optional[Any] = None,
        vector_service: Optional[Any] = None,
    ):
        self.catalog = catalog
        if self.catalog is None:
            from src.services.knowledge.catalog_manager import KnowledgeCatalog

            self.catalog = KnowledgeCatalog()

        self.resolver = resolver
        if self.resolver is None:
            from src.services.knowledge.metadata_resolver import MetadataResolver
            from src.services.knowledge.registry_loader import RegistryLoader

            self.resolver = MetadataResolver.__new__(MetadataResolver)
            self.resolver.registry = RegistryLoader()
            self.resolver.catalog = self.catalog

        self.validator = validator
        if self.validator is None:
            from src.services.knowledge.validator import Validator

            self.validator = Validator()

        self.chunk_builder = chunk_builder
        if self.chunk_builder is None:
            from src.services.knowledge.chunk_builder import ChunkBuilder

            self.chunk_builder = ChunkBuilder()

        self.vector_service = vector_service

    def dry_run(self, file_path: str) -> IngestResult:
        result, metadata, validation, chunk_result = self._prepare(file_path, action="dry-run")
        self._print_result(result, validation)
        return result

    def ingest_file(self, file_path: str) -> IngestResult:
        result, metadata, validation, chunk_result = self._prepare(file_path, action="ingest-file")

        if result.status != "READY":
            self._print_result(result, validation)
            return result

        if chunk_result["status"] == "PARTIAL_TEXT":
            result.messages.append("[WARNING] PARTIAL_TEXT detected; indexing with caution.")

        doc_id = result.doc_id
        job_id = f"kp_ingest_{uuid.uuid4().hex}"

        if not self.catalog.acquire_index_lock(doc_id, job_id, worker_id="kp_ingest"):
            result.status = "FAILED"
            result.messages.append(f"[ERROR] Could not acquire index lock for doc_id={doc_id}")
            self.catalog.upsert_document(doc_id, {"index_status": "FAILED", "error_message": "Lock acquisition failed"})
            self._print_result(result, validation)
            return result

        try:
            vector_service = self._get_vector_service()
            ok = vector_service.upsert_document(doc_id, chunk_result["chunks"], job_id)
            if not ok:
                result.status = "FAILED"
                result.messages.append("[ERROR] VectorServiceV3.upsert_document returned False.")
                self.catalog.release_index_lock(doc_id, job_id, "FAILED", "Vector upsert returned False.")
                self._print_result(result, validation)
                return result

            result.status = "INDEXED"
            result.indexed = True
            self._print_result(result, validation)
            return result
        except Exception as exc:
            result.status = "FAILED"
            result.messages.append(f"[ERROR] {exc}")
            self.catalog.release_index_lock(doc_id, job_id, "FAILED", str(exc))
            self._print_result(result, validation)
            return result

    def ingest_repo(self, repo_path: str) -> RepoSummary:
        root = Path(repo_path)
        files = sorted(
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ) if root.exists() else []
        summary = RepoSummary(discovered=len(files))

        for file_path in files:
            result = self.ingest_file(str(file_path))
            summary.results.append(result)
            if result.indexed:
                summary.indexed += 1
            elif result.status == "QUARANTINE":
                summary.quarantined += 1
                summary.skipped += 1
            elif result.status == "NEEDS_OCR":
                summary.needs_ocr += 1
                summary.skipped += 1
            elif result.status == "FAILED":
                summary.failed += 1
            else:
                summary.skipped += 1

        self._print_summary(summary)
        return summary

    def _prepare(self, pdf_path: str, action: str):
        should_mutate_catalog = action != "dry-run"
        metadata = self.resolver.resolve(pdf_path)
        result = self._result_from_metadata(pdf_path, action, metadata)

        if metadata.get("lifecycle") == "QUARANTINE":
            result.status = "QUARANTINE"
            result.messages.append(metadata.get("error", "QUARANTINE"))
            return result, metadata, None, None

        validation = self.validator.validate(pdf_path, metadata)
        result.messages.extend(getattr(validation, "messages", []))
        if not validation.is_valid or validation.level in {"ERROR", "FATAL"}:
            result.status = "FAILED"
            if should_mutate_catalog:
                self._mark_catalog_failure(result, "Validation failed.")
            return result, metadata, validation, None

        if metadata.get("lifecycle") == "QUARANTINE":
            result.status = "QUARANTINE"
            result.messages.append("[FATAL] Metadata lifecycle is QUARANTINE.")
            if should_mutate_catalog:
                self._mark_catalog_failure(result, "Lifecycle QUARANTINE.")
            return result, metadata, validation, None

        chunk_result = self.chunk_builder.build_chunks(pdf_path, metadata)
        result.ocr_status = chunk_result.get("status", "")
        result.chunk_count = len(chunk_result.get("chunks", []))

        if result.ocr_status in BLOCKED_CHUNK_STATUSES:
            result.status = result.ocr_status
            if should_mutate_catalog:
                if result.ocr_status == "NEEDS_OCR":
                    self._mark_catalog_failure(result, "Document needs OCR.")
                elif result.ocr_status == "EMPTY_DOCUMENT":
                    self._mark_catalog_failure(result, "Document is empty.")
                else:
                    self._mark_catalog_failure(result, chunk_result.get("error", "Chunking failed."))
            return result, metadata, validation, chunk_result

        if result.ocr_status == "PARTIAL_TEXT":
            result.status = "READY"
            result.messages.append("[WARNING] PARTIAL_TEXT detected.")
            return result, metadata, validation, chunk_result

        result.status = "READY"
        return result, metadata, validation, chunk_result

    def _result_from_metadata(self, pdf_path: str, action: str, metadata: Dict[str, Any]) -> IngestResult:
        routing = metadata.get("routing_metadata", {})
        return IngestResult(
            path=pdf_path,
            action=action,
            status="READY",
            doc_id=metadata.get("doc_id", ""),
            lifecycle=metadata.get("lifecycle", ""),
            domain=routing.get("domain", ""),
            subdomain=routing.get("subdomain", ""),
        )

    def _mark_catalog_failure(self, result: IngestResult, error_message: str) -> None:
        if not result.doc_id:
            return
        self.catalog.upsert_document(result.doc_id, {
            "index_status": "FAILED",
            "error_message": error_message,
        })

    def _get_vector_service(self):
        if self.vector_service is None:
            from src.services.knowledge.vector_service import VectorServiceV3

            self.vector_service = VectorServiceV3()
        return self.vector_service

    def _print_result(self, result: IngestResult, validation: Optional[Any]) -> None:
        print(f"\n[{result.action}] {result.path}")
        print(f"status: {result.status}")
        print(f"doc_id: {result.doc_id}")
        print(f"lifecycle: {result.lifecycle}")
        print(f"domain/subdomain: {result.domain}/{result.subdomain}")
        print(f"chunk_count: {result.chunk_count}")
        print(f"ocr_status: {result.ocr_status}")
        if validation is not None:
            print(f"validation_level: {validation.level}")
        for message in result.messages:
            print(message)

    def _print_summary(self, summary: RepoSummary) -> None:
        print("\n[ingest-repo summary]")
        print(f"discovered: {summary.discovered}")
        print(f"indexed: {summary.indexed}")
        print(f"skipped: {summary.skipped}")
        print(f"failed: {summary.failed}")
        print(f"needs_ocr: {summary.needs_ocr}")
        print(f"quarantined: {summary.quarantined}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Knowledge Platform V3 ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_file = subparsers.add_parser("ingest-file", help="Ingest one PDF/EPUB into Knowledge Platform V3")
    ingest_file.add_argument("pdf_path")

    ingest_repo = subparsers.add_parser("ingest-repo", help="Recursively ingest PDFs/EPUBs under a repository path")
    ingest_repo.add_argument("repo_path")

    dry_run = subparsers.add_parser("dry-run", help="Validate and chunk one PDF/EPUB without indexing")
    dry_run.add_argument("pdf_path")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    ingestor = KnowledgePlatformIngestor()

    if args.command == "dry-run":
        result = ingestor.dry_run(args.pdf_path)
        return 0 if result.status in {"READY", "PARTIAL_TEXT"} else 1
    if args.command == "ingest-file":
        result = ingestor.ingest_file(args.pdf_path)
        return 0 if result.indexed else 1
    if args.command == "ingest-repo":
        summary = ingestor.ingest_repo(args.repo_path)
        return 0 if summary.failed == 0 else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
