from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.config import Config
from src.services.trading.decision.autonomous_orchestrator import (
    AutonomousOrderIntentProposal,
    AutonomousOrderMarketSnapshot,
    _ORDER_TYPE_SEMANTICS,
    autonomous_market_snapshot_provenance_hash,
)
from src.services.trading.decision.models import TradeReadinessDecision
from src.services.trading.knowledge.models import RuntimeContextPack
from src.services.trading.market.live_feature_service import LiveFeatureResult
from src.services.trading.reasoning.llm_adapter import ProjectLLMReasoningProvider, ReasoningProvider
from src.services.trading.reasoning.models import MethodSelectionResult
from src.services.trading.scoring.models import SignalScoreReport



_FIELDS = {
    "status", "order_type", "entry_price", "trigger_price", "limit_price",
    "stop_loss", "take_profit", "proposed_volume", "reason_codes", "blockers",
}
_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,63}$")


@dataclass(frozen=True)
class AutonomousOrderProposalRequest:
    feature_result: LiveFeatureResult
    runtime_context: RuntimeContextPack
    method_selection: MethodSelectionResult
    score_report: SignalScoreReport
    risk_decision: TradeReadinessDecision
    evaluated_at: datetime
    maximum_age_seconds: int


@dataclass(frozen=True)
class AutonomousOrderProposalResult:
    proposal_reference: str = ""
    created_at: str = ""
    direction: str = ""
    semantic_parameter_references: tuple[str, ...] = ()
    order_proposal: AutonomousOrderIntentProposal | None = field(default=None, repr=False)
    order_market_snapshot: AutonomousOrderMarketSnapshot | None = field(default=None, repr=False)
    source_bindings: tuple[str, ...] = ()
    provenance_hash: str = ""
    blockers: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return bool(
            not self.blockers and self.proposal_reference and self.direction
            and self.semantic_parameter_references and self.order_proposal
            and self.order_market_snapshot and self.provenance_hash
            and valid_autonomous_order_proposal_bindings(self.source_bindings)
        )


