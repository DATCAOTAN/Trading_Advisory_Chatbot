import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.services.knowledge.query_intent import QueryIntent, QueryIntentRouter


@dataclass
class AnswerMode:
    mode: str = "UNKNOWN"
    market_impact_allowed: bool = False
    requires_official_report: bool = False
    requires_book_source: bool = False
    template_id: str = "default"
    confidence: float = 0.0
    reason: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "mode": self.mode,
            "market_impact_allowed": self.market_impact_allowed,
            "requires_official_report": self.requires_official_report,
            "requires_book_source": self.requires_book_source,
            "template_id": self.template_id,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EvidenceSchema:
    event_type: str
    summary_terms: List[str] = field(default_factory=list)
    numbers_terms: List[str] = field(default_factory=list)
    methodology_terms: List[str] = field(default_factory=list)
    market_impact_terms: List[str] = field(default_factory=list)
    secondary_detail_terms: List[str] = field(default_factory=list)
    format_hints: List[str] = field(default_factory=list)

    def terms_for_mode(self, answer_mode: AnswerMode) -> List[str]:
        mode = answer_mode.mode
        if mode == "REPORT_METHODOLOGY":
            return self.methodology_terms or self.summary_terms
        if mode == "REPORT_NUMBERS":
            return self.numbers_terms or self.summary_terms
        if mode == "MARKET_IMPACT":
            return list(dict.fromkeys(self.summary_terms + self.market_impact_terms))
        if mode == "REPORT_SUMMARY":
            return list(dict.fromkeys(self.summary_terms + self.numbers_terms))
        return self.summary_terms

    def penalty_terms_for_mode(self, answer_mode: AnswerMode) -> List[str]:
        if answer_mode.mode in {"REPORT_SUMMARY", "REPORT_NUMBERS"}:
            return self.methodology_terms
        return []


