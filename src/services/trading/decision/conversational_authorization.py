from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
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
    INDICATOR_PARAMETER_SUGGESTIONS,
    parse_conversational_strategy,
    project_resolved_semantic_strategy,
    validate_strategy,
    conversation_trading_scope,
)
from src.services.semantic.query_plan import QueryPlan
from src.services.semantic.resolved_semantics import (
    ResolvedSemanticState,
    SemanticCompletionPatch,
    apply_semantic_completion,
)
from src.services.semantic.structured_semantics import SEMANTIC_SCHEMA_VERSION


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
    trading_scope: str = ""

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
            "trading_scope": self.trading_scope,
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
        trading_scope = str(payload.get("trading_scope") or "")
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
                or strategy.trading_scope != trading_scope
            )
            or bool(trading_scope) and not re.fullmatch(r"trading_scope_[0-9a-f]{24}", trading_scope)
            or payload.get("execution_authority") is not False
            or payload.get("executable") is not False
            or payload.get("metadata_redacted") is not True
            or response_format not in RESPONSE_FORMATS
            or trade_action not in {"", "OPEN_POSITION", "GENERIC_TRADE", "CLOSE_POSITION", "MANAGE_POSITION"}
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
            trading_scope=trading_scope,
        )


@dataclass(frozen=True)
class StrategyCompletionSuggestion:
    field_path: str
    value: str | float
    source: str = "STRATEGY_POLICY"


@dataclass(frozen=True)
class StrategyCompletionState:
    """Non-executable semantic completion state before evidence and Draft."""

    request_id: str
    action: str
    direction: str
    canonical_symbol: str
    broker_symbol: str
    requested_mode: str
    confirmation_policy: str
    strategy: ConversationalStrategyRequest
    unresolved_fields: tuple[str, ...]
    field_sources: tuple[tuple[str, str], ...]
    suggestions: tuple[StrategyCompletionSuggestion, ...]
    operational_timeframe_profile: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    executable: bool = False


def build_strategy_completion_state(
    request: ConversationalTradingRequest,
    semantic_state: ResolvedSemanticState | None,
) -> StrategyCompletionState | None:
    strategy = request.strategy
    if strategy is None or not strategy.semantic_unresolved_fields:
        return None
    if (
        semantic_state is not None
        and (
            semantic_state.canonical_symbols
            and semantic_state.canonical_symbols[0] != request.canonical_symbol
            or sorted(
                (item.indicator_id, item.parameters, item.timeframe)
                for item in semantic_state.indicators
            )
            != sorted(
                (item.indicator_id, item.parameters, item.timeframe)
                for item in strategy.indicators
            )
        )
    ):
        raise ValueError("STRATEGY_COMPLETION_BINDING_INVALID")
    suggestions: list[StrategyCompletionSuggestion] = []
    for field in strategy.semantic_unresolved_fields:
        match = re.fullmatch(
            r"indicators\[(\d+)]\.(timeframe|parameters\.([A-Za-z][A-Za-z0-9_]*))",
            field,
        )
        if match is None or int(match.group(1)) >= len(strategy.indicators):
            continue
        indicator = strategy.indicators[int(match.group(1))]
        if match.group(2) == "timeframe":
            if request.timeframe_profile:
                suggestions.append(
                    StrategyCompletionSuggestion(field, request.timeframe_profile[0])
                )
        else:
            value = INDICATOR_PARAMETER_SUGGESTIONS.get(
                indicator.indicator_id, {}
            ).get(str(match.group(3)))
            if value is not None:
                suggestions.append(StrategyCompletionSuggestion(field, value))
    return StrategyCompletionState(
        request_id=request.request_id,
        action=request.trade_action,
        direction=request.trade_direction,
        canonical_symbol=request.canonical_symbol,
        broker_symbol=request.broker_symbol,
        requested_mode=request.requested_mode,
        confirmation_policy=request.confirmation_policy,
        strategy=strategy,
        unresolved_fields=strategy.semantic_unresolved_fields,
        field_sources=strategy.field_sources,
        suggestions=tuple(suggestions),
        operational_timeframe_profile=request.timeframe_profile,
        blockers=request.blockers,
    )


