import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.knowledge.query_intent import QueryFilterBuilder, QueryIntent, QueryIntentRouter


ROUTING_FILTER_KEYS = {
    "domain",
    "subdomain",
    "author",
    "organization",
    "event_type",
    "period",
    "strategies",
    "assets",
    "timeframe_focus",
    "knowledge_type",
    "source_tier",
    "language",
    "lifecycle",
}

FALLBACK_FILTER_LEVELS = [
    ("domain", "subdomain", "knowledge_type", "event_type", "period", "author", "organization", "strategies", "assets", "timeframe_focus"),
    ("domain", "subdomain", "strategies", "assets"),
    ("domain", "subdomain", "strategies"),
    ("domain", "subdomain"),
    ("domain",),
]

LIST_FILTER_KEYS = {
    "strategies",
    "assets",
    "timeframe_focus",
    "source_tier",
}


@dataclass
class SearchRequest:
    query: str
    routing_filters: Dict[str, Any]
    retrieval_mode: str = "hybrid"
    rerank: bool = True
    top_k: int = 8
    score_threshold: float = 0.7
    citation_required: bool = True
    allowed_source_tier: List[str] = field(
        default_factory=lambda: ["tier1", "tier2", "tier3"]
    )
    language: str = "en"
    query_intent: Optional[Any] = None


@dataclass
class SearchResponse:
    chunks: List[Dict[str, Any]]
    total_found: int
    fallback_level: int
    latency_ms: float
    query: str = ""
    filters_used: Dict[str, Any] = field(default_factory=dict)
    retrieval_mode: str = "hybrid"
    rerank: bool = True
    intent_type: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": self.chunks,
            "total_found": self.total_found,
            "fallback_level": self.fallback_level,
            "latency_ms": self.latency_ms,
            "query": self.query,
            "filters_used": self.filters_used,
            "retrieval_mode": self.retrieval_mode,
            "rerank": self.rerank,
            "intent_type": self.intent_type,
        }


