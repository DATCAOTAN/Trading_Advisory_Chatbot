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


def install_stubs():
    if importlib.util.find_spec("streamlit") is None:
        streamlit_stub = types.ModuleType("streamlit")
        streamlit_stub.cache_resource = lambda func=None, **kwargs: func if func is not None else (lambda f: f)
        sys.modules["streamlit"] = streamlit_stub

    if importlib.util.find_spec("cohere") is None:
        cohere_stub = types.ModuleType("cohere")
        cohere_stub.Client = object
        cohere_stub.ClientV2 = object
        sys.modules["cohere"] = cohere_stub

    if importlib.util.find_spec("dotenv") is None:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = dotenv_stub

    if importlib.util.find_spec("ollama") is None:
        sys.modules["ollama"] = types.ModuleType("ollama")


install_stubs()

from src.pipelines.context_packer import ContextPacker
from src.services.llm_service import LLMService
from src.ui.tab_chatbot import _normalize_source_for_display


def make_doc(content="EMA context", **metadata):
    return {
        "content": content,
        "metadata": {
            "source": "technical_analysis_financial_markets_ocr.pdf",
            "doc_type": "book",
            "doc_id": "book_technical_analysis_financial_markets_john_murphy_v1",
            "chunk_id": "doc_p12_c1",
            "parent_chunk_id": "doc_p12_parent1",
            "title": "Technical Analysis of the Financial Markets",
            "author": "John Murphy",
            "page": 12,
            "domain": "technical",
            "subdomain": "indicators",
            "source_tier": "tier2",
            "chunk_policy_id": "technical_indicators",
            **metadata,
        },
        "score": 0.91,
    }


class CapturingLLMService(LLMService):
    def __init__(self):
        self.calls = []

    def _call(self, messages, stream=False, temperature=0.2):
        self.calls.append({
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        })
        return iter(["ok"])


class Sprint84SourceAwareAnswerTests(unittest.TestCase):
    def test_source_aware_context_formatting_with_v3_metadata(self):
        context = ContextPacker().render_context([make_doc()])

        self.assertIn("[SOURCE]", context)
        self.assertIn("Title: Technical Analysis of the Financial Markets", context)
        self.assertIn("Author: John Murphy", context)
        self.assertIn("Page: 12", context)
        self.assertIn("Routing: technical/indicators", context)
        self.assertNotIn("Doc ID:", context)
        self.assertNotIn("Chunk ID:", context)
        self.assertIn("[CONTENT]\nEMA context", context)

    def test_source_aware_context_formatting_with_legacy_metadata(self):
        doc = {
            "content": "legacy parent text",
            "metadata": {"source": "legacy.pdf", "doc_type": "static", "parent_id": 7},
            "score": 0.42,
        }

        context = ContextPacker().render_context([doc])

        self.assertIn("Title: legacy.pdf", context)
        self.assertIn("Doc type: static", context)
        self.assertIn("[CONTENT]\nlegacy parent text", context)

    def test_missing_metadata_does_not_crash_context_formatting(self):
        context = ContextPacker().render_context([{"content": "bare context", "score": 0.1}])

        self.assertIn("Title: Unknown source", context)
        self.assertIn("[CONTENT]\nbare context", context)

    def test_finance_answer_contract_contains_risk_constraints(self):
        contract = LLMService.FINANCE_ANSWER_CONTRACT.lower()

        self.assertIn("guaranteed profit", contract)
        self.assertIn("must buy now", contract)
        self.assertIn("must sell now", contract)
        self.assertIn("static educational context", contract)
        self.assertIn("do not invent citations", contract)

    def test_generation_prompt_uses_source_headers_and_risk_contract(self):
        svc = CapturingLLMService()
        context = ContextPacker().render_context([make_doc()])

        output = "".join(svc.generate_multihop_stream("EMA là gì?", context))

        self.assertEqual(output, "ok")
        system_prompt = svc.calls[0]["messages"][0]["content"]
        user_prompt = svc.calls[0]["messages"][-1]["content"]
        self.assertIn("FINANCE/TRADING ANSWER CONTRACT", system_prompt)
        self.assertIn("guaranteed profit", system_prompt)
        self.assertIn("[SOURCE]", user_prompt)
        self.assertIn("Title/Organization/Author/Period/Page", user_prompt)
        self.assertIn("Doc ID/doc_id/chunk_id/parent_chunk_id", user_prompt)
        self.assertIn("không được trình bày như dữ liệu thị trường live", user_prompt)

    def test_ui_source_rendering_handles_v3_metadata_cleanly(self):
        source_name, doc_type, preview, score = _normalize_source_for_display(make_doc())

        self.assertEqual(
            source_name,
            "Technical Analysis of the Financial Markets - John Murphy (p. 12)",
        )
        self.assertEqual(doc_type, "book")
        self.assertEqual(preview, "EMA context")
        self.assertEqual(score, 0.91)
        self.assertNotIn("�", source_name)
        self.assertNotIn("TÃ", source_name)

    def test_ui_source_rendering_handles_missing_metadata_without_garbled_fallback(self):
        source_name, doc_type, preview, score = _normalize_source_for_display({"content": "plain"})

        self.assertEqual(source_name, "Tai lieu he thong")
        self.assertEqual(doc_type, "")
        self.assertEqual(preview, "plain")
        self.assertEqual(score, 0.0)

    def test_legacy_vector_warmup_is_from_history_service_memory_path(self):
        history_text = (PROJECT_ROOT / "src" / "services" / "history_service.py").read_text(encoding="utf-8")
        orchestrator_text = (PROJECT_ROOT / "src" / "orchestrator.py").read_text(encoding="utf-8")

        self.assertIn("from src.services.vector_service import VectorService", history_text)
        self.assertIn("chat_history_collection", history_text)
        self.assertIn("self.retrieval_adapter.retrieve", orchestrator_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
