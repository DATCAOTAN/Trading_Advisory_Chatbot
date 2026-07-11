import unittest
import sys
import types
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

if importlib.util.find_spec("ollama") is None:
    sys.modules["ollama"] = types.ModuleType("ollama")

if importlib.util.find_spec("cohere") is None:
    cohere_stub = types.ModuleType("cohere")
    cohere_stub.Client = object
    cohere_stub.ClientV2 = object
    sys.modules["cohere"] = cohere_stub

if importlib.util.find_spec("dotenv") is None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if importlib.util.find_spec("fitz") is None:
    fitz_stub = types.ModuleType("fitz")
    fitz_stub.VersionBind = "stub"
    sys.modules["fitz"] = fitz_stub

if importlib.util.find_spec("streamlit") is None:
    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
    sys.modules["streamlit"] = streamlit_stub

if importlib.util.find_spec("qdrant_client") is None:
    qdrant_stub = types.ModuleType("qdrant_client")
    qdrant_stub.QdrantClient = object
    qdrant_models_stub = types.ModuleType("qdrant_client.models")
    for name in [
        "Distance",
        "VectorParams",
        "PointStruct",
        "SparseVectorParams",
        "SparseIndexParams",
    ]:
        setattr(qdrant_models_stub, name, type(name, (), {}))
    qdrant_http_stub = types.ModuleType("qdrant_client.http")
    qdrant_http_models_stub = types.ModuleType("qdrant_client.http.models")
    for name in ["SparseVector", "NamedSparseVector", "Filter", "FieldCondition", "MatchValue"]:
        setattr(qdrant_http_models_stub, name, type(name, (), {}))

    sys.modules["qdrant_client"] = qdrant_stub
    sys.modules["qdrant_client.models"] = qdrant_models_stub
    sys.modules["qdrant_client.http"] = qdrant_http_stub
    sys.modules["qdrant_client.http.models"] = qdrant_http_models_stub

from src.pipelines.modules.evaluator import EvaluatorModule
from src.pipelines.modules.query_rewriter import QueryRewriterModule
from src.pipelines.modules.reranker import RerankerModule
from src.services.knowledge.answer_mode import AnswerModeClassifier, EvidenceSchemaRegistry
from src.services.knowledge.query_decomposer import QueryDecomposer
from src.services.decision_context import DecisionContextBuilder
from src.services.orchestrator_contract import OrchestratorContractBuilder
from src.services.vector_service import VectorService
from src.services.llm_service import LLMService
from src.orchestrator import RAGOrchestrator
from src.pipelines.modules.router import RouteAction
from src.ui.tab_chatbot import (
    _AnswerStreamLogger,
    _normalize_source_for_display,
    _sanitize_user_facing_answer,
    _should_show_static_data_notice,
    _source_metadata_lines,
    check_answer_completeness,
)


class FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def chat(self, *args, **kwargs):
        return self.response


class FakeRouter:
    def process(self, query, chat_history):
        return RouteAction.VECTOR_SEARCH, ""


class FakeRewriter:
    def process(self, query, chat_history):
        return query


class FakeRetrievalAdapter:
    def __init__(self):
        from src.services.knowledge.query_intent import QueryIntentRouter

        self.query_intent_router = QueryIntentRouter()
        self.retrieve_calls = []

    def infer_routing_filters(self, query, query_intent=None):
        intent = query_intent or self.query_intent_router.route(query)
        return {
            "domain": intent.primary_domain,
            "subdomain": intent.primary_subdomain,
            "event_type": intent.event_type_candidates[0] if intent.event_type_candidates else "",
            "organization": intent.preferred_organizations[0] if intent.preferred_organizations else "",
            "knowledge_type": "report" if intent.source_preference in {"official_report_first", "mixed_report_and_book"} else "",
        }

    def retrieve(self, query, filters=None, top_k=8, use_v3=False, fallback_to_legacy=None, query_intent=None):
        intent = query_intent or self.query_intent_router.route(query)
        self.retrieve_calls.append((query, filters, intent.intent_type))
        title_by_author = {
            "Al Brooks": "Reading Price Charts Bar By Bar",
            "Anna Coulling": "A Complete Guide To Volume Price Analysis",
            "Van Tharp": "Trade Your Way To Financial Freedom",
            "Mark Douglas": "Trading In The Zone",
        }
        title_by_event = {
            "CPI": ("US CPI Report", "BLS", "macro", "inflation"),
            "GOLD_MARKET": ("Gold Market Commentary", "World Gold Council", "market", "gold"),
        }
        if intent.event_type_candidates:
            event = intent.event_type_candidates[0]
            title, organization, domain, subdomain = title_by_event.get(
                event,
                ("Official Report", "Official Org", intent.primary_domain, intent.primary_subdomain),
            )
            return [{
                "content": f"{title} context for {query}",
                "metadata": {
                    "title": title,
                    "organization": organization,
                    "knowledge_type": "report",
                    "source_tier": "tier1",
                    "domain": domain,
                    "subdomain": subdomain,
                    "event_type": event,
                    "chunk_id": f"chunk_{len(self.retrieve_calls)}",
                },
                "score": 0.9,
            }]
        author = intent.preferred_authors[0] if intent.preferred_authors else "Unknown"
        return [{
            "content": f"{author} context for {query}",
            "metadata": {
                "title": title_by_author.get(author, "Unknown"),
                "author": author,
                "knowledge_type": "book",
                "domain": intent.primary_domain,
                "subdomain": intent.primary_subdomain,
                "chunk_id": f"chunk_{len(self.retrieve_calls)}",
            },
            "score": 0.9,
        }]


