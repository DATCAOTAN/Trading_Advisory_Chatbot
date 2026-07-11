import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class QueryIntent:
    intent_type: str = "unknown"
    domain_candidates: List[str] = field(default_factory=list)
    subdomain_candidates: List[str] = field(default_factory=list)
    source_preference: str = "any"
    preferred_organizations: List[str] = field(default_factory=list)
    preferred_authors: List[str] = field(default_factory=list)
    event_type_candidates: List[str] = field(default_factory=list)
    period_candidates: List[str] = field(default_factory=list)
    required_source_tier: str = "any"
    confidence: float = 0.0
    routing_reason: str = ""
    expanded_terms: List[str] = field(default_factory=list)

    @property
    def primary_domain(self) -> str:
        return self.domain_candidates[0] if self.domain_candidates else ""

    @property
    def primary_subdomain(self) -> str:
        return self.subdomain_candidates[0] if self.subdomain_candidates else ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "domain_candidates": list(self.domain_candidates),
            "subdomain_candidates": list(self.subdomain_candidates),
            "source_preference": self.source_preference,
            "preferred_organizations": list(self.preferred_organizations),
            "preferred_authors": list(self.preferred_authors),
            "event_type_candidates": list(self.event_type_candidates),
            "period_candidates": list(self.period_candidates),
            "required_source_tier": self.required_source_tier,
            "confidence": self.confidence,
            "routing_reason": self.routing_reason,
            "expanded_terms": list(self.expanded_terms),
        }

    @classmethod
    def from_dict(cls, value: Optional[Dict[str, Any]]) -> "QueryIntent":
        if not isinstance(value, dict):
            return cls()
        allowed = {
            "intent_type",
            "domain_candidates",
            "subdomain_candidates",
            "source_preference",
            "preferred_organizations",
            "preferred_authors",
            "event_type_candidates",
            "period_candidates",
            "required_source_tier",
            "confidence",
            "routing_reason",
            "expanded_terms",
        }
        return cls(**{key: value[key] for key in allowed if key in value})


