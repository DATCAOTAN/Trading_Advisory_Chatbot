import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import cohere

from src.config import Config
from src.pipelines.context_packer import ContextPacker


class RerankerModule:
    """Rerank and pack retrieved documents."""

    def __init__(self):
        self.cohere_client = cohere.Client(api_key=Config.COHERE_API_KEY)
        self.context_packer = ContextPacker()

    def process(
        self,
        query: str,
        raw_documents: List[Dict],
        top_k: int = 3,
        enabled: Optional[bool] = None,
        query_intent: Optional[Any] = None,
        is_refinement: bool = False,
    ) -> Tuple[str, List[Dict]]:
        is_enabled = enabled if enabled is not None else Config.ENABLE_RERANKER
        if is_refinement:
            top_k = max(top_k, 6)
        if not hasattr(self, "context_packer"):
            self.context_packer = ContextPacker()

        if not is_enabled or not raw_documents:
            best_docs, stats = self.context_packer.pack(raw_documents, max_sources=top_k)
            print(f"[ContextPacker] Packed {stats.output_docs}/{stats.input_docs} docs (max_sources={top_k})")
            context_str = self.context_packer.render_context(best_docs, include_scores=False)
            return context_str, best_docs

        print("[RerankerModule] Starting Cohere rerank...")
        start_t = time.time()
        docs_text = [d["content"] for d in raw_documents]

        try:
            response = self.cohere_client.rerank(
                model="rerank-multilingual-v3.0",
                query=query,
                documents=docs_text,
                top_n=len(raw_documents),
                return_documents=True,
            )

            scored_docs = []
            threshold = 0.01 if is_refinement else 0.1
            for result in response.results:
                orig_doc = raw_documents[result.index]
                if result.relevance_score < threshold:
                    continue
                orig_doc["score"] = result.relevance_score
                scored_docs.append(orig_doc)

            if not scored_docs and response.results:
                result = response.results[0]
                orig_doc = raw_documents[result.index]
                orig_doc["score"] = result.relevance_score
                scored_docs.append(orig_doc)

            scored_docs = self._anchor_authoritative_reports(query, scored_docs, raw_documents, query_intent)
            best_docs, stats = self.context_packer.pack(scored_docs, max_sources=top_k)
            print(f"[ContextPacker] Packed {stats.output_docs}/{stats.input_docs} docs (max_sources={top_k}) after Rerank")
            print(f"[RerankerModule] Done ({time.time() - start_t:.2f}s)")
            context_str = self.context_packer.render_context(best_docs, include_scores=True)
            return context_str, best_docs

        except Exception as exc:
            print(f"[RerankerModule] API error: {exc} -> fallback top {top_k}.")
            best_docs, stats = self.context_packer.pack(raw_documents, max_sources=top_k)
            print(f"[ContextPacker] Packed {stats.output_docs}/{stats.input_docs} docs (max_sources={top_k}) fallback")
            context_str = self.context_packer.render_context(best_docs, include_scores=False)
            return context_str, best_docs

    def _anchor_authoritative_reports(
        self,
        query: str,
        selected: List[Dict],
        candidates: List[Dict],
        query_intent: Optional[Any] = None,
    ) -> List[Dict]:
        """Keep one explicitly indicated tier-1 report in context.

        Cross-encoder rerankers can occasionally prefer a broad background book
        over an official report chunk. When the query or canonical intent points
        to an official/report source, preserve one compatible report candidate
        without increasing candidate pools or top_k.
        """
        indicated_reports = [
            doc for doc in candidates or []
            if self._is_authoritative_report(doc) and self._report_is_indicated(query, doc, query_intent)
        ]
        if not indicated_reports:
            return selected

        anchor = max(indicated_reports, key=lambda doc: self._report_anchor_score(query, doc))
        output: List[Dict] = []
        seen = set()
        for doc in [anchor] + list(selected or []):
            key = self._doc_context_key(doc)
            if key in seen:
                continue
            seen.add(key)
            output.append(doc)
        return output

    def _report_is_indicated(self, query: str, doc: Dict, query_intent: Optional[Any]) -> bool:
        source_preference = str(getattr(query_intent, "source_preference", "") or "")
        if source_preference in {"official_report_first", "mixed_report_and_book"}:
            return True

        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        query_tokens = self._tokens(query)
        if not query_tokens:
            return False

        title_tokens = self._tokens(metadata.get("title", ""))
        event_tokens = self._tokens(metadata.get("event_type", ""))
        organization_tokens = self._tokens(metadata.get("organization", ""))
        domain_tokens = self._tokens(" ".join(str(metadata.get(k, "")) for k in ("domain", "subdomain")))

        if event_tokens and query_tokens & event_tokens:
            return True
        if organization_tokens and len(query_tokens & organization_tokens) >= 1:
            return True
        if title_tokens and len(query_tokens & title_tokens) >= min(2, len(title_tokens)):
            return True
        if title_tokens and domain_tokens and (query_tokens & title_tokens) and (query_tokens & domain_tokens):
            return True
        return False

    def _report_anchor_score(self, query: str, doc: Dict) -> float:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        query_tokens = self._tokens(query)
        score = float(doc.get("retrieval_rank_score", doc.get("score", 0.0)) or 0.0)
        for field, weight in (
            ("event_type", 1.2),
            ("title", 0.8),
            ("organization", 0.5),
            ("subdomain", 0.3),
            ("domain", 0.2),
        ):
            overlap = query_tokens & self._tokens(metadata.get(field, ""))
            score += weight * len(overlap)
        return score

    @staticmethod
    def _is_authoritative_report(doc: Dict) -> bool:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        return (
            str(metadata.get("knowledge_type", "")).lower() == "report"
            and str(metadata.get("source_tier", "")).lower() == "tier1"
        )

    @staticmethod
    def _doc_context_key(doc: Dict) -> str:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        return str(
            metadata.get("parent_chunk_id")
            or metadata.get("chunk_id")
            or doc.get("parent_chunk_id")
            or doc.get("chunk_id")
            or doc.get("content", "")
        )

    @staticmethod
    def _tokens(value: Any) -> set:
        text = str(value or "").lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 1}

    def _apply_report_section_targeting(self, query: str, selected: List[Dict], candidates: List[Dict]) -> List[Dict]:
        """Rank report chunks toward substantive headline/component sections.

        This helper is side-effect free. It does not change the main rerank
        runtime flow unless called explicitly.
        """
        docs = []
        seen = set()
        for doc in list(selected or []) + list(candidates or []):
            meta = doc.get("metadata", {}) if isinstance(doc, dict) else {}
            key = meta.get("chunk_id") or meta.get("parent_chunk_id") or doc.get("content", "")
            if key in seen:
                continue
            seen.add(key)
            docs.append(doc)
        return sorted(docs, key=lambda doc: self._report_section_score(query, doc), reverse=True)

    def _report_section_score(self, query: str, doc: Dict) -> float:
        text = f"{doc.get('content', '')} {doc.get('metadata', {})}".lower()
        query_text = str(query or "").lower()
        score = float(doc.get("score", 0.0) or 0.0)
        positive_terms = (
            "rose", "increased", "decreased", "changed little", "headline",
            "all items", "core cpi", "less food and energy", "components",
            "contributed", "total nonfarm payroll", "unemployment rate",
            "average hourly earnings", "job gains", "revisions",
        )
        negative_terms = (
            "methodology", "sample", "collection", "index calculation",
            "civilian noninstitutional population", "employment-population ratio",
            "by race", "adult men", "adult women", "technical note",
        )
        score += 0.12 * sum(1 for term in positive_terms if term in text)
        score -= 0.18 * sum(1 for term in negative_terms if term in text)
        return score
