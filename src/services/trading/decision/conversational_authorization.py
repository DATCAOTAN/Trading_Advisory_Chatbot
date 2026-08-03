from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from src.config import Config
from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.trading.reasoning.strategy_evidence import (
    ConversationalStrategyRequest,
    parse_conversational_strategy,
)


TRADING_MODES = {"advisory_only", "human_confirmed_live", "autonomous_live"}


@dataclass(frozen=True)
class ConversationalTradingRequest:
    request_id: str
    requested_mode: str
    confirmation_policy: str
    canonical_symbol: str
    broker_symbol: str
    timeframe_profile: tuple[str, ...]
    strategy_description: str
    account_scope: str
    mt5_authorization_required: bool
    mandate_required: bool
    allowed_next_action: str
    blockers: tuple[str, ...] = ()
    strategy: ConversationalStrategyRequest | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "intent_type": "TRADING_AUTHORIZATION_REQUEST",
            "requested_mode": self.requested_mode,
            "confirmation_policy": self.confirmation_policy,
            "canonical_symbol": self.canonical_symbol,
            "broker_symbol": self.broker_symbol,
            "timeframe_profile": list(self.timeframe_profile),
            "strategy_description": self.strategy_description,
            "account_scope": self.account_scope,
            "mt5_authorization_required": self.mt5_authorization_required,
            "mandate_required": self.mandate_required,
            "allowed_next_action": self.allowed_next_action,
            "blockers": list(self.blockers),
            "strategy": self.strategy.as_dict() if self.strategy else None,
            "execution_authority": False,
            "executable": False,
            "metadata_redacted": True,
        }

    @classmethod
    def from_public_dict(cls, payload: Mapping[str, Any]) -> "ConversationalTradingRequest":
        mode = str(payload.get("requested_mode") or "")
        symbol = str(payload.get("canonical_symbol") or "")
        broker_symbol = str(payload.get("broker_symbol") or "")
        timeframe_profile = tuple(payload.get("timeframe_profile") or ())
        strategy_payload = payload.get("strategy")
        strategy = (
            ConversationalStrategyRequest.from_dict(strategy_payload)
            if isinstance(strategy_payload, Mapping)
            else None
        )
        expected_profile = (
            strategy.timeframes if strategy and strategy.timeframes else operator_timeframe_profile(symbol)
        )
        if (
            payload.get("intent_type") != "TRADING_AUTHORIZATION_REQUEST"
            or mode not in TRADING_MODES
            or not re.fullmatch(r"conversation_trade_[0-9a-f]{24}", str(payload.get("request_id") or ""))
            or not symbol
            or broker_symbol != broker_symbol_for(symbol)
            or timeframe_profile != expected_profile
            or bool(strategy) and (
                strategy.canonical_symbol != symbol
                or strategy.requested_mode != mode
                or strategy.confirmation_policy != str(payload.get("confirmation_policy") or "")
                or strategy.account_scope != str(payload.get("account_scope") or "UNKNOWN")
            )
            or payload.get("execution_authority") is not False
            or payload.get("executable") is not False
            or payload.get("metadata_redacted") is not True
        ):
            raise ValueError("CONVERSATIONAL_TRADING_REQUEST_INVALID")
        return cls(
            request_id=str(payload.get("request_id") or ""),
            requested_mode=mode,
            confirmation_policy=str(payload.get("confirmation_policy") or ""),
            canonical_symbol=symbol,
            broker_symbol=broker_symbol,
            timeframe_profile=timeframe_profile,
            strategy_description=str(payload.get("strategy_description") or ""),
            account_scope=str(payload.get("account_scope") or "UNKNOWN"),
            mt5_authorization_required=payload.get("mt5_authorization_required") is True,
            mandate_required=payload.get("mandate_required") is True,
            allowed_next_action=str(payload.get("allowed_next_action") or "BLOCKED"),
            blockers=tuple(str(item) for item in payload.get("blockers") or ()),
            strategy=strategy,
        )


