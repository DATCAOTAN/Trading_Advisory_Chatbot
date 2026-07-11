import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest


class FakeVectorService:
    def __init__(self, records=None):
        self.records = records or []
        self.calls = []

    def search(self, query, filters, top_k=8, score_threshold=0.7):
        self.calls.append({
            "query": query,
            "filters": dict(filters),
            "top_k": top_k,
            "score_threshold": score_threshold,
        })
        matches = []
        for record in self.records:
            payload = record.get("payload", {})
            score = record.get("score", 0.0)
            if score < score_threshold:
                continue
            if self._matches(payload, filters):
                matches.append(record)
        return matches[:top_k]

    def _matches(self, payload, filters):
        for key, expected in filters.items():
            actual = payload.get(key)
            if isinstance(expected, list):
                if isinstance(actual, list):
                    if not any(item in actual for item in expected):
                        return False
                elif actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True


def make_record(
    doc_id="doc-1",
    chunk_id="doc-1_p12_c1",
    parent_chunk_id=None,
    content="EMA crossover content",
    score=0.91,
    domain="technical",
    subdomain="indicators",
    strategies=None,
    assets=None,
    timeframe_focus=None,
    source_tier="tier2",
    language="en",
    lifecycle="ACTIVE",
    index_status="INDEXED",
):
    return {
        "content": content,
        "score": score,
        "payload": {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "parent_chunk_id": parent_chunk_id or "",
            "text": content,
            "page": 12,
            "domain": domain,
            "subdomain": subdomain,
            "strategies": strategies if strategies is not None else ["trend_following"],
            "assets": assets if assets is not None else ["XAUUSD"],
            "timeframe_focus": timeframe_focus if timeframe_focus is not None else ["h1"],
            "knowledge_type": "book",
            "source_tier": source_tier,
            "language": language,
            "lifecycle": lifecycle,
            "index_status": index_status,
            "document_metadata": {
                "doc_id": doc_id,
                "title": "Technical Analysis",
                "author": "John Murphy",
            },
            "operational_metadata": {"index_version": "v3"},
        },
    }