class AutonomousOrderProposalProvider:
    """Own one typed advisory proposal; never owns execution permission."""

    def __init__(self, model_provider: ReasoningProvider | None = None) -> None:
        self.model_provider = model_provider

    def produce(self, request: AutonomousOrderProposalRequest) -> AutonomousOrderProposalResult:
        blockers = _input_blockers(request)
        if blockers:
            return _blocked(request, blockers)
        if self.model_provider is None and not Config.TRADING_REASONING_LLM_ENABLED:
            return _blocked(request, ["STRUCTURED_PROPOSAL_MODEL_DISABLED"])
        snapshot = _market_snapshot(request)
        try:
            raw = (
                self.model_provider
                or ProjectLLMReasoningProvider(structured_json=True)
            ).complete(
                _prompt(request), Config.TRADING_REASONING_MAX_TOKENS,
                Config.TRADING_REASONING_TEMPERATURE,
            )
        except Exception:
            return _blocked(request, ["STRUCTURED_PROPOSAL_MODEL_UNAVAILABLE"])
        payload, blockers = _parse(raw)
        if blockers:
            return _blocked(request, blockers)
        proposal, blockers = _make_proposal(payload, request, snapshot)
        if blockers:
            return _blocked(request, blockers)

        created_at, bindings = _utc(request.evaluated_at).isoformat(), _bindings(request)
        material = {
            "created_at": created_at,
            "source_bindings": bindings,
            "snapshot_hash": autonomous_market_snapshot_provenance_hash(snapshot),
            "proposal": _proposal_material(proposal),
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        reference = f"autonomous_order_proposal_{digest[:24]}"
        return AutonomousOrderProposalResult(
            proposal_reference=reference,
            created_at=created_at,
            direction=proposal.side,
            semantic_parameter_references=(
                reference, request.risk_decision.decision_id,
                request.method_selection.result_id, request.runtime_context.context_pack_id,
            ),
            order_proposal=proposal,
            order_market_snapshot=snapshot,
            source_bindings=bindings,
            provenance_hash=digest,
        )


def _input_blockers(request):
    feature = getattr(request.feature_result, "feature_snapshot", None)
    bundle = getattr(request.feature_result, "bundle", None)
    tick = getattr(bundle, "tick", None)
    if feature is None:
        return ["PROPOSAL_FEATURE_SNAPSHOT_MISSING"]
    if bundle is None or tick is None:
        return ["PROPOSAL_MARKET_SNAPSHOT_MISSING"]
    if any(item is None for item in (
        request.runtime_context, request.method_selection,
        request.score_report, request.risk_decision,
    )):
        return ["PROPOSAL_ANALYSIS_INPUT_MISSING"]
    blockers = []
    symbols = {str(value or "").upper() for value in (
        feature.symbol, bundle.symbol, request.runtime_context.symbol,
        request.method_selection.symbol, request.score_report.symbol, request.risk_decision.symbol,
    )}
    brokers = {str(value or "") for value in (
        feature.broker_symbol, bundle.broker_symbol, request.runtime_context.broker_symbol,
        request.score_report.broker_symbol, request.risk_decision.broker_symbol,
    )}
    if "" in symbols or len(symbols) != 1 or "" in brokers or len(brokers) != 1:
        blockers.append("PROPOSAL_SYMBOL_METADATA_CONFLICT")
    if not all(_fresh(value, request.evaluated_at, request.maximum_age_seconds) for value in (
        feature.created_at, bundle.created_at, tick.timestamp, request.runtime_context.created_at,
        request.method_selection.created_at, request.score_report.created_at,
        request.risk_decision.created_at,
    )):
        blockers.append("PROPOSAL_INPUT_STALE")
    if (
        request.method_selection.source_context_pack_id != request.runtime_context.context_pack_id
        or request.score_report.source_context_pack_id != request.runtime_context.context_pack_id
        or request.score_report.source_method_selection_id != request.method_selection.result_id
        or request.risk_decision.source_context_pack_id != request.runtime_context.context_pack_id
        or request.risk_decision.source_method_selection_id != request.method_selection.result_id
        or request.risk_decision.source_score_report_id != request.score_report.score_report_id
    ):
        blockers.append("PROPOSAL_INPUT_REFERENCE_CONFLICT")
    reference_groups = (
        feature.source_snapshot_ids,
        request.runtime_context.source_refs,
        request.method_selection.source_refs,
        request.score_report.source_refs,
    )
    if (
        not valid_autonomous_order_proposal_bindings(_bindings(request))
        or any(
            not group or not all(_valid_source_identifier(item) for item in group)
            for group in reference_groups
        )
    ):
        blockers.append("PROPOSAL_PROVENANCE_MISSING")
    bid, ask = _number(getattr(tick, "bid", None)), _number(getattr(tick, "ask", None))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        blockers.append("PROPOSAL_MARKET_BID_ASK_INVALID")
    return blockers


def _prompt(request):
    feature, tick = request.feature_result.feature_snapshot, request.feature_result.bundle.tick
    primary = feature.indicator_snapshots.get(feature.primary_timeframe)
    payload = {
        "role": "non_executable_autonomous_order_proposal",
        "instructions": [
            "Return strict JSON matching required_json_schema.",
            "This advisory output grants no execution authority.",
            "Return NO_PROPOSAL when typed evidence is insufficient.",
            "No prose, chain-of-thought, account data, credentials, or extra fields.",
        ],
        "symbol": feature.symbol,
        "broker_symbol": feature.broker_symbol,
        "market": {
            "observed_at": tick.timestamp, "bid": tick.bid, "ask": tick.ask,
            "trend_direction": feature.trend_direction,
            "trend_strength": feature.trend_strength,
            "volatility_state": feature.volatility_state,
            "momentum_state": feature.momentum_state,
            "pullback_detected": feature.pullback_detected,
            "breakout_candidate": feature.breakout_candidate,
            "primary_indicator": ({
                "latest_close": primary.latest_close, "atr": primary.atr,
                "swing_high": primary.swing_high, "swing_low": primary.swing_low,
                "support_zones": list(primary.support_zones),
                "resistance_zones": list(primary.resistance_zones),
            } if primary else None),
        },
        "analysis": {
            "regime": request.runtime_context.market_regime_summary,
            "calendar": request.runtime_context.calendar_context_summary,
            "method_id": request.method_selection.primary_method_id,
            "method_summary": request.method_selection.reasoning_summary,
            "score": request.score_report.final_context_score,
            "grade": request.score_report.grade,
            "readiness_action": request.risk_decision.action,
            "readiness_score": request.risk_decision.readiness_score,
            "risk_reasons": list(request.risk_decision.reasons),
            "risk_blockers": [item.code for item in request.risk_decision.blockers],
        },
        "required_json_schema": {
            "status": "PROPOSE|NO_PROPOSAL",
            "order_type": "BUY|SELL|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|BUY_STOP_LIMIT|SELL_STOP_LIMIT|null",
            "entry_price": "positive number|string|null",
            "trigger_price": "positive number|string|null",
            "limit_price": "positive number|string|null",
            "stop_loss": "positive number|string|null",
            "take_profit": "positive number|string|null",
            "proposed_volume": "positive number|string|null",
            "reason_codes": ["UPPERCASE_CODE"], "blockers": ["UPPERCASE_CODE"],
        },
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _parse(raw):
    if not isinstance(raw, str):
        return {}, ["STRUCTURED_PROPOSAL_OUTPUT_NOT_TEXT"]
    try:
        text = raw.strip()
        lines = text.splitlines()
        if (
            len(lines) >= 3
            and lines[0].strip().lower() == "```json"
            and lines[-1].strip() == "```"
        ):
            text = "\n".join(lines[1:-1]).strip()
        payload = json.loads(text, parse_constant=_reject_json_constant)
        if isinstance(payload, str):
            payload = json.loads(payload, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError):
        return {}, ["STRUCTURED_PROPOSAL_OUTPUT_INVALID_JSON"]
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        return {}, ["STRUCTURED_PROPOSAL_OUTPUT_FIELDS_INVALID"]
    blockers = _codes(payload.get("blockers"))
    if blockers is None:
        return {}, ["STRUCTURED_PROPOSAL_BLOCKERS_INVALID"]
    status = str(payload.get("status") or "").upper()
    if status == "NO_PROPOSAL":
        return {}, blockers or ["STRUCTURED_PROPOSAL_NOT_AVAILABLE"]
    if status != "PROPOSE":
        return {}, ["STRUCTURED_PROPOSAL_STATUS_INVALID"]
    if blockers:
        return {}, blockers
    reasons = _codes(payload.get("reason_codes"))
    if not reasons:
        return {}, ["STRUCTURED_PROPOSAL_REASON_CODES_MISSING"]
    payload["reason_codes"] = reasons
    return payload, []


def _reject_json_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def _make_proposal(payload, request, snapshot):
    order_type = str(payload.get("order_type") or "").upper()
    semantics = _ORDER_TYPE_SEMANTICS.get(order_type)
    if semantics is None:
        return None, ["STRUCTURED_PROPOSAL_ORDER_TYPE_INVALID"]
    side, entry_intent, action = semantics
    values, blockers = {}, []
    for name in ("entry_price", "trigger_price", "limit_price", "stop_loss", "take_profit", "proposed_volume"):
        values[name], valid = _number_text(payload.get(name))
        if not valid:
            blockers.append("STRUCTURED_PROPOSAL_" + name.upper() + "_INVALID")
    if action == "MARKET" and any(values[name] for name in ("entry_price", "trigger_price", "limit_price")):
        blockers.append("STRUCTURED_PROPOSAL_MARKET_PRICE_FIELDS_NOT_ALLOWED")
    elif entry_intent == "STOP_LIMIT":
        if not values["trigger_price"]:
            blockers.append("STRUCTURED_PROPOSAL_TRIGGER_PRICE_MISSING")
        if not values["limit_price"]:
            blockers.append("STRUCTURED_PROPOSAL_LIMIT_PRICE_MISSING")
        if values["entry_price"]:
            blockers.append("STRUCTURED_PROPOSAL_STOP_LIMIT_ENTRY_NOT_ALLOWED")
    elif action == "PENDING":
        if not values["entry_price"]:
            blockers.append("STRUCTURED_PROPOSAL_ENTRY_PRICE_MISSING")
        if values["trigger_price"] or values["limit_price"]:
            blockers.append("STRUCTURED_PROPOSAL_TRIGGER_LIMIT_NOT_ALLOWED")
    blockers.extend(_relation_blockers(order_type, values, snapshot))
    if blockers:
        return None, list(dict.fromkeys(blockers))
    return AutonomousOrderIntentProposal(
        symbol=request.runtime_context.symbol, side=side, entry_intent=entry_intent,
        order_type=order_type, proposed_action=action,
        entry_price=values["entry_price"], trigger_price=values["trigger_price"],
        limit_price=values["limit_price"], stop_loss=values["stop_loss"],
        take_profit=values["take_profit"], proposed_volume=values["proposed_volume"],
        risk_policy_reference=request.risk_decision.decision_id,
        structured_reasoning=tuple(payload["reason_codes"]),
    ), []


def _relation_blockers(order_type, values, snapshot):
    bid, ask = _number(snapshot.bid), _number(snapshot.ask)
    entry, trigger, limit = _number(values["entry_price"]), _number(values["trigger_price"]), _number(values["limit_price"])
    relations = {
        "BUY_LIMIT": entry is not None and entry < ask,
        "SELL_LIMIT": entry is not None and entry > bid,
        "BUY_STOP": entry is not None and entry > ask,
        "SELL_STOP": entry is not None and entry < bid,
        "BUY_STOP_LIMIT": trigger is not None and trigger > ask,
        "SELL_STOP_LIMIT": trigger is not None and trigger < bid,
    }
    blockers = []
    if order_type in relations and not relations[order_type]:
        blockers.append("STRUCTURED_PROPOSAL_MARKET_RELATION_INVALID")
    if order_type == "BUY_STOP_LIMIT" and trigger and limit and limit >= trigger:
        blockers.append("STRUCTURED_PROPOSAL_STOP_LIMIT_RELATION_INVALID")
    if order_type == "SELL_STOP_LIMIT" and trigger and limit and limit <= trigger:
        blockers.append("STRUCTURED_PROPOSAL_STOP_LIMIT_RELATION_INVALID")
    reference = ask if order_type == "BUY" else bid if order_type == "SELL" else limit if "STOP_LIMIT" in order_type else entry
    stop, take = _number(values["stop_loss"]), _number(values["take_profit"])
    if reference and order_type.startswith("BUY") and (
        (stop is not None and stop >= reference) or (take is not None and take <= reference)
    ):
        blockers.append("STRUCTURED_PROPOSAL_PROTECTION_INVALID")
    if reference and order_type.startswith("SELL") and (
        (stop is not None and stop <= reference) or (take is not None and take >= reference)
    ):
        blockers.append("STRUCTURED_PROPOSAL_PROTECTION_INVALID")
    return blockers


def _market_snapshot(request):
    feature, bundle = request.feature_result.feature_snapshot, request.feature_result.bundle
    return AutonomousOrderMarketSnapshot(
        snapshot_reference=bundle.bundle_id, observed_at=bundle.tick.timestamp,
        symbol=feature.symbol, broker_symbol=feature.broker_symbol,
        bid=bundle.tick.bid, ask=bundle.tick.ask,
        provider_name=bundle.provider_name,
        point=getattr(bundle.tick, "point", None),
        tick_size=getattr(bundle.tick, "tick_size", None),
        digits=getattr(bundle.tick, "digits", None),
        minimum_distance_points=getattr(bundle.tick, "minimum_distance_points", None),
        volume_min=getattr(bundle.tick, "volume_min", None),
        volume_max=getattr(bundle.tick, "volume_max", None),
        volume_step=getattr(bundle.tick, "volume_step", None),
        tick_value=getattr(bundle.tick, "tick_value", None),
        contract_size=getattr(bundle.tick, "contract_size", None),
        source_refs=tuple(dict.fromkeys((bundle.bundle_id, feature.feature_snapshot_id, *feature.source_snapshot_ids))),
    )


def _proposal_material(proposal):
    result = {name: getattr(proposal, name) for name in (
        "symbol", "side", "entry_intent", "order_type", "proposed_action",
        "entry_price", "trigger_price", "limit_price", "stop_loss",
        "take_profit", "proposed_volume", "risk_policy_reference",
    )}
    result["structured_reasoning"] = list(proposal.structured_reasoning)
    return result


def _bindings(request):
    feature = getattr(request.feature_result, "feature_snapshot", None)
    bundle = getattr(request.feature_result, "bundle", None)
    values = (
        getattr(feature, "feature_snapshot_id", ""),
        getattr(bundle, "bundle_id", ""),
        getattr(request.runtime_context, "context_pack_id", ""),
        getattr(request.method_selection, "result_id", ""),
        getattr(request.score_report, "score_report_id", ""),
        getattr(request.risk_decision, "decision_id", ""),
    )
    return tuple(value if isinstance(value, str) else "" for value in values)


def valid_autonomous_order_proposal_bindings(bindings) -> bool:
    return len(bindings) == 6 and all(_valid_source_identifier(item) for item in bindings)


def _valid_source_identifier(value) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(character.isspace() for character in value)
    )


def _blocked(request, blockers):
    return AutonomousOrderProposalResult(
        source_bindings=_bindings(request), blockers=tuple(dict.fromkeys(blockers))
    )


def _codes(value):
    if not isinstance(value, list):
        return None
    output = []
    for item in value:
        code = str(item or "").strip().upper()
        if not _CODE.fullmatch(code):
            return None
        if code not in output:
            output.append(code)
    return output


def _number_text(value):
    if value in (None, ""):
        return None, True
    if isinstance(value, bool):
        return None, False
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, False
    if not number.is_finite() or number <= 0:
        return None, False
    text = format(number, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text), True


def _number(value):
    text, valid = _number_text(value)
    return Decimal(text) if valid and text else None


def _fresh(value, now, maximum_age_seconds):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return -5 <= (_utc(now) - parsed.astimezone(timezone.utc)).total_seconds() <= maximum_age_seconds
    except (TypeError, ValueError):
        return False


def _utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
