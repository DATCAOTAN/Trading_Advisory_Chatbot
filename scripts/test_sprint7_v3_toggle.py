import importlib.util
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


def install_import_stubs():
    if importlib.util.find_spec("ollama") is None:
        sys.modules["ollama"] = types.ModuleType("ollama")

    if importlib.util.find_spec("cohere") is None:
        cohere_stub = types.ModuleType("cohere")
        cohere_stub.Client = object
        cohere_stub.ClientV2 = object
        sys.modules["cohere"] = cohere_stub

    if importlib.util.find_spec("fitz") is None:
        fitz_stub = types.ModuleType("fitz")
        fitz_stub.VersionBind = "test-stub"
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
            "Filter",
            "FieldCondition",
            "MatchValue",
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


install_import_stubs()

from src.config import Config
from src.orchestrator import RAGOrchestrator
from src.pipelines.modules.router import RouteAction
from src.ui.runtime_flags import get_knowledge_v3_flags


class FakeRouter:
    def process(self, query, chat_history):
        return RouteAction.VECTOR_SEARCH, ""


class FakeRewriter:
    def process(self, query, chat_history):
        return query


class FakeRetrievalAdapter:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, **kwargs):
        kwargs["query"] = query
        self.calls.append(kwargs)
        return [{"content": "doc content", "metadata": {"source": "fake"}, "score": 0.9}]
    def infer_routing_filters(self, query, **kwargs):
        return None


class FakeReranker:
    def process(self, query, docs, enabled=None, **kwargs):
        return "reranked context", docs


class FakeLLMService:
    def generate_multihop_stream(self, user_query, combined_context, short_term_history):
        return iter(["answer"])


class FakeQueryPlanAssembler:
    def assemble(self, original_query, rewritten_query):
        from unittest.mock import MagicMock
        plan = MagicMock()
        plan.child_plans = []
        plan.task_id = "task_1"
        plan.source_signals = {}
        return plan

class FakeDecisionContextBuilder:
    def __init__(self):
        self.query_plan_assembler = FakeQueryPlanAssembler()
        self.requirement_planner = type("ReqPlanner", (), {"plan": lambda *args: None})()
        self.execution_planner = type("ExecPlanner", (), {"plan": lambda *args: None})()
        self.capability_registry = None
    def build(self, **kwargs):
        from unittest.mock import MagicMock
        ctx = MagicMock()
        ctx.query_intent = "FINANCIAL_RAG"
        ctx.evidence_bundles = []
        ctx.answer_contracts = []
        ctx.evidence_sufficiency = {"status": "COMPLETE"}
        ctx.sufficiency = {"status": "COMPLETE"}
        ctx.missing_required_context = []
        ctx.query_plan = MagicMock()
        ctx.warnings = []
        return ctx

class FakeOrchestratorContractBuilder:
    def build(self, *args, **kwargs):
        class DummyOutput:
            answer_type = "static_explanation"
        return DummyOutput()

class FakeContextAcquisitionExecutor:
    def __init__(self, *args, **kwargs):
        pass
    def execute(self, *args, **kwargs):
        class DummyBatch:
            task_context_views = []
            results = []
        return DummyBatch()
    def render_context(self, *args, **kwargs):
        return ""
    def knowledge_documents(self, *args, **kwargs):
        return []


def make_orchestrator():
    orch = RAGOrchestrator.__new__(RAGOrchestrator)
    orch.router_module = FakeRouter()
    orch.rewriter_module = FakeRewriter()
    orch.retrieval_adapter = FakeRetrievalAdapter()
    orch.reranker_module = FakeReranker()
    orch.llm_service = FakeLLMService()
    orch.live_service = object()
    orch.evaluator_module = type("FakeEvaluator", (), {"process": lambda *args: (True, "")})()
    orch.decision_context_builder = FakeDecisionContextBuilder()
    orch.orchestrator_contract_builder = FakeOrchestratorContractBuilder()
    orch.context_acquisition_executor = FakeContextAcquisitionExecutor()
    orch._agent_tool_selector = lambda current_query, now_str: [{"tool": "VectorDB_Search", "args": {}}]
    return orch


class Sprint7V3ToggleTests(unittest.TestCase):
    def test_default_config_keeps_v3_disabled(self):
        self.assertFalse(Config.USE_KNOWLEDGE_V3)
        self.assertTrue(Config.KNOWLEDGE_V3_FALLBACK_TO_LEGACY)

        flags = get_knowledge_v3_flags({})

        self.assertFalse(flags["use_knowledge_v3"])
        self.assertTrue(flags["knowledge_v3_fallback_to_legacy"])

    def test_session_override_enables_v3(self):
        session_state = {
            "use_knowledge_v3": True,
            "knowledge_v3_fallback_to_legacy": False,
        }

        flags = get_knowledge_v3_flags(session_state)

        self.assertTrue(flags["use_knowledge_v3"])
        self.assertFalse(flags["knowledge_v3_fallback_to_legacy"])

    def test_orchestrator_passes_v3_and_fallback_flags_to_adapter(self):
        Config.SEMANTIC_CONTEXT_EXECUTOR_AUTHORITATIVE = False
        orch = make_orchestrator()

        stream, sources, intent, artifacts = orch.query_financial_advisor(
            "RSI indicator",
            chat_history=[],
            session_id="session",
            enable_reranker=True,
            use_knowledge_v3=True,
            knowledge_v3_fallback_to_legacy=False,
        )

        self.assertEqual("".join(stream), "answer")
        self.assertEqual(intent, "FINANCIAL_RAG")
        self.assertEqual(sources[0]["content"], "doc content")
        call = orch.retrieval_adapter.calls[0]
        self.assertTrue(call["use_v3"])
        self.assertFalse(call["fallback_to_legacy"])

    def test_orchestrator_uses_legacy_by_default(self):
        Config.SEMANTIC_CONTEXT_EXECUTOR_AUTHORITATIVE = False
        orch = make_orchestrator()

        orch.query_financial_advisor("RSI indicator", chat_history=[], session_id="session")

        call = orch.retrieval_adapter.calls[0]
        self.assertFalse(call["use_v3"])
        self.assertTrue(call["fallback_to_legacy"])

    def test_ui_does_not_import_v3_or_external_services_directly(self):
        forbidden = [
            "KnowledgeService",
            "VectorServiceV3",
            "qdrant_client",
            "cohere",
            "KnowledgeCatalog",
            "catalog_manager",
        ]
        for path in (PROJECT_ROOT / "src" / "ui").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            import_lines = [
                line
                for line in text.splitlines()
                if line.strip().startswith("import ") or line.strip().startswith("from ")
            ]
            joined = "\n".join(import_lines)
            for token in forbidden:
                self.assertNotIn(token, joined, f"{path} imports {token}")

    def test_chatbot_and_settings_expose_v3_indicator_text(self):
        chatbot_text = (PROJECT_ROOT / "src" / "ui" / "tab_chatbot.py").read_text(encoding="utf-8")
        settings_text = (PROJECT_ROOT / "src" / "ui" / "tab_settings.py").read_text(encoding="utf-8")

        self.assertIn("Knowledge V3 experimental retrieval enabled", chatbot_text)
        self.assertIn("Use Knowledge Platform V3 (experimental)", settings_text)
        self.assertIn("Fallback to legacy if V3 fails", settings_text)
        self.assertIn("knowledge_current", settings_text)
        self.assertIn("xauusd_knowledge_v2", settings_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
