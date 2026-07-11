import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


TEST_COLLECTION = "knowledge_test_sprint31"


if importlib.util.find_spec("qdrant_client") is None:
    print("SKIPPED: qdrant_client is not installed, so real Qdrant local smoke test cannot run.")
    sys.exit(0)

if importlib.util.find_spec("dotenv") is None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if importlib.util.find_spec("streamlit") is None:
    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    sys.modules["streamlit"] = streamlit_stub


from qdrant_client import QdrantClient
from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
from src.services.knowledge.vector_service import VectorServiceV3


class FakeEmbeddingClient:
    def embed(self, texts, model, input_type, embedding_types):
        vectors = [[1.0 if i == 0 else 0.0 for i in range(1024)] for _ in texts]
        return types.SimpleNamespace(embeddings=types.SimpleNamespace(float=vectors))


class CollectionScopedVectorService:
    def __init__(self, vector_service, collection_name):
        self.vector_service = vector_service
        self.collection_name = collection_name

    def search(self, query, filters, top_k=8, score_threshold=0.7):
        return self.vector_service.search(
            query=query,
            filters=filters,
            top_k=top_k,
            score_threshold=score_threshold,
            collection_name=self.collection_name,
        )


def make_chunk(
    doc_id,
    chunk_id,
    text,
    strategies=None,
    assets=None,
    timeframe_focus=None,
    lifecycle="ACTIVE",
    index_status="INDEXED",
):
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "text": text,
        "page": 7,
        "routing_metadata": {
            "domain": "technical",
            "subdomain": "indicators",
            "strategies": strategies if strategies is not None else ["trend_following"],
            "assets": assets if assets is not None else ["forex"],
            "timeframe_focus": timeframe_focus if timeframe_focus is not None else ["h1"],
            "knowledge_type": "book",
            "source_tier": "tier2",
            "language": "en",
        },
        "document_metadata": {
            "doc_id": doc_id,
            "title": "Sprint 3.1 Smoke Fixture",
            "author": "Integration Test",
            "lifecycle": lifecycle,
            "index_status": index_status,
        },
        "operational_metadata": {"index_version": "v3-test"},
    }


class Sprint31V3IntegrationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        temp_path = Path(cls.temp_dir.name)
        cls.client = QdrantClient(path=str(temp_path / "qdrant"))
        cls.catalog = KnowledgeCatalog(str(temp_path / "catalog" / "catalog.sqlite"))
        cls.vector_service = VectorServiceV3(
            client=cls.client,
            catalog=cls.catalog,
            cohere_client=FakeEmbeddingClient(),
        )
        cls.knowledge_service = KnowledgeService(
            vector_service=CollectionScopedVectorService(cls.vector_service, TEST_COLLECTION)
        )
        cls._seed_collection()

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "client", None) and cls.client.collection_exists(TEST_COLLECTION):
                cls.client.delete_collection(TEST_COLLECTION)
        finally:
            if getattr(cls, "client", None) and hasattr(cls.client, "close"):
                cls.client.close()
            if getattr(cls, "temp_dir", None):
                cls.temp_dir.cleanup()

    @classmethod
    def _seed_collection(cls):
        chunks = [
            make_chunk(
                "doc-active",
                "doc-active_p7_c1",
                "Trend following indicator content for forex markets.",
            ),
            make_chunk(
                "doc-fallback",
                "doc-fallback_p7_c1",
                "Different routing metadata that should be reached by fallback.",
                strategies=["mean_reversion"],
                assets=["commodities"],
                timeframe_focus=["d1"],
            ),
            make_chunk(
                "doc-inactive",
                "doc-inactive_p7_c1",
                "Inactive document should never be returned.",
                lifecycle="ARCHIVED",
            ),
            make_chunk(
                "doc-failed-index",
                "doc-failed-index_p7_c1",
                "Failed index status should be post-filtered.",
                index_status="FAILED",
            ),
        ]
        cls.catalog.acquire_index_lock("sprint31-seed", "sprint31-seed-job")
        ok = cls.vector_service.upsert_document(
            "sprint31-seed",
            chunks,
            "sprint31-seed-job",
            collection_name=TEST_COLLECTION,
        )
        if not ok:
            raise RuntimeError("Failed to seed isolated Sprint 3.1 Qdrant collection.")

    def test_domain_only_search_works_and_excludes_unsafe_chunks(self):
        response = self.knowledge_service.search(
            SearchRequest(
                query="indicator",
                routing_filters={"domain": "technical"},
                top_k=10,
                score_threshold=0.0,
            )
        )

        chunk_ids = {chunk["citation"]["chunk_id"] for chunk in response.chunks}
        self.assertIn("doc-active_p7_c1", chunk_ids)
        self.assertIn("doc-fallback_p7_c1", chunk_ids)
        self.assertNotIn("doc-inactive_p7_c1", chunk_ids)
        self.assertNotIn("doc-failed-index_p7_c1", chunk_ids)

    def test_full_filter_search_works(self):
        response = self.knowledge_service.search(
            SearchRequest(
                query="trend following",
                routing_filters={
                    "domain": "technical",
                    "subdomain": "indicators",
                    "strategies": ["trend_following"],
                    "assets": ["forex"],
                    "timeframe_focus": ["h1"],
                },
                top_k=10,
                score_threshold=0.0,
            )
        )

        chunk_ids = {chunk["citation"]["chunk_id"] for chunk in response.chunks}
        self.assertIn("doc-active_p7_c1", chunk_ids)
        self.assertNotIn("doc-fallback_p7_c1", chunk_ids)
        self.assertEqual(response.fallback_level, 0)

    def test_fallback_works_without_removing_domain(self):
        response = self.knowledge_service.search(
            SearchRequest(
                query="fallback",
                routing_filters={
                    "domain": "technical",
                    "subdomain": "missing_subdomain",
                    "strategies": ["trend_following"],
                    "assets": ["forex"],
                    "timeframe_focus": ["h1"],
                },
                top_k=10,
                score_threshold=0.0,
            )
        )

        self.assertGreater(response.total_found, 0)
        self.assertEqual(response.fallback_level, 4)
        self.assertEqual(response.filters_used["domain"], "technical")

    def test_citation_object_is_structured(self):
        response = self.knowledge_service.search(
            SearchRequest(
                query="citation",
                routing_filters={"domain": "technical"},
                top_k=10,
                score_threshold=0.0,
            )
        )

        citation = response.chunks[0]["citation"]
        self.assertTrue(
            {"doc_id", "chunk_id", "title", "author", "page", "source_tier"}.issubset(set(citation)),
            citation,
        )
        self.assertTrue(citation["doc_id"])
        self.assertTrue(citation["chunk_id"])
        self.assertEqual(citation["title"], "Sprint 3.1 Smoke Fixture")
        self.assertEqual(citation["author"], "Integration Test")
        self.assertEqual(citation["page"], 7)
        self.assertEqual(citation["source_tier"], "tier2")


if __name__ == "__main__":
    print(f"Running Sprint 3.1 smoke test with isolated collection: {TEST_COLLECTION}")
    unittest.main(verbosity=2)
