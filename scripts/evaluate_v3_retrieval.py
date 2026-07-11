import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = Path(__file__).with_name("v3_retrieval_eval_cases.json")
REQUIRED_CITATION_FIELDS = {"doc_id", "chunk_id", "title", "author", "source_tier"}


@dataclass
class RetrievalEvalCase:
    id: str
    query: str
    routing_filters: Dict[str, Any] = field(default_factory=dict)
    expected_domain: str = ""
    expected_subdomain: str = ""
    expected_source_contains: str = ""
    expected_author_contains: str = ""
    expected_organization: str = ""
    expected_organization_contains: str = ""
    expected_title_contains: str = ""
    expected_author: str = ""
    expected_title: str = ""
    expected_event_type: str = ""
    expected_knowledge_type: str = ""
    expected_document_type: str = ""
    expected_in_top_k: Optional[int] = None
    expected_primary: bool = False
    must_use_v3: bool = True
    must_not_fallback_legacy: bool = True
    min_score: Optional[float] = None
    top_k: int = 8
    score_threshold: float = 0.0
    language: str = "en"
    enabled: bool = True
    notes: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class RetrievalEvalResult:
    case_id: str
    query: str
    passed: bool
    reasons: List[str]
    top_k_returned: int
    best_score: float
    fallback_level: Optional[int]
    latency_ms: Optional[float]
    domain_matched: Optional[bool]
    subdomain_matched: Optional[bool]
    title_matched: Optional[bool]
    author_matched: Optional[bool]
    organization_matched: Optional[bool]
    event_type_matched: Optional[bool]
    knowledge_type_matched: Optional[bool]
    document_type_matched: Optional[bool]
    source_matched: Optional[bool]
    primary_source_matched: Optional[bool]
    expected_source_rank: Optional[int]
    expected_in_top_k_matched: Optional[bool]
    fallback_to_legacy: bool
    duplicate_parent_chunk_count: int
    missing_citation_count: int
    missing_metadata_count: int
    actual_top_authors: List[str] = field(default_factory=list)
    actual_top_titles: List[str] = field(default_factory=list)
    skipped: bool = False


@dataclass
class RetrievalEvalSummary:
    total_cases: int
    passed_cases: int
    failed_cases: int
    skipped_cases: int
    primary_source_hit_rate: float
    expected_source_top_k_rate: float
    expected_domain_hit_rate: float
    expected_subdomain_hit_rate: float
    legacy_fallback_count: int
    duplicate_parent_chunk_count: int
    missing_citation_count: int
    missing_metadata_count: int
    average_latency_ms: float
    results: List[RetrievalEvalResult] = field(default_factory=list)


