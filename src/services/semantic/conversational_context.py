from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from src.services.trading.market.timeframes import (
    broker_symbol_for,
    resolve_symbol,
    resolve_symbols_from_text,
)
from src.services.trading.reasoning.strategy_evidence import (
    IndicatorSpec,
    parse_indicator_specs,
)


RESPONSE_FORMATS = {
    "MARKET_EVIDENCE_RESPONSE",
    "CONCEPT_EXPLANATION_RESPONSE",
    "STRATEGY_SPECIFICATION_CARD",
    "STRATEGY_COMPLETION_REQUIRED_CARD",
    "MT5_ACCESS_CARD",
    "STANDING_MANDATE_CARD",
    "CANDIDATE_REVIEW_CARD",
    "CLARIFICATION_OR_BLOCKER_RESPONSE",
}


@dataclass(frozen=True)
class TradeInstructionSemantics:
    action: str = ""
    direction: str = ""
    instruction: bool = False
    negated: bool = False
    hypothetical: bool = False
    concept_question: bool = False


def normalize_trade_instruction(text: str) -> TradeInstructionSemantics:
    """Classify bounded trade language without granting execution authority."""
    value = _normalized(text)
    concept = _contains(
        value, " la gi", " what is", " nghia la gi", " explain buy", " explain sell"
    )
    hypothetical = _contains(
        value, " neu ", " if ", " gia su", " co nen", " should i", " would ", " risk gi"
    )
    negated = bool(
        re.search(
            r"\b(?:khong|dung|do not|don't|never|chi phan tich|analysis only)\b"
            r".{0,28}\b(?:buy|sell|mua|ban|long|short|trade|giao dich|vao lenh)\b",
            value,
        )
    )
    close = bool(
        re.search(r"\b(?:close|exit|dong lenh|thoat lenh|chot vi the)\b", value)
    )
    buy = bool(
        re.search(
            r"\b(?:buy|mua|long|mo lenh mua|vao lenh mua|mo vi the long|enter long|open a buy)\b",
            value,
        )
    )
    sell = bool(
        re.search(
            r"\b(?:sell|ban|short|mo lenh ban|vao lenh ban|mo vi the short|enter short|open a sell)\b",
            value,
        )
    )
    generic = bool(
        re.search(r"\b(?:trade|giao dich|vao lenh|tao lenh|tim co hoi giao dich)\b", value)
    )
    imperative = bool(
        re.search(r"\b(?:hay|please|mo|vao|enter|open|tao|thuc hien)\b", value)
    ) or bool(re.search(r"\b(?:buy|sell|long|short)\b\s+(?:when|khi)\b", value))
    question = "?" in str(text or "") or concept or hypothetical
    direct_command = value in {"buy", "sell", "mua", "ban", "long", "short", "trade", "giao dich"}
    instruction = not negated and not question and (imperative or generic or close or direct_command)
    direction = "BUY" if instruction and buy and not sell else "SELL" if instruction and sell and not buy else ""
    action = (
        "CLOSE_POSITION"
        if instruction and close
        else "OPEN_POSITION"
        if instruction and direction
        else "GENERIC_TRADE"
        if instruction and generic
        else ""
    )
    return TradeInstructionSemantics(
        action=action,
        direction=direction,
        instruction=instruction,
        negated=negated,
        hypothetical=hypothetical,
        concept_question=concept,
    )


