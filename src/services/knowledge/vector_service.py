import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

try:
    from qdrant_client.models import MatchAny
except (ImportError, AttributeError):
    MatchAny = None

from src.config import Config
from src.core.database import QdrantDatabaseProvider
from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.embedding_reliability import (
    EmbeddingCache,
    EmbeddingCircuitOpen,
    EmbeddingErrorInfo,
    EmbeddingProviderError,
    classify_embedding_error,
    compute_backoff_seconds,
)


@dataclass
class VectorIndexResult:
    ok: bool
    status: str
    reason: str = ""
    category: str = ""
    retryable: bool = False
    vectors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    rate_limit_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reason": self.reason,
            "category": self.category,
            "retryable": self.retryable,
            "vectors": self.vectors,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "rate_limit_count": self.rate_limit_count,
        }


class VectorServiceV3:
    DENSE_VECTOR_NAME = "dense"
    VECTOR_SIZE = 1024

    def __init__(
        self,
        client: Optional[Any] = None,
        catalog: Optional[KnowledgeCatalog] = None,
        cohere_client: Optional[Any] = None,
        embedding_cache: Optional[EmbeddingCache] = None,
        sleep_fn: Optional[Any] = None,
    ):
        if client is None:
            db = QdrantDatabaseProvider()
            client = db.qdrant_client
        self.client = client
        self.catalog = catalog or KnowledgeCatalog()

        self.embedding_provider = Config.EMBEDDING_PROVIDER or "cohere"
        self.embedding_model = getattr(Config, "COHERE_EMBED_MODEL", "") or "embed-multilingual-v3.0"
        self.batch_size = max(1, int(Config.EMBEDDING_BATCH_SIZE or 32))
        self.request_timeout_seconds = max(1, int(Config.EMBEDDING_REQUEST_TIMEOUT_SECONDS or 90))
        self.max_retries = max(0, int(Config.EMBEDDING_MAX_RETRIES or 5))
        self.backoff_base_seconds = max(1, int(Config.EMBEDDING_BACKOFF_BASE_SECONDS or 10))
        self.backoff_max_seconds = max(1, int(Config.EMBEDDING_BACKOFF_MAX_SECONDS or 300))
        self.rate_limit_cooldown_seconds = max(1, int(Config.EMBEDDING_RATE_LIMIT_COOLDOWN_SECONDS or 600))
        self.circuit_breaker_failures = max(1, int(Config.EMBEDDING_CIRCUIT_BREAKER_FAILURES or 3))
        self.fail_fast_on_auth = bool(Config.EMBEDDING_FAIL_FAST_ON_AUTH)
        self.retry_jitter = bool(Config.EMBEDDING_RETRY_JITTER)
        self.sleep_fn = sleep_fn or time.sleep

        self.last_index_result: Dict[str, Any] = {}
        self._rate_limit_streak = 0
        self._cohere_api_key_present = bool(Config.COHERE_API_KEY)
        self.cohere_client = cohere_client if cohere_client is not None else self._build_cohere_client()
        self.embedding_cache = embedding_cache or self._build_embedding_cache()

    def _build_cohere_client(self) -> Optional[Any]:
        if self.embedding_provider != "cohere":
            return None
        if not Config.COHERE_API_KEY:
            return None
        import cohere

        return cohere.ClientV2(Config.COHERE_API_KEY)

    def _build_embedding_cache(self) -> Optional[EmbeddingCache]:
        if not Config.EMBEDDING_CACHE_ENABLED or Config.EMBEDDING_CACHE_BACKEND != "sqlite":
            return None
        return EmbeddingCache(Config.EMBEDDING_CACHE_PATH, enabled=True)

    def reconcile_index_jobs(self, timeout_seconds: float = 300, collection_name: str = "knowledge_current"):
        """
        Cleanup stale locks without deleting active vectors. Old vectors are kept
        unless a replacement index has completed successfully.
        """
        stale_jobs = self.catalog.get_stale_jobs(timeout_seconds)
        for job in stale_jobs:
            doc_id = job["doc_id"]
            job_id = job["job_id"]
            print(f"[Reconciliation] stale_index_job doc_id={doc_id} job_id={job_id}")
            try:
                self.catalog.release_index_lock(doc_id, job_id, "PENDING_RETRY", "Stale indexing lock; active vectors preserved.")
            except Exception as exc:
                print(f"[Reconciliation] status=failed doc_id={doc_id} reason={exc}")

    def _encode_dense(self, texts: List[str], input_type: str = "search_document") -> List[List[float]]:
        result = self._embed_texts_reliably(
            texts=texts,
            input_type=input_type,
            doc_id="search",
            fingerprint="",
            batch_label="1/1",
            log_document_start=False,
        )
        return result["vectors"]

    def delete_by_doc_id(self, doc_id: str, collection_name: str = "knowledge_current"):
        self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            wait=True,
        )

    def delete_by_doc_id_and_fingerprint(
        self,
        doc_id: str,
        ingestion_fingerprint: str,
        collection_name: str = "knowledge_current",
    ) -> None:
        if not ingestion_fingerprint:
            return
        self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="ingestion_fingerprint", match=MatchValue(value=ingestion_fingerprint)),
                ]
            ),
            wait=True,
        )

    def delete_obsolete_by_doc_id(
        self,
        doc_id: str,
        keep_fingerprint: str,
        collection_name: str = "knowledge_current",
    ) -> None:
        if not keep_fingerprint:
            return
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))],
                    must_not=[
                        FieldCondition(
                            key="ingestion_fingerprint",
                            match=MatchValue(value=keep_fingerprint),
                        )
                    ],
                ),
                wait=True,
            )
        except TypeError:
            print(f"[QdrantUpsert] doc_id={doc_id} status=warning reason=obsolete_cleanup_not_supported")

    def search(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 8,
        score_threshold: float = 0.7,
        collection_name: str = "knowledge_current",
    ) -> List[Dict[str, Any]]:
        if not self.client.collection_exists(collection_name):
            return []

        dense_vec = self._encode_dense([query], input_type="search_query")[0]
        query_filter = self._build_query_filter(filters)
        search_kwargs = {
            "collection_name": collection_name,
            "query_vector": (self.DENSE_VECTOR_NAME, dense_vec),
            "query_filter": query_filter,
            "limit": top_k,
            "with_payload": True,
        }
        if score_threshold is not None:
            search_kwargs["score_threshold"] = score_threshold

        try:
            hits = self.client.search(**search_kwargs)
        except TypeError:
            search_kwargs.pop("score_threshold", None)
            hits = self.client.search(**search_kwargs)

        results = []
        for hit in hits or []:
            payload = hit.payload or {}
            results.append(
                {
                    "content": payload.get("parent_text") or payload.get("text", ""),
                    "payload": payload,
                    "metadata": payload,
                    "score": float(getattr(hit, "score", 0.0) or 0.0),
                }
            )
        return results

    def _build_query_filter(self, filters: Dict[str, Any]):
        conditions = []
        for key, value in (filters or {}).items():
            if isinstance(value, list):
                if not value:
                    continue
                if MatchAny is not None:
                    conditions.append(FieldCondition(key=key, match=MatchAny(any=value)))
                else:
                    for item in value:
                        conditions.append(FieldCondition(key=key, match=MatchValue(value=item)))
            elif value is not None:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        return Filter(must=conditions) if conditions else None

    def upsert_document(
        self,
        doc_id: str,
        chunks: List[Dict[str, Any]],
        job_id: str,
        collection_name: str = "knowledge_current",
        ingestion_fingerprint: str = "",
        parser_type: str = "",
    ) -> bool:
        self.last_index_result = {}
        if not chunks:
            self.last_index_result = VectorIndexResult(False, "FAILED_NON_RETRYABLE", "empty_chunks").as_dict()
            return False

        fingerprint = ingestion_fingerprint or self._chunks_fingerprint(chunks)
        print(
            "[Embedding] "
            f"doc_id={doc_id} fingerprint={fingerprint} provider={self.embedding_provider} "
            f"model={self.embedding_model} chunks={len(chunks)} batch_size={self.batch_size} status=start"
        )
        started = time.perf_counter()

        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={self.DENSE_VECTOR_NAME: VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE)},
            )

        all_vectors: List[List[float]] = []
        all_chunk_ids: List[str] = []
        cache_hits = 0
        cache_misses = 0
        rate_limit_count = 0
        batches = [
            chunks[start : start + self.batch_size]
            for start in range(0, len(chunks), self.batch_size)
        ]

        try:
            for index, batch in enumerate(batches, start=1):
                self.catalog.heartbeat(job_id)
                batch_texts = [str(chunk.get("text", "")) for chunk in batch]
                batch_result = self._embed_texts_reliably(
                    texts=batch_texts,
                    input_type="search_document",
                    doc_id=doc_id,
                    fingerprint=fingerprint,
                    batch_label=f"{index}/{len(batches)}",
                )
                all_vectors.extend(batch_result["vectors"])
                cache_hits += int(batch_result.get("cache_hits", 0))
                cache_misses += int(batch_result.get("cache_misses", 0))
                rate_limit_count += int(batch_result.get("rate_limit_count", 0))
                all_chunk_ids.extend(str(chunk.get("chunk_id", "")) for chunk in batch)

            self._validate_vectors(chunks, all_vectors)
            points = [
                PointStruct(
                    id=self._point_id(doc_id, fingerprint, chunk),
                    vector={self.DENSE_VECTOR_NAME: all_vectors[index]},
                    payload=self._build_payload(doc_id, chunk, fingerprint, job_id, parser_type),
                )
                for index, chunk in enumerate(chunks)
            ]

            upsert_started = time.perf_counter()
            print(f"[QdrantUpsert] doc_id={doc_id} vectors={len(points)} fingerprint={fingerprint} status=start")
            response = self.client.upsert(collection_name=collection_name, points=points, wait=True)
            if response is False:
                raise RuntimeError("vector_upsert_false")
            response_status = str(getattr(response, "status", "") or "").lower()
            if response_status and not any(token in response_status for token in ("completed", "acknowledged")):
                raise RuntimeError(f"vector_upsert_status:{response_status}")
            latency_ms = round((time.perf_counter() - upsert_started) * 1000, 2)
            print(f"[QdrantUpsert] doc_id={doc_id} vectors={len(points)} status=ok latency_ms={latency_ms}")

            self.delete_obsolete_by_doc_id(doc_id, fingerprint, collection_name)
            chunk_ids_hash = hashlib.sha256(",".join(sorted(all_chunk_ids)).encode()).hexdigest()
            self.catalog.upsert_document(
                doc_id,
                {
                    "chunk_count": len(points),
                    "chunks_count": len(points),
                    "vectors_expected": len(points),
                    "chunk_ids_hash": chunk_ids_hash,
                    "last_indexed_at": str(time.time()),
                    "index_version": "v3",
                    "parser_type": parser_type,
                    "embedding_provider": self.embedding_provider,
                    "embedding_model": self.embedding_model,
                    "failed_stage": "",
                    "failure_category": "",
                    "failure_reason": "",
                    "retryable": 0,
                    "next_retry_after": 0,
                },
            )
            self.catalog.release_index_lock(doc_id, job_id, "INDEXED")
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            print(f"[Embedding] doc_id={doc_id} status=completed vectors={len(points)} latency_ms={latency_ms}")
            self.last_index_result = VectorIndexResult(
                True,
                "INDEXED",
                vectors=len(points),
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                rate_limit_count=rate_limit_count,
            ).as_dict()
            return True

        except (EmbeddingProviderError, EmbeddingCircuitOpen) as exc:
            info = exc.info
            retryable = bool(info.retryable)
            status = "PENDING_RETRY" if retryable else "FAILED_NON_RETRYABLE"
            cooldown = getattr(exc, "cooldown_seconds", None)
            reason = info.category
            if cooldown:
                reason = f"{info.category}; cooldown_seconds={cooldown}"
            print(
                "[Embedding] "
                f"doc_id={doc_id} status=failed category={info.category} "
                f"retryable={str(retryable).lower()} reason={info.error_tail}"
            )
            self.catalog.release_index_lock(doc_id, job_id, status, reason)
            self.last_index_result = VectorIndexResult(
                False,
                status,
                reason=reason,
                category=info.category,
                retryable=retryable,
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                rate_limit_count=rate_limit_count or (1 if info.category in {"rate_limited", "quota_exceeded"} else 0),
            ).as_dict()
            return False
        except Exception as exc:
            reason = str(exc)[:220]
            print(f"[QdrantUpsert] doc_id={doc_id} status=failed reason={reason} vectors={len(all_vectors)}")
            try:
                self.delete_by_doc_id_and_fingerprint(doc_id, fingerprint, collection_name)
            except Exception:
                pass
            self.catalog.release_index_lock(doc_id, job_id, "FAILED_UPSERT", reason)
            self.last_index_result = VectorIndexResult(
                False,
                "FAILED_UPSERT",
                reason=reason,
                category="provider_error",
                retryable=True,
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                rate_limit_count=rate_limit_count,
            ).as_dict()
            return False

    def _embed_texts_reliably(
        self,
        texts: List[str],
        input_type: str,
        doc_id: str,
        fingerprint: str,
        batch_label: str,
        log_document_start: bool = True,
    ) -> Dict[str, Any]:
        del fingerprint
        if not texts:
            return {"vectors": [], "cache_hits": 0, "cache_misses": 0, "rate_limit_count": 0}
        print(f"[Embedding] doc_id={doc_id} batch={batch_label} size={len(texts)} status=start")

        cached_vectors: List[Optional[List[float]]] = [None for _ in texts]
        cache_hits = 0
        cache_misses = len(texts)
        if self.embedding_cache is not None:
            cached_vectors, cache_hits, cache_misses = self.embedding_cache.get_many(
                self.embedding_provider,
                self.embedding_model,
                input_type,
                texts,
            )
            print(f"[EmbeddingCache] doc_id={doc_id} hits={cache_hits} misses={cache_misses}")

        missing_indexes = [index for index, vector in enumerate(cached_vectors) if vector is None]
        if not missing_indexes:
            print(f"[Embedding] doc_id={doc_id} batch={batch_label} status=ok latency_ms=0 cache_only=true")
            return {"vectors": [vector or [] for vector in cached_vectors], "cache_hits": cache_hits, "cache_misses": 0, "rate_limit_count": 0}

        if self.embedding_provider != "cohere":
            info = EmbeddingErrorInfo("provider_error", True, "UnsupportedEmbeddingProvider", self.embedding_provider)
            raise EmbeddingProviderError(info)
        if self.cohere_client is None:
            raise EmbeddingProviderError(classify_embedding_error(missing_key=True))

        missing_texts = [texts[index] for index in missing_indexes]
        attempt = 0
        rate_limit_count = 0
        while True:
            attempt += 1
            started = time.perf_counter()
            try:
                provider_vectors = self._call_cohere_embed(missing_texts, input_type)
                if len(provider_vectors) != len(missing_texts):
                    raise ValueError(f"embedding_count_mismatch expected={len(missing_texts)} actual={len(provider_vectors)}")
                if self.embedding_cache is not None:
                    self.embedding_cache.set_many(
                        self.embedding_provider,
                        self.embedding_model,
                        input_type,
                        missing_texts,
                        provider_vectors,
                    )
                    print(f"[EmbeddingCache] batch={batch_label} status=write_ok vectors={len(provider_vectors)}")
                for source_index, vector in zip(missing_indexes, provider_vectors):
                    cached_vectors[source_index] = vector
                self._rate_limit_streak = 0
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                print(f"[Embedding] doc_id={doc_id} batch={batch_label} status=ok latency_ms={latency_ms}")
                return {
                    "vectors": [vector or [] for vector in cached_vectors],
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "rate_limit_count": rate_limit_count,
                }
            except Exception as exc:
                info = classify_embedding_error(exc)
                if info.category in {"rate_limited", "quota_exceeded"}:
                    self._rate_limit_streak += 1
                    rate_limit_count += 1
                else:
                    self._rate_limit_streak = 0

                if self.fail_fast_on_auth and info.category in {"missing_api_key", "invalid_api_key"}:
                    raise EmbeddingProviderError(info)
                if not info.retryable or attempt > self.max_retries:
                    raise EmbeddingProviderError(info)
                if self._rate_limit_streak >= self.circuit_breaker_failures:
                    cooldown = int(info.retry_after or self.rate_limit_cooldown_seconds)
                    raise EmbeddingCircuitOpen(info, cooldown)

                sleep_seconds = compute_backoff_seconds(
                    attempt,
                    self.backoff_base_seconds,
                    self.backoff_max_seconds,
                    retry_after=info.retry_after,
                    jitter=self.retry_jitter,
                )
                print(
                    "[Embedding] "
                    f"doc_id={doc_id} batch={batch_label} status={info.category} "
                    f"retry={attempt} sleep_seconds={sleep_seconds}"
                )
                self.sleep_fn(sleep_seconds)

    def _call_cohere_embed(self, texts: List[str], input_type: str) -> List[List[float]]:
        kwargs = {
            "texts": texts,
            "model": self.embedding_model,
            "input_type": input_type,
            "embedding_types": ["float"],
        }
        try:
            response = self.cohere_client.embed(
                **kwargs,
                request_options={"timeout_in_seconds": self.request_timeout_seconds},
            )
        except TypeError:
            response = self.cohere_client.embed(**kwargs)
        vectors = getattr(getattr(response, "embeddings", None), "float", None)
        if vectors is None and isinstance(getattr(response, "embeddings", None), list):
            vectors = response.embeddings
        if vectors is None:
            raise ValueError("provider_bad_response: embeddings.float missing")
        return [list(vector) for vector in vectors]

    def _validate_vectors(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"vector_count_mismatch chunks={len(chunks)} vectors={len(vectors)}")
        dimensions = {len(vector) for vector in vectors if vector is not None}
        if not dimensions or 0 in dimensions:
            raise ValueError("vector_dimension_empty")
        if len(dimensions) != 1:
            raise ValueError(f"vector_dimension_inconsistent dimensions={sorted(dimensions)}")
        if self.VECTOR_SIZE not in dimensions:
            raise ValueError(f"vector_dimension_unexpected expected={self.VECTOR_SIZE} actual={sorted(dimensions)}")

    def _build_payload(
        self,
        doc_id: str,
        chunk: Dict[str, Any],
        ingestion_fingerprint: str,
        index_run_id: str,
        parser_type: str,
    ) -> Dict[str, Any]:
        rm = chunk.get("routing_metadata", {}) or {}
        document_metadata = chunk.get("document_metadata", {}) or {}
        lifecycle = document_metadata.get("lifecycle", "ACTIVE")
        payload = {
            "doc_id": doc_id,
            "ingestion_fingerprint": ingestion_fingerprint,
            "chunk_id": chunk.get("chunk_id", ""),
            "text": chunk.get("text", ""),
            "page": chunk.get("page"),
            "domain": rm.get("domain", ""),
            "subdomain": rm.get("subdomain", ""),
            "strategies": rm.get("strategies", []),
            "assets": rm.get("assets", []),
            "timeframe_focus": rm.get("timeframe_focus", []),
            "knowledge_type": rm.get("knowledge_type", ""),
            "source_tier": rm.get("source_tier", ""),
            "language": rm.get("language", "en"),
            "lifecycle": lifecycle,
            "document_metadata": document_metadata,
            "operational_metadata": chunk.get("operational_metadata", {}),
            "chunk_level": chunk.get("chunk_level", "chunk"),
            "parent_chunk_id": chunk.get("parent_chunk_id", ""),
            "parent_text": chunk.get("parent_text", ""),
            "parent_offset": chunk.get("parent_offset"),
            "chunk_policy_id": chunk.get("chunk_policy_id", ""),
            "char_count": chunk.get("char_count", 0),
            "token_count": chunk.get("token_count", 0),
            "section_title": chunk.get("section_title", ""),
            "chapter": chunk.get("chapter", ""),
            "location": chunk.get("location", ""),
            "spine_index": chunk.get("spine_index"),
            "href": chunk.get("href", ""),
            "index_run_id": index_run_id,
            "parser_type": parser_type,
            "embedding_model": self.embedding_model,
            "embedding_provider": self.embedding_provider,
        }
        for key in (
            "title",
            "author",
            "organization",
            "event_type",
            "period",
            "published_date",
            "document_type",
        ):
            if document_metadata.get(key):
                payload[key] = document_metadata.get(key)
        return payload

    def _point_id(self, doc_id: str, fingerprint: str, chunk: Dict[str, Any]) -> str:
        raw = f"{doc_id}:{fingerprint}:{chunk.get('chunk_id', '')}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

    def _chunks_fingerprint(self, chunks: List[Dict[str, Any]]) -> str:
        joined = "|".join(str(chunk.get("chunk_id", "")) for chunk in chunks)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
