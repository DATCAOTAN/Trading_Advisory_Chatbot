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


try:
    import fitz  # noqa: F401
except ImportError:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "test-stub"
    fitz_stub.open = lambda *args, **kwargs: None
    sys.modules["fitz"] = fitz_stub


from scripts.compare_chunk_stats import collect_stats
from src.services.knowledge import chunk_builder as chunk_builder_module
from src.services.knowledge.chunk_builder import ChunkBuilder
from src.services.knowledge.document_parser import ParsedDocument, ParsedSection


class FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self):
        return self.text


class FakePdf:
    def __init__(self, pages):
        self.pages = [FakePage(text) for text in pages]
        self.closed = False

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def close(self):
        self.closed = True


class FakeParserRegistry:
    def __init__(self, pages):
        self.pages = list(pages)

    def parse(self, file_path, metadata):
        total_pages = len(self.pages)
        non_empty = [
            (index, str(text or ""))
            for index, text in enumerate(self.pages, start=1)
            if str(text or "").strip()
        ]
        empty_pages = total_pages - len(non_empty)

        if total_pages == 0 or not non_empty:
            status = "EMPTY_DOCUMENT"
            quality = 0.0
            sections = []
        else:
            quality = len(non_empty) / max(total_pages, 1)
            if quality < 0.2:
                status = "NEEDS_OCR"
                sections = []
            else:
                status = "PARTIAL_TEXT" if quality < 0.8 else "CHUNKED"
                sections = [
                    ParsedSection(text=text, page=page_number, paragraph_index=page_number)
                    for page_number, text in non_empty
                ]

        return ParsedDocument(
            file_path=str(file_path),
            parser_type="test:fake",
            parser_version="fake-parser-v1",
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            warnings=[] if sections else [status],
            metadata_hints={
                "quality": {
                    "total_pages": total_pages,
                    "empty_pages": empty_pages,
                    "quality_score": quality,
                    "needs_ocr": status == "NEEDS_OCR",
                }
            },
        )


class FakeResolver:
    def __init__(self, metadata):
        self.metadata = metadata

    def resolve(self, file_path):
        return self.metadata


class AdaptiveChunkingTests(unittest.TestCase):
    def setUp(self):
        self.original_open = chunk_builder_module.fitz.open
        self.original_parser_registry = chunk_builder_module.DocumentParserRegistry

    def tearDown(self):
        chunk_builder_module.fitz.open = self.original_open
        chunk_builder_module.DocumentParserRegistry = self.original_parser_registry

    def metadata(self, domain="technical", subdomain="indicators", knowledge_type="book"):
        return {
            "doc_id": f"{knowledge_type}_{domain}_{subdomain}_fixture_v1",
            "lifecycle": "ACTIVE",
            "routing_metadata": {
                "domain": domain,
                "subdomain": subdomain,
                "knowledge_type": knowledge_type,
                "source_tier": "tier2",
                "language": "en",
                "strategies": ["trend_following"],
                "assets": ["forex"],
                "timeframe_focus": ["h1"],
            },
            "document_metadata": {
                "doc_id": f"{knowledge_type}_{domain}_{subdomain}_fixture_v1",
                "title": "Fixture",
                "author": "Tester",
                "publisher": "Test Publisher",
                "checksum": "",
            },
        }

    def patch_pdf_text(self, pages):
        chunk_builder_module.fitz.open = lambda _path: FakePdf(pages)
        chunk_builder_module.DocumentParserRegistry = lambda: FakeParserRegistry(pages)

    def build_with_text(self, metadata):
        text = "EMA moving average trend following market structure support resistance. " * 80
        self.patch_pdf_text([text])
        return ChunkBuilder().build_chunks("fixture.pdf", metadata)

    def test_v3_resolves_technical_indicators_policy(self):
        result = self.build_with_text(self.metadata("technical", "indicators"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "technical_indicators")
        self.assertTrue(all(c["chunk_policy_id"] == "technical_indicators" for c in result["chunks"]))

    def test_v3_resolves_price_action_policy(self):
        result = self.build_with_text(self.metadata("technical", "price_action"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "technical_price_action")

    def test_v3_resolves_smc_policy(self):
        result = self.build_with_text(self.metadata("technical", "smc"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "technical_smc")

    def test_v3_resolves_macro_report_policy(self):
        result = self.build_with_text(self.metadata("macro", "fomc", knowledge_type="report"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "macro_report_default")

    def test_v3_resolves_risk_policy(self):
        result = self.build_with_text(self.metadata("risk", "position_sizing"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "risk_management")

    def test_unknown_metadata_falls_back_to_default_policy(self):
        result = self.build_with_text(self.metadata("general", "unknown"))

        self.assertEqual(result["chunk_stats"]["selected_chunk_policy"], "book_default")

    def test_chunk_output_includes_policy_and_parent_traceability(self):
        result = self.build_with_text(self.metadata("technical", "indicators"))
        chunk = result["chunks"][0]

        self.assertEqual(chunk["chunk_level"], "child")
        self.assertEqual(chunk["chunk_policy_id"], "technical_indicators")
        self.assertTrue(chunk["parent_chunk_id"])
        self.assertTrue(chunk["parent_text"])
        self.assertIn("char_count", chunk)
        self.assertIn("token_count", chunk)

    def test_chunk_stats_include_extracted_counts_and_chunk_counts(self):
        result = self.build_with_text(self.metadata("technical", "indicators"))
        stats = result["chunk_stats"]

        self.assertGreater(stats["extracted_char_count"], 0)
        self.assertGreater(stats["extracted_word_count"], 0)
        self.assertGreater(stats["parent_chunk_count"], 0)
        self.assertEqual(stats["indexed_chunk_count"], len(result["chunks"]))
        self.assertGreater(stats["average_chunk_size"], 0)

    def test_empty_whitespace_chunks_are_not_produced(self):
        self.patch_pdf_text(["   ", "\n\t", "valid trading text " * 20])

        result = ChunkBuilder(chunk_size=120, overlap=20).build_chunks(
            "fixture.pdf",
            self.metadata("technical", "indicators"),
        )

        self.assertTrue(all(chunk["text"].strip() for chunk in result["chunks"]))
        self.assertEqual(result["status"], "PARTIAL_TEXT")
        self.assertGreater(len(result["chunks"]), 0)

    def test_compare_chunk_stats_uses_chunk_builder_without_indexing(self):
        metadata = self.metadata("technical", "indicators")
        self.patch_pdf_text(["EMA trend following " * 80])

        stats = collect_stats("fixture.pdf", resolver=FakeResolver(metadata))

        self.assertEqual(stats["status"], "CHUNKED")
        self.assertEqual(stats["selected_chunk_policy"], "technical_indicators")
        self.assertGreater(stats["extracted_char_count"], 0)
        self.assertGreater(stats["indexed_chunk_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
