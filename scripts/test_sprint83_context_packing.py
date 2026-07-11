import sys
import types
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


if importlib.util.find_spec("cohere") is None:
    cohere_stub = types.ModuleType("cohere")
    cohere_stub.Client = object
    sys.modules["cohere"] = cohere_stub


from src.pipelines.context_packer import ContextPacker
from src.pipelines.modules.reranker import RerankerModule


def make_doc(content, score=0.5, **metadata):
    return {
        "content": content,
        "metadata": {
            "source": "fixture.pdf",
            "doc_type": "book",
            "doc_id": "doc-1",
            "chunk_id": metadata.pop("chunk_id", "doc-1_c1"),
            "title": "Fixture",
            "author": "Tester",
            **metadata,
        },
        "score": score,
    }


def make_report_doc(content, score=0.5, **metadata):
    return make_doc(
        content,
        score=score,
        doc_type="report",
        knowledge_type="report",
        source_tier="tier1",
        organization=metadata.pop("organization", "BLS"),
        title=metadata.pop("title", "US CPI Report"),
        author="",
        event_type=metadata.pop("event_type", "CPI"),
        domain=metadata.pop("domain", "macro"),
        subdomain=metadata.pop("subdomain", "inflation"),
        **metadata,
    )


class ContextPackingTests(unittest.TestCase):
    def test_duplicate_parent_chunk_id_is_deduplicated_and_highest_score_kept(self):
        packer = ContextPacker()
        docs = [
            make_doc("lower score parent context", score=0.2, parent_chunk_id="parent-1", chunk_id="c1"),
            make_doc("higher score parent context", score=0.9, parent_chunk_id="parent-1", chunk_id="c2"),
            make_doc("other parent context", score=0.7, parent_chunk_id="parent-2", chunk_id="c3"),
        ]

        packed, stats = packer.pack(docs)

        self.assertEqual(len(packed), 2)
        self.assertEqual(stats.duplicate_parent_count, 1)
        self.assertEqual(packed[0]["content"], "higher score parent context")
        self.assertEqual(packed[0]["metadata"]["parent_chunk_id"], "parent-1")
        self.assertEqual(packed[0]["metadata"]["chunk_id"], "c2")

    def test_metadata_and_output_shape_are_preserved(self):
        packer = ContextPacker()
        doc = make_doc("context", score=0.8, parent_chunk_id="parent-1", source_tier="tier2")

        packed, _ = packer.pack([doc])

        self.assertEqual(set(packed[0]), {"content", "metadata", "score"})
        self.assertEqual(packed[0]["metadata"]["source"], "fixture.pdf")
        self.assertEqual(packed[0]["metadata"]["source_tier"], "tier2")

    def test_docs_without_parent_chunk_id_fallback_to_chunk_id(self):
        packer = ContextPacker()
        docs = [
            make_doc("first", score=0.4, chunk_id="same-chunk"),
            make_doc("second", score=0.6, chunk_id="same-chunk"),
        ]

        packed, stats = packer.pack(docs)

        self.assertEqual(len(packed), 1)
        self.assertEqual(stats.duplicate_parent_count, 1)
        self.assertEqual(packed[0]["content"], "second")

    def test_docs_without_ids_fallback_to_content_hash(self):
        packer = ContextPacker()
        docs = [
            {"content": "same content", "metadata": {}, "score": 0.1},
            {"content": "same content", "metadata": {}, "score": 0.9},
        ]

        packed, stats = packer.pack(docs)

        self.assertEqual(len(packed), 1)
        self.assertEqual(stats.duplicate_parent_count, 1)
        self.assertEqual(packed[0]["score"], 0.9)

    def test_max_source_and_context_limits_work(self):
        packer = ContextPacker()
        docs = [
            make_doc("a" * 10, score=0.9, chunk_id="c1"),
            make_doc("b" * 10, score=0.8, chunk_id="c2"),
            make_doc("c" * 10, score=0.7, chunk_id="c3"),
        ]

        packed, stats = packer.pack(docs, max_sources=3, max_context_chars=20)

        self.assertEqual(len(packed), 2)
        self.assertEqual(stats.truncated_docs_count, 1)
        self.assertEqual(stats.total_context_chars, 20)

    def test_reranker_disabled_uses_context_packer_and_preserves_legacy_shape(self):
        reranker = RerankerModule.__new__(RerankerModule)
        reranker.context_packer = ContextPacker()
        docs = [
            make_doc("legacy parent context", score=0.1, parent_id=123, chunk_id="legacy-1"),
            make_doc("legacy duplicate better", score=0.9, parent_id=123, chunk_id="legacy-2"),
        ]

        context, selected = reranker.process("query", docs, enabled=False)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["content"], "legacy duplicate better")
        self.assertIn("[SOURCE]", context)
        self.assertIn("[CONTENT]\nlegacy duplicate better", context)

    def test_reranker_requests_extra_results_then_packs_unique_top_k(self):
        class FakeCohereClient:
            def __init__(self):
                self.top_n = None

            def rerank(self, model, query, documents, top_n, return_documents):
                self.top_n = top_n
                return SimpleNamespace(results=[
                    SimpleNamespace(index=0, relevance_score=0.95),
                    SimpleNamespace(index=1, relevance_score=0.90),
                    SimpleNamespace(index=2, relevance_score=0.85),
                    SimpleNamespace(index=3, relevance_score=0.80),
                ])

        fake_client = FakeCohereClient()
        reranker = RerankerModule.__new__(RerankerModule)
        reranker.context_packer = ContextPacker()
        reranker.cohere_client = fake_client
        docs = [
            make_doc("parent one lower", score=0.1, parent_chunk_id="parent-1", chunk_id="c1"),
            make_doc("parent one higher", score=0.1, parent_chunk_id="parent-1", chunk_id="c2"),
            make_doc("parent two", score=0.1, parent_chunk_id="parent-2", chunk_id="c3"),
            make_doc("parent three", score=0.1, parent_chunk_id="parent-3", chunk_id="c4"),
        ]

        context, selected = reranker.process("query", docs, top_k=2, enabled=True)

        self.assertEqual(fake_client.top_n, 4)
        self.assertEqual(len(selected), 2)
        self.assertEqual([doc["metadata"]["parent_chunk_id"] for doc in selected], ["parent-1", "parent-2"])
        self.assertIn("Relevance score", context)
        self.assertIn("[SOURCE]", context)

    def test_reranker_anchors_official_report_when_semantic_rerank_prefers_background_book(self):
        class FakeCohereClient:
            def rerank(self, model, query, documents, top_n, return_documents):
                return SimpleNamespace(results=[
                    SimpleNamespace(index=1, relevance_score=0.96),
                ])

        reranker = RerankerModule.__new__(RerankerModule)
        reranker.context_packer = ContextPacker()
        reranker.cohere_client = FakeCohereClient()
        docs = [
            make_report_doc(
                "official CPI report context",
                score=0.72,
                retrieval_rank_score=1.12,
                chunk_id="cpi-report-c1",
                parent_chunk_id="cpi-report-p1",
            ),
            make_doc(
                "background macro book context",
                score=0.88,
                title="The Federal Reserve And The Financial Crisis",
                author="Ben Bernanke",
                knowledge_type="book",
                source_tier="tier2",
                domain="macro",
                subdomain="monetary_policy",
                chunk_id="book-c1",
                parent_chunk_id="book-p1",
            ),
        ]

        context, selected = reranker.process("CPI cao ảnh hưởng vàng thế nào?", docs, top_k=2, enabled=True)

        self.assertEqual(selected[0]["metadata"]["title"], "US CPI Report")
        self.assertEqual(selected[0]["metadata"]["event_type"], "CPI")
        self.assertEqual(selected[1]["metadata"]["title"], "The Federal Reserve And The Financial Crisis")
        self.assertIn("Title: US CPI Report", context)
        self.assertIn("Organization: BLS", context)
        self.assertIn("Event type: CPI", context)
        self.assertIn("official CPI report context", context)

    def test_reranker_anchors_market_official_reports(self):
        class FakeCohereClient:
            def rerank(self, model, query, documents, top_n, return_documents):
                return SimpleNamespace(results=[
                    SimpleNamespace(index=1, relevance_score=0.95),
                ])

        reranker = RerankerModule.__new__(RerankerModule)
        reranker.context_packer = ContextPacker()
        reranker.cohere_client = FakeCohereClient()
        docs = [
            make_report_doc(
                "official commodity report context",
                title="Commodity Markets Outlook",
                organization="World Bank",
                event_type="COMMODITY_MARKETS",
                domain="market",
                subdomain="commodities",
                chunk_id="commodity-c1",
                parent_chunk_id="commodity-p1",
            ),
            make_doc(
                "technical background context",
                title="Technical Analysis of the Financial Markets",
                author="John Murphy",
                knowledge_type="book",
                source_tier="tier2",
                domain="technical",
                subdomain="indicators",
                chunk_id="technical-c1",
                parent_chunk_id="technical-p1",
            ),
        ]

        context, selected = reranker.process("Commodity Markets Outlook nói gì về hàng hóa?", docs, top_k=2, enabled=True)

        self.assertEqual(selected[0]["metadata"]["title"], "Commodity Markets Outlook")
        self.assertEqual(selected[0]["metadata"]["event_type"], "COMMODITY_MARKETS")
        self.assertIn("Organization: World Bank", context)
        self.assertIn("official commodity report context", context)

        gold_docs = [
            make_report_doc(
                "official gold report context",
                title="Gold Market Commentary",
                organization="World Gold Council",
                event_type="GOLD_MARKET",
                domain="market",
                subdomain="gold",
                chunk_id="gold-c1",
                parent_chunk_id="gold-p1",
            ),
            docs[1],
        ]

        context, selected = reranker.process("gold market report nói gì về vàng?", gold_docs, top_k=2, enabled=True)

        self.assertEqual(selected[0]["metadata"]["title"], "Gold Market Commentary")
        self.assertEqual(selected[0]["metadata"]["event_type"], "GOLD_MARKET")
        self.assertIn("Organization: World Gold Council", context)
        self.assertIn("official gold report context", context)


if __name__ == "__main__":
    unittest.main(verbosity=2)
