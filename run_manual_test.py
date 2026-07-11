import asyncio
from src.orchestrator import RAGOrchestrator

orch = RAGOrchestrator()
stream, sources, intent, artifacts = orch.query_financial_advisor(
    "CPI mới nhất ảnh hưởng XAUUSD thế nào? Al Brooks nói gì về price action?",
    chat_history=[],
    session_id="manual_test",
    enable_self_correction=False,
    enable_reranker=True,
    use_knowledge_v3=True,
    knowledge_v3_fallback_to_legacy=False
)

print(f"Intent: {intent}")
print(f"Sources: {len(sources)}")
print(f"Artifacts keys: {list(artifacts.keys()) if artifacts else []}")
print(f"Is bounded response: {artifacts.get('is_bounded_response') if artifacts else False}")

answer = ""
for chunk in stream:
    answer += chunk
print(f"\nAnswer:\n{answer}")
