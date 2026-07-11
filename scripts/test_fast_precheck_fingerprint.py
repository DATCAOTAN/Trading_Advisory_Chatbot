import importlib.util
import os
import sys
import time
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if importlib.util.find_spec("dotenv") is None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if importlib.util.find_spec("streamlit") is None:
    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    sys.modules["streamlit"] = streamlit_stub

if importlib.util.find_spec("fitz") is None:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "stub"
    sys.modules["fitz"] = fitz_stub


from src.config import Config
from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.document_parser import ParsedDocument, ParsedSection
from src.services.knowledge.fast_precheck_fingerprint import FastPrecheckFingerprintService
from src.services.knowledge.update_service import IngestionStatus, KnowledgeUpdateService


class CountingParserRegistry:
    supported_extensions = {".pdf", ".epub"}

    def __init__(self):
        self.calls = []

    def parse(self, file_path: str) -> ParsedDocument:
        self.calls.append(file_path)
        path = Path(file_path)
        text = (f"{path.stem} fast precheck test content. " * 120).strip()
        section = ParsedSection(text=text, page=1, section="Test")
        return ParsedDocument(
            file_path=file_path,
            parser_type="epub:fake" if path.suffix.lower() == ".epub" else "pdf:fake",
            parser_version="fake",
            extraction_status="CHUNKED",
            extraction_quality=1.0,
            sections=[section],
            metadata_hints={"total_pages": 1},
        )


class FakeVectorService:
    def __init__(self, catalog):
        self.catalog = catalog
        self.calls = []
        self.deleted_doc_ids = []
        self.last_index_result = {"status": "INDEXED", "vectors": 0}

    def upsert_document(self, doc_id, chunks, job_id, **kwargs):
        self.calls.append({"doc_id": doc_id, "chunks": chunks, "job_id": job_id, "kwargs": kwargs})
        self.last_index_result = {
            "status": "INDEXED",
            "vectors": len(chunks),
            "cache_hits": 0,
            "cache_misses": len(chunks),
            "rate_limit_count": 0,
        }
        self.catalog.release_index_lock(doc_id, job_id, "INDEXED")
        return True

    def delete_by_doc_id(self, doc_id, collection_name="knowledge_current"):
        self.deleted_doc_ids.append(doc_id)


class FailingVectorService(FakeVectorService):
    def __init__(self, catalog, status, category, reason, retryable=True):
        super().__init__(catalog)
        self.status = status
        self.category = category
        self.reason = reason
        self.retryable = retryable

    def upsert_document(self, doc_id, chunks, job_id, **kwargs):
        self.calls.append({"doc_id": doc_id, "chunks": chunks, "job_id": job_id, "kwargs": kwargs})
        self.last_index_result = {
            "status": self.status,
            "category": self.category,
            "reason": self.reason,
            "retryable": self.retryable,
            "vectors": 0,
        }
        return False


