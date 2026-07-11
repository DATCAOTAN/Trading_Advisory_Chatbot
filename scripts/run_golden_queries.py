"""Manual golden-query runner.

This script is intentionally small: it exercises the configured orchestrator
against a fixed set of representative queries and prints compact outputs for
human inspection. It does not mutate ingestion, Qdrant, providers, or execution
settings.
"""

from src.orchestrator import RAGOrchestrator


GOLDEN_QUERIES = [
    "Al Brooks noi gi ve price action?",
    "CPI report noi gi ve inflation?",
    "CPI moi nhat anh huong XAUUSD the nao?",
    "XAUUSD hien tai dang chiu tac dong boi yeu to nao?",
    "CPI moi nhat anh huong XAUUSD the nao?\nAl Brooks noi gi ve price action?",
]


def main() -> None:
    orchestrator = RAGOrchestrator()
    for index, query in enumerate(GOLDEN_QUERIES, start=1):
        print(f"\n=== GOLDEN CASE {index} ===")
        print(query)
        stream, sources, mode, artifacts = orchestrator.query_financial_advisor(
            query,
            use_knowledge_v3=True,
            knowledge_v3_fallback_to_legacy=False,
            enable_reranker=True,
        )
        answer = "".join(str(chunk or "") for chunk in stream)
        print(f"mode={mode} sources={len(sources or [])}")
        if artifacts:
            print(f"evidence={artifacts.get('evidence_sufficiency')}")
            print(f"contract={artifacts.get('contract_evaluation')}")
            print(f"repair={artifacts.get('AnswerCoverageRepair')}")
        print(answer[:1200])


if __name__ == "__main__":
    main()
