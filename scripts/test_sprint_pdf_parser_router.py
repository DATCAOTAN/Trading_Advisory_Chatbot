import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if importlib.util.find_spec("dotenv") is None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if importlib.util.find_spec("fitz") is None:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "stub"
    sys.modules["fitz"] = fitz_stub


from src.services.knowledge.document_parser import (
    DocumentParser,
    DocumentParserRegistry,
    EpubDocumentParser,
    MinerUFailed,
    MinerUPdfParser,
    MinerUTimeout,
    MinerUUnavailable,
    PageProbeResult,
    ParsedDocument,
    ParsedSection,
    ParsePlan,
    ParsedDocumentMerger,
    PdfParsePlanner,
    PdfProbeResult,
    PdfParserRouter,
)
from src.services.knowledge.ingestion_fingerprint import IngestionFingerprintBuilder


class FakePyMuPDFParser(DocumentParser):
    supported_extensions = {".pdf"}

    def __init__(self):
        self.calls = []

    def parse(self, file_path: str):
        self.calls.append(file_path)
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:pymupdf",
            parser_version="fake-pymupdf",
            extraction_status="CHUNKED",
            extraction_quality=1.0,
            sections=[ParsedSection(text="PyMuPDF fallback text", page=1, location="page:1")],
            metadata_hints={
                "total_pages": 1,
                "empty_pages": 0,
                "quality": {
                    "total_pages": 1,
                    "total_chars": 21,
                    "total_words": 3,
                    "quality_score": 1.0,
                    "fallback_used": False,
                    "fallback_reason": "",
                },
            },
        )


class FakeProbeService:
    def __init__(self, probe):
        self.probe_result = probe
        self.calls = []

    def probe(self, file_path: str, metadata=None):
        self.calls.append({"file_path": file_path, "metadata": metadata})
        return self.probe_result


class FakeMinerUParser(DocumentParser):
    supported_extensions = {".pdf"}

    def __init__(self, mode="ok"):
        self.mode = mode
        self.calls = []
        self.command_name = "mineru"
        self.backend = "pipeline"
        self.method = "auto"
        self.timeout_seconds = 1800

    def parse(self, file_path: str, metadata=None):
        self.calls.append({"file_path": file_path, "metadata": metadata})
        if self.mode == "unavailable":
            raise MinerUUnavailable("missing mineru")
        if self.mode == "failed":
            raise MinerUFailed("mineru failed")
        if self.mode == "timeout":
            raise MinerUTimeout(123)
        status = "NEEDS_OCR" if self.mode == "needs_ocr_with_text" else "CHUNKED"
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:mineru",
            parser_version="fake-mineru",
            extraction_status=status,
            extraction_quality=0.5 if status == "NEEDS_OCR" else 1.0,
            sections=[ParsedSection(text="# Heading\n\nMinerU markdown text", page=1, location="page:1")],
            metadata_hints={
                "total_pages": 1,
                "empty_pages": 0,
                "image_count": 1,
                "table_count": 1,
                "quality": {
                    "total_pages": 1,
                    "total_chars": 29,
                    "total_words": 4,
                    "image_count": 1,
                    "table_count": 1,
                    "quality_score": 1.0,
                    "fallback_used": False,
                    "fallback_reason": "",
                },
            },
        )