@dataclass(frozen=True)
class ConversationalIntentContext:
    intent_families: tuple[str, ...] = ()
    canonical_symbol: str = ""
    broker_symbol: str = ""
    timeframes: tuple[str, ...] = ()
    indicators: tuple[IndicatorSpec, ...] = ()
    requested_mode: str = ""
    confirmation_policy: str = ""
    account_scope: str = "UNKNOWN"
    response_format: str = "CLARIFICATION_OR_BLOCKER_RESPONSE"
    blockers: tuple[str, ...] = ()
    explicit_fields: tuple[str, ...] = ()

    @property
    def is_strategy_request(self) -> bool:
        return "strategy" in self.intent_families

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "conversational-intent-context/v1",
            "intent_families": list(self.intent_families),
            "canonical_symbol": self.canonical_symbol,
            "broker_symbol": self.broker_symbol,
            "timeframes": list(self.timeframes),
            "indicators": [item.as_dict() for item in self.indicators],
            "requested_mode": self.requested_mode,
            "confirmation_policy": self.confirmation_policy,
            "account_scope": self.account_scope,
            "response_format": self.response_format,
            "blockers": list(self.blockers),
            "explicit_fields": list(self.explicit_fields),
            "execution_authority": False,
            "executable": False,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationalIntentContext":
        if (
            payload.get("schema") != "conversational-intent-context/v1"
            or payload.get("execution_authority") is not False
            or payload.get("executable") is not False
        ):
            raise ValueError("CONVERSATIONAL_INTENT_CONTEXT_INVALID")
        indicators = tuple(
            IndicatorSpec(
                indicator_id=str(item["indicator_id"]),
                timeframe=str(item["timeframe"]),
                parameters=tuple(
                    sorted(
                        (str(key), float(value))
                        for key, value in dict(item["parameters"]).items()
                    )
                ),
                output_alias=str(item["output_alias"]),
            )
            for item in payload.get("indicators", ())
        )
        response_format = str(payload.get("response_format") or "")
        if response_format not in RESPONSE_FORMATS:
            raise ValueError("CONVERSATIONAL_RESPONSE_FORMAT_INVALID")
        symbol = str(payload.get("canonical_symbol") or "")
        broker_symbol = str(payload.get("broker_symbol") or "")
        if symbol:
            resolution = resolve_symbol(symbol)
            if resolution.status != "RESOLVED" or broker_symbol != resolution.broker_symbol:
                raise ValueError("CONVERSATIONAL_SYMBOL_BINDING_INVALID")
        elif broker_symbol:
            raise ValueError("CONVERSATIONAL_SYMBOL_BINDING_INVALID")
        mode = str(payload.get("requested_mode") or "")
        policy = str(payload.get("confirmation_policy") or "")
        expected_policy = {
            "": "",
            "advisory_only": "NO_EXECUTION",
            "human_confirmed_live": "CONFIRM_EVERY_TRADE",
            "autonomous_live": "STANDING_MANDATE",
        }.get(mode)
        if expected_policy is None or policy != expected_policy:
            raise ValueError("CONVERSATIONAL_MODE_BINDING_INVALID")
        return cls(
            intent_families=tuple(str(item) for item in payload.get("intent_families", ())),
            canonical_symbol=symbol,
            broker_symbol=broker_symbol,
            timeframes=tuple(str(item) for item in payload.get("timeframes", ())),
            indicators=indicators,
            requested_mode=mode,
            confirmation_policy=policy,
            account_scope=str(payload.get("account_scope") or "UNKNOWN"),
            response_format=response_format,
            blockers=tuple(str(item) for item in payload.get("blockers", ())),
            explicit_fields=tuple(str(item) for item in payload.get("explicit_fields", ())),
        )


