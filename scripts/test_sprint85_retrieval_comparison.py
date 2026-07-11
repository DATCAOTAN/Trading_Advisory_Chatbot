import contextlib
import importlib.util
import io
import sys
import types
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


def install_stubs():
    if importlib.util.find_spec("streamlit") is None:
        streamlit_stub = types.ModuleType("streamlit")
        streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
        sys.modules["streamlit"] = streamlit_stub

    if importlib.util.find_spec("dotenv") is None:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = dotenv_stub


install_stubs()

from src.services.retrieval_adapter import RetrievalAdapter
from src.ui.tab_chatbot import _normalize_source_for_display, _source_metadata_lines


class FakeLegacyService:
    def __init__(self):
        self.calls = []

    def retrieve_candidates(self, query, top_k=None):
        self.calls.append({"query": query, "top_k": top_k})
        return [
            {
                "content": "legacy text",
                "metadata": {"source": "legacy.pdf", "doc_type": "static"},
                "score": 0.31,
            }
        ]


class FakeKnowledgeService:
    def __init__(self, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    def search(self, request):
        self.calls.append(request)
        if self.should_fail:
            raise RuntimeError("fake v3 down")
        return SimpleNamespace(
            chunks=[
                {
                    "content": "v3 parent context",
                    "citation": {
                        "doc_id": "doc-v3",
                        "chunk_id": "doc-v3_p10_c2",
                        "title": "Technical Analysis of the Financial Markets",
                        "author": "John Murphy",
                        "page": 10,
                        "source_tier": "tier2",
                    },
                    "metadata": {
                        "knowledge_type": "book",
                        "domain": "technical",
                        "subdomain": "indicators",
                        "source_tier": "tier2",
                        "parent_chunk_id": "doc-v3_parent_10",
                        "chunk_policy_id": "technical_indicators",
                    },
                    "score": 0.93,
                }
            ]
        )


class Sprint85RetrievalComparisonTests(unittest.TestCase):
    def test_v3_success_trace_does_not_mark_legacy_fallback(self):
        legacy = FakeLegacyService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=FakeKnowledgeService())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs = adapter.retrieve("EMA indicator", use_v3=True, filters={"domain": "technical"})

        self.assertEqual(legacy.calls, [])
        self.assertEqual(len(docs), 1)
        self.assertEqual(adapter.last_trace.mode_used, "v3")
        self.assertTrue(adapter.last_trace.v3_succeeded)
        self.assertFalse(adapter.last_trace.fallback_to_legacy)
        self.assertEqual(adapter.last_trace.collection, "knowledge_current")
        self.assertIn("mode=v3", stdout.getvalue())
        self.assertIn("fallback_to_legacy=False", stdout.getvalue())

    def test_v3_failure_fallback_is_marked_clearly(self):
        legacy = FakeLegacyService()
        adapter = RetrievalAdapter(
            legacy_service=legacy,
            knowledge_service=FakeKnowledgeService(should_fail=True),
            fallback_to_legacy=True,
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            docs = adapter.retrieve("EMA indicator", use_v3=True, filters={"domain": "technical"})

        self.assertEqual(docs[0]["content"], "legacy text")
        self.assertEqual(adapter.last_trace.mode_used, "legacy")
        self.assertFalse(adapter.last_trace.v3_succeeded)
        self.assertTrue(adapter.last_trace.fallback_to_legacy)
        self.assertIn("v3_error", adapter.last_trace.fallback_reason)
        self.assertIn("collection=xauusd_knowledge_v2", stdout.getvalue())

    def test_v3_metadata_reaches_source_display_helpers(self):
        adapter = RetrievalAdapter(legacy_service=FakeLegacyService(), knowledge_service=FakeKnowledgeService())
        docs = adapter.retrieve("EMA indicator", use_v3=True, filters={"domain": "technical"})

        source_name, doc_type, preview, score = _normalize_source_for_display(docs[0])
        lines = _source_metadata_lines(docs[0])

        self.assertEqual(source_name, "Technical Analysis of the Financial Markets - John Murphy (p. 10)")
        self.assertEqual(doc_type, "book")
        self.assertEqual(preview, "v3 parent context")
        self.assertEqual(score, 0.93)
        self.assertIn("Domain: technical/indicators", lines)
        self.assertIn("Source tier: tier2", lines)
        self.assertIn("Collection: knowledge_current", lines)
        self.assertNotIn("Policy: technical_indicators", lines)

    def test_report_metadata_reaches_source_display_helpers(self):
        class ReportKnowledgeService:
            def search(self, request):
                return SimpleNamespace(
                    chunks=[
                        {
                            "content": "FOMC statement context",
                            "citation": {
                                "doc_id": "report_fomc_statement_2026_06_17_federal_reserve_v1",
                                "chunk_id": "fomc_c1",
                                "title": "FOMC Statement",
                                "author": "Federal Reserve",
                                "organization": "Federal Reserve",
                                "page": 1,
                                "source_tier": "tier1",
                            },
                            "metadata": {
                                "knowledge_type": "report",
                                "domain": "macro",
                                "subdomain": "central_bank",
                                "source_tier": "tier1",
                                "event_type": "FOMC",
                                "period": "2026-06-17",
                                "published_date": "2026-06-17",
                                "document_metadata": {
                                    "title": "FOMC Statement",
                                    "author": "Federal Reserve",
                                    "organization": "Federal Reserve",
                                    "document_type": "pdf",
                                    "event_type": "FOMC",
                                    "period": "2026-06-17",
                                },
                            },
                            "score": 0.88,
                        }
                    ]
                )

        adapter = RetrievalAdapter(legacy_service=FakeLegacyService(), knowledge_service=ReportKnowledgeService())
        docs = adapter.retrieve("FOMC ảnh hưởng thị trường như thế nào?", use_v3=True, filters={"domain": "macro"})
        source_name, _, _, _ = _normalize_source_for_display(docs[0])
        lines = _source_metadata_lines(docs[0])

        self.assertEqual(source_name, "FOMC Statement - Federal Reserve (p. 1)")
        self.assertIn("Organization: Federal Reserve", lines)
        self.assertIn("Type: Official report", lines)
        self.assertIn("Event type: FOMC", lines)
        self.assertIn("Period: 2026-06-17", lines)
        self.assertIn("Domain: macro/central_bank", lines)

    def test_legacy_source_display_still_works(self):
        doc = {
            "content": "legacy text",
            "metadata": {"source": "legacy.pdf", "doc_type": "static"},
            "score": "0.42",
        }

        source_name, doc_type, preview, score = _normalize_source_for_display(doc)
        lines = _source_metadata_lines(doc)

        self.assertEqual(source_name, "legacy.pdf")
        self.assertEqual(doc_type, "static")
        self.assertEqual(preview, "legacy text")
        self.assertEqual(score, 0.42)
        self.assertIn("Title: legacy.pdf", lines)
        self.assertIn("Doc type: static", lines)

    def test_missing_metadata_does_not_crash_source_helpers(self):
        source_name, doc_type, preview, score = _normalize_source_for_display({"content": "plain"})
        lines = _source_metadata_lines({"content": "plain"})

        self.assertEqual(source_name, "Tai lieu he thong")
        self.assertEqual(doc_type, "")
        self.assertEqual(preview, "plain")
        self.assertEqual(score, 0.0)
        self.assertEqual(lines, [])

    def test_comparison_script_has_no_collection_delete_or_recreate(self):
        script = (PROJECT_ROOT / "scripts" / "compare_legacy_v3_retrieval.py").read_text(encoding="utf-8")

        self.assertNotIn("delete_collection", script)
        self.assertNotIn("recreate_collection", script)
        self.assertNotIn("upsert_document", script)
        self.assertNotIn("kp_ingest", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