def load_cases(path: str) -> List[RetrievalEvalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Evaluation case file must contain a JSON list.")

    cases = []
    for index, raw in enumerate(data, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Case #{index} must be an object.")
        if not raw.get("query"):
            raise ValueError(f"Case #{index} is missing query.")
        case_id = raw.get("id") or f"case_{index}"
        routing_filters = raw.get("routing_filters") or {}
        if not isinstance(routing_filters, dict):
            raise ValueError(f"Case {case_id} routing_filters must be an object.")
        expected_author = raw.get("expected_author", "")
        expected_organization = raw.get("expected_organization", "")
        expected_title = raw.get("expected_title", "")
        cases.append(RetrievalEvalCase(
            id=case_id,
            query=raw["query"],
            routing_filters=routing_filters,
            expected_domain=raw.get("expected_domain", ""),
            expected_subdomain=raw.get("expected_subdomain", ""),
            expected_source_contains=raw.get("expected_source_contains", ""),
            expected_author_contains=raw.get("expected_author_contains", expected_author),
            expected_organization=expected_organization,
            expected_organization_contains=raw.get("expected_organization_contains", expected_organization),
            expected_title_contains=raw.get("expected_title_contains", expected_title),
            expected_author=expected_author,
            expected_title=expected_title,
            expected_event_type=raw.get("expected_event_type", ""),
            expected_knowledge_type=raw.get("expected_knowledge_type", ""),
            expected_document_type=raw.get("expected_document_type", ""),
            expected_in_top_k=raw.get("expected_in_top_k"),
            expected_primary=bool(raw.get("expected_primary", False)),
            must_use_v3=bool(raw.get("must_use_v3", True)),
            must_not_fallback_legacy=bool(raw.get("must_not_fallback_legacy", True)),
            min_score=raw.get("min_score"),
            top_k=int(raw.get("top_k", 8)),
            score_threshold=float(raw.get("score_threshold", 0.0)),
            language=raw.get("language", "en"),
            enabled=bool(raw.get("enabled", True)),
            notes=raw.get("notes", ""),
            tags=raw.get("tags", []) if isinstance(raw.get("tags", []), list) else [],
        ))
    return cases


def evaluate_cases(cases: List[RetrievalEvalCase], retrieval_service: Any) -> RetrievalEvalSummary:
    results = [evaluate_case(case, retrieval_service) for case in cases]
    active = [result for result in results if not result.skipped]
    latencies = [result.latency_ms for result in active if result.latency_ms is not None]
    return RetrievalEvalSummary(
        total_cases=len(results),
        passed_cases=sum(1 for result in active if result.passed),
        failed_cases=sum(1 for result in active if not result.passed),
        skipped_cases=sum(1 for result in results if result.skipped),
        primary_source_hit_rate=_rate(
            sum(1 for result in active if result.primary_source_matched is True),
            sum(1 for result in active if result.primary_source_matched is not None),
        ),
        expected_source_top_k_rate=_rate(
            sum(1 for result in active if result.expected_in_top_k_matched is True),
            sum(1 for result in active if result.expected_in_top_k_matched is not None),
        ),
        expected_domain_hit_rate=_rate(
            sum(1 for result in active if result.domain_matched is True),
            sum(1 for result in active if result.domain_matched is not None),
        ),
        expected_subdomain_hit_rate=_rate(
            sum(1 for result in active if result.subdomain_matched is True),
            sum(1 for result in active if result.subdomain_matched is not None),
        ),
        legacy_fallback_count=sum(1 for result in active if result.fallback_to_legacy),
        duplicate_parent_chunk_count=sum(result.duplicate_parent_chunk_count for result in active),
        missing_citation_count=sum(result.missing_citation_count for result in active),
        missing_metadata_count=sum(result.missing_metadata_count for result in active),
        average_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        results=results,
    )


def evaluate_case(case: RetrievalEvalCase, retrieval_service: Any) -> RetrievalEvalResult:
    if not case.enabled:
        return RetrievalEvalResult(
            case_id=case.id,
            query=case.query,
            passed=True,
            reasons=["case disabled"],
            top_k_returned=0,
            best_score=0.0,
            fallback_level=None,
            latency_ms=None,
            domain_matched=None,
            subdomain_matched=None,
            title_matched=None,
            author_matched=None,
            organization_matched=None,
            event_type_matched=None,
            knowledge_type_matched=None,
            document_type_matched=None,
            source_matched=None,
            primary_source_matched=None,
            expected_source_rank=None,
            expected_in_top_k_matched=None,
            fallback_to_legacy=False,
            duplicate_parent_chunk_count=0,
            missing_citation_count=0,
            missing_metadata_count=0,
            skipped=True,
        )

    response = retrieval_service.search(_build_search_request(case))
    chunks = list(getattr(response, "chunks", []) or [])
    best_score = max([_as_float(chunk.get("score")) for chunk in chunks], default=0.0)

    duplicate_parent_count = count_duplicate_parent_chunks(chunks)
    missing_citation_count = count_missing_citations(chunks)
    missing_metadata_count = count_missing_metadata(chunks)

    domain_matched = _optional_match(case.expected_domain, chunks, _chunk_domain, exact=True)
    subdomain_matched = _optional_match(case.expected_subdomain, chunks, _chunk_subdomain, exact=True)
    title_expected = case.expected_title_contains or case.expected_title
    author_expected = case.expected_author_contains or case.expected_author
    organization_expected = case.expected_organization_contains or case.expected_organization
    title_matched = _optional_match(title_expected, chunks, _chunk_title, exact=False)
    author_matched = _optional_match(author_expected, chunks, _chunk_author, exact=False)
    organization_matched = _optional_match(organization_expected, chunks, _chunk_organization, exact=False)
    event_type_matched = _optional_match(case.expected_event_type, chunks, _chunk_event_type, exact=True)
    knowledge_type_matched = _optional_match(case.expected_knowledge_type, chunks, _chunk_knowledge_type, exact=True)
    document_type_matched = _optional_match(case.expected_document_type, chunks, _chunk_document_type, exact=True)
    source_matched = _optional_match(case.expected_source_contains, chunks, _chunk_source_blob, exact=False)
    source_rank = _expected_source_rank(case, chunks)
    missing_optional_report_source = _should_skip_missing_report_source(case, chunks, source_rank)
    primary_matched = None if not case.expected_primary else source_rank == 1
    top_k_matched = None
    if case.expected_in_top_k is not None:
        top_k_matched = source_rank is not None and source_rank <= int(case.expected_in_top_k)
    fallback_to_legacy = bool(getattr(response, "fallback_to_legacy", False))

    reasons = []
    if not chunks:
        reasons.append("no chunks returned")
    if missing_optional_report_source:
        reason = (
            "Expected source not indexed: "
            f"organization={case.expected_organization or case.expected_author or organization_expected} "
            f"subdomain={case.expected_subdomain}"
        )
        return RetrievalEvalResult(
            case_id=case.id,
            query=case.query,
            passed=True,
            reasons=[reason],
            top_k_returned=len(chunks),
            best_score=best_score,
            fallback_level=getattr(response, "fallback_level", None),
            latency_ms=getattr(response, "latency_ms", None),
            domain_matched=domain_matched,
            subdomain_matched=subdomain_matched,
            title_matched=title_matched,
            author_matched=author_matched,
            organization_matched=organization_matched,
            event_type_matched=event_type_matched,
            knowledge_type_matched=knowledge_type_matched,
            document_type_matched=document_type_matched,
            source_matched=source_matched,
            primary_source_matched=None,
            expected_source_rank=None,
            expected_in_top_k_matched=None,
            fallback_to_legacy=fallback_to_legacy,
            duplicate_parent_chunk_count=duplicate_parent_count,
            missing_citation_count=missing_citation_count,
            missing_metadata_count=missing_metadata_count,
            actual_top_authors=[_chunk_author(chunk) for chunk in chunks[:5]],
            actual_top_titles=[_chunk_title(chunk) for chunk in chunks[:5]],
            skipped=True,
        )
    if case.min_score is not None and best_score < case.min_score:
        reasons.append(f"best_score {best_score:.4f} below min_score {case.min_score:.4f}")
    if case.must_not_fallback_legacy and fallback_to_legacy:
        reasons.append("legacy fallback was used")
    _append_match_reason(reasons, "domain", case.expected_domain, domain_matched)
    _append_match_reason(reasons, "subdomain", case.expected_subdomain, subdomain_matched)
    _append_match_reason(reasons, "title", title_expected, title_matched)
    _append_match_reason(reasons, "author", author_expected, author_matched)
    _append_match_reason(reasons, "organization", organization_expected, organization_matched)
    _append_match_reason(reasons, "event_type", case.expected_event_type, event_type_matched)
    _append_match_reason(reasons, "knowledge_type", case.expected_knowledge_type, knowledge_type_matched)
    _append_match_reason(reasons, "document_type", case.expected_document_type, document_type_matched)
    _append_match_reason(reasons, "source", case.expected_source_contains, source_matched)
    if primary_matched is False:
        reasons.append("expected primary source not found in top result")
    if top_k_matched is False:
        reasons.append(f"expected source not found in top {case.expected_in_top_k}")
    if duplicate_parent_count:
        reasons.append(f"duplicate parent_chunk_id count: {duplicate_parent_count}")
    if missing_citation_count:
        reasons.append(f"chunks with missing citation fields: {missing_citation_count}")
    if missing_metadata_count:
        reasons.append(f"chunks with missing metadata: {missing_metadata_count}")

    return RetrievalEvalResult(
        case_id=case.id,
        query=case.query,
        passed=not reasons,
        reasons=reasons,
        top_k_returned=len(chunks),
        best_score=best_score,
        fallback_level=getattr(response, "fallback_level", None),
        latency_ms=getattr(response, "latency_ms", None),
        domain_matched=domain_matched,
        subdomain_matched=subdomain_matched,
        title_matched=title_matched,
        author_matched=author_matched,
        organization_matched=organization_matched,
        event_type_matched=event_type_matched,
        knowledge_type_matched=knowledge_type_matched,
        document_type_matched=document_type_matched,
        source_matched=source_matched,
        primary_source_matched=primary_matched,
        expected_source_rank=source_rank,
        expected_in_top_k_matched=top_k_matched,
        fallback_to_legacy=fallback_to_legacy,
        duplicate_parent_chunk_count=duplicate_parent_count,
        missing_citation_count=missing_citation_count,
        missing_metadata_count=missing_metadata_count,
        actual_top_authors=[_chunk_author(chunk) for chunk in chunks[:5]],
        actual_top_titles=[_chunk_title(chunk) for chunk in chunks[:5]],
    )


def count_duplicate_parent_chunks(chunks: List[Dict[str, Any]]) -> int:
    seen = set()
    duplicates = 0
    for chunk in chunks:
        parent_chunk_id = (chunk.get("metadata") or {}).get("parent_chunk_id")
        if not parent_chunk_id:
            continue
        if parent_chunk_id in seen:
            duplicates += 1
        else:
            seen.add(parent_chunk_id)
    return duplicates


def count_missing_citations(chunks: List[Dict[str, Any]]) -> int:
    missing = 0
    for chunk in chunks:
        citation = chunk.get("citation")
        if not isinstance(citation, dict):
            missing += 1
            continue
        missing_required = [field for field in REQUIRED_CITATION_FIELDS if not _has_value(citation.get(field))]
        if missing_required and not citation.get("organization"):
            missing += 1
    return missing


def count_missing_metadata(chunks: List[Dict[str, Any]]) -> int:
    return sum(1 for chunk in chunks if not isinstance(chunk.get("metadata"), dict) or not chunk.get("metadata"))


def print_summary(summary: RetrievalEvalSummary) -> None:
    print("[V3 Retrieval Evaluation]")
    for result in summary.results:
        status = "SKIP" if result.skipped else "PASS" if result.passed else "FAIL"
        print(
            f"{status} {result.case_id}: "
            f"returned={result.top_k_returned} "
            f"best_score={result.best_score:.4f} "
            f"fallback={_format_optional(result.fallback_level)} "
            f"latency_ms={_format_latency(result.latency_ms)} "
            f"primary={_format_optional(result.primary_source_matched)} "
            f"source_rank={_format_optional(result.expected_source_rank)} "
            f"dup_parent={result.duplicate_parent_chunk_count} "
            f"missing_citation={result.missing_citation_count} "
            f"missing_metadata={result.missing_metadata_count}"
        )
        print(
            f"[RetrievalEval] case={result.case_id} pass={result.passed} "
            f"actual_top_authors={result.actual_top_authors} actual_top_titles={result.actual_top_titles}"
        )
        if result.reasons:
            print(f"  query={result.query!r}")
            for reason in result.reasons:
                print(f"  - {reason}")

    print("\n[summary]")
    print(f"total_cases: {summary.total_cases}")
    print(f"passed_cases: {summary.passed_cases}")
    print(f"failed_cases: {summary.failed_cases}")
    print(f"skipped_cases: {summary.skipped_cases}")
    print(f"primary_source_hit_rate: {summary.primary_source_hit_rate:.2%}")
    print(f"expected_source_top_k_rate: {summary.expected_source_top_k_rate:.2%}")
    print(f"expected_domain_hit_rate: {summary.expected_domain_hit_rate:.2%}")
    print(f"expected_subdomain_hit_rate: {summary.expected_subdomain_hit_rate:.2%}")
    print(f"legacy_fallback_count: {summary.legacy_fallback_count}")
    print(f"duplicate_parent_chunk_count: {summary.duplicate_parent_chunk_count}")
    print(f"missing_citation_count: {summary.missing_citation_count}")
    print(f"missing_metadata_count: {summary.missing_metadata_count}")
    print(f"average_latency_ms: {summary.average_latency_ms:.2f}")
    print("FINAL:", "PASS" if summary.failed_cases == 0 else "FAIL")


def _build_search_request(case: RetrievalEvalCase) -> Any:
    from src.services.knowledge.knowledge_service import SearchRequest

    routing_filters = dict(case.routing_filters or {})
    if not routing_filters.get("domain"):
        from src.services.retrieval_adapter import RetrievalAdapter

        routing_filters.update(RetrievalAdapter(legacy_service=None).infer_routing_filters(case.query))

    return SearchRequest(
        query=case.query,
        routing_filters=routing_filters,
        top_k=case.top_k,
        score_threshold=case.score_threshold,
        language=case.language,
    )


def _build_real_service() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from src.services.knowledge.knowledge_service import KnowledgeService

        return KnowledgeService(), None
    except ImportError as exc:
        return None, f"SKIPPED: missing dependency for V3 retrieval evaluation: {exc}"
    except Exception as exc:
        return None, f"SKIPPED: could not initialize KnowledgeService: {exc}"


def _expected_source_rank(case: RetrievalEvalCase, chunks: List[Dict[str, Any]]) -> Optional[int]:
    has_expected = any([
        case.expected_title,
        case.expected_title_contains,
        case.expected_author,
        case.expected_author_contains,
        case.expected_organization,
        case.expected_organization_contains,
        case.expected_domain,
        case.expected_subdomain,
        case.expected_event_type,
    ])
    if not has_expected:
        return None
    for index, chunk in enumerate(chunks, start=1):
        if _chunk_matches_expected_source(case, chunk):
            return index
    return None


def _chunk_matches_expected_source(case: RetrievalEvalCase, chunk: Dict[str, Any]) -> bool:
    checks = []
    if case.expected_domain:
        checks.append(_norm(_chunk_domain(chunk)) == _norm(case.expected_domain))
    if case.expected_subdomain:
        checks.append(_norm(_chunk_subdomain(chunk)) == _norm(case.expected_subdomain))
    if case.expected_title or case.expected_title_contains:
        checks.append(_norm(case.expected_title or case.expected_title_contains) in _norm(_chunk_title(chunk)))
    if case.expected_author or case.expected_author_contains:
        checks.append(_norm(case.expected_author or case.expected_author_contains) in _norm(_chunk_author(chunk)))
    if case.expected_organization or case.expected_organization_contains:
        checks.append(_norm(case.expected_organization or case.expected_organization_contains) in _norm(_chunk_organization(chunk)))
    if case.expected_event_type:
        checks.append(_norm(case.expected_event_type) == _norm(_chunk_event_type(chunk)))
    return all(checks) if checks else False


def _should_skip_missing_report_source(
    case: RetrievalEvalCase,
    chunks: List[Dict[str, Any]],
    source_rank: Optional[int],
) -> bool:
    is_report_case = _norm(case.expected_knowledge_type) == "report" or "report" in [str(tag).lower() for tag in case.tags]
    return bool(is_report_case and source_rank is None)


def _optional_match(expected: str, chunks: List[Dict[str, Any]], getter, exact: bool) -> Optional[bool]:
    if not expected:
        return None
    expected_norm = _norm(expected)
    for chunk in chunks:
        actual = getter(chunk)
        actual_values = actual if isinstance(actual, list) else [actual]
        for value in actual_values:
            value_norm = _norm(value)
            if exact and value_norm == expected_norm:
                return True
            if not exact and expected_norm in value_norm:
                return True
    return False


def _append_match_reason(reasons: List[str], label: str, expected: str, matched: Optional[bool]) -> None:
    if expected and matched is False:
        reasons.append(f"{label} did not match expected {expected!r}")


def _chunk_domain(chunk: Dict[str, Any]) -> str:
    return (chunk.get("metadata") or {}).get("domain", "")


def _chunk_subdomain(chunk: Dict[str, Any]) -> str:
    return (chunk.get("metadata") or {}).get("subdomain", "")


def _chunk_title(chunk: Dict[str, Any]) -> str:
    citation = chunk.get("citation") or {}
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    return citation.get("title") or document_metadata.get("title") or metadata.get("title", "")


def _chunk_author(chunk: Dict[str, Any]) -> str:
    citation = chunk.get("citation") or {}
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    return citation.get("author") or document_metadata.get("author") or metadata.get("author") or citation.get("organization", "")


def _chunk_organization(chunk: Dict[str, Any]) -> str:
    citation = chunk.get("citation") or {}
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    return citation.get("organization") or document_metadata.get("organization") or metadata.get("organization", "")


def _chunk_event_type(chunk: Dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    return metadata.get("event_type") or document_metadata.get("event_type", "")


def _chunk_knowledge_type(chunk: Dict[str, Any]) -> str:
    return (chunk.get("metadata") or {}).get("knowledge_type", "")


def _chunk_document_type(chunk: Dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    return metadata.get("document_type") or document_metadata.get("document_type", "")


def _chunk_source_blob(chunk: Dict[str, Any]) -> str:
    citation = chunk.get("citation") or {}
    metadata = chunk.get("metadata") or {}
    document_metadata = metadata.get("document_metadata") or {}
    parts = [
        citation.get("doc_id", ""),
        citation.get("chunk_id", ""),
        citation.get("title", ""),
        citation.get("author", ""),
        citation.get("organization", ""),
        metadata.get("organization", ""),
        metadata.get("event_type", ""),
        metadata.get("period", ""),
        metadata.get("country", ""),
        metadata.get("source", ""),
        metadata.get("doc_id", ""),
        metadata.get("chunk_id", ""),
        metadata.get("parent_chunk_id", ""),
        document_metadata.get("title", ""),
        document_metadata.get("author", ""),
        document_metadata.get("organization", ""),
        document_metadata.get("event_type", ""),
        document_metadata.get("period", ""),
        document_metadata.get("original_filename", ""),
    ]
    return " ".join(str(part) for part in parts if part)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _format_optional(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _format_latency(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Knowledge Platform V3 retrieval quality.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to JSON retrieval eval cases.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases(args.cases)
    except Exception as exc:
        print(f"FAILED: could not load evaluation cases: {exc}")
        return 1

    service, error = _build_real_service()
    if error:
        print(error)
        return 2

    summary = evaluate_cases(cases, service)
    print_summary(summary)
    return 0 if summary.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