class KnowledgeService:
    """
    Stable V3 search API for agents and future chatbot migration.

    Sprint 3 keeps retrieval vector-only under the hood. `retrieval_mode` and
    `rerank` remain part of the contract for future hybrid/rerank support.
    """

    VALID_RETRIEVAL_MODES = {"vector", "keyword", "hybrid"}

    def __init__(self, vector_service: Optional[Any] = None):
        if vector_service is None:
            from src.services.knowledge.vector_service import VectorServiceV3

            vector_service = VectorServiceV3()
        self.vector_service = vector_service
        self.query_intent_router = QueryIntentRouter()
        self.query_filter_builder = QueryFilterBuilder()

    def search(self, request: SearchRequest) -> SearchResponse:
        if isinstance(request, dict):
            request = SearchRequest(**request)

        self._validate_request(request)
        start = time.perf_counter()

        query_intent = self._query_intent_for_request(request)
        self._log_query_intent(request.query, query_intent)
        self._log_query_expansion(request.query, query_intent)

        base_filters = self.build_filters(request, query_intent=query_intent)
        last_filters: Dict[str, Any] = {}
        final_chunks: List[Dict[str, Any]] = []
        final_level = 0

        for fallback_level, relaxed_filters in self._iter_fallback_filters(base_filters):
            print(
                "[RetrievalFilter] "
                f"query={request.query!r} "
                f"fallback_level={fallback_level} "
                f"filters={relaxed_filters}"
            )
            raw_chunks = self.vector_service.search(
                query=request.query,
                filters=relaxed_filters,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            )
            final_chunks = self._normalize_search_results(raw_chunks, request, query_intent=query_intent)
            last_filters = relaxed_filters
            final_level = fallback_level
            if final_chunks:
                break

        latency_ms = (time.perf_counter() - start) * 1000
        response = SearchResponse(
            chunks=final_chunks,
            total_found=len(final_chunks),
            fallback_level=final_level,
            latency_ms=latency_ms,
            query=request.query,
            filters_used=last_filters,
            retrieval_mode=request.retrieval_mode,
            rerank=request.rerank,
            intent_type=query_intent.intent_type,
        )
        self._log_search_response(response)
        return response

    def build_filters(self, request: SearchRequest, query_intent: Optional[QueryIntent] = None) -> Dict[str, Any]:
        normalized = self._normalize_routing_filters(request.routing_filters)
        domain = normalized.get("domain")
        if not domain:
            raise ValueError("SearchRequest.routing_filters.domain is required; global scan is disabled.")

        if query_intent is not None:
            filters = self.query_filter_builder.build(query_intent, explicit_filters=normalized)
        else:
            filters = dict(normalized)
        filters["source_tier"] = self._normalize_list(request.allowed_source_tier, key="source_tier")

        language = self._normalize_scalar(request.language, key="language")
        if language not in {"all", "*"}:
            filters["language"] = language

        filters["lifecycle"] = "ACTIVE"
        return {key: value for key, value in filters.items() if self._has_value(value)}

    def _validate_request(self, request: SearchRequest) -> None:
        if not request.query or not request.query.strip():
            raise ValueError("SearchRequest.query is required.")
        if request.retrieval_mode not in self.VALID_RETRIEVAL_MODES:
            raise ValueError(f"Unsupported retrieval_mode: {request.retrieval_mode}")
        if request.top_k <= 0:
            raise ValueError("SearchRequest.top_k must be greater than zero.")

    def _iter_fallback_filters(self, filters: Dict[str, Any]):
        guardrail_keys = {"knowledge_type", "source_tier", "language", "lifecycle"}
        for level, keys in enumerate(FALLBACK_FILTER_LEVELS):
            keep = set(keys) | guardrail_keys
            relaxed = {
                key: value
                for key, value in filters.items()
                if key in keep and self._has_value(value)
            }
            if "domain" not in relaxed:
                raise ValueError("Fallback filters attempted to remove domain; global scan is disabled.")
            yield level, relaxed

    def _normalize_routing_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in (filters or {}).items():
            if key not in ROUTING_FILTER_KEYS:
                continue
            if key in LIST_FILTER_KEYS:
                normalized[key] = self._normalize_list(value, key=key)
            else:
                normalized[key] = self._normalize_scalar(value, key=key)
        return {key: value for key, value in normalized.items() if self._has_value(value)}

    def _normalize_scalar(self, value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if key == "lifecycle":
                return value.upper()
            if key == "event_type":
                return value.upper()
            if key in {"domain", "subdomain", "strategies", "timeframe_focus", "knowledge_type", "source_tier", "language"}:
                return value.lower()
            return value
        return value

    def _normalize_list(self, value: Any, key: str) -> List[Any]:
        values = value if isinstance(value, list) else [value]
        normalized = []
        seen = set()
        for item in values:
            item = self._normalize_scalar(item, key=key)
            if not self._has_value(item) or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    def _normalize_search_results(
        self,
        raw_chunks: List[Dict[str, Any]],
        request: SearchRequest,
        query_intent: Optional[QueryIntent] = None,
    ) -> List[Dict[str, Any]]:
        chunks = []
        for raw in raw_chunks or []:
            item = self._build_chunk_item(raw)
            if not self._is_allowed_chunk(item, request):
                continue
            chunks.append(item)
        deduped = self._dedupe_search_results(chunks)
        ranked = self._rank_search_results(deduped, request, query_intent=query_intent)
        return ranked[: request.top_k]

    def _build_chunk_item(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        payload = raw.get("payload") or raw.get("metadata") or raw
        document_metadata = payload.get("document_metadata", {}) or {}

        content = raw.get("content") or payload.get("text") or raw.get("text") or ""
        source_tier = payload.get("source_tier") or document_metadata.get("source_tier", "")

        citation = {
            "doc_id": payload.get("doc_id") or document_metadata.get("doc_id", ""),
            "chunk_id": payload.get("chunk_id") or document_metadata.get("chunk_id", ""),
            "title": document_metadata.get("title", payload.get("title", "")),
            "author": document_metadata.get("author", payload.get("author", "")),
            "organization": document_metadata.get("organization", payload.get("organization", "")),
            "page": payload.get("page") or document_metadata.get("page_number"),
            "chapter": payload.get("chapter", ""),
            "section": payload.get("section_title", ""),
            "location": payload.get("location", ""),
            "spine_index": payload.get("spine_index"),
            "href": payload.get("href", ""),
            "source_tier": source_tier,
        }

        metadata = dict(payload)
        metadata.setdefault("document_metadata", document_metadata)
        for key in [
            "author",
            "organization",
            "event_type",
            "published_date",
            "period",
            "country",
            "asset_focus",
            "document_type",
        ]:
            if document_metadata.get(key) and not metadata.get(key):
                metadata[key] = document_metadata[key]

        return {
            "content": content,
            "citation": citation,
            "score": float(raw.get("score", payload.get("score", 0.0)) or 0.0),
            "metadata": metadata,
        }

    def _dedupe_search_results(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped = []
        seen = set()
        for chunk in chunks:
            metadata = chunk.get("metadata", {}) or {}
            citation = chunk.get("citation", {}) or {}
            dedupe_key = (
                metadata.get("parent_chunk_id")
                or citation.get("chunk_id")
                or metadata.get("chunk_id")
            )
            if dedupe_key and dedupe_key in seen:
                continue
            if dedupe_key:
                seen.add(dedupe_key)
            deduped.append(chunk)
        return deduped

    def _rank_search_results(
        self,
        chunks: List[Dict[str, Any]],
        request: SearchRequest,
        query_intent: Optional[QueryIntent] = None,
    ) -> List[Dict[str, Any]]:
        query = self._normalize_match_text(request.query)
        ranked = []
        for chunk in chunks:
            boost, reasons, penalties = self._metadata_boost(
                chunk,
                query,
                request.routing_filters,
                query_intent=query_intent,
            )
            base_score = float(chunk.get("score", 0.0) or 0.0)
            rank_score = base_score + boost
            metadata = chunk.setdefault("metadata", {})
            metadata["retrieval_base_score"] = base_score
            metadata["retrieval_boost"] = round(boost, 6)
            metadata["retrieval_rank_score"] = round(rank_score, 6)
            metadata["retrieval_ranking_reasons"] = list(reasons)
            metadata["retrieval_ranking_penalties"] = list(penalties)
            ranked.append((rank_score, chunk))
            if boost != 0:
                citation = chunk.get("citation", {}) or {}
                print(
                    "[RetrievalRanking] "
                    f"query={request.query!r} boost={boost:.3f} "
                    f"title={citation.get('title', '')!r} "
                    f"reasons={','.join(reasons)} "
                    f"penalties={','.join(penalties)}"
                )
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in ranked]

    def _metadata_boost(
        self,
        chunk: Dict[str, Any],
        query: str,
        routing_filters: Dict[str, Any],
        query_intent: Optional[QueryIntent] = None,
    ) -> tuple[float, List[str], List[str]]:
        metadata = chunk.get("metadata", {}) or {}
        citation = chunk.get("citation", {}) or {}
        document_metadata = metadata.get("document_metadata", {}) or {}
        title = self._normalize_match_text(
            citation.get("title") or document_metadata.get("title") or metadata.get("title", "")
        )
        author = self._normalize_match_text(
            citation.get("author") or document_metadata.get("author") or metadata.get("author", "")
        )
        organization = self._normalize_match_text(
            citation.get("organization")
            or document_metadata.get("organization")
            or metadata.get("organization", "")
        )
        event_type = self._normalize_match_text(document_metadata.get("event_type", "") or metadata.get("event_type", ""))
        period = self._normalize_match_text(document_metadata.get("period", "") or metadata.get("period", ""))
        knowledge_type = self._normalize_match_text(metadata.get("knowledge_type", ""))
        source_tier = self._normalize_match_text(metadata.get("source_tier", "") or citation.get("source_tier", ""))
        domain = self._normalize_match_text(metadata.get("domain", ""))
        subdomain = self._normalize_match_text(metadata.get("subdomain", ""))

        boost = 0.0
        reasons: List[str] = []
        penalties: List[str] = []
        title_tokens = self._significant_tokens(title)
        query_tokens = self._significant_tokens(query)
        title_overlap = title_tokens & query_tokens
        if title and title in query:
            boost += 0.35
            reasons.append("title_phrase")
        elif title_tokens and title_overlap:
            overlap_ratio = len(title_overlap) / max(len(title_tokens), 1)
            if overlap_ratio >= 0.5:
                boost += 0.20
                reasons.append("title_tokens")

        if author and author in query:
            boost += 0.18
            reasons.append("author")
        if organization and organization in query:
            boost += 0.18
            reasons.append("organization")
        if event_type and self._event_type_matches_query(event_type, query):
            boost += 0.20
            reasons.append("event_type")
        if period and period in query:
            boost += 0.08
            reasons.append("period")
        if subdomain and subdomain.replace("_", " ") in query:
            boost += 0.22
            reasons.append("subdomain")
        if domain and domain == self._normalize_match_text((routing_filters or {}).get("domain", "")):
            boost += 0.04
            reasons.append("domain_filter")
        if subdomain and subdomain == self._normalize_match_text((routing_filters or {}).get("subdomain", "")):
            boost += 0.08
            reasons.append("subdomain_filter")
        if knowledge_type == "report" and source_tier == "tier1":
            boost += 0.08
            reasons.append("official_report")

        if query_intent is not None:
            intent_domains = {self._normalize_match_text(value) for value in query_intent.domain_candidates}
            intent_subdomains = {self._normalize_match_text(value) for value in query_intent.subdomain_candidates}
            intent_authors = {self._normalize_match_text(value) for value in query_intent.preferred_authors}
            intent_orgs = {self._normalize_match_text(value) for value in query_intent.preferred_organizations}
            intent_events = {
                self._normalize_match_text(value).replace("_", " ")
                for value in query_intent.event_type_candidates
            }
            intent_periods = {self._normalize_match_text(value) for value in query_intent.period_candidates}

            if domain and domain in intent_domains:
                boost += 0.20
                reasons.append("intent_domain")
            elif intent_domains and domain:
                boost -= 0.25
                penalties.append("wrong_domain")

            if subdomain and subdomain in intent_subdomains:
                boost += 0.20
                reasons.append("intent_subdomain")
            elif intent_subdomains and subdomain:
                boost -= 0.15
                penalties.append("wrong_subdomain")

            if author and author in intent_authors:
                boost += 0.25
                reasons.append("intent_author")
            if organization and organization in intent_orgs:
                boost += 0.25
                reasons.append("intent_organization")
            if event_type and event_type.replace("_", " ") in intent_events:
                boost += 0.20
                reasons.append("intent_event_type")
            if period and period in intent_periods:
                boost += 0.15
                reasons.append("intent_period")
            if (
                query_intent.source_preference in {"official_report_first", "mixed_report_and_book"}
                and knowledge_type == "report"
                and source_tier == "tier1"
            ):
                boost += 0.25
                reasons.append("intent_official_report")
            if query_intent.source_preference == "book_first" and knowledge_type == "book":
                boost += 0.12
                reasons.append("intent_book")
            if source_tier == "tier1":
                boost += 0.10
                reasons.append("tier1")
            if not domain or not subdomain:
                boost -= 0.05
                penalties.append("weak_metadata")
            if self._normalize_match_text(metadata.get("lifecycle", "ACTIVE")) != "active":
                boost -= 0.30
                penalties.append("inactive_lifecycle")

        return max(min(boost, 1.25), -0.50), reasons, penalties

    def _is_allowed_chunk(self, item: Dict[str, Any], request: SearchRequest) -> bool:
        metadata = item.get("metadata", {})
        citation = item.get("citation", {})
        allowed_tiers = set(self._normalize_list(request.allowed_source_tier, key="source_tier"))

        source_tier = self._normalize_scalar(
            metadata.get("source_tier") or citation.get("source_tier"),
            key="source_tier",
        )
        if not source_tier or source_tier not in allowed_tiers:
            return False

        lifecycle = self._normalize_scalar(metadata.get("lifecycle", "ACTIVE"), key="lifecycle")
        if lifecycle != "ACTIVE":
            return False

        language = self._normalize_scalar(metadata.get("language", request.language), key="language")
        request_language = self._normalize_scalar(request.language, key="language")
        if request_language not in {"all", "*"} and language != request_language:
            return False

        index_status = metadata.get("index_status") or metadata.get("document_metadata", {}).get("index_status")
        if index_status and index_status != "INDEXED":
            return False

        return True

    def _query_intent_for_request(self, request: SearchRequest) -> QueryIntent:
        if isinstance(request.query_intent, QueryIntent):
            return request.query_intent
        if isinstance(request.query_intent, dict):
            return QueryIntent.from_dict(request.query_intent)
        return self.query_intent_router.route(request.query)

    def _log_search_response(self, response: SearchResponse) -> None:
        print(
            "[KnowledgeService] "
            f"query={response.query!r} "
            f"intent_type={response.intent_type} "
            f"filters={response.filters_used} "
            f"fallback_level={response.fallback_level} "
            f"latency_ms={response.latency_ms:.2f} "
            f"total_found={response.total_found}"
        )

    @staticmethod
    def _log_query_intent(query: str, intent: QueryIntent) -> None:
        print(
            "[QueryRouter] "
            f"query={query!r} "
            f"intent_type={intent.intent_type} "
            f"confidence={intent.confidence:.2f} "
            f"domains={intent.domain_candidates} "
            f"subdomains={intent.subdomain_candidates} "
            f"source_preference={intent.source_preference} "
            f"reason={intent.routing_reason}"
        )

    @staticmethod
    def _log_query_expansion(query: str, intent: QueryIntent) -> None:
        if intent.expanded_terms:
            print(
                "[QueryExpansion] "
                f"original={query!r} "
                f"expanded_terms={intent.expanded_terms}"
            )

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value)
        return True

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", " ")
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @classmethod
    def _significant_tokens(cls, value: str) -> set[str]:
        stopwords = {
            "the",
            "and",
            "of",
            "to",
            "a",
            "an",
            "in",
            "for",
            "is",
            "la",
            "là",
            "gi",
            "gì",
        }
        tokens = {
            token.strip(".,:;!?()[]{}\"'")
            for token in cls._normalize_match_text(value).split()
        }
        return {token for token in tokens if len(token) > 2 and token not in stopwords}

    @staticmethod
    def _event_type_matches_query(event_type: str, query: str) -> bool:
        normalized = event_type.replace("_", " ")
        aliases = {
            "fomc": ["fomc", "federal reserve", "fed"],
            "fomc minutes": ["fomc minutes", "minutes", "federal reserve"],
            "cpi": ["cpi", "inflation"],
            "nfp": ["nfp", "nonfarm", "payroll", "employment"],
            "employment": ["employment", "jobs", "payroll"],
            "gdp": ["gdp", "growth", "tăng trưởng"],
            "global outlook": ["world economic outlook", "global outlook", "tăng trưởng toàn cầu"],
            "commodity markets": ["commodity markets", "commodities", "hàng hóa"],
            "gold market": ["gold market", "gold", "vàng"],
            "sep": ["sep", "summary of economic projections", "economic projections"],
        }
        if normalized and normalized in query:
            return True
        for alias in aliases.get(normalized, []):
            if alias in query:
                return True
        return False