class FastPrecheckTests(unittest.TestCase):
    def setUp(self):
        self._old_values = {
            name: getattr(Config, name)
            for name in [
                "KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED",
                "KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED",
                "KNOWLEDGE_UPDATE_FORCE_REPARSE",
                "KNOWLEDGE_UPDATE_FORCE_REINDEX",
                "KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY",
                "MINERU_SELECTIVE_MAX_PAGES_PER_DOC",
            ]
        }
        Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED = True
        Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED = True
        Config.KNOWLEDGE_UPDATE_FORCE_REPARSE = False
        Config.KNOWLEDGE_UPDATE_FORCE_REINDEX = False
        Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY = False

    def tearDown(self):
        for name, value in self._old_values.items():
            setattr(Config, name, value)

    def make_service(self, tmpdir):
        root = Path(tmpdir) / "data" / "knowledge_repository"
        catalog = KnowledgeCatalog(str(Path(tmpdir) / "catalog.sqlite"))
        parser = CountingParserRegistry()
        vector = FakeVectorService(catalog)
        service = KnowledgeUpdateService(
            repository_path=str(root),
            parser_registry=parser,
            catalog=catalog,
            vector_service=vector,
            retrieval_smoke_evaluator=None,
        )
        return root, service, parser, vector

    def write_doc(self, root: Path, relative_path: str, content: bytes = b"fast precheck document"):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_unchanged_indexed_pdf_skips_before_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, vector = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/unchanged.pdf")

            first = service.update_file(str(pdf))
            second = service.update_file(str(pdf))

            self.assertEqual(first.status, IngestionStatus.INDEXED)
            self.assertEqual(second.status, IngestionStatus.SKIPPED_ALREADY_INDEXED)
            self.assertTrue(second.precheck_skipped)
            self.assertEqual(second.reason, "FAST_FINGERPRINT_UNCHANGED")
            self.assertEqual(len(parser.calls), 1)
            self.assertEqual(len(vector.calls), 1)

    def test_unchanged_indexed_epub_skips_before_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            epub = self.write_doc(root, "book/psychology/trading_discipline/mark_douglas/book.epub")

            service.update_file(str(epub))
            result = service.update_file(str(epub))

            self.assertTrue(result.precheck_skipped)
            self.assertEqual(len(parser.calls), 1)

    def test_file_content_changed_continues_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/content_changed.pdf", b"one")
            service.update_file(str(pdf))
            time.sleep(0.01)
            pdf.write_bytes(b"two changed content")
            os.utime(pdf, None)

            result = service.update_file(str(pdf))

            self.assertFalse(result.precheck_skipped)
            self.assertEqual(result.precheck_reason, "FAST_FINGERPRINT_CHANGED")
            self.assertEqual(len(parser.calls), 2)

    def test_file_size_changed_recomputes_content_hash(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/size_changed.pdf", b"one")
            precheck = service._get_fast_precheck_service()
            first = precheck.compute_content_hash(str(pdf))
            time.sleep(0.01)
            pdf.write_bytes(b"one plus more")
            os.utime(pdf, None)
            second = precheck.compute_content_hash(str(pdf))

            self.assertEqual(first.cache_status, "computed")
            self.assertEqual(second.cache_status, "computed")
            self.assertNotEqual(first.content_sha256, second.content_sha256)

    def test_hash_cache_invalidates_when_mtime_changes_with_same_size(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/same_size_changed.pdf", b"one")
            precheck = service._get_fast_precheck_service()
            first = precheck.compute_content_hash(str(pdf))
            pdf.write_bytes(b"two")
            new_ns = first.mtime_ns + 1_000_000_000
            os.utime(pdf, ns=(new_ns, new_ns))
            second = precheck.compute_content_hash(str(pdf))

            self.assertEqual(first.file_size, second.file_size)
            self.assertEqual(second.cache_status, "computed")
            self.assertNotEqual(first.content_sha256, second.content_sha256)

    def test_manifest_metadata_changed_continues_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/manifest_changed.pdf")
            service.update_file(str(pdf))
            manifest = Path(f"{pdf.with_suffix('')}.manifest.yaml")
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["title"] = "Changed Manifest Title"
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            result = service.update_file(str(pdf))

            self.assertFalse(result.precheck_skipped)
            self.assertEqual(result.precheck_reason, "FAST_FINGERPRINT_CHANGED")
            self.assertEqual(len(parser.calls), 2)

    def test_parser_config_changed_continues_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/config_changed.pdf")
            service.update_file(str(pdf))
            Config.MINERU_SELECTIVE_MAX_PAGES_PER_DOC += 1

            result = service.update_file(str(pdf))

            self.assertFalse(result.precheck_skipped)
            self.assertEqual(result.precheck_reason, "FAST_FINGERPRINT_CHANGED")
            self.assertEqual(len(parser.calls), 2)

    def test_embedding_model_change_triggers_continue_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/fingerprint_fields.pdf")
            service.update_file(str(pdf))
            document = service.catalog.get_document("book_fingerprint_fields_owner_v1")
            previous = document["fast_precheck_fingerprint"]

            import src.services.knowledge.fast_precheck_fingerprint as fp_module

            old_model = fp_module.EMBEDDING_MODEL
            try:
                fp_module.EMBEDDING_MODEL = "changed-model"
                result = service.update_file(str(pdf))
            finally:
                fp_module.EMBEDDING_MODEL = old_model

            self.assertNotEqual(result.fast_precheck_fingerprint, previous)
            self.assertEqual(result.precheck_reason, "FAST_FINGERPRINT_CHANGED")

    def test_chunk_policy_config_change_triggers_continue_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/chunk_policy_fields.pdf")
            service.update_file(str(pdf))
            document = service.catalog.get_document("book_chunk_policy_fields_owner_v1")
            previous = document["fast_precheck_fingerprint"]

            import src.services.knowledge.fast_precheck_fingerprint as fp_module
            from src.services.knowledge.chunk_policy_resolver import ChunkPolicy

            old_policy = fp_module.V3_CHUNK_POLICIES["global_default"]
            try:
                fp_module.V3_CHUNK_POLICIES["global_default"] = ChunkPolicy(
                    policy_id="global_default",
                    parent_size=old_policy.parent_size + 4,
                    parent_overlap=old_policy.parent_overlap,
                    child_size=old_policy.child_size,
                    child_overlap=old_policy.child_overlap,
                )
                result = service.update_file(str(pdf))
            finally:
                fp_module.V3_CHUNK_POLICIES["global_default"] = old_policy

            self.assertNotEqual(result.fast_precheck_fingerprint, previous)
            self.assertEqual(result.precheck_reason, "FAST_FINGERPRINT_CHANGED")

    def test_ingestion_fingerprint_mismatch_bypasses_precheck_skip(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/ingestion_mismatch.pdf")
            first = service.update_file(str(pdf))
            service.catalog.upsert_document(first.doc_id, {"ingestion_fingerprint": "old-policy-fingerprint"})

            result = service.update_file(str(pdf))

            self.assertFalse(result.precheck_skipped)
            self.assertEqual(result.precheck_reason, "INGESTION_FINGERPRINT_MISMATCH")
            self.assertEqual(result.status, IngestionStatus.REINDEXED_POLICY_CHANGED)
            self.assertEqual(len(parser.calls), 2)

    def test_no_previous_success_state_continues_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/new_doc.pdf")

            result = service.update_file(str(pdf))

            self.assertEqual(result.precheck_reason, "NO_PREVIOUS_SUCCESS_STATE")
            self.assertEqual(len(parser.calls), 1)

    def test_pending_retry_triggers_continue_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/pending_retry.pdf")
            first = service.update_file(str(pdf))
            service.catalog.upsert_document(
                first.doc_id,
                {"index_status": "PENDING_RETRY", "retryable": 1, "failure_category": "rate_limited"},
            )

            result = service.update_file(str(pdf))

            self.assertFalse(result.precheck_skipped)
            self.assertEqual(result.precheck_reason, "PENDING_RETRY")
            self.assertEqual(len(parser.calls), 2)

    def test_retrieval_smoke_only_failure_can_skip_when_index_is_valid(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/smoke_only.pdf")
            first = service.update_file(str(pdf))
            service.catalog.upsert_document(
                first.doc_id,
                {"index_status": "INDEXED", "retryable": 1, "failure_category": "retrieval_smoke"},
            )

            result = service.update_file(str(pdf))

            self.assertTrue(result.precheck_skipped)
            self.assertEqual(len(parser.calls), 1)

    def test_failed_embedding_does_not_backfill_valid_fast_precheck(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            service.vector_service = FailingVectorService(
                service.catalog,
                status="PENDING_RETRY",
                category="rate_limited",
                reason="embedding rate limited",
                retryable=True,
            )
            pdf = self.write_doc(root, "book/technical/indicators/owner/rate_limited.pdf")

            result = service.update_file(str(pdf))
            document = service.catalog.get_document(result.doc_id)

            self.assertEqual(result.status, IngestionStatus.PENDING_RETRY)
            self.assertFalse(result.fast_precheck_backfilled)
            self.assertFalse(document.get("fast_precheck_fingerprint"))

    def test_failed_qdrant_upsert_does_not_backfill_valid_fast_precheck(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            service.vector_service = FailingVectorService(
                service.catalog,
                status="FAILED_UPSERT",
                category="upsert_failed",
                reason="vector_upsert_false",
                retryable=True,
            )
            pdf = self.write_doc(root, "book/technical/indicators/owner/upsert_failed.pdf")

            result = service.update_file(str(pdf))
            document = service.catalog.get_document(result.doc_id)

            self.assertEqual(result.status, IngestionStatus.FAILED_UPSERT)
            self.assertFalse(result.fast_precheck_backfilled)
            self.assertFalse(document.get("fast_precheck_fingerprint"))

    def test_force_reparse_and_force_reindex_bypass_precheck(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/force.pdf")
            service.update_file(str(pdf))
            Config.KNOWLEDGE_UPDATE_FORCE_REPARSE = True
            reparse = service.update_file(str(pdf))
            Config.KNOWLEDGE_UPDATE_FORCE_REPARSE = False
            Config.KNOWLEDGE_UPDATE_FORCE_REINDEX = True
            reindex = service.update_file(str(pdf))

            self.assertEqual(reparse.precheck_reason, "FORCE_REPARSE")
            self.assertEqual(reindex.precheck_reason, "FORCE_REINDEX")
            self.assertEqual(reindex.status, IngestionStatus.REINDEXED_POLICY_CHANGED)
            self.assertEqual(len(parser.calls), 3)

    def test_hash_cache_hit_avoids_rehashing(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/cache_hit.pdf")
            precheck = service._get_fast_precheck_service()
            first = precheck.compute_content_hash(str(pdf))
            second = precheck.compute_content_hash(str(pdf))

            self.assertEqual(first.cache_status, "computed")
            self.assertEqual(second.cache_status, "cache_hit")

    def test_fast_precheck_summary_counts(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _, _ = self.make_service(tmpdir)
            self.write_doc(root, "book/technical/indicators/owner/one.pdf", b"one")
            self.write_doc(root, "book/technical/indicators/owner/two.pdf", b"two")
            service.update_repository()

            report = service.update_repository()

            self.assertEqual(report.discovered, 2)
            self.assertEqual(report.precheck_skipped, 2)
            self.assertEqual(report.parsed, 0)
            self.assertEqual(report.skipped_after_parse, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
