import importlib.util
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


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
from src.services.knowledge.update_service import IngestionStatus, KnowledgeUpdateService


class CountingParserRegistry:
    supported_extensions = {".pdf", ".epub"}

    def __init__(self):
        self.calls = []

    def parse(self, file_path: str) -> ParsedDocument:
        self.calls.append(file_path)
        text = ("runtime backfill simulation content. " * 140).strip()
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:fake",
            parser_version="fake",
            extraction_status="CHUNKED",
            extraction_quality=1.0,
            sections=[ParsedSection(text=text, page=1, section="Runtime")],
            metadata_hints={"total_pages": 1},
        )


class CountingChunkBuilder:
    def __init__(self):
        self.calls = []

    def build_chunks_from_parsed(self, parsed_document, metadata):
        self.calls.append(parsed_document.file_path)
        text = parsed_document.text
        chunks = [
            {
                "chunk_id": "runtime_chunk_1",
                "parent_chunk_id": "runtime_parent_1",
                "text": text[:1200],
                "metadata": {"doc_id": metadata.get("doc_id", "")},
            }
        ]
        return {
            "status": "CHUNKED",
            "chunks": chunks,
            "chunk_stats": {
                "selected_chunk_policy": "runtime_test_policy",
                "parent_chunk_count": 1,
                "parent_size_chars": 1200,
                "child_size_chars": 600,
                "parent_overlap_chars": 120,
                "child_overlap_chars": 80,
            },
            "operational_metadata": {
                "chunker_version": "runtime_test_chunker",
                "pdf_parser_mode": Config.PDF_PARSER_MODE,
                "mineru_backend": Config.MINERU_BACKEND,
                "mineru_method": Config.MINERU_METHOD,
                "parser_output_schema_version": Config.PARSER_OUTPUT_SCHEMA_VERSION,
            },
        }


class FakeVectorService:
    def __init__(self, catalog):
        self.catalog = catalog
        self.calls = []
        self.last_index_result = {"status": "INDEXED", "vectors": 0}

    def upsert_document(self, doc_id, chunks, job_id, **kwargs):
        self.calls.append((doc_id, len(chunks), job_id, kwargs))
        self.last_index_result = {"status": "INDEXED", "vectors": len(chunks)}
        self.catalog.release_index_lock(doc_id, job_id, "INDEXED")
        return True

    def delete_by_doc_id(self, doc_id, collection_name="knowledge_current"):
        return None


class FastPrecheckRuntimeSimulationTests(unittest.TestCase):
    def setUp(self):
        self._old_fast = Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED
        self._old_hash_cache = Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED
        self._old_reparse = Config.KNOWLEDGE_UPDATE_FORCE_REPARSE
        self._old_reindex = Config.KNOWLEDGE_UPDATE_FORCE_REINDEX
        Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED = True
        Config.KNOWLEDGE_UPDATE_FORCE_REPARSE = False
        Config.KNOWLEDGE_UPDATE_FORCE_REINDEX = False

    def tearDown(self):
        Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED = self._old_fast
        Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_HASH_CACHE_ENABLED = self._old_hash_cache
        Config.KNOWLEDGE_UPDATE_FORCE_REPARSE = self._old_reparse
        Config.KNOWLEDGE_UPDATE_FORCE_REINDEX = self._old_reindex

    def make_service(self, tmpdir):
        root = Path(tmpdir) / "data" / "knowledge_repository"
        catalog_path = Path(tmpdir) / "catalog.sqlite"
        catalog = KnowledgeCatalog(str(catalog_path))
        parser = CountingParserRegistry()
        chunk_builder = CountingChunkBuilder()
        vector = FakeVectorService(catalog)
        service = KnowledgeUpdateService(
            repository_path=str(root),
            parser_registry=parser,
            chunk_builder=chunk_builder,
            catalog=catalog,
            vector_service=vector,
            retrieval_smoke_evaluator=None,
        )
        return root, service, parser, chunk_builder, vector, catalog_path

    def write_doc(self, root):
        path = root / "book" / "technical" / "indicators" / "owner" / "runtime_backfill.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime-backfill")
        return path

    def test_backfill_run_then_second_run_skips_before_parse(self):
        with TemporaryDirectory() as tmpdir:
            root, service, parser, chunk_builder, vector, catalog_path = self.make_service(tmpdir)
            pdf = self.write_doc(root)

            Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED = False
            initial = service.update_file(str(pdf))
            self.assertEqual(initial.status, IngestionStatus.INDEXED)
            self.assertEqual(len(parser.calls), 1)
            self.assertEqual(len(chunk_builder.calls), 1)
            self.assertEqual(len(vector.calls), 1)

            inspect_script = PROJECT_ROOT / "scripts" / "inspect_fast_precheck_state.py"
            before = subprocess.run(
                [sys.executable, str(inspect_script), "--catalog", str(catalog_path), "--missing-only"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(before.returncode, 0)
            self.assertIn(initial.doc_id, before.stdout)

            Config.KNOWLEDGE_UPDATE_FAST_PRECHECK_ENABLED = True
            backfill = service.update_file(str(pdf))
            self.assertEqual(backfill.status, IngestionStatus.SKIPPED_ALREADY_INDEXED)
            self.assertEqual(backfill.reason, "UNCHANGED_ALREADY_INDEXED")
            self.assertEqual(backfill.precheck_reason, "NO_PREVIOUS_FAST_FINGERPRINT")
            self.assertTrue(backfill.fast_precheck_backfilled)
            self.assertEqual(len(parser.calls), 2)
            self.assertEqual(len(chunk_builder.calls), 2)
            self.assertEqual(len(vector.calls), 1)

            document = service.catalog.get_document(backfill.doc_id)
            self.assertTrue(document.get("fast_precheck_fingerprint"))
            self.assertEqual(
                document.get("fast_precheck_ingestion_fingerprint"),
                document.get("ingestion_fingerprint"),
            )
            self.assertEqual(document.get("last_successful_status"), IngestionStatus.SKIPPED_UNCHANGED)

            after = subprocess.run(
                [sys.executable, str(inspect_script), "--catalog", str(catalog_path), "--missing-only"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(after.returncode, 0)
            self.assertIn("No documents matched.", after.stdout)

            second = service.update_file(str(pdf))
            self.assertEqual(second.status, IngestionStatus.SKIPPED_ALREADY_INDEXED)
            self.assertEqual(second.reason, "FAST_FINGERPRINT_UNCHANGED")
            self.assertTrue(second.precheck_skipped)
            self.assertEqual(len(parser.calls), 2)
            self.assertEqual(len(chunk_builder.calls), 2)
            self.assertEqual(len(vector.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
