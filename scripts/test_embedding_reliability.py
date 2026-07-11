import io
import importlib.util
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "qdrant_client" not in sys.modules and importlib.util.find_spec("qdrant_client") is None:
    qdrant_stub = types.ModuleType("qdrant_client")
    models_stub = types.ModuleType("qdrant_client.models")

    class _Model:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def __repr__(self):
            args = ", ".join(f"{key}={value!r}" for key, value in self.__dict__.items())
            return f"{self.__class__.__name__}({args})"

    class Distance:
        COSINE = "Cosine"

    class FieldCondition(_Model):
        pass

    class Filter(_Model):
        pass

    class MatchValue(_Model):
        pass

    class PointStruct(_Model):
        pass

    class VectorParams(_Model):
        pass

    class QdrantClient:
        def __init__(self, *args, **kwargs):
            pass

    models_stub.Distance = Distance
    models_stub.FieldCondition = FieldCondition
    models_stub.Filter = Filter
    models_stub.MatchValue = MatchValue
    models_stub.PointStruct = PointStruct
    models_stub.VectorParams = VectorParams
    qdrant_stub.QdrantClient = QdrantClient
    qdrant_stub.models = models_stub
    sys.modules["qdrant_client"] = qdrant_stub
    sys.modules["qdrant_client.models"] = models_stub

if "streamlit" not in sys.modules:
    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    sys.modules["streamlit"] = streamlit_stub

from src.config import Config
from src.services.knowledge.embedding_reliability import (
    EmbeddingCache,
    EmbeddingCircuitOpen,
    classify_embedding_error,
)
from src.services.knowledge.retrieval_smoke import RetrievalSmokeEvaluator, RetrievalSmokeStatus
from src.services.knowledge.vector_service import VectorServiceV3


def vector(value=0.1, size=1024):
    return [value for _ in range(size)]


class FakeEmbeddings:
    def __init__(self, vectors):
        self.float = vectors


class FakeResponse:
    def __init__(self, vectors):
        self.embeddings = FakeEmbeddings(vectors)


class FakeCohere:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []

    def embed(self, **kwargs):
        self.calls.append(kwargs)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        texts = kwargs.get("texts", [])
        return FakeResponse([vector(0.2) for _ in texts])


class FakeQdrant:
    def __init__(self, upsert_result=True):
        self.upsert_result = upsert_result
        self.created = []
        self.upserts = []
        self.deletes = []

    def collection_exists(self, collection_name):
        return True

    def create_collection(self, **kwargs):
        self.created.append(kwargs)

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)
        return self.upsert_result

    def delete(self, **kwargs):
        self.deletes.append(kwargs)
        return True


class FakeCatalog:
    def __init__(self):
        self.releases = []
        self.upserts = []
        self.heartbeats = []

    def heartbeat(self, job_id):
        self.heartbeats.append(job_id)

    def release_index_lock(self, doc_id, job_id, status, error_msg=""):
        self.releases.append(
            {"doc_id": doc_id, "job_id": job_id, "status": status, "error_msg": error_msg}
        )

    def upsert_document(self, doc_id, data):
        self.upserts.append({"doc_id": doc_id, "data": data})

    def get_stale_jobs(self, timeout_seconds):
        return []


class FakeSmokeSearch:
    def search(self, request):
        raise Exception("429 rate limit from embedding provider")