def apply_strategy_completion(
    request: ConversationalTradingRequest,
    semantic_state: ResolvedSemanticState,
    patch: SemanticCompletionPatch,
) -> tuple[ConversationalTradingRequest, ResolvedSemanticState]:
    """Reproject one typed completion transaction through the existing strategy owner."""

    current = build_strategy_completion_state(request, semantic_state)
    if current is None:
        raise ValueError("STRATEGY_COMPLETION_NOT_REQUIRED")
    if any(update.field_path not in current.unresolved_fields for update in patch.updates):
        raise ValueError("STRATEGY_COMPLETION_FIELD_NOT_UNRESOLVED")
    updated_state = apply_semantic_completion(semantic_state, patch)
    request_material = json.dumps(
        {"source_request_id": request.request_id, "semantic_context": updated_state.as_dict()},
        sort_keys=True,
        separators=(",", ":"),
    )
    request_id = "conversation_trade_" + hashlib.sha256(
        request_material.encode("utf-8")
    ).hexdigest()[:24]
    strategy = project_resolved_semantic_strategy(
        updated_state.as_dict(),
        canonical_symbol=request.canonical_symbol,
        requested_mode=request.requested_mode,
        confirmation_policy=request.confirmation_policy,
        account_scope=request.account_scope,
        request_id=request_id,
        trading_scope=request.trading_scope,
    )
    if strategy is None:
        raise ValueError("STRATEGY_COMPLETION_PROJECTION_INVALID")
    issues = validate_strategy(strategy)
    hard_issues = tuple(issue for issue in issues if issue != "SEMANTIC_FIELDS_UNRESOLVED")
    if hard_issues:
        raise ValueError(",".join(hard_issues))
    retained = tuple(
        blocker
        for blocker in request.blockers
        if not blocker.startswith("SEMANTIC_UNRESOLVED:")
        and blocker not in {
            "SEMANTIC_FIELDS_UNRESOLVED",
            "INDICATOR_PARAMETER_INVALID",
            "UNSUPPORTED_TIMEFRAME",
        }
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *retained,
                *(f"SEMANTIC_UNRESOLVED:{field}" for field in strategy.semantic_unresolved_fields),
                *issues,
            )
        )
    )
    response_format = (
        "STRATEGY_COMPLETION_REQUIRED_CARD"
        if blockers
        else {
            "advisory_only": "CLARIFICATION_OR_BLOCKER_RESPONSE",
            "human_confirmed_live": "MT5_ACCESS_CARD",
            "autonomous_live": "STANDING_MANDATE_CARD",
        }[request.requested_mode]
    )
    next_action = {
        "advisory_only": "ANALYZE_ONLY",
        "human_confirmed_live": "GRANT_MT5_DEMO_ACCESS",
        "autonomous_live": "REVIEW_STANDING_MANDATE",
    }[request.requested_mode]
    return (
        replace(
            request,
            request_id=request_id,
            timeframe_profile=(
                strategy.timeframes
                if not strategy.semantic_unresolved_fields
                else request.timeframe_profile
            ),
            strategy_description=strategy.strategy_description,
            allowed_next_action="BLOCKED" if blockers else next_action,
            response_format=response_format,
            blockers=blockers,
            strategy=strategy,
        ),
        updated_state,
    )


def parse_conversational_trading_request(
    query: str,
    *,
    conversation_id: str,
    context: ConversationalIntentContext | None = None,
    query_plan: QueryPlan | None = None,
) -> ConversationalTradingRequest | None:
    if query_plan is not None:
        return project_conversational_trading_request(
            query_plan,
            conversation_id=conversation_id,
        )
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
    trading_scope = conversation_trading_scope(conversation_id)
    has_local_timeframe = bool(
        re.search(r"\b(?:M1|M5|M15|H1|H4|D1)\b", str(query or ""), re.IGNORECASE)
    )
    strategy_default_timeframes = (
        operator_timeframe_profile(symbol)
        if has_local_timeframe
        else context.timeframes or operator_timeframe_profile(symbol)
    )
    strategy = parse_conversational_strategy(
        query,
        canonical_symbol=symbol,
        requested_mode=mode,
        confirmation_policy=confirmation_policy,
        account_scope=account_scope,
        request_id=request_id,
        default_timeframes=strategy_default_timeframes,
        trading_scope=trading_scope,
    )
    strategy_issues = ()
    if strategy is not None:
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
        trading_scope=trading_scope,
    )


