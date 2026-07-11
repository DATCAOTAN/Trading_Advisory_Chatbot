import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from scripts.evaluate_v3_retrieval import (
    RetrievalEvalCase,
    count_duplicate_parent_chunks,
    count_missing_citations,
    count_missing_metadata,
    evaluate_case,
    evaluate_cases,
    load_cases,
)
from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
from src.services.knowledge.retrieval_smoke import RetrievalSmokeEvaluator, RetrievalSmokeStatus


def make_chunk(
    domain="technical",
    subdomain="indicators",
    title="Technical Analysis of the Financial Markets",
    author="John Murphy",
    score=0.91,
    chunk_id="doc_p1_c1",
    parent_chunk_id="doc_p1_parent1",
    include_citation=True,
    include_metadata=True,
    organization="",
    event_type="",
    knowledge_type="book",
    document_type="pdf",
):
    chunk = {
        "content": "parent context about moving averages",
        "score": score,
    }
    if include_citation:
        chunk["citation"] = {
            "doc_id": "book_technical_analysis_financial_markets_john_murphy_v1",
            "chunk_id": chunk_id,
            "title": title,
            "author": author,
            "page": 12,
            "source_tier": "tier2",
        }
        if organization:
            chunk["citation"]["organization"] = organization
    if include_metadata:
        chunk["metadata"] = {
            "doc_id": "book_technical_analysis_financial_markets_john_murphy_v1",
            "chunk_id": chunk_id,
            "parent_chunk_id": parent_chunk_id,
            "domain": domain,
            "subdomain": subdomain,
            "knowledge_type": knowledge_type,
            "document_type": document_type,
            "organization": organization,
            "event_type": event_type,
            "source_tier": "tier2",
            "language": "en",
            "lifecycle": "ACTIVE",
            "document_metadata": {
                "title": title,
                "author": author,
                "organization": organization,
                "event_type": event_type,
                "document_type": document_type,
                "original_filename": "technical_analysis_financial_markets_ocr.pdf",
            },
        }
    return chunk


class FakeRetrievalService:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def search(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            chunks=list(self.chunks),
            total_found=len(self.chunks),
            fallback_level=0,
            latency_ms=12.5,
        )


