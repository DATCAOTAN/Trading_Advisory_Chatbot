from typing import Any, Dict, List, Optional, Tuple
import time

import fitz  # PyMuPDF

from src.services.knowledge.chunk_policy_resolver import (
    ChunkPolicy,
    ChunkPolicyDecision,
    ChunkPolicyResolver,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    V3_CHUNK_POLICIES,
)
from src.services.knowledge.document_parser import DocumentParserRegistry, ParsedDocument, ParsedSection


class ChunkBuilder:
    """
    V3-native chunk builder with OCR guardrails and metadata-driven policies.

    The indexed unit is a child chunk. Each child keeps parent context metadata
    so search can rank precise text while downstream answer generation can still
    see the wider local context.
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
        parser_registry: Optional[DocumentParserRegistry] = None,
        policy_resolver: Optional[ChunkPolicyResolver] = None,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunker_version = "v1.4-adaptive-parsed"
        self.parser_version = f"PyMuPDF-{fitz.VersionBind}"
        self.parser_registry = parser_registry or DocumentParserRegistry()
        self.policy_resolver = policy_resolver or ChunkPolicyResolver()

    def build_chunks(self, file_path: str, resolved_metadata: Dict[str, Any]) -> Dict[str, Any]:
        try:
            parsed_document = self.parser_registry.parse(file_path, resolved_metadata)
        except Exception as exc:
            return {"status": "FAILED", "chunks": [], "error": str(exc)}
        return self.build_chunks_from_parsed(parsed_document, resolved_metadata)

    def build_chunks_from_parsed(
        self,
        parsed_document: ParsedDocument,
        resolved_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        doc_id = resolved_metadata["document_metadata"]["doc_id"]
        policy_decision = self.resolve_policy(resolved_metadata, parsed_document)
        policy = policy_decision.policy
        self._log_policy_decision(policy_decision)

        if parsed_document.extraction_status in {"FAILED", "EMPTY_DOCUMENT", "NEEDS_OCR"}:
            chunk_stats = self.collect_chunk_stats(
                file_path=parsed_document.file_path,
                status=parsed_document.extraction_status,
                policy=policy,
                chunks=[],
                total_pages=self._total_units(parsed_document),
                empty_pages=self._empty_units(parsed_document),
                extracted_char_count=parsed_document.extracted_char_count,
                extracted_word_count=parsed_document.extracted_word_count,
                parent_count=0,
                indexed_count=0,
                parser_type=parsed_document.parser_type,
                parser_version=parsed_document.parser_version,
                policy_decision=policy_decision,
            )
            return {
                "status": parsed_document.extraction_status,
                "chunks": [],
                "error": "; ".join(parsed_document.warnings),
                "operational_metadata": self._operational_metadata(parsed_document, policy_decision, chunk_stats),
                "chunk_stats": chunk_stats,
            }

        chunks: List[Dict[str, Any]] = []
        parent_count = 0

        for section_index, section in enumerate(parsed_document.sections, start=1):
            text = section.text or ""
            if not text.strip():
                continue

            parent_chunks = self._make_sliding_chunks(
                text,
                policy.parent_size,
                policy.parent_overlap,
                policy.min_chunk_chars,
            )
            child_counter = 0
            chunk_prefix = self._chunk_prefix(doc_id, section_index, section)
            unit_label = self._unit_label(section_index, section)

            for parent_idx, (parent_start, parent_text) in enumerate(parent_chunks, start=1):
                parent_count += 1
                parent_chunk_id = f"{chunk_prefix}_parent{parent_idx}"
                child_chunks = self._make_sliding_chunks(
                    parent_text,
                    policy.child_size,
                    policy.child_overlap,
                    policy.min_chunk_chars,
                )

                for child_start, child_text in child_chunks:
                    if not child_text.strip():
                        continue

                    child_counter += 1
                    chunk_id = f"{chunk_prefix}_c{child_counter}"
                    char_count = len(child_text)

                    chunks.append({
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "text": child_text,
                        "page": section.page,
                        "paragraph": section.paragraph_index or child_counter,
                        "offset": parent_start + child_start,
                        "char_count": char_count,
                        "token_count": max(1, char_count // 4),
                        "section_title": section.section or section.chapter or unit_label,
                        "heading_level": 0,
                        "chunk_level": "child",
                        "parent_chunk_id": parent_chunk_id,
                        "parent_text": parent_text,
                        "parent_offset": parent_start,
                        "chunk_policy_id": policy.policy_id,
                        "chapter": section.chapter,
                        "location": section.location or unit_label,
                        "spine_index": section.spine_index,
                        "href": section.href,
                        "routing_metadata": resolved_metadata.get("routing_metadata", {}),
                        "document_metadata": resolved_metadata.get("document_metadata", {}),
                    })

        status = parsed_document.extraction_status or "CHUNKED"
        if not chunks:
            status = "EMPTY_DOCUMENT"
        elif parsed_document.extraction_quality < 0.8 and status == "CHUNKED":
            status = "PARTIAL_TEXT"

        chunk_stats = self.collect_chunk_stats(
            file_path=parsed_document.file_path,
            status=status,
            policy=policy,
            chunks=chunks,
            total_pages=self._total_units(parsed_document),
            empty_pages=self._empty_units(parsed_document),
            extracted_char_count=parsed_document.extracted_char_count,
            extracted_word_count=parsed_document.extracted_word_count,
            parent_count=parent_count if chunks else 0,
            indexed_count=len(chunks),
            parser_type=parsed_document.parser_type,
            parser_version=parsed_document.parser_version,
            policy_decision=policy_decision,
        )

        self._log_chunk_counts(parsed_document.file_path, chunks)

        operational_metadata = self._operational_metadata(parsed_document, policy_decision, chunk_stats)
        for chunk in chunks:
            chunk["operational_metadata"] = operational_metadata

        return {
            "status": status,
            "chunks": chunks,
            "operational_metadata": operational_metadata,
            "chunk_stats": chunk_stats,
        }

    def select_policy(self, resolved_metadata: Dict[str, Any]) -> ChunkPolicy:
        return self.resolve_policy(resolved_metadata, self._empty_parsed_document()).policy

    def resolve_policy(
        self,
        resolved_metadata: Dict[str, Any],
        parsed_document: ParsedDocument,
    ) -> ChunkPolicyDecision:
        return self.policy_resolver.resolve(
            resolved_metadata=resolved_metadata,
            parsed_document=parsed_document,
            custom_chunk_size=self.chunk_size,
            custom_overlap=self.overlap,
        )

    def collect_chunk_stats(
        self,
        file_path: str,
        status: str,
        policy: ChunkPolicy,
        chunks: List[Dict[str, Any]],
        total_pages: int,
        empty_pages: int,
        extracted_char_count: int,
        extracted_word_count: int,
        parent_count: int,
        indexed_count: int,
        parser_type: str = "pdf:pymupdf",
        parser_version: Optional[str] = None,
        policy_decision: Optional[ChunkPolicyDecision] = None,
    ) -> Dict[str, Any]:
        chunk_sizes = [len(chunk.get("text", "")) for chunk in chunks]
        avg_chunk_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0.0
        stats = {
            "input_file_path": file_path,
            "parser_type": parser_type,
            "parser_version": parser_version or self.parser_version,
            "extracted_char_count": extracted_char_count,
            "extracted_word_count": extracted_word_count,
            "selected_chunk_policy": policy.policy_id,
            "parent_chunk_count": parent_count,
            "indexed_chunk_count": indexed_count,
            "average_chunk_size": round(avg_chunk_size, 2),
            "ocr_status": status,
            "total_pages": total_pages,
            "empty_pages": empty_pages,
            "parent_size": policy.parent_size,
            "parent_overlap": policy.parent_overlap,
            "child_size": policy.child_size,
            "child_overlap": policy.child_overlap,
            "parent_size_chars": policy.parent_size,
            "parent_overlap_chars": policy.parent_overlap,
            "child_size_chars": policy.child_size,
            "child_overlap_chars": policy.child_overlap,
            "chunk_size_unit": "characters",
            "token_estimate_unit": f"characters/{TOKEN_ESTIMATE_CHARS_PER_TOKEN}",
            "parent_target_tokens": self._estimate_tokens(policy.parent_size),
            "child_target_tokens": self._estimate_tokens(policy.child_size),
            "overlap_tokens": self._estimate_tokens(policy.child_overlap),
        }
        if policy_decision is not None:
            stats["policy_fallback_level"] = policy_decision.fallback_level
            stats["policy_reason"] = policy_decision.reason
            stats["policy_warnings"] = list(policy_decision.warnings)
            stats["document_policy_stats"] = dict(policy_decision.stats)
        return stats

    def _make_sliding_chunks(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
        min_chars: int = 50,
    ) -> List[Tuple[int, str]]:
        if chunk_size <= 0:
            return []

        step = max(1, chunk_size - max(0, overlap))
        chunks = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = start + chunk_size
            chunk_text = text[start:end].strip()
            if len(chunk_text) > min_chars:
                chunks.append((start, chunk_text))
            start += step
        return chunks

    def _operational_metadata(
        self,
        parsed_document: ParsedDocument,
        policy_decision: ChunkPolicyDecision,
        chunk_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        policy = policy_decision.policy
        return {
            "parser_version": parsed_document.parser_version,
            "pdf_parser_mode": (parsed_document.metadata_hints or {}).get("pdf_parser_mode", ""),
            "mineru_command": (parsed_document.metadata_hints or {}).get("mineru_command", ""),
            "mineru_backend": (parsed_document.metadata_hints or {}).get("mineru_backend", ""),
            "mineru_method": (parsed_document.metadata_hints or {}).get("mineru_method", ""),
            "mineru_timeout_seconds": (parsed_document.metadata_hints or {}).get("mineru_timeout_seconds", ""),
            "mineru_parse_books": (parsed_document.metadata_hints or {}).get("mineru_parse_books", ""),
            "parser_output_schema_version": (parsed_document.metadata_hints or {}).get("parser_output_schema_version", ""),
            "mineru_selective_book_pages_enabled": (parsed_document.metadata_hints or {}).get("mineru_selective_book_pages_enabled", ""),
            "mineru_selective_max_pages_per_doc": (parsed_document.metadata_hints or {}).get("mineru_selective_max_pages_per_doc", ""),
            "mineru_selective_max_ranges_per_doc": (parsed_document.metadata_hints or {}).get("mineru_selective_max_ranges_per_doc", ""),
            "mineru_selective_low_text_chars": (parsed_document.metadata_hints or {}).get("mineru_selective_low_text_chars", ""),
            "mineru_selective_table_like_threshold": (parsed_document.metadata_hints or {}).get("mineru_selective_table_like_threshold", ""),
            "mineru_selective_image_area_ratio": (parsed_document.metadata_hints or {}).get("mineru_selective_image_area_ratio", ""),
            "mineru_full_max_pages_soft_limit": (parsed_document.metadata_hints or {}).get("mineru_full_max_pages_soft_limit", ""),
            "mineru_full_complex_page_ratio_threshold": (parsed_document.metadata_hints or {}).get("mineru_full_complex_page_ratio_threshold", ""),
            "parse_plan_type": (parsed_document.metadata_hints or {}).get("parse_plan_type", ""),
            "base_parser": (parsed_document.metadata_hints or {}).get("base_parser", ""),
            "advanced_parser": (parsed_document.metadata_hints or {}).get("advanced_parser", ""),
            "selective_page_count": (parsed_document.metadata_hints or {}).get("selective_page_count", 0),
            "selective_failed_pages": (parsed_document.metadata_hints or {}).get("selective_failed_pages", []),
            "chunker_version": self.chunker_version,
            "extraction_quality_score": parsed_document.extraction_quality,
            "empty_pages": self._empty_units(parsed_document),
            "total_pages": self._total_units(parsed_document),
            "ingestion_timestamp": time.time(),
            "chunk_policy_id": policy.policy_id,
            "chunk_policy_fallback_level": policy_decision.fallback_level,
            "chunk_policy_reason": policy_decision.reason,
            "chunk_policy_warnings": policy_decision.warnings,
            "chunk_stats": chunk_stats,
            "parser_type": parsed_document.parser_type,
            "warnings": parsed_document.warnings,
        }

    def _log_policy_decision(self, decision: ChunkPolicyDecision) -> None:
        policy = decision.policy
        stats = decision.stats
        print(
            "[ChunkPolicy] "
            f"file={stats.get('file_path', '')} "
            f"document_type={stats.get('document_type', '')} "
            f"knowledge_type={stats.get('knowledge_type', '')} "
            f"domain={stats.get('domain', '')} "
            f"subdomain={stats.get('subdomain', '')} "
            f"selected_policy={policy.policy_id} "
            f"fallback_level={decision.fallback_level} "
            "unit=characters "
            f"token_estimate_unit=chars/{TOKEN_ESTIMATE_CHARS_PER_TOKEN} "
            f"parent_size_chars={policy.parent_size} "
            f"child_size_chars={policy.child_size} "
            f"overlap_chars={policy.child_overlap} "
            f"parent_target_tokens={self._estimate_tokens(policy.parent_size)} "
            f"child_target_tokens={self._estimate_tokens(policy.child_size)} "
            f"overlap_tokens={self._estimate_tokens(policy.child_overlap)} "
            f"reason={decision.reason}"
        )
        for warning in decision.warnings:
            print(f"[ChunkPolicy] file={stats.get('file_path', '')} warning={warning}")

    def _log_chunk_counts(self, file_path: str, chunks: List[Dict[str, Any]]) -> None:
        token_counts = [int(chunk.get("token_count") or 0) for chunk in chunks]
        avg_child_tokens = sum(token_counts) / len(token_counts) if token_counts else 0.0
        max_child_tokens = max(token_counts) if token_counts else 0
        parent_ids = {chunk.get("parent_chunk_id") for chunk in chunks if chunk.get("parent_chunk_id")}
        print(
            "[ChunkBuilder] "
            f"file={file_path} "
            f"parents={len(parent_ids)} "
            f"children={len(chunks)} "
            f"avg_child_tokens={avg_child_tokens:.2f} "
            f"max_child_tokens={max_child_tokens} "
            "truncated=0"
        )

    def _chunk_prefix(self, doc_id: str, section_index: int, section: ParsedSection) -> str:
        if section.page is not None:
            return f"{doc_id}_p{section.page}"
        location = f"loc{section.spine_index or section_index}"
        return f"{doc_id}_{location}"

    def _unit_label(self, section_index: int, section: ParsedSection) -> str:
        if section.page is not None:
            return f"page:{section.page}"
        if section.location:
            return section.location
        return f"section:{section_index}"

    def _total_units(self, parsed_document: ParsedDocument) -> int:
        hints = parsed_document.metadata_hints or {}
        return int(hints.get("total_pages") or hints.get("section_count") or len(parsed_document.sections))

    def _empty_units(self, parsed_document: ParsedDocument) -> int:
        hints = parsed_document.metadata_hints or {}
        if "empty_pages" in hints:
            return int(hints["empty_pages"])
        total = self._total_units(parsed_document)
        return max(0, total - len(parsed_document.sections))

    def _empty_parsed_document(self) -> ParsedDocument:
        return ParsedDocument(
            file_path="",
            parser_type="",
            parser_version="",
            extraction_status="EMPTY_DOCUMENT",
            extraction_quality=0.0,
            sections=[],
        )

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _estimate_tokens(char_count: int) -> int:
        return max(1, int(char_count) // TOKEN_ESTIMATE_CHARS_PER_TOKEN)