def project_conversational_trading_request(
    query_plan: QueryPlan,
    *,
    conversation_id: str,
) -> ConversationalTradingRequest | None:
    """Consume an authoritative structured QueryPlan without reparsing its raw query."""

    semantic_context = query_plan.semantic_context
    semantic = semantic_context.get("input") if isinstance(semantic_context, Mapping) else None
    if not isinstance(semantic, Mapping) or semantic.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
        return None
    primary_intent = str(semantic.get("primary_intent") or "")
    action = str(semantic.get("action") or "")
    if primary_intent not in {"STRATEGY", "TRADE_LIFECYCLE", "POSITION_MANAGEMENT"} and action not in {
        "OPEN_POSITION",
        "CLOSE_POSITION",
        "MANAGE_POSITION",
    }:
        return None

    requested_mode = str(query_plan.constraints.get("requested_mode") or "")
    if requested_mode not in TRADING_MODES:
        return None
    account_scope = str(semantic.get("account_scope") or "") or "UNKNOWN"
    confirmation_policy = {
        "advisory_only": "NO_EXECUTION",
        "human_confirmed_live": "CONFIRM_EVERY_TRADE",
        "autonomous_live": "STANDING_MANDATE",
    }.get(requested_mode)
    if confirmation_policy is None:
        return None
    canonical_symbol = next(iter(query_plan.entities.symbols), "")
    broker_symbol = next(iter(query_plan.entities.broker_symbols), "")
    request_material = json.dumps(
        {"conversation_id": conversation_id.strip(), "semantic_context": semantic_context},
        sort_keys=True,
        separators=(",", ":"),
    )
    request_id = "conversation_trade_" + hashlib.sha256(request_material.encode("utf-8")).hexdigest()[:24]
    trading_scope = conversation_trading_scope(conversation_id)
    strategy = project_resolved_semantic_strategy(
        semantic_context,
        canonical_symbol=canonical_symbol,
        requested_mode=requested_mode,
        confirmation_policy=confirmation_policy,
        account_scope=account_scope,
        request_id=request_id,
        trading_scope=trading_scope,
    )
    # The strict strategy projection is the authority for indicator-child completion.
    # Retain every other semantic unresolved field, and only clear children it has
    # independently validated against the existing indicator registry.
    strategy_unresolved = set(strategy.semantic_unresolved_fields) if strategy is not None else None
    semantic_unresolved = tuple(
        f"SEMANTIC_UNRESOLVED:{value}"
        for value in semantic_context.get("unresolved_fields", ())
        if str(value).strip()
        and (strategy_unresolved is None or value in strategy_unresolved)
    )
    blockers: list[str] = list(semantic_unresolved)
    if not canonical_symbol:
        blockers.append("SYMBOL_REQUIRED")
    if requested_mode != "advisory_only" and account_scope != "DEMO":
        blockers.append("DEMO_ACCOUNT_SCOPE_REQUIRED")
    if action == "OPEN_POSITION" and not str(semantic.get("direction") or ""):
        blockers.append("SEMANTIC_UNRESOLVED:direction")
    if semantic.get("negated") is True:
        blockers.append("NEGATED_TRADE_ACTION")
    if semantic.get("hypothetical") is True:
        blockers.append("HYPOTHETICAL_TRADE_ACTION")
    if strategy is not None:
        strategy_issues = validate_strategy(strategy)
        blockers.extend(
            f"SEMANTIC_UNRESOLVED:{field}"
            for field in strategy.semantic_unresolved_fields
        )
        blockers.extend(strategy_issues)
        if any(issue != "SEMANTIC_FIELDS_UNRESOLVED" for issue in strategy_issues):
            # Never publish a strategy that the strict public reload will reject.
            strategy = None

    blockers = list(dict.fromkeys(blockers))
    response_format = (
        "STRATEGY_COMPLETION_REQUIRED_CARD"
        if blockers
        else {
            "advisory_only": "CLARIFICATION_OR_BLOCKER_RESPONSE",
            "human_confirmed_live": "MT5_ACCESS_CARD",
            "autonomous_live": "STANDING_MANDATE_CARD",
        }[requested_mode]
    )
    next_action = {
        "advisory_only": "ANALYZE_ONLY",
        "human_confirmed_live": "GRANT_MT5_DEMO_ACCESS",
        "autonomous_live": "REVIEW_STANDING_MANDATE",
    }[requested_mode]
    is_non_actionable = semantic.get("negated") is True or semantic.get("hypothetical") is True
    trade_action = "" if is_non_actionable else action
    if trade_action not in {"OPEN_POSITION", "CLOSE_POSITION", "MANAGE_POSITION"}:
        trade_action = "GENERIC_TRADE" if primary_intent == "STRATEGY" and not is_non_actionable else ""
    trade_direction = "" if is_non_actionable else str(semantic.get("direction") or "")
    timeframe_profile = (
        strategy.timeframes
        if strategy and strategy.timeframes and all(strategy.timeframes)
        else operator_timeframe_profile(canonical_symbol)
    )
    return ConversationalTradingRequest(
        request_id=request_id,
        requested_mode=requested_mode,
        confirmation_policy=confirmation_policy,
        canonical_symbol=canonical_symbol,
        broker_symbol=broker_symbol,
        timeframe_profile=timeframe_profile,
        strategy_description=(strategy.strategy_description if strategy else "STRUCTURED_SEMANTIC_PROJECTION"),
        account_scope=account_scope,
        mt5_authorization_required=requested_mode != "advisory_only",
        mandate_required=requested_mode == "autonomous_live",
        allowed_next_action="BLOCKED" if blockers else next_action,
        response_format=response_format,
        trade_action=trade_action,
        trade_direction=trade_direction,
        trade_instruction_text=str(query_plan.original_query or "")[:500],
        blockers=tuple(blockers),
        strategy=strategy,
        trading_scope=trading_scope,
    )
