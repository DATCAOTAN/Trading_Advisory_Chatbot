import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from scripts.kp_ingest import KnowledgePlatformIngestor
from src.services.knowledge.catalog_manager import KnowledgeCatalog


class TrackingCatalog:
    def __init__(self, db_path):
        self.inner = KnowledgeCatalog(str(db_path))
        self.locks = []
        self.releases = []
        self.upserts = []

    def acquire_index_lock(self, doc_id, job_id, worker_id="worker_1"):
        self.locks.append((doc_id, job_id, worker_id))
        return self.inner.acquire_index_lock(doc_id, job_id, worker_id)

    def release_index_lock(self, doc_id, job_id, status, error_msg=""):
        self.releases.append((doc_id, job_id, status, error_msg))
        return self.inner.release_index_lock(doc_id, job_id, status, error_msg)

    def upsert_document(self, doc_id, data):
        self.upserts.append((doc_id, dict(data)))
        return self.inner.upsert_document(doc_id, data)

    def get_document(self, doc_id):
        return self.inner.get_document(doc_id)


class FakeResolver:
    def resolve(self, file_path):
        stem = Path(file_path).stem
        if stem == "missing_manifest":
            return {"lifecycle": "QUARANTINE", "error": "FATAL: Missing .manifest.yaml"}
        if stem == "invalid_path":
            return {"lifecycle": "QUARANTINE", "error": "FATAL: Path convention violation"}
        if stem == "duplicate":
            return {"lifecycle": "QUARANTINE", "error": "POSSIBLE_DUPLICATE: checksum matches"}

        doc_id = f"doc_{stem}"
        return {
            "doc_id": doc_id,
            "lifecycle": "ACTIVE",
            "routing_metadata": {
                "domain": "technical",
                "subdomain": "indicators",
                "knowledge_type": "book",
                "source_tier": "tier2",
                "language": "en",
            },
            "document_metadata": {
                "doc_id": doc_id,
                "title": f"Title {stem}",
                "author": "Test Author",
                "publisher": "Test Publisher",
                "checksum": "checksum",
            },
        }


class FakeValidator:
    def validate(self, file_path, resolved_metadata):
        stem = Path(file_path).stem
        if stem == "validation_fail":
            return SimpleNamespace(
                is_valid=False,
                level="FATAL",
                messages=["[FATAL] validation failed"],
            )
        return SimpleNamespace(
            is_valid=True,
            level="WARNING" if stem == "partial" else "INFO",
            messages=["[WARNING] test warning"] if stem == "partial" else [],
        )


class FakeChunkBuilder:
    def build_chunks(self, file_path, resolved_metadata):
        stem = Path(file_path).stem
        status_by_stem = {
            "empty": "EMPTY_DOCUMENT",
            "ocr": "NEEDS_OCR",
            "chunk_failed": "FAILED",
            "partial": "PARTIAL_TEXT",
        }
        status = status_by_stem.get(stem, "CHUNKED")
        chunks = []
        if status in {"CHUNKED", "PARTIAL_TEXT"}:
            chunks = [{
                "chunk_id": f"{resolved_metadata['doc_id']}_p1_c1",
                "doc_id": resolved_metadata["doc_id"],
                "text": "chunk text",
                "page": 1,
                "routing_metadata": resolved_metadata["routing_metadata"],
                "document_metadata": resolved_metadata["document_metadata"],
            }]
        return {
            "status": status,
            "chunks": chunks,
            "error": "chunk failed" if status == "FAILED" else "",
            "operational_metadata": {"parser_version": "fake"},
        }


class FakeVectorService:
    def __init__(self):
        self.calls = []

    def upsert_document(self, doc_id, chunks, job_id):
        self.calls.append((doc_id, list(chunks), job_id))
        if doc_id in {"doc_fail", "doc_repo_fail"}:
            return False
        if doc_id == "doc_raise":
            raise RuntimeError("vector exploded")
        return True


class KpIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "data" / "knowledge_repository" / "book" / "technical" / "indicators" / "tester"
        self.repo.mkdir(parents=True)
        self.catalog = TrackingCatalog(self.root / "catalog" / "catalog.sqlite")
        self.vector = FakeVectorService()
        self.ingestor = KnowledgePlatformIngestor(
            resolver=FakeResolver(),
            validator=FakeValidator(),
            chunk_builder=FakeChunkBuilder(),
            catalog=self.catalog,
            vector_service=self.vector,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_pdf(self, stem):
        path = self.repo / f"{stem}.pdf"
        path.write_bytes(b"%PDF-1.4 test\n")
        return path

    def test_dry_run_valid_file_does_not_lock_or_call_vector(self):
        pdf = self.make_pdf("valid")

        result = self.ingestor.dry_run(str(pdf))

        self.assertEqual(result.doc_id, "doc_valid")
        self.assertEqual(result.chunk_count, 1)
        self.assertEqual(result.ocr_status, "CHUNKED")
        self.assertEqual(result.status, "READY")
        self.assertEqual(self.catalog.locks, [])
        self.assertEqual(self.catalog.upserts, [])
        self.assertEqual(self.vector.calls, [])

    def test_missing_manifest_is_quarantined(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("missing_manifest")))

        self.assertEqual(result.status, "QUARANTINE")
        self.assertIn("Missing .manifest.yaml", result.messages[0])
        self.assertEqual(self.catalog.locks, [])
        self.assertEqual(self.vector.calls, [])

    def test_invalid_path_is_quarantined(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("invalid_path")))

        self.assertEqual(result.status, "QUARANTINE")
        self.assertIn("Path convention", result.messages[0])
        self.assertEqual(self.vector.calls, [])

    def test_duplicate_checksum_is_quarantined(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("duplicate")))

        self.assertEqual(result.status, "QUARANTINE")
        self.assertIn("POSSIBLE_DUPLICATE", result.messages[0])
        self.assertEqual(self.vector.calls, [])

    def test_empty_document_and_needs_ocr_do_not_index(self):
        empty = self.ingestor.ingest_file(str(self.make_pdf("empty")))
        ocr = self.ingestor.ingest_file(str(self.make_pdf("ocr")))

        self.assertEqual(empty.status, "EMPTY_DOCUMENT")
        self.assertEqual(ocr.status, "NEEDS_OCR")
        self.assertEqual(self.catalog.locks, [])
        self.assertEqual(self.vector.calls, [])

    def test_partial_text_indexes_with_warning(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("partial")))

        self.assertTrue(result.indexed)
        self.assertEqual(result.status, "INDEXED")
        self.assertTrue(any("PARTIAL_TEXT" in message for message in result.messages))
        self.assertEqual(len(self.catalog.locks), 1)
        self.assertEqual(self.vector.calls[0][0], "doc_partial")

    def test_ingest_file_success_calls_lock_and_vector_upsert(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("success")))

        self.assertTrue(result.indexed)
        self.assertEqual(result.status, "INDEXED")
        self.assertEqual(self.catalog.locks[0][0], "doc_success")
        self.assertEqual(self.vector.calls[0][0], "doc_success")
        self.assertEqual(len(self.vector.calls[0][1]), 1)

    def test_ingest_file_failure_releases_and_marks_failed(self):
        result = self.ingestor.ingest_file(str(self.make_pdf("fail")))

        self.assertFalse(result.indexed)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(self.catalog.releases[-1][0], "doc_fail")
        self.assertEqual(self.catalog.releases[-1][2], "FAILED")
        self.assertEqual(self.catalog.get_document("doc_fail")["index_status"], "FAILED")

    def test_ingest_repo_continues_after_one_file_fails(self):
        self.make_pdf("repo_ok")
        self.make_pdf("repo_fail")

        summary = self.ingestor.ingest_repo(str(self.repo))

        self.assertEqual(summary.discovered, 2)
        self.assertEqual(summary.indexed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(len(self.vector.calls), 2)

    def test_no_legacy_files_or_collections_are_referenced(self):
        script_text = (PROJECT_ROOT / "scripts" / "kp_ingest.py").read_text(encoding="utf-8")

        self.assertNotIn("xauusd_knowledge_v2", script_text)
        self.assertNotIn("ingestion_state", script_text)
        self.assertNotIn("src.services.vector_service", script_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
