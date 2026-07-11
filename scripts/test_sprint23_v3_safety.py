import os
import importlib.util
import sqlite3
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def install_dependency_stubs():
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv_stub)

    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = (
        lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    )
    sys.modules.setdefault("streamlit", streamlit_stub)

    cohere_stub = types.ModuleType("cohere")
    cohere_stub.ClientV2 = object
    sys.modules.setdefault("cohere", cohere_stub)

    if importlib.util.find_spec("fitz") is None:
        fitz_stub = types.ModuleType("fitz")
        fitz_stub.VersionBind = "test-stub"
        fitz_stub.open = lambda *args, **kwargs: None
        sys.modules["fitz"] = fitz_stub

    if importlib.util.find_spec("qdrant_client") is None:
        qdrant_stub = types.ModuleType("qdrant_client")
        qdrant_stub.QdrantClient = object
        qdrant_models_stub = types.ModuleType("qdrant_client.models")

        class Distance:
            COSINE = "Cosine"

        class VectorParams:
            def __init__(self, size, distance):
                self.size = size
                self.distance = distance

        class PointStruct:
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload

        class MatchValue:
            def __init__(self, value):
                self.value = value

        class FieldCondition:
            def __init__(self, key, match):
                self.key = key
                self.match = match

        class Filter:
            def __init__(self, must):
                self.must = must

        for name, cls in {
            "Distance": Distance,
            "VectorParams": VectorParams,
            "PointStruct": PointStruct,
            "Filter": Filter,
            "FieldCondition": FieldCondition,
            "MatchValue": MatchValue,
        }.items():
            setattr(qdrant_models_stub, name, cls)

        sys.modules["qdrant_client"] = qdrant_stub
        sys.modules["qdrant_client.models"] = qdrant_models_stub


install_dependency_stubs()

from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.chunk_builder import ChunkBuilder
from src.services.knowledge.document_parser import ParsedDocument, ParsedSection
from src.services.knowledge.metadata_resolver import MetadataResolver
from src.services.knowledge.registry_loader import RegistryLoader
from src.services.knowledge.vector_service import VectorServiceV3


class FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self):
        return self.text


class FakePdf:
    def __init__(self, pages):
        self.pages = [FakePage(text) for text in pages]
        self.closed = False

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def close(self):
        self.closed = True


class FakeEmbeddingClient:
    def embed(self, texts, model, input_type, embedding_types):
        vectors = [[float((i % 7) + 1) for i in range(1024)] for _ in texts]
        return types.SimpleNamespace(embeddings=types.SimpleNamespace(float=vectors))


class FakeParserRegistry:
    def __init__(self, pages):
        self.pages = list(pages)

    def parse(self, file_path, metadata):
        total_pages = len(self.pages)
        non_empty = [(index, text) for index, text in enumerate(self.pages, start=1) if str(text or "").strip()]
        empty_pages = total_pages - len(non_empty)
        if total_pages == 0 or not non_empty:
            status = "EMPTY_DOCUMENT"
            quality = 0.0
            sections = []
        else:
            quality = len(non_empty) / max(total_pages, 1)
            if quality < 0.2:
                status = "NEEDS_OCR"
                sections = []
            elif quality < 0.8:
                status = "PARTIAL_TEXT"
                sections = [
                    ParsedSection(text=text, page=index, location=f"page:{index}")
                    for index, text in non_empty
                ]
            else:
                status = "CHUNKED"
                sections = [
                    ParsedSection(text=text, page=index, location=f"page:{index}")
                    for index, text in non_empty
                ]
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:test",
            parser_version="test-parser",
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            metadata_hints={
                "total_pages": total_pages,
                "empty_pages": empty_pages,
                "quality": {
                    "total_pages": total_pages,
                    "empty_pages": empty_pages,
                    "quality_score": quality,
                    "needs_ocr": status == "NEEDS_OCR",
                },
            },
        )


