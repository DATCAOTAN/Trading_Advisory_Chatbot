from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.services.trading.decision.operator_candidate_generation import (
    operator_timeframe_profile,
)
from src.services.trading.market.timeframes import broker_symbol_for
from src.services.semantic.conversational_context import (
    ConversationalIntentContext,
    RESPONSE_FORMATS,
    normalize_trade_instruction,
    resolve_conversational_context,
)
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
    response_format: str
    trade_action: str = ""
    trade_direction: str = ""
    trade_instruction_text: str = ""
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
            "response_format": self.response_format,
            "trade_action": self.trade_action,
            "trade_direction": self.trade_direction,
            "trade_instruction_text": self.trade_instruction_text,
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
        response_format = str(payload.get("response_format") or "CLARIFICATION_OR_BLOCKER_RESPONSE")
        trade_action = str(payload.get("trade_action") or "")
        trade_direction = str(payload.get("trade_direction") or "")
        blockers = tuple(str(item) for item in payload.get("blockers") or ())
        missing_symbol_allowed = (
            response_format == "STRATEGY_COMPLETION_REQUIRED_CARD"
            and bool({"SYMBOL_REQUIRED", "SYMBOL_UNRESOLVED"} & set(blockers))
        )
        if (
            payload.get("intent_type") != "TRADING_AUTHORIZATION_REQUEST"
            or mode not in TRADING_MODES
            or not re.fullmatch(r"conversation_trade_[0-9a-f]{24}", str(payload.get("request_id") or ""))
            or (not symbol and not missing_symbol_allowed)
            or broker_symbol != (broker_symbol_for(symbol) if symbol else "")
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
            or response_format not in RESPONSE_FORMATS
            or trade_action not in {"", "OPEN_POSITION", "GENERIC_TRADE", "CLOSE_POSITION"}
            or trade_direction not in {"", "BUY", "SELL"}
            or trade_action == "OPEN_POSITION" and not trade_direction
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
            response_format=response_format,
            trade_action=trade_action,
            trade_direction=trade_direction,
            trade_instruction_text=str(payload.get("trade_instruction_text") or "")[:500],
            blockers=blockers,
            strategy=strategy,
        )


def parse_conversational_trading_request(
    query: str,
    *,
    conversation_id: str,
    context: ConversationalIntentContext | None = None,
) -> ConversationalTradingRequest | None:
    context = context or resolve_conversational_context(query)
    if not str(query or "").strip() or not ({"strategy", "authorization", "advisory", "autonomous"} & set(context.intent_families)):
        return None

    mode = context.requested_mode
    symbol = context.canonical_symbol
    account_scope = context.account_scope
    confirmation_policy = context.confirmation_policy
    semantics = normalize_trade_instruction(query)
    proposable = {
        "STOP_POLICY_MISSING",
        "EXIT_RULE_MISSING",
        "RISK_POLICY_MISSING",
        "POSITION_SIZING_POLICY_MISSING",
    }
    blockers = tuple(item for item in context.blockers if item not in proposable)
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
        default_timeframes=context.timeframes or operator_timeframe_profile(symbol),
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
        broker_symbol=context.broker_symbol or (broker_symbol_for(symbol) if symbol else ""),
        timeframe_profile=(strategy.timeframes if strategy and strategy.timeframes else context.timeframes or operator_timeframe_profile(symbol)),
        strategy_description=(strategy.strategy_description if strategy else "CURRENT_CONFIGURED_STRATEGY"),
        account_scope=account_scope,
        mt5_authorization_required=mode != "advisory_only",
        mandate_required=mode == "autonomous_live",
        allowed_next_action="BLOCKED" if blockers or strategy_issues else next_action,
        response_format=context.response_format,
        trade_action=semantics.action,
        trade_direction=semantics.direction,
        trade_instruction_text=str(query or "").strip()[:500],
        blockers=tuple(dict.fromkeys((*blockers, *strategy_issues))),
        strategy=strategy,
    )
