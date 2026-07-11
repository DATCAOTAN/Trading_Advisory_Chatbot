import re
from dataclasses import dataclass, field
from typing import List

from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter


@dataclass
class SubQuery:
    query: str
    intent: QueryIntent
    index: int


@dataclass
class QueryDecomposition:
    original_query: str
    subqueries: List[SubQuery] = field(default_factory=list)
    is_multi_intent: bool = False
    reason: str = ""


class QueryDecomposer:
    """Deterministic multi-intent splitter for Knowledge V3 retrieval.

    It intentionally avoids LLM calls. The goal is not linguistic perfection;
    it prevents a multi-line/multi-question request from being forced through
    one QueryIntent/filter.
    """

    def __init__(self, router: QueryIntentRouter = None):
        self.router = router or QueryIntentRouter()

    def decompose(self, query: str) -> QueryDecomposition:
        original = str(query or "").strip()
        parts = self._candidate_parts(original)
        subqueries: List[SubQuery] = []
        for part in parts:
            intent = self.router.route(part)
            if intent.intent_type == "unknown":
                continue
            subqueries.append(SubQuery(query=part, intent=intent, index=len(subqueries) + 1))

        if len(subqueries) < 2:
            return QueryDecomposition(original_query=original, subqueries=subqueries, is_multi_intent=False, reason="single_or_unknown_intent")

        signatures = {
            (
                item.intent.intent_type,
                tuple(item.intent.domain_candidates),
                tuple(item.intent.subdomain_candidates),
                tuple(item.intent.preferred_authors),
                tuple(item.intent.preferred_organizations),
                tuple(item.intent.event_type_candidates),
            )
            for item in subqueries
        }
        if len(signatures) < 2:
            return QueryDecomposition(original_query=original, subqueries=subqueries, is_multi_intent=False, reason="same_intent_signature")

        return QueryDecomposition(
            original_query=original,
            subqueries=subqueries,
            is_multi_intent=True,
            reason="multiple_distinct_intent_signatures",
        )

    @staticmethod
    def _candidate_parts(query: str) -> List[str]:
        if not query:
            return []

        normalized = query.replace("\r\n", "\n").replace("\r", "\n")
        raw_parts: List[str] = []
        for line in normalized.split("\n"):
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if not line:
                continue
            raw_parts.extend(QueryDecomposer._split_question_line(line))

        cleaned = []
        seen = set()
        for part in raw_parts:
            part = re.sub(r"\s+", " ", part).strip(" ;")
            if len(part) < 8:
                continue
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(part)
        return cleaned

    @staticmethod
    def _split_question_line(line: str) -> List[str]:
        if line.count("?") <= 1:
            return [line.strip()]

        pieces = []
        start = 0
        for match in re.finditer(r"\?", line):
            piece = line[start:match.end()].strip()
            if piece:
                pieces.append(piece)
            start = match.end()
        tail = line[start:].strip()
        if tail:
            pieces.append(tail)
        return pieces