def parse_conversational_trading_request(
    query: str,
    *,
    conversation_id: str,
) -> ConversationalTradingRequest | None:
    normalized = _normalized(query)
    if not normalized or not _has_trading_authorization_intent(normalized):
        return None

    mode = _requested_mode(normalized)
    symbol = _configured_symbol(normalized)
    account_scope = "DEMO" if re.search(r"\b(demo|thu nghiem|test account)\b", normalized) else "UNKNOWN"
    confirmation_policy = {
        "advisory_only": "NO_EXECUTION",
        "human_confirmed_live": "CONFIRM_EVERY_TRADE",
        "autonomous_live": "STANDING_MANDATE",
    }[mode]
    blockers = (
        ("DEMO_ACCOUNT_SCOPE_REQUIRED",)
        if mode != "advisory_only" and account_scope != "DEMO"
        else ()
    )
    next_action = {
        "advisory_only": "ANALYZE_ONLY",
        "human_confirmed_live": "GRANT_MT5_DEMO_ACCESS",
        "autonomous_live": "REVIEW_STANDING_MANDATE",
    }[mode]
    request_material = f"{conversation_id.strip()}|{query.strip()}"
    request_id = "conversation_trade_" + hashlib.sha256(request_material.encode("utf-8")).hexdigest()[:24]
    strategy = parse_conversational_strategy(
        query,
        canonical_symbol=symbol,
        requested_mode=mode,
        confirmation_policy=confirmation_policy,
        account_scope=account_scope,
        request_id=request_id,
        default_timeframes=operator_timeframe_profile(symbol),
    )
    strategy_issues = ()
    if strategy is not None:
        from src.services.trading.reasoning.strategy_evidence import validate_strategy

        strategy_issues = validate_strategy(strategy)
    return ConversationalTradingRequest(
        request_id=request_id,
        requested_mode=mode,
        confirmation_policy=confirmation_policy,
        canonical_symbol=symbol,
        broker_symbol=broker_symbol_for(symbol),
        timeframe_profile=(strategy.timeframes if strategy and strategy.timeframes else operator_timeframe_profile(symbol)),
        strategy_description=(strategy.strategy_description if strategy else "CURRENT_CONFIGURED_STRATEGY"),
        account_scope=account_scope,
        mt5_authorization_required=mode != "advisory_only",
        mandate_required=mode == "autonomous_live",
        allowed_next_action="BLOCKED" if blockers or strategy_issues else next_action,
        blockers=tuple(dict.fromkeys((*blockers, *strategy_issues))),
        strategy=strategy,
    )


def _requested_mode(normalized: str) -> str:
    if _contains_any(
        normalized,
        "chi phan tich",
        "analysis only",
        "advisory only",
        "khong giao dich",
        "khong gui lenh",
        "khong truy cap mt5",
        "do not trade",
        "do not submit",
    ):
        return "advisory_only"
    if _contains_any(
        normalized,
        "hoi toi",
        "bao toi",
        "toi duyet",
        "xac nhan",
        "confirm",
        "approve",
        "ask before",
        "before every trade",
        "before each order",
    ):
        return "human_confirmed_live"
    if _contains_any(
        normalized,
        "tu dong giao dich",
        "tu giao dich",
        "khong can hoi",
        "autonomous",
        "automatically trade",
        "standing mandate",
        "mandate",
    ):
        return "autonomous_live"
    return "advisory_only"


def _configured_symbol(normalized: str) -> str:
    symbols = sorted(
        {
            name.removeprefix("MARKET_BROKER_SYMBOL_")
            for name in dir(Config)
            if name.startswith("MARKET_BROKER_SYMBOL_") and getattr(Config, name, "")
        },
        key=len,
        reverse=True,
    )
    compact = normalized.replace("/", "").replace("_", "")
    return next((symbol for symbol in symbols if symbol.lower() in compact), Config.MARKET_DEFAULT_SYMBOL)


def _has_trading_authorization_intent(normalized: str) -> bool:
    return _contains_any(
        normalized,
        "giao dich",
        "vao lenh",
        "gui lenh",
        "trade",
        "order",
        "submit",
        "mt5",
        "mandate",
        "xac nhan",
        "confirm",
    )


def _contains_any(value: str, *markers: str) -> bool:
    return any(marker in value for marker in markers)


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.lower().replace("đ", "d")).strip()
