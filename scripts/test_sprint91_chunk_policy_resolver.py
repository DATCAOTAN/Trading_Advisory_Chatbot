import contextlib
import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


if importlib.util.find_spec("fitz") is None:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "stub"
    sys.modules["fitz"] = fitz_stub


from src.services.knowledge.chunk_builder import ChunkBuilder
from src.services.knowledge.chunk_policy_resolver import (
    ChunkPolicyResolver,
    POLICY_BOUNDS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
)
from src.services.knowledge.document_parser import ParsedDocument, ParsedSection


def metadata(domain="", subdomain="", knowledge_type="", document_type="pdf", override=None):
    data = {
        "doc_id": "doc_policy_fixture",
        "lifecycle": "ACTIVE",
        "routing_metadata": {
            "domain": domain,
            "subdomain": subdomain,
            "knowledge_type": knowledge_type,
            "source_tier": "tier2",
            "language": "en",
        },
        "document_metadata": {
            "doc_id": "doc_policy_fixture",
            "title": "Policy Fixture",
            "author": "Tester",
            "publisher": "Fixture",
            "checksum": "",
            "document_type": document_type,
        },
    }
    if override is not None:
        data["chunking_override"] = override
    return data


def parsed_document(document_type="pdf", chars=8000, sections=2, table_like=False):
    text_unit = "price action moving average trend following context "
    if table_like:
        text_unit = "2020 | 2021 | 2022 | 12345 | 67890\n"
    text = (text_unit * max(1, chars // max(1, len(text_unit))))[:chars]
    parsed_sections = []
    for index in range(sections):
        parsed_sections.append(
            ParsedSection(
                text=text,
                page=index + 1 if document_type == "pdf" else None,
                chapter=f"Chapter {index + 1}" if document_type == "epub" else "",
                section=f"Section {index + 1}",
                location=f"spine:{index + 1}" if document_type == "epub" else f"page:{index + 1}",
                spine_index=index + 1 if document_type == "epub" else None,
                href=f"chapter{index + 1}.xhtml" if document_type == "epub" else "",
                paragraph_index=1,
            )
        )
    return ParsedDocument(
        file_path=f"fixture.{document_type or 'txt'}",
        parser_type=f"{document_type}:fake" if document_type else "unknown:fake",
        parser_version="fake",
        extraction_status="CHUNKED",
        extraction_quality=1.0,
        sections=parsed_sections,
        metadata_hints={
            "total_pages": sections if document_type == "pdf" else 0,
            "section_count": sections,
        },
    )


class ChunkPolicyResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = ChunkPolicyResolver()

    def resolve(self, meta, parsed=None):
        return self.resolver.resolve(meta, parsed or parsed_document())

    def test_exact_policy_match(self):
        decision = self.resolve(metadata("technical", "indicators", "book", "pdf"))

        self.assertEqual(decision.policy.policy_id, "technical_indicators")
        self.assertEqual(decision.fallback_level, "exact")
        self.assertGreaterEqual(decision.policy.parent_size // TOKEN_ESTIMATE_CHARS_PER_TOKEN, 900)
        self.assertGreaterEqual(decision.policy.child_size // TOKEN_ESTIMATE_CHARS_PER_TOKEN, 250)

    def test_domain_default_fallback(self):
        decision = self.resolve(metadata("technical", "candlestick", "book", "pdf"))

        self.assertEqual(decision.policy.policy_id, "technical_default")
        self.assertEqual(decision.fallback_level, "domain_default")

    def test_knowledge_type_fallback(self):
        decision = self.resolve(metadata("", "", "report", "unknown"), parsed_document(document_type=""))

        self.assertEqual(decision.policy.policy_id, "report_default")
        self.assertEqual(decision.fallback_level, "knowledge_type_default")

    def test_document_type_fallback_for_epub_book(self):
        decision = self.resolve(metadata("", "", "book", "epub"), parsed_document(document_type="epub"))

        self.assertEqual(decision.policy.policy_id, "epub_book_default")
        self.assertEqual(decision.fallback_level, "document_type_default")

    def test_global_fallback(self):
        decision = self.resolve(metadata("", "", "", ""), parsed_document(document_type=""))

        self.assertEqual(decision.policy.policy_id, "global_default")
        self.assertEqual(decision.fallback_level, "global_default")

    def test_auto_calibration_stays_within_bounds(self):
        decision = self.resolve(
            metadata("technical", "indicators", "book", "pdf"),
            parsed_document(document_type="pdf", chars=900_000, sections=5, table_like=True),
        )

        self.assertGreaterEqual(decision.policy.parent_size, POLICY_BOUNDS["parent_size"][0])
        self.assertLessEqual(decision.policy.parent_size, POLICY_BOUNDS["parent_size"][1])
        self.assertGreaterEqual(decision.policy.child_size, POLICY_BOUNDS["child_size"][0])
        self.assertLessEqual(decision.policy.child_size, POLICY_BOUNDS["child_size"][1])
        self.assertLessEqual(decision.policy.child_overlap, decision.policy.child_size // 2)

    def test_manual_override_works_when_valid(self):
        decision = self.resolve(
            metadata(
                "technical",
                "indicators",
                "book",
                "pdf",
                override={
                    "policy_id": "custom_manifest",
                    "parent_size": 4400,
                    "parent_overlap": 440,
                    "child_size": 1200,
                    "child_overlap": 220,
                },
            )
        )

        self.assertEqual(decision.policy.policy_id, "custom_manifest")
        self.assertEqual(decision.policy.parent_size, 4400)
        self.assertEqual(decision.policy.child_size, 1200)
        self.assertEqual(decision.fallback_level, "manifest_override")

    def test_too_small_manual_override_is_raised_by_quality_gate(self):
        decision = self.resolve(
            metadata(
                "technical",
                "indicators",
                "book",
                "pdf",
                override={
                    "policy_id": "tiny_manifest",
                    "parent_size": 900,
                    "parent_overlap": 80,
                    "child_size": 220,
                    "child_overlap": 30,
                },
            )
        )

        self.assertEqual(decision.policy.policy_id, "tiny_manifest")
        self.assertGreaterEqual(decision.policy.parent_size // TOKEN_ESTIMATE_CHARS_PER_TOKEN, 900)
        self.assertGreaterEqual(decision.policy.child_size // TOKEN_ESTIMATE_CHARS_PER_TOKEN, 250)
        self.assertTrue(any("quality gate" in warning.lower() for warning in decision.warnings))

    def test_bad_manual_override_falls_back_safely(self):
        decision = self.resolve(
            metadata("technical", "indicators", "book", "pdf", override={"child_size": "nope"})
        )

        self.assertEqual(decision.policy.policy_id, "technical_indicators")
        self.assertTrue(decision.warnings)

    def test_epub_chunking_preserves_chapter_section_location(self):
        builder = ChunkBuilder()
        result = builder.build_chunks_from_parsed(
            parsed_document(document_type="epub", chars=4000, sections=1),
            metadata("", "", "book", "epub"),
        )

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "epub_book_default")
        self.assertEqual(result["chunks"][0]["chapter"], "Chapter 1")
        self.assertEqual(result["chunks"][0]["section_title"], "Section 1")
        self.assertEqual(result["chunks"][0]["location"], "spine:1")
        self.assertEqual(result["chunks"][0]["href"], "chapter1.xhtml")

    def test_pdf_chunking_still_works(self):
        builder = ChunkBuilder()
        result = builder.build_chunks_from_parsed(
            parsed_document(document_type="pdf", chars=4000, sections=1),
            metadata("technical", "indicators", "book", "pdf"),
        )

        self.assertEqual(result["status"], "CHUNKED")
        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "technical_indicators")
        self.assertEqual(result["chunks"][0]["page"], 1)

    def test_logs_include_selected_policy_and_parameters(self):
        builder = ChunkBuilder()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            builder.build_chunks_from_parsed(
                parsed_document(document_type="pdf", chars=4000, sections=1),
                metadata("technical", "candlestick", "book", "pdf"),
            )

        output = stdout.getvalue()
        self.assertIn("[ChunkPolicy]", output)
        self.assertIn("selected_policy=technical_default", output)
        self.assertIn("unit=characters", output)
        self.assertIn("token_estimate_unit=chars/4", output)
        self.assertIn("child_size_chars=", output)
        self.assertIn("parent_target_tokens=", output)
        self.assertIn("[ChunkBuilder]", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
