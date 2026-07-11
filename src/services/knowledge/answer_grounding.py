from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter


@dataclass
class AnswerGroundingPlan:
    documents: List[Dict[str, Any]]
    primary_sources: List[str] = field(default_factory=list)
    supporting_sources: List[str] = field(default_factory=list)
    source_coverage_score: float = 0.0
    missing_source_warnings: List[str] = field(default_factory=list)
    official_report_available: bool = False
    book_source_available: bool = False
    status: str = "insufficient"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "primary_sources": list(self.primary_sources),
            "supporting_sources": list(self.supporting_sources),
            "source_coverage_score": self.source_coverage_score,
            "missing_source_warnings": list(self.missing_source_warnings),
            "official_report_available": self.official_report_available,
            "book_source_available": self.book_source_available,
            "status": self.status,
        }


class AnswerGroundingPlanner:
    """Annotate retrieved docs with source roles before prompt/source panel use."""

    def __init__(self, router: Optional[QueryIntentRouter] = None):
        self.router = router or QueryIntentRouter()

    def build(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        intent: Optional[QueryIntent] = None,
    ) -> AnswerGroundingPlan:
        intent = intent or self.router.route(query)
        docs = [self._clone_doc(doc) for doc in (documents or [])]

        official_docs = [doc for doc in docs if self._is_official_report(doc)]
        book_docs = [doc for doc in docs if self._metadata(doc).get("knowledge_type") == "book"]
        matching_official_docs = [doc for doc in official_docs if self._matches_intent(doc, intent, official=True)]
        matching_book_docs = [doc for doc in book_docs if self._matches_intent(doc, intent, official=False)]

        primary_docs: List[Dict[str, Any]] = []
        supporting_docs: List[Dict[str, Any]] = []
        warnings: List[str] = []

        if intent.source_preference in {"official_report_first", "mixed_report_and_book"}:
            if matching_official_docs:
                primary_docs = matching_official_docs[:1]
                supporting_docs = [doc for doc in docs if doc not in primary_docs]
            elif official_docs:
                primary_docs = official_docs[:1]
                supporting_docs = [doc for doc in docs if doc not in primary_docs]
                warnings.append("official report found, but exact event/source metadata did not match intent")
            else:
                warnings.append("expected official report source was not retrieved")
                supporting_docs = list(docs)
        elif intent.source_preference == "book_first":
            if matching_book_docs:
                primary_docs = matching_book_docs[:1]
                supporting_docs = [doc for doc in docs if doc not in primary_docs]
            elif book_docs:
                primary_docs = book_docs[:1]
                supporting_docs = [doc for doc in docs if doc not in primary_docs]
                warnings.append("book source found, but exact author/subdomain metadata did not match intent")
            else:
                warnings.append("expected book source was not retrieved")
                supporting_docs = list(docs)
        elif docs:
            primary_docs = docs[:1]
            supporting_docs = docs[1:]
        else:
            warnings.append("no retrieved context chunks available")

        primary_keys = {self._identity(doc) for doc in primary_docs}
        supporting_keys = {self._identity(doc) for doc in supporting_docs}
        for doc in docs:
            metadata = self._metadata(doc)
            if self._identity(doc) in primary_keys:
                role = "primary_source"
                reasons = self._usage_reasons(doc, intent, primary=True)
            elif self._identity(doc) in supporting_keys:
                role = "supporting_source"
                reasons = self._usage_reasons(doc, intent, primary=False)
            else:
                role = "retrieved_context"
                reasons = []
            metadata["source_role"] = role
            metadata["source_usage_reasons"] = reasons

        coverage = self._coverage_score(intent, docs, primary_docs, warnings)
        status = "complete" if coverage >= 0.75 and not warnings else ("partial" if coverage >= 0.35 else "insufficient")
        for doc in docs:
            metadata = self._metadata(doc)
            metadata["grounding_coverage_score"] = round(coverage, 3)
            metadata["answer_grounding_status"] = status
            if warnings:
                metadata["grounding_warnings"] = list(warnings)

        plan = AnswerGroundingPlan(
            documents=docs,
            primary_sources=[self._display_name(doc) for doc in primary_docs],
            supporting_sources=[self._display_name(doc) for doc in supporting_docs],
            source_coverage_score=round(coverage, 3),
            missing_source_warnings=warnings,
            official_report_available=bool(official_docs),
            book_source_available=bool(book_docs),
            status=status,
        )
        self.log(query, intent, plan)
        return plan

    def log(self, query: str, intent: QueryIntent, plan: AnswerGroundingPlan) -> None:
        print(
            "[AnswerGrounding] "
            f"query={query!r} "
            f"intent_type={intent.intent_type} "
            f"primary_sources={plan.primary_sources} "
            f"supporting_sources={plan.supporting_sources} "
            f"coverage_score={plan.source_coverage_score:.3f} "
            f"status={plan.status} "
            f"warnings={plan.missing_source_warnings}"
        )

    def _coverage_score(
        self,
        intent: QueryIntent,
        docs: List[Dict[str, Any]],
        primary_docs: List[Dict[str, Any]],
        warnings: List[str],
    ) -> float:
        if not docs:
            return 0.0
        if not primary_docs:
            return 0.25

        primary = primary_docs[0]
        score = 0.45
        if self._matches_domain(primary, intent):
            score += 0.15
        if self._matches_subdomain(primary, intent):
            score += 0.15
        if self._matches_event(primary, intent):
            score += 0.15
        if self._matches_owner(primary, intent):
            score += 0.15
        if intent.source_preference == "official_report_first" and self._is_official_report(primary):
            score += 0.15
        if intent.source_preference == "book_first" and self._metadata(primary).get("knowledge_type") == "book":
            score += 0.10
        if warnings:
            score -= 0.20
        return max(0.0, min(score, 1.0))

    def _usage_reasons(self, doc: Dict[str, Any], intent: QueryIntent, primary: bool) -> List[str]:
        reasons = ["primary_source" if primary else "supporting_source"]
        if self._is_official_report(doc):
            reasons.append("official_report")
        if self._matches_owner(doc, intent):
            reasons.append("matched_author_or_organization")
        if self._matches_event(doc, intent):
            reasons.append("matched_event_type")
        if self._matches_domain(doc, intent):
            reasons.append("matched_domain")
        if self._matches_subdomain(doc, intent):
            reasons.append("matched_subdomain")
        return reasons

    def _matches_intent(self, doc: Dict[str, Any], intent: QueryIntent, official: bool) -> bool:
        if official and not self._is_official_report(doc):
            return False
        if self._matches_event(doc, intent):
            return True
        if self._matches_owner(doc, intent) and (self._matches_domain(doc, intent) or self._matches_subdomain(doc, intent)):
            return True
        if self._matches_domain(doc, intent) and self._matches_subdomain(doc, intent):
            return True
        return False

    def _matches_domain(self, doc: Dict[str, Any], intent: QueryIntent) -> bool:
        domain = str(self._metadata(doc).get("domain", "")).lower()
        return bool(domain and domain in {item.lower() for item in intent.domain_candidates})

    def _matches_subdomain(self, doc: Dict[str, Any], intent: QueryIntent) -> bool:
        subdomain = str(self._metadata(doc).get("subdomain", "")).lower()
        return bool(subdomain and subdomain in {item.lower() for item in intent.subdomain_candidates})

    def _matches_event(self, doc: Dict[str, Any], intent: QueryIntent) -> bool:
        event_type = str(self._metadata(doc).get("event_type", "")).upper()
        return bool(event_type and event_type in {item.upper() for item in intent.event_type_candidates})

    def _matches_owner(self, doc: Dict[str, Any], intent: QueryIntent) -> bool:
        metadata = self._metadata(doc)
        author = str(metadata.get("author", "")).lower()
        organization = str(metadata.get("organization", "")).lower()
        authors = {item.lower() for item in intent.preferred_authors}
        organizations = {item.lower() for item in intent.preferred_organizations}
        return bool((author and author in authors) or (organization and organization in organizations))

    def _is_official_report(self, doc: Dict[str, Any]) -> bool:
        metadata = self._metadata(doc)
        return metadata.get("knowledge_type") == "report" and str(metadata.get("source_tier", "")).lower() == "tier1"

    @staticmethod
    def _clone_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        cloned = dict(doc or {})
        metadata = cloned.get("metadata", {})
        cloned["metadata"] = dict(metadata) if isinstance(metadata, dict) else {}
        return cloned

    @staticmethod
    def _metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
        metadata = doc.get("metadata", {}) if isinstance(doc, dict) else {}
        return metadata if isinstance(metadata, dict) else {}

    def _display_name(self, doc: Dict[str, Any]) -> str:
        metadata = self._metadata(doc)
        title = metadata.get("title") or metadata.get("source") or "Unknown source"
        owner = metadata.get("organization") or metadata.get("author") or ""
        return f"{title} - {owner}" if owner else str(title)

    def _identity(self, doc: Dict[str, Any]) -> str:
        metadata = self._metadata(doc)
        return str(
            metadata.get("parent_chunk_id")
            or metadata.get("chunk_id")
            or metadata.get("doc_id")
            or self._display_name(doc)
        )

