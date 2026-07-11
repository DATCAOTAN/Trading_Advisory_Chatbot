import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ContextPackStats:
    input_docs: int
    output_docs: int
    duplicate_parent_count: int
    total_context_chars: int
    truncated_docs_count: int


class ContextPacker:
    """
    Prepare retrieved documents before they become LLM context.

    Keeps the existing {content, metadata, score} document contract while
    removing duplicate parent contexts that can appear when child chunks match
    the same parent chunk.
    """

    def pack(
        self,
        documents: List[Dict[str, Any]],
        max_sources: Optional[int] = None,
        max_context_chars: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], ContextPackStats]:
        valid_docs = [
            doc for doc in (documents or [])
            if isinstance(doc, dict) and str(doc.get("content", "")).strip()
        ]
        deduped_docs, duplicate_count = self._dedupe_by_context_key(valid_docs)
        limited_docs, truncated_count = self._apply_limits(
            deduped_docs,
            max_sources=max_sources,
            max_context_chars=max_context_chars,
        )
        total_chars = sum(len(str(doc.get("content", ""))) for doc in limited_docs)
        stats = ContextPackStats(
            input_docs=len(valid_docs),
            output_docs=len(limited_docs),
            duplicate_parent_count=duplicate_count,
            total_context_chars=total_chars,
            truncated_docs_count=truncated_count,
        )
        return limited_docs, stats

    def render_context(self, documents: List[Dict[str, Any]], include_scores: bool = True) -> str:
        parts = []
        for doc in documents or []:
            content = str(doc.get("content", "")).strip()
            if not content:
                continue
            parts.append(f"{self._source_header(doc, include_scores=include_scores)}\n[CONTENT]\n{content}")
        return "\n\n".join(parts)

    def _source_header(self, doc: Dict[str, Any], include_scores: bool = True) -> str:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        title = metadata.get("title") or metadata.get("source") or doc.get("source") or "Unknown source"
        source = metadata.get("source") or doc.get("source") or ""
        author = metadata.get("author") or ""
        organization = metadata.get("organization") or ""
        page = metadata.get("page")
        doc_type = metadata.get("doc_type") or ""
        domain = metadata.get("domain") or ""
        subdomain = metadata.get("subdomain") or ""
        source_tier = metadata.get("source_tier") or ""
        event_type = metadata.get("event_type") or ""
        period = metadata.get("period") or ""
        published_date = metadata.get("published_date") or ""
        country = metadata.get("country") or ""
        source_role = metadata.get("source_role") or ""
        source_usage_reasons = metadata.get("source_usage_reasons") or []
        grounding_status = metadata.get("answer_grounding_status") or ""
        grounding_warnings = metadata.get("grounding_warnings") or []

        lines = ["[SOURCE]", f"Title: {title}"]
        if source and source != title:
            lines.append(f"Source: {source}")
        if author:
            lines.append(f"Author: {author}")
        if organization:
            lines.append(f"Organization: {organization}")
        if page not in {None, ""}:
            lines.append(f"Page: {page}")
        if doc_type:
            lines.append(f"Doc type: {doc_type}")
        if event_type:
            lines.append(f"Event type: {event_type}")
        if period:
            lines.append(f"Period: {period}")
        if published_date:
            lines.append(f"Published date: {published_date}")
        if country:
            lines.append(f"Country: {country}")
        if source_role:
            lines.append(f"Source role: {source_role}")
        if source_usage_reasons:
            if isinstance(source_usage_reasons, list):
                reasons_text = ", ".join(str(item) for item in source_usage_reasons)
            else:
                reasons_text = str(source_usage_reasons)
            lines.append(f"Why used: {reasons_text}")
        if grounding_status:
            lines.append(f"Grounding status: {grounding_status}")
        if grounding_warnings:
            warnings_text = "; ".join(str(item) for item in grounding_warnings[:3]) if isinstance(grounding_warnings, list) else str(grounding_warnings)
            lines.append(f"Grounding warning: {warnings_text}")
        if domain or subdomain:
            lines.append(f"Routing: {domain}/{subdomain}".rstrip("/"))
        if source_tier:
            lines.append(f"Source tier: {source_tier}")
        if include_scores:
            lines.append(f"Relevance score: {self._score(doc):.2f}")
        return "\n".join(lines)

    def _dedupe_by_context_key(self, documents: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        by_key: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        duplicate_count = 0

        for doc in documents:
            key = self._context_key(doc)
            if key in by_key:
                duplicate_count += 1
                if self._score(doc) > self._score(by_key[key]):
                    by_key[key] = doc
                continue

            by_key[key] = doc
            order.append(key)

        return [by_key[key] for key in order], duplicate_count

    def _apply_limits(
        self,
        documents: List[Dict[str, Any]],
        max_sources: Optional[int],
        max_context_chars: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], int]:
        if max_sources is not None and max_sources >= 0:
            source_limited = documents[:max_sources]
            truncated_count = max(0, len(documents) - len(source_limited))
        else:
            source_limited = list(documents)
            truncated_count = 0

        if max_context_chars is None or max_context_chars <= 0:
            return source_limited, truncated_count

        packed = []
        used_chars = 0
        for doc in source_limited:
            content_len = len(str(doc.get("content", "")))
            if used_chars + content_len > max_context_chars:
                truncated_count += 1
                continue
            packed.append(doc)
            used_chars += content_len
        return packed, truncated_count

    def _context_key(self, doc: Dict[str, Any]) -> str:
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        key = (
            metadata.get("parent_chunk_id")
            or metadata.get("parent_id")
            or doc.get("parent_chunk_id")
            or doc.get("parent_id")
            or metadata.get("chunk_id")
            or doc.get("chunk_id")
        )
        if key:
            return str(key)
        return hashlib.sha256(str(doc.get("content", "")).encode("utf-8")).hexdigest()

    @staticmethod
    def _score(doc: Dict[str, Any]) -> float:
        try:
            return float(doc.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
