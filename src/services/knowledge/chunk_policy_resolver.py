from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from src.services.knowledge.document_parser import ParsedDocument


@dataclass(frozen=True)
class ChunkPolicy:
    policy_id: str
    # Sizes are character windows. Token values in logs/stats are estimates
    # using TOKEN_ESTIMATE_CHARS_PER_TOKEN so operators do not confuse units.
    parent_size: int
    parent_overlap: int
    child_size: int
    child_overlap: int
    min_chunk_chars: int = 50


@dataclass(frozen=True)
class ChunkPolicyDecision:
    policy: ChunkPolicy
    fallback_level: str
    reason: str
    stats: Dict[str, Any]
    warnings: List[str]


TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4


POLICY_BOUNDS = {
    "parent_size": (2400, 7200),
    "parent_overlap": (240, 1200),
    "child_size": (800, 1800),
    "child_overlap": (120, 420),
    "min_chunk_chars": (80, 260),
}


CUSTOM_POLICY_BOUNDS = {
    "parent_size": (80, 7200),
    "parent_overlap": (0, 1200),
    "child_size": (80, 1800),
    "child_overlap": (0, 420),
    "min_chunk_chars": (30, 260),
}


V3_CHUNK_POLICIES: Dict[str, ChunkPolicy] = {
    # Exact domain/subdomain policies. Values are character windows sized for
    # real books/reports, with token estimates roughly chars / 4.
    "technical_indicators": ChunkPolicy("technical_indicators", 5200, 520, 1200, 220),
    "technical_price_action": ChunkPolicy("technical_price_action", 5200, 520, 1200, 220),
    "technical_smc": ChunkPolicy("technical_smc", 5600, 560, 1300, 260),
    "risk_management": ChunkPolicy("risk_management", 5600, 560, 1400, 280),

    # Broader fallback policies.
    "technical_default": ChunkPolicy("technical_default", 4800, 480, 1100, 220),
    "psychology_default": ChunkPolicy("psychology_default", 5600, 560, 1400, 280),
    "risk_default": ChunkPolicy("risk_default", 5600, 560, 1400, 280),
    "macro_report_default": ChunkPolicy("macro_report_default", 3600, 360, 900, 180),
    "macro_default": ChunkPolicy("macro_default", 3600, 360, 900, 180),
    "market_report_default": ChunkPolicy("market_report_default", 3600, 360, 900, 180),
    "market_default": ChunkPolicy("market_default", 3800, 380, 950, 190),
    "quantitative_default": ChunkPolicy("quantitative_default", 4200, 420, 1000, 200),
    "book_default": ChunkPolicy("book_default", 4800, 480, 1100, 220),
    "report_default": ChunkPolicy("report_default", 3600, 360, 900, 180),
    "pdf_default": ChunkPolicy("pdf_default", 4200, 420, 1000, 200),
    "epub_book_default": ChunkPolicy("epub_book_default", 5200, 520, 1200, 240),
    "epub_default": ChunkPolicy("epub_default", 4400, 440, 1000, 200),
    "global_default": ChunkPolicy("global_default", 4000, 400, 900, 180),

    # Backward-compatible alias used by older tests/scripts.
    "default": ChunkPolicy("global_default", 4000, 400, 900, 180),
}


EXACT_POLICY_BY_DOMAIN_SUBDOMAIN: Dict[Tuple[str, str], str] = {
    ("technical", "indicators"): "technical_indicators",
    ("technical", "price_action"): "technical_price_action",
    ("technical", "smc"): "technical_smc",
    ("risk", "position_sizing"): "risk_management",
}


DOMAIN_DEFAULT_POLICY: Dict[str, str] = {
    "technical": "technical_default",
    "psychology": "psychology_default",
    "risk": "risk_default",
    "macro": "macro_default",
    "market": "market_default",
    "quantitative": "quantitative_default",
}


KNOWLEDGE_TYPE_DEFAULT_POLICY: Dict[str, str] = {
    "book": "book_default",
    "report": "report_default",
}


DOCUMENT_TYPE_DEFAULT_POLICY: Dict[Tuple[str, str], str] = {
    ("epub", "book"): "epub_book_default",
    ("epub", ""): "epub_default",
    ("pdf", ""): "pdf_default",
}