class FakeQdrantClient:
    def __init__(self, fail_on_upsert_call=None, persist_before_failure=False):
        self.collections = set()
        self.points = {}
        self.upsert_calls = 0
        self.delete_calls = []
        self.fail_on_upsert_call = fail_on_upsert_call
        self.persist_before_failure = persist_before_failure

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config):
        self.collections.add(collection_name)
        self.points.setdefault(collection_name, {})

    def upsert(self, collection_name, points, wait=True):
        self.upsert_calls += 1
        self.points.setdefault(collection_name, {})

        if self.fail_on_upsert_call == self.upsert_calls:
            if self.persist_before_failure:
                for point in points:
                    self.points[collection_name][point.id] = point
            raise RuntimeError("simulated qdrant batch failure")

        for point in points:
            self.points[collection_name][point.id] = point

    def delete(self, collection_name, points_selector, wait=True):
        del wait
        self.delete_calls.append((collection_name, points_selector))
        self.points.setdefault(collection_name, {})
        must = list(getattr(points_selector, "must", None) or [])
        must_not = list(getattr(points_selector, "must_not", None) or [])
        to_delete = [
            point_id
            for point_id, point in self.points[collection_name].items()
            if self._matches_filter(point.payload, must, must_not)
        ]
        for point_id in to_delete:
            del self.points[collection_name][point_id]

    def _matches_filter(self, payload, must, must_not):
        return all(self._matches_condition(payload, condition) for condition in must) and not any(
            self._matches_condition(payload, condition) for condition in must_not
        )

    def _matches_condition(self, payload, condition):
        key = getattr(condition, "key", None)
        match = getattr(condition, "match", None)
        if not key or match is None:
            return False
        if hasattr(match, "value"):
            return payload.get(key) == getattr(match, "value")
        if hasattr(match, "any"):
            return payload.get(key) in set(getattr(match, "any") or [])
        return False

    def delete_doc(self, doc_id, collection_name):
        self.points.setdefault(collection_name, {})
        to_delete = [
            point_id
            for point_id, point in self.points[collection_name].items()
            if point.payload.get("doc_id") == doc_id
        ]
        for point_id in to_delete:
            del self.points[collection_name][point_id]

    def count_doc(self, doc_id, collection_name):
        return sum(
            1
            for point in self.points.get(collection_name, {}).values()
            if point.payload.get("doc_id") == doc_id
        )

    def ids_for_doc(self, doc_id, collection_name):
        return {
            point_id
            for point_id, point in self.points.get(collection_name, {}).items()
            if point.payload.get("doc_id") == doc_id
        }


