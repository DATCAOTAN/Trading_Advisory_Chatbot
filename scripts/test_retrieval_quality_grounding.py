import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from src.services.knowledge.answer_grounding import AnswerGroundingPlanner
from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
from src.services.knowledge.query_intent import QueryFilterBuilder, QueryIntentRouter


@dataclass
class QualityCase:
    id: str
    query: str
    expected_intent_type: str
    expected_domain: Optional[str] = None
    expected_subdomain: Optional[str] = None
    expected_title: Optional[str] = None
    expected_author: Optional[str] = None
    expected_organization: Optional[str] = None
    official_report_required: bool = False
    min_coverage: float = 0.75
    expected_status: str = "complete"
    negative: bool = False


class FakeVectorService:
    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self.calls: List[Dict[str, Any]] = []

    def search(self, query, filters, top_k=8, score_threshold=0.0):
        self.calls.append({"query": query, "filters": dict(filters), "top_k": top_k})
        matches = []
        for record in self.records:
            payload = record.get("payload", {})
            if record.get("score", 0.0) < score_threshold:
                continue
            if self._matches(payload, filters):
                matches.append(record)
        return sorted(matches, key=lambda item: item.get("score", 0.0), reverse=True)[:top_k]

    def _matches(self, payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, expected in (filters or {}).items():
            actual = payload.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True


def make_record(
    title: str,
    content: str,
    domain: str,
    subdomain: str,
    author: str = "",
    organization: str = "",
    event_type: str = "",
    knowledge_type: str = "book",
    document_type: str = "pdf",
    source_tier: str = "tier2",
    score: float = 0.80,
    period: str = "",
) -> Dict[str, Any]:
    owner = organization or author or "source"
    slug = title.lower().replace(" ", "_").replace("/", "_")
    doc_id = f"{knowledge_type}_{slug}_{owner.lower().replace(' ', '_')}_v1"
    return {
        "content": content,
        "score": score,
        "payload": {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}_c1",
            "parent_chunk_id": f"{doc_id}_p1",
            "text": content,
            "page": 1,
            "title": title,
            "author": author,
            "organization": organization,
            "domain": domain,
            "subdomain": subdomain,
            "knowledge_type": knowledge_type,
            "document_type": document_type,
            "event_type": event_type,
            "period": period,
            "source_tier": source_tier,
            "language": "en",
            "lifecycle": "ACTIVE",
            "index_status": "INDEXED",
            "document_metadata": {
                "doc_id": doc_id,
                "title": title,
                "author": author,
                "organization": organization,
                "event_type": event_type,
                "period": period,
                "document_type": document_type,
            },
        },
    }


