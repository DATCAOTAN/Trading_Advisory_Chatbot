from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class MethodCard:
    method_id: str
    method_name: str
    source_type: str
    source_refs: List[str]
    domains: List[str] = field(default_factory=list)
    suitable_regimes: List[str] = field(default_factory=list)
    bad_regimes: List[str] = field(default_factory=list)
    required_features: List[str] = field(default_factory=list)
    confirmation_features: List[str] = field(default_factory=list)
    invalidation_features: List[str] = field(default_factory=list)
    preferred_timeframes: List[str] = field(default_factory=list)
    asset_scope: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class MacroCard:
    macro_id: str
    title: str
    source_type: str
    source_refs: List[str]
    event_type: str = ""
    affected_assets: List[str] = field(default_factory=list)
    affected_currencies: List[str] = field(default_factory=list)
    release_date: str = ""
    freshness: str = "UNKNOWN"
    key_points: List[str] = field(default_factory=list)
    gold_impact: str = ""
    usd_impact: str = ""
    uncertainty: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class StrategyPlaybook:
    playbook_id: str
    method_id: str
    name: str
    compatible_regimes: List[str]
    required_market_features: List[str] = field(default_factory=list)
    no_trade_conditions: List[str] = field(default_factory=list)
    confirmation_rules: List[str] = field(default_factory=list)
    invalidation_rules: List[str] = field(default_factory=list)
    preferred_timeframes: List[str] = field(default_factory=list)
    scoring_weights: Dict[str, float] = field(default_factory=dict)
    source_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class RegimeMethodMap:
    regime: str
    preferred_method_ids: List[str] = field(default_factory=list)
    supporting_method_ids: List[str] = field(default_factory=list)
    avoided_method_ids: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class RejectedKnowledgeItem:
    item_id: str
    item_type: str
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclass
class CandidateKnowledgeSet:
    symbol: str
    market_regime: str
    calendar_risk_state: str
    method_cards: List[MethodCard] = field(default_factory=list)
    macro_cards: List[MacroCard] = field(default_factory=list)
    strategy_playbooks: List[StrategyPlaybook] = field(default_factory=list)
    rejected_items: List[RejectedKnowledgeItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market_regime": self.market_regime,
            "calendar_risk_state": self.calendar_risk_state,
            "method_cards": [item.as_dict() for item in self.method_cards],
            "macro_cards": [item.as_dict() for item in self.macro_cards],
            "strategy_playbooks": [item.as_dict() for item in self.strategy_playbooks],
            "rejected_items": [item.as_dict() for item in self.rejected_items],
            "warnings": list(self.warnings),
            "source_refs": list(dict.fromkeys(self.source_refs)),
        }


@dataclass
class RuntimeContextPack:
    context_pack_id: str
    created_at: str
    mode: str
    symbol: str
    broker_symbol: str
    feature_snapshot_summary: Dict[str, Any]
    calendar_context_summary: Dict[str, Any]
    market_regime_summary: Dict[str, Any]
    selected_method_cards: List[Dict[str, Any]] = field(default_factory=list)
    selected_macro_cards: List[Dict[str, Any]] = field(default_factory=list)
    selected_playbooks: List[Dict[str, Any]] = field(default_factory=list)
    rejected_or_blocked_knowledge: List[Dict[str, Any]] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    token_budget_estimate: int = 0
    payload_size_chars: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "context_pack_id": self.context_pack_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "feature_snapshot_summary": dict(self.feature_snapshot_summary),
            "calendar_context_summary": dict(self.calendar_context_summary),
            "market_regime_summary": dict(self.market_regime_summary),
            "selected_method_cards": list(self.selected_method_cards),
            "selected_macro_cards": list(self.selected_macro_cards),
            "selected_playbooks": list(self.selected_playbooks),
            "rejected_or_blocked_knowledge": list(self.rejected_or_blocked_knowledge),
            "source_refs": list(dict.fromkeys(self.source_refs)),
            "warnings": list(dict.fromkeys(self.warnings)),
            "blockers": list(dict.fromkeys(self.blockers)),
            "token_budget_estimate": int(self.token_budget_estimate),
            "payload_size_chars": int(self.payload_size_chars),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _asdict(obj: Any) -> Dict[str, Any]:
    data = dict(obj.__dict__)
    if "confidence" in data:
        data["confidence"] = _clamp(data["confidence"])
    for key, value in list(data.items()):
        if isinstance(value, list):
            data[key] = list(value)
        elif isinstance(value, dict):
            data[key] = dict(value)
    return data


def _clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0