class FakeReranker:
    def __init__(self):
        self.calls = []

    def process(self, query, raw_candidates, enabled=None, query_intent=None):
        self.calls.append((query, getattr(query_intent, "intent_type", "")))
        doc = raw_candidates[0]
        return f"[SOURCE]\nTitle: {doc['metadata']['title']}\n[CONTENT]\n{doc['content']}", raw_candidates


class FakeLiveService:
    def __init__(self):
        self.price_calls = []
        self.calendar_calls = 0
        self.candle_calls = []

    def get_live_price(self, symbol):
        self.price_calls.append(symbol)
        return f"{symbol} price=2400"

    def get_economic_calendar(self):
        self.calendar_calls += 1
        return "CPI actual=3.4 forecast=3.2 previous=3.1"

    def get_historical_candles(self, symbol="XAUUSD", timeframe="1h", limit=100, target_date=None, indicators=None):
        self.candle_calls.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "target_date": target_date,
            "indicators": indicators,
        })
        return [{"time": "2026-07-05T00:00:00Z", "close": 2400}]


class FakeLLMService:
    def generate_multihop_stream(self, query, context, short_term_history=None):
        yield context


class RuntimeStabilizationTests(unittest.TestCase):
    def make_evaluator(self, response):
        evaluator = EvaluatorModule.__new__(EvaluatorModule)
        evaluator.llm_client = FakeLLMClient(response)
        return evaluator

    def test_evaluator_extracts_dict_fail_response(self):
        evaluator = self.make_evaluator({"message": {"content": "FAIL: invented number"}})

        passed, feedback = evaluator.process("answer", "context")

        self.assertFalse(passed)
        self.assertIn("invented number", feedback)

    def test_evaluator_accepts_string_pass_response(self):
        evaluator = self.make_evaluator("PASS")

        passed, feedback = evaluator.process("answer", "context")

        self.assertTrue(passed)
        self.assertEqual(feedback, "")

    def test_query_rewriter_scope_guard_removes_unrequested_trading_context(self):
        rewriter = QueryRewriterModule.__new__(QueryRewriterModule)

        rewritten = rewriter._apply_scope_guard(
            "FOMC Minutes nói gì về inflation và interest rates?",
            "FOMC Minutes nói gì về lạm phát và lãi suất trong giao dịch tài chính (Trading/Forex)",
        )

        self.assertEqual(rewritten, "FOMC Minutes nói gì về lạm phát và lãi suất")
        self.assertNotIn("Trading/Forex", rewritten)

    def test_query_rewriter_scope_guard_keeps_requested_trading_context(self):
        rewriter = QueryRewriterModule.__new__(QueryRewriterModule)

        rewritten = rewriter._apply_scope_guard(
            "FOMC ảnh hưởng XAUUSD thế nào?",
            "FOMC ảnh hưởng XAUUSD trong giao dịch tài chính (Trading/Forex)",
        )

        self.assertIn("Trading/Forex", rewritten)

    def test_answer_scope_for_report_summary_does_not_add_xauusd(self):
        service = LLMService.__new__(LLMService)

        instruction = service._answer_scope_instruction("FOMC Minutes nói gì về inflation và interest rates?")

        self.assertIn("chỉ hỏi tài liệu/báo cáo nói gì", instruction.lower())
        self.assertIn("Không tự thêm XAUUSD", instruction)
        self.assertIn("Kết luận ngắn", instruction)

    def test_answer_scope_for_market_impact_allows_xauusd(self):
        service = LLMService.__new__(LLMService)

        instruction = service._answer_scope_instruction("FOMC ảnh hưởng XAUUSD thế nào?")

        self.assertIn("tác động thị trường", instruction.lower())
        self.assertIn("XAUUSD", instruction)
        self.assertIn("dữ liệu realtime", instruction)

    def test_answer_scope_for_nfp_report_summary_does_not_add_market_impact(self):
        service = LLMService.__new__(LLMService)

        instruction = service._answer_scope_instruction("NFP report noi gi ve labor market?")

        self.assertIn("XAUUSD", instruction)
        self.assertNotIn("dá»¯ liá»‡u realtime", instruction)

    def test_answer_scope_for_nfp_market_impact_allows_xauusd(self):
        service = LLMService.__new__(LLMService)

        instruction = service._answer_scope_instruction("NFP anh huong XAUUSD va USD the nao?")

        self.assertIn("XAUUSD", instruction)
        self.assertIn("realtime", instruction)

    def test_answer_mode_classifier_matrix_for_report_modes(self):
        classifier = AnswerModeClassifier()

        summary = classifier.classify("NFP report noi gi ve labor market?")
        methodology = classifier.classify("NFP duoc tinh nhu the nao?")
        impact = classifier.classify("NFP anh huong XAUUSD va USD the nao?")
        concept = classifier.classify("Van Tharp noi gi ve position sizing?")

        self.assertEqual(summary.mode, "REPORT_SUMMARY")
        self.assertFalse(summary.market_impact_allowed)
        self.assertEqual(methodology.mode, "REPORT_METHODOLOGY")
        self.assertFalse(methodology.market_impact_allowed)
        self.assertEqual(impact.mode, "MARKET_IMPACT")
        self.assertTrue(impact.market_impact_allowed)
        self.assertEqual(concept.mode, "BOOK_CONCEPT_EXPLANATION")

    def test_evidence_schema_terms_change_by_answer_mode(self):
        classifier = AnswerModeClassifier()
        schema = EvidenceSchemaRegistry.get("NFP")

        summary_terms = schema.terms_for_mode(classifier.classify("NFP report noi gi ve labor market?"))
        methodology_terms = schema.terms_for_mode(classifier.classify("NFP duoc tinh nhu the nao?"))

        self.assertIn("total nonfarm payroll employment", summary_terms)
        self.assertIn("average hourly earnings", summary_terms)
        self.assertIn("seasonal adjustment", methodology_terms)
        self.assertIn("definitions", methodology_terms)

    def test_query_decomposer_splits_multi_author_book_question(self):
        query = "\n".join([
            "Al Brooks noi gi ve price action?",
            "Anna Coulling noi gi ve volume price analysis?",
            "Van Tharp noi gi ve position sizing?",
            "Mark Douglas noi gi ve trading discipline?",
        ])

        decomposition = QueryDecomposer().decompose(query)

        self.assertTrue(decomposition.is_multi_intent)
        self.assertEqual(len(decomposition.subqueries), 4)
        intents = [item.intent.intent_type for item in decomposition.subqueries]
        authors = [item.intent.preferred_authors[0] for item in decomposition.subqueries]
        self.assertEqual(intents, ["price_action", "volume_analysis", "risk_management", "trading_psychology"])
        self.assertEqual(authors, ["Al Brooks", "Anna Coulling", "Van Tharp", "Mark Douglas"])

    def test_answer_scope_for_multi_intent_uses_subquestion_template(self):
        service = LLMService.__new__(LLMService)
        query = "\n".join([
            "Al Brooks noi gi ve price action?",
            "Anna Coulling noi gi ve volume price analysis?",
        ])

        instruction = service._answer_scope_instruction(query)

        self.assertIn("ANSWER_MODE: MULTI_INTENT", instruction)
        self.assertIn("[SUBQUESTION]", instruction)

    def test_orchestrator_runs_v3_retrieval_per_multi_intent_subquery(self):
        orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
        fake_adapter = FakeRetrievalAdapter()
        orchestrator.retrieval_adapter = fake_adapter
        orchestrator.query_decomposer = QueryDecomposer(fake_adapter.query_intent_router)
        orchestrator.vector_service = type("FakeVectorService", (), {"search_chat_history": lambda *args, **kwargs: ""})()
        orchestrator.live_service = None
        orchestrator.router_module = FakeRouter()
        orchestrator.rewriter_module = FakeRewriter()
        orchestrator.reranker_module = FakeReranker()
        orchestrator.llm_service = FakeLLMService()
        orchestrator.evaluator_module = None
        orchestrator.decision_context_builder = DecisionContextBuilder(
            intent_router=fake_adapter.query_intent_router,
        )
        orchestrator.orchestrator_contract_builder = OrchestratorContractBuilder()
        orchestrator._agent_tool_selector = lambda query, now_str: [{"tool": "VectorDB_Search", "args": {}}]
        query = "\n".join([
            "Al Brooks noi gi ve price action?",
            "Anna Coulling noi gi ve volume price analysis?",
            "Van Tharp noi gi ve position sizing?",
            "Mark Douglas noi gi ve trading discipline?",
        ])

        stream, sources, mode, artifacts = orchestrator.query_financial_advisor(
            query,
            use_knowledge_v3=True,
            knowledge_v3_fallback_to_legacy=False,
            enable_reranker=False,
        )
        context = "".join(stream)

        self.assertEqual(mode, "FINANCIAL_RAG")
        self.assertGreaterEqual(len(fake_adapter.retrieve_calls), 4)
        self.assertEqual(len(sources), 4)
        self.assertIn("Reading Price Charts Bar By Bar", str(sources))
        self.assertIn("A Complete Guide To Volume Price Analysis", str(sources))
        self.assertIn("Trade Your Way To Financial Freedom", str(sources))
        self.assertIn("Trading In The Zone", str(sources))

    def test_orchestrator_uses_query_plan_for_cpi_xauusd_retrieval(self):
        orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
        fake_adapter = FakeRetrievalAdapter()
        fake_reranker = FakeReranker()
        live_service = FakeLiveService()
        orchestrator.retrieval_adapter = fake_adapter
        orchestrator.query_decomposer = QueryDecomposer(fake_adapter.query_intent_router)
        orchestrator.vector_service = type("FakeVectorService", (), {"search_chat_history": lambda *args, **kwargs: ""})()
        orchestrator.live_service = live_service
        orchestrator.router_module = FakeRouter()
        orchestrator.rewriter_module = type(
            "DriftyRewriter",
            (),
            {"process": lambda self, query, history: f"{query} trong giao dịch Forex"},
        )()
        orchestrator.reranker_module = fake_reranker
        orchestrator.llm_service = FakeLLMService()
        orchestrator.evaluator_module = None
        orchestrator.decision_context_builder = DecisionContextBuilder(
            intent_router=fake_adapter.query_intent_router,
        )
        orchestrator.orchestrator_contract_builder = OrchestratorContractBuilder()
        orchestrator._agent_tool_selector = lambda query, now_str: [{"tool": "VectorDB_Search", "args": {}}]

        stream, sources, mode, artifacts = orchestrator.query_financial_advisor(
            "CPI moi nhat anh huong XAUUSD the nao?",
            use_knowledge_v3=True,
            knowledge_v3_fallback_to_legacy=False,
            enable_reranker=False,
        )
        context = "".join(stream)

        self.assertEqual(mode, "FINANCIAL_RAG")
        self.assertEqual(fake_adapter.retrieve_calls[0][2], "macro_report")
        self.assertEqual(fake_adapter.retrieve_calls[0][1]["domain"], "macro")
        self.assertEqual(fake_adapter.retrieve_calls[0][1]["subdomain"], "inflation")
        self.assertEqual(fake_adapter.retrieve_calls[0][1]["event_type"], "CPI")
        self.assertEqual(fake_reranker.calls[0][1], "macro_report")
        self.assertIn("US CPI Report", str(sources))
        self.assertTrue(live_service.price_calls)
        self.assertEqual(live_service.calendar_calls, 1)

    def test_orchestrator_uses_query_plan_for_current_xauusd_market_state(self):
        orchestrator = RAGOrchestrator.__new__(RAGOrchestrator)
        fake_adapter = FakeRetrievalAdapter()
        fake_reranker = FakeReranker()
        live_service = FakeLiveService()
        orchestrator.retrieval_adapter = fake_adapter
        orchestrator.query_decomposer = QueryDecomposer(fake_adapter.query_intent_router)
        orchestrator.vector_service = type("FakeVectorService", (), {"search_chat_history": lambda *args, **kwargs: ""})()
        orchestrator.live_service = live_service
        orchestrator.router_module = FakeRouter()
        orchestrator.rewriter_module = type(
            "DriftyRewriter",
            (),
            {"process": lambda self, query, history: f"{query} trong giao dịch Forex"},
        )()
        orchestrator.reranker_module = fake_reranker
        orchestrator.llm_service = FakeLLMService()
        orchestrator.evaluator_module = None
        orchestrator.decision_context_builder = DecisionContextBuilder(
            intent_router=fake_adapter.query_intent_router,
        )
        orchestrator.orchestrator_contract_builder = OrchestratorContractBuilder()
        orchestrator._agent_tool_selector = lambda query, now_str: [{"tool": "VectorDB_Search", "args": {}}]

        stream, sources, mode, artifacts = orchestrator.query_financial_advisor(
            "XAUUSD hien tai dang chiu tac dong boi yeu to nao?",
            use_knowledge_v3=True,
            knowledge_v3_fallback_to_legacy=False,
            enable_reranker=False,
        )
        context = "".join(stream)

        self.assertEqual(mode, "FINANCIAL_RAG")
        self.assertEqual(fake_adapter.retrieve_calls, [])
        self.assertEqual(fake_reranker.calls, [])
        self.assertTrue(live_service.price_calls)
        self.assertTrue(live_service.candle_calls)

    def test_source_display_supports_current_schema(self):
        src = {
            "content": "current content",
            "metadata": {"source": "doc.pdf", "doc_type": "static"},
            "score": "0.42",
        }

        source_name, doc_type, preview, score = _normalize_source_for_display(src)

        self.assertEqual(source_name, "doc.pdf")
        self.assertEqual(doc_type, "static")
        self.assertEqual(preview, "current content")
        self.assertEqual(score, 0.42)

    def test_source_display_supports_legacy_schema(self):
        src = {
            "parent_text": "legacy parent",
            "source": "legacy.pdf",
            "rerank_score": 0.25,
        }

        source_name, doc_type, preview, score = _normalize_source_for_display(src)

        self.assertEqual(source_name, "legacy.pdf")
        self.assertEqual(doc_type, "")
        self.assertEqual(preview, "legacy parent")
        self.assertEqual(score, 0.25)

    def test_answer_sanitization_removes_raw_doc_ids(self):
        answer = (
            "Theo US CPI Report cua BLS (Doc ID: report_us_cpi_report_2026_05_bls_v1), "
            "CPI cao co the anh huong den vang."
        )

        sanitized = _sanitize_user_facing_answer(answer)

        self.assertIn("US CPI Report", sanitized)
        self.assertNotIn("Doc ID", sanitized)
        self.assertNotIn("report_us_cpi_report_2026_05_bls_v1", sanitized)

    def test_report_source_metadata_lines_are_user_friendly(self):
        doc = {
            "content": "CPI context",
            "metadata": {
                "title": "US CPI Report",
                "organization": "BLS",
                "knowledge_type": "report",
                "document_type": "pdf",
                "event_type": "CPI",
                "period": "2026-05",
                "published_date": "2026-06-11",
                "domain": "macro",
                "subdomain": "inflation",
                "source_tier": "tier1",
                "retrieval_mode": "v3",
                "collection": "knowledge_current",
                "doc_id": "report_us_cpi_report_2026_05_bls_v1",
                "chunk_id": "cpi_c1",
                "parent_chunk_id": "cpi_p1",
                "chunk_policy_id": "macro_report_default",
            },
        }

        lines = _source_metadata_lines(doc)

        self.assertIn("Title: US CPI Report", lines)
        self.assertIn("Organization: BLS", lines)
        self.assertIn("Type: Official report", lines)
        self.assertIn("Event type: CPI", lines)
        self.assertIn("Period: 2026-05", lines)
        self.assertIn("Domain: macro/inflation", lines)
        self.assertIn("Retrieval mode: v3", lines)
        self.assertIn("Collection: knowledge_current", lines)
        self.assertFalse(any("doc_id" in line.lower() for line in lines))
        self.assertFalse(any(line.startswith(("Chunk:", "Parent:", "Policy:")) for line in lines))

    def test_static_data_notice_only_for_financial_rag_v3_sources(self):
        sources = [{"metadata": {"retrieval_mode": "v3", "collection": "knowledge_current", "knowledge_type": "report"}}]

        self.assertTrue(_should_show_static_data_notice(sources, "FINANCIAL_RAG"))
        self.assertFalse(_should_show_static_data_notice(sources, "GREETING"))
        self.assertFalse(_should_show_static_data_notice([], "FINANCIAL_RAG"))

    def test_vector_retrieve_returns_empty_list_on_embedding_error(self):
        svc = VectorService.__new__(VectorService)

        def raise_embedding_error(*args, **kwargs):
            raise RuntimeError("embedding unavailable")

        svc._encode_dense = raise_embedding_error

        self.assertEqual(svc.retrieve_candidates("query"), [])

    def test_reranker_runtime_toggle_bypasses_rerank(self):
        reranker = RerankerModule.__new__(RerankerModule)
        docs = [{"content": "doc text", "metadata": {"source": "doc.pdf"}, "score": 0.1}]

        context, selected = reranker.process("query", docs, enabled=False)

        self.assertIn("[SOURCE]", context)
        self.assertIn("[CONTENT]\ndoc text", context)
        self.assertEqual(selected, docs)

    def test_report_section_targeting_prefers_cpi_data_over_methodology(self):
        reranker = RerankerModule.__new__(RerankerModule)
        selected = [{
            "content": "CPI-U CPI-W C-CPI-U sample price collection methodology index calculation.",
            "metadata": {
                "title": "US CPI Report",
                "organization": "BLS",
                "knowledge_type": "report",
                "source_tier": "tier1",
                "event_type": "CPI",
                "chunk_id": "methodology",
            },
            "score": 0.90,
        }]
        candidates = selected + [
            {
                "content": "The all items index rose over the month and over the last 12 months. Core CPI less food and energy increased.",
                "metadata": {
                    "title": "US CPI Report",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "source_tier": "tier1",
                    "event_type": "CPI",
                    "chunk_id": "summary",
                },
                "score": 0.72,
            },
            {
                "content": "Food, energy, and shelter components contributed to inflation pressure.",
                "metadata": {
                    "title": "US CPI Report",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "source_tier": "tier1",
                    "event_type": "CPI",
                    "chunk_id": "components",
                },
                "score": 0.70,
            },
        ]

        enhanced = reranker._apply_report_section_targeting(
            "CPI report nói gì về inflation?",
            selected,
            candidates,
        )

        chunk_ids = [doc["metadata"]["chunk_id"] for doc in enhanced[:3]]
        self.assertIn("summary", chunk_ids)
        self.assertIn("components", chunk_ids)
        self.assertLess(
            reranker._report_section_score("CPI report nói gì về inflation?", selected[0]),
            reranker._report_section_score("CPI report nói gì về inflation?", candidates[1]),
        )

    def test_report_section_targeting_prefers_nfp_headline_over_household_detail(self):
        reranker = RerankerModule.__new__(RerankerModule)
        selected = [{
            "content": (
                "Civilian noninstitutional population and civilian labor force details. "
                "Employment-population ratio by race and adult men adult women demographic groups."
            ),
            "metadata": {
                "title": "US Nonfarm Payrolls",
                "organization": "BLS",
                "knowledge_type": "report",
                "source_tier": "tier1",
                "event_type": "NFP",
                "chunk_id": "household_detail",
            },
            "score": 0.88,
        }]
        candidates = selected + [
            {
                "content": (
                    "Total nonfarm payroll employment continued to trend up. "
                    "The unemployment rate changed little. Average hourly earnings increased."
                ),
                "metadata": {
                    "title": "US Nonfarm Payrolls",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "source_tier": "tier1",
                    "event_type": "NFP",
                    "chunk_id": "headline",
                },
                "score": 0.70,
            },
            {
                "content": (
                    "Job gains occurred in health care, social assistance, government, and construction. "
                    "Payroll employment revisions were reported for prior months."
                ),
                "metadata": {
                    "title": "US Nonfarm Payrolls",
                    "organization": "BLS",
                    "knowledge_type": "report",
                    "source_tier": "tier1",
                    "event_type": "NFP",
                    "chunk_id": "sectors",
                },
                "score": 0.68,
            },
        ]

        enhanced = reranker._apply_report_section_targeting(
            "NFP report noi gi ve labor market?",
            selected,
            candidates,
        )

        chunk_ids = [doc["metadata"]["chunk_id"] for doc in enhanced[:3]]
        self.assertIn("headline", chunk_ids)
        self.assertIn("sectors", chunk_ids)
        self.assertLess(
            reranker._report_section_score("NFP report noi gi ve labor market?", selected[0]),
            reranker._report_section_score("NFP report noi gi ve labor market?", candidates[1]),
        )

    def test_answer_stream_logger_logs_start_and_done(self):
        logger = _AnswerStreamLogger(
            "CPI cao ảnh hưởng vàng thế nào?",
            request_id="abc123",
            finish_reason_getter=lambda: "STOP",
        )
        output = StringIO()
        answer = "Xin chào."

        with redirect_stdout(output):
            chunks = list(logger.wrap(["Xin ", "chào."]))
            result = logger.log_done(answer, min_chars=1)

        self.assertEqual(chunks, ["Xin ", "chào."])
        self.assertTrue(result["complete"])
        logs = output.getvalue()
        self.assertIn("[AnswerStream] START request_id=abc123", logs)
        self.assertIn("[AnswerStream] DONE request_id=abc123 chunks=2 chars=9", logs)
        self.assertIn("finish_reason=STOP", logs)
        self.assertIn("output_complete=true", logs)
        self.assertIn("sha256=", logs)
        self.assertIn("tail=Xin chào.", logs)

    def test_answer_stream_logger_logs_partial_error(self):
        def broken_stream():
            yield "partial"
            raise RuntimeError("stream failed")

        logger = _AnswerStreamLogger("FOMC", request_id="err123")
        output = StringIO()

        with self.assertRaises(RuntimeError):
            with redirect_stdout(output):
                list(logger.wrap(broken_stream()))

        logs = output.getvalue()
        self.assertIn("[AnswerStream] START request_id=err123", logs)
        self.assertIn("[AnswerStream] ERROR request_id=err123 chunks=1 chars=7", logs)
        self.assertIn("stream failed", logs)

    def test_answer_stream_logger_marks_max_tokens_incomplete(self):
        logger = _AnswerStreamLogger(
            "gold market report nói gì về vàng?",
            request_id="max123",
            finish_reason_getter=lambda: "MAX_TOKENS",
        )
        output = StringIO()
        answer = "Đây là một câu trả lời đủ dài về báo cáo thị trường vàng. " * 5

        with redirect_stdout(output):
            list(logger.wrap([answer]))
            result = logger.log_done(answer, min_chars=50)

        self.assertFalse(result["complete"])
        logs = output.getvalue()
        self.assertIn("finish_reason=MAX_TOKENS", logs)
        self.assertIn("output_complete=false", logs)

    def test_answer_completeness_fails_for_max_tokens(self):
        answer = "Đây là một câu trả lời đủ dài. " * 10

        result = check_answer_completeness(answer, "MAX_TOKENS", min_chars=50)

        self.assertFalse(result["complete"])
        self.assertEqual(result["finish_reason"], "MAX_TOKENS")
        self.assertEqual(result["reason"], "finish_reason:MAX_TOKENS")

    def test_answer_completeness_fails_for_connector_ending(self):
        answer = ("Đây là phần giải thích dài về báo cáo thị trường vàng. " * 5) + "bao gồm"

        result = check_answer_completeness(answer, "STOP", min_chars=50)

        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "ends_with_incomplete_connector")

    def test_answer_completeness_allows_specific_as_valid_adjective(self):
        answer = (
            "Theo US CPI Report cua BLS, CPI cao co the anh huong den vang thong qua ky vong lai suat va dong USD.\n\n"
            "- Khi CPI cao, thi truong co the ky vong Fed duy tri lai suat cao hon.\n"
            "- Dieu nay co the lam USD va loi suat thuc tang, gay ap luc len vang.\n"
            "- Nha giao dich can ket hop them du lieu gia va quan tri rui ro.\n\n"
            "Tom lai, bao cao CPI la nguon vi mo huu ich, nhung khong chua du lieu thi truong truc tiep de dua ra khuyen nghi giao dich cu the."
        )

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="CPI cao anh huong vang the nao?",
            sources=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )

        self.assertTrue(result["complete"])
        self.assertNotEqual(result["reason"], "ends_with_incomplete_connector")

    def test_answer_completeness_flags_specific_opening_pattern(self):
        answer = ("Đây là phần giải thích dài về báo cáo thị trường vàng. " * 5) + "Cụ thể:"

        result = check_answer_completeness(answer, "STOP", min_chars=50)

        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "ends_with_incomplete_connector")

    def test_greeting_completeness_passes_with_trailing_emoji(self):
        answer = "Xin chào! Tôi có thể giúp gì cho bạn? 💡"

        result = check_answer_completeness(answer, "STOP", intent="GREETING")

        self.assertTrue(result["complete"])
        self.assertEqual(result["level"], "pass")
        self.assertEqual(result["mode"], "GREETING")
        self.assertEqual(result["reason"], "normal_stop_short_response")
        self.assertTrue(result["ends_with_sentence"])

    def test_greeting_completeness_does_not_require_rag_structure(self):
        answer = "Xin chào, tôi sẵn sàng hỗ trợ bạn hôm nay."

        result = check_answer_completeness(answer, "STOP", intent="GREETING")

        self.assertTrue(result["complete"])
        self.assertFalse(result["has_source_reference"])
        self.assertFalse(result["has_enough_bullets_or_sections"])
        self.assertFalse(result["has_summary_or_conclusion"])

    def test_greeting_unknown_finish_reason_passes_when_stream_done(self):
        answer = "Xin chào! Tôi có thể giúp gì cho bạn? 💡"

        result = check_answer_completeness(answer, "UNKNOWN", intent="EARLY_EXIT")

        self.assertTrue(result["complete"])
        self.assertEqual(result["level"], "pass")
        self.assertEqual(result["mode"], "EARLY_EXIT")
        self.assertEqual(result["finish_reason"], "UNKNOWN")

    def test_greeting_max_tokens_fails(self):
        answer = "Xin chào! Tôi có thể giúp gì cho bạn?"

        result = check_answer_completeness(answer, "MAX_TOKENS", intent="GREETING")

        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "finish_reason:MAX_TOKENS")

    def test_rag_max_tokens_still_fails(self):
        answer = (
            "Theo US CPI Report cua BLS, CPI cao cho thay ap luc lam phat van dang ton tai.\n\n"
            "- Dieu nay co the lam thi truong ky vong lai suat cao hon.\n"
            "- Vang co the chiu ap luc neu USD va loi suat thuc tang.\n\n"
            "Tom lai, CPI la nguon vi mo quan trong nhung khong phai tin hieu giao dich rieng le."
        )

        result = check_answer_completeness(
            answer,
            "MAX_TOKENS",
            intent="FINANCIAL_RAG",
            query="CPI cao anh huong vang the nao?",
            sources=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "finish_reason:MAX_TOKENS")


    def test_rag_completeness_passes_with_source_structure_and_summary(self):
        answer = (
            "Theo Commodity Markets Outlook cua World Bank, bao cao nhan manh thi truong hang hoa dang chiu tac dong tu tang truong, lai suat va rui ro cung ung.\n\n"
            "- Gia nang luong va kim loai co the bien dong khi cung ung bi gian doan hoac nhu cau toan cau doi huong.\n"
            "- Voi vang, moi truong bat on va ky vong lai suat thap hon co the ho tro nhu cau phong thu.\n"
            "- Nha giao dich nen xem day la nguon boi canh vi mo, khong phai tin hieu mua ban truc tiep.\n\n"
            "Phan tich thuc te can ket hop voi du lieu gia, USD, loi suat thuc va quan tri rui ro. "
            "Tom lai, bao cao World Bank huu ich de doc xu huong hang hoa, nhung khong thay the mot ke hoach giao dich rieng."
        )
        sources = [{"metadata": {"title": "Commodity Markets Outlook", "organization": "World Bank"}}]

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="Commodity Markets Outlook noi gi ve hang hoa?",
            sources=sources,
        )

        self.assertTrue(result["complete"])
        self.assertEqual(result["level"], "pass")
        self.assertTrue(result["has_source_reference"])
        self.assertTrue(result["has_enough_bullets_or_sections"])
        self.assertTrue(result["has_summary_or_conclusion"])
        self.assertEqual(result["detected_report_title"], "Commodity Markets Outlook")

    def test_rag_completeness_fails_when_required_report_is_missing(self):
        answer = (
            "Theo mot tai lieu phan tich ky thuat, hang hoa co the bien dong theo xu huong thi truong.\n\n"
            "- Diem mot noi ve xu huong va dong tien.\n"
            "- Diem hai noi ve rui ro va bien dong.\n"
            "- Diem ba noi ve cach quan sat thi truong.\n\n"
            "Do do, cau tra loi nay co cau truc nhung khong nhac dung nguon can thiet. "
            "No du dai de vuot qua dieu kien ky thuat nhung sai nguon doi voi cau hoi report. "
            "Tom lai, day khong phai la nguon chinh thuc can duoc uu tien trong cau hoi nay."
        )

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="Commodity Markets Outlook noi gi ve hang hoa?",
            sources=[],
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["level"], "fail")
        self.assertIn("missing_required_report_reference:Commodity Markets Outlook", result["reason"])

    def test_rag_completeness_warns_when_complete_but_short(self):
        answer = (
            "Theo US CPI Report cua BLS, CPI cao cho thay ap luc lam phat van dang ton tai.\n\n"
            "- Dieu nay co the lam thi truong ky vong lai suat cao hon.\n"
            "- Vang co the chiu ap luc neu USD va loi suat thuc tang.\n\n"
            "Tom lai, CPI la nguon vi mo quan trong nhung khong phai tin hieu giao dich rieng le. "
            "Nguoi dung nen ket hop them USD, loi suat thuc va bien dong gia."
        )
        sources = [{"metadata": {"title": "US CPI Report", "organization": "BLS"}}]

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="CPI cao anh huong vang the nao?",
            sources=sources,
        )

        self.assertTrue(result["complete"])
        self.assertEqual(result["level"], "warn")
        self.assertIn("short_rag_answer", result["reason"])

    def test_multi_intent_task_coverage_fails_when_one_task_missing(self):
        answer = (
            "Theo US CPI Report cua BLS, CPI moi nhat la dau vao quan trong de danh gia ap luc lam phat va ky vong lai suat.\n\n"
            "- Neu CPI cao hon ky vong, thi truong co the tang ky vong Fed giu lai suat cao hon.\n"
            "- Dieu nay co the lam USD va loi suat tang, qua do gay ap luc len XAUUSD.\n"
            "- Neu thi truong lo ngai lam phat hon la lai suat, vang van co the duoc ho tro nhu mot tai san phong thu.\n\n"
            "Phan tich nay chi noi ve kenh vi mo cua CPI doi voi XAUUSD dua tren bao cao CPI va co che lai suat. "
            "No khong xem du lieu gia live, dong tien, loi suat thuc hay tin tuc trong ngay. "
            "Tom lai, CPI la mot yeu to quan trong nhung chua du de tra loi toan bo boi canh giao dich cua XAUUSD."
        )

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="CPI moi nhat anh huong XAUUSD the nao?\nXAUUSD hien tai dang chiu tac dong boi yeu to nao?",
            sources=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["level"], "fail")
        self.assertIn("missing_task_coverage", result["reason"])
        self.assertEqual(result["task_coverage"]["total_tasks"], 2)
        self.assertIn("task_2", result["task_coverage"]["missing_tasks"])

    def test_rag_completeness_fails_when_too_short(self):
        answer = "Theo BLS, CPI cao co the lam vang bien dong."

        result = check_answer_completeness(
            answer,
            "STOP",
            intent="FINANCIAL_RAG",
            query="CPI cao anh huong vang the nao?",
            sources=[{"metadata": {"title": "US CPI Report", "organization": "BLS"}}],
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["level"], "fail")
        self.assertTrue(result["reason"].startswith("too_short:"))


if __name__ == "__main__":
    unittest.main()