class QueryIntentRouter:
    """Deterministic Knowledge V3 query intent router.

    This is deliberately rule-based. It is used before vector retrieval, so it
    must be fast, explainable, and free from LLM/API calls.
    """

    EXPANSIONS = {
        "FOMC": ["Federal Open Market Committee", "Fed", "interest rates", "policy statement", "minutes", "SEP"],
        "CPI": ["Consumer Price Index", "inflation", "headline CPI", "core CPI", "BLS"],
        "NFP": ["nonfarm payrolls", "employment situation", "unemployment", "BLS"],
        "GDP": ["gross domestic product", "BEA", "real GDP"],
        "GLOBAL_OUTLOOK": ["World Economic Outlook", "global growth", "IMF"],
        "COMMODITY_MARKETS": ["Commodity Markets Outlook", "commodities", "World Bank"],
        "GOLD_MARKET": ["gold", "XAUUSD", "World Gold Council", "ETF flows", "central bank buying"],
        "VPA": ["volume price analysis", "volume spread analysis", "Anna Coulling"],
        "R_MULTIPLE": ["risk multiple", "R multiple", "position sizing", "Van Tharp"],
        "PRICE_ACTION": ["bar by bar", "price action", "Al Brooks"],
    }

    def route(self, query: str, conversation_context: Optional[str] = None, selected_mode: Optional[str] = None) -> QueryIntent:
        del conversation_context, selected_mode
        raw = query or ""
        text = self.normalize(raw)
        periods = self._period_candidates(text)

        if self._has_explicit_report_signal(text):
            report = self._route_reports_and_markets(text, periods)
            if report.intent_type != "unknown":
                return self._with_expansion(report)

        # Highly specific book/concept routes first. These should not be stolen
        # by generic "gold/trading/forex" terms added by query rewriting.
        concept = self._route_trading_concepts(text, periods)
        if concept.intent_type != "unknown":
            return self._with_expansion(concept)

        report = self._route_reports_and_markets(text, periods)
        if report.intent_type != "unknown":
            return self._with_expansion(report)

        return QueryIntent(
            intent_type="unknown",
            confidence=0.0,
            routing_reason="no deterministic knowledge intent matched",
            period_candidates=periods,
        )

    def _route_trading_concepts(self, text: str, periods: List[str]) -> QueryIntent:
        if self._has_any(text, ["price action", "bar by bar", "al brooks"]):
            return QueryIntent(
                intent_type="price_action",
                domain_candidates=["technical"],
                subdomain_candidates=["price_action"],
                source_preference="book_first",
                preferred_authors=["Al Brooks"],
                confidence=0.95,
                routing_reason="matched price action / Al Brooks terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["volume price analysis", "volume price", " vpa ", "volume analysis", "anna coulling", "volume anomaly", "volume anomalies"]):
            return QueryIntent(
                intent_type="volume_analysis",
                domain_candidates=["technical"],
                subdomain_candidates=["volume"],
                source_preference="book_first",
                preferred_authors=["Anna Coulling"],
                confidence=0.95,
                routing_reason="matched VPA / Anna Coulling terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["risk management", "limit losses", "position sizing", "r multiple", "risk multiple", "risk per trade", "risk reward", "stop loss", "drawdown", "lot size", "expectancy", "van tharp"]):
            return QueryIntent(
                intent_type="risk_management",
                domain_candidates=["risk"],
                subdomain_candidates=["position_sizing"],
                source_preference="book_first",
                preferred_authors=["Van Tharp"],
                confidence=0.95,
                routing_reason="matched risk management / Van Tharp terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["trading discipline", "discipline", "psychology", "fear", "greed", "mark douglas"]):
            return QueryIntent(
                intent_type="trading_psychology",
                domain_candidates=["psychology"],
                subdomain_candidates=["trading_discipline"],
                source_preference="book_first",
                preferred_authors=["Mark Douglas"],
                confidence=0.92,
                routing_reason="matched trading psychology / Mark Douglas terms",
                period_candidates=periods,
            )

        has_trend_following = self._has_any(text, ["trend following", "trend-following", "covel", "turtle"])
        has_indicator_context = self._has_any(text, ["ema", "sma", "rsi", "macd", "indicator", "moving average", "moving averages"])
        if has_trend_following and has_indicator_context:
            return QueryIntent(
                intent_type="technical_analysis",
                domain_candidates=["technical"],
                subdomain_candidates=[],
                source_preference="book_first",
                preferred_authors=["John Murphy"],
                confidence=0.78,
                routing_reason="matched indicator context with trend-following phrase; kept broad technical route",
                period_candidates=periods,
            )
        if has_trend_following and not has_indicator_context:
            return QueryIntent(
                intent_type="trend_following",
                domain_candidates=["strategy"],
                subdomain_candidates=["trend_following"],
                source_preference="book_first",
                preferred_authors=["Michael Covel"],
                confidence=0.95,
                routing_reason="matched trend following / Michael Covel terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["john murphy", "technical analysis", "moving average", "moving averages", "support resistance", "support and resistance", "macd", "rsi", "ema", "sma"]):
            return QueryIntent(
                intent_type="technical_analysis",
                domain_candidates=["technical"],
                subdomain_candidates=["indicators"],
                source_preference="book_first",
                preferred_authors=["John Murphy"],
                confidence=0.88,
                routing_reason="matched technical indicators / John Murphy terms",
                period_candidates=periods,
            )

        # Preserve legacy behavior for broad "indicator trend following" queries:
        # keep the route technical, but avoid hard subdomain narrowing.
        if self._has_any(text, ["indicator", "trading", "forex", "breakout", "support", "resistance", "candlestick", "candle"]):
            return QueryIntent(
                intent_type="technical_analysis",
                domain_candidates=["technical"],
                subdomain_candidates=[],
                source_preference="book_first",
                preferred_authors=["John Murphy"],
                confidence=0.72,
                routing_reason="matched broad technical-analysis terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["bernanke", "financial crisis", "monetary policy"]):
            return QueryIntent(
                intent_type="monetary_policy",
                domain_candidates=["macro"],
                subdomain_candidates=["monetary_policy"],
                source_preference="book_first",
                preferred_authors=["Ben Bernanke"],
                confidence=0.90,
                routing_reason="matched Bernanke / monetary policy book terms",
                period_candidates=periods,
            )

        return QueryIntent(period_candidates=periods)

    def _has_explicit_report_signal(self, text: str) -> bool:
        return self._has_any(
            text,
            [
                "commodity markets outlook",
                "commodity outlook",
                "gold market commentary",
                "gold market report",
                "world gold council",
                "world economic outlook",
                "fomc",
                "fomc minutes",
                "fomc statement",
                "summary of economic projections",
                "cpi report",
                "nfp report",
                "nonfarm payrolls",
                "gdp report",
            ],
        )

    def _route_reports_and_markets(self, text: str, periods: List[str]) -> QueryIntent:
        has_gold = self._has_any(text, ["gold", "xau", "xauusd", "vang"])
        has_cpi = self._has_any(text, ["cpi", "consumer price index", "inflation", "core cpi", "headline cpi"])
        has_fomc = self._has_any(text, ["fomc", "federal reserve", "fed", "dot plot", "rate path", "powell", "interest rate", "policy rate"])
        has_nfp = self._has_any(text, ["nfp", "nonfarm", "payroll", "employment report", "jobs report", "unemployment"])
        has_gdp = self._has_any(text, ["gdp", "gross domestic product", "bea"])
        has_weo = self._has_any(text, ["world economic outlook", "global outlook", "imf", "weo"])
        has_commodity = self._has_any(text, ["commodity markets outlook", "commodity outlook", "commodity market", "commodity markets", "commodities", "hang hoa", "oil", "copper"])

        if has_cpi and has_gold:
            return QueryIntent(
                intent_type="mixed",
                domain_candidates=["macro", "market"],
                subdomain_candidates=["inflation", "gold"],
                source_preference="mixed_report_and_book",
                preferred_organizations=["BLS", "World Gold Council"],
                event_type_candidates=["CPI", "GOLD_MARKET"],
                required_source_tier="tier1_or_tier2",
                confidence=0.94,
                routing_reason="matched CPI macro event plus gold impact terms",
                period_candidates=periods,
            )

        if has_fomc and has_gold:
            return QueryIntent(
                intent_type="mixed",
                domain_candidates=["macro", "market"],
                subdomain_candidates=["central_bank", "gold"],
                source_preference="mixed_report_and_book",
                preferred_organizations=["Federal Reserve", "World Gold Council"],
                event_type_candidates=self._fomc_events(text) + ["GOLD_MARKET"],
                required_source_tier="tier1_or_tier2",
                confidence=0.93,
                routing_reason="matched FOMC/Fed event plus gold impact terms",
                period_candidates=periods,
            )

        if self._has_any(text, ["gold market commentary", "gold market report", "world gold council", "wgc", "gold market"]) or (
            has_gold and not (has_cpi or has_fomc or has_nfp or has_gdp)
        ):
            return QueryIntent(
                intent_type="market_gold",
                domain_candidates=["market"],
                subdomain_candidates=["gold"],
                source_preference="official_report_first",
                preferred_organizations=["World Gold Council"],
                event_type_candidates=["GOLD_MARKET"],
                required_source_tier="tier1_or_tier2",
                confidence=0.92,
                routing_reason="matched gold market / World Gold Council terms",
                period_candidates=periods,
            )

        if has_commodity:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["market"],
                subdomain_candidates=["commodities"],
                source_preference="official_report_first",
                preferred_organizations=["World Bank"],
                event_type_candidates=["COMMODITY_MARKETS"],
                required_source_tier="tier1_or_tier2",
                confidence=0.94,
                routing_reason="matched commodity market official report terms",
                period_candidates=periods,
            )

        if has_weo:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["macro"],
                subdomain_candidates=["global_outlook"],
                source_preference="official_report_first",
                preferred_organizations=["IMF"],
                event_type_candidates=["GLOBAL_OUTLOOK"],
                required_source_tier="tier1_or_tier2",
                confidence=0.94,
                routing_reason="matched World Economic Outlook / IMF terms",
                period_candidates=periods,
            )

        if has_fomc:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["macro"],
                subdomain_candidates=["central_bank"],
                source_preference="official_report_first",
                preferred_organizations=["Federal Reserve"],
                event_type_candidates=self._fomc_events(text),
                required_source_tier="tier1_or_tier2",
                confidence=0.92,
                routing_reason="matched FOMC/Fed official report terms",
                period_candidates=periods,
            )

        if has_cpi:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["macro"],
                subdomain_candidates=["inflation"],
                source_preference="official_report_first",
                preferred_organizations=["BLS"],
                event_type_candidates=["CPI"],
                required_source_tier="tier1_or_tier2",
                confidence=0.92,
                routing_reason="matched CPI/inflation official report terms",
                period_candidates=periods,
            )

        if has_nfp:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["macro"],
                subdomain_candidates=["employment"],
                source_preference="official_report_first",
                preferred_organizations=["BLS"],
                event_type_candidates=["NFP"],
                required_source_tier="tier1_or_tier2",
                confidence=0.92,
                routing_reason="matched NFP/employment official report terms",
                period_candidates=periods,
            )

        if has_gdp:
            return QueryIntent(
                intent_type="macro_report",
                domain_candidates=["macro"],
                subdomain_candidates=["gdp"],
                source_preference="official_report_first",
                preferred_organizations=["BEA"],
                event_type_candidates=["GDP"],
                required_source_tier="tier1_or_tier2",
                confidence=0.91,
                routing_reason="matched GDP/BEA official report terms",
                period_candidates=periods,
            )

        return QueryIntent(period_candidates=periods)

    def _with_expansion(self, intent: QueryIntent) -> QueryIntent:
        terms: List[str] = []
        for event in intent.event_type_candidates:
            terms.extend(self.EXPANSIONS.get(event, []))
        if intent.intent_type == "price_action":
            terms.extend(self.EXPANSIONS["PRICE_ACTION"])
        if intent.intent_type == "volume_analysis":
            terms.extend(self.EXPANSIONS["VPA"])
        if intent.intent_type == "risk_management":
            terms.extend(self.EXPANSIONS["R_MULTIPLE"])
        intent.expanded_terms = self._dedupe(terms)
        return intent

    def _fomc_events(self, text: str) -> List[str]:
        events: List[str] = []
        if "minutes" in text:
            events.append("FOMC_MINUTES")
        if "summary of economic projections" in text or " sep" in f" {text} " or "dot plot" in text:
            events.append("SEP")
        if "statement" in text:
            events.append("FOMC")
        if not events:
            events = ["FOMC", "FOMC_MINUTES", "SEP"]
        return events

    @classmethod
    def normalize(cls, value: Any) -> str:
        text = str(value or "").lower().replace("đ", "d").replace("-", " ")
        normalized = unicodedata.normalize("NFD", text)
        stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        compact = re.sub(r"\s+", " ", stripped).strip()
        return f" {compact} "

    @staticmethod
    def _has_any(text: str, terms: Iterable[str]) -> bool:
        normalized_terms = [QueryIntentRouter.normalize(term).strip() for term in terms]
        return any(term and term in text for term in normalized_terms)

    @staticmethod
    def _period_candidates(text: str) -> List[str]:
        patterns = [
            r"\b20\d{2}[-_/](0[1-9]|1[0-2])[-_/]([0-3]\d)\b",
            r"\b20\d{2}[-_/](0[1-9]|1[0-2])\b",
            r"\b20\d{2}\s*q[1-4]\b",
            r"\bq[1-4]\s*20\d{2}\b",
        ]
        found: List[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                found.append(match.group(0).replace("_", "-").replace("/", "-").strip())
        return QueryIntentRouter._dedupe(found)

    @staticmethod
    def _dedupe(values: Iterable[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for value in values:
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out


class QueryFilterBuilder:
    """Build conservative Qdrant payload filters from QueryIntent."""

    def build(self, intent: QueryIntent, explicit_filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        explicit_filters = {
            key: value
            for key, value in (explicit_filters or {}).items()
            if self._has_value(value)
        }
        filters: Dict[str, Any] = {}

        if intent.primary_domain:
            filters["domain"] = intent.primary_domain
        if intent.primary_subdomain:
            filters["subdomain"] = intent.primary_subdomain

        if intent.source_preference == "official_report_first" and intent.event_type_candidates:
            filters["knowledge_type"] = "report"
        if intent.intent_type == "mixed" and intent.event_type_candidates:
            filters["knowledge_type"] = "report"

        if intent.event_type_candidates and intent.source_preference in {"official_report_first", "mixed_report_and_book"}:
            primary_events = [
                event
                for event in intent.event_type_candidates
                if event not in {"GOLD_MARKET"} or intent.primary_subdomain == "gold"
            ]
            if primary_events:
                filters["event_type"] = primary_events if len(primary_events) > 1 else primary_events[0]

        if intent.period_candidates:
            filters["period"] = intent.period_candidates[0]
        if intent.preferred_organizations and intent.source_preference in {"official_report_first", "mixed_report_and_book"}:
            filters["organization"] = intent.preferred_organizations[0]

        # Explicit caller filters win. This preserves older tests and lets eval
        # cases intentionally pin a domain/subdomain.
        filters.update(explicit_filters)
        return {key: value for key, value in filters.items() if self._has_value(value)}

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set)):
            return bool(value)
        return True