def resolve_conversational_context(
    query: str,
    previous: ConversationalIntentContext | None = None,
) -> ConversationalIntentContext:
    normalized = _normalized(query)
    trade_semantics = normalize_trade_instruction(query)
    families = _intent_families(normalized, trade_semantics)
    explicit: list[str] = []
    blockers: list[str] = []

    resolutions = resolve_symbols_from_text(query)
    unresolved = [item.raw_symbol for item in resolutions if item.status != "RESOLVED"]
    resolved = next((item for item in resolutions if item.status == "RESOLVED"), None)
    if unresolved and resolved is None:
        symbol = ""
        broker_symbol = ""
        explicit.append("canonical_symbol")
        blockers.append("SYMBOL_UNRESOLVED")
    elif resolved is not None:
        symbol = resolved.canonical_symbol
        broker_symbol = resolved.broker_symbol
        explicit.append("canonical_symbol")
    else:
        symbol = previous.canonical_symbol if previous else ""
        broker_symbol = previous.broker_symbol if previous else ""

    timeframe_tokens = tuple(dict.fromkeys(re.findall(r"\b([MHD]\d+)\b", normalized.upper())))
    unsupported_timeframes = tuple(
        item for item in timeframe_tokens if item not in {"M1", "M5", "M15", "H1", "H4", "D1"}
    )
    explicit_timeframes = tuple(item for item in timeframe_tokens if item not in unsupported_timeframes)
    if unsupported_timeframes:
        timeframes = unsupported_timeframes
        explicit.append("timeframes")
        blockers.append("TIMEFRAME_UNSUPPORTED")
    elif explicit_timeframes:
        timeframes = explicit_timeframes
        explicit.append("timeframes")
    else:
        timeframes = previous.timeframes if previous else ()

    default_timeframes = timeframes or ("H1",)
    indicators = parse_indicator_specs(query, default_timeframes)
    if indicators:
        explicit.append("indicators")
    elif previous and _references_previous_indicator(normalized):
        indicators = previous.indicators

    requested_mode, confirmation_policy = _mode_policy(normalized, families, previous)
    if requested_mode:
        explicit.append("requested_mode")
    account_scope = (
        "DEMO"
        if _contains(normalized, "demo", "thu nghiem", "test account")
        else previous.account_scope if previous else "UNKNOWN"
    )
    if requested_mode and requested_mode != "advisory_only" and account_scope != "DEMO":
        blockers.append("DEMO_ACCOUNT_SCOPE_REQUIRED")
    if "authorization" in families and "advisory" not in families and not symbol:
        blockers.append("SYMBOL_REQUIRED")

    if "strategy" in families:
        if not symbol:
            blockers.append("SYMBOL_REQUIRED")
        if not timeframes:
            blockers.append("TIMEFRAME_REQUIRED")
        if not indicators:
            blockers.append("STRATEGY_INDICATORS_MISSING")
        has_direction = bool(trade_semantics.direction)
        if not _has_rule(normalized) or not has_direction:
            blockers.append("ENTRY_ACTION_MISSING")
        if not has_direction:
            blockers.append("STRATEGY_DIRECTION_MISSING")
        if not _contains(normalized, " risk ", " rui ro ", "%"):
            blockers.append("RISK_POLICY_MISSING")
        if not _contains(normalized, " stop loss", " stop-loss", " sl ", " atr "):
            blockers.append("STOP_POLICY_MISSING")
        if not _contains(normalized, " take profit", " tp ", " exit ", " chot loi", " thoat lenh"):
            blockers.append("EXIT_RULE_MISSING")
        if not _contains(normalized, " lot", " volume", " position size", " khoi luong", "%"):
            blockers.append("POSITION_SIZING_POLICY_MISSING")
        if not confirmation_policy:
            blockers.append("CONFIRMATION_POLICY_REQUIRED")

    response_format = _response_format(families, requested_mode, blockers)
    return ConversationalIntentContext(
        intent_families=families,
        canonical_symbol=symbol,
        broker_symbol=broker_symbol or (broker_symbol_for(symbol) if symbol else ""),
        timeframes=timeframes,
        indicators=tuple(indicators),
        requested_mode=requested_mode,
        confirmation_policy=confirmation_policy,
        account_scope=account_scope,
        response_format=response_format,
        blockers=tuple(dict.fromkeys(blockers)),
        explicit_fields=tuple(dict.fromkeys(explicit)),
    )


def strategy_response_message(context: ConversationalIntentContext) -> str:
    indicators = ", ".join(
        f"{item.indicator_id}({','.join(f'{key}={value:g}' for key, value in item.parameters)})@{item.timeframe}"
        for item in context.indicators
    ) or "none"
    heading = (
        "Strategy specification requires more information."
        if context.blockers
        else "Strategy specification normalized."
    )
    return (
        heading + "\n\n"
        f"- Symbol: {context.canonical_symbol or 'missing'}"
        + (f" / {context.broker_symbol}" if context.broker_symbol else "")
        + f"\n- Timeframe: {','.join(context.timeframes) or 'missing'}"
        + f"\n- Indicators: {indicators}"
        + f"\n- Mode: {context.requested_mode or 'missing'}"
        + f"\n- Confirmation: {context.confirmation_policy or 'missing'}"
        + "\n- Execution: NON_EXECUTABLE"
        + (f"\n- Required next information: {', '.join(context.blockers)}" if context.blockers else "")
    )


