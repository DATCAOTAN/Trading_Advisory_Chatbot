import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config import Config
from src.services.knowledge.query_intent import QueryFilterBuilder, QueryIntent, QueryIntentRouter


KNOWLEDGE_V3_COLLECTION = "knowledge_current"
LEGACY_COLLECTION = Config.VECTOR_COLLECTION_NAME


@dataclass
class RetrievalTrace:
    requested_v3: bool
    mode_used: str
    v3_succeeded: bool
    fallback_to_legacy: bool
    fallback_reason: str
    docs_returned: int
    collection: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "requested_v3": self.requested_v3,
            "mode_used": self.mode_used,
            "v3_succeeded": self.v3_succeeded,
            "fallback_to_legacy": self.fallback_to_legacy,
            "fallback_reason": self.fallback_reason,
            "docs_returned": self.docs_returned,
            "collection": self.collection,
        }


class RetrievalAdapter:
    """
    Stable retrieval facade for the active chatbot runtime.

    Default path remains legacy VectorService. Knowledge Platform V3 is loaded
    lazily only when explicitly requested by feature flag.
    """

    TECHNICAL_TERMS = {
        "indicator",
        "price action",
        "smc",
        "fvg",
        "order block",
        "ema",
        "sma",
        "rsi",
        "macd",
        "moving average",
        "moving averages",
        "technical analysis",
        "trading",
        "forex",
        "breakout",
        "support",
        "resistance",
        "trend",
        "candlestick",
        "candle",
    }
    TECHNICAL_SPECIFIC_TERMS = {
        "indicator",
        "price action",
        "smc",
        "fvg",
        "order block",
        "ema",
        "sma",
        "rsi",
        "macd",
        "moving average",
        "moving averages",
        "technical analysis",
        "support",
        "resistance",
        "candlestick",
        "candle",
    }
    STRATEGY_TERMS = {
        "strategy",
        "strategies",
        "trading strategy",
        "trading system",
        "systematic trading",
        "michael covel",
        "covel",
    }
    RISK_TERMS = {
        "risk",
        "position sizing",
        "drawdown",
        "stop loss",
        "take profit",
        "risk reward",
        "r:r",
        "lot size",
        "leverage",
    }
    MACRO_TERMS = {
        "macro",
        "cpi",
        "fomc",
        "fomc minutes",
        "fomc statement",
        "summary of economic projections",
        "sep",
        "interest rate",
        "rate cut",
        "inflation",
        "nfp",
        "nonfarm",
        "payroll",
        "employment",
        "fed",
        "ecb",
        "gdp",
        "unemployment",
    }
    MARKET_COMMODITY_TERMS = {
        "commodity markets outlook",
        "commodity outlook",
        "commodities",
        "commodity market",
        "commodity markets",
        "hang hoa",
        "hàng hóa",
        "hÃ ng hÃ³a",
    }
    MARKET_GOLD_TERMS = {
        "gold market commentary",
        "gold market report",
        "world gold council",
        "wgc",
    }
    GENERIC_GOLD_TERMS = {
        "vang",
        "vàng",
        "vÃ ng",
        "gold",
    }

    def __init__(
        self,
        legacy_service: Any,
        knowledge_service: Optional[Any] = None,
        fallback_to_legacy: Optional[bool] = None,
    ):
        self.legacy_service = legacy_service
        self.knowledge_service = knowledge_service
        self.fallback_to_legacy = fallback_to_legacy
        self.last_trace: Optional[RetrievalTrace] = None
        self.query_intent_router = QueryIntentRouter()
        self.query_filter_builder = QueryFilterBuilder()

    def retrieve(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 8,
        use_v3: bool = False,
        fallback_to_legacy: Optional[bool] = None,
        query_intent: Optional[QueryIntent] = None,
    ) -> List[Dict[str, Any]]:
        if not use_v3:
            docs = self._retrieve_legacy(query, top_k)
            self._set_trace(
                requested_v3=False,
                mode_used="legacy",
                v3_succeeded=False,
                fallback_to_legacy=False,
                fallback_reason="",
                docs_returned=len(docs),
                collection=LEGACY_COLLECTION,
            )
            return docs

        v3_filters = self._build_v3_filters(query, filters or {}, query_intent=query_intent)
        if not v3_filters.get("domain"):
            return self._fallback_or_empty(
                query,
                top_k,
                fallback_to_legacy,
                reason="missing_or_uninferable_domain",
            )

        try:
            docs = self._retrieve_v3(query, v3_filters, top_k, query_intent=query_intent)
            self._set_trace(
                requested_v3=True,
                mode_used="v3",
                v3_succeeded=True,
                fallback_to_legacy=False,
                fallback_reason="",
                docs_returned=len(docs),
                collection=KNOWLEDGE_V3_COLLECTION,
            )
            return docs
        except Exception as exc:
            return self._fallback_or_empty(
                query,
                top_k,
                fallback_to_legacy,
                reason=f"v3_error:{self._sanitize_reason(exc)}",
            )

    def _retrieve_legacy(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        return self.legacy_service.retrieve_candidates(query, top_k=top_k)

    def _retrieve_v3(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int,
        query_intent: Optional[QueryIntent] = None,
    ) -> List[Dict[str, Any]]:
        service = self._get_knowledge_service()
        SearchRequest = self._get_search_request_class()
        response = service.search(
            SearchRequest(
                query=query,
                routing_filters=filters,
                top_k=top_k,
                score_threshold=Config.KNOWLEDGE_V3_SCORE_THRESHOLD,
                query_intent=query_intent.as_dict() if query_intent is not None else None,
            )
        )
        return [self._v3_chunk_to_legacy_doc(chunk) for chunk in response.chunks]

    def _get_knowledge_service(self):
        if self.knowledge_service is None:
            from src.services.knowledge.knowledge_service import KnowledgeService

            self.knowledge_service = KnowledgeService()
        return self.knowledge_service

    def _get_search_request_class(self):
        from src.services.knowledge.knowledge_service import SearchRequest

        return SearchRequest

    def _fallback_or_empty(
        self,
        query: str,
        top_k: int,
        fallback_to_legacy: Optional[bool] = None,
        reason: str = "",
    ) -> List[Dict[str, Any]]:
        if self._fallback_enabled(fallback_to_legacy):
            docs = self._retrieve_legacy(query, top_k)
            self._set_trace(
                requested_v3=True,
                mode_used="legacy",
                v3_succeeded=False,
                fallback_to_legacy=True,
                fallback_reason=reason,
                docs_returned=len(docs),
                collection=LEGACY_COLLECTION,
            )
            return docs
        self._set_trace(
            requested_v3=True,
            mode_used="v3",
            v3_succeeded=False,
            fallback_to_legacy=False,
            fallback_reason=reason,
            docs_returned=0,
            collection=KNOWLEDGE_V3_COLLECTION,
        )
        return []

    def _fallback_enabled(self, fallback_to_legacy: Optional[bool] = None) -> bool:
        if fallback_to_legacy is not None:
            return fallback_to_legacy
        if self.fallback_to_legacy is not None:
            return self.fallback_to_legacy
        return Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY

    def _build_v3_filters(
        self,
        query: str,
        filters: Dict[str, Any],
        query_intent: Optional[QueryIntent] = None,
    ) -> Dict[str, Any]:
        routing_filters = {
            key: value
            for key, value in filters.items()
            if value is not None
        }
        if routing_filters.get("domain"):
            return routing_filters

        inferred_filters = self.infer_routing_filters(query, query_intent=query_intent)
        routing_filters.update(inferred_filters)
        return routing_filters

    def infer_domain(self, query: str) -> Optional[str]:
        return self.infer_routing_filters(query).get("domain")

    def infer_routing_filters(self, query: str, query_intent: Optional[QueryIntent] = None) -> Dict[str, str]:
        intent = query_intent or self.query_intent_router.route(query)
        filters = self.query_filter_builder.build(intent)
        if not filters.get("domain"):
            return {}
        return filters

    def _infer_strategy_filters(self, text: str) -> Dict[str, str]:
        has_trend_following = "trend following" in text or "trend-following" in text
        has_strategy_context = self._contains_any(text, self.STRATEGY_TERMS)
        has_technical_specific_term = self._contains_any(text, self.TECHNICAL_SPECIFIC_TERMS)

        if has_trend_following and (has_strategy_context or not has_technical_specific_term):
            return {"domain": "strategy", "subdomain": "trend_following"}

        if has_strategy_context and not has_technical_specific_term:
            return {"domain": "strategy"}

        return {}

    def _infer_market_filters(self, text: str, normalized_text: str) -> Dict[str, str]:
        if self._contains_any(text, self.MARKET_COMMODITY_TERMS) or self._contains_any(normalized_text, self.MARKET_COMMODITY_TERMS):
            return {"domain": "market", "subdomain": "commodities"}
        if self._contains_any(text, self.MARKET_GOLD_TERMS) or self._contains_any(normalized_text, self.MARKET_GOLD_TERMS):
            return {"domain": "market", "subdomain": "gold"}
        if (
            not self._has_macro_event_signal(text, normalized_text)
            and (
                self._contains_any(text, self.GENERIC_GOLD_TERMS)
                or self._contains_any(normalized_text, self.GENERIC_GOLD_TERMS)
            )
        ):
            return {"domain": "market", "subdomain": "gold"}
        return {}

    def _infer_macro_filters(self, text: str) -> Dict[str, str]:
        if "fomc" in text or "federal reserve" in text or "summary of economic projections" in text or "sep" in text:
            return {"domain": "macro", "subdomain": "central_bank"}
        if "cpi" in text or "inflation" in text or "lạm phát" in text:
            return {"domain": "macro", "subdomain": "inflation"}
        if "nfp" in text or "nonfarm" in text or "payroll" in text or "employment" in text:
            return {"domain": "macro", "subdomain": "employment"}
        if "gdp" in text:
            return {"domain": "macro", "subdomain": "gdp"}
        if "world economic outlook" in text or "global outlook" in text:
            return {"domain": "macro", "subdomain": "global_outlook"}
        return {}

    def _v3_chunk_to_legacy_doc(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        citation = chunk.get("citation", {}) or {}
        metadata = chunk.get("metadata", {}) or {}
        document_metadata = metadata.get("document_metadata", {}) or {}

        title = citation.get("title") or document_metadata.get("title", "")
        doc_id = citation.get("doc_id") or metadata.get("doc_id", "")

        return {
            "content": chunk.get("content", ""),
            "metadata": {
                "source": title or doc_id or "Knowledge V3",
                "doc_type": metadata.get("knowledge_type", "knowledge_v3"),
                "doc_id": doc_id,
                "chunk_id": citation.get("chunk_id") or metadata.get("chunk_id", ""),
                "title": title,
                "author": citation.get("author") or document_metadata.get("author", ""),
                "organization": citation.get("organization") or document_metadata.get("organization", ""),
                "page": citation.get("page"),
                "chapter": citation.get("chapter") or metadata.get("chapter", ""),
                "section": citation.get("section") or metadata.get("section_title", ""),
                "section_title": metadata.get("section_title", ""),
                "location": citation.get("location") or metadata.get("location", ""),
                "spine_index": citation.get("spine_index") or metadata.get("spine_index"),
                "href": citation.get("href") or metadata.get("href", ""),
                "source_tier": citation.get("source_tier") or metadata.get("source_tier", ""),
                "parent_chunk_id": metadata.get("parent_chunk_id", ""),
                "parent_id": metadata.get("parent_id", ""),
                "chunk_policy_id": metadata.get("chunk_policy_id", ""),
                "domain": metadata.get("domain", ""),
                "subdomain": metadata.get("subdomain", ""),
                "knowledge_type": metadata.get("knowledge_type", ""),
                "document_type": document_metadata.get("document_type", ""),
                "event_type": metadata.get("event_type") or document_metadata.get("event_type", ""),
                "published_date": metadata.get("published_date") or document_metadata.get("published_date", ""),
                "period": metadata.get("period") or document_metadata.get("period", ""),
                "country": metadata.get("country") or document_metadata.get("country", ""),
                "asset_focus": metadata.get("asset_focus") or document_metadata.get("asset_focus", ""),
                "retrieval_base_score": metadata.get("retrieval_base_score"),
                "retrieval_boost": metadata.get("retrieval_boost"),
                "retrieval_rank_score": metadata.get("retrieval_rank_score"),
                "retrieval_ranking_reasons": metadata.get("retrieval_ranking_reasons", []),
                "retrieval_ranking_penalties": metadata.get("retrieval_ranking_penalties", []),
                "retrieval_mode": "v3",
                "collection": KNOWLEDGE_V3_COLLECTION,
            },
            "score": float(chunk.get("score", 0.0) or 0.0),
        }

    def _set_trace(
        self,
        requested_v3: bool,
        mode_used: str,
        v3_succeeded: bool,
        fallback_to_legacy: bool,
        fallback_reason: str,
        docs_returned: int,
        collection: str,
    ) -> None:
        trace = RetrievalTrace(
            requested_v3=requested_v3,
            mode_used=mode_used,
            v3_succeeded=v3_succeeded,
            fallback_to_legacy=fallback_to_legacy,
            fallback_reason=fallback_reason,
            docs_returned=docs_returned,
            collection=collection,
        )
        self.last_trace = trace
        self._log_trace(trace)

    @staticmethod
    def _log_trace(trace: RetrievalTrace) -> None:
        print(
            "[RetrievalAdapter] "
            f"mode={trace.mode_used} "
            f"requested_v3={trace.requested_v3} "
            f"v3_succeeded={trace.v3_succeeded} "
            f"fallback_to_legacy={trace.fallback_to_legacy} "
            f"collection={trace.collection} "
            f"docs_returned={trace.docs_returned} "
            f"reason={trace.fallback_reason}"
        )

    @staticmethod
    def _sanitize_reason(exc: Exception) -> str:
        reason = str(exc).replace("\n", " ").replace("\r", " ").strip()
        return reason[:180]

    @staticmethod
    def _contains_any(text: str, terms: set) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _has_macro_event_signal(text: str, normalized_text: str) -> bool:
        macro_event_terms = {
            "cpi",
            "inflation",
            "lam phat",
            "fomc",
            "federal reserve",
            "summary of economic projections",
            "sep",
            "nfp",
            "nonfarm",
            "payroll",
            "employment",
            "gdp",
            "world economic outlook",
            "global outlook",
        }
        return any(term in text or term in normalized_text for term in macro_event_terms)

    @staticmethod
    def _normalize_query_text(query: str) -> str:
        text = str(query or "").lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