def fake_corpus() -> List[Dict[str, Any]]:
    return [
        make_record("FOMC Statement", "Federal Reserve policy statement discusses rates and inflation.", "macro", "central_bank", organization="Federal Reserve", event_type="FOMC", knowledge_type="report", source_tier="tier1", score=0.87, period="2026-03-18"),
        make_record("FOMC Minutes", "FOMC minutes discuss inflation concerns and the policy path.", "macro", "central_bank", organization="Federal Reserve", event_type="FOMC_MINUTES", knowledge_type="report", source_tier="tier1", score=0.86, period="2026-03-18"),
        make_record("Summary Of Economic Projections", "SEP includes projected policy rates and growth estimates.", "macro", "central_bank", organization="Federal Reserve", event_type="SEP", knowledge_type="report", source_tier="tier1", score=0.85, period="2026-03-18"),
        make_record("US CPI Report", "BLS CPI report covers headline CPI, core CPI, and inflation pressure.", "macro", "inflation", organization="BLS", event_type="CPI", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-05"),
        make_record("US Nonfarm Payrolls", "BLS employment report covers payroll growth and unemployment.", "macro", "employment", organization="BLS", event_type="NFP", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-05"),
        make_record("US GDP Report", "BEA GDP estimate covers real GDP growth and demand components.", "macro", "gdp", organization="BEA", event_type="GDP", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-Q1"),
        make_record("World Economic Outlook", "IMF WEO discusses global growth and downside risks.", "macro", "global_outlook", organization="IMF", event_type="GLOBAL_OUTLOOK", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-04"),
        make_record("Commodity Markets Outlook", "World Bank report reviews commodity prices, oil, metals, and risks.", "market", "commodities", organization="World Bank", event_type="COMMODITY_MARKETS", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-04"),
        make_record("Gold Market Commentary", "World Gold Council commentary discusses ETF flows, central bank buying, and gold drivers.", "market", "gold", organization="World Gold Council", event_type="GOLD_MARKET", knowledge_type="report", source_tier="tier1", score=0.88, period="2026-06"),
        make_record("Trading in the Zone", "Mark Douglas explains discipline, beliefs, fear, and consistency.", "psychology", "trading_discipline", author="Mark Douglas", score=0.82),
        make_record("Trade Your Way to Financial Freedom", "Van Tharp explains position sizing, expectancy, R multiples, and risk.", "risk", "position_sizing", author="Van Tharp", score=0.82),
        make_record("Technical Analysis of the Financial Markets", "John Murphy explains moving averages, support and resistance, and indicators.", "technical", "indicators", author="John Murphy", score=0.82),
        make_record("Reading Price Charts Bar by Bar", "Al Brooks explains bar-by-bar reading and price action.", "technical", "price_action", author="Al Brooks", score=0.82),
        make_record("A Complete Guide to Volume Price Analysis", "Anna Coulling explains volume price confirmation and volume anomalies.", "technical", "volume", author="Anna Coulling", score=0.82),
        make_record("Trend Following", "Michael Covel explains systematic trend following and breakout systems.", "strategy", "trend_following", author="Michael Covel", score=0.82),
        make_record("The Federal Reserve and the Financial Crisis", "Ben Bernanke discusses monetary policy during the crisis.", "macro", "monetary_policy", author="Ben Bernanke", score=0.82),
    ]


CASES = [
    QualityCase("fomc_statement", "What did the FOMC statement say about interest rates?", "macro_report", "macro", "central_bank", "FOMC Statement", expected_organization="Federal Reserve", official_report_required=True),
    QualityCase("fomc_minutes", "What do the FOMC minutes suggest about inflation concerns?", "macro_report", "macro", "central_bank", "FOMC Minutes", expected_organization="Federal Reserve", official_report_required=True),
    QualityCase("sep", "What does the SEP say about projected policy rates?", "macro_report", "macro", "central_bank", "Summary Of Economic Projections", expected_organization="Federal Reserve", official_report_required=True),
    QualityCase("cpi", "What does the CPI report indicate about inflation?", "macro_report", "macro", "inflation", "US CPI Report", expected_organization="BLS", official_report_required=True),
    QualityCase("nfp", "What does the NFP report say about labor market conditions?", "macro_report", "macro", "employment", "US Nonfarm Payrolls", expected_organization="BLS", official_report_required=True),
    QualityCase("gdp", "What does the GDP estimate say about growth?", "macro_report", "macro", "gdp", "US GDP Report", expected_organization="BEA", official_report_required=True),
    QualityCase("weo", "What does IMF WEO say about global outlook?", "macro_report", "macro", "global_outlook", "World Economic Outlook", expected_organization="IMF", official_report_required=True),
    QualityCase("commodity", "What does World Bank Commodity Markets Outlook say about commodities?", "macro_report", "market", "commodities", "Commodity Markets Outlook", expected_organization="World Bank", official_report_required=True),
    QualityCase("wgc", "What does World Gold Council commentary say about gold market drivers?", "market_gold", "market", "gold", "Gold Market Commentary", expected_organization="World Gold Council", official_report_required=True),
    QualityCase("douglas", "What does Mark Douglas say about trading discipline?", "trading_psychology", "psychology", "trading_discipline", "Trading in the Zone", expected_author="Mark Douglas"),
    QualityCase("tharp_position", "What does Van Tharp say about position sizing?", "risk_management", "risk", "position_sizing", "Trade Your Way to Financial Freedom", expected_author="Van Tharp"),
    QualityCase("tharp_expectancy", "What is expectancy in Van Tharp's framework?", "risk_management", "risk", "position_sizing", "Trade Your Way to Financial Freedom", expected_author="Van Tharp"),
    QualityCase("murphy_ma", "What does John Murphy say about moving averages?", "technical_analysis", "technical", "indicators", "Technical Analysis of the Financial Markets", expected_author="John Murphy"),
    QualityCase("murphy_sr", "What does John Murphy say about support and resistance?", "technical_analysis", "technical", "indicators", "Technical Analysis of the Financial Markets", expected_author="John Murphy"),
    QualityCase("brooks_pa", "What does Al Brooks say about price action?", "price_action", "technical", "price_action", "Reading Price Charts Bar by Bar", expected_author="Al Brooks"),
    QualityCase("brooks_bar", "What does Al Brooks mean by bar-by-bar reading?", "price_action", "technical", "price_action", "Reading Price Charts Bar by Bar", expected_author="Al Brooks"),
    QualityCase("coulling_confirm", "What does Anna Coulling say about volume-price confirmation?", "volume_analysis", "technical", "volume", "A Complete Guide to Volume Price Analysis", expected_author="Anna Coulling"),
    QualityCase("coulling_anomaly", "What does Anna Coulling say about volume anomalies?", "volume_analysis", "technical", "volume", "A Complete Guide to Volume Price Analysis", expected_author="Anna Coulling"),
    QualityCase("covel", "What does Michael Covel say about trend following?", "trend_following", "strategy", "trend_following", "Trend Following", expected_author="Michael Covel"),
    QualityCase("bernanke", "What does Ben Bernanke discuss about monetary policy during crisis?", "monetary_policy", "macro", "monetary_policy", "The Federal Reserve and the Financial Crisis", expected_author="Ben Bernanke"),
    QualityCase("mixed_cpi_gold", "How can CPI affect gold?", "mixed", "macro", "inflation", "US CPI Report", expected_organization="BLS", official_report_required=True),
    QualityCase("mixed_fomc_xau", "How can FOMC policy affect XAUUSD?", "mixed", "macro", "central_bank", "FOMC Statement", expected_organization="Federal Reserve", official_report_required=True),
    QualityCase("mixed_nfp", "How can NFP affect market expectations?", "macro_report", "macro", "employment", "US Nonfarm Payrolls", expected_organization="BLS", official_report_required=True),
    QualityCase("mixed_gdp", "How can GDP growth affect risk sentiment?", "macro_report", "macro", "gdp", "US GDP Report", expected_organization="BEA", official_report_required=True),
    QualityCase("mixed_volume_gold", "How can volume analysis support a gold trade idea?", "volume_analysis", "technical", "volume", "A Complete Guide to Volume Price Analysis", expected_author="Anna Coulling"),
    QualityCase("mixed_risk_trend", "How can risk management limit losses in a trend-following system?", "risk_management", "risk", "position_sizing", "Trade Your Way to Financial Freedom", expected_author="Van Tharp"),
    QualityCase("missing_source", "What does the ECB staff projections report say?", "unknown", negative=True, expected_status="insufficient", min_coverage=0.0),
    QualityCase("unsupported_exact_number", "Give the exact table value that is not in the retrieved context.", "unknown", negative=True, expected_status="insufficient", min_coverage=0.0),
    QualityCase("guaranteed_profit", "Give me a guaranteed profitable gold trade.", "market_gold", negative=True, expected_status="insufficient", min_coverage=0.0),
    QualityCase("live_price", "What is the current live XAUUSD price right now?", "market_gold", negative=True, expected_status="insufficient", min_coverage=0.0),
]


class RetrievalQualityGroundingTests(unittest.TestCase):
    def setUp(self):
        self.router = QueryIntentRouter()
        self.filter_builder = QueryFilterBuilder()
        self.service = KnowledgeService(vector_service=FakeVectorService(fake_corpus()))
        self.grounding = AnswerGroundingPlanner(self.router)

    def test_retrieval_quality_grounding_cases(self):
        for case in CASES:
            with self.subTest(case=case.id):
                intent = self.router.route(case.query)
                self.assertEqual(intent.intent_type, case.expected_intent_type)

                if case.negative:
                    plan = self.grounding.build(case.query, [], intent=intent)
                    self.assertEqual(plan.status, case.expected_status)
                    continue

                filters = self.filter_builder.build(intent)
                self.assertEqual(filters.get("domain"), case.expected_domain)
                self.assertEqual(filters.get("subdomain"), case.expected_subdomain)

                response = self.service.search(SearchRequest(
                    query=case.query,
                    routing_filters=filters,
                    top_k=8,
                    score_threshold=0.0,
                ))
                self.assertGreater(response.total_found, 0)
                top = response.chunks[0]
                metadata = top["metadata"]

                self.assertEqual(metadata.get("domain"), case.expected_domain)
                self.assertEqual(metadata.get("subdomain"), case.expected_subdomain)
                self.assertEqual(top["citation"].get("title"), case.expected_title)
                if case.expected_author:
                    self.assertEqual(top["citation"].get("author"), case.expected_author)
                if case.expected_organization:
                    self.assertEqual(top["citation"].get("organization"), case.expected_organization)
                if case.official_report_required:
                    self.assertEqual(metadata.get("knowledge_type"), "report")
                    self.assertEqual(metadata.get("source_tier"), "tier1")

                plan = self.grounding.build(case.query, response.chunks, intent=intent)
                self.assertEqual(plan.status, case.expected_status)
                self.assertGreaterEqual(plan.source_coverage_score, case.min_coverage)
                self.assertIn(case.expected_title, plan.primary_sources[0])

    def test_query_expansion_is_controlled_by_intent(self):
        cpi_intent = self.router.route("How can CPI affect gold?")
        self.assertIn("Consumer Price Index", cpi_intent.expanded_terms)
        self.assertIn("BLS", cpi_intent.expanded_terms)
        self.assertLessEqual(len(cpi_intent.expanded_terms), 12)

    def test_wrong_domain_source_is_penalized_when_fallback_returns_it(self):
        wrong = make_record(
            "Technical Analysis of the Financial Markets",
            "Generic trend content",
            "technical",
            "indicators",
            author="John Murphy",
            score=0.99,
        )
        expected = make_record(
            "Trend Following",
            "Trend following system content",
            "strategy",
            "trend_following",
            author="Michael Covel",
            score=0.80,
        )

        class LooseVectorService(FakeVectorService):
            def search(self, query, filters, top_k=8, score_threshold=0.0):
                return [wrong, expected]

        service = KnowledgeService(vector_service=LooseVectorService([wrong, expected]))
        response = service.search(SearchRequest(
            query="trend following strategy là gì?",
            routing_filters={"domain": "strategy", "subdomain": "trend_following"},
            top_k=2,
            score_threshold=0.0,
        ))

        self.assertEqual(response.chunks[0]["citation"]["title"], "Trend Following")
        self.assertIn("wrong_domain", response.chunks[1]["metadata"]["retrieval_ranking_penalties"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