class KnowledgeServiceSearchTests(unittest.TestCase):
    def make_service(self, records=None):
        fake_vector = FakeVectorService(records=records)
        return KnowledgeService(vector_service=fake_vector), fake_vector

    def test_missing_domain_rejects_search_and_prevents_global_scan(self):
        service, fake_vector = self.make_service([make_record()])
        request = SearchRequest(query="ema", routing_filters={})

        with self.assertRaisesRegex(ValueError, "domain is required"):
            service.search(request)

        self.assertEqual(fake_vector.calls, [])

    def test_domain_only_search_works(self):
        service, fake_vector = self.make_service([make_record(), make_record(domain="macro")])
        request = SearchRequest(query="ema", routing_filters={"domain": "technical"})

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.fallback_level, 0)
        self.assertEqual(response.filters_used["domain"], "technical")
        self.assertEqual(fake_vector.calls[0]["filters"]["domain"], "technical")

    def test_full_filters_search_works(self):
        service, _ = self.make_service([
            make_record(),
            make_record(chunk_id="wrong", assets=["EURUSD"]),
        ])
        request = SearchRequest(
            query="ema crossover",
            routing_filters={
                "domain": " technical ",
                "subdomain": "Indicators",
                "strategies": ["Trend_Following"],
                "assets": ["XAUUSD"],
                "timeframe_focus": ["H1"],
                "title": "Should Not Become A Filter",
            },
        )

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.chunks[0]["citation"]["chunk_id"], "doc-1_p12_c1")
        self.assertNotIn("title", response.filters_used)
        self.assertEqual(response.filters_used["subdomain"], "indicators")
        self.assertEqual(response.filters_used["strategies"], ["trend_following"])
        self.assertEqual(response.filters_used["assets"], ["XAUUSD"])

    def test_fallback_relaxes_filters_step_by_step_and_keeps_domain(self):
        service, fake_vector = self.make_service([
            make_record(strategies=["mean_reversion"], assets=["EURUSD"], timeframe_focus=["m15"])
        ])
        request = SearchRequest(
            query="find relaxed",
            routing_filters={
                "domain": "technical",
                "subdomain": "indicators",
                "strategies": ["trend_following"],
                "assets": ["XAUUSD"],
                "timeframe_focus": ["h1"],
            },
        )

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.fallback_level, 3)
        self.assertEqual(len(fake_vector.calls), 4)
        for call in fake_vector.calls:
            self.assertIn("domain", call["filters"])
        self.assertIn("timeframe_focus", fake_vector.calls[0]["filters"])
        self.assertNotIn("timeframe_focus", fake_vector.calls[1]["filters"])
        self.assertNotIn("assets", fake_vector.calls[2]["filters"])
        self.assertEqual(set(fake_vector.calls[3]["filters"]).issuperset({"domain", "subdomain"}), True)

    def test_source_tier_filtering_works(self):
        service, _ = self.make_service([
            make_record(doc_id="tier-1", chunk_id="tier-1_c1", source_tier="tier1"),
            make_record(doc_id="tier-3", chunk_id="tier-3_c1", source_tier="tier3"),
        ])
        request = SearchRequest(
            query="source tier",
            routing_filters={"domain": "technical"},
            allowed_source_tier=["tier1"],
        )

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.chunks[0]["citation"]["source_tier"], "tier1")

    def test_lifecycle_filtering_returns_only_active_chunks(self):
        service, _ = self.make_service([
            make_record(doc_id="active", chunk_id="active_c1", lifecycle="ACTIVE"),
            make_record(doc_id="draft", chunk_id="draft_c1", lifecycle="DRAFT"),
        ])
        request = SearchRequest(query="lifecycle", routing_filters={"domain": "technical"})

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.chunks[0]["citation"]["doc_id"], "active")
        self.assertEqual(response.chunks[0]["metadata"]["lifecycle"], "ACTIVE")

    def test_index_status_filtering_returns_only_indexed_chunks_when_available(self):
        service, _ = self.make_service([
            make_record(doc_id="indexed", chunk_id="indexed_c1", index_status="INDEXED"),
            make_record(doc_id="failed", chunk_id="failed_c1", index_status="FAILED"),
        ])
        request = SearchRequest(query="index status", routing_filters={"domain": "technical"})

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(response.chunks[0]["citation"]["doc_id"], "indexed")

    def test_citation_object_is_structured(self):
        service, _ = self.make_service([make_record()])
        request = SearchRequest(query="citation", routing_filters={"domain": "technical"})

        response = service.search(request)
        citation = response.chunks[0]["citation"]

        self.assertTrue(
            {"doc_id", "chunk_id", "title", "author", "page", "source_tier"}.issubset(set(citation))
        )
        self.assertEqual(citation["doc_id"], "doc-1")
        self.assertEqual(citation["chunk_id"], "doc-1_p12_c1")
        self.assertEqual(citation["title"], "Technical Analysis")
        self.assertEqual(citation["author"], "John Murphy")
        self.assertEqual(citation["page"], 12)
        self.assertEqual(citation["source_tier"], "tier2")

    def test_search_deduplicates_child_hits_by_parent_chunk_id(self):
        service, _ = self.make_service([
            make_record(
                chunk_id="doc-1_p12_c1",
                parent_chunk_id="doc-1_p12_parent1",
                content="same parent context",
                score=0.95,
            ),
            make_record(
                chunk_id="doc-1_p12_c2",
                parent_chunk_id="doc-1_p12_parent1",
                content="same parent context",
                score=0.93,
            ),
            make_record(
                chunk_id="doc-1_p13_c1",
                parent_chunk_id="doc-1_p13_parent1",
                content="different parent context",
                score=0.91,
            ),
        ])
        request = SearchRequest(query="dedupe", routing_filters={"domain": "technical"}, top_k=8)

        response = service.search(request)

        self.assertEqual(response.total_found, 2)
        self.assertEqual(
            [chunk["citation"]["chunk_id"] for chunk in response.chunks],
            ["doc-1_p12_c1", "doc-1_p13_c1"],
        )
        self.assertEqual(
            {chunk["metadata"]["parent_chunk_id"] for chunk in response.chunks},
            {"doc-1_p12_parent1", "doc-1_p13_parent1"},
        )

    def test_response_contains_observability_fields(self):
        service, _ = self.make_service([make_record()])
        request = SearchRequest(query="observability", routing_filters={"domain": "technical"})

        response = service.search(request)
        response_dict = response.to_dict()

        self.assertIn("fallback_level", response_dict)
        self.assertIn("total_found", response_dict)
        self.assertIn("latency_ms", response_dict)
        self.assertIn("filters_used", response_dict)
        self.assertGreaterEqual(response.latency_ms, 0.0)

    def test_no_real_network_services_are_required(self):
        service, fake_vector = self.make_service([make_record()])
        request = SearchRequest(query="network isolation", routing_filters={"domain": "technical"})

        response = service.search(request)

        self.assertEqual(response.total_found, 1)
        self.assertEqual(len(fake_vector.calls), 1)
        self.assertIs(service.vector_service, fake_vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