class EvidenceSchemaRegistry:
    """Event-level evidence requirements for report section targeting and prompts."""

    SCHEMAS: Dict[str, EvidenceSchema] = {
        "CPI": EvidenceSchema(
            event_type="CPI",
            summary_terms=[
                "all items",
                "headline cpi",
                "core cpi",
                "less food and energy",
                "over the month",
                "over the year",
                "over the last 12 months",
                "seasonally adjusted",
                "food",
                "energy",
                "shelter",
                "rose",
                "increased",
                "decreased",
            ],
            numbers_terms=[
                "percent",
                "0.",
                "1.",
                "2.",
                "3.",
                "12 months",
                "month",
            ],
            methodology_terms=[
                "cpi-u",
                "cpi-w",
                "c-cpi-u",
                "sample",
                "methodology",
                "price collection",
                "calculation",
                "index calculation",
            ],
            market_impact_terms=[
                "inflation",
                "fed",
                "interest rates",
                "yields",
                "dollar",
                "usd",
                "gold",
            ],
            format_hints=[
                "headline CPI",
                "core CPI",
                "month-over-month/year-over-year",
                "food/energy/shelter",
                "inflation trend",
            ],
        ),
        "NFP": EvidenceSchema(
            event_type="NFP",
            summary_terms=[
                "total nonfarm payroll employment",
                "nonfarm payroll employment",
                "payroll employment",
                "employment continued to trend up",
                "job gains",
                "jobs added",
                "unemployment rate",
                "labor force participation rate",
                "average hourly earnings",
                "earnings",
                "revisions",
                "revised",
                "establishment survey",
                "household survey",
                "sector",
                "sectors",
                "industry",
                "industries",
                "health care",
                "social assistance",
                "leisure and hospitality",
                "government",
                "construction",
                "manufacturing",
            ],
            numbers_terms=[
                "thousand",
                "percent",
                "unemployment rate",
                "average hourly earnings",
                "revisions",
            ],
            methodology_terms=[
                "establishment survey",
                "household survey",
                "seasonal adjustment",
                "definitions",
                "population",
                "civilian noninstitutional population",
                "civilian labor force",
                "employment-population ratio",
                "part time for economic reasons",
                "persons not in the labor force",
                "demographic",
            ],
            market_impact_terms=[
                "labor market strength",
                "wage pressure",
                "fed",
                "interest rates",
                "yields",
                "dollar",
                "usd",
                "gold",
            ],
            format_hints=[
                "headline payroll change",
                "unemployment rate",
                "labor force participation",
                "average hourly earnings",
                "job gains/losses by sector",
                "revisions",
            ],
        ),
        "FOMC": EvidenceSchema(
            event_type="FOMC",
            summary_terms=[
                "policy rate",
                "federal funds rate",
                "inflation",
                "labor market",
                "economic activity",
                "risks",
                "committee",
                "future policy",
            ],
            numbers_terms=["basis points", "percent", "projection", "median"],
            methodology_terms=["minutes", "statement", "summary of economic projections"],
            market_impact_terms=["rates", "yields", "dollar", "usd", "gold", "risk sentiment"],
            format_hints=[
                "policy rate decision",
                "inflation assessment",
                "labor market assessment",
                "risk outlook",
                "future policy guidance",
            ],
        ),
        "FOMC_MINUTES": EvidenceSchema(
            event_type="FOMC_MINUTES",
            summary_terms=[
                "participants",
                "inflation",
                "labor market",
                "policy",
                "interest rates",
                "risks",
                "outlook",
            ],
            numbers_terms=["percent", "basis points", "projection"],
            methodology_terms=["minutes", "discussion"],
            market_impact_terms=["rates", "yields", "dollar", "usd", "gold", "risk sentiment"],
            format_hints=[
                "inflation assessment",
                "labor market assessment",
                "policy stance",
                "risk outlook",
            ],
        ),
        "SEP": EvidenceSchema(
            event_type="SEP",
            summary_terms=["projected", "median", "federal funds rate", "inflation", "unemployment", "gdp"],
            numbers_terms=["median", "range", "central tendency", "percent"],
            methodology_terms=["projections", "assumptions"],
            market_impact_terms=["rate path", "yields", "usd", "gold"],
            format_hints=["policy rate projections", "inflation projections", "growth/unemployment projections"],
        ),
        "GDP": EvidenceSchema(
            event_type="GDP",
            summary_terms=[
                "real gross domestic product",
                "real gdp",
                "consumer spending",
                "investment",
                "government spending",
                "exports",
                "imports",
                "price index",
                "revision",
            ],
            numbers_terms=["percent", "annual rate", "quarter", "estimate", "revision"],
            methodology_terms=["estimate", "revision", "source data", "methodology"],
            market_impact_terms=["growth", "risk sentiment", "yields", "usd"],
            format_hints=["real GDP growth", "consumer spending", "investment", "net exports", "revision"],
        ),
        "GLOBAL_OUTLOOK": EvidenceSchema(
            event_type="GLOBAL_OUTLOOK",
            summary_terms=["global growth", "inflation", "risks", "forecast", "advanced economies", "emerging market"],
            numbers_terms=["percent", "forecast", "projection"],
            methodology_terms=["assumptions", "methodology"],
            market_impact_terms=["risk sentiment", "dollar", "commodities", "gold"],
            format_hints=["global growth", "inflation outlook", "risks", "regional split"],
        ),
        "COMMODITY_MARKETS": EvidenceSchema(
            event_type="COMMODITY_MARKETS",
            summary_terms=["commodity prices", "energy", "oil", "metals", "agriculture", "forecast", "risks"],
            numbers_terms=["percent", "price", "forecast"],
            methodology_terms=["methodology", "assumptions"],
            market_impact_terms=["inflation", "growth", "gold", "risk sentiment"],
            format_hints=["commodity price performance", "energy/metals/agriculture", "forecast", "risks"],
        ),
        "GOLD_MARKET": EvidenceSchema(
            event_type="GOLD_MARKET",
            summary_terms=[
                "gold price",
                "etf flows",
                "central bank demand",
                "investment demand",
                "physical demand",
                "geopolitical risk",
                "dollar",
                "yields",
            ],
            numbers_terms=["tonnes", "percent", "price", "flows"],
            methodology_terms=["methodology", "data"],
            market_impact_terms=["gold", "xauusd", "dollar", "yields", "risk", "central bank buying"],
            format_hints=["gold price performance", "ETF flows", "central bank demand", "USD/yields", "geopolitical risk"],
        ),
    }

    @classmethod
    def get(cls, event_type: str) -> Optional[EvidenceSchema]:
        return cls.SCHEMAS.get(str(event_type or "").upper())

    @classmethod
    def first_for_intent(cls, intent: QueryIntent) -> Optional[EvidenceSchema]:
        for event_type in intent.event_type_candidates:
            schema = cls.get(event_type)
            if schema:
                return schema
        return None