def make_page(
    page: int,
    chars: int = 1000,
    image_count: int = 0,
    image_area_ratio: float = 0.0,
    table_like_ratio: float = 0.0,
    reasons=None,
):
    reasons = reasons or []
    complexity = 0.0
    if chars < 300:
        complexity += 0.18
    complexity += min(0.28, image_area_ratio)
    complexity += min(0.30, table_like_ratio)
    if reasons:
        complexity += 0.2
    return PageProbeResult(
        page_number=page - 1,
        human_page_number=page,
        chars=chars,
        words=max(1, chars // 5),
        image_count=image_count,
        image_area_ratio=image_area_ratio,
        table_count=1 if table_like_ratio > 0 else 0,
        table_like_ratio=table_like_ratio,
        empty_text=chars == 0,
        low_text_density=chars < 300,
        likely_chart_or_figure_caption="figure_caption" in reasons,
        likely_table_caption="table_caption" in reasons,
        likely_scan_or_ocr_page="scan_or_ocr_page" in reasons,
        multi_column_likelihood="multi_column" in reasons,
        complexity_score=min(1.0, complexity),
        reasons=reasons,
    )


def make_probe(
    file_path="sample.pdf",
    total_pages=10,
    chars_per_page=1000,
    knowledge_type="",
    pages=None,
    scanned_likelihood="low",
    needs_ocr=False,
):
    pages = pages or [make_page(i + 1, chars=chars_per_page) for i in range(total_pages)]
    total_chars = sum(page.chars for page in pages)
    total_words = sum(page.words for page in pages)
    return PdfProbeResult(
        file_path=file_path,
        total_pages=total_pages,
        total_chars=total_chars,
        total_words=total_words,
        avg_chars_per_page=total_chars / max(1, total_pages),
        empty_pages_count=sum(1 for page in pages if page.empty_text),
        image_count=sum(page.image_count for page in pages),
        image_count_per_page=[page.image_count for page in pages],
        table_count=sum(page.table_count for page in pages),
        table_like_ratio=sum(page.table_like_ratio for page in pages) / max(1, len(pages)),
        scanned_likelihood=scanned_likelihood,
        needs_ocr=needs_ocr,
        layout_complexity="high" if any(page.complexity_score >= 0.45 for page in pages) else "low",
        page_metrics=pages,
        inferred_knowledge_type=knowledge_type,
    )


class PdfParserRouterTests(unittest.TestCase):
    def test_pymupdf_mode_keeps_pymupdf_behavior(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        probe = make_probe()
        probe_service = FakeProbeService(probe)
        router = PdfParserRouter(mode="pymupdf", mineru_parser=mineru, fallback_parser=fallback, probe_service=probe_service)

        parsed = router.parse("sample.pdf", {"document_metadata": {"doc_id": "doc"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertEqual(parsed.parser_id, "pdf:pymupdf")
        self.assertEqual(parsed.text, "PyMuPDF fallback text")
        self.assertEqual(len(probe_service.calls), 1)
        self.assertEqual(len(mineru.calls), 0)
        self.assertEqual(len(fallback.calls), 1)
        self.assertFalse(parsed.quality["fallback_used"])
        self.assertEqual(parsed.metadata_hints["parse_plan_type"], "pymupdf_only")

    def test_mineru_first_report_attempts_mineru_first(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"domain": "macro", "knowledge_type": "report"}})

        self.assertEqual(parsed.parser_type, "pdf:mineru")
        self.assertIn("MinerU markdown text", parsed.text)
        self.assertEqual(len(mineru.calls), 1)
        self.assertEqual(mineru.calls[0]["metadata"]["routing_metadata"]["domain"], "macro")
        self.assertEqual(len(fallback.calls), 1)
        self.assertEqual(parsed.metadata_hints["parse_plan_type"], "mineru_full")

    def test_mineru_first_book_defaults_to_pymupdf(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="book")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "book"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertEqual(len(mineru.calls), 0)
        self.assertEqual(len(fallback.calls), 1)
        self.assertFalse(parsed.quality["fallback_used"])
        self.assertEqual(parsed.metadata_hints["parse_plan_type"], "pymupdf_only")
        self.assertNotIn("non_book_mineru_first", str(parsed.metadata_hints))

    def test_mineru_first_book_can_be_enabled_by_config(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            mineru_parse_books=True,
            probe_service=FakeProbeService(make_probe(knowledge_type="book")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "book"}})

        self.assertEqual(parsed.parser_type, "pdf:mineru")
        self.assertEqual(len(mineru.calls), 1)
        self.assertEqual(len(fallback.calls), 1)
        self.assertTrue(parsed.metadata_hints["mineru_parse_books"])

    def test_manifest_parser_preferred_mineru_overrides_book_default(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="book")),
        )

        parsed = router.parse(
            "sample.pdf",
            {"routing_metadata": {"knowledge_type": "book"}, "parser": {"preferred": "mineru"}},
        )

        self.assertEqual(parsed.parser_type, "pdf:mineru")
        self.assertEqual(len(mineru.calls), 1)
        self.assertEqual(len(fallback.calls), 1)

    def test_mineru_command_includes_backend_and_method(self):
        parser = MinerUPdfParser(
            command_name="/opt/mineru_venv/bin/mineru",
            backend="pipeline",
            method="auto",
            timeout_seconds=1800,
        )

        command = parser._build_command("input.pdf", "/tmp/mineru_parse")

        self.assertEqual(command[:5], ["/opt/mineru_venv/bin/mineru", "-p", "input.pdf", "-o", "/tmp/mineru_parse"])
        self.assertIn("--backend", command)
        self.assertEqual(command[command.index("--backend") + 1], "pipeline")
        self.assertIn("-m", command)
        self.assertEqual(command[command.index("-m") + 1], "auto")

    def test_mineru_timeout_falls_back_without_crashing(self):
        mineru = FakeMinerUParser(mode="timeout")
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "report"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertTrue(parsed.quality["fallback_used"])
        self.assertIn("mineru_timeout", parsed.quality["fallback_reason"])

    def test_missing_mineru_dependency_falls_back_without_crashing(self):
        mineru = FakeMinerUParser(mode="unavailable")
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "report"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertTrue(parsed.quality["fallback_used"])
        self.assertIn("mineru_unavailable", parsed.quality["fallback_reason"])

    def test_mineru_exception_falls_back_without_crashing(self):
        mineru = FakeMinerUParser(mode="failed")
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "report"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertTrue(parsed.quality["fallback_used"])
        self.assertIn("mineru_failed", parsed.quality["fallback_reason"])

    def test_mineru_needs_ocr_with_usable_text_does_not_fallback(self):
        mineru = FakeMinerUParser(mode="needs_ocr_with_text")
        fallback = FakePyMuPDFParser()
        router = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "report"}})

        self.assertEqual(parsed.parser_type, "pdf:mineru")
        self.assertEqual(parsed.extraction_status, "NEEDS_OCR")
        self.assertIn("usable text was preserved", "; ".join(parsed.warnings))
        self.assertEqual(len(fallback.calls), 1)

    def test_adaptive_book_with_selected_complex_pages_merges_selective_output(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        complex_probe = make_probe(
            knowledge_type="book",
            pages=[
                make_page(1, chars=1000),
                make_page(2, chars=120, image_count=1, image_area_ratio=0.35, reasons=["large_image_area"]),
                make_page(3, chars=1000),
            ],
            total_pages=3,
        )
        router = PdfParserRouter(
            mode="adaptive",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(complex_probe),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "book"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf+mineru_selective")
        self.assertEqual(parsed.metadata_hints["parse_plan_type"], "pymupdf_plus_mineru_selective")
        self.assertEqual(parsed.metadata_hints["selective_page_count"], 1)

    def test_adaptive_clean_text_book_ignores_weak_caption_pages(self):
        mineru = FakeMinerUParser()
        fallback = FakePyMuPDFParser()
        clean_probe = make_probe(
            knowledge_type="book",
            pages=[
                make_page(1, chars=1200),
                make_page(2, chars=1400, reasons=["figure_caption"]),
                make_page(3, chars=1300, reasons=["multi_column"]),
                make_page(4, chars=1250),
            ],
            total_pages=4,
        )
        self.assertEqual(clean_probe.selected_candidate_pages, [])
        router = PdfParserRouter(
            mode="adaptive",
            mineru_parser=mineru,
            fallback_parser=fallback,
            probe_service=FakeProbeService(clean_probe),
        )

        parsed = router.parse("sample.pdf", {"routing_metadata": {"knowledge_type": "book"}})

        self.assertEqual(parsed.parser_type, "pdf:pymupdf")
        self.assertEqual(len(mineru.calls), 0)
        self.assertEqual(parsed.metadata_hints["parse_plan_type"], "pymupdf_only")
        self.assertEqual(parsed.metadata_hints["parse_plan_reason"], "book_text_based_pymupdf")

    def test_planner_simple_long_text_report_can_use_pymupdf_only(self):
        planner = PdfParsePlanner()
        probe = make_probe(knowledge_type="report", total_pages=100, chars_per_page=1400)

        plan = planner.build_plan("report.pdf", {"routing_metadata": {"knowledge_type": "report"}}, probe, "adaptive", False)

        self.assertEqual(plan.plan_type, "pymupdf_only")
        self.assertEqual(plan.reason, "simple_text_report_pymupdf")

    def test_planner_large_report_with_candidates_uses_selective_mineru(self):
        planner = PdfParsePlanner()
        pages = [make_page(i + 1, chars=1200) for i in range(69)]
        pages[12] = make_page(13, chars=150, image_count=1, image_area_ratio=0.35, reasons=["large_image_area"])
        probe = make_probe(knowledge_type="report", pages=pages, total_pages=69)

        plan = planner.build_plan("commodity_markets_outlook.pdf", {"routing_metadata": {"knowledge_type": "report"}}, probe, "adaptive", False)

        self.assertEqual(plan.plan_type, "pymupdf_plus_mineru_selective")
        self.assertEqual(plan.reason, "large_report_selective_mineru")
        self.assertEqual(plan.selected_pages, [13])

    def test_planner_large_report_without_candidates_avoids_full_mineru(self):
        planner = PdfParsePlanner()
        probe = make_probe(knowledge_type="report", total_pages=69, chars_per_page=500)

        plan = planner.build_plan("large_report.pdf", {"routing_metadata": {"knowledge_type": "report"}}, probe, "adaptive", False)

        self.assertEqual(plan.plan_type, "pymupdf_only")
        self.assertEqual(plan.reason, "large_report_avoid_full_mineru")

    def test_planner_infers_knowledge_type_from_book_path(self):
        planner = PdfParsePlanner()
        probe = make_probe(file_path="data/knowledge_repository/book/technical/topic/owner/file.pdf")

        plan = planner.build_plan(
            "data/knowledge_repository/book/technical/topic/owner/file.pdf",
            {},
            probe,
            "adaptive",
            False,
        )

        self.assertEqual(plan.knowledge_type, "book")
        self.assertIn(plan.plan_type, {"pymupdf_only", "pymupdf_plus_mineru_selective"})
        self.assertNotEqual(plan.reason, "non_book_mineru_first")

    def test_common_parsed_document_output_contract_is_stable(self):
        parsed = FakeMinerUParser().parse("sample.pdf")

        self.assertEqual(parsed.parser_id, "pdf:mineru")
        self.assertTrue(parsed.text)
        self.assertEqual(parsed.quality["total_pages"], 1)
        self.assertEqual(parsed.quality["image_count"], 1)
        self.assertEqual(parsed.quality["table_count"], 1)
        self.assertFalse(parsed.quality["fallback_used"])

    def test_fingerprint_includes_mineru_runtime_fields(self):
        parsed = PdfParserRouter(
            mode="mineru_first",
            mineru_parser=FakeMinerUParser(),
            fallback_parser=FakePyMuPDFParser(),
            probe_service=FakeProbeService(make_probe(knowledge_type="report")),
        ).parse("sample.pdf", {"routing_metadata": {"knowledge_type": "report"}})
        chunk_result = {
            "chunk_stats": {
                "selected_chunk_policy": "macro_report_default",
                "parent_size_chars": 3600,
                "child_size_chars": 900,
                "parent_overlap_chars": 360,
                "child_overlap_chars": 180,
            },
            "operational_metadata": {
                "chunker_version": "test",
                "chunk_policy_id": "macro_report_default",
                "pdf_parser_mode": parsed.metadata_hints.get("pdf_parser_mode", ""),
                "mineru_command": parsed.metadata_hints.get("mineru_command", ""),
                "mineru_backend": parsed.metadata_hints.get("mineru_backend", ""),
                "mineru_method": parsed.metadata_hints.get("mineru_method", ""),
                "mineru_timeout_seconds": parsed.metadata_hints.get("mineru_timeout_seconds", ""),
                "mineru_parse_books": parsed.metadata_hints.get("mineru_parse_books", ""),
                "parser_output_schema_version": parsed.metadata_hints.get("parser_output_schema_version", ""),
                "mineru_selective_book_pages_enabled": parsed.metadata_hints.get("mineru_selective_book_pages_enabled", ""),
                "mineru_selective_max_pages_per_doc": parsed.metadata_hints.get("mineru_selective_max_pages_per_doc", ""),
                "mineru_selective_max_ranges_per_doc": parsed.metadata_hints.get("mineru_selective_max_ranges_per_doc", ""),
                "mineru_selective_low_text_chars": parsed.metadata_hints.get("mineru_selective_low_text_chars", ""),
                "mineru_selective_table_like_threshold": parsed.metadata_hints.get("mineru_selective_table_like_threshold", ""),
                "mineru_selective_image_area_ratio": parsed.metadata_hints.get("mineru_selective_image_area_ratio", ""),
                "mineru_full_max_pages_soft_limit": parsed.metadata_hints.get("mineru_full_max_pages_soft_limit", ""),
                "mineru_full_complex_page_ratio_threshold": parsed.metadata_hints.get("mineru_full_complex_page_ratio_threshold", ""),
            },
        }

        fingerprint = IngestionFingerprintBuilder().build("checksum", parsed, chunk_result)

        self.assertEqual(fingerprint["payload"]["parser_name"], "pdf:mineru")
        self.assertEqual(fingerprint["payload"]["pdf_parser_mode"], "mineru_first")
        self.assertTrue(fingerprint["payload"]["mineru_command"])
        self.assertEqual(fingerprint["payload"]["mineru_backend"], "pipeline")
        self.assertEqual(fingerprint["payload"]["mineru_method"], "auto")
        self.assertEqual(fingerprint["payload"]["mineru_timeout_seconds"], 1800)
        self.assertFalse(fingerprint["payload"]["mineru_parse_books"])
        self.assertEqual(
            fingerprint["payload"]["parser_output_schema_version"],
            parsed.metadata_hints.get("parser_output_schema_version"),
        )
        self.assertEqual(
            fingerprint["payload"]["mineru_selective_max_pages_per_doc"],
            parsed.metadata_hints.get("mineru_selective_max_pages_per_doc"),
        )
        self.assertEqual(
            fingerprint["payload"]["mineru_full_max_pages_soft_limit"],
            parsed.metadata_hints.get("mineru_full_max_pages_soft_limit"),
        )

    def test_epub_parser_remains_registry_supported_and_unchanged(self):
        registry = DocumentParserRegistry(parsers=[PdfParserRouter(fallback_parser=FakePyMuPDFParser()), EpubDocumentParser()])

        parser = registry.get_parser("book.epub")

        self.assertIsInstance(parser, EpubDocumentParser)
        self.assertIn(".epub", registry.supported_extensions)
        self.assertIn(".pdf", registry.supported_extensions)

    def test_no_qdrant_delete_or_recreate_in_parser_layer(self):
        parser_source = (PROJECT_ROOT / "src" / "services" / "knowledge" / "document_parser.py").read_text(encoding="utf-8")

        self.assertNotIn("delete_collection", parser_source)
        self.assertNotIn("recreate_collection", parser_source)
        self.assertNotIn("upsert_document", parser_source)
        self.assertNotIn("non_book_mineru_first", parser_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
