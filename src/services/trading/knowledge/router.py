from __future__ import annotations

from typing import Iterable

from src.config import Config
from src.services.trading.calendar.models import CalendarContext
from src.services.trading.knowledge.models import (
    CandidateKnowledgeSet,
    MacroCard,
    MethodCard,
    RejectedKnowledgeItem,
    RegimeMethodMap,
    StrategyPlaybook,
)
from src.services.trading.knowledge.stores import MacroCardStore, MethodCardStore, RegimeMethodMapStore, StrategyPlaybookStore
from src.services.trading.market.feature_models import FeatureSnapshot
from src.services.trading.market.regime_models import MarketRegimeSnapshot


class KnowledgeRouter:
    def __init__(
        self,
        method_store: MethodCardStore | None = None,
        macro_store: MacroCardStore | None = None,
        playbook_store: StrategyPlaybookStore | None = None,
        regime_map_store: RegimeMethodMapStore | None = None,
    ):
        self.method_store = method_store or MethodCardStore()
        self.macro_store = macro_store or MacroCardStore()
        self.playbook_store = playbook_store or StrategyPlaybookStore()
        self.regime_map_store = regime_map_store or RegimeMethodMapStore()

    def route(
        self,
        mode: str,
        symbol: str,
        feature_snapshot: FeatureSnapshot,
        calendar_context: CalendarContext,
        market_regime: MarketRegimeSnapshot,
        user_selected_method_id: str | None = None,
        user_intent: str | None = None,
    ) -> CandidateKnowledgeSet:
        methods = self.method_store.load_all()
        macros = self.macro_store.load_all()
        playbooks = self.playbook_store.load_all()
        regime_maps = self.regime_map_store.load_all()
        warnings = (
            list(self.method_store.warnings)
            + list(self.macro_store.warnings)
            + list(self.playbook_store.warnings)
            + list(self.regime_map_store.warnings)
        )
        rejected: list[RejectedKnowledgeItem] = []
        normalized_mode = str(mode or "advisory_only").strip().lower()
        primary_regime = market_regime.primary_regime

        if normalized_mode == "human_confirmed_live":
            selected_methods = self._route_human_confirmed(methods, user_selected_method_id, rejected)
        elif normalized_mode == "autonomous_live":
            selected_methods = self._route_by_regime(methods, regime_maps, primary_regime, feature_snapshot, symbol, rejected)
        elif normalized_mode == "manage_existing_position":
            selected_methods = self._route_manage_position(methods, rejected)
        elif normalized_mode == "learning_review":
            selected_methods = self._route_learning_review(methods, rejected)
        else:
            selected_methods = self._route_advisory(methods, primary_regime, feature_snapshot, symbol, user_intent, rejected)

        selected_methods = _limit(selected_methods, int(getattr(Config, "KNOWLEDGE_MAX_METHOD_CARDS", 3)))
        method_ids = {item.method_id for item in selected_methods}
        selected_playbooks = self._select_playbooks(playbooks, method_ids, primary_regime, normalized_mode, rejected)
        selected_playbooks = _limit(selected_playbooks, int(getattr(Config, "KNOWLEDGE_MAX_PLAYBOOKS", 3)))
        selected_macros = self._select_macros(macros, symbol, calendar_context, market_regime, normalized_mode)
        selected_macros = _limit(selected_macros, int(getattr(Config, "KNOWLEDGE_MAX_MACRO_CARDS", 3)))
        source_refs = _source_refs(selected_methods, selected_macros, selected_playbooks)
        if not source_refs:
            warnings.append("candidate_source_refs_empty")

        return CandidateKnowledgeSet(
            symbol=str(symbol or "XAUUSD").upper(),
            market_regime=primary_regime,
            calendar_risk_state=calendar_context.calendar_risk_state,
            method_cards=selected_methods,
            macro_cards=selected_macros,
            strategy_playbooks=selected_playbooks,
            rejected_items=rejected,
            warnings=list(dict.fromkeys(warnings)),
            source_refs=source_refs,
        )

    def _route_human_confirmed(
        self,
        methods: list[MethodCard],
        user_selected_method_id: str | None,
        rejected: list[RejectedKnowledgeItem],
    ) -> list[MethodCard]:
        if not user_selected_method_id:
            return methods[:1]
        selected = [item for item in methods if item.method_id == user_selected_method_id]
        for item in methods:
            if item.method_id != user_selected_method_id:
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", "human_confirmed_primary_method_locked"))
        return selected

    def _route_by_regime(
        self,
        methods: list[MethodCard],
        maps: list[RegimeMethodMap],
        regime: str,
        feature: FeatureSnapshot,
        symbol: str,
        rejected: list[RejectedKnowledgeItem],
    ) -> list[MethodCard]:
        regime_map = next((item for item in maps if item.regime == regime), None)
        preferred = list(regime_map.preferred_method_ids if regime_map else [])
        supporting = list(regime_map.supporting_method_ids if regime_map else [])
        avoided = set(regime_map.avoided_method_ids if regime_map else [])
        selected: list[MethodCard] = []
        for method_id in preferred + supporting:
            method = next((item for item in methods if item.method_id == method_id), None)
            if not method:
                continue
            if method.method_id in avoided or regime in method.bad_regimes:
                rejected.append(RejectedKnowledgeItem(method.method_id, "method_card", f"bad_regime:{regime}"))
                continue
            if not _asset_matches(method.asset_scope, symbol):
                rejected.append(RejectedKnowledgeItem(method.method_id, "method_card", "asset_scope_mismatch"))
                continue
            if not _required_features_available(method.required_features, feature):
                rejected.append(RejectedKnowledgeItem(method.method_id, "method_card", "required_features_missing"))
                continue
            selected.append(method)
        if not selected:
            selected = self._route_advisory(methods, regime, feature, symbol, None, rejected)
        return selected

    def _route_manage_position(self, methods: list[MethodCard], rejected: list[RejectedKnowledgeItem]) -> list[MethodCard]:
        selected = [item for item in methods if "risk" in item.domains or "risk" in item.method_id]
        for item in methods:
            if item not in selected:
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", "manage_position_prioritizes_risk"))
        return selected

    def _route_learning_review(self, methods: list[MethodCard], rejected: list[RejectedKnowledgeItem]) -> list[MethodCard]:
        selected = [item for item in methods if "risk" in item.domains or "review" in item.domains or "learning" in item.domains]
        return selected or methods[:1]

    def _route_advisory(
        self,
        methods: list[MethodCard],
        regime: str,
        feature: FeatureSnapshot,
        symbol: str,
        user_intent: str | None,
        rejected: list[RejectedKnowledgeItem],
    ) -> list[MethodCard]:
        intent = str(user_intent or "").lower()
        selected: list[MethodCard] = []
        for item in methods:
            if not _asset_matches(item.asset_scope, symbol):
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", "asset_scope_mismatch"))
                continue
            if regime in item.bad_regimes:
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", f"bad_regime:{regime}"))
                continue
            if intent and not _matches_intent(item, intent):
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", "intent_mismatch"))
                continue
            if item.suitable_regimes and regime not in item.suitable_regimes and regime != "UNKNOWN":
                continue
            if not _required_features_available(item.required_features, feature):
                rejected.append(RejectedKnowledgeItem(item.method_id, "method_card", "required_features_missing"))
                continue
            selected.append(item)
        return selected or methods[:1]

    def _select_playbooks(
        self,
        playbooks: list[StrategyPlaybook],
        method_ids: set[str],
        regime: str,
        mode: str,
        rejected: list[RejectedKnowledgeItem],
    ) -> list[StrategyPlaybook]:
        selected: list[StrategyPlaybook] = []
        for playbook in playbooks:
            if mode == "manage_existing_position" and not _contains_any(playbook.no_trade_conditions + playbook.invalidation_rules, ["risk", "volatility", "calendar", "regime"]):
                rejected.append(RejectedKnowledgeItem(playbook.playbook_id, "strategy_playbook", "manage_position_playbook_mismatch"))
                continue
            if method_ids and playbook.method_id not in method_ids:
                rejected.append(RejectedKnowledgeItem(playbook.playbook_id, "strategy_playbook", "method_not_selected"))
                continue
            if playbook.compatible_regimes and regime not in playbook.compatible_regimes and "ANY" not in playbook.compatible_regimes:
                rejected.append(RejectedKnowledgeItem(playbook.playbook_id, "strategy_playbook", f"regime_mismatch:{regime}"))
                continue
            selected.append(playbook)
        return selected

    def _select_macros(
        self,
        macros: list[MacroCard],
        symbol: str,
        calendar: CalendarContext,
        regime: MarketRegimeSnapshot,
        mode: str,
    ) -> list[MacroCard]:
        selected: list[MacroCard] = []
        risk_state = calendar.calendar_risk_state
        for item in macros:
            asset_scope = {str(value).upper() for value in item.affected_assets}
            generic_asset = not asset_scope or "ALL" in asset_scope
            usd_macro = "USD" in {value.upper() for value in item.affected_currencies}
            if _asset_matches(item.affected_assets, symbol) or (generic_asset and usd_macro):
                selected.append(item)
        if regime.primary_regime == "NEWS_RISK" or risk_state in {"UPCOMING_HIGH_IMPACT", "IMMEDIATE_HIGH_IMPACT", "EVENT_ACTIVE", "POST_EVENT_COOLDOWN"}:
            news_cards = [item for item in selected if "calendar" in item.event_type.lower() or "risk" in item.title.lower()]
            selected = news_cards + [item for item in selected if item not in news_cards]
        deduped: list[MacroCard] = []
        seen: set[str] = set()
        for item in selected:
            if item.macro_id not in seen:
                seen.add(item.macro_id)
                deduped.append(item)
        return deduped


