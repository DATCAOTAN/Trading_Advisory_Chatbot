import sys
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


from src.config import Config
from src.services.retrieval_adapter import RetrievalAdapter


class FakeLegacyService:
    def __init__(self):
        self.calls = []

    def retrieve_candidates(self, query, top_k=None):
        self.calls.append({"query": query, "top_k": top_k})
        return [
            {
                "content": "legacy content",
                "metadata": {"source": "legacy.pdf", "doc_type": "static"},
                "score": 0.42,
            }
        ]


class FakeKnowledgeService:
    def __init__(self, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    def search(self, request):
        self.calls.append(request)
        if self.should_fail:
            raise RuntimeError("v3 unavailable")
        return SimpleNamespace(
            chunks=[
                {
                    "content": "v3 content",
                    "citation": {
                        "doc_id": "doc-v3",
                        "chunk_id": "doc-v3_p1_c1",
                        "title": "V3 Fixture",
                        "author": "Knowledge Author",
                        "page": 12,
                        "source_tier": "tier2",
                        "parent_chunk_id": "doc-v3_p1_parent1",
                        "chunk_policy_id": "technical_indicators",
                        "domain": "technical",
                        "subdomain": "indicators",
                    },
                    "score": 0.91,
                    "metadata": {
                        "knowledge_type": "book",
                        "source_tier": "tier2",
                        "parent_chunk_id": "doc-v3_p1_parent1",
                        "chunk_policy_id": "technical_indicators",
                        "domain": "technical",
                        "subdomain": "indicators",
                        "document_metadata": {
                            "title": "V3 Fixture",
                            "author": "Knowledge Author",
                        },
                    },
                }
            ]
        )


class FakeMarketReportKnowledgeService:
    def __init__(self):
        self.calls = []

    def search(self, request):
        self.calls.append(request)
        subdomain = request.routing_filters.get("subdomain")
        if subdomain == "commodities":
            title = "Commodity Markets Outlook"
            organization = "World Bank"
            event_type = "COMMODITY_MARKETS"
        else:
            title = "Gold Market Commentary"
            organization = "World Gold Council"
            event_type = "GOLD_MARKET"
        return SimpleNamespace(
            chunks=[
                {
                    "content": f"{title} report context",
                    "citation": {
                        "doc_id": f"report_{subdomain}",
                        "chunk_id": f"report_{subdomain}_c1",
                        "title": title,
                        "author": "",
                        "organization": organization,
                        "page": 1,
                        "source_tier": "tier1",
                    },
                    "score": 0.95,
                    "metadata": {
                        "knowledge_type": "report",
                        "source_tier": "tier1",
                        "domain": "market",
                        "subdomain": subdomain,
                        "event_type": event_type,
                        "document_metadata": {
                            "title": title,
                            "organization": organization,
                            "event_type": event_type,
                            "document_type": "pdf",
                        },
                    },
                }
            ]
        )


class RetrievalAdapterTests(unittest.TestCase):
    def test_default_config_and_use_v3_false_uses_legacy(self):
        self.assertFalse(Config.USE_KNOWLEDGE_V3)
        self.assertTrue(Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY)
        self.assertEqual(Config.KNOWLEDGE_V3_SCORE_THRESHOLD, 0.0)
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("EMA indicator", top_k=5)

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["content"], "legacy content")
        self.assertEqual(len(legacy.calls), 1)
        self.assertEqual(v3.calls, [])

    def test_use_v3_true_calls_knowledge_service_and_converts_shape(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("EMA indicator", filters={"domain": "technical"}, top_k=3, use_v3=True)

        self.assertEqual(legacy.calls, [])
        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "technical")
        self.assertEqual(v3.calls[0].top_k, 3)
        self.assertEqual(v3.calls[0].score_threshold, Config.KNOWLEDGE_V3_SCORE_THRESHOLD)
        self.assertEqual(docs[0]["content"], "v3 content")
        self.assertEqual(docs[0]["score"], 0.91)
        self.assertEqual(docs[0]["metadata"]["source"], "V3 Fixture")
        self.assertEqual(docs[0]["metadata"]["doc_type"], "book")
        self.assertEqual(docs[0]["metadata"]["doc_id"], "doc-v3")
        self.assertEqual(docs[0]["metadata"]["chunk_id"], "doc-v3_p1_c1")
        self.assertEqual(docs[0]["metadata"]["title"], "V3 Fixture")
        self.assertEqual(docs[0]["metadata"]["author"], "Knowledge Author")
        self.assertEqual(docs[0]["metadata"]["page"], 12)
        self.assertEqual(docs[0]["metadata"]["source_tier"], "tier2")
        self.assertEqual(docs[0]["metadata"]["parent_chunk_id"], "doc-v3_p1_parent1")
        self.assertEqual(docs[0]["metadata"]["chunk_policy_id"], "technical_indicators")
        self.assertEqual(docs[0]["metadata"]["domain"], "technical")
        self.assertEqual(docs[0]["metadata"]["subdomain"], "indicators")
        self.assertEqual(docs[0]["metadata"]["retrieval_mode"], "v3")
        self.assertEqual(docs[0]["metadata"]["collection"], "knowledge_current")
        self.assertEqual(adapter.last_trace.mode_used, "v3")
        self.assertTrue(adapter.last_trace.v3_succeeded)
        self.assertFalse(adapter.last_trace.fallback_to_legacy)

    def test_v3_failure_falls_back_to_legacy_when_enabled(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService(should_fail=True)
        adapter = RetrievalAdapter(
            legacy_service=legacy,
            knowledge_service=v3,
            fallback_to_legacy=True,
        )

        docs = adapter.retrieve("EMA indicator", filters={"domain": "technical"}, use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(len(legacy.calls), 1)
        self.assertEqual(docs[0]["content"], "legacy content")
        self.assertEqual(adapter.last_trace.mode_used, "legacy")
        self.assertFalse(adapter.last_trace.v3_succeeded)
        self.assertTrue(adapter.last_trace.fallback_to_legacy)
        self.assertIn("v3_error", adapter.last_trace.fallback_reason)

    def test_v3_failure_returns_empty_when_fallback_disabled(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService(should_fail=True)
        adapter = RetrievalAdapter(
            legacy_service=legacy,
            knowledge_service=v3,
            fallback_to_legacy=False,
        )

        docs = adapter.retrieve("EMA indicator", filters={"domain": "technical"}, use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(legacy.calls, [])
        self.assertEqual(docs, [])
        self.assertEqual(adapter.last_trace.mode_used, "v3")
        self.assertFalse(adapter.last_trace.v3_succeeded)
        self.assertFalse(adapter.last_trace.fallback_to_legacy)

    def test_missing_domain_is_inferred_and_calls_v3(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("How does RSI indicator work?", use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "technical")
        self.assertEqual(legacy.calls, [])
        self.assertEqual(docs[0]["metadata"]["doc_id"], "doc-v3")

    def test_macro_event_queries_infer_specific_report_subdomains(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        adapter.retrieve("CPI cao ảnh hưởng vàng thế nào?", use_v3=True)
        self.assertEqual(v3.calls[-1].routing_filters["domain"], "macro")
        self.assertEqual(v3.calls[-1].routing_filters["subdomain"], "inflation")

        adapter.retrieve("NFP mạnh ảnh hưởng USD và vàng thế nào?", use_v3=True)
        self.assertEqual(v3.calls[-1].routing_filters["domain"], "macro")
        self.assertEqual(v3.calls[-1].routing_filters["subdomain"], "employment")

        adapter.retrieve("FOMC ảnh hưởng thị trường như thế nào?", use_v3=True)
        self.assertEqual(v3.calls[-1].routing_filters["domain"], "macro")
        self.assertEqual(v3.calls[-1].routing_filters["subdomain"], "central_bank")
        self.assertEqual(legacy.calls, [])

    def test_market_report_queries_override_generic_trading_terms(self):
        legacy = FakeLegacyService()
        v3 = FakeMarketReportKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve(
            "Commodity Markets Outlook nói gì về hàng hóa trong Trading/Forex?",
            use_v3=True,
        )

        self.assertEqual(v3.calls[-1].routing_filters["domain"], "market")
        self.assertEqual(v3.calls[-1].routing_filters["subdomain"], "commodities")
        self.assertEqual(docs[0]["metadata"]["title"], "Commodity Markets Outlook")
        self.assertEqual(docs[0]["metadata"]["organization"], "World Bank")
        self.assertFalse(adapter.last_trace.fallback_to_legacy)

        docs = adapter.retrieve(
            "gold market report nói gì về vàng trong Trading/Forex?",
            use_v3=True,
        )

        self.assertEqual(v3.calls[-1].routing_filters["domain"], "market")
        self.assertEqual(v3.calls[-1].routing_filters["subdomain"], "gold")
        self.assertEqual(docs[0]["metadata"]["title"], "Gold Market Commentary")
        self.assertEqual(docs[0]["metadata"]["organization"], "World Gold Council")
        self.assertFalse(adapter.last_trace.fallback_to_legacy)
        self.assertEqual(legacy.calls, [])

    def test_moving_averages_query_is_inferred_as_technical(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("John Murphy moving averages", use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "technical")
        self.assertEqual(legacy.calls, [])
        self.assertEqual(docs[0]["metadata"]["doc_id"], "doc-v3")

    def test_trend_following_strategy_query_routes_to_strategy_subdomain(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("trend following strategy là gì?", use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "strategy")
        self.assertEqual(v3.calls[0].routing_filters["subdomain"], "trend_following")
        self.assertEqual(legacy.calls, [])
        self.assertEqual(docs[0]["metadata"]["doc_id"], "doc-v3")

    def test_indicator_trend_following_query_stays_technical(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        adapter.retrieve("EMA indicator trend following là gì?", use_v3=True)

        self.assertEqual(len(v3.calls), 1)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "technical")
        self.assertNotIn("subdomain", v3.calls[0].routing_filters)

    def test_missing_uninferable_domain_falls_back_to_legacy(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(
            legacy_service=legacy,
            knowledge_service=v3,
            fallback_to_legacy=True,
        )

        docs = adapter.retrieve("Tell me something interesting", use_v3=True)

        self.assertEqual(v3.calls, [])
        self.assertEqual(len(legacy.calls), 1)
        self.assertEqual(docs[0]["content"], "legacy content")
        self.assertEqual(adapter.last_trace.fallback_reason, "missing_or_uninferable_domain")

    def test_output_shape_remains_legacy_compatible(self):
        legacy = FakeLegacyService()
        v3 = FakeKnowledgeService()
        adapter = RetrievalAdapter(legacy_service=legacy, knowledge_service=v3)

        docs = adapter.retrieve("risk reward and stop loss", use_v3=True)

        self.assertEqual(len(docs), 1)
        self.assertEqual(set(docs[0]), {"content", "metadata", "score"})
        self.assertIsInstance(docs[0]["metadata"], dict)
        for key in ["source", "doc_type", "doc_id", "chunk_id", "title", "author", "page"]:
            self.assertIn(key, docs[0]["metadata"])
        self.assertIsInstance(docs[0]["score"], float)
        self.assertEqual(v3.calls[0].routing_filters["domain"], "risk")


if __name__ == "__main__":
    unittest.main(verbosity=2)
