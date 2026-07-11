"""Compare legacy and Knowledge Platform V3 retrieval for one query.

This script is retrieval-only:
- no LLM answer generation
- no ingestion
- no collection delete/recreate
- no catalog mutation

It may still need the same local dependencies and API keys as the retrieval
services themselves. If a local Qdrant folder is already locked by the running
Streamlit app, the affected side is reported as SKIP.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def summarize_docs(label: str, docs: List[Dict[str, Any]], collection: str) -> None:
    print(f"\n[{label}] collection={collection} docs={len(docs)}")
    if not docs:
        print("  no results")
        return

    for idx, doc in enumerate(docs[:5], 1):
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        score = _float_or_zero(doc.get("score", doc.get("rerank_score", 0.0)))
        title = metadata.get("title") or metadata.get("source") or doc.get("source") or "Unknown source"
        author = metadata.get("author") or ""
        page = metadata.get("page")
        domain = metadata.get("domain") or ""
        subdomain = metadata.get("subdomain") or ""
        chunk_id = metadata.get("chunk_id") or ""
        parent_chunk_id = metadata.get("parent_chunk_id") or metadata.get("parent_id") or ""
        routing = f"{domain}/{subdomain}".strip("/")
        print(f"  #{idx} score={score:.4f} title={title}")
        if author:
            print(f"     author={author}")
        if page not in {None, ""}:
            print(f"     page={page}")
        if routing:
            print(f"     domain={routing}")
        if chunk_id:
            print(f"     chunk_id={chunk_id}")
        if parent_chunk_id:
            print(f"     parent_chunk_id={parent_chunk_id}")


def run_legacy(query: str, top_k: int) -> Optional[List[Dict[str, Any]]]:
    try:
        from src.services.vector_service import VectorService

        start = time.perf_counter()
        service = VectorService()
        docs = service.retrieve_candidates(query, top_k=top_k)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"[legacy] latency_ms={elapsed_ms:.2f}")
        return docs
    except Exception as exc:
        print(f"[legacy][SKIP] {exc}")
        return None


def run_v3(query: str, top_k: int, domain: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    try:
        from src.services.knowledge.knowledge_service import KnowledgeService, SearchRequest
        from src.services.retrieval_adapter import RetrievalAdapter

        adapter = RetrievalAdapter(legacy_service=None)
        resolved_domain = domain or adapter.infer_domain(query)
        if not resolved_domain:
            print("[v3][SKIP] could not infer domain. Pass --domain technical|risk|macro|strategy.")
            return None

        start = time.perf_counter()
        response = KnowledgeService().search(
            SearchRequest(
                query=query,
                routing_filters={"domain": resolved_domain},
                top_k=top_k,
                score_threshold=0.0,
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(
            f"[v3] latency_ms={elapsed_ms:.2f} "
            f"fallback_level={response.fallback_level} total_found={response.total_found}"
        )
        return [adapter._v3_chunk_to_legacy_doc(chunk) for chunk in response.chunks]
    except Exception as exc:
        print(f"[v3][SKIP] {exc}")
        return None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy vs V3 retrieval for a single query.")
    parser.add_argument("query", help="Query to retrieve against both stores.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--domain", default=None, help="Optional V3 domain override: technical, risk, macro, strategy.")
    args = parser.parse_args()

    print(f"Query: {args.query}")
    legacy_docs = run_legacy(args.query, args.top_k)
    v3_docs = run_v3(args.query, args.top_k, args.domain)

    if legacy_docs is not None:
        from src.config import Config

        summarize_docs("legacy", legacy_docs, Config.VECTOR_COLLECTION_NAME)
    if v3_docs is not None:
        from src.services.retrieval_adapter import KNOWLEDGE_V3_COLLECTION

        summarize_docs("v3", v3_docs, KNOWLEDGE_V3_COLLECTION)

    if legacy_docs is None and v3_docs is None:
        print("\nFINAL: SKIPPED - neither retrieval backend could be initialized.")
        return 2

    print("\nFINAL: DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
