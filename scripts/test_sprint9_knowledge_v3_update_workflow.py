import importlib.util
import hashlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


if importlib.util.find_spec("dotenv") is None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if importlib.util.find_spec("streamlit") is None:
    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    sys.modules["streamlit"] = streamlit_stub

if importlib.util.find_spec("fitz") is None:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "stub"
    sys.modules["fitz"] = fitz_stub


from src.services.knowledge.catalog_manager import KnowledgeCatalog
from src.services.knowledge.document_parser import ParsedDocument, ParsedSection
from src.services.knowledge.retrieval_smoke import RetrievalSmokeResult, RetrievalSmokeStatus
from src.config import Config
from src.services.knowledge.update_service import IngestionStatus, KnowledgeUpdateService


class FakeParserRegistry:
    supported_extensions = {".pdf", ".epub"}

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        stem = path.stem
        if "empty" in stem:
            return ParsedDocument(
                file_path=file_path,
                parser_type=self._parser_type(path),
                parser_version="fake",
                extraction_status="EMPTY_DOCUMENT",
                extraction_quality=0.0,
            )
        if "ocr" in stem:
            return ParsedDocument(
                file_path=file_path,
                parser_type=self._parser_type(path),
                parser_version="fake",
                extraction_status="NEEDS_OCR",
                extraction_quality=0.0,
            )

        text = (
            f"{stem} technical trading knowledge. "
            "Moving averages, RSI, risk, discipline, and market structure context. "
            "This fake parsed text is deliberately long enough to create chunks. "
        ) * 20
        section = ParsedSection(
            text=text,
            page=1 if path.suffix.lower() == ".pdf" else None,
            chapter="Chapter 1" if path.suffix.lower() == ".epub" else "",
            section="Intro",
            location="spine:1" if path.suffix.lower() == ".epub" else "page:1",
            spine_index=1 if path.suffix.lower() == ".epub" else None,
            href="chapter1.xhtml" if path.suffix.lower() == ".epub" else "",
        )
        return ParsedDocument(
            file_path=file_path,
            parser_type=self._parser_type(path),
            parser_version="fake",
            extraction_status="CHUNKED",
            extraction_quality=1.0,
            sections=[section],
            metadata_hints={"section_count": 1, "total_pages": 1 if path.suffix.lower() == ".pdf" else 0},
        )

    def _parser_type(self, path: Path) -> str:
        return "epub:fake" if path.suffix.lower() == ".epub" else "pdf:fake"


class FakeVectorService:
    def __init__(self, catalog: KnowledgeCatalog, fail_names=None, fail_result=None):
        self.catalog = catalog
        self.calls = []
        self.deleted_doc_ids = []
        self.fail_names = set(fail_names or [])
        self.fail_result = fail_result or {}
        self.last_index_result = {}

    def upsert_document(self, doc_id, chunks, job_id, **kwargs):
        self.calls.append({"doc_id": doc_id, "chunks": chunks, "job_id": job_id, "kwargs": kwargs})
        if any(name in doc_id for name in self.fail_names):
            status = self.fail_result.get("status", "FAILED")
            reason = self.fail_result.get("reason", "fake failure")
            self.last_index_result = {
                "status": status,
                "reason": reason,
                "category": self.fail_result.get("category", "provider_error"),
                "retryable": self.fail_result.get("retryable", False),
                "cache_hits": self.fail_result.get("cache_hits", 0),
                "cache_misses": self.fail_result.get("cache_misses", 0),
                "rate_limit_count": self.fail_result.get("rate_limit_count", 0),
            }
            self.catalog.release_index_lock(doc_id, job_id, status, reason)
            return False
        self.last_index_result = {
            "status": "INDEXED",
            "vectors": len(chunks),
            "cache_hits": 0,
            "cache_misses": len(chunks),
            "rate_limit_count": 0,
        }
        self.catalog.release_index_lock(doc_id, job_id, "INDEXED")
        return True

    def delete_by_doc_id(self, doc_id, collection_name="knowledge_current"):
        self.deleted_doc_ids.append(doc_id)