def _intent_families(
    normalized: str,
    trade_semantics: TradeInstructionSemantics | None = None,
) -> tuple[str, ...]:
    trade_semantics = trade_semantics or normalize_trade_instruction(normalized)
    indicator = _contains(normalized, " ema", " rsi", " atr", " macd", " sma", " bollinger", " bbands")
    current = indicator and _contains(
        normalized,
        " hien tai",
        " moi nhat",
        " bay gio",
        " current",
        " latest",
        " now",
        " luc nay",
        " symbol nay",
        " this symbol",
    )
    concept = _contains(
        normalized,
        " la gi",
        " tinh nhu the nao",
        " duoc tinh",
        " dung de lam gi",
        " sach giai thich",
        " what is",
        " how is",
        " explain",
    )
    trade_language = trade_semantics.instruction or _contains(
        normalized,
        " giao dich",
        " trade",
        " vao lenh",
        " entry",
        " strategy",
        " chien luoc",
        " stop loss",
        " take profit",
    )
    strategy = indicator and trade_language and not trade_semantics.negated
    advisory = _contains(
        normalized,
        " chi phan tich",
        " analysis only",
        " khong giao dich",
        " khong gui lenh",
        " do not trade",
        " do not submit",
    )
    autonomous = _contains(normalized, " tu dong giao dich", " tu giao dich", " autonomous", " mandate", " khong can hoi")
    authorization = trade_language or advisory or autonomous or _contains(normalized, " xac nhan", " confirm", " approve", " mt5")
    values = []
    if current:
        values.append("current_market")
    if concept:
        values.append("concept")
    if strategy:
        values.append("strategy")
    if authorization:
        values.append("authorization")
    if advisory:
        values.append("advisory")
    if autonomous:
        values.append("autonomous")
    return tuple(values)


def _mode_policy(
    normalized: str,
    families: tuple[str, ...],
    previous: ConversationalIntentContext | None,
) -> tuple[str, str]:
    if "advisory" in families:
        return "advisory_only", "NO_EXECUTION"
    human = _contains(normalized, " hoi toi", " bao toi", " toi duyet", " xac nhan", " confirm", " approve", " ask before")
    if human:
        return "human_confirmed_live", "CONFIRM_EVERY_TRADE"
    if "autonomous" in families:
        return "autonomous_live", "STANDING_MANDATE"
    if "strategy" in families:
        return "human_confirmed_live", "CONFIRM_EVERY_TRADE"
    if "authorization" in families:
        return "human_confirmed_live", "CONFIRM_EVERY_TRADE"
    if previous:
        return previous.requested_mode, previous.confirmation_policy
    return "", ""


def _response_format(
    families: tuple[str, ...],
    mode: str,
    blockers: list[str],
) -> str:
    if "strategy" in families:
        if blockers:
            return "STRATEGY_COMPLETION_REQUIRED_CARD"
        if mode == "human_confirmed_live":
            return "MT5_ACCESS_CARD"
        if mode == "autonomous_live":
            return "STANDING_MANDATE_CARD"
        return "STRATEGY_SPECIFICATION_CARD"
    if "current_market" in families:
        return "MARKET_EVIDENCE_RESPONSE"
    if "concept" in families:
        return "CONCEPT_EXPLANATION_RESPONSE"
    if mode == "human_confirmed_live":
        return "MT5_ACCESS_CARD"
    if mode == "autonomous_live":
        return "STANDING_MANDATE_CARD"
    return "CLARIFICATION_OR_BLOCKER_RESPONSE"


def _has_rule(normalized: str) -> bool:
    return bool(
        re.search(r"(?:>|<|\b(?:above|below|greater than|less than|tren|duoi|lon hon|nho hon|cat len|cat xuong)\b)", normalized)
    )


def _references_previous_indicator(normalized: str) -> bool:
    return _contains(normalized, " chi bao nay", " indicator nay", " no ", " cai do")


def _contains(value: str, *markers: str) -> bool:
    padded = f" {value} "
    return any(marker in padded for marker in markers)


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.lower().replace("đ", "d").split())