class ChunkPolicyResolver:
    """Resolve and safely calibrate V3 chunking policy from metadata and parsed stats."""

    def resolve(
        self,
        resolved_metadata: Dict[str, Any],
        parsed_document: ParsedDocument,
        custom_chunk_size: Optional[int] = None,
        custom_overlap: Optional[int] = None,
    ) -> ChunkPolicyDecision:
        stats = self.collect_document_stats(resolved_metadata, parsed_document)
        warnings: List[str] = []

        if custom_chunk_size is not None or custom_overlap is not None:
            policy = self._custom_policy(custom_chunk_size, custom_overlap)
            return ChunkPolicyDecision(
                policy=policy,
                fallback_level="runtime_custom",
                reason="ChunkBuilder was constructed with explicit chunk_size/overlap.",
                stats=stats,
                warnings=warnings,
            )

        base_policy, fallback_level, reason = self._select_base_policy(stats)
        calibrated_policy = self._calibrate(base_policy, stats)
        warnings.extend(self._describe_calibration(base_policy, calibrated_policy, stats))
        calibrated_policy, quality_warnings = self._enforce_quality_gate(calibrated_policy, stats)
        warnings.extend(quality_warnings)

        override = resolved_metadata.get("chunking_override") or resolved_metadata.get("chunk_policy")
        if isinstance(override, dict) and override:
            override_policy, override_warning = self._apply_manifest_override(calibrated_policy, override)
            if override_warning:
                warnings.append(override_warning)
            else:
                calibrated_policy, quality_warnings = self._enforce_quality_gate(override_policy, stats)
                warnings.extend(quality_warnings)
                fallback_level = "manifest_override"
                reason = f"Manifest chunking override applied over {base_policy.policy_id}."

        return ChunkPolicyDecision(
            policy=calibrated_policy,
            fallback_level=fallback_level,
            reason=reason,
            stats=stats,
            warnings=warnings,
        )

    def collect_document_stats(
        self,
        resolved_metadata: Dict[str, Any],
        parsed_document: ParsedDocument,
    ) -> Dict[str, Any]:
        routing = resolved_metadata.get("routing_metadata", {}) or {}
        document = resolved_metadata.get("document_metadata", {}) or {}
        document_type = self._norm(document.get("document_type")) or self._document_type_from_parser(parsed_document)
        knowledge_type = self._norm(routing.get("knowledge_type"))
        domain = self._norm(routing.get("domain"))
        subdomain = self._norm(routing.get("subdomain"))

        section_lengths = [len(section.text or "") for section in parsed_document.sections if (section.text or "").strip()]
        paragraph_lengths: List[int] = []
        table_like_lines = 0
        total_lines = 0
        heading_count = 0
        for section in parsed_document.sections:
            text = section.text or ""
            paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
            paragraph_lengths.extend(len(p) for p in paragraphs)
            if section.chapter or section.section:
                heading_count += 1
            for line in paragraphs:
                total_lines += 1
                if self._is_table_like(line):
                    table_like_lines += 1

        total_chars = parsed_document.extracted_char_count
        total_words = parsed_document.extracted_word_count
        total_units = self._total_units(parsed_document)
        avg_section_chars = sum(section_lengths) / len(section_lengths) if section_lengths else 0.0
        avg_paragraph_chars = sum(paragraph_lengths) / len(paragraph_lengths) if paragraph_lengths else 0.0
        table_like_ratio = table_like_lines / total_lines if total_lines else 0.0
        text_density = total_chars / max(1, total_units)

        return {
            "file_path": parsed_document.file_path,
            "document_type": document_type,
            "knowledge_type": knowledge_type,
            "domain": domain,
            "subdomain": subdomain,
            "parser_type": parsed_document.parser_type,
            "total_chars": total_chars,
            "total_words": total_words,
            "page_count": int((parsed_document.metadata_hints or {}).get("total_pages") or 0),
            "chapter_count": len(parsed_document.sections) if document_type == "epub" else 0,
            "section_count": len(parsed_document.sections),
            "average_section_chars": round(avg_section_chars, 2),
            "average_paragraph_chars": round(avg_paragraph_chars, 2),
            "heading_count": heading_count,
            "table_like_text_ratio": round(table_like_ratio, 4),
            "text_density": round(text_density, 2),
        }

    def _select_base_policy(self, stats: Dict[str, Any]) -> Tuple[ChunkPolicy, str, str]:
        domain = stats["domain"]
        subdomain = stats["subdomain"]
        knowledge_type = stats["knowledge_type"]
        document_type = stats["document_type"]

        exact_policy_id = EXACT_POLICY_BY_DOMAIN_SUBDOMAIN.get((domain, subdomain))
        if exact_policy_id:
            return V3_CHUNK_POLICIES[exact_policy_id], "exact", f"Matched exact domain/subdomain {domain}/{subdomain}."

        if domain == "macro" and knowledge_type == "report":
            return V3_CHUNK_POLICIES["macro_report_default"], "domain_default", "Matched macro report default."

        if domain == "market" and knowledge_type == "report":
            return V3_CHUNK_POLICIES["market_report_default"], "domain_default", "Matched market report default."

        domain_policy_id = DOMAIN_DEFAULT_POLICY.get(domain)
        if domain_policy_id:
            return V3_CHUNK_POLICIES[domain_policy_id], "domain_default", f"Matched domain default for {domain}."

        specialized_document_policy_id = DOCUMENT_TYPE_DEFAULT_POLICY.get((document_type, knowledge_type))
        if specialized_document_policy_id:
            return (
                V3_CHUNK_POLICIES[specialized_document_policy_id],
                "document_type_default",
                f"Matched document_type/knowledge_type default for {document_type}/{knowledge_type}.",
            )

        knowledge_policy_id = KNOWLEDGE_TYPE_DEFAULT_POLICY.get(knowledge_type)
        if knowledge_policy_id:
            return V3_CHUNK_POLICIES[knowledge_policy_id], "knowledge_type_default", f"Matched knowledge_type default for {knowledge_type}."

        document_policy_id = DOCUMENT_TYPE_DEFAULT_POLICY.get((document_type, knowledge_type))
        if not document_policy_id:
            document_policy_id = DOCUMENT_TYPE_DEFAULT_POLICY.get((document_type, ""))
        if document_policy_id:
            return V3_CHUNK_POLICIES[document_policy_id], "document_type_default", f"Matched document_type default for {document_type}."

        return V3_CHUNK_POLICIES["global_default"], "global_default", "No specific policy matched; using global default."

    def _calibrate(self, policy: ChunkPolicy, stats: Dict[str, Any]) -> ChunkPolicy:
        parent_size = policy.parent_size
        parent_overlap = policy.parent_overlap
        child_size = policy.child_size
        child_overlap = policy.child_overlap

        total_chars = int(stats.get("total_chars") or 0)
        avg_paragraph_chars = float(stats.get("average_paragraph_chars") or 0.0)
        table_like_ratio = float(stats.get("table_like_text_ratio") or 0.0)
        document_type = stats.get("document_type", "")
        knowledge_type = stats.get("knowledge_type", "")

        if total_chars > 600_000:
            parent_size = int(parent_size * 1.12)
            child_size = int(child_size * 1.08)
        elif 0 < total_chars < 25_000:
            parent_size = int(parent_size * 0.85)
            child_size = int(child_size * 0.9)

        if document_type == "epub" and knowledge_type == "book":
            parent_size = int(parent_size * 1.05)

        if avg_paragraph_chars > 900:
            child_size = int(child_size * 1.12)
        elif 0 < avg_paragraph_chars < 180:
            child_size = int(child_size * 0.92)

        if table_like_ratio > 0.25:
            child_size = int(child_size * 0.9)

        parent_size = self._bounded("parent_size", parent_size)
        child_size = self._bounded("child_size", child_size)
        parent_overlap = self._bounded("parent_overlap", max(parent_overlap, int(parent_size * 0.08)))
        child_overlap = self._bounded("child_overlap", max(child_overlap, int(child_size * 0.12)))

        parent_overlap = min(parent_overlap, parent_size // 2)
        child_overlap = min(child_overlap, child_size // 2)

        return replace(
            policy,
            parent_size=parent_size,
            parent_overlap=parent_overlap,
            child_size=child_size,
            child_overlap=child_overlap,
        )

    def _describe_calibration(
        self,
        base_policy: ChunkPolicy,
        calibrated_policy: ChunkPolicy,
        stats: Dict[str, Any],
    ) -> List[str]:
        changes = []
        if calibrated_policy.parent_size < base_policy.parent_size:
            changes.append(
                "Auto-calibration reduced parent window for a short document "
                f"(total_chars={stats.get('total_chars', 0)})."
            )
        if calibrated_policy.child_size < base_policy.child_size:
            changes.append(
                "Auto-calibration reduced child window for short paragraphs or table-like text "
                f"(avg_paragraph_chars={stats.get('average_paragraph_chars', 0)}, "
                f"table_like_ratio={stats.get('table_like_text_ratio', 0)})."
            )
        if calibrated_policy.parent_size > base_policy.parent_size:
            changes.append(
                "Auto-calibration expanded parent window for a long document "
                f"(total_chars={stats.get('total_chars', 0)}, document_type={stats.get('document_type', '')})."
            )
        if calibrated_policy.child_size > base_policy.child_size:
            changes.append(
                "Auto-calibration expanded child window for long paragraphs or long documents "
                f"(total_chars={stats.get('total_chars', 0)}, "
                f"avg_paragraph_chars={stats.get('average_paragraph_chars', 0)})."
            )
        return changes

    def _enforce_quality_gate(
        self,
        policy: ChunkPolicy,
        stats: Dict[str, Any],
    ) -> Tuple[ChunkPolicy, List[str]]:
        min_parent_tokens, min_child_tokens, min_overlap_tokens = self._minimum_token_targets(stats)
        min_parent_chars = min_parent_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN
        min_child_chars = min_child_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN
        min_overlap_chars = min_overlap_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN

        parent_size = max(policy.parent_size, min_parent_chars)
        child_size = max(policy.child_size, min_child_chars)
        child_overlap = max(policy.child_overlap, min_overlap_chars)
        parent_overlap = max(policy.parent_overlap, min(min_parent_chars // 10, parent_size // 2))

        parent_size = self._bounded("parent_size", parent_size)
        child_size = self._bounded("child_size", child_size)
        parent_overlap = min(self._bounded("parent_overlap", parent_overlap), parent_size // 2)
        child_overlap = min(self._bounded("child_overlap", child_overlap), child_size // 2)

        warnings = []
        if (
            parent_size != policy.parent_size
            or child_size != policy.child_size
            or parent_overlap != policy.parent_overlap
            or child_overlap != policy.child_overlap
        ):
            warnings.append(
                "Chunk quality gate adjusted policy below safe token floors "
                f"(unit=chars, token_estimate=chars/{TOKEN_ESTIMATE_CHARS_PER_TOKEN}, "
                f"min_parent_tokens={min_parent_tokens}, min_child_tokens={min_child_tokens}, "
                f"min_overlap_tokens={min_overlap_tokens})."
            )

        return replace(
            policy,
            parent_size=parent_size,
            parent_overlap=parent_overlap,
            child_size=child_size,
            child_overlap=child_overlap,
        ), warnings

    def _minimum_token_targets(self, stats: Dict[str, Any]) -> Tuple[int, int, int]:
        domain = stats.get("domain", "")
        knowledge_type = stats.get("knowledge_type", "")

        if knowledge_type == "book" and domain in {"psychology", "risk"}:
            return 1000, 280, 55
        if knowledge_type == "book" and domain == "technical":
            return 900, 250, 50
        if knowledge_type == "report" and domain == "macro":
            return 650, 200, 45
        if knowledge_type == "book":
            return 800, 240, 50
        if knowledge_type == "report":
            return 650, 200, 45
        return 600, 180, 40

    def _apply_manifest_override(
        self,
        base_policy: ChunkPolicy,
        override: Dict[str, Any],
    ) -> Tuple[ChunkPolicy, str]:
        try:
            parent_size = self._bounded("parent_size", int(override.get("parent_size", base_policy.parent_size)))
            child_size = self._bounded("child_size", int(override.get("child_size", base_policy.child_size)))
            parent_overlap = self._bounded("parent_overlap", int(override.get("parent_overlap", base_policy.parent_overlap)))
            child_overlap = self._bounded("child_overlap", int(override.get("child_overlap", base_policy.child_overlap)))
            min_chunk_chars = self._bounded("min_chunk_chars", int(override.get("min_chunk_chars", base_policy.min_chunk_chars)))
        except (TypeError, ValueError):
            return base_policy, "Invalid manifest chunking override; using calibrated policy."

        parent_overlap = min(parent_overlap, parent_size // 2)
        child_overlap = min(child_overlap, child_size // 2)
        return ChunkPolicy(
            policy_id=str(override.get("policy_id") or "manifest_override"),
            parent_size=parent_size,
            parent_overlap=parent_overlap,
            child_size=child_size,
            child_overlap=child_overlap,
            min_chunk_chars=min_chunk_chars,
        ), ""

    def _custom_policy(self, chunk_size: Optional[int], overlap: Optional[int]) -> ChunkPolicy:
        size = self._bounded(
            "child_size",
            int(chunk_size or V3_CHUNK_POLICIES["global_default"].child_size),
            CUSTOM_POLICY_BOUNDS,
        )
        resolved_overlap = overlap if overlap is not None else min(size // 5, 80)
        resolved_overlap = min(self._bounded("child_overlap", int(resolved_overlap), CUSTOM_POLICY_BOUNDS), size // 2)
        return ChunkPolicy(
            "custom",
            parent_size=size,
            parent_overlap=resolved_overlap,
            child_size=size,
            child_overlap=resolved_overlap,
        )

    def _bounded(self, key: str, value: int, bounds: Optional[Dict[str, Tuple[int, int]]] = None) -> int:
        lower, upper = (bounds or POLICY_BOUNDS)[key]
        return max(lower, min(upper, int(value)))

    def _total_units(self, parsed_document: ParsedDocument) -> int:
        hints = parsed_document.metadata_hints or {}
        return int(hints.get("total_pages") or hints.get("section_count") or len(parsed_document.sections) or 1)

    def _document_type_from_parser(self, parsed_document: ParsedDocument) -> str:
        parser_type = (parsed_document.parser_type or "").lower()
        if parser_type.startswith("epub"):
            return "epub"
        if parser_type.startswith("pdf"):
            return "pdf"
        return ""

    def _is_table_like(self, line: str) -> bool:
        separators = line.count("|") + line.count("\t")
        digit_ratio = sum(ch.isdigit() for ch in line) / max(1, len(line))
        return separators >= 2 or digit_ratio > 0.35

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()