class AnswerModeClassifier:
    """Rule-based answer-mode classifier. No LLM calls."""

    REPORT_SUMMARY_TERMS = [
        "noi gi",
        "cho biet gi",
        "say",
        "what did",
        "what does",
        "indicate",
        "suggest",
        "summary",
        "tom tat",
        "report",
        "statement",
        "minutes",
        "commentary",
        "outlook",
    ]
    NUMBERS_TERMS = ["bao nhieu", "so lieu", "number", "numbers", "data", "figure", "percent", "%"]
    METHODOLOGY_TERMS = [
        "tinh nhu the nao",
        "cach tinh",
        "phuong phap",
        "methodology",
        "method",
        "calculate",
        "calculation",
        "survey",
        "definition",
        "dinh nghia",
    ]
    MARKET_IMPACT_TERMS = [
        "xauusd",
        " vang ",
        " gold ",
        "giao dich",
        "trading",
        " trade ",
        "thi truong",
        "market reaction",
        "market impact",
        "tac dong thi truong",
        "anh huong thi truong",
        "anh huong vang",
        "anh huong gold",
        "anh huong xauusd",
        "impact on gold",
        "impact on xauusd",
        " dxy ",
        " usd ",
        "yield",
        "loi suat trai phieu",
        "entry",
        " sl ",
        " tp ",
        " buy ",
        " sell ",
        "mua hay ban",
        "nen mua",
        "nen ban",
        "gia vang",
        "gold price",
    ]
    UNSUPPORTED_CERTAINTY_TERMS = ["dam bao", "guarantee", "sure win", "chac chan loi", "profit guaranteed"]

    def __init__(self, router: Optional[QueryIntentRouter] = None):
        self.router = router or QueryIntentRouter()

    def classify(self, query: str, intent: Optional[QueryIntent] = None) -> AnswerMode:
        intent = intent or self.router.route(query)
        text = self.normalize(query)
        padded = f" {text} "

        if self._has_any(padded, self.UNSUPPORTED_CERTAINTY_TERMS):
            return AnswerMode(
                mode="INSUFFICIENT_EVIDENCE",
                market_impact_allowed=False,
                template_id="insufficient_evidence",
                confidence=0.95,
                reason="query asks for unsupported certainty or guaranteed outcome",
            )

        if self._has_any(padded, self.MARKET_IMPACT_TERMS):
            return AnswerMode(
                mode="MARKET_IMPACT",
                market_impact_allowed=True,
                requires_official_report=intent.source_preference in {"official_report_first", "mixed_report_and_book"},
                template_id="market_impact",
                confidence=0.92,
                reason="explicit market/trading/gold impact signal",
            )

        if self._has_any(padded, self.METHODOLOGY_TERMS):
            return AnswerMode(
                mode="REPORT_METHODOLOGY" if intent.source_preference != "book_first" else "BOOK_CONCEPT_EXPLANATION",
                market_impact_allowed=False,
                requires_official_report=intent.source_preference in {"official_report_first", "mixed_report_and_book"},
                requires_book_source=intent.source_preference == "book_first",
                template_id="methodology",
                confidence=0.88,
                reason="methodology/calculation signal",
            )

        if self._has_any(padded, self.NUMBERS_TERMS) and intent.source_preference in {"official_report_first", "mixed_report_and_book"}:
            return AnswerMode(
                mode="REPORT_NUMBERS",
                market_impact_allowed=False,
                requires_official_report=True,
                template_id="report_numbers",
                confidence=0.84,
                reason="report numbers/data signal",
            )

        if intent.source_preference == "book_first":
            return AnswerMode(
                mode="BOOK_CONCEPT_EXPLANATION",
                market_impact_allowed=False,
                requires_book_source=True,
                template_id="book_concept",
                confidence=0.86,
                reason="book/concept intent",
            )

        if intent.source_preference in {"official_report_first", "mixed_report_and_book"} or self._has_any(padded, self.REPORT_SUMMARY_TERMS):
            return AnswerMode(
                mode="REPORT_SUMMARY",
                market_impact_allowed=False,
                requires_official_report=True,
                template_id="report_summary",
                confidence=0.86,
                reason="report summary/default official report mode",
            )

        return AnswerMode(
            mode="UNKNOWN",
            market_impact_allowed=False,
            template_id="default",
            confidence=0.25,
            reason="no answer-mode signal matched",
        )

    @staticmethod
    def normalize(value: str) -> str:
        text = str(value or "").lower().replace("đ", "d")
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _has_any(text: str, terms: List[str]) -> bool:
        return any(term in text for term in terms)
