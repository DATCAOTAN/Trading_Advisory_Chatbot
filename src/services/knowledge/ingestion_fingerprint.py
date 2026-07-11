import hashlib
import json
from typing import Any, Dict


FINGERPRINT_VERSION = "v1"
METADATA_SCHEMA_VERSION = "v3"
EMBEDDING_MODEL = "embed-multilingual-v3.0"
EMBEDDING_DIMENSION = 1024
EMBEDDING_VERSION = "cohere-client-v2"


class IngestionFingerprintBuilder:
    """Build stable fingerprints for content + indexing configuration."""

    def build(
        self,
        checksum: str,
        parsed_document: Any,
        chunk_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        chunk_stats = chunk_result.get("chunk_stats", {}) or {}
        operational = chunk_result.get("operational_metadata", {}) or {}
        payload = {
            "fingerprint_version": FINGERPRINT_VERSION,
            "document_checksum": checksum or "",
            "parser_name": getattr(parsed_document, "parser_type", "") or chunk_stats.get("parser_type", ""),
            "parser_version": getattr(parsed_document, "parser_version", "") or chunk_stats.get("parser_version", ""),
            "pdf_parser_mode": operational.get("pdf_parser_mode", ""),
            "mineru_command": operational.get("mineru_command", ""),
            "mineru_backend": operational.get("mineru_backend", ""),
            "mineru_method": operational.get("mineru_method", ""),
            "mineru_timeout_seconds": operational.get("mineru_timeout_seconds", ""),
            "mineru_parse_books": operational.get("mineru_parse_books", ""),
            "mineru_selective_book_pages_enabled": operational.get("mineru_selective_book_pages_enabled", ""),
            "mineru_selective_max_pages_per_doc": operational.get("mineru_selective_max_pages_per_doc", ""),
            "mineru_selective_max_ranges_per_doc": operational.get("mineru_selective_max_ranges_per_doc", ""),
            "mineru_selective_low_text_chars": operational.get("mineru_selective_low_text_chars", ""),
            "mineru_selective_table_like_threshold": operational.get("mineru_selective_table_like_threshold", ""),
            "mineru_selective_image_area_ratio": operational.get("mineru_selective_image_area_ratio", ""),
            "mineru_full_max_pages_soft_limit": operational.get("mineru_full_max_pages_soft_limit", ""),
            "mineru_full_complex_page_ratio_threshold": operational.get("mineru_full_complex_page_ratio_threshold", ""),
            "parser_output_schema_version": operational.get("parser_output_schema_version", ""),
            "chunker_version": operational.get("chunker_version", ""),
            "chunk_policy_id": chunk_stats.get("selected_chunk_policy", ""),
            "chunk_policy_version": operational.get("chunk_policy_id", chunk_stats.get("selected_chunk_policy", "")),
            "parent_size_chars": int(chunk_stats.get("parent_size_chars") or chunk_stats.get("parent_size") or 0),
            "child_size_chars": int(chunk_stats.get("child_size_chars") or chunk_stats.get("child_size") or 0),
            "parent_overlap_chars": int(chunk_stats.get("parent_overlap_chars") or chunk_stats.get("parent_overlap") or 0),
            "child_overlap_chars": int(chunk_stats.get("child_overlap_chars") or chunk_stats.get("child_overlap") or 0),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "embedding_version": EMBEDDING_VERSION,
            "metadata_schema_version": METADATA_SCHEMA_VERSION,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "fingerprint": hashlib.sha256(encoded).hexdigest(),
            "fingerprint_version": FINGERPRINT_VERSION,
            "payload": payload,
        }