def _asset_matches(values: Iterable[str], symbol: str) -> bool:
    scope = {str(item).upper() for item in values}
    return not scope or "ALL" in scope or str(symbol or "").upper() in scope


def _required_features_available(required: Iterable[str], feature: FeatureSnapshot) -> bool:
    for name in required:
        value = getattr(feature, str(name), None)
        if value is None or value == "" or value == "UNKNOWN":
            return False
        if isinstance(value, (list, dict)) and not value:
            return False
    return True


def _matches_intent(method: MethodCard, intent: str) -> bool:
    haystack = " ".join([method.method_id, method.method_name] + method.domains).lower()
    return any(token for token in intent.split() if token in haystack)


def _contains_any(values: Iterable[str], tokens: Iterable[str]) -> bool:
    text = " ".join(str(item).lower() for item in values)
    return any(token in text for token in tokens)


def _limit(items: list, count: int) -> list:
    return list(items[: max(0, count)])


def _source_refs(methods: list[MethodCard], macros: list[MacroCard], playbooks: list[StrategyPlaybook]) -> list[str]:
    refs: list[str] = []
    for item in list(methods) + list(macros) + list(playbooks):
        refs.extend(str(ref) for ref in getattr(item, "source_refs", []) if ref)
    return list(dict.fromkeys(refs))