class EmbeddingReliabilityTests(unittest.TestCase):
    def setUp(self):
        self._old_values = {
            name: getattr(Config, name)
            for name in [
                "EMBEDDING_BATCH_SIZE",
                "EMBEDDING_MAX_RETRIES",
                "EMBEDDING_BACKOFF_BASE_SECONDS",
                "EMBEDDING_BACKOFF_MAX_SECONDS",
                "EMBEDDING_CIRCUIT_BREAKER_FAILURES",
                "EMBEDDING_RETRY_JITTER",
                "EMBEDDING_CACHE_ENABLED",
            ]
        }
        Config.EMBEDDING_BATCH_SIZE = 2
        Config.EMBEDDING_MAX_RETRIES = 3
        Config.EMBEDDING_BACKOFF_BASE_SECONDS = 1
        Config.EMBEDDING_BACKOFF_MAX_SECONDS = 10
        Config.EMBEDDING_CIRCUIT_BREAKER_FAILURES = 10
        Config.EMBEDDING_RETRY_JITTER = False
        Config.EMBEDDING_CACHE_ENABLED = False

    def tearDown(self):
        for name, value in self._old_values.items():
            setattr(Config, name, value)

    def make_service(self, cohere_client=None, qdrant=None, catalog=None, sleep_calls=None, cache=None):
        sleep_calls = sleep_calls if sleep_calls is not None else []
        return VectorServiceV3(
            client=qdrant or FakeQdrant(),
            catalog=catalog or FakeCatalog(),
            cohere_client=cohere_client or FakeCohere(),
            embedding_cache=cache,
            sleep_fn=sleep_calls.append,
        )

    def test_error_classifier_categories(self):
        self.assertEqual(classify_embedding_error(missing_key=True).category, "missing_api_key")
        self.assertFalse(classify_embedding_error(missing_key=True).retryable)
        self.assertEqual(classify_embedding_error(Exception("401 invalid API key")).category, "invalid_api_key")
        self.assertFalse(classify_embedding_error(Exception("401 invalid API key")).retryable)
        rate = classify_embedding_error(Exception("429 rate limit exceeded"))
        self.assertEqual(rate.category, "rate_limited")
        self.assertTrue(rate.retryable)
        timeout = classify_embedding_error(TimeoutError("request timeout"))
        self.assertEqual(timeout.category, "timeout")
        self.assertTrue(timeout.retryable)

    def test_retry_backoff_then_success(self):
        sleep_calls = []
        cohere = FakeCohere(
            [
                Exception("429 rate limit"),
                Exception("429 rate limit"),
                FakeResponse([vector(0.4)]),
            ]
        )
        service = self.make_service(cohere_client=cohere, sleep_calls=sleep_calls)

        with redirect_stdout(io.StringIO()):
            result = service._embed_texts_reliably(
                ["hello"],
                input_type="search_document",
                doc_id="doc",
                fingerprint="fp",
                batch_label="1/1",
            )

        self.assertEqual(len(result["vectors"]), 1)
        self.assertEqual(sleep_calls, [1.0, 2.0])
        self.assertEqual(result["rate_limit_count"], 2)
        self.assertEqual(len(cohere.calls), 3)
        self.assertIn("request_options", cohere.calls[-1])

    def test_circuit_breaker_opens_after_repeated_rate_limits(self):
        Config.EMBEDDING_CIRCUIT_BREAKER_FAILURES = 2
        cohere = FakeCohere([Exception("429 rate limit"), Exception("429 rate limit")])
        service = self.make_service(cohere_client=cohere, sleep_calls=[])

        with self.assertRaises(EmbeddingCircuitOpen):
            with redirect_stdout(io.StringIO()):
                service._embed_texts_reliably(
                    ["hello"],
                    input_type="search_document",
                    doc_id="doc",
                    fingerprint="fp",
                    batch_label="1/1",
                )

    def test_embedding_cache_reuses_vectors_without_provider_call(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cache = EmbeddingCache(str(Path(tmpdir) / "cache.sqlite"), enabled=True)
            cache.set_many("cohere", "embed-multilingual-v3.0", "search_document", ["cached"], [vector(0.7)])
            cohere = FakeCohere()
            service = self.make_service(cohere_client=cohere, cache=cache)

            with redirect_stdout(io.StringIO()):
                result = service._embed_texts_reliably(
                    ["cached"],
                    input_type="search_document",
                    doc_id="doc",
                    fingerprint="fp",
                    batch_label="1/1",
                )

            self.assertEqual(result["cache_hits"], 1)
            self.assertEqual(len(cohere.calls), 0)

    def test_upsert_failure_does_not_delete_old_vectors_before_success(self):
        qdrant = FakeQdrant(upsert_result=False)
        catalog = FakeCatalog()
        service = self.make_service(cohere_client=FakeCohere(), qdrant=qdrant, catalog=catalog)
        chunks = [
            {
                "chunk_id": "chunk-1",
                "text": "hello",
                "routing_metadata": {"domain": "technical"},
                "document_metadata": {"lifecycle": "ACTIVE"},
            }
        ]

        with redirect_stdout(io.StringIO()):
            ok = service.upsert_document("doc", chunks, "job", ingestion_fingerprint="fp-new")

        self.assertFalse(ok)
        self.assertEqual(catalog.releases[-1]["status"], "FAILED_UPSERT")
        self.assertEqual(service.last_index_result["status"], "FAILED_UPSERT")
        self.assertEqual(len(qdrant.upserts), 1)
        self.assertEqual(len(qdrant.deletes), 1)
        delete_filter = qdrant.deletes[0]["points_selector"]
        self.assertIn("ingestion_fingerprint", str(delete_filter))

    def test_upsert_success_commits_indexed_status(self):
        qdrant = FakeQdrant(upsert_result=True)
        catalog = FakeCatalog()
        service = self.make_service(cohere_client=FakeCohere(), qdrant=qdrant, catalog=catalog)
        chunks = [
            {
                "chunk_id": "chunk-1",
                "text": "hello",
                "routing_metadata": {"domain": "technical"},
                "document_metadata": {"lifecycle": "ACTIVE"},
            }
        ]

        with redirect_stdout(io.StringIO()):
            ok = service.upsert_document("doc", chunks, "job", ingestion_fingerprint="fp-new")

        self.assertTrue(ok)
        self.assertEqual(catalog.releases[-1]["status"], "INDEXED")
        self.assertEqual(service.last_index_result["vectors"], 1)
        self.assertEqual(len(qdrant.deletes), 1)
        self.assertIn("must_not", str(qdrant.deletes[0]["points_selector"]))

    def test_retrieval_smoke_rate_limit_is_skipped_not_failed(self):
        evaluator = RetrievalSmokeEvaluator(search_service=FakeSmokeSearch())
        metadata = {
            "routing_metadata": {"domain": "market", "subdomain": "gold"},
            "document_metadata": {"title": "Gold Market Commentary", "organization": "World Gold Council"},
        }

        with redirect_stdout(io.StringIO()):
            result = evaluator.evaluate_document("doc", metadata)

        self.assertEqual(result.status, RetrievalSmokeStatus.SKIPPED)
        self.assertEqual(result.reason, "embedding_rate_limited")


if __name__ == "__main__":
    unittest.main()