class V3RetrievalEvalTests(unittest.TestCase):
    def test_evaluation_case_parsing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir) / "cases.json"
            case_path.write_text(json.dumps([
                {
                    "id": "case-a",
                    "query": "EMA moving average",
                    "routing_filters": {"domain": "technical"},
                    "expected_domain": "technical",
                    "top_k": 5,
                    "score_threshold": 0.0,
                }
            ]), encoding="utf-8")

            cases = load_cases(str(case_path))

            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].id, "case-a")
            self.assertEqual(cases[0].routing_filters["domain"], "technical")
            self.assertEqual(cases[0].top_k, 5)

    def test_passing_case_detection(self):
        case = RetrievalEvalCase(
            id="pass",
            query="EMA moving average",
            routing_filters={"domain": "technical"},
            expected_domain="technical",
            expected_subdomain="indicators",
            expected_title_contains="Technical Analysis",
            expected_author_contains="Murphy",
            expected_source_contains="technical_analysis",
            min_score=0.5,
        )
        service = FakeRetrievalService([make_chunk()])

        result = evaluate_case(case, service)

        self.assertTrue(result.passed)
        self.assertEqual(result.top_k_returned, 1)
        self.assertEqual(result.best_score, 0.91)
        self.assertEqual(len(service.calls), 1)

    def test_primary_and_top_k_source_detection(self):
        case = RetrievalEvalCase(
            id="strategy",
            query="trend following strategy là gì?",
            routing_filters={"domain": "strategy", "subdomain": "trend_following"},
            expected_domain="strategy",
            expected_subdomain="trend_following",
            expected_title="Trend Following",
            expected_author="Michael Covel",
            expected_primary=True,
            expected_in_top_k=3,
        )
        service = FakeRetrievalService([
            make_chunk(
                domain="strategy",
                subdomain="trend_following",
                title="Trend Following",
                author="Michael Covel",
            )
        ])

        result = evaluate_case(case, service)

        self.assertTrue(result.passed)
        self.assertTrue(result.primary_source_matched)
        self.assertEqual(result.expected_source_rank, 1)
        self.assertTrue(result.expected_in_top_k_matched)

    def test_primary_source_failure_reports_actual_sources(self):
        case = RetrievalEvalCase(
            id="strategy-fail",
            query="trend following strategy là gì?",
            routing_filters={"domain": "strategy", "subdomain": "trend_following"},
            expected_title="Trend Following",
            expected_author="Michael Covel",
            expected_primary=True,
        )
        service = FakeRetrievalService([
            make_chunk(title="Technical Analysis of the Financial Markets", author="John Murphy")
        ])

        result = evaluate_case(case, service)

        self.assertFalse(result.passed)
        self.assertIn("expected primary source", " ".join(result.reasons))
        self.assertEqual(result.actual_top_authors[0], "John Murphy")

    def test_wrong_domain_and_subdomain_detection(self):
        case = RetrievalEvalCase(
            id="wrong-domain",
            query="EMA moving average",
            routing_filters={"domain": "technical"},
            expected_domain="technical",
            expected_subdomain="indicators",
        )
        service = FakeRetrievalService([
            make_chunk(domain="macro", subdomain="fomc")
        ])

        result = evaluate_case(case, service)

        self.assertFalse(result.passed)
        self.assertFalse(result.domain_matched)
        self.assertFalse(result.subdomain_matched)
        self.assertTrue(any("domain" in reason for reason in result.reasons))

    def test_empty_retrieval_result_handling(self):
        case = RetrievalEvalCase(id="empty", query="unknown", routing_filters={"domain": "technical"})
        service = FakeRetrievalService([])

        result = evaluate_case(case, service)

        self.assertFalse(result.passed)
        self.assertEqual(result.top_k_returned, 0)
        self.assertIn("no chunks returned", result.reasons)

    def test_missing_citation_and_metadata_detection(self):
        chunks = [
            make_chunk(include_citation=False),
            make_chunk(include_metadata=False),
        ]

        self.assertEqual(count_missing_citations(chunks), 1)
        self.assertEqual(count_missing_metadata(chunks), 1)

        case = RetrievalEvalCase(id="missing", query="EMA", routing_filters={"domain": "technical"})
        result = evaluate_case(case, FakeRetrievalService(chunks))

        self.assertFalse(result.passed)
        self.assertEqual(result.missing_citation_count, 1)
        self.assertEqual(result.missing_metadata_count, 1)

    def test_duplicate_parent_chunk_counting(self):
        chunks = [
            make_chunk(chunk_id="doc_p1_c1", parent_chunk_id="doc_p1_parent1"),
            make_chunk(chunk_id="doc_p1_c2", parent_chunk_id="doc_p1_parent1"),
            make_chunk(chunk_id="doc_p2_c1", parent_chunk_id="doc_p2_parent1"),
        ]

        self.assertEqual(count_duplicate_parent_chunks(chunks), 1)

        case = RetrievalEvalCase(id="dupe", query="EMA", routing_filters={"domain": "technical"})
        result = evaluate_case(case, FakeRetrievalService(chunks))

        self.assertFalse(result.passed)
        self.assertEqual(result.duplicate_parent_chunk_count, 1)

    def test_summary_metrics_calculation(self):
        cases = [
            RetrievalEvalCase(id="ok", query="EMA", routing_filters={"domain": "technical"}),
            RetrievalEvalCase(
                id="bad",
                query="EMA",
                routing_filters={"domain": "technical"},
                expected_domain="technical",
            ),
        ]

        class MixedService:
            def __init__(self):
                self.calls = 0

            def search(self, request):
                self.calls += 1
                chunks = [make_chunk()] if self.calls == 1 else []
                return SimpleNamespace(chunks=chunks, total_found=len(chunks), fallback_level=0, latency_ms=10.0)

        summary = evaluate_cases(cases, MixedService())

        self.assertEqual(summary.total_cases, 2)
        self.assertEqual(summary.passed_cases, 1)
        self.assertEqual(summary.failed_cases, 1)
        self.assertEqual(summary.average_latency_ms, 10.0)

    def test_metadata_boost_prioritizes_exact_title_and_subdomain(self):
        class FakeVectorService:
            def search(self, query, filters, top_k, score_threshold):
                return [
                    make_chunk(
                        domain="technical",
                        subdomain="indicators",
                        title="Technical Analysis of the Financial Markets",
                        author="John Murphy",
                        score=0.95,
                        chunk_id="murphy_c1",
                        parent_chunk_id="murphy_parent",
                    ),
                    make_chunk(
                        domain="strategy",
                        subdomain="trend_following",
                        title="Trend Following",
                        author="Michael Covel",
                        score=0.80,
                        chunk_id="covel_c1",
                        parent_chunk_id="covel_parent",
                    ),
                ]

        service = KnowledgeService(vector_service=FakeVectorService())
        response = service.search(SearchRequest(
            query="trend following strategy là gì?",
            routing_filters={"domain": "strategy", "subdomain": "trend_following"},
            top_k=2,
            score_threshold=0.0,
        ))

        self.assertEqual(response.chunks[0]["citation"]["author"], "Michael Covel")
        self.assertGreater(response.chunks[0]["metadata"]["retrieval_boost"], 0)

    def test_retrieval_smoke_passes_when_expected_document_appears(self):
        metadata = {
            "routing_metadata": {"domain": "strategy", "subdomain": "trend_following"},
            "document_metadata": {"title": "Trend Following", "author": "Michael Covel"},
        }
        smoke = RetrievalSmokeEvaluator(
            search_service=FakeRetrievalService([
                make_chunk(
                    domain="strategy",
                    subdomain="trend_following",
                    title="Trend Following",
                    author="Michael Covel",
                )
            ])
        )

        result = smoke.evaluate_document(
            "book_trend_following_michael_covel_v1",
            metadata,
        )

        self.assertEqual(result.status, RetrievalSmokeStatus.PASS)
        self.assertIn("trend_following", result.query)

    def test_retrieval_smoke_fails_when_expected_document_is_missing(self):
        metadata = {
            "routing_metadata": {"domain": "strategy", "subdomain": "trend_following"},
            "document_metadata": {"title": "Trend Following", "author": "Michael Covel"},
        }
        smoke = RetrievalSmokeEvaluator(
            search_service=FakeRetrievalService([
                make_chunk(title="Technical Analysis of the Financial Markets", author="John Murphy")
            ])
        )

        result = smoke.evaluate_document(
            "book_trend_following_michael_covel_v1",
            metadata,
        )

        self.assertEqual(result.status, RetrievalSmokeStatus.FAIL)
        self.assertIn("missing", result.reason)

    def test_report_eval_case_skips_when_expected_source_not_indexed(self):
        case = RetrievalEvalCase(
            id="macro-cpi",
            query="CPI cao ảnh hưởng vàng thế nào?",
            routing_filters={"domain": "macro", "subdomain": "inflation"},
            expected_domain="macro",
            expected_subdomain="inflation",
            expected_organization="BLS",
            expected_title="US CPI Report",
            expected_event_type="CPI",
            expected_knowledge_type="report",
            expected_document_type="pdf",
            expected_primary=True,
            tags=["report"],
        )
        result = evaluate_case(case, FakeRetrievalService([]))

        self.assertTrue(result.skipped)
        self.assertTrue(result.passed)
        self.assertIn("Expected source not indexed", result.reasons[0])

    def test_report_eval_passes_when_fake_expected_source_appears(self):
        case = RetrievalEvalCase(
            id="macro-cpi",
            query="CPI cao ảnh hưởng vàng thế nào?",
            routing_filters={"domain": "macro", "subdomain": "inflation"},
            expected_domain="macro",
            expected_subdomain="inflation",
            expected_organization="BLS",
            expected_title="US CPI Report",
            expected_event_type="CPI",
            expected_knowledge_type="report",
            expected_document_type="pdf",
            expected_primary=True,
            expected_in_top_k=3,
            tags=["report"],
        )
        chunk = make_chunk(
            domain="macro",
            subdomain="inflation",
            title="US CPI Report",
            author="BLS",
            organization="BLS",
            event_type="CPI",
            knowledge_type="report",
            document_type="pdf",
        )

        result = evaluate_case(case, FakeRetrievalService([chunk]))

        self.assertTrue(result.passed)
        self.assertFalse(result.skipped)
        self.assertTrue(result.primary_source_matched)
        self.assertTrue(result.organization_matched)
        self.assertTrue(result.event_type_matched)

    def test_official_report_boost_prioritizes_source_tier_and_event_type(self):
        class FakeVectorService:
            def search(self, query, filters, top_k, score_threshold):
                official = make_chunk(
                    domain="macro",
                    subdomain="inflation",
                    title="US CPI Report",
                    author="BLS",
                    organization="BLS",
                    event_type="CPI",
                    knowledge_type="report",
                    document_type="pdf",
                    score=0.80,
                    chunk_id="cpi_c1",
                    parent_chunk_id="cpi_parent",
                )
                official["metadata"]["source_tier"] = "tier1"
                official["citation"]["source_tier"] = "tier1"
                support = make_chunk(
                    domain="macro",
                    subdomain="inflation",
                    title="Generic Inflation Notes",
                    author="Analyst",
                    organization="",
                    event_type="",
                    knowledge_type="report",
                    document_type="pdf",
                    score=0.95,
                    chunk_id="generic_c1",
                    parent_chunk_id="generic_parent",
                )
                return [support, official]

        service = KnowledgeService(vector_service=FakeVectorService())
        response = service.search(SearchRequest(
            query="CPI cao ảnh hưởng vàng thế nào?",
            routing_filters={"domain": "macro", "subdomain": "inflation"},
            top_k=2,
            score_threshold=0.0,
        ))

        self.assertEqual(response.chunks[0]["metadata"]["organization"], "BLS")
        self.assertEqual(response.chunks[0]["metadata"]["event_type"], "CPI")

    def test_no_real_network_imports_are_needed_for_fake_eval(self):
        script_text = (PROJECT_ROOT / "scripts" / "evaluate_v3_retrieval.py").read_text(encoding="utf-8")

        self.assertNotIn("qdrant_client", script_text)
        self.assertNotIn("cohere.Client", script_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
