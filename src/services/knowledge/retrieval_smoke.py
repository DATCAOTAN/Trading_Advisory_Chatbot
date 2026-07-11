from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.services.knowledge.embedding_reliability import classify_embedding_error


class RetrievalSmokeStatus:
    PASS = "RETRIEVAL_SMOKE_PASS"
    FAIL = "RETRIEVAL_SMOKE_FAIL"
    SKIPPED = "RETRIEVAL_SMOKE_SKIPPED"


@dataclass
class RetrievalSmokeResult:
    status: str
    reason: str = ""
    query: str = ""
    top_source_title: str = ""
    top_source_author: str = ""
    top_source_organization: str = ""
    top_source_domain: str = ""
    top_source_subdomain: str = ""
    top_source_event_type: str = ""
    top_source_period: str = ""
    top_k_returned: int = 0
    latency_ms: float = 0.0


class RetrievalSmokeEvaluator:
    """Run a post-index V3 retrieval smoke check without calling an LLM."""

    def __init__(self, search_service: Optional[Any] = None, top_k: int = 5, enabled: bool = True):
        self.search_service = search_service
        self.top_k = top_k
        self.enabled = enabled

    def evaluate_document(self, doc_id: str, metadata: Dict[str, Any]) -> RetrievalSmokeResult:
        if not self.enabled:
            return RetrievalSmokeResult(
                status=RetrievalSmokeStatus.SKIPPED,
                reason="retrieval smoke disabled",
            )
        if not doc_id:
            return RetrievalSmokeResult(
                status=RetrievalSmokeStatus.SKIPPED,
                reason="missing doc_id",
            )

        routing_metadata = metadata.get("routing_metadata", {}) or {}
        document_metadata = metadata.get("document_metadata", {}) or {}
        domain = routing_metadata.get("domain", "")
        if not domain:
            return RetrievalSmokeResult(
                status=RetrievalSmokeStatus.SKIPPED,
                reason="missing domain",
            )

        query = self._build_query(routing_metadata, document_metadata)
        try:
            response = self._get_search_service().search(self._build_request(query, routing_metadata))
            chunks = list(getattr(response, "chunks", []) or [])
            top = chunks[0] if chunks else {}
            top_info = self._source_info(top)
            found = any(self._matches_doc(chunk, doc_id, document_metadata) for chunk in chunks)
            status = RetrievalSmokeStatus.PASS if found else RetrievalSmokeStatus.FAIL
            reason = "" if found else "expected document missing from top-k"
            result = RetrievalSmokeResult(
                status=status,
                reason=reason,
                query=query,
                top_source_title=top_info["title"],
                top_source_author=top_info["author"],
                top_source_organization=top_info["organization"],
                top_source_domain=top_info["domain"],
                top_source_subdomain=top_info["subdomain"],
                top_source_event_type=top_info["event_type"],
                top_source_period=top_info["period"],
                top_k_returned=len(chunks),
                latency_ms=float(getattr(response, "latency_ms", 0.0) or 0.0),
            )
            print(
                "[RetrievalSmoke] "
                f"doc_id={doc_id} status={result.status} query={query!r} "
                f"top_title={result.top_source_title!r} top_author={result.top_source_author!r} "
                f"returned={result.top_k_returned}"
            )
            return result
        except Exception as exc:
            error_info = classify_embedding_error(exc)
            reason = str(exc)[:180]
            retryable = error_info.retryable
            if error_info.category in {"rate_limited", "quota_exceeded"}:
                reason = "embedding_rate_limited"
            result = RetrievalSmokeResult(
                status=RetrievalSmokeStatus.SKIPPED,
                reason=reason,
                query=query,
            )
            print(
                f"[RetrievalSmoke] doc_id={doc_id} status={result.status} "
                f"reason={result.reason} retryable={str(retryable).lower()}"
            )
            return result

    def _get_search_service(self) -> Any:
        if self.search_service is None:
            from src.services.knowledge.knowledge_service import KnowledgeService

            self.search_service = KnowledgeService()
        return self.search_service

    def _build_request(self, query: str, routing_metadata: Dict[str, Any]) -> Any:
        from src.services.knowledge.knowledge_service import SearchRequest

        routing_filters = {"domain": routing_metadata.get("domain", "")}
        if routing_metadata.get("subdomain"):
            routing_filters["subdomain"] = routing_metadata["subdomain"]
        return SearchRequest(
            query=query,
            routing_filters=routing_filters,
            top_k=self.top_k,
            score_threshold=0.0,
        )

    @staticmethod
    def _build_query(routing_metadata: Dict[str, Any], document_metadata: Dict[str, Any]) -> str:
        title = document_metadata.get("title", "")
        author = document_metadata.get("author", "")
        organization = document_metadata.get("organization", "")
        event_type = document_metadata.get("event_type", "")
        period = document_metadata.get("period", "")
        subdomain = routing_metadata.get("subdomain", "")
        query = " ".join(part for part in [subdomain, title, organization or author, event_type, period] if part).strip()
        return query or document_metadata.get("doc_id", "") or "knowledge document"

    @staticmethod
    def _matches_doc(chunk: Dict[str, Any], doc_id: str, document_metadata: Dict[str, Any]) -> bool:
        citation = chunk.get("citation", {}) or {}
        metadata = chunk.get("metadata", {}) or {}
        chunk_document = metadata.get("document_metadata", {}) or {}
        expected_title = str(document_metadata.get("title", "")).lower()
        expected_author = str(document_metadata.get("author", "")).lower()
        expected_organization = str(document_metadata.get("organization", "")).lower()

        if citation.get("doc_id") == doc_id or metadata.get("doc_id") == doc_id:
            return True

        actual_title = str(citation.get("title") or chunk_document.get("title", "")).lower()
        actual_author = str(citation.get("author") or chunk_document.get("author", "")).lower()
        actual_organization = str(citation.get("organization") or chunk_document.get("organization", "")).lower()
        return bool(
            expected_title
            and (expected_author or expected_organization)
            and expected_title in actual_title
            and (
                expected_author in actual_author
                or expected_organization in actual_organization
                or expected_organization in actual_author
            )
        )

    @staticmethod
    def _source_info(chunk: Dict[str, Any]) -> Dict[str, str]:
        citation = chunk.get("citation", {}) or {}
        metadata = chunk.get("metadata", {}) or {}
        document_metadata = metadata.get("document_metadata", {}) or {}
        return {
            "title": citation.get("title") or document_metadata.get("title", "") or metadata.get("title", ""),
            "author": citation.get("author") or document_metadata.get("author", "") or metadata.get("author", ""),
            "organization": citation.get("organization") or document_metadata.get("organization", "") or metadata.get("organization", ""),
            "domain": metadata.get("domain", ""),
            "subdomain": metadata.get("subdomain", ""),
            "event_type": metadata.get("event_type") or document_metadata.get("event_type", ""),
            "period": metadata.get("period") or document_metadata.get("period", ""),
        }