class KnowledgePlatformV3SafetyTests(unittest.TestCase):
    def make_catalog(self, temp_dir):
        return KnowledgeCatalog(str(Path(temp_dir) / "catalog" / "catalog.sqlite"))

    def make_resolver(self, catalog):
        resolver = MetadataResolver.__new__(MetadataResolver)
        resolver.registry = RegistryLoader()
        resolver.catalog = catalog
        return resolver

    def write_pdf(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n% test fixture\n")

    def write_manifest(self, pdf_path, checksum="checksum-a", title_slug="fixture"):
        manifest = {
            "title": "Fixture Document",
            "title_slug": title_slug,
            "author_slug": "test_author",
            "author": "Test Author",
            "knowledge_type": "book",
            "domain": "technical",
            "version": "v1",
            "language": "en",
            "lifecycle": "ACTIVE",
            "checksum": checksum,
            "publisher": "Test Publisher",
            "publish_year": 2026,
            "tags": {
                "strategies": ["trend_following"],
                "assets": ["XAUUSD"],
                "timeframe_focus": ["H1"],
            },
        }
        manifest_path = pdf_path.with_suffix(".manifest.yaml")
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        return manifest_path

    def make_valid_pdf_path(self, temp_dir, filename="fixture.pdf"):
        return (
            Path(temp_dir)
            / "data"
            / "knowledge_repository"
            / "book"
            / "technical"
            / "indicators"
            / "test_author"
            / filename
        )

    def make_vector_service(self, catalog, client):
        service = VectorServiceV3.__new__(VectorServiceV3)
        service.client = client
        service.catalog = catalog
        service.cohere_client = FakeEmbeddingClient()
        service.embedding_provider = "cohere"
        service.embedding_model = "embed-multilingual-v3.0"
        service.batch_size = 32
        service.request_timeout_seconds = 90
        service.max_retries = 0
        service.backoff_base_seconds = 1
        service.backoff_max_seconds = 1
        service.rate_limit_cooldown_seconds = 1
        service.circuit_breaker_failures = 3
        service.fail_fast_on_auth = True
        service.retry_jitter = False
        service.sleep_fn = lambda _seconds: None
        service.embedding_cache = None
        service.last_index_result = {}
        service._rate_limit_streak = 0
        service._cohere_api_key_present = True
        service.delete_calls = []

        def fake_delete(doc_id, collection_name="knowledge_current"):
            service.delete_calls.append((doc_id, collection_name))
            client.delete_doc(doc_id, collection_name)

        service.delete_by_doc_id = fake_delete
        return service

    def make_chunks(self, doc_id, count=3):
        return [
            {
                "chunk_id": f"{doc_id}_p1_c{i + 1}",
                "doc_id": doc_id,
                "text": f"Chunk {i + 1} text with enough deterministic content for indexing.",
                "page": 1,
                "routing_metadata": {
                    "domain": "technical",
                    "subdomain": "indicators",
                    "knowledge_type": "book",
                    "source_tier": "tier3",
                    "language": "en",
                },
                "document_metadata": {"doc_id": doc_id, "title": "Fixture"},
                "operational_metadata": {"parser_version": "test"},
            }
            for i in range(count)
        ]

    def test_strict_path_outside_repository_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            resolver = self.make_resolver(catalog)
            outside_pdf = Path(temp_dir) / "random" / "outside.pdf"

            result = resolver.resolve(str(outside_pdf))

            self.assertEqual(result["lifecycle"], "QUARANTINE")
            self.assertIn("knowledge_repository", result["error"])

    def test_missing_manifest_is_quarantined_without_guessing_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            resolver = self.make_resolver(catalog)
            pdf_path = self.make_valid_pdf_path(temp_dir)
            self.write_pdf(pdf_path)

            result = resolver.resolve(str(pdf_path))

            self.assertEqual(result["lifecycle"], "QUARANTINE")
            self.assertIn("Missing .manifest.yaml", result["error"])
            self.assertNotIn("doc_id", result)

    def test_duplicate_checksum_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            catalog.upsert_document("book_existing_other_author_v1", {"checksum": "same-checksum"})
            resolver = self.make_resolver(catalog)
            pdf_path = self.make_valid_pdf_path(temp_dir, filename="duplicate.pdf")
            self.write_pdf(pdf_path)
            self.write_manifest(pdf_path, checksum="same-checksum", title_slug="duplicate")

            result = resolver.resolve(str(pdf_path))

            self.assertEqual(result["lifecycle"], "QUARANTINE")
            self.assertIn("POSSIBLE_DUPLICATE", result["error"])

    def test_catalog_rejects_second_active_index_lock_for_same_doc(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)

            first = catalog.acquire_index_lock("doc-lock", "job-1", worker_id="worker-a")
            second = catalog.acquire_index_lock("doc-lock", "job-2", worker_id="worker-b")

            self.assertTrue(first)
            self.assertFalse(second)
            with catalog._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM index_jobs WHERE doc_id = ? AND job_status = 'RUNNING'",
                    ("doc-lock",),
                )
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_stale_heartbeat_reconciliation_marks_failed_and_cleans_vectors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            self.assertTrue(catalog.acquire_index_lock("doc-stale", "job-stale"))
            with catalog._connect() as conn:
                conn.execute(
                    "UPDATE index_jobs SET heartbeat_at = ? WHERE job_id = ?",
                    (time.time() - 3600, "job-stale"),
                )
                conn.commit()

            fake_client = FakeQdrantClient()
            service = self.make_vector_service(catalog, fake_client)

            service.reconcile_index_jobs(timeout_seconds=300)

            document = catalog.get_document("doc-stale")
            self.assertEqual(document["index_status"], "PENDING_RETRY")
            self.assertEqual(service.delete_calls, [])
            self.assertEqual(fake_client.delete_calls, [])
            with catalog._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT job_status, log FROM index_jobs WHERE job_id = ?", ("job-stale",))
                job_status, log = cursor.fetchone()
            self.assertEqual(job_status, "PENDING_RETRY")
            self.assertIn("Stale indexing lock", log)

    def test_chunk_builder_ocr_guardrails_do_not_return_empty_chunks(self):
        from src.services.knowledge import chunk_builder as chunk_builder_module

        metadata = {
            "routing_metadata": {"domain": "technical"},
            "document_metadata": {"doc_id": "doc-chunks"},
        }
        long_text = "extracted trading text " * 20
        builder = ChunkBuilder(chunk_size=120, overlap=20)

        cases = [
            ([], "EMPTY_DOCUMENT"),
            (["", "   "], "EMPTY_DOCUMENT"),
            ([long_text] + [""] * 9, "NEEDS_OCR"),
            ([long_text, long_text, long_text, ""], "PARTIAL_TEXT"),
        ]

        for pages, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                builder = ChunkBuilder(
                    chunk_size=120,
                    overlap=20,
                    parser_registry=FakeParserRegistry(pages),
                )

                result = builder.build_chunks("fake.pdf", metadata)

                self.assertEqual(result["status"], expected_status)
                self.assertTrue(all(chunk["text"].strip() for chunk in result["chunks"]))
                if expected_status in {"EMPTY_DOCUMENT", "NEEDS_OCR"}:
                    self.assertEqual(result["chunks"], [])
                if expected_status == "PARTIAL_TEXT":
                    self.assertGreater(len(result["chunks"]), 0)

    def test_vector_upsert_is_idempotent_and_uses_deterministic_point_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            fake_client = FakeQdrantClient()
            service = self.make_vector_service(catalog, fake_client)
            doc_id = "doc-vector"
            chunks = self.make_chunks(doc_id, count=3)

            self.assertTrue(catalog.acquire_index_lock(doc_id, "job-vector-1"))
            self.assertTrue(service.upsert_document(doc_id, chunks, "job-vector-1"))
            first_ids = fake_client.ids_for_doc(doc_id, "knowledge_current")
            self.assertEqual(fake_client.count_doc(doc_id, "knowledge_current"), 3)

            self.assertTrue(catalog.acquire_index_lock(doc_id, "job-vector-2"))
            self.assertTrue(service.upsert_document(doc_id, chunks, "job-vector-2"))
            second_ids = fake_client.ids_for_doc(doc_id, "knowledge_current")

            fingerprint = service._chunks_fingerprint(chunks)
            expected_ids = {
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{fingerprint}:{chunk['chunk_id']}"))
                for chunk in chunks
            }
            self.assertEqual(first_ids, expected_ids)
            self.assertEqual(second_ids, expected_ids)
            self.assertEqual(fake_client.count_doc(doc_id, "knowledge_current"), 3)
            self.assertEqual(service.delete_calls, [])
            self.assertEqual(len(fake_client.delete_calls), 2)

    def test_vector_upsert_failure_cleans_partial_vectors_and_marks_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = self.make_catalog(temp_dir)
            fake_client = FakeQdrantClient(fail_on_upsert_call=1, persist_before_failure=True)
            service = self.make_vector_service(catalog, fake_client)
            doc_id = "doc-failure"
            chunks = self.make_chunks(doc_id, count=97)

            self.assertTrue(catalog.acquire_index_lock(doc_id, "job-failure"))
            result = service.upsert_document(doc_id, chunks, "job-failure")

            self.assertFalse(result)
            self.assertEqual(fake_client.count_doc(doc_id, "knowledge_current"), 0)
            self.assertEqual(service.delete_calls, [])
            self.assertGreaterEqual(len(fake_client.delete_calls), 1)
            document = catalog.get_document(doc_id)
            self.assertEqual(document["index_status"], "FAILED_UPSERT")
            self.assertIn("simulated qdrant batch failure", document["error_message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