class FakeSmokeEvaluator:
    def __init__(self, status=RetrievalSmokeStatus.PASS):
        self.status = status
        self.calls = []

    def evaluate_document(self, doc_id, metadata):
        self.calls.append({"doc_id": doc_id, "metadata": metadata})
        return RetrievalSmokeResult(
            status=self.status,
            reason="" if self.status == RetrievalSmokeStatus.PASS else "fake missing",
            query="fake smoke query",
            top_source_title="Fake Title",
            top_source_author="Fake Author",
            top_source_organization="Fake Org",
            top_source_domain="technical",
            top_source_subdomain="indicators",
            top_source_event_type="FAKE",
            top_source_period="2026-01",
            top_k_returned=1,
        )


class KnowledgeV3UpdateWorkflowTests(unittest.TestCase):
    def make_service(self, tmpdir, fail_names=None, smoke_evaluator=None, fail_result=None):
        root = Path(tmpdir) / "data" / "knowledge_repository"
        catalog = KnowledgeCatalog(str(Path(tmpdir) / "catalog.sqlite"))
        vector = FakeVectorService(catalog, fail_names=fail_names, fail_result=fail_result)
        service = KnowledgeUpdateService(
            repository_path=str(root),
            parser_registry=FakeParserRegistry(),
            catalog=catalog,
            vector_service=vector,
            retrieval_smoke_evaluator=smoke_evaluator,
        )
        return root, service, vector

    def write_doc(self, root: Path, relative: str, content: bytes = b"content") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_scan_detects_pdf_epub_and_unsupported(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(tmpdir)
            self.write_doc(root, "book/technical/indicators/john_murphy/a.pdf")
            self.write_doc(root, "book/risk/psychology/mark_douglas/b.epub")
            self.write_doc(root, "book/risk/psychology/mark_douglas/notes.txt")
            self.write_doc(root, "book/.gitkeep")

            report = service.scan_repository()

            self.assertEqual(report.discovered, 3)
            statuses = sorted(result.status for result in report.results)
            self.assertIn(IngestionStatus.DISCOVERED, statuses)
            self.assertIn(IngestionStatus.SKIPPED_UNSUPPORTED_EXTENSION, statuses)

    def test_missing_manifest_is_created_and_checksum_is_filled_for_pdf(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/new_author/my_book.pdf")

            result = service.update_file(str(pdf))

            manifest = pdf.with_suffix(".manifest.yaml")
            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertTrue(result.manifest_created)
            self.assertTrue(manifest.exists())
            self.assertTrue(result.checksum)
            self.assertEqual(result.domain, "technical")
            self.assertEqual(result.subdomain, "indicators")
            self.assertEqual(len(vector.calls), 1)

    def test_indexed_file_records_retrieval_smoke_status(self):
        with TemporaryDirectory() as tmpdir:
            smoke = FakeSmokeEvaluator()
            root, service, _ = self.make_service(tmpdir, smoke_evaluator=smoke)
            pdf = self.write_doc(root, "book/technical/indicators/new_author/my_book.pdf")

            result = service.update_file(str(pdf))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.retrieval_smoke_status, RetrievalSmokeStatus.PASS)
            self.assertEqual(result.retrieval_smoke_query, "fake smoke query")
            self.assertEqual(result.top_source_title, "Fake Title")
            self.assertEqual(result.top_source_organization, "Fake Org")
            self.assertEqual(len(smoke.calls), 1)

    def test_report_fomc_metadata_is_inferred_from_path_and_filename(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            pdf = self.write_doc(
                root,
                "report/macro/central_bank/federal_reserve/fomc_statement_2026_06_17.pdf",
            )

            result = service.update_file(str(pdf))
            call = vector.calls[0]
            document_metadata = call["chunks"][0]["document_metadata"]
            routing_metadata = call["chunks"][0]["routing_metadata"]

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.domain, "macro")
            self.assertEqual(result.subdomain, "central_bank")
            self.assertEqual(result.chunk_policy_id, "macro_report_default")
            self.assertEqual(document_metadata["organization"], "Federal Reserve")
            self.assertEqual(document_metadata["event_type"], "FOMC")
            self.assertEqual(document_metadata["period"], "2026-06-17")
            self.assertEqual(document_metadata["published_date"], "2026-06-17")
            self.assertEqual(document_metadata["country"], "US")
            self.assertEqual(routing_metadata["knowledge_type"], "report")

    def test_fomc_minutes_and_sep_have_distinct_metadata_and_doc_ids(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            minutes = self.write_doc(
                root,
                "report/macro/central_bank/federal_reserve/fomc_minutes_2026_03_18.pdf",
                b"minutes",
            )
            sep = self.write_doc(
                root,
                "report/macro/central_bank/federal_reserve/summary_of_economic_projections_2026_03_18.pdf",
                b"sep",
            )

            minutes_result = service.update_file(str(minutes))
            sep_result = service.update_file(str(sep))
            minutes_metadata = vector.calls[0]["chunks"][0]["document_metadata"]
            sep_metadata = vector.calls[1]["chunks"][0]["document_metadata"]

            self.assertEqual(minutes_result.status, IngestionStatus.INDEXED)
            self.assertEqual(minutes_result.doc_id, "report_fomc_minutes_2026_03_18_federal_reserve_v1")
            self.assertEqual(minutes_metadata["title"], "FOMC Minutes")
            self.assertEqual(minutes_metadata["event_type"], "FOMC_MINUTES")
            self.assertEqual(minutes_metadata["period"], "2026-03-18")

            self.assertEqual(sep_result.status, IngestionStatus.INDEXED)
            self.assertEqual(sep_result.doc_id, "report_summary_of_economic_projections_2026_03_18_federal_reserve_v1")
            self.assertEqual(sep_metadata["title"], "Summary Of Economic Projections")
            self.assertEqual(sep_metadata["event_type"], "SEP")
            self.assertEqual(sep_metadata["period"], "2026-03-18")

    def test_existing_wrong_fomc_minutes_manifest_is_repaired(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            minutes = self.write_doc(
                root,
                "report/macro/central_bank/federal_reserve/fomc_minutes_2026_03_18.pdf",
                b"minutes",
            )
            minutes.with_suffix(".manifest.yaml").write_text(
                "\n".join([
                    "title: FOMC Statement",
                    "title_slug: fomc_statement_2026_03_18",
                    "author: Federal Reserve",
                    "author_slug: federal_reserve",
                    "organization: Federal Reserve",
                    "organization_slug: federal_reserve",
                    "knowledge_type: report",
                    "domain: macro",
                    "subdomain: central_bank",
                    "document_type: pdf",
                    "version: v1",
                    "lifecycle: ACTIVE",
                    "language: en",
                    "source_tier: tier1",
                    "event_type: FOMC",
                    "period: 2026-03-18",
                    "tags:",
                    "  strategies: []",
                    "  assets: []",
                    "  timeframe_focus: []",
                ]),
                encoding="utf-8",
            )

            result = service.update_file(str(minutes))
            document_metadata = vector.calls[0]["chunks"][0]["document_metadata"]

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.doc_id, "report_fomc_minutes_2026_03_18_federal_reserve_v1")
            self.assertEqual(document_metadata["title"], "FOMC Minutes")
            self.assertEqual(document_metadata["event_type"], "FOMC_MINUTES")

    def test_moved_market_report_manifest_is_repaired_from_path(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            gold = self.write_doc(
                root,
                "report/market/gold/world_gold_council/gold_market_commentary_2026_06.pdf",
                b"gold",
            )
            gold.with_suffix(".manifest.yaml").write_text(
                "\n".join([
                    "title: Gold Market Commentary",
                    "title_slug: gold_market_commentary_2026_06",
                    "author: Gold",
                    "author_slug: gold",
                    "organization: Gold",
                    "organization_slug: gold",
                    "knowledge_type: report",
                    "domain: macro",
                    "subdomain: market",
                    "document_type: pdf",
                    "version: v1",
                    "lifecycle: ACTIVE",
                    "language: en",
                    "source_tier: tier3",
                    "event_type: GOLD_MARKET",
                    "period: 2026-06",
                    "tags:",
                    "  strategies: []",
                    "  assets: []",
                    "  timeframe_focus: []",
                ]),
                encoding="utf-8",
            )

            result = service.update_file(str(gold))
            document_metadata = vector.calls[0]["chunks"][0]["document_metadata"]

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.domain, "market")
            self.assertEqual(result.subdomain, "gold")
            self.assertEqual(document_metadata["organization"], "World Gold Council")
            self.assertEqual(document_metadata["organization_slug"], "world_gold_council")
            self.assertEqual(document_metadata["source_tier"], "tier1")

    def test_moved_report_replaces_missing_old_source_with_same_checksum(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            content = b"same report bytes"
            checksum = hashlib.sha256(content).hexdigest()
            old_source = root / "report/macro/market/gold/gold/gold_market_commentary_2026_06.pdf"
            service.catalog.upsert_document(
                "report_gold_market_commentary_2026_06_gold_v1",
                {
                    "source_path": str(old_source),
                    "checksum": checksum,
                    "lifecycle": "ACTIVE",
                    "index_status": "INDEXED",
                },
            )
            gold = self.write_doc(
                root,
                "report/market/gold/world_gold_council/gold_market_commentary_2026_06.pdf",
                content,
            )

            result = service.update_file(str(gold))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.replaces_doc_id, "report_gold_market_commentary_2026_06_gold_v1")
            self.assertEqual(result.doc_id, "report_gold_market_commentary_2026_06_world_gold_council_v1")
            self.assertIn("report_gold_market_commentary_2026_06_gold_v1", vector.deleted_doc_ids)

    def test_report_cpi_nfp_and_gdp_metadata_inference(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            cpi = self.write_doc(root, "report/macro/inflation/bls/us_cpi_report_2026_05.pdf")
            nfp = self.write_doc(root, "report/macro/employment/bls/us_nonfarm_payrolls_2026_05.pdf", b"nfp")
            gdp = self.write_doc(root, "report/macro/gdp/bea/us_gdp_2026_q1_second_estimate.pdf", b"gdp")

            service.update_file(str(cpi))
            service.update_file(str(nfp))
            service.update_file(str(gdp))

            docs = [call["chunks"][0]["document_metadata"] for call in vector.calls]
            by_event = {doc["event_type"]: doc for doc in docs}
            self.assertEqual(by_event["CPI"]["organization"], "BLS")
            self.assertEqual(by_event["CPI"]["period"], "2026-05")
            self.assertEqual(by_event["NFP"]["organization"], "BLS")
            self.assertEqual(by_event["GDP"]["organization"], "BEA")
            self.assertEqual(by_event["GDP"]["period"], "2026-Q1")
            self.assertEqual(by_event["GDP"]["revision"], "second_estimate")

    def test_unknown_report_organization_is_auto_discovered_safely(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            pdf = self.write_doc(root, "report/market/gold/custom_org/gold_market_commentary_2026_06.pdf")

            result = service.update_file(str(pdf))
            document_metadata = vector.calls[0]["chunks"][0]["document_metadata"]

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.domain, "market")
            self.assertEqual(result.subdomain, "gold")
            self.assertEqual(result.chunk_policy_id, "market_report_default")
            self.assertEqual(document_metadata["organization"], "Custom Org")
            self.assertEqual(document_metadata["event_type"], "GOLD_MARKET")
            self.assertEqual(document_metadata["asset_focus"], "gold")

    def test_epub_parser_path_indexes_with_location_metadata(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            epub = self.write_doc(root, "book/psychology/trading_discipline/mark_douglas/trading_in_the_zone.epub")

            result = service.update_file(str(epub))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.document_type, "epub")
            self.assertEqual(result.parser_type, "epub:fake")
            self.assertEqual(vector.calls[0]["chunks"][0]["chapter"], "Chapter 1")
            self.assertEqual(vector.calls[0]["chunks"][0]["location"], "spine:1")

    def test_unknown_subdomain_under_known_domain_uses_default_policy(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/new_subdomain/owner/new_topic.pdf")

            result = service.update_file(str(pdf))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.chunk_policy_id, "technical_default")

    def test_strategy_trend_following_domain_is_supported(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/strategy/trend_following/michael_covel/trend_following.pdf")

            result = service.update_file(str(pdf))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.domain, "strategy")
            self.assertEqual(result.subdomain, "trend_following")

    def test_validation_failure_logs_error_details(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/unknown_domain/topic/owner/bad.pdf")

            result = service.update_file(str(pdf))

            self.assertEqual(result.status, IngestionStatus.FAILED)
            self.assertIn("Domain 'unknown_domain'", result.reason)
            self.assertTrue(any("stage=validate status=FAILED errors=" in line for line in result.logs))

    def test_canonical_slug_replaces_old_same_source_doc(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            epub = self.write_doc(
                root,
                "book/macro/monetary_policy/ben_bernake/the_federal_reserve_and_the_financial_crisis.epub",
                b"bernanke",
            )
            old_doc_id = "book_the_federal_reserve_and_the_financial_crisis_ben_bernake_v1"
            checksum = service.auto_manifest_service.calculate_checksum(str(epub))
            service.catalog.upsert_document(old_doc_id, {
                "source_path": str(epub),
                "checksum": checksum,
                "index_status": "INDEXED",
                "lifecycle": "ACTIVE",
            })

            result = service.update_file(str(epub))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.doc_id, "book_the_federal_reserve_and_the_financial_crisis_ben_bernanke_v1")
            self.assertEqual(result.replaces_doc_id, old_doc_id)
            self.assertIn(old_doc_id, vector.deleted_doc_ids)
            self.assertEqual(service.catalog.get_document(old_doc_id)["index_status"], "REPLACED")

    def test_canonical_slug_replaces_old_doc_after_folder_rename(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            old_path = root / "book/macro/monetary_policy/ben_bernake/the_federal_reserve_and_the_financial_crisis.epub"
            new_path = self.write_doc(
                root,
                "book/macro/monetary_policy/ben_bernanke/the_federal_reserve_and_the_financial_crisis.epub",
                b"bernanke",
            )
            old_doc_id = "book_the_federal_reserve_and_the_financial_crisis_ben_bernake_v1"
            checksum = service.auto_manifest_service.calculate_checksum(str(new_path))
            service.catalog.upsert_document(old_doc_id, {
                "source_path": str(old_path),
                "checksum": checksum,
                "index_status": "INDEXED",
                "lifecycle": "ACTIVE",
            })

            result = service.update_file(str(new_path))

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertEqual(result.doc_id, "book_the_federal_reserve_and_the_financial_crisis_ben_bernanke_v1")
            self.assertEqual(result.replaces_doc_id, old_doc_id)
            self.assertIn(old_doc_id, vector.deleted_doc_ids)
            self.assertEqual(service.catalog.get_document(old_doc_id)["index_status"], "REPLACED")

    def test_unsupported_extension_is_skipped_cleanly(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            note = self.write_doc(root, "book/technical/indicators/owner/readme.txt")

            result = service.update_file(str(note))

            self.assertEqual(result.status, IngestionStatus.SKIPPED_UNSUPPORTED_EXTENSION)
            self.assertEqual(vector.calls, [])

    def test_duplicate_checksum_is_not_indexed_twice(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            first = self.write_doc(root, "book/technical/indicators/owner/first.pdf", b"same")
            second = self.write_doc(root, "book/technical/indicators/owner/second.pdf", b"same")

            first_result = service.update_file(str(first))
            second_result = service.update_file(str(second))

            self.assertEqual(first_result.status, IngestionStatus.INDEXED)
            self.assertEqual(second_result.status, IngestionStatus.DUPLICATE)
            self.assertEqual(len(vector.calls), 1)

    def test_unchanged_indexed_file_is_skipped_and_changed_checksum_reindexes(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/reindex_me.pdf", b"one")

            first = service.update_file(str(pdf))
            second = service.update_file(str(pdf))
            pdf.write_bytes(b"two")
            third = service.update_file(str(pdf))

            self.assertEqual(first.status, IngestionStatus.INDEXED)
            self.assertEqual(second.status, IngestionStatus.SKIPPED_ALREADY_INDEXED)
            self.assertEqual(third.status, IngestionStatus.REINDEXED_CONTENT_CHANGED)
            self.assertEqual(len(vector.calls), 2)

    def test_same_checksum_reindexes_when_ingestion_fingerprint_changes(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/policy_changed.pdf", b"same")

            first = service.update_file(str(pdf))
            service.catalog.upsert_document(first.doc_id, {
                "ingestion_fingerprint": "old-policy-fingerprint",
                "index_status": "INDEXED",
                "checksum": first.checksum,
            })
            second = service.update_file(str(pdf))

            self.assertEqual(first.status, IngestionStatus.INDEXED)
            self.assertEqual(second.status, IngestionStatus.REINDEXED_POLICY_CHANGED)
            self.assertEqual(second.reason, "INGESTION_FINGERPRINT_CHANGED")
            self.assertEqual(len(vector.calls), 2)

    def test_catalog_stores_ingestion_fingerprint_metadata(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(tmpdir)
            pdf = self.write_doc(root, "book/technical/indicators/owner/fingerprint.pdf", b"same")

            result = service.update_file(str(pdf))
            document = service.catalog.get_document(result.doc_id)

            self.assertEqual(result.status, IngestionStatus.INDEXED)
            self.assertTrue(document["ingestion_fingerprint"])
            self.assertEqual(document["ingestion_fingerprint"], result.ingestion_fingerprint)
            self.assertIn("child_size_chars", document["ingestion_fingerprint_payload"])
            self.assertEqual(document["embedding_model"], "embed-multilingual-v3.0")

    def test_invalid_path_empty_and_needs_ocr_do_not_index(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir)
            invalid = Path(tmpdir) / "outside.pdf"
            invalid.write_bytes(b"bad")
            empty = self.write_doc(root, "book/technical/indicators/owner/empty_doc.pdf", b"empty")
            ocr = self.write_doc(root, "book/technical/indicators/owner/needs_ocr.pdf", b"ocr")

            invalid_result = service.update_file(str(invalid))
            empty_result = service.update_file(str(empty))
            ocr_result = service.update_file(str(ocr))

            self.assertEqual(invalid_result.status, IngestionStatus.QUARANTINE)
            self.assertFalse(Path(f"{invalid.with_suffix('')}.manifest.yaml").exists())
            self.assertEqual(empty_result.status, IngestionStatus.EMPTY_DOCUMENT)
            self.assertEqual(ocr_result.status, IngestionStatus.NEEDS_OCR)
            self.assertEqual(vector.calls, [])

    def test_one_failed_file_does_not_stop_batch_and_summary_counts_are_correct(self):
        with TemporaryDirectory() as tmpdir:
            root, service, vector = self.make_service(tmpdir, fail_names={"fail_book"})
            self.write_doc(root, "book/technical/indicators/owner/good_book.pdf", b"good")
            self.write_doc(root, "book/technical/indicators/owner/fail_book.pdf", b"fail")
            self.write_doc(root, "book/technical/indicators/owner/needs_ocr.pdf", b"ocr")

            report = service.update_repository()

            self.assertEqual(report.discovered, 3)
            self.assertEqual(report.indexed, 1)
            self.assertEqual(report.failed, 1)
            self.assertEqual(report.needs_ocr, 1)
            self.assertEqual(len(vector.calls), 2)

    def test_embedding_rate_limit_marks_pending_retry(self):
        with TemporaryDirectory() as tmpdir:
            root, service, _ = self.make_service(
                tmpdir,
                fail_names={"rate_book"},
                fail_result={
                    "status": "PENDING_RETRY",
                    "reason": "rate_limited; cooldown_seconds=600",
                    "category": "rate_limited",
                    "retryable": True,
                    "rate_limit_count": 1,
                },
            )
            pdf = self.write_doc(root, "book/technical/indicators/owner/rate_book.pdf", b"rate")

            result = service.update_file(str(pdf))
            document = service.catalog.get_document(result.doc_id)

            self.assertEqual(result.status, IngestionStatus.PENDING_RETRY)
            self.assertEqual(result.failure_category, "rate_limited")
            self.assertTrue(result.retryable)
            self.assertEqual(document["index_status"], "PENDING_RETRY")
            self.assertEqual(document["retryable"], 1)
            self.assertFalse(document.get("ingestion_fingerprint"))

    def test_retry_failed_only_processes_only_retryable_pending_docs(self):
        old_retry_only = Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY
        try:
            Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY = True
            with TemporaryDirectory() as tmpdir:
                root, service, vector = self.make_service(tmpdir)
                retry_pdf = self.write_doc(root, "book/technical/indicators/owner/retry_me.pdf", b"retry")
                ignored_pdf = self.write_doc(root, "book/technical/indicators/owner/ignore_me.pdf", b"ignore")
                service.catalog.upsert_document(
                    "book_retry_me_owner_v1",
                    {
                        "source_path": str(retry_pdf),
                        "index_status": "PENDING_RETRY",
                        "retryable": 1,
                    },
                )

                report = service.update_repository()

                self.assertEqual(report.discovered, 1)
                self.assertEqual(len(vector.calls), 1)
                self.assertIn("retry_me", vector.calls[0]["doc_id"])
                self.assertNotIn("ignore_me", vector.calls[0]["doc_id"])
                self.assertTrue(ignored_pdf.exists())
        finally:
            Config.KNOWLEDGE_UPDATE_RETRY_FAILED_ONLY = old_retry_only

    def test_ui_layer_does_not_import_qdrant_or_vector_internals(self):
        text = (PROJECT_ROOT / "src" / "ui" / "tab_settings.py").read_text(encoding="utf-8")

        self.assertNotIn("qdrant_client", text)
        self.assertNotIn("VectorServiceV3", text)
        self.assertNotIn("KnowledgeCatalog", text)
        self.assertIn("retrieval_smoke", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
